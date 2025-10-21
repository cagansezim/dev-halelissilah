from __future__ import annotations

import io
import imghdr
from typing import List
from PIL import Image
from pdf2image import convert_from_bytes


def sniff_is_pdf(raw: bytes) -> bool:
    return raw[:4] == b"%PDF"


def pdf_to_images(raw_pdf: bytes, dpi: int = 300) -> List[bytes]:
    pages = convert_from_bytes(raw_pdf, dpi=dpi, fmt="png")
    out: List[bytes] = []
    for im in pages:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        out.append(buf.getvalue())
    return out


def ensure_png_bytes(raw: bytes) -> bytes:
    kind = imghdr.what(None, h=raw)
    if kind == "png":
        return raw
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()
