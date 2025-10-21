# packages/shared/settings.py
from __future__ import annotations

from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyUrl, SecretStr, Field, AliasChoices


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------ Internal API base & endpoints ------------
    INTERNAL_API_BASE: AnyUrl = "https://pruva.usbcertification.com"

    # These are PATHS (not full URLs)
    INTERNAL_API_AUTH_PATH: str = "/api/authentication.php"
    INTERNAL_API_LIST_PATH: str = "/api/ai/textile/masraflar/Api.php?action=list"
    INTERNAL_API_JSON_PATH: str = "/api/ai/textile/masraflar/Api.php?action=json"
    INTERNAL_API_FILE_PATH: str = "/api/ai/textile/masraflar/Api.php?action=file"

    INTERNAL_API_LANG: Literal["EN", "TR"] = "EN"

    # Support either INTERNAL_API_USERNAME or INTERNAL_API_EMAIL from env
    INTERNAL_API_USERNAME: SecretStr = Field(
        default=SecretStr("hakanoktay@bpm.com.tr"),
        validation_alias=AliasChoices("INTERNAL_API_USERNAME", "INTERNAL_API_EMAIL"),
    )
    INTERNAL_API_PASSWORD: SecretStr = SecretStr("K0l@Y8lS!N?%#!")

    # Optional HMAC (not enforced by client unless you wire a scheme)
    INTERNAL_API_HMAC_KEY_ID: Optional[str] = ""
    INTERNAL_API_HMAC_SECRET: Optional[SecretStr] = None

    INTERNAL_API_TIMEOUT_SEC: int = 30
    INTERNAL_API_MAX_RETRIES: int = 3
    INTERNAL_API_BACKOFF_MS: int = 250

    # ------------ Object Storage (MinIO/S3) ------------
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "pruva-files"
    S3_REGION: str = "us-east-1"
    S3_DATASET_PREFIX: str = "dataset"   # <-- ADD THE TYPE (this line fixes the crash)

    # ------------ Antivirus ------------
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310
    AV_REQUIRED: bool = False

    # ------------ Gateway ------------
    GATEWAY_HOST: str = "0.0.0.0"
    GATEWAY_PORT: int = 8080


settings = Settings()
