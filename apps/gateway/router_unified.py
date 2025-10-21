# apps/gateway/router_unified.py
from __future__ import annotations
from typing import List, Optional, Literal, Dict, Any
import os, json, asyncio
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import StreamingResponse

from packages.security.jwt_dep import verify_service_jwt
from apps.gateway.events_bus import new_request, enqueue, get_status, stream_events

# If you already have AV and storage utilities, import them; otherwise minimal safe fallbacks:
try:
    from packages.shared.av import scan_bytes as _clam_scan  # your existing util
except Exception:
    _clam_scan = None

try:
    # prefer your existing MinIO helpers if present
    from packages.shared.storage import put_bytes as _put_bytes
except Exception:
    _put_bytes = None

router = APIRouter(prefix="/api", tags=["unified"])

# ---- Schemas (pydantic) kept simple to avoid import collisions ----
from pydantic import BaseModel, HttpUrl, Field

RequestKind = Literal["chat","extract"]

class UnifiedRequestCreate(BaseModel):
    kind: RequestKind = "extract"
    message: Optional[str] = None
    doc_type: Optional[str] = "receipt"
    locale: Optional[str] = "tr_TR"
    webhook_url: Optional[HttpUrl] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class UnifiedRequestCreated(BaseModel):
    request_id: str
    state: Literal["queued","processing","done","error"] = "queued"

class UnifiedRequestStatus(BaseModel):
    request_id: str
    kind: RequestKind
    state: Literal["queued","processing","done","error"]
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

def _scan_or_pass(b: bytes):
    if _clam_scan:
        _clam_scan(b)  # raise on virus
    # else: no-op fallback (keeps current behavior)

def _store_bytes(obj_key: str, data: bytes, mime: str):
    if _put_bytes:
        _put_bytes(obj_key, data, mime)
    else:
        # fallback local FS under ./storage for dev
        base = os.getenv("LOCAL_STORAGE_DIR", "./storage")
        os.makedirs(os.path.join(base, os.path.dirname(obj_key)), exist_ok=True)
        with open(os.path.join(base, obj_key), "wb") as f:
            f.write(data)

@router.post("/requests", response_model=UnifiedRequestCreated)
async def create_request(
    data: UnifiedRequestCreate = Depends(),
    files: List[UploadFile] = File(default=[]),
    _svc=Depends(verify_service_jwt)
):
    rid = new_request(data.kind)

    file_bytes = None
    file_name = None
    if files:
        f = files[0]
        fb = await f.read()
        _scan_or_pass(fb)  # ClamAV if available
        file_name = f.filename or "upload.bin"
        key = f"raw/{rid}/{file_name}"
        _store_bytes(key, fb, f.content_type or "application/octet-stream")
        file_bytes = fb

    enqueue(data.kind, rid, {
        "message": data.message,
        "webhook_url": data.webhook_url,
        "doc_type": data.doc_type,
        "locale": data.locale,
        "metadata": data.metadata,
        "file_bytes_present": bool(file_bytes),  # worker may choose to reload from storage
    })
    # NOTE: we do not push `file_bytes` into Redis by default to keep memory low.

    return UnifiedRequestCreated(request_id=rid)

@router.get("/requests/{rid}", response_model=UnifiedRequestStatus)
async def request_status(rid: str, _svc=Depends(verify_service_jwt)):
    s = get_status(rid)
    if not s:
        raise HTTPException(status_code=404, detail="not found")
    return UnifiedRequestStatus(
        request_id=rid,
        kind=s.get("kind","extract"),
        state=s.get("state","queued"),
        progress=s.get("progress",0.0),
        result=s.get("result"),
        error=s.get("error")
    )

@router.get("/requests/{rid}/events")
async def request_events(rid: str, _svc=Depends(verify_service_jwt)):
    async def gen():
        yield "retry: 3000\n\n"
        it = stream_events(rid)
        while True:
            data = next(it)
            if data is None:
                # keep-alive
                yield ": ping\n\n"
            else:
                yield f"data: {data}\n\n"
            await asyncio.sleep(0)
    return StreamingResponse(gen(), media_type="text/event-stream")
