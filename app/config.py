"""Application configuration.

Secrets (LLM key, endpoint, JWT, admin key, payment keys) are resolved via the
encrypted secret store (``app.secrets_manager``): environment variable first,
then the AES-encrypted ``data/secrets.enc`` (master key in the OS vault). No
secret is ever hardcoded here — config.py is tracked by git.
"""

import os
from pathlib import Path

from pydantic import BaseModel

try:
    from dotenv import load_dotenv

    # Legacy/local convenience only. The canonical store is encrypted; run
    # `python -m app.secrets_setup` to migrate any .env secrets and remove it.
    load_dotenv()
except ImportError:
    pass

from app.secrets_manager import get_secret, get_or_create_secret

# LLM usage caps (anti-abuse / cost control)
LLM_RATE_PER_IP = int(os.environ.get("LLM_RATE_PER_IP", "30"))      # per IP per window
LLM_RATE_WINDOW = int(os.environ.get("LLM_RATE_WINDOW", "3600"))    # seconds
LLM_GLOBAL_HOURLY_CAP = int(os.environ.get("LLM_GLOBAL_HOURLY_CAP", "500"))


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

    # LLM (internal LiteLLM) — key AND base_url are sensitive; from encrypted store.
    llm_api_key: str = get_secret("LLM_API_KEY", "")
    llm_base_url: str = get_secret("LLM_BASE_URL", "")
    llm_model: str = get_secret("LLM_MODEL", "gpt-5.2")

    # Gate thresholds
    reference_confidence_threshold: float = 60.0  # below this = FAIL
    max_missing_doi_ratio: float = 0.0  # 0 = every entry MUST have DOI

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    app_env: str = os.environ.get("APP_ENV", "local").lower()

    # Auth & Billing — generated + persisted to the encrypted store if absent.
    jwt_secret: str = get_or_create_secret("JWT_SECRET", 32)
    jwt_expire_days: int = 7

    # Credits pricing (1 credit = 1 full check)
    credits_upload: int = 1      # 完整质检 = 1 次
    credits_recheck: int = 0     # 重新质检免费（已付过了）
    credits_ai_fix: int = 0      # AI 修复免费（增值体验）
    credits_bib_clean: int = 0   # 工具类免费
    credits_tidyup: int = 0      # 工具类免费

    # Payment
    payment_sandbox: bool = os.environ.get("PAYMENT_SANDBOX", "true").lower() == "true"
    alipay_app_id: str = get_secret("ALIPAY_APP_ID", "")
    alipay_private_key: str = get_secret("ALIPAY_PRIVATE_KEY", "")
    alipay_public_key: str = get_secret("ALIPAY_PUBLIC_KEY", "")

    # Admin
    admin_key: str = get_or_create_secret("ADMIN_KEY", 16)


settings = Settings()
