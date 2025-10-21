from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date

class LineItem(BaseModel):
    desc: str
    qty: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None

class InvoiceV1(BaseModel):
    schema: str = "invoice.v1"
    invoice_no: Optional[str] = None
    date: Optional[date] = None
    vendor: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    line_items: List[LineItem] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    model: Optional[dict] = None

class OcrLine(BaseModel):
    text: str
    conf: float
    bbox: list  # [x1,y1,x2,y2]

class OcrResult(BaseModel):
    lang: str
    lines: List[OcrLine]
    full_text: str
    mean_conf: float
