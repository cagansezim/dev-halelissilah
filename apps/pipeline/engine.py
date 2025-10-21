from __future__ import annotations
from typing import List, Optional
from PIL import Image
import io
from .preprocess import render_pdf_pages, basic_normalize
from .ocr import OcrEngine
from .extractors import extract_simple
from .schemas import OcrResult, InvoiceV1

class PipelineEngine:
    def __init__(self, locale: str = "tr_TR"):
        self.locale = locale
        self.ocr = OcrEngine(lang="tr+en")

    def _bytes_to_images(self, data: bytes) -> List[Image.Image]:
        if data[:4] == b"%PDF":
            return [basic_normalize(p) for p in render_pdf_pages(data)]
        im = Image.open(io.BytesIO(data)).convert("RGB")
        return [basic_normalize(im)]

    def ocr_bytes(self, data: bytes, locale: Optional[str] = None) -> List[OcrResult]:
        imgs = self._bytes_to_images(data)
        outs: List[OcrResult] = []
        for im in imgs:
            outs.append(self.ocr.run(im, lang="tr+en"))
        return outs

    def extract_invoice(self, data: bytes, locale: Optional[str] = None) -> InvoiceV1:
        locale = locale or self.locale
        ocr_pages = self.ocr_bytes(data, locale=locale)
        full_text = "\n\n".join(p.full_text for p in ocr_pages)
        inv = extract_simple(full_text, locale=locale)
        mean_conf = sum(p.mean_conf for p in ocr_pages)/max(1,len(ocr_pages))
        conf = 0.6*min(1.0, mean_conf/100.0) + 0.4*(1.0 if inv.total else 0.7)
        inv.confidence = round(conf, 3)
        inv.model = {"stack": "paddleocr+rules", "mean_ocr_conf": mean_conf}
        return inv

_engine: Optional[PipelineEngine] = None
def get_engine() -> PipelineEngine:
    global _engine
    if _engine is None:
        _engine = PipelineEngine(locale="tr_TR")
    return _engine
