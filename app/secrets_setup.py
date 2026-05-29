"""One-time secret setup / migration tool.

Usage:
    python -m app.secrets_setup            # migrate from .env + old files, then
                                           # remove the plaintext copies
    python -m app.secrets_setup --set KEY  # interactively set a single secret
    python -m app.secrets_setup --show     # list which secret names are stored
                                           # (values are never printed)

After migration the API key / JWT secret / admin key live only in the
AES-encrypted store (data/secrets.enc) with the master key in the OS vault.
"""

from __future__ import annotations

import sys
from pathlib import Path

from app import secrets_manager as sm

# Secret names we know how to migrate out of the legacy plaintext .env file.
_ENV_KEYS = ["LLM_API_KEY", "LLM_API_KEY_V1", "LLM_API_KEY_V2", "LLM_BASE_URL", "LLM_MODEL"]
_LEGACY_FILES = {"JWT_SECRET": Path("data/.jwt_secret"), "ADMIN_KEY": Path("data/.admin_key")}


def _mask(v: str) -> str:
    if not v:
        return "(empty)"
    return v[:3] + "…" + v[-2:] if len(v) > 6 else "***"


def migrate() -> None:
    if not sm.is_available():
        print("ERROR: encryption backend (keyring + cryptography) unavailable.")
        sys.exit(1)

    migrated = []

    # 1. Pull values from .env (without polluting the real environment).
    env_path = Path(".env")
    if env_path.exists():
        try:
            from dotenv import dotenv_values
            env = dotenv_values(env_path)
        except Exception:
            env = {}
        for name in _ENV_KEYS:
            val = (env or {}).get(name)
            if val:
                sm.set_secret(name, val)
                migrated.append(name)

    # 2. Pull legacy plaintext secret files.
    for name, path in _LEGACY_FILES.items():
        if path.exists():
            val = path.read_text(encoding="utf-8").strip()
            if val:
                sm.set_secret(name, val)
                migrated.append(name)

    print("Migrated into encrypted store:", ", ".join(migrated) if migrated else "(nothing found)")
    for n in migrated:
        print(f"  {n} = {_mask(sm.get_secret(n))}")

    # 3. Remove plaintext copies now that they are encrypted.
    removed = []
    for _, path in _LEGACY_FILES.items():
        if path.exists():
            path.unlink()
            removed.append(str(path))
    if env_path.exists():
        env_path.unlink()
        removed.append(".env")
    if removed:
        print("Removed plaintext files:", ", ".join(removed))
    print("\nDone. Secrets are now AES-encrypted in data/secrets.enc; master key in OS vault.")


def set_one(name: str) -> None:
    import getpass
    value = getpass.getpass(f"Enter value for {name} (hidden): ").strip()
    if not value:
        print("No value entered, aborting.")
        return
    sm.set_secret(name, value)
    print(f"Stored {name} = {_mask(value)} (encrypted).")


def show() -> None:
    names = sorted(sm.load_secrets().keys())
    print("Stored secret names:", ", ".join(names) if names else "(none)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--set" and len(args) >= 2:
        set_one(args[1])
    elif args and args[0] == "--show":
        show()
    else:
        migrate()
