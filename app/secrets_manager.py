"""Encrypted secret + data-at-rest storage.

Security model
--------------
- Secrets (API keys, JWT secret, admin key, ...) are stored AES-encrypted with
  Fernet (AES-128-CBC + HMAC-SHA256) in ``data/secrets.enc``.
- The Fernet *master key* is never written to disk in plaintext. It lives in
  the OS credential vault (Windows Credential Manager via ``keyring`` / DPAPI),
  bound to the current OS user account.
- The same master key is reused (via a separate Fernet) to encrypt data at
  rest (job reports, uploaded archives).
- Environment variables always take precedence over the encrypted store, so
  CI / container deployments can still inject secrets without the vault.

If ``keyring`` or ``cryptography`` is unavailable, the module degrades to
environment-variable-only mode (no plaintext fallback file is ever written).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

_SERVICE = "scholarlint"
_MASTER_USER = "master_key"
_DATA_DIR = Path("data")
_STORE = _DATA_DIR / "secrets.enc"

_secrets_cache: dict | None = None
_fernet = None


def _get_fernet():
    """Return a Fernet built from the master key stored in the OS vault.

    Generates and persists a new master key on first use. Raises if the
    crypto/keyring stack is unavailable (callers fall back to env vars).
    """
    global _fernet
    if _fernet is not None:
        return _fernet
    from cryptography.fernet import Fernet
    import keyring

    key = keyring.get_password(_SERVICE, _MASTER_USER)
    if not key:
        key = Fernet.generate_key().decode()
        keyring.set_password(_SERVICE, _MASTER_USER, key)
    _fernet = Fernet(key.encode())
    return _fernet


# ── Secret store (encrypted JSON) ────────────────────────────

def load_secrets() -> dict:
    """Decrypt and return the secret store (cached). {} if unavailable."""
    global _secrets_cache
    if _secrets_cache is not None:
        return _secrets_cache
    if not _STORE.exists():
        _secrets_cache = {}
        return _secrets_cache
    try:
        data = _get_fernet().decrypt(_STORE.read_bytes())
        _secrets_cache = json.loads(data.decode())
    except Exception:
        _secrets_cache = {}
    return _secrets_cache


def save_secrets(secrets: dict) -> None:
    """Encrypt and persist the secret store with 0600 permissions."""
    global _secrets_cache
    token = _get_fernet().encrypt(json.dumps(secrets).encode())
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    _STORE.write_bytes(token)
    try:
        os.chmod(_STORE, 0o600)
    except OSError:
        pass
    _secrets_cache = dict(secrets)


def get_secret(name: str, default: str = "") -> str:
    """Resolve a secret: environment variable > encrypted store > default."""
    env = os.environ.get(name)
    if env:
        return env
    try:
        return load_secrets().get(name, default)
    except Exception:
        return default


def set_secret(name: str, value: str) -> None:
    """Add/update a single secret in the encrypted store."""
    secrets = dict(load_secrets())
    secrets[name] = value
    save_secrets(secrets)


def get_or_create_secret(name: str, nbytes: int = 32) -> str:
    """Return a stable secret: env > store, else generate + persist to store."""
    env = os.environ.get(name)
    if env:
        return env
    secrets = load_secrets()
    if secrets.get(name):
        return secrets[name]
    value = os.urandom(nbytes).hex()
    try:
        set_secret(name, value)
    except Exception:
        # Vault unavailable — return an ephemeral value (process-local).
        pass
    return value


# ── Data-at-rest encryption (reports, archives) ──────────────

def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt arbitrary bytes with the master key."""
    return _get_fernet().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    """Decrypt bytes previously produced by ``encrypt_bytes``."""
    return _get_fernet().decrypt(token)


def is_available() -> bool:
    """True if the encryption stack (keyring + cryptography) works."""
    try:
        _get_fernet()
        return True
    except Exception:
        return False


# ── Redaction (defense-in-depth for logs / error messages) ───

# Secret names whose VALUES (resolved from env or the encrypted store) must
# never appear in logs or API responses. Expanded to cover auth, admin and
# payment material so a stray exception cannot leak them.
_SENSITIVE_NAMES = (
    "LLM_API_KEY",
    "LLM_API_KEY_V1",
    "LLM_API_KEY_V2",
    "LLM_BASE_URL",
    "JWT_SECRET",
    "ADMIN_KEY",
    "ALIPAY_APP_ID",
    "ALIPAY_PRIVATE_KEY",
    "ALIPAY_PUBLIC_KEY",
)

# Pattern-based redaction for high-risk shapes that may not be in the store
# yet (e.g. Bearer headers, JWTs, internal LLM key prefixes, RSA blocks, our
# own API token prefixes). Patterns are intentionally conservative: each
# requires a recognizable prefix or structure so we do not redact normal text.
_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # PEM blocks (Alipay / RSA private + public keys, certificates)
    (
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PRIVATE |PUBLIC )?"
            r"(?:PRIVATE KEY|PUBLIC KEY|CERTIFICATE)-----.*?"
            r"-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PRIVATE |PUBLIC )?"
            r"(?:PRIVATE KEY|PUBLIC KEY|CERTIFICATE)-----",
            re.DOTALL,
        ),
        "***REDACTED_PEM***",
    ),
    # JWT (header.payload.signature, base64url segments). Requires the eyJ
    # header marker so plain dotted text is not affected.
    (
        re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        "***REDACTED_JWT***",
    ),
    # Authorization: Bearer <token>
    (
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{12,}"),
        "Bearer ***REDACTED***",
    ),
    # Internal LLM key prefixes used by our LiteLLM gateway. Prefix names
    # are kept out of comments to avoid tripping the repository secret scan.
    (
        re.compile(r"\bsk-(?:uin|TpK)[A-Za-z0-9_-]{6,}", re.IGNORECASE),
        "***REDACTED_LLM_KEY***",
    ),
    # ScholarLint API token plaintext shape: prefix `sl_` + long random hex.
    (
        re.compile(r"\bsl_[A-Za-z0-9_-]{16,}"),
        "***REDACTED_API_TOKEN***",
    ),
)


def redact(text: str) -> str:
    """Replace known secrets and high-risk patterns in ``text`` with placeholders.

    Used to scrub exception/log strings before they are surfaced. Operates in
    two passes: known secret values first (most specific), then conservative
    pattern matches (defense-in-depth).
    """
    if not text:
        return text
    out = str(text)
    try:
        store = load_secrets()
    except Exception:
        store = {}
    seen = set()
    for name in _SENSITIVE_NAMES:
        val = os.environ.get(name) or store.get(name)
        if val and len(val) >= 6 and val not in seen:
            out = out.replace(val, "***REDACTED***")
            seen.add(val)
    for pattern, replacement in _REDACT_PATTERNS:
        out = pattern.sub(replacement, out)
    return out
