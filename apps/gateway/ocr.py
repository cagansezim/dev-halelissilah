from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import List, Optional

from PIL import Image
from pdf2image import convert_from_bytes

try:
    import pytesseract  # type: ignore
except Exception:  # pragma: no cover
    pytesseract = None  # type: ignore


@dataclass
class OCRResult:
    text: str
    image_png_base64: str
    page_count: int
    note: Optional[str] = None
    size: Optional[List[int]] = None


def _png_b64(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def do_ocr(raw: bytes, mime: Optional[str] = None) -> OCRResult:
    # PDF
    if mime == "application/pdf" or raw[:4] == b"%PDF":
        pages = convert_from_bytes(raw, dpi=200)  # type: ignore
        if not pages:
            raise ValueError("empty PDF") 
        text = ""
        if pytesseract:
            text = "\n".join((pytesseract.image_to_string(p) or "") for p in pages).strip()
        first = pages[0].convert("RGB")
        return OCRResult(
            text=text,
            image_png_base64=_png_b64(first),
            page_count=len(pages),
            note=None if pytesseract else "pytesseract not installed",
            size=[first.width, first.height],
        )

    # Image
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    text = ""
    if pytesseract:
        text = pytesseract.image_to_string(im) or ""
    return OCRResult(
        text=text.strip(),
        image_png_base64=_png_b64(im),
        page_count=1,
        note=None if pytesseract else "pytesseract not installed",
        size=[im.width, im.height],
    )
