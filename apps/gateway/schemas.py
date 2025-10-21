from __future__ import annotations

import time
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, HttpUrl, Field

RequestKind = Literal["chat","extract"]

class UnifiedRequestCreate(BaseModel):
    kind: RequestKind = "extract"
    message: Optional[str] = None        # for chat
    doc_type: Optional[str] = "receipt"  # for extract
    locale: Optional[str] = "tr_TR"
    webhook_url: Optional[HttpUrl] = None
    metadata: Dict[str, Any] = {}

class UnifiedRequestCreated(BaseModel):
    request_id: str
    state: Literal["queued","processing","done","error"]

class UnifiedRequestStatus(BaseModel):
    request_id: str
    kind: RequestKind
    state: Literal["queued","processing","done","error"]
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# For extraction result you already have; make sure it's JSONable:
class InvoiceExtraction(BaseModel):
    doc_type: str
    vendor: Optional[str]
    date: Optional[str]
    currency: Optional[str]
    subtotal: Optional[float]
    tax: Optional[float]
    total: Optional[float]
    payment_method: Optional[str]
    line_items: List[Dict[str, Any]] = []
    confidence: float = 0.0
    warnings: List[str] = []


# --------- LLM

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str
    images: Optional[List[str]] = None  # base64 strings for vision


class ChatIn(BaseModel):
    model: str = Field(default="qwen2.5:7b-instruct")
    messages: List[ChatMessage]
    stream: bool = False


# --------- Vision extract

class FileRef(BaseModel):
    kod: int
    fileId: int
    fileHash: str


class ExtractIn(BaseModel):
    ref: FileRef
    prompt: Optional[str] = None
    model: str = Field(default="llama3.2-vision")
    run_ocr: bool = True
    return_prompt: bool = False


# --------- Sessions

class Attachment(BaseModel):
    id: str
    filename: str
    content_type: str
    image_png_b64: Optional[str] = None
    size: int = 0


class Turn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    ts: float = Field(default_factory=lambda: time.time())
    attachments: List[Attachment] = Field(default_factory=list)
    raw_response: Optional[Dict[str, Any]] = None


class ChatSession(BaseModel):
    id: str
    title: str = "New session"
    model: str = "llama3.2-vision"
    created_ts: float = Field(default_factory=lambda: time.time())
    updated_ts: float = Field(default_factory=lambda: time.time())
    turns: List[Turn] = Field(default_factory=list)
    mode: Literal["free", "extract"] = "extract"
