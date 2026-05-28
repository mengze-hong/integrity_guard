"""Application configuration."""

from pathlib import Path
from pydantic import BaseModel


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

    # LLM (internal LiteLLM)
    llm_api_key: str = "***REMOVED_LLM_API_KEY***"
    llm_base_url: str = "http://REMOVED_HOST/v1"
    llm_model: str = "gpt-5.2"

    # Gate thresholds
    reference_confidence_threshold: float = 60.0  # below this = FAIL
    max_missing_doi_ratio: float = 0.0  # 0 = every entry MUST have DOI

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Auth & Billing
    jwt_secret: str = "***REMOVED_JWT_SECRET***"
    jwt_expire_days: int = 7

    # Credits pricing (1 credit = 1 full check)
    credits_upload: int = 1      # 完整质检 = 1 次
    credits_recheck: int = 0     # 重新质检免费（已付过了）
    credits_ai_fix: int = 0      # AI 修复免费（增值体验）
    credits_bib_clean: int = 0   # 工具类免费
    credits_tidyup: int = 0      # 工具类免费

    # Payment
    payment_sandbox: bool = True  # True = auto-complete payments (testing mode)
    alipay_app_id: str = ""
    alipay_private_key: str = ""
    alipay_public_key: str = ""


settings = Settings()
