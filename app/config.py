"""Application configuration."""

import os
from pathlib import Path

from pydantic import BaseModel

try:
    from dotenv import load_dotenv

    # Load secrets from .env (gitignored). Never hardcode keys in this file —
    # config.py is tracked by git and would leak to GitHub.
    load_dotenv()
except ImportError:
    pass

_DATA_DIR = Path("data")


def _load_or_create_secret(env_var: str, file_name: str, nbytes: int = 32) -> str:
    """Return a stable secret.

    Priority: explicit env var > persisted file under data/ > newly generated
    (then persisted). Persisting avoids invalidating all issued JWTs / admin
    keys on every restart while keeping secrets out of source control.
    """
    explicit = os.environ.get(env_var)
    if explicit:
        return explicit
    secret_path = _DATA_DIR / file_name
    try:
        if secret_path.exists():
            value = secret_path.read_text(encoding="utf-8").strip()
            if value:
                return value
        secret = os.urandom(nbytes).hex()
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        secret_path.write_text(secret, encoding="utf-8")
        try:
            os.chmod(secret_path, 0o600)
        except OSError:
            pass
        return secret
    except OSError:
        # Last resort: ephemeral secret (still functional within one process)
        return os.urandom(nbytes).hex()


class Settings(BaseModel):
    """Application settings."""

    # Paths
    upload_dir: Path = Path("uploads")
    data_dir: Path = Path("data")

    # Crossref API
    crossref_base_url: str = "https://api.crossref.org"
    crossref_email: str = "mengzehong@example.com"  # polite pool
    crossref_timeout: float = 10.0
    crossref_max_concurrent: int = 5

    # LLM (internal LiteLLM) — keys MUST come from .env / environment, never hardcoded
    llm_api_key: str = os.environ.get("LLM_API_KEY", "")
    llm_base_url: str = os.environ.get("LLM_BASE_URL", "http://REMOVED_HOST")
    llm_model: str = os.environ.get("LLM_MODEL", "gpt-5.2")

    # Gate thresholds
    reference_confidence_threshold: float = 60.0  # below this = FAIL
    max_missing_doi_ratio: float = 0.0  # 0 = every entry MUST have DOI

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Auth & Billing
    jwt_secret: str = _load_or_create_secret("JWT_SECRET", ".jwt_secret", 32)
    jwt_expire_days: int = 7

    # Credits pricing (1 credit = 1 full check)
    credits_upload: int = 1      # 完整质检 = 1 次
    credits_recheck: int = 0     # 重新质检免费（已付过了）
    credits_ai_fix: int = 0      # AI 修复免费（增值体验）
    credits_bib_clean: int = 0   # 工具类免费
    credits_tidyup: int = 0      # 工具类免费

    # Payment
    payment_sandbox: bool = os.environ.get("PAYMENT_SANDBOX", "true").lower() == "true"
    alipay_app_id: str = os.environ.get("ALIPAY_APP_ID", "")
    alipay_private_key: str = os.environ.get("ALIPAY_PRIVATE_KEY", "")
    alipay_public_key: str = os.environ.get("ALIPAY_PUBLIC_KEY", "")

    # Admin
    admin_key: str = _load_or_create_secret("ADMIN_KEY", ".admin_key", 16)


settings = Settings()
