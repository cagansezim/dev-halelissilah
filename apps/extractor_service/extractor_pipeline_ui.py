# extractor_pipeline_ui.py
# Modern wizard UI for end-to-end invoice extraction & comparison (no OpenAI).
# Flow:
#  1) Pick date interval -> list expenses
#  2) Select ONE expense -> preview its files (optionally subset)
#  3) Configure prompts & engines (system prompt, fields, notes, models)
#  4) Review final prompt & settings -> Launch
#  5) Monitor logs; per-file results; GT vs Pred diffs
#
# Engines: HTTP Chat API (vLLM/TGI) or Ollama; HF Vision Doc-AI; Tesseract OCR
# Storage: local ./artifacts or MinIO/S3
# Artifacts: JSON with doc pages, prompts, model outputs, merged/validated fields, diffs
# -----------------------------------------------------------------------------

import os
import io
import re
import sys
import json
import uuid
import base64
import asyncio
import logging
import mimetypes
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Literal, Tuple

from fastapi import FastAPI, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse
from pydantic import BaseModel, Field

# ---------- Optional deps ----------
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
    ImageOps = None

try:
    import extract_msg
except Exception:
    extract_msg = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    import httpx
except Exception:
    httpx = None

try:
    from minio import Minio
except Exception:
    Minio = None

try:
    from deepdiff import DeepDiff
except Exception:
    DeepDiff = None

try:
    import torch
    from transformers import AutoProcessor, AutoModelForCausalLM
except Exception:
    torch = None
    AutoProcessor = None
    AutoModelForCausalLM = None


# ----------------------------- Config -----------------------------

