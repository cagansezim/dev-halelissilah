import base64, json
from typing import List, Tuple
from ..config import settings
from ..ingest.pdf_convert import pdf_to_images_and_text
from ..ingest.msg_parse import parse_msg
from ..ingest.ocr import build_ocr
from ..ingest.image_ops import normalize_png
from ..llm.evaluator import run_all_strategies
from ..core.storage import put_bytes
from ..core.internal_client import get_internal_client, api_expense_file_b64
from ..ingest.msg_parse import guess_kind

async def build_pages_from_files(files: list[dict]) -> Tuple[List[bytes], List[str], str|None, list[dict]]:
    pages_png, pages_txt = [], []
    email_body = None
    dosya = []
    internal = get_internal_client()
    ocr = build_ocr("paddleocr")

    for f in files:
        fname = f["filename"]; mime = f["mime"]; size = f.get("size") or 0
        raw = None
        if f.get("content_b64"):
            raw = base64.b64decode(f["content_b64"], validate=False)
        elif f.get("ref") and internal:
            ref = f["ref"]
            raw_b64 = api_expense_file_b64(
                kod=int(ref["kod"]),
                file_id=int(ref["fileId"]),
                file_hash=str(ref["fileHash"])
            )
            raw = base64.b64decode(raw_b64, validate=False)
        if raw is None:
            continue

        dosya.append({"Kod": None, "Adi": None, "OrjinalAdi": fname, "Hash": None,
                      "MimeType": mime, "Size": size, "Md5": None, "EklenmeTarihi": None})

        kind = guess_kind(fname, mime)
        if kind == "pdf":
            for png, native in pdf_to_images_and_text(raw, dpi=settings.DPI):
                png = normalize_png(png)
                ocr_text = ocr.text(png)
                pages_png.append(png)
                pages_txt.append(((native or "") + "\n" + (ocr_text or "")).strip())
        elif kind == "msg":
            email_body, atts = parse_msg(raw)
            for aname, adata, amime in atts:
                akind = guess_kind(aname, amime)
                if akind == "pdf":
                    for png, native in pdf_to_images_and_text(adata, dpi=settings.DPI):
                        png = normalize_png(png)
                        ocr_text = ocr.text(png)
                        pages_png.append(png)
                        pages_txt.append(((native or "") + "\n" + (ocr_text or "")).strip())
                elif akind == "image":
                    adata = normalize_png(adata)
                    pages_png.append(adata)
                    pages_txt.append(ocr.text(adata))
        else:  # image
            raw = normalize_png(raw)
            pages_png.append(raw)
            pages_txt.append(ocr.text(raw))

    return pages_png, pages_txt, email_body, dosya

async def run_pipeline(payload: dict, rid: str):
    pages_png, pages_txt, email_body, _dosya = await build_pages_from_files(payload.get("files", []))

    for idx, (png, txt) in enumerate(zip(pages_png, pages_txt), 1):
        put_bytes(f"expenses/{rid}/pages/{idx:04d}.png", png, "image/png")
        put_bytes(f"expenses/{rid}/texts/{idx:04d}.txt", txt.encode(), "text/plain")

    report = await run_all_strategies(pages_png, pages_txt, payload.get("description") or "", email_body)

    put_bytes(f"expenses/{rid}/evaluation.json", json.dumps(report, ensure_ascii=False).encode(), "application/json")

    chosen = report["chosen"]["merged"]
    final_draft = {
        "final": chosen,
        "flags": report["chosen"]["flags"],
        "confidence": report["chosen"]["confidence"],
        "provenance": {
            "mode": report["chosen"]["mode"],
            "text_model": report["chosen"]["text_model"],
            "vision_model": report["chosen"]["vision_model"]
        }
    }
    put_bytes(f"expenses/{rid}/final_draft.json", json.dumps(final_draft, ensure_ascii=False).encode(), "application/json")
    return final_draft
