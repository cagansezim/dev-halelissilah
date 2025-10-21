# apps/gateway/deps.py
from __future__ import annotations

import os
from functools import lru_cache

from packages.shared.settings import settings, Settings
from packages.clients.internal_api.client import InternalAPIClient
from packages.storage.s3_store import S3Store

# AV alias (module name may vary in your tree)
try:
    from packages.shared.av import AVScanner as AVClient
except Exception:
    from packages.shared.av import AVClient  # type: ignore

__all__ = [
    "get_settings",
    "get_internal_client",
    "get_s3_store",
    "get_s3",
    "get_av",
    "get_engine",
    "get_sessions",
]


# ---------------- Sessions (proxy) ----------------
def get_sessions():
    """
    Proxy to the session store factory so callers can import from apps.gateway.deps
    without creating import cycles.
    """
    # Import inside the function to avoid circular imports at module import time
    from apps.gateway.session import get_sessions as _get_sessions  # type: ignore
    return _get_sessions()


# ---------------- Engine (proxy) ----------------
def get_engine():
    """
    Proxy to the engine factory so callers can import from apps.gateway.deps.
    Keeps pipeline_router stable.
    """
    # Import inside the function to avoid import-time cycles
    from apps.gateway.engine import get_engine as _get_engine  # type: ignore
    return _get_engine()


# ---------------- Settings ----------------
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return settings


# ---------------- Internal API client ----------------
@lru_cache(maxsize=1)
def get_internal_client() -> InternalAPIClient:
    s = get_settings()
    return InternalAPIClient(
        base_url=str(s.INTERNAL_API_BASE),
        auth_url=s.INTERNAL_API_AUTH_PATH,
        list_url=s.INTERNAL_API_LIST_PATH,
        json_url=s.INTERNAL_API_JSON_PATH,
        file_url=s.INTERNAL_API_FILE_PATH,
        email=s.INTERNAL_API_USERNAME.get_secret_value(),
        password=s.INTERNAL_API_PASSWORD.get_secret_value(),
        timeout=s.INTERNAL_API_TIMEOUT_SEC,
    )


# ---------------- S3 store (lazy singleton) ----------------
_s3: S3Store | None = None

def get_s3() -> S3Store:  # backward-compat alias
    return get_s3_store()

def get_s3_store() -> S3Store:
    global _s3
    if _s3 is None:
        s = get_settings()
        _s3 = S3Store(
            endpoint=s.S3_ENDPOINT,
            access_key=s.S3_ACCESS_KEY,
            secret_key=s.S3_SECRET_KEY,
            bucket=s.S3_BUCKET,
            region=s.S3_REGION,
        )
        # Don’t fail import-time; just try to ensure the bucket exists.
        try:
            _s3.ensure_bucket(create_if_missing=True)
        except Exception:
            pass
    return _s3


# ---------------- AV client (lazy singleton) ----------------
_av: AVClient | None = None

def get_av() -> AVClient:
    global _av
    if _av is None:
        s = get_settings()
        _av = AVClient(host=s.CLAMAV_HOST, port=s.CLAMAV_PORT, required=s.AV_REQUIRED)
    return _av
