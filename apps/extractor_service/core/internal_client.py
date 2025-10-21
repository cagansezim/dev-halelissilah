from __future__ import annotations
import time
from typing import Optional, Callable, Any
from ..config import settings
from packages.clients.internal_api.client import InternalAPIClient  # type: ignore

_client: Optional[InternalAPIClient] = None

def _with_retries(fn: Callable[[], Any]) -> Any:
    retries = max(0, int(settings.INTERNAL_API_MAX_RETRIES))
    backoff = max(0, int(settings.INTERNAL_API_BACKOFF_MS)) / 1000.0
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(backoff)

def get_internal_client() -> Optional[InternalAPIClient]:
    global _client
    if not settings.INTERNAL_API_BASE or not settings.INTERNAL_API_EMAIL:
        return None
    if _client is None:
        _client = InternalAPIClient(
            base_url=settings.INTERNAL_API_BASE,
            auth_url=settings.INTERNAL_API_AUTH_PATH,
            list_url=settings.INTERNAL_API_LIST_PATH,
            json_url=settings.INTERNAL_API_JSON_PATH,
            file_url=settings.INTERNAL_API_FILE_PATH,
            email=settings.INTERNAL_API_EMAIL,
            password=settings.INTERNAL_API_PASSWORD,
            timeout=int(settings.INTERNAL_API_TIMEOUT_SEC),
        )
    return _client

def api_list_expenses(start_date: str, end_date: str):
    cli = get_internal_client()
    if not cli:
        raise RuntimeError("Internal client not configured")
    return _with_retries(lambda: cli.list_expenses(start_date=start_date, end_date=end_date))

def api_expense_file_b64(kod: int, file_id: int, file_hash: str) -> str:
    cli = get_internal_client()
    if not cli:
        raise RuntimeError("Internal client not configured")
    return _with_retries(lambda: cli.expense_file_base64(id=kod, file_id=file_id, file_hash=file_hash))