class Config:
    HOST: str = os.getenv("UI_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("UI_PORT", "8090"))

    # Internal gateway (date-window first; no client/kod)
    INTERNAL_API_BASE_URL: str = os.getenv("INTERNAL_API_BASE_URL", "http://gateway:8080/internal")
    INTERNAL_API_KEY: str = os.getenv("INTERNAL_API_KEY", "dev-key")

    # Storage
    ARTIFACT_DIR: str = os.getenv("ARTIFACT_DIR", "./artifacts")
    S3_ENDPOINT: Optional[str] = os.getenv("S3_ENDPOINT")
    S3_BUCKET: Optional[str] = os.getenv("S3_BUCKET")
    S3_ACCESS_KEY: Optional[str] = os.getenv("S3_ACCESS_KEY")
    S3_SECRET_KEY: Optional[str] = os.getenv("S3_SECRET_KEY")
    S3_REGION: str = os.getenv("S3_REGION", "us-east-1")

    # HTTP Chat API (vLLM/TGI style) or Ollama
    CHAT_API_BASE_URL: str = os.getenv("CHAT_API_BASE_URL") or os.getenv("CHAT_LLM_BASE_URL") or "http://localhost:8000/v1"
    CHAT_API_MODEL: str = os.getenv("CHAT_API_MODEL", "llama-3-8b-instruct")
    CHAT_API_KEY: str = os.getenv("CHAT_API_KEY", "x")

    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_CHAT_MODEL: str = os.getenv("OLLAMA_CHAT_MODEL", "llama3.1")

    # HF Vision
    HF_DOC_MODEL: str = os.getenv("HF_DOC_MODEL", "mPLUG/DocOwl2")
    HF_DEVICE: str = os.getenv("HF_DEVICE", "cpu")

    # OCR
    TESSERACT_LANG: str = os.getenv("TESSERACT_LANG", "eng")

CFG = Config()

os.makedirs(CFG.ARTIFACT_DIR, exist_ok=True)
RUNS_DIR = os.path.join(CFG.ARTIFACT_DIR, "runs")
os.makedirs(RUNS_DIR, exist_ok=True)
HISTORY_PATH = os.path.join(RUNS_DIR, "index.json")


# ----------------------------- Logging -----------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("extractor_ui")


# ----------------------------- Storage -----------------------------

class Storage:
    def __init__(self):
        self.local = True
        self.root = CFG.ARTIFACT_DIR
        self.s3 = None
        if CFG.S3_ENDPOINT and CFG.S3_BUCKET and Minio:
            endpoint = CFG.S3_ENDPOINT.replace("http://","").replace("https://","")
            secure = CFG.S3_ENDPOINT.startswith("https://")
            try:
                self.s3 = Minio(
                    endpoint=endpoint,
                    access_key=CFG.S3_ACCESS_KEY,
                    secret_key=CFG.S3_SECRET_KEY,
                    secure=secure,
                    region=CFG.S3_REGION
                )
                if not self.s3.bucket_exists(CFG.S3_BUCKET):
                    self.s3.make_bucket(CFG.S3_BUCKET)
                self.local = False
            except Exception as e:
                log.warning("MinIO init failed, using local. %s", e)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> str:
        if self.local or not self.s3:
            path = os.path.join(self.root, key)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
            return f"file://{path}"
        from io import BytesIO
        self.s3.put_object(CFG.S3_BUCKET, key, BytesIO(data), len(data), content_type=content_type)
        return f"s3://{CFG.S3_BUCKET}/{key}"

    def put_json(self, key: str, obj: Any) -> str:
        return self.put_bytes(key, json.dumps(obj, ensure_ascii=False, indent=2).encode(), "application/json")

    def put_png(self, key: str, pil_img: "Image.Image") -> str:
        if Image is None:
            raise RuntimeError("Pillow not installed")
        bio = io.BytesIO()
        pil_img.save(bio, format="PNG")
        return self.put_bytes(key, bio.getvalue(), "image/png")

STORAGE = Storage()


# ----------------------------- Internal API -----------------------------
# Date-interval first: /internal/expenses?start=YYYY-MM-DD&end=YYYY-MM-DD

async def _http_get_json(url: str, headers: Dict[str,str] = None, params: Dict[str,Any] = None):
    if httpx is None:
        raise RuntimeError("httpx not installed")
    async with httpx.AsyncClient(timeout=180) as c:
        r = await c.get(url, headers=headers, params=params)
        r.raise_for_status()
        return r.json()

async def list_expenses(start_date: Optional[str], end_date: Optional[str]) -> List[Dict[str, Any]]:
    url = f"{CFG.INTERNAL_API_BASE_URL.rstrip('/')}/expenses"
    headers = {"Authorization": f"Bearer {CFG.INTERNAL_API_KEY}"}
    params: Dict[str, Any] = {}
    if start_date: params["start"] = start_date
    if end_date:   params["end"]   = end_date
    data = await _http_get_json(url, headers=headers, params=params)
    return data.get("items", [])

async def list_files(expense_id: str) -> List[Dict[str, Any]]:
    url = f"{CFG.INTERNAL_API_BASE_URL.rstrip('/')}/expenses/{expense_id}/files"
    headers = {"Authorization": f"Bearer {CFG.INTERNAL_API_KEY}"}
    data = await _http_get_json(url, headers=headers)
    return data.get("items", [])

async def fetch_file_b64(expense_id: str, file_id: str) -> Tuple[str, bytes]:
    url = f"{CFG.INTERNAL_API_BASE_URL.rstrip('/')}/expenses/{expense_id}/files/{file_id}"
    headers = {"Authorization": f"Bearer {CFG.INTERNAL_API_KEY}"}
    j = await _http_get_json(url, headers=headers)
    return j["name"], base64.b64decode(j["base64"])

async def fetch_gt_json_for_expense(expense: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return expense.get("json")


# ----------------------------- Normalization -----------------------------

def _norm_img(pil: "Image.Image") -> "Image.Image":
    pil = ImageOps.exif_transpose(pil)
    return pil.convert("RGB")

def pdf_to_pages(pdf_bytes: bytes) -> List["Image.Image"]:
    if not fitz or not Image:
        raise RuntimeError("PyMuPDF + Pillow required for PDF")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out=[]
    for i in range(len(doc)):
        px = doc[i].get_pixmap(dpi=200)
        out.append(Image.frombytes("RGB", [px.width, px.height], px.samples))
    return out

def pdf_text_pages(pdf_bytes: bytes) -> List[str]:
    if not fitz:
        return [""]
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return [doc[i].get_text("text") or "" for i in range(len(doc))]

def image_bytes_to_pil(b: bytes) -> "Image.Image":
    if not Image:
        raise RuntimeError("Pillow not installed")
    return Image.open(io.BytesIO(b))

def parse_msg_bytes(raw: bytes) -> Tuple[str, List[Tuple[str, bytes, str]]]:
    if extract_msg is None:
        return "", []
    import tempfile, os
    with tempfile.NamedTemporaryFile(delete=False, suffix=".msg") as tmp:
        tmp.write(raw); tmp.flush(); path = tmp.name
    try:
        msg = extract_msg.Message(path)
        body = msg.body or ""
        atts=[]
        for a in msg.attachments:
            data=a.data
            name=a.longFilename or a.shortFilename or "attachment"
            mime=mimetypes.guess_type(name)[0] or "application/octet-stream"
            atts.append((name, data, mime))
        return body, atts
    finally:
        os.remove(path)

class Page(BaseModel):
    index: int
    png_ref: str
    text: Optional[str]

class UnifiedDocument(BaseModel):
    source: Literal["pdf","image","msg"]
    filename: str
    mime: str
    pages: List[Page] = []
    email_body: Optional[str] = None

def normalize_file(name: str, raw: bytes, key_prefix: str) -> UnifiedDocument:
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    if name.lower().endswith(".pdf") or raw[:4] == b"%PDF":
        imgs = pdf_to_pages(raw)
        txts = pdf_text_pages(raw)
        pages=[]
        for i, img in enumerate(imgs):
            ref = STORAGE.put_png(f"{key_prefix}/{os.path.basename(name)}.page{i:03d}.png", _norm_img(img))
            pages.append(Page(index=i, png_ref=ref, text=(txts[i] if i < len(txts) else None)))
        return UnifiedDocument(source="pdf", filename=name, mime=mime, pages=pages)

    if name.lower().endswith(".msg"):
        body, atts = parse_msg_bytes(raw)
        pages=[]
        for att_name, att_bytes, att_mime in atts:
            if att_name.lower().endswith(".pdf"):
                imgs = pdf_to_pages(att_bytes); txts = pdf_text_pages(att_bytes)
                for i, img in enumerate(imgs):
                    ref = STORAGE.put_png(f"{key_prefix}/{os.path.basename(att_name)}.page{i:03d}.png", _norm_img(img))
                    pages.append(Page(index=len(pages), png_ref=ref, text=(txts[i] if i < len(txts) else None)))
            elif att_name.lower().endswith((".png",".jpg",".jpeg",".webp",".tif",".tiff")):
                ref = STORAGE.put_png(f"{key_prefix}/{os.path.basename(att_name)}.page000.png", _norm_img(image_bytes_to_pil(att_bytes)))
                pages.append(Page(index=len(pages), png_ref=ref, text=None))
        return UnifiedDocument(source="msg", filename=name, mime=mime, pages=pages, email_body=body)

    # image
    ref = STORAGE.put_png(f"{key_prefix}/{os.path.basename(name)}.page000.png", _norm_img(image_bytes_to_pil(raw)))
    return UnifiedDocument(source="image", filename=name, mime=mime, pages=[Page(index=0, png_ref=ref, text=None)])


# ----------------------------- Engines -----------------------------

async def _load_ref_bytes(ref: str) -> bytes:
    if ref.startswith("file://"):
        with open(ref.replace("file://",""), "rb") as f:
            return f.read()
    raise RuntimeError(f"Byte-loader supports file:// only for now: {ref}")

def ocr_png_bytes(png_bytes: bytes, lang: str) -> str:
    if pytesseract is None or Image is None:
        return ""
    return pytesseract.image_to_string(Image.open(io.BytesIO(png_bytes)), lang=lang) or ""

async def chat_http_api_extract(text_pages: List[str], system_prompt: str, schema_prompt: str,
                                base_url: str, model: str, api_key: str) -> Dict[str, Any]:
    if httpx is None:
        return {"_error":"httpx missing"}
    msgs = [
        {"role":"system","content":system_prompt.strip()},
        {"role":"user","content": (schema_prompt + "\n\n" + "\n\n".join(text_pages))[:200000]}
    ]
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    payload = {"model": model, "messages": msgs, "temperature": 0}
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(url, headers=headers, json=payload)
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except Exception:
            m = re.search(r"\{.*\}", content, re.S)
            return json.loads(m.group(0)) if m else {"_raw": content}
    except Exception as e:
        return {"_error": str(e)}

async def chat_ollama_extract(text_pages: List[str], system_prompt: str, schema_prompt: str,
                              base_url: str, model: str) -> Dict[str, Any]:
    if httpx is None:
        return {"_error":"httpx missing"}
    prompt = (system_prompt.strip() + "\n\n" + schema_prompt + "\n\n" + "\n\n".join(text_pages))[:200000]
    try:
        async with httpx.AsyncClient(timeout=180) as c:
            r = await c.post(f"{base_url.rstrip('/')}/api/chat",
                             json={"model": model, "messages":[{"role":"user","content":prompt}], "stream": False})
            r.raise_for_status()
            content = r.json().get("message",{}).get("content","")
        try:
            return json.loads(content)
        except Exception:
            m = re.search(r"\{.*\}", content, re.S)
            return json.loads(m.group(0)) if m else {"_raw": content}
    except Exception as e:
        return {"_error": str(e)}

_doc_proc = None
_doc_model = None

def _load_hf_vision(model_name: str, device: str):
    global _doc_proc, _doc_model
    if AutoProcessor is None or AutoModelForCausalLM is None:
        raise RuntimeError("transformers not installed")
    if _doc_proc is None:
        _doc_proc = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
        dtype = torch.float16 if (torch and torch.cuda.is_available() and device.startswith("cuda")) else None
        _doc_model = AutoModelForCausalLM.from_pretrained(model_name, trust_remote_code=True, torch_dtype=dtype)
        _doc_model.to(device)
    return _doc_proc, _doc_model

def _json_from_text(txt: str) -> Dict[str, Any]:
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else {"_raw": txt}

def vision_extract_pngs(png_blobs: List[bytes], prompt_text: str, model_name: str, device: str) -> Dict[str, Any]:
    if not png_blobs:
        return {}
    if AutoProcessor is None or AutoModelForCausalLM is None or torch is None:
        return {"_error":"transformers/torch missing"}
    from PIL import Image as PILImage
    proc, mdl = _load_hf_vision(model_name, device)
    images = [PILImage.open(io.BytesIO(b)).convert("RGB") for b in png_blobs]
    inputs = proc(images=images, text=prompt_text, return_tensors="pt").to(device)
    with torch.inference_mode():
        gen = mdl.generate(**inputs, max_new_tokens=2048)
    try:
        out_text = proc.batch_decode(gen, skip_special_tokens=True)[0]
    except Exception:
        out_text = ""
    return _json_from_text(out_text)


# ----------------------------- Merge / Validate / Diff -----------------------------

DEFAULT_FIELDS = [
    "Masraf","MasrafAlt","Dosya","Kisi","IBAN","ParaBirimi","Aciklama",
    "Firma","IlgiliKod","Tarih","Tutar","ErpMasrafKod","Onaylayan",
    "ProjeKodu","AltProjeKodu","DosyaAciklamasi","CikisTarihi","GidisTarihi"
]

def build_schema_prompt(fields: List[str], invoice_desc: str) -> str:
    keys = ", ".join(fields)
    lines = [
        "You are an expert invoice extractor.",
        f"Extract ONLY these fields as JSON: {keys}.",
        "Rules:",
        "- Missing/unknown → null",
        "- Tarih format: YYYY-MM-DD",
        "- Tutar uses dot decimals",
        "- No commentary; output strict JSON only"
    ]
    if (invoice_desc or "").strip():
        lines.append(f"Operator notes: {(invoice_desc or '').strip()}")
    return "\n".join(lines)

def validate_and_shape(data: Dict[str, Any], filename: str, fields: List[str]) -> Dict[str, Any]:
    out = {k: None for k in fields}
    if isinstance(data, dict):
        for k in fields:
            if k in data:
                out[k] = data[k]
    if "Dosya" in out:
        out["Dosya"] = filename
    return out

def compute_diff(gt: Optional[Dict[str, Any]], pred: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not gt or DeepDiff is None:
        return None
    try:
        return DeepDiff(gt, pred, ignore_order=True).to_dict()
    except Exception:
        return None


# ----------------------------- Jobs / History -----------------------------

JobPhase = Literal[
    "queued","running:normalize","running:ocr",
    "running:llm:chat","running:llm:vision","running:merge",
    "running:validate","running:compare","completed","failed"
]

class JobSpec(BaseModel):
    # scope
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    expense_id: str  # exactly one selected

    # selection
    file_ids: Optional[List[str]] = None  # None or [] -> all files

    # engines
    run_ocr: bool = True
    ocr_lang: str = CFG.TESSERACT_LANG

    chat_engine: Literal["http","ollama","disabled"] = "http"
    chat_model: Optional[str] = None
    chat_base_url: Optional[str] = None

    vision_engine: Literal["hf_vision","disabled"] = "hf_vision"
    vision_model: Optional[str] = None
    hf_device: Optional[str] = None

    # prompting
    fields: List[str] = Field(default_factory=lambda: list(DEFAULT_FIELDS))
    system_prompt: str = "You are a meticulous data extractor. Return only valid JSON."
    invoice_description: str = ""

class JobStatus(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    phase: JobPhase = "queued"
    progress: float = 0.0
    message: Optional[str] = None
    errors: List[str] = []
    artifacts: Dict[str, Any] = {}
    results: Dict[str, Any] = {}
    logs: List[str] = []
    spec: Optional[JobSpec] = None

JOBS: Dict[str, JobStatus] = {}
HISTORY: List[Dict[str, Any]] = []

def _load_history():
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH,"r",encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def _append_history(entry: Dict[str, Any]):
    HISTORY.append(entry)
    try:
        with open(HISTORY_PATH,"w",encoding="utf-8") as f:
            json.dump(HISTORY, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("history write failed: %s", e)

HISTORY = _load_history()

def job_log(st: JobStatus, msg: str):
    ts = datetime.utcnow().strftime("%H:%M:%S")
    st.logs.append(f"[{ts}] {msg}")
    if len(st.logs) > 2000:
        st.logs = st.logs[-2000:]


# ----------------------------- Pipeline -----------------------------

SEM = asyncio.Semaphore(2)

async def run_job(spec: JobSpec, st: JobStatus):
    async with SEM:
        try:
            # Ensure selection exists
            expense_id = str(spec.expense_id)

            # Resolve GT by re-listing expenses in window and matching id (cheap & keeps API simple)
            gt: Optional[Dict[str, Any]] = None
            try:
                for e in await list_expenses(spec.start_date, spec.end_date):
                    if str(e.get("id")) == expense_id:
                        gt = await fetch_gt_json_for_expense(e)
                        break
            except Exception:
                pass

            files = await list_files(expense_id)
            if spec.file_ids:
                files = [f for f in files if str(f["id"]) in set(spec.file_ids)]
            total = len(files)
            done = 0

            chat_model = spec.chat_model or (CFG.CHAT_API_MODEL if spec.chat_engine=="http" else CFG.OLLAMA_CHAT_MODEL)
            chat_base  = spec.chat_base_url or (CFG.CHAT_API_BASE_URL if spec.chat_engine=="http" else CFG.OLLAMA_URL)
            vision_model = spec.vision_model or CFG.HF_DOC_MODEL
            device = spec.hf_device or CFG.HF_DEVICE

            schema_txt = build_schema_prompt(spec.fields, spec.invoice_description)
            sys_prompt = spec.system_prompt.strip()

            for f in files:
                file_id = str(f["id"])
                try:
                    st.phase="running:normalize"; st.message=f"Normalizing {file_id}"
                    job_log(st, f"download file {file_id}")
                    name, raw = await fetch_file_b64(expense_id, file_id)
                    key_prefix = f"runs/{st.job_id}/{expense_id}_{file_id}"
                    doc = normalize_file(name, raw, key_prefix)

                    png_blobs, text_pages = [], []
                    for p in doc.pages:
                        try:
                            png_blobs.append(await _load_ref_bytes(p.png_ref))
                        except Exception:
                            png_blobs.append(b"")
                        text_pages.append(p.text or "")

                    # OCR
                    ocr_texts: List[str] = []
                    if spec.run_ocr and png_blobs:
                        st.phase="running:ocr"; st.message=f"OCR {file_id}"
                        job_log(st, f"OCR pages={len(png_blobs)} lang={spec.ocr_lang}")
                        for b in png_blobs:
                            ocr_texts.append(ocr_png_bytes(b, spec.ocr_lang) if b else "")

                    # Chat LLM
                    chat_json: Dict[str, Any] = {}
                    if spec.chat_engine != "disabled":
                        st.phase="running:llm:chat"; st.message=f"Chat {file_id}"
                        job_log(st, f"chat engine={spec.chat_engine} model={chat_model}")
                        inputs = (text_pages if any(text_pages) else ocr_texts)
                        if spec.chat_engine == "http":
                            chat_json = await chat_http_api_extract(inputs, sys_prompt, schema_txt, chat_base, chat_model, CFG.CHAT_API_KEY)
                        else:
                            chat_json = await chat_ollama_extract(inputs, sys_prompt, schema_txt, chat_base, chat_model)

                    # Vision LLM
                    vision_json: Dict[str, Any] = {}
                    if spec.vision_engine == "hf_vision" and png_blobs:
                        st.phase="running:llm:vision"; st.message=f"Vision {file_id}"
                        job_log(st, f"vision model={vision_model} device={device}")
                        vision_json = vision_extract_pngs(png_blobs, schema_txt + "\nReturn strict JSON only.", vision_model, device)

                    # Merge/validate/diff
                    st.phase="running:merge"; st.message=f"Merging {file_id}"
                    merged: Dict[str, Any] = {}
                    for src in [vision_json or {}, chat_json or {}]:
                        if isinstance(src, dict):
                            for k,v in src.items():
                                if k.startswith("_"):  # ignore meta keys
                                    continue
                                if v not in (None, "", [], {}):
                                    merged.setdefault(k, v)
                    st.phase="running:validate"
                    valid = validate_and_shape(merged, filename=name, fields=spec.fields)
                    st.phase="running:compare"
                    diff = compute_diff(gt, valid)

                    # store artifacts
                    artifact = {
                        "doc": doc.model_dump(),
                        "chat_json": chat_json,
                        "vision_json": vision_json,
                        "merged": valid,
                        "gt": gt,
                        "diff": diff,
                        "schema_prompt": schema_txt,
                        "system_prompt": sys_prompt
                    }
                    art_ref = STORAGE.put_json(f"{key_prefix}.json", artifact)
                    st.artifacts[f"{expense_id}/{file_id}"] = art_ref
                    st.results[f"{expense_id}/{file_id}"] = valid

                    done += 1
                    st.progress = done / max(1,total)
                    job_log(st, f"done {file_id} ({done}/{total})")
                except Exception as e:
                    msg = f"{expense_id}/{file_id}: {e}"
                    st.errors.append(msg)
                    job_log(st, f"ERROR {msg}\n{traceback.format_exc()}")

            st.phase = "completed" if not st.errors else "failed"
            st.message = "Done" if not st.errors else "Done with errors"
            _append_history({
                "job_id": st.job_id,
                "created_at": st.created_at.isoformat(),
                "phase": st.phase,
                "message": st.message,
                "errors": st.errors,
                "spec": st.spec.model_dump() if st.spec else None,
                "artifacts": st.artifacts,
            })
            job_log(st, f"finished: {st.phase}")
        except Exception as e:
            st.phase = "failed"
            st.message = str(e)
            st.errors.append(str(e))
            job_log(st, f"FATAL {e}\n{traceback.format_exc()}")


# ----------------------------- Web (Wizard) UI -----------------------------

app = FastAPI(title="Extractor Pipeline UI")

# ---- HTML helpers ----
STEP_LABELS = [
    "Date interval",
    "Pick expense",
    "Prompts & engines",
    "Review & launch",
    "Monitor & compare",
]

def _page(title: str, body: str, active_step: int = 1, profile: str = "dev") -> str:
    steps = []
    for i, label in enumerate(STEP_LABELS, start=1):
        state = "bg-blue-600 text-white" if i == active_step else "bg-slate-200 text-slate-700"
        steps.append(f"""
        <div class="flex items-center gap-2">
          <div class="w-8 h-8 flex items-center justify-center rounded-full {state}">{i}</div>
          <div class="text-sm">{label}</div>
        </div>
        """)
        if i < len(STEP_LABELS):
            steps.append('<div class="flex-1 h-px bg-slate-200"></div>')
    stepper = f'<div class="flex items-center gap-3">{"" .join(steps)}</div>'

    return f"""<!doctype html><html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<script src="https://unpkg.com/htmx.org@1.9.12"></script>
<script src="https://unpkg.com/htmx.org/dist/ext/sse.js"></script>
<link href="https://cdn.jsdelivr.net/npm/tailwindcss@3.4.10/dist/tailwind.min.css" rel="stylesheet"/>
<script>
function copyText(id){{navigator.clipboard.writeText(document.getElementById(id).innerText)}}
function toggleAll(box, group){{document.querySelectorAll('[data-group=\"'+group+'\"] input[type=checkbox]').forEach(c=>{{c.checked=box.checked;}})}}
</script>
</head>
<body class="bg-slate-50 text-slate-900">
<header class="sticky top-0 z-10 backdrop-blur bg-white/80 border-b">
  <div class="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
    <div class="font-semibold">Pruva AI — Invoice Extraction</div>
    <div class="text-xs text-slate-500">UI profile: {profile}</div>
  </div>
</header>
<main class="max-w-7xl mx-auto p-6 space-y-6">
  {stepper}
  {body}
</main>
</body></html>"""

def _card(title: str, content: str) -> str:
    return f"""
<section class="bg-white rounded-2xl shadow-sm p-5">
  <h3 class="font-semibold mb-3">{title}</h3>
  {content}
</section>"""

def _error(text: str) -> str:
    return f'<div class="px-3 py-2 rounded bg-red-50 text-red-700 text-sm">{text}</div>'


# ------------------ Step 1: Date interval ------------------

def _step1() -> str:
    content = f"""
<form hx-post="/step/2" hx-target="main" class="grid grid-cols-1 md:grid-cols-3 gap-4">
  <div>
    <label class="text-sm">Start</label>
    <input name="start_date" type="date" required class="w-full mt-1 border rounded p-2"/>
  </div>
  <div>
    <label class="text-sm">End</label>
    <input name="end_date" type="date" required class="w-full mt-1 border rounded p-2"/>
  </div>
  <div class="flex items-end justify-end">
    <button class="px-4 py-2 rounded bg-blue-600 text-white">List expenses</button>
  </div>
</form>
"""
    return _page("Step 1 — Date interval", _card("Step 1 — Select date interval", content), 1)

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse(_step1())


# ------------------ Step 2: Pick ONE expense & preview files ------------------

def _expense_row(exp: Dict[str, Any]) -> str:
    eid = str(exp.get("id"))
    title = exp.get("title") or exp.get("name") or f"Expense {eid}"
    has_gt = "json" in exp and bool(exp["json"])
    gt_badge = '<span class="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">GT</span>' if has_gt else ""
    return f"""
<div class="border rounded-xl p-3" id="exp-{eid}">
  <div class="flex items-center justify-between">
    <label class="flex items-center gap-2">
      <input type="radio" name="expense_id" value="{eid}">
      <span class="font-medium">{title}</span>{gt_badge}
      <span class="text-xs text-slate-500">#{eid}</span>
    </label>
    <button class="text-xs px-2 py-1 rounded bg-slate-200"
            hx-get="/expense/{eid}/files"
            hx-target="#files-preview" hx-swap="innerHTML">Preview files</button>
  </div>
</div>"""

@app.post("/step/2", response_class=HTMLResponse)
async def step2(start_date: str = Form(...), end_date: str = Form(...)):
    if not start_date or not end_date:
        return HTMLResponse(_page("Step 1", _card("Validation", _error("Start and End dates are required.")), 1))
    try:
        items = await list_expenses(start_date, end_date)
    except Exception as e:
        return HTMLResponse(_page("Step 2", _card("Error", _error(f"Failed to load expenses: {e}"))))
    if not items:
        return HTMLResponse(_page("Step 2", _card("No data", _error("No expenses for the selected interval.")), 2))

    rows = "".join(_expense_row(e) for e in items)
    body = f"""
<form hx-post="/step/3" hx-target="main" hx-include="this" class="space-y-4">
  <!-- keep dates -->
  <input type="hidden" name="start_date" value="{start_date}"/>
  <input type="hidden" name="end_date" value="{end_date}"/>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <div class="lg:col-span-2 space-y-3">
      {_card("Step 2 — Pick ONE expense", rows)}
    </div>
    <div class="lg:col-span-1 space-y-3">
      {_card("Files preview", '<div id="files-preview" class="min-h-[260px] text-sm text-slate-600">Select an expense and click “Preview files”.</div>')}
      {_card("Next", '<button class="w-full px-4 py-2 rounded bg-blue-600 text-white">Continue</button>')}
    </div>
  </div>
</form>
"""
    return HTMLResponse(_page("Step 2 — Pick expense", body, 2))

@app.get("/expense/{expense_id}/files", response_class=HTMLResponse)
async def expense_files(expense_id: str):
    try:
        files = await list_files(expense_id)
    except Exception as e:
        return HTMLResponse(_error(f"Failed to list files: {e}"))
    if not files:
        return HTMLResponse('<div class="text-xs text-slate-500">No files.</div>')

    # Allow optional sub-selection; default is all
    rows=[]
    for f in files:
        fid = str(f.get("id"))
        name = f.get("name") or f"file-{fid}"
        rows.append(f"""
<div class="flex items-center justify-between py-1">
  <label class="flex items-center gap-2 text-sm">
    <input type="checkbox" name="file_ids" value="{fid}">
    <span class="font-mono text-xs text-slate-500">#{fid}</span>
    <span>{name}</span>
  </label>
  <button class="text-xs px-2 py-1 rounded bg-slate-100"
          hx-get="/preview/{expense_id}/{fid}"
          hx-target="#live-preview" hx-swap="innerHTML">Preview</button>
</div>""")
    html = f"""
<div class="space-y-3">
  <div class="rounded border bg-slate-50 p-2">
    {''.join(rows)}
  </div>
  <div id="live-preview" class="rounded border bg-slate-50 p-2 text-xs text-slate-700">Click Preview on a file to see image/text.</div>
</div>
"""
    return HTMLResponse(html)

@app.get("/preview/{expense_id}/{file_id}", response_class=HTMLResponse)
async def preview_file(expense_id: str, file_id: str):
    try:
        name, raw = await fetch_file_b64(expense_id, file_id)
        key_prefix = f"previews/{expense_id}_{file_id}"
        doc = normalize_file(name, raw, key_prefix)
    except Exception as e:
        return HTMLResponse(_error(f"Preview failed: {e}"))

    imgs = []
    for p in doc.pages[:4]:
        if p.png_ref.startswith("file://"):
            path = p.png_ref.replace("file://","")
            data = base64.b64encode(open(path,"rb").read()).decode()
            imgs.append(f'<img class="rounded w-full object-cover" src="data:image/png;base64,{data}"/>')
    grid = '<div class="grid grid-cols-2 gap-3">' + "".join(imgs or ['<div class="col-span-2 text-xs text-slate-500">No images</div>']) + '</div>'
    text = "\n\n".join([p.text or "" for p in doc.pages])[:4000]
    text_html = f'<pre class="text-xs whitespace-pre-wrap">{(text or "No embedded text. Try OCR.").strip()}</pre>'

    return HTMLResponse(f"""
<div class="grid grid-cols-2 gap-3">
  <div class="rounded bg-slate-50 p-2">{grid}</div>
  <div class="rounded bg-slate-50 p-2 overflow-auto">{text_html}</div>
</div>
""")


# ------------------ Step 3: Prompts & engines ------------------

def _engines_prompts_card() -> str:
    fields_default = ", ".join(DEFAULT_FIELDS)
    return f"""
<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
  <div>
    <label class="text-sm">OCR</label>
    <select name="run_ocr" class="w-full mt-1 border rounded p-2">
      <option value="true" selected>Enabled (Tesseract)</option>
      <option value="false">Disabled</option>
    </select>
    <label class="block text-xs mt-2">OCR Language</label>
    <input name="ocr_lang" class="w-full mt-1 border rounded p-2" value="{CFG.TESSERACT_LANG}">
  </div>

  <div>
    <label class="text-sm">Chat Engine</label>
    <select name="chat_engine" class="w-full mt-1 border rounded p-2">
      <option value="http" selected>HTTP Chat API (vLLM/TGI)</option>
      <option value="ollama">Ollama</option>
      <option value="disabled">Disabled</option>
    </select>
  </div>
  <div>
    <label class="text-sm">Chat Model</label>
    <input name="chat_model" class="w-full mt-1 border rounded p-2" placeholder="{CFG.CHAT_API_MODEL} or {CFG.OLLAMA_CHAT_MODEL}">
    <div class="mt-2">
      <button class="text-xs px-2 py-1 bg-slate-200 rounded"
              hx-get="/models/ollama" hx-target="#ollama-models" hx-swap="innerHTML">List Ollama models</button>
      <div id="ollama-models" class="text-xs text-slate-600 mt-1"></div>
    </div>
  </div>

  <div class="md:col-span-2">
    <label class="text-sm">Chat Base URL</label>
    <input name="chat_base_url" class="w-full mt-1 border rounded p-2" placeholder="{CFG.CHAT_API_BASE_URL} or {CFG.OLLAMA_URL}">
  </div>

  <div>
    <label class="text-sm">Vision Engine</label>
    <select name="vision_engine" class="w-full mt-1 border rounded p-2">
      <option value="hf_vision" selected>HF Vision Doc-AI</option>
      <option value="disabled">Disabled</option>
    </select>
  </div>
  <div>
    <label class="text-sm">HF Vision Model</label>
    <input name="vision_model" class="w-full mt-1 border rounded p-2" placeholder="{CFG.HF_DOC_MODEL}">
  </div>
  <div>
    <label class="text-sm">HF Device</label>
    <input name="hf_device" class="w-full mt-1 border rounded p-2" value="{CFG.HF_DEVICE}" placeholder="cpu / cuda:0">
  </div>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
  <div>
    <label class="text-sm">Structured Fields (comma-separated)</label>
    <input name="fields" class="w-full mt-1 border rounded p-2" value="{fields_default}">
    <label class="text-sm block mt-3">System Prompt</label>
    <textarea name="system_prompt" rows="6" class="w-full mt-1 border rounded p-2"
>You are a meticulous data extractor. Return only valid JSON.</textarea>
  </div>
  <div>
    <label class="text-sm">Invoice Description / Operator Notes (optional)</label>
    <textarea name="invoice_description" rows="6" class="w-full mt-1 border rounded p-2"
      placeholder="eg. taxi receipt; vendor format X; VAT below total; etc."></textarea>
    <div class="mt-2 flex items-center gap-2">
      <button class="px-3 py-1 bg-slate-200 rounded text-sm"
              hx-post="/prompt/compose"
              hx-include="closest form"
              hx-target="#prompt-preview" hx-swap="innerHTML">Compose final prompt</button>
      <span class="text-xs text-slate-500">Uses fields + notes + context from the selected expense’s files</span>
    </div>
  </div>
</div>

<div class="mt-4">
  <div id="prompt-preview" class="rounded border bg-slate-50 p-3 text-xs text-slate-800">No preview yet.</div>
</div>
"""

@app.post("/step/3", response_class=HTMLResponse)
async def step3(
    start_date: str = Form(...), end_date: str = Form(...),
    expense_id: str = Form(None),  # must be provided
    file_ids: List[str] = Form(default=None)
):
    if not expense_id:
        return HTMLResponse(_page("Step 2", _card("Validation", _error("Please select one expense.")), 2))
    file_ids = file_ids or []

    form = f"""
<form hx-post="/step/4" hx-target="main" hx-include="this">
  <!-- keep scope & selection -->
  <input type="hidden" name="start_date" value="{start_date}"/>
  <input type="hidden" name="end_date" value="{end_date}"/>
  <input type="hidden" name="expense_id" value="{expense_id}"/>
  {''.join([f'<input type="hidden" name="file_ids" value="{f}"/>' for f in file_ids])}

  {_card("Step 3 — Prompts & engines", _engines_prompts_card())}
  {_card("Proceed", '<div class="flex justify-between"><a href="/" class="px-3 py-2 rounded bg-slate-100">Back</a><button class="px-4 py-2 rounded bg-blue-600 text-white">Review & launch</button></div>')}
</form>
"""
    return HTMLResponse(_page("Step 3 — Prompts & engines", form, 3))

@app.post("/prompt/compose", response_class=HTMLResponse)
async def compose_prompt(
    start_date: str = Form(...), end_date: str = Form(...),
    expense_id: str = Form(...), file_ids: List[str] = Form(default=None),
    fields: str = Form(...), system_prompt: str = Form(...), invoice_description: str = Form("")
):
    fields_list = [s.strip() for s in fields.split(",") if s.strip()] or DEFAULT_FIELDS
    schema_txt = build_schema_prompt(fields_list, invoice_description or "")

    # light context from first 2 files of the selected expense (or selected subset)
    context_snips = []
    try:
        pairs: List[str] = []
        files = await list_files(expense_id)
        want = set(file_ids or [])
        for f in files:
            if not want or str(f["id"]) in want:
                pairs.append(str(f["id"]))
            if len(pairs) >= 2: break
        for fid in pairs:
            try:
                name, raw = await fetch_file_b64(expense_id, fid)
                doc = normalize_file(name, raw, key_prefix=f"prompt/{expense_id}_{fid}")
                text = "\n\n".join([p.text or "" for p in doc.pages])[:1500]
                context_snips.append(text.strip())
            except Exception:
                continue
    except Exception:
        pass

    composed = (system_prompt or "").strip() + "\n\n" + schema_txt + ("\n\nContext:\n" + "\n---\n".join(context_snips) if context_snips else "")
    return HTMLResponse(f"<pre class='whitespace-pre-wrap text-xs'>{composed}</pre>")


# ------------------ Step 4: Review & launch ------------------

def _summary_list(items: Dict[str, str]) -> str:
    rows = "".join([f"<div class='flex justify-between text-sm'><div class='text-slate-500'>{k}</div><div class='font-medium'>{v}</div></div>" for k,v in items.items()])
    return f"<div class='space-y-1'>{rows}</div>"

@app.post("/step/4", response_class=HTMLResponse)
async def step4(
    start_date: str = Form(...), end_date: str = Form(...),
    expense_id: str = Form(...), file_ids: List[str] = Form(default=None),
    run_ocr: str = Form(...), ocr_lang: str = Form(...),
    chat_engine: str = Form(...), chat_model: str = Form(""),
    chat_base_url: str = Form(""), vision_engine: str = Form(...),
    vision_model: str = Form(""), hf_device: str = Form(""),
    fields: str = Form(...), system_prompt: str = Form(...), invoice_description: str = Form("")
):
    file_count = len(file_ids or [])
    fields_list = [s.strip() for s in fields.split(",") if s.strip()] or DEFAULT_FIELDS
    schema_txt = build_schema_prompt(fields_list, invoice_description or "")
    final_prompt = (system_prompt or "").strip() + "\n\n" + schema_txt

    left = _card("Step 4 — Review selection", _summary_list({
        "Expense": expense_id,
        "Date start": start_date or "—", "Date end": end_date or "—",
        "Files selected": str(file_count) if file_count else "— (all files in expense)"
    }))
    center = _card("Engines", _summary_list({
        "OCR": "Enabled" if run_ocr=="true" else "Disabled",
        "OCR lang": ocr_lang,
        "Chat engine": chat_engine,
        "Chat model": chat_model or "default",
        "Base URL": chat_base_url or "default",
        "Vision": vision_engine,
        "Vision model": vision_model or "default",
        "HF device": hf_device or "cpu"
    }))
    right = _card("Final prompt", f"<pre class='whitespace-pre-wrap text-xs'>{final_prompt}</pre>")

    form = f"""
<form hx-post="/launch" hx-target="#launch-result" hx-include="this" class="space-y-4">
  <!-- carry all fields -->
  {''.join([f'<input type="hidden" name="{k}" value="{v}"/>' for k,v in dict(
    start_date=start_date, end_date=end_date, expense_id=expense_id,
    run_ocr=run_ocr, ocr_lang=ocr_lang, chat_engine=chat_engine, chat_model=chat_model,
    chat_base_url=chat_base_url, vision_engine=vision_engine, vision_model=vision_model, hf_device=hf_device,
    fields=",".join(fields_list), system_prompt=system_prompt, invoice_description=invoice_description
  ).items()])}
  {''.join([f'<input type="hidden" name="file_ids" value="{f}"/>' for f in (file_ids or [])])}

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <div>{left}</div>
    <div>{center}</div>
    <div>{right}</div>
  </div>

  <div class="flex justify-between">
    <button hx-get="/" class="px-3 py-2 rounded bg-slate-100" type="button">Back</button>
    <button class="px-4 py-2 rounded bg-blue-600 text-white">Launch pipeline</button>
  </div>
</form>
<div id="launch-result" class="mt-3"></div>
"""
    return HTMLResponse(_page("Step 4 — Review & launch", form, 4))


# ------------------ Launch / Monitor ------------------

@app.post("/launch", response_class=HTMLResponse)
async def launch(
    start_date: str = Form(...), end_date: str = Form(...),
    expense_id: str = Form(...), file_ids: List[str] = Form(default=None),
    run_ocr: str = Form("true"), ocr_lang: str = Form(CFG.TESSERACT_LANG),
    chat_engine: str = Form("http"), chat_model: str = Form(""),
    chat_base_url: str = Form(""), vision_engine: str = Form("hf_vision"),
    vision_model: str = Form(""), hf_device: str = Form(""),
    fields: str = Form(""), system_prompt: str = Form(""), invoice_description: str = Form("")
):
    spec = JobSpec(
        start_date=start_date or None,
        end_date=end_date or None,
        expense_id=str(expense_id),
        file_ids=[s.strip() for s in (file_ids or []) if s.strip()] or None,
        run_ocr=(run_ocr.lower()=="true"),
        ocr_lang=ocr_lang.strip() or CFG.TESSERACT_LANG,
        chat_engine=chat_engine,
        chat_model=(chat_model or None),
        chat_base_url=(chat_base_url or None),
        vision_engine=vision_engine,
        vision_model=(vision_model or None),
        hf_device=(hf_device or None),
        fields=[s.strip() for s in (fields or ", ".join(DEFAULT_FIELDS)).split(",") if s.strip()],
        system_prompt=(system_prompt or "You are a meticulous data extractor. Return only valid JSON."),
        invoice_description=(invoice_description or "")
    )
    st = JobStatus(spec=spec)
    JOBS[st.job_id] = st
    asyncio.create_task(run_job(spec, st))
    return HTMLResponse(f"""
<div class="text-green-700">
  Launched job <a class="underline" href="/job/{st.job_id}">{st.job_id}</a>.
</div>
""")

@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_detail(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        h = next((x for x in HISTORY if x["job_id"] == job_id), None)
        if not h:
            raise HTTPException(404, "job not found")
        spec = h.get("spec", {})
        body = _card("Job (archived)", f"""
<div class="text-slate-600">This job is from history (server restarted).</div>
<h4 class="font-semibold mt-3 mb-1">Artifacts</h4>
<pre class="text-xs bg-slate-50 p-2 rounded overflow-auto">{json.dumps(h.get("artifacts",{}), indent=2, ensure_ascii=False)}</pre>
<h4 class="font-semibold mt-3 mb-1">Spec</h4>
<pre class="text-xs bg-slate-50 p-2 rounded overflow-auto">{json.dumps(spec, indent=2, ensure_ascii=False)}</pre>
<a class="inline-block mt-3 px-3 py-2 bg-slate-200 rounded" href="/">Back</a>
""")
        return HTMLResponse(_page(f"Job {job_id}", body, 5))

    # Results table
    result_rows=[]
    for k, _pred in j.results.items():
        viewbtn = f'<a class="text-blue-600 underline text-sm" href="/job/{job_id}/item?k={k}">view</a>'
        result_rows.append(f"<tr class='border-b'><td class='py-2'>{k}</td><td class='py-2'>{viewbtn}</td><td class='py-2 text-xs'>{j.message or ''}</td></tr>")
    result_table = f"""
<table class="w-full bg-white rounded shadow mt-2">
  <thead class="bg-slate-100"><tr><th class="text-left py-2 px-2">Item</th><th class="text-left py-2 px-2">Details</th><th class="text-left py-2 px-2">Note</th></tr></thead>
  <tbody>{''.join(result_rows) if result_rows else '<tr><td class="p-3 text-slate-500" colspan="3">No results yet.</td></tr>'}</tbody>
</table>
"""

    logs = f"""
<div id="logbox" class="bg-black text-green-300 font-mono text-xs p-3 h-64 overflow-auto"
     hx-ext="sse" sse-connect="/events/{j.job_id}" sse-swap="message">
  <div>waiting for logs…</div>
</div>
"""

    header = f"""
<div class="flex items-center justify-between">
  <div><div class="text-sm text-slate-500">Job</div><div class="font-mono">{j.job_id}</div></div>
  <div><span class="px-3 py-1 rounded bg-slate-200">{j.phase}</span><span class="ml-2 text-sm">{int(j.progress*100)}%</span></div>
</div>
"""

    body = _card("Step 5 — Monitor & compare", header + logs + "<h4 class='font-semibold mt-4'>Results</h4>" + result_table + '<div class="mt-4"><a class="px-4 py-2 bg-slate-200 rounded" href="/">Back</a></div>')
    return HTMLResponse(_page(f"Job {job_id}", body, 5))

@app.get("/job/{job_id}/item", response_class=HTMLResponse)
def job_item(job_id: str, k: str = Query(...)):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")
    pred = j.results.get(k, {})
    art_ref = j.artifacts.get(k)
    gt, diff = None, None
    try:
        if art_ref and art_ref.startswith("file://"):
            with open(art_ref.replace("file://",""), "rb") as f:
                art = json.loads(f.read().decode())
            gt = art.get("gt")
            diff = art.get("diff")
    except Exception:
        pass

    a = f"<pre class='text-xs bg-slate-50 p-2 rounded overflow-auto'>{json.dumps(gt, indent=2, ensure_ascii=False) if gt else '—'}</pre>"
    b = f"<pre class='text-xs bg-slate-50 p-2 rounded overflow-auto'>{json.dumps(pred, indent=2, ensure_ascii=False)}</pre>"
    c = f"<pre class='text-xs bg-slate-50 p-2 rounded overflow-auto'>{json.dumps(diff, indent=2, ensure_ascii=False) if diff else '—'}</pre>"

    grid = f"""
<div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
  <div><h4 class="font-semibold mb-2">Ground Truth</h4>{a}</div>
  <div><h4 class="font-semibold mb-2">Prediction</h4>{b}</div>
  <div><h4 class="font-semibold mb-2">DeepDiff</h4>{c}</div>
</div>
<div class="mt-4"><a class="px-3 py-2 rounded bg-slate-100" href="/job/{job_id}">Back</a></div>
"""
    return HTMLResponse(_page(f"Job {job_id} — {k}", _card(k, grid), 5))

@app.get("/models/ollama", response_class=HTMLResponse)
async def models_ollama():
    if httpx is None:
        return HTMLResponse("<div>httpx missing</div>")
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{CFG.OLLAMA_URL.rstrip('/')}/api/tags")
            r.raise_for_status()
            data = r.json()
        items = data.get("models", [])
        opts = []
        for m in items:
            name = m.get("name") or m.get("model") or "unknown"
            size = m.get("size", 0)
            sz = f"{size/1e9:.2f} GB" if isinstance(size,(int,float)) and size>0 else ""
            opts.append(f"<option value='{name}'>{name} {sz}</option>")
        html = f"""
<label class="block text-xs font-medium mt-2">Ollama Installed Models</label>
<select class="w-full border rounded p-2 text-xs" onchange="document.querySelector('[name=chat_model]').value=this.value;">
  {''.join(opts) if opts else '<option>(none)</option>'}
</select>
"""
        return HTMLResponse(html)
    except Exception as e:
        return HTMLResponse(f"<div class='text-red-700 text-xs'>Ollama list failed: {e}</div>")

# SSE (escape newlines)
@app.get("/events/{job_id}")
async def sse_events(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "job not found")

    async def eventgen():
        last_idx = 0
        yield "event: message\ndata: {}\n\n".format(f"Started job {job_id}")
        while True:
            await asyncio.sleep(1.0)
            if job_id not in JOBS:
                break
            cur = JOBS[job_id]
            if last_idx < len(cur.logs):
                for i in range(last_idx, len(cur.logs)):
                    msg = (cur.logs[i] or "").replace("\n", "\\n")
                    yield "event: message\ndata: {}\n\n".format(msg)
                last_idx = len(cur.logs)
            if cur.phase in ("completed", "failed") and last_idx == len(cur.logs):
                yield "event: message\ndata: {}\n\n".format(f"[END] phase={cur.phase}")
                break

    return StreamingResponse(eventgen(), media_type="text/event-stream")

# Health
@app.get("/health", response_class=PlainTextResponse)
def health():
    return "ok"

# ----------------------------- Main -----------------------------

if __name__ == "__main__":
    try:
        import uvicorn
    except Exception:
        print("Install uvicorn: pip install 'uvicorn[standard]'")
        sys.exit(1)
    print(f"Extractor Pipeline UI → http://{CFG.HOST}:{CFG.PORT}")
    uvicorn.run(app, host=CFG.HOST, port=CFG.PORT)
