# apps/gateway/worker_unified.py
from __future__ import annotations
import os, json, time
import redis, httpx

from apps.gateway.events_bus import _redis, set_state
# Reuse your existing OCR/engine if present; otherwise minimal stubs
try:
    from apps.gateway.ocr import run_ocr_text  # your implementation
except Exception:
    def run_ocr_text(data_or_key) -> str:
        # minimal stub: return empty; plug in your Paddle/Tesseract pipeline here
        return ""

try:
    from apps.gateway.engine import llm_post_edit  # your JSON-constrained LLM
except Exception:
    def llm_post_edit(ocr_text: str, hints: dict) -> dict:
        # minimal stub result to keep flow intact
        return {
            "doc_type": hints.get("doc_type","receipt"),
            "vendor": None, "date": None, "currency": None,
            "subtotal": None, "tax": None, "total": None,
            "payment_method": None, "line_items": [], "confidence": 0.0, "warnings": ["stub"]
        }

def _deliver_webhook(url: str, body: dict):
    try:
        httpx.post(url, json=body, timeout=15)
    except Exception:
        pass

def _pop_job(timeout=5):
    job = _redis.brpop("jobs", timeout=timeout)
    if not job:
        return None
    _, payload = job
    return json.loads(payload)

def main_loop():
    while True:
        j = _pop_job()
        if not j:
            continue
        rid = j["request_id"]; kind = j["kind"]; webhook = j.get("webhook_url")
        try:
            set_state(rid, "processing", 0.05)
            if kind == "extract":
                # 1) OCR (load from storage inside your ocr function)
                text = run_ocr_text(j)  # pass job payload so your impl can locate the object
                set_state(rid, "processing", 0.35)
                # 2) LLM post-edit (strict JSON)
                result = llm_post_edit(text, {"doc_type": j.get("doc_type"), "locale": j.get("locale")})
                set_state(rid, "processing", 0.90, result=result)
                set_state(rid, "done", 1.00, result=result)
                if webhook:
                    _deliver_webhook(webhook, {"request_id": rid, "state": "done", "result": result})
            else:  # chat
                for i, chunk in enumerate(["Thinking...", "Reading OCR...", "Answer ready."]):
                    _redis.xadd(f"events:{rid}", {"data": json.dumps({"request_id": rid, "chunk": chunk})})
                    set_state(rid, "processing", (i+1)/3.0)
                    time.sleep(0.4)
                set_state(rid, "done", 1.0, result={"message": "Chat finished"})
                if webhook:
                    _deliver_webhook(webhook, {"request_id": rid, "state": "done"})
        except Exception as e:
            set_state(rid, "error", error=str(e))
            if webhook:
                _deliver_webhook(webhook, {"request_id": rid, "state": "error", "error": str(e)})

if __name__ == "__main__":
    main_loop()
