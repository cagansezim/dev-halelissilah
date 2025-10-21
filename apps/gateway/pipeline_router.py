from __future__ import annotations

import base64
import io
import json
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException
from PIL import Image

from apps.gateway.deps import get_engine, get_internal_client
from apps.gateway.ocr import do_ocr, OCRResult
from apps.gateway.schemas import ChatIn, ExtractIn

router = APIRouter(prefix="/api/llm", tags=["llm", "ai"])


@router.get("/models")
def list_models(engine=Depends(get_engine)) -> Dict[str, Any]:
    try:
        return engine.list_models()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama /api/tags failed: {e}")


@router.post("/chat")
def chat(body: ChatIn = Body(...), engine=Depends(get_engine)) -> Dict[str, Any]:
    msgs = [m.model_dump() for m in body.messages]
    try:
        res = engine.chat(model=body.model, messages=msgs, stream=False)  # type: ignore
        return {"ok": True, "model": body.model, "message": (res or {}).get("message", {}).get("content", "")}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama chat failed: {e}")


@router.post("/extract")
def vision_extract(
    body: ExtractIn = Body(...),
    engine=Depends(get_engine),
    internal=Depends(get_internal_client),
) -> Dict[str, Any]:
    if internal is None:
        raise HTTPException(status_code=424, detail="Internal API client not configured (set INTERNAL_API_BASE).")

    try:
        b64 = internal.expense_file_base64(
            kod=body.ref.kod, file_id=body.ref.fileId, file_hash=body.ref.fileHash
        )
    except Exception as e:
        raise HTTPException(status_code=424, detail=f"internal file fetch failed: {e}")
    raw = base64.b64decode(b64, validate=False)

    try:
        ocr: OCRResult = do_ocr(raw)
        img_b64 = ocr.image_png_base64
        ocr_excerpt = (ocr.text or "")[:2000]
    except Exception:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        ocr_excerpt = ""

    system = (
        "You are an invoice/receipt extraction assistant. "
        "Return ONLY a JSON object with fields: "
        '{"merchant":string|null,"date":string|null,"invoice_no":string|null,"currency":string|null,'
        '"subtotal":number|null,"tax":number|null,"total":number|null,'
        '"items":[{"description":string|null,"qty":number|null,"unit_price":number|null,"line_total":number|null}],'
        '"notes":string|null}'
    )
    user = "Extract key fields from the image. " + (f"\n\nOCR excerpt:\n{ocr_excerpt}" if ocr_excerpt else "")

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user, "images": [img_b64]},
    ]
    try:
        res = engine.chat(model=body.model, messages=messages, stream=False)  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama vision chat failed: {e}")

    text = (res or {}).get("message", {}).get("content", "") or ""

    data = {}
    s = text.strip()
    try:
        if s.startswith("{") and s.endswith("}"):
            data = json.loads(s)
        else:
            i, j = s.find("{"), s.rfind("}")
            if i != -1 and j != -1:
                data = json.loads(s[i : j + 1])
    except Exception:
        pass

    return {"ok": True, "model": body.model, "data": data or None, "raw": None if data else text}
