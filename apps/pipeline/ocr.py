from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Optional, Tuple

from PIL import Image
import pytesseract
from pdf2image import convert_from_bytes


@dataclass
class OCRResult:
    text: str
    image_png_base64: str
    size: Tuple[int, int]
    page_count: int
    note: Optional[str] = None


def _png_b64_from_pil(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _to_rgb_img(data: bytes) -> Image.Image:
    """Load arbitrary image bytes to RGB PIL Image."""
    return Image.open(io.BytesIO(data)).convert("RGB")


def do_ocr(data: bytes, mime: Optional[str] = None) -> OCRResult:
    """
    - If PDF: rasterize first page to PNG and OCR the concatenated text of all pages.
    - If image: OCR directly.
    Returns an OCRResult with a normalized preview PNG (first page / the image).
    """
    is_pdf = mime == "application/pdf" or data[:4] == b"%PDF"

    if is_pdf:
        pages = convert_from_bytes(data, dpi=200, fmt="png")  # first page will be preview
        page_count = len(pages)
        if not pages:
            raise ValueError("Empty PDF after rasterization")

        preview = pages[0].convert("RGB")
        text_chunks = []
        for p in pages:
            text_chunks.append(pytesseract.image_to_string(p))

        text = "\n".join(text_chunks).strip()
        b64 = _png_b64_from_pil(preview)
        return OCRResult(
            text=text,
            image_png_base64=b64,
            size=preview.size,
            page_count=page_count,
            note="pdf rasterized -> OCR",
        )

    # image path
    img = _to_rgb_img(data)
    text = pytesseract.image_to_string(img).strip()
    b64 = _png_b64_from_pil(img)
    return OCRResult(
        text=text,
        image_png_base64=b64,
        size=img.size,
        page_count=1,
        note="image -> OCR",
    )
