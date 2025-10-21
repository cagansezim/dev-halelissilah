from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Storage / queue
    REDIS_URL: str = "redis://localhost:6379/0"
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "pruva-files"
    S3_USE_SSL: bool = False

    # LLM (OpenAI-compatible)
    VLLM_BASE_URL: str = "http://localhost:11434"
    VLLM_API_KEY: str = ""

    # Strategy / models
    PIPELINE_STRATEGY: str = "both_merge"
    OCR_ENGINES: str = "paddleocr,tesseract"
    TEXT_MODELS: str = "mixtral:8x7b-instruct,llama3.1:70b-instruct"
    VISION_MODELS: str = "docowl-2,qwen-vl-7b"
    TABLES: str = "off"
    CONF_THRESHOLD: float = 0.90
    AUTO_APPROVE: bool = True
    FIRST_VENDOR_APPROVALS: int = 3
    DPI: int = 200
    MAX_PAGES_PER_BATCH: int = 4

    # Internal API (aligns with packages/clients/internal_api/client.py)
    INTERNAL_API_BASE: str = ""
    INTERNAL_API_AUTH_PATH: str = "/auth/login"
    INTERNAL_API_LIST_PATH: str = "/expenses/list"
    INTERNAL_API_JSON_PATH: str = "/expenses/json"
    INTERNAL_API_FILE_PATH: str = "/expenses/file"
    INTERNAL_API_EMAIL: str = ""
    INTERNAL_API_PASSWORD: str = ""
    INTERNAL_API_TIMEOUT_SEC: int = 30
    INTERNAL_API_MAX_RETRIES: int = 3
    INTERNAL_API_BACKOFF_MS: int = 250

    # Optional webhooks
    WEBHOOK_NEEDS_REVIEW: str = ""
    WEBHOOK_DONE: str = ""

    # HF token for local transformers (future-proof)


    class Config:
        env_prefix = ""
        case_sensitive = False

settings = Settings()
