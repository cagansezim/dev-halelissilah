from __future__ import annotations


from typing import Dict, List, Optional
from pydantic import BaseModel, Field

# /list response
class ExpenseListItem(BaseModel):
    Kod: int
    BaslangicTarihi: str
    BitisTarihi: str
    Aciklama: str
    Bolum: str
    Hash: str

class ExpenseListResponse(BaseModel):
    success: bool
    data: List[ExpenseListItem]

# /json response
class FileInfo(BaseModel):
    Kod: int
    Adi: Optional[str] = None
    OrjinalAdi: Optional[str] = None
    Hash: Optional[str] = None
    MimeType: Optional[str] = None
    Size: Optional[int] = None
    Md5: Optional[str] = None
    EklenmeTarihi: Optional[str] = None

class ExpenseItem(BaseModel):
    Kod: int
    MasrafTarihi: str
    MasrafTuru: Optional[str] = None
    Butce: Optional[str] = None
    Tedarikci: Optional[str] = None
    OdemeTuru: Optional[str] = None
    Miktar: Optional[float] = None
    Birim: Optional[str] = None
    BirimMasrafTutari: Optional[float] = None
    KDVOrani: Optional[str] = None
    ToplamMasrafTutari: Optional[float] = None
    Aciklama: Optional[str] = None
    Dosya: Optional[Dict[str, FileInfo]] = None  # keyed by file id

class ExpenseHeader(BaseModel):
    Kod: int
    BaslangicTarihi: str
    BitisTarihi: str
    Aciklama: str
    Bolum: str
    Hash: str

class ExpenseDetailData(BaseModel):
    masraf: ExpenseHeader
    MasrafAlt: Dict[str, ExpenseItem]

class ExpenseDetailResponse(BaseModel):
    success: bool
    data: ExpenseDetailData
