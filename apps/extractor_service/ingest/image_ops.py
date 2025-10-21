# apps/extractor_service/ingest/image_ops.py
from __future__ import annotations

from io import BytesIO
from typing import Tuple, Optional
from PIL import Image, ImageOps

def normalize_png(data: bytes, max_side: int = 2000) -> bytes:
    """
    - loads bytes
    - converts to RGB
    - auto-orients & contrast stretch
    - downscales longest side to max_side
    - returns optimized PNG bytes
    """
    im = Image.open(BytesIO(data))
    im = ImageOps.exif_transpose(im).convert("RGB")
    # light normalization
    im = ImageOps.autocontrast(im, cutoff=1)
    w, h = im.size
    scale = min(1.0, float(max_side) / float(max(w, h)))
    if scale < 1.0:
        im = im.resize((int(w*scale), int(h*scale)), Image.LANCZOS)

    out = BytesIO()
    im.save(out, format="PNG", optimize=True)
    return out.getvalue()
