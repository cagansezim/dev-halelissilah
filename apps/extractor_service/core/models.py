from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# *** Your target JSON schema ***
class DosyaItem(BaseModel):
    Kod: Optional[str] = None
    Adi: Optional[str] = None
    OrjinalAdi: Optional[str] = None
    Hash: Optional[str] = None
    MimeType: Optional[str] = None
    Size: Optional[int] = None
    Md5: Optional[str] = None
    EklenmeTarihi: Optional[str] = None

class MasrafAltItem(BaseModel):
    Kod: Optional[str] = None
    MasrafTarihi: Optional[str] = ""
    MasrafTuru: Optional[str] = ""
    Butce: Optional[str] = None
    Tedarikci: Optional[str] = ""
    Miktar: float = 1
    Birim: Optional[str] = ""
    BirimMasrafTutari: float = 0.0
    KDVOrani: float = 0.0
    ToplamMasrafTutari: float = 0.0
    Aciklama: Optional[str] = ""

class Masraf(BaseModel):
    Kod: Optional[str] = None
    BaslangicTarihi: Optional[str] = ""
    BitisTarihi: Optional[str] = ""
    Aciklama: Optional[str] = ""
    Bolum: Optional[str] = None
    Hash: Optional[str] = None

from enum import Enum

class RequestState(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"

class ExpenseJSON(BaseModel):
    # DO NOT name anything "Field" or "BaseModel"
    vendor: str = Field(..., description="Supplier name")
    amount: float = Field(..., ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    invoice_no: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}  # be explicit in v2

# --- Submit input ---
class SubmitFile(BaseModel):
    filename: str
    mime: str
    size: int
    content_b64: Optional[str] = None           # direct upload case
    ref: Optional[Dict[str, Any]] = None        # ERP reference case {kod,fileId,fileHash}

class SubmitRequest(BaseModel):
    description: Optional[str] = ""
    locale: Optional[str] = "tr_TR"
    currency: Optional[str] = "TRY"
    files: List[SubmitFile]

class DraftResult(BaseModel):
    draft: ExpenseJSON
    flags: List[Dict[str, Any]] = []
    provenance: Dict[str, Any] = {}

class RetryPayload(BaseModel):
    corrections: Optional[Dict[str, Any]] = None
    instructions: Optional[str] = None
