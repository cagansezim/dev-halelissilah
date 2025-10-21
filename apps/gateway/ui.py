# apps/gateway/ui.py
from __future__ import annotations

import base64
import io
import json
import os
import pathlib
import secrets
import shutil
import time
import mimetypes
from collections import deque, defaultdict
from typing import Any, Deque, Dict, List, Tuple, Optional

from fastapi import APIRouter, Body, Depends, Response, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from PIL import Image

from apps.gateway.deps import get_internal_client, get_s3_store, get_av
from packages.clients.internal_api.client import InternalAPIClient, InternalAPIError
from packages.storage.s3_store import S3Store
from packages.shared.av import AVScanner

# ------------------------------- globals ------------------------------------ #

router = APIRouter(tags=["ui", "dataset", "ocr", "ai", "metrics", "config", "live"])
STATE_ROOT = pathlib.Path("./_state")
SESSION_ROOT = pathlib.Path("./_sessions")

# live API event ring buffer
API_EVENTS: Deque[Dict[str, Any]] = deque(maxlen=500)  # bumped to 500

# --------------------------------------------------------------------------- #
# State & config helpers
# --------------------------------------------------------------------------- #

def _now_ts() -> float:
    return time.time()

def _ensure_dir(p: pathlib.Path) -> pathlib.Path:
    p.mkdir(parents=True, exist_ok=True)
    return p

def _state_file(name: str) -> pathlib.Path:
    return _ensure_dir(STATE_ROOT) / name

def _config_path() -> pathlib.Path:
    return _state_file("config.json")

def _load_user_config() -> Dict[str, Any]:
    try:
        return json.loads(_config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_user_config(cfg: Dict[str, Any]) -> None:
    _config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def _get_effective_config() -> Dict[str, Any]:
    """
    Merge environment and user overrides (user overrides win).
    Only includes settings that affect this UI service.
    """
    env = {
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_HOST") or "http://ollama:11434",
        "INTERNAL_API_BASE": os.getenv("INTERNAL_API_BASE", ""),
        "S3_ENDPOINT": os.getenv("S3_ENDPOINT", ""),
        "S3_BUCKET": os.getenv("S3_BUCKET", ""),
        "S3_REGION": os.getenv("S3_REGION", ""),
    }
    user = _load_user_config()
    eff = {**env, **(user.get("overrides") or {})}
    return {"env": env, "user_overrides": user.get("overrides") or {}, "effective": eff}

def _get_ollama_base_url() -> str:
    eff = _get_effective_config()["effective"]
    return (eff.get("OLLAMA_BASE_URL") or "http://ollama:11434").rstrip("/")

# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _dataset_root(s3: S3Store) -> pathlib.Path:
    local = getattr(s3, "local_root", None)
    if local:
        p = pathlib.Path(local)
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = pathlib.Path("./_dataset").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p

def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return "{}"

def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii")

def _b64url_dec(s: str) -> str:
    return base64.urlsafe_b64decode(s.encode("ascii")).decode("utf-8")

def _session_dir(session_id: str) -> pathlib.Path:
    sid = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))[:64] or "default"
    return _ensure_dir(SESSION_ROOT / sid)

def _upload_dir(session_id: str) -> pathlib.Path:
    return _ensure_dir(_session_dir(session_id) / "uploads")

def _guess_mime(path: pathlib.Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"

def _record_api_event(kind: str, status: int, ms: float, meta: Dict[str, Any] | None = None):
    API_EVENTS.appendleft({
        "ts": int(_now_ts()),
        "kind": kind,
        "status": status,
        "ms": round(ms, 1),
        "meta": meta or {},
    })

# poor-man HTTP (no extra deps)
def _http_json(method: str, url: str, payload: Optional[dict] = None, timeout: float = 90.0) -> dict:
    import urllib.request, urllib.error
    data = None
    headers = {"content-type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            b = r.read()
            out = json.loads(b.decode("utf-8")) if b else {}
            _record_api_event("ollama:"+method, r.status, (time.time()-t0)*1000, {"url": url})
            return out
    except urllib.error.HTTPError as e:
        try:
            err = e.read().decode("utf-8")
        except Exception:
            err = str(e)
        _record_api_event("ollama:"+method, int(getattr(e, "code", 500)), (time.time()-t0)*1000, {"url": url})
        return {"error": err, "status": getattr(e, "code", 500)}
    except Exception as e:
        _record_api_event("ollama:"+method, 599, (time.time()-t0)*1000, {"url": url})
        return {"error": str(e)}

# --------------------------------------------------------------------------- #
# Derived metrics & summaries
# --------------------------------------------------------------------------- #

def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    k = int(round((len(values)-1) * p))
    return float(values[k])

def _scan_items_under(root: pathlib.Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if not root.exists():
        return items
    for meta_path in root.rglob("meta.json"):
        try:
            rel = meta_path.parent.relative_to(root)
            name = rel.name
            if not name.startswith("file_"): continue
            _, rest = name.split("file_", 1)
            file_id_str, file_hash = rest.split("_", 1)
            file_id = int(file_id_str)
            kod_folder = rel.parent.name
            if not kod_folder.startswith("kod_"): continue
            kod = int(kod_folder.split("_", 1)[1])
            item_id = _b64url(str(rel))
            items.append({"id": item_id, "kod": kod, "fileId": file_id, "fileHash": file_hash})
        except Exception:
            continue
    items.sort(key=lambda x: (x["kod"], x["fileId"]))
    return items

def _dataset_summary(s3: S3Store) -> Dict[str, Any]:
    root = _dataset_root(s3) / "dataset"
    items = _scan_items_under(root)
    total_bytes = 0
    uniq_kod = set()
    last_ts = 0
    latest: List[Dict[str, Any]] = []
    for it in items:
        meta_path = root / pathlib.Path(_b64url_dec(it["id"])) / "meta.json"
        try:
            js = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            js = {}
        size = int(js.get("size_bytes") or 0)
        ts = int(js.get("ts") or 0)
        total_bytes += size
        uniq_kod.add(it["kod"])
        if ts > last_ts:
            last_ts = ts
        latest.append({"kod": it["kod"], "fileId": it["fileId"], "size_bytes": size, "ts": ts})
    latest.sort(key=lambda x: x.get("ts") or 0, reverse=True)
    return {
        "count": len(items),
        "bytes": total_bytes,
        "unique_kods": len(uniq_kod),
        "last_ts": last_ts,
        "latest": latest[:8],
    }

def _live_summary() -> Dict[str, Any]:
    evs = list(API_EVENTS)
    total = len(evs)
    by_kind: Dict[str, int] = defaultdict(int)
    by_status: Dict[str, int] = defaultdict(int)
    lat_all: List[float] = []
    lat_by_kind: Dict[str, List[float]] = defaultdict(list)
    last_error_ts = 0
    for e in evs:
        k = str(e.get("kind") or "")
        s = str(e.get("status") or "")
        ms = float(e.get("ms") or 0.0)
        by_kind[k] += 1
        by_status[s] += 1
        lat_all.append(ms)
        lat_by_kind[k].append(ms)
        st = int(e.get("status") or 0)
        if st >= 400:
            last_error_ts = max(last_error_ts, int(e.get("ts") or 0))
    def lat_stats(vals: List[float]) -> Dict[str, Optional[float]]:
        if not vals: return {"avg": None, "p50": None, "p95": None}
        return {
            "avg": round(sum(vals)/len(vals), 1),
            "p50": _percentile(vals, 0.50),
            "p95": _percentile(vals, 0.95),
        }
    per_kind = {k: lat_stats(v) for k, v in lat_by_kind.items()}
    overall = lat_stats(lat_all)
    return {
        "total": total,
        "last_5": evs[:5],
        "by_kind": by_kind,
        "by_status": by_status,
        "latency": {"overall": overall, "per_kind": per_kind},
        "errors": {"count": sum(1 for e in evs if int(e.get("status") or 0) >= 400), "last_ts": last_error_ts},
    }

# --------------------------------------------------------------------------- #
# HTML — modernized app shell + rich dashboard
# --------------------------------------------------------------------------- #

@router.get("/ui", response_class=HTMLResponse)
def ui() -> str:
    return r"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>Pruva AI — Control Panel</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  :root{
    --ink:#0b1222; --muted:#6b7280; --line:#e9edf3; --bg:#f7f9fc; --card:#fff;
    --chip:#eef3ff; --primary:#2563eb; --ok:#10b981; --warn:#f59e0b; --danger:#ef4444;
    --dark:#0f172a; --accent:#7c92ff;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{margin:0;font:14px system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg)}
  .shell{display:grid;grid-template-columns:280px 1fr;min-height:100vh}
  aside{padding:18px;border-right:1px solid var(--line);background:#fff}
  main{padding:24px 28px 80px}
  h1{margin:0 0 6px;font-size:22px}
  h2{margin:10px 0 4px;font-size:16px}
  h3{margin:0;font-size:13px;padding:12px 14px;border-bottom:1px dashed var(--line);letter-spacing:.02em;color:#111}
  .muted{color:var(--muted)}
  .row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .pill{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:6px 10px;background:#fff;font-size:12px}
  .badge{background:var(--chip);padding:4px 8px;border-radius:8px;display:inline-block}
  input,button,select,textarea{padding:8px 10px;border:1px solid var(--line);border-radius:10px;background:#fff;font:inherit}
  textarea{resize:vertical}
  button{background:var(--primary);color:#fff;border:0;cursor:pointer}
  button.secondary{background:#fff;color:#111;border:1px solid var(--line)}
  button.ghost{background:transparent;border:1px dashed var(--line);color:#111}
  button:disabled{opacity:.6;cursor:not-allowed}
  .grid{display:grid;gap:18px}
  .grid.cols-3{grid-template-columns:1fr 1fr 1fr}
  .grid.cols-2{grid-template-columns:1fr 1fr}
  .grid.cols-1-1-2{grid-template-columns:1fr 1fr 2fr}
  .grid.cols-1-2{grid-template-columns:1fr 2fr}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
  .pad{padding:12px 14px}
  .pad-sm{padding:8px 10px}
  .kv{display:grid;grid-template-columns:160px 1fr;gap:8px;align-items:start}
  .kv>div{padding:4px 0;border-bottom:1px dashed var(--line)}
  .kv .k{color:#334155;font-size:12px}
  .mono{font-family:ui-monospace,Menlo,Consolas,monospace}
  .right{text-align:right}
  .nav a{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:10px;color:#111;text-decoration:none}
  .nav a.active{background:#eef3ff}
  .stat-tiles{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:12px}
  .tile{background:linear-gradient(180deg,#ffffff,#f7faff);border:1px solid var(--line);border-radius:12px;padding:10px 12px}
  .tile .val{font-weight:700;font-size:18px}
  .tile .sub{font-size:11px;color:var(--muted)}
  .table{width:100%;border-collapse:separate;border-spacing:0 8px}
  .table th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:#475569;text-align:left;padding:0 10px}
  .table td{background:#fff;border:1px solid var(--line);border-left:0;border-right:0;padding:10px 12px}
  .table tr td:first-child{border-left:1px solid var(--line);border-top-left-radius:10px;border-bottom-left-radius:10px}
  .table tr td:last-child{border-right:1px solid var(--line);border-top-right-radius:10px;border-bottom-right-radius:10px}
  .chip{display:inline-block;padding:2px 8px;border-radius:999px;background:#eef3ff;font-size:11px;color:#334155}
  .chip.ok{background:#e6fcef;color:#065f46}
  .chip.err{background:#fde2e2;color:#991b1b}
  .chip.warn{background:#fff4d6;color:#8a6d1e}
  .toolbar{display:flex;gap:8px;align-items:center;justify-content:space-between}
  .toolbar .left,.toolbar .right{display:flex;gap:8px;align-items:center}
  details.disc{background:#f8fafc;border:1px dashed var(--line);border-radius:10px;padding:8px 10px}
  details.disc>summary{cursor:pointer;font-weight:600;font-size:12px;color:#334155}
  pre.json{margin:0;padding:12px;background:var(--dark);color:#d7e3ff;border-radius:10px;height:420px;overflow:auto;font:12px ui-monospace,Menlo,Consolas,monospace}
  .pv4{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .pvbox{height:180px;background:#0b1222;border-radius:12px;display:flex;align-items:center;justify-content:center;color:#9fb3ff;overflow:hidden}
  .pvbox img{max-width:100%;max-height:100%;display:block}
  .thumb{width:140px;height:140px;background:#0b1222;border-radius:12px;display:flex;align-items:center;justify-content:center;overflow:hidden}
  .thumb img{max-width:100%;max-height:100%;display:block}
  .gridDataset{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}
  .chatWrap{display:grid;grid-template-columns:1fr 370px;gap:18px}
  .chatBox{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px;height:64vh;overflow:auto}
  .bubble{max-width:76%;margin:10px 0;padding:12px 14px;border:1px solid var(--line);border-radius:12px}
  .bubble.me{margin-left:auto;background:#eef3ff}
  .bubble.ai{background:#fff}
  .bubble .tag{font-size:11px;padding:2px 6px;border-radius:6px;background:#eef2ff;margin-left:6px}
  .attach{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border:1px dashed var(--line);border-radius:10px;margin-right:6px;font-size:12px;background:#fff}
  .attach img{width:24px;height:24px;object-fit:cover;border-radius:5px;border:1px solid var(--line)}
  .extractCard{border:1px solid var(--line);border-radius:12px;padding:12px;margin-top:10px;background:#fcfdfd}
  .extractGrid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .itemsTable{width:100%;border-collapse:collapse}
  .itemsTable th,.itemsTable td{border-bottom:1px dashed var(--line);padding:6px 8px;text-align:left}
  .small{font-size:12px;color:#64748b}
  .sparkline{width:100%;height:40px}
  #activity{background:var(--dark);color:#d7e3ff;padding:10px;border-radius:10px;height:200px;overflow:auto;font:12px ui-monospace,Menlo,Consolas,monospace}
  .progress{width:100%;height:8px;border-radius:999px;background:#eef2ff;overflow:hidden}
  .progress>span{display:block;height:100%;background:linear-gradient(90deg,#60a5fa,#34d399)}
  .search{padding:8px 10px;border:1px solid var(--line);border-radius:10px;background:#fff}
</style>
</head>
<body>
<div class="shell">
  <aside>
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:14px">
      <div style="width:34px;height:34px;border-radius:10px;background:#eef3ff"></div>
      <div><div style="font-weight:700">Pruva AI</div><div class="muted">Invoice Extraction</div></div>
    </div>

    <div class="muted" style="font-size:12px;margin:10px 0 6px">Menu</div>
    <div class="nav">
      <a href="#dash" id="nav-dash">🏠 Dashboard</a>
      <a href="#tune" id="nav-tune">🧪 Tune data</a>
      <a href="#dataset" id="nav-dataset">🗂️ Dataset</a>
      <a href="/ai_chat" id="nav-chat">💬 AI Chat</a>
      <a href="#config" id="nav-config">⚙️ Config</a>
      <a href="#live" id="nav-live">📡 Live API</a>
      <a href="#apis" id="nav-apis">📚 APIs & Docs</a>
    </div>

    <div class="muted" style="font-size:12px;margin:16px 0 6px">Live stats</div>
    <div class="grid cols-2">
      <div class="card">
        <h3>Internal API</h3>
        <div class="pad" id="stat-api">checking…</div>
      </div>
      <div class="card">
        <h3>Storage</h3>
        <div class="pad" id="stat-s3">—</div>
      </div>
      <div class="card">
        <h3>CPU / RAM</h3>
        <div class="pad">
          <div id="stat-sys">—</div>
          <canvas id="memSpark" class="sparkline"></canvas>
        </div>
      </div>
      <div class="card">
        <h3>Docker</h3>
        <div class="pad" id="stat-docker">—</div>
      </div>
      <div class="card">
        <h3>Ollama</h3>
        <div class="pad" id="stat-ollama">—</div>
      </div>
      <div class="card">
        <h3>Events</h3>
        <div class="pad" id="stat-events">—</div>
      </div>
    </div>
  </aside>

  <main>
    <!-- Dashboard ------------------------------------------------------- -->
    <section id="page-dash" style="display:none">
      <h1>Dashboard</h1>
      <div class="muted" style="margin-bottom:12px">System, models, dataset and runtime snapshots. Click “Raw JSON” to see everything.</div>

      <div class="stat-tiles" id="dashTiles">
        <div class="tile"><div class="sub">Uptime</div><div class="val" id="tileUp">—</div></div>
        <div class="tile"><div class="sub">RAM</div><div class="val" id="tileMem">—</div></div>
        <div class="tile"><div class="sub">Load (1/5/15)</div><div class="val" id="tileLoad">—</div></div>
        <div class="tile"><div class="sub">Dataset items</div><div class="val" id="tileDS">—</div></div>
        <div class="tile"><div class="sub">Dataset size</div><div class="val" id="tileDSz">—</div></div>
        <div class="tile"><div class="sub">Disk free</div><div class="val" id="tileDisk">—</div></div>
      </div>

      <div class="grid cols-1-1-2" style="margin-top:14px">
        <div class="card">
          <h3>Gateway status</h3>
          <div class="pad">
            <div class="kv" id="dashStatusKV"></div>
            <details class="disc" style="margin-top:10px">
              <summary>Raw JSON</summary>
              <pre class="json" id="dashStatusRaw">{}</pre>
            </details>
          </div>
        </div>

        <div class="card">
          <h3>Metrics</h3>
          <div class="pad">
            <div class="kv" id="dashMetricsKV"></div>
            <details class="disc" style="margin-top:10px">
              <summary>Raw JSON</summary>
              <pre class="json" id="dashMetricsRaw">{}</pre>
            </details>
          </div>
        </div>

        <div class="card">
          <div class="toolbar pad">
            <div class="left"><h2 style="margin:0">Ollama Models</h2></div>
            <div class="right"><button class="secondary" id="dashReload">Reload</button></div>
          </div>
          <div class="pad">
            <table class="table" id="dashModelsTable">
              <thead><tr><th>Name</th><th>Family</th><th class="right">Size</th><th>Details</th></tr></thead>
              <tbody></tbody>
            </table>
            <details class="disc" style="margin-top:10px">
              <summary>Raw JSON</summary>
              <pre class="json" id="dashModelsRaw">{}</pre>
            </details>
          </div>
        </div>
      </div>

      <div class="grid cols-2" style="margin-top:14px">
        <div class="card">
          <h3>Recent events</h3>
          <div class="pad">
            <table class="table" id="dashEvents">
              <thead><tr><th>Time</th><th>Kind</th><th>Status</th><th class="right">Latency (ms)</th></tr></thead>
              <tbody></tbody>
            </table>
          </div>
        </div>
        <div class="card">
          <h3>Event summary</h3>
          <div class="pad">
            <div class="kv" id="dashEventKV"></div>
            <details class="disc" style="margin-top:10px">
              <summary>Raw summary JSON</summary>
              <pre class="json" id="dashEventRaw">{}</pre>
            </details>
          </div>
        </div>
      </div>

      <div class="grid cols-1-2" style="margin-top:14px">
        <div class="card">
          <h3>Dataset highlights</h3>
          <div class="pad">
            <div class="kv" id="dashDatasetKV"></div>
            <details class="disc" style="margin-top:10px">
              <summary>Latest items</summary>
              <pre class="json" id="dashDatasetRaw">{}</pre>
            </details>
          </div>
        </div>
        <div class="card">
          <h3>Notes</h3>
          <div class="pad small">
            This dashboard aggregates <span class="mono">/api/status</span>, <span class="mono">/api/metrics</span>, <span class="mono">/api/llm/models</span>, dataset summary, and live event summaries.
          </div>
        </div>
      </div>
    </section>

    <!-- Tune ------------------------------------------------------------ -->
    <section id="page-tune" style="display:none">
      <h1>Tune data</h1>
      <div class="muted" style="margin-bottom:12px">Fetch expenses and files, preview, run OCR/AI, and add to your dataset.</div>

      <div class="toolbar">
        <div class="left row">
          <div><div class="muted" style="font-size:12px">Start</div><input id="start" type="date" /></div>
          <div><div class="muted" style="font-size:12px">End</div><input id="end" type="date" /></div>
          <button id="btnLoad">Load expenses</button>
          <span class="pill">/api/expenses → /api/expense → /api/preview → /api/collect</span>
        </div>
        <div class="right row">
          <button class="secondary" id="btnSelectAll" disabled>Select all files</button>
          <button class="secondary" id="btnBulkOCR" disabled>Bulk OCR</button>
          <button class="secondary" id="btnBulkAI" disabled>Bulk AI</button>
          <button id="btnAdd" disabled>Add to dataset</button>
        </div>
      </div>

      <div class="grid cols-3" style="margin-top:12px">
        <!-- Expenses -->
        <div class="card">
          <h3>Expenses <span id="expCount" class="muted"></span></h3>
          <div class="pad">
            <input id="expSearch" class="search" placeholder="Search in description / department / KOD…">
            <table class="table" id="tblExpenses" style="margin-top:8px">
              <thead><tr><th>KOD</th><th>AÇIKLAMA</th><th>BÖLÜM</th><th>HASH</th></tr></thead>
              <tbody></tbody>
            </table>
            <details class="disc" style="margin-top:8px"><summary>Last expense raw</summary><pre class="json" id="lastExpenseRaw">{}</pre></details>
          </div>
        </div>

        <!-- Files / JSON -->
        <div class="card">
          <div class="pad toolbar">
            <div class="left row">
              <button class="pill" id="tabFiles">Files</button>
              <button class="pill" id="tabSelected">Selected (0)</button>
              <button class="pill" id="tabJSON">Expense JSON</button>
            </div>
            <div class="right small muted" id="filesSummary">—</div>
          </div>
          <div class="pad" id="paneFiles">
            <table class="table" id="tblFiles">
              <thead><tr><th></th><th>FILEID</th><th>ORIGINAL</th><th>HASH</th><th>TYPE</th><th class="right">SIZE</th></tr></thead>
              <tbody><tr><td colspan="6">No files</td></tr></tbody>
            </table>
          </div>
          <div class="pad" id="paneJSON" style="display:none">
            <pre class="json" id="jsonView">{}</pre>
          </div>
        </div>

        <!-- Preview & actions -->
        <div class="card">
          <h3>Preview</h3>
          <div class="pad">
            <div class="pv4">
              <div class="pvbox" id="pv1">Select a file</div>
              <div class="pvbox" id="pv2">Select a file</div>
              <div class="pvbox" id="pv3">Select a file</div>
              <div class="pvbox" id="pv4">Select a file</div>
            </div>
            <div class="row" style="margin-top:10px">
              <button id="btnOCR" disabled>Run OCR</button>
              <button id="btnAI" disabled>AI extract</button>
            </div>
            <div class="small" style="margin-top:8px">Bulk status</div>
            <div class="progress"><span id="bulkProg" style="width:0%"></span></div>
          </div>

          <h3>Activity</h3>
          <div class="pad"><div id="activity"></div></div>
        </div>
      </div>
    </section>

    <!-- Dataset ---------------------------------------------------------- -->
    <section id="page-dataset" style="display:none">
      <h1>Dataset</h1>
      <div class="toolbar">
        <div class="left">
          <button id="btnReloadDataset" class="secondary">Reload</button>
          <span id="dsCount" class="badge">0 items</span>
        </div>
        <div class="right">
          <input id="dsSearch" class="search" placeholder="Filter by kod / fileId…">
        </div>
      </div>
      <div class="grid cols-2" style="margin-top:12px">
        <div class="card">
          <h3>Items</h3>
          <div class="pad">
            <div id="datasetGrid" class="gridDataset"></div>
          </div>
        </div>
        <div class="card">
          <h3>Meta (structured)</h3>
          <div class="pad">
            <div class="kv" id="dsMetaKV"></div>
            <details class="disc" style="margin-top:10px">
              <summary>Raw JSON</summary>
              <pre class="json" id="dsMeta">{}</pre>
            </details>
          </div>
          <h3>Files for this expense (siblings)</h3>
          <div class="pad">
            <div id="dsSiblings" class="gridDataset"></div>
          </div>
        </div>
      </div>
    </section>

    <!-- AI Chat ---------------------------------------------------------- -->
    <section id="page-chat" style="display:none">
      <h1>AI Chat</h1>
      <div class="muted" style="margin-bottom:12px">Chat to <span class="mono">/api/llm/chat</span>. Sessions are stored locally in your browser.</div>

      <div class="chatWrap">
        <!-- left: messages -->
        <div class="chatBox" id="chatBox"></div>

        <!-- right: controls -->
        <div>
          <div class="card">
            <h3>Session</h3>
            <div class="pad">
              <div class="row" style="margin-bottom:8px">
                <select id="sessionSel" style="flex:1"></select>
                <button class="secondary" id="btnNew">New</button>
                <button class="secondary" id="btnDelete">Delete</button>
              </div>
              <div class="row" style="margin-bottom:8px">
                <button class="secondary" id="btnExport">Export</button>
                <select id="modelSel" style="flex:1"><option value="">No models</option></select>
                <button class="secondary" id="btnReloadModels">Reload models</button>
              </div>
              <textarea id="sysPrompt" rows="3" placeholder="Optional system prompt (English enforced)"></textarea>
              <div class="small" style="margin-top:6px">
                Expected first JSON block (auto-parsed):
                <span class="mono">{"merchant":"...", "date":"YYYY-MM-DD", "total":0, "currency":"TRY","items":[...]}</span>
              </div>
            </div>
          </div>

          <div class="card" style="margin-top:12px">
            <h3>Attachments</h3>
            <div class="pad">
              <input id="filePick" type="file" multiple accept="image/*,.pdf,.png,.jpg,.jpeg" />
              <div id="attachList" class="small" style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px"></div>
            </div>
          </div>

          <div class="card" style="margin-top:12px">
            <h3>Message</h3>
            <div class="pad">
              <textarea id="msgBox" rows="4" placeholder="Type your message and press Send…"></textarea>
              <div class="row" style="margin-top:8px;justify-content:flex-end">
                <button id="btnSend">Send</button>
              </div>
            </div>
          </div>

          <div class="card" style="margin-top:12px">
            <h3>Last raw model response</h3>
            <div class="pad">
              <details class="disc">
                <summary>Raw JSON</summary>
                <pre class="json" id="lastChatRaw">{}</pre>
              </details>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Config ----------------------------------------------------------- -->
    <section id="page-config" style="display:none">
      <h1>Config</h1>
      <div class="muted" style="margin-bottom:12px">Environment vs overrides. Changes apply immediately for Ollama URL.</div>
      <div class="grid cols-2">
        <div class="card">
          <h3>Effective</h3>
          <div class="pad">
            <div class="kv" id="cfgEffectiveKV"></div>
            <details class="disc" style="margin-top:10px"><summary>Raw JSON</summary><pre class="json" id="cfgEffective">{}</pre></details>
          </div>
        </div>
        <div class="card">
          <h3>Edit overrides</h3>
          <div class="pad">
            <div class="row"><label style="width:160px">OLLAMA_BASE_URL</label><input id="ovOllama" placeholder="http://localhost:11434" style="flex:1"></div>
            <div class="row" style="margin-top:6px"><label style="width:160px">INTERNAL_API_BASE</label><input id="ovInternal" placeholder="https://internal.example/api" style="flex:1"></div>
            <div class="row" style="margin-top:6px"><label style="width:160px">S3_ENDPOINT</label><input id="ovS3e" placeholder="http://minio:9000" style="flex:1"></div>
            <div class="row" style="margin-top:6px"><label style="width:160px">S3_BUCKET</label><input id="ovS3b" placeholder="pruva" style="flex:1"></div>
            <div class="row" style="margin-top:6px"><label style="width:160px">S3_REGION</label><input id="ovS3r" placeholder="us-east-1" style="flex:1"></div>
            <div class="row" style="margin-top:10px">
              <button id="btnCfgSave">Save overrides</button>
              <button class="secondary" id="btnCfgClear">Clear</button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Live API Mgmt ---------------------------------------------------- -->
    <section id="page-live" style="display:none">
      <h1>Live API Mgmt</h1>
      <div class="muted" style="margin-bottom:12px">Recent gateway & Ollama calls. Filter, inspect metadata, and export to CSV.</div>
      <div class="toolbar">
        <div class="left">
          <button id="btnLiveRefresh" class="secondary">Refresh</button>
          <button id="btnLiveClear" class="secondary">Clear</button>
          <button id="btnLiveCSV" class="secondary">Export CSV</button>
          <span class="badge" id="liveCount">0 events</span>
        </div>
        <div class="right">
          <input id="liveFilter" class="search" placeholder="Filter (kind:ollama status:200 text)">
        </div>
      </div>
      <div class="card" style="margin-top:10px">
        <div class="pad">
          <table class="table" id="liveTable">
            <thead><tr><th>Time</th><th>Kind</th><th>Status</th><th class="right">Latency (ms)</th><th>Meta</th></tr></thead>
            <tbody></tbody>
          </table>
          <details class="disc" style="margin-top:10px">
            <summary>Raw JSON</summary>
            <pre class="json" id="liveJSON">{}</pre>
          </details>
        </div>
      </div>
    </section>

    <!-- APIs & Docs ------------------------------------------------------ -->
    <section id="page-apis" style="display:none">
      <h1>APIs & Docs</h1>
      <div class="grid cols-2">
        <div class="card">
          <h3>Live status</h3>
          <div class="pad">
            <div class="kv" id="statusKV"></div>
            <details class="disc" style="margin-top:10px"><summary>Raw JSON</summary><pre class="json" id="statusJSON">{}</pre></details>
          </div>
        </div>
        <div class="card">
          <h3>Metrics</h3>
          <div class="pad">
            <div class="kv" id="metricsKV"></div>
            <details class="disc" style="margin-top:10px"><summary>Raw JSON</summary><pre class="json" id="metricsJSON">{}</pre></details>
          </div>
        </div>
        <div class="card" style="grid-column:span 2">
          <h3>Ollama Models</h3>
          <div class="pad">
            <table class="table" id="modelsTable">
              <thead><tr><th>Name</th><th>Family</th><th class="right">Size</th><th>Details</th></tr></thead>
              <tbody></tbody>
            </table>
            <details class="disc" style="margin-top:10px"><summary>Raw JSON</summary><pre class="json" id="modelsJSON">{}</pre></details>
          </div>
        </div>
        <div class="card" style="grid-column:span 2">
          <h3>Docs</h3>
          <div class="pad row">
            <a href="/docs" class="pill">OpenAPI</a>
            <a href="/redoc" class="pill">ReDoc</a>
            <a href="/graphql" class="pill">GraphQL</a>
          </div>
        </div>
      </div>
    </section>
  </main>
</div>

<script>
/* ------------------------- small utils ------------------------- */
const $  = (s)=>document.querySelector(s);
const $$ = (s)=>Array.from(document.querySelectorAll(s));
const sleep=(ms)=>new Promise(r=>setTimeout(r,ms));

function fmtBytes(n){
  try{
    if(n===null||n===undefined) return "—";
    const units=["B","KB","MB","GB","TB"]; let i=0, v=Number(n);
    while(v>=1024 && i<units.length-1){ v/=1024; i++; }
    return (Math.round(v*10)/10).toLocaleString()+ " " + units[i];
  }catch(_){ return String(n) }
}
function copy(text){ navigator.clipboard?.writeText(text).catch(()=>{}); }
function humanTime(ts){
  try{ const d=new Date(ts*1000); return d.toLocaleString(); }catch(_){ return String(ts) }
}

/* JSON helpers: structured KV + raw viewer */
function renderKV(el, obj, path=[]){
  el.innerHTML="";
  const kv=document.createElement("div"); kv.className="kv";
  function row(k,v){
    const dk=document.createElement("div"); dk.className="k"; dk.textContent=path.concat([k]).join(".");
    const dv=document.createElement("div");
    dv.innerHTML = (typeof v==="object" && v!==null)
      ? `<code class="mono">${Array.isArray(v)?"[Array]":"{Object}"}</code>`
      : `<code class="mono">${String(v)}</code>`;
    kv.appendChild(dk); kv.appendChild(dv);
  }
  try{
    Object.entries(obj||{}).forEach(([k,v])=>{
      if(typeof v==="object" && v!==null){
        row(k,v);
        Object.entries(v).forEach(([k2,v2])=>row(k+"."+k2,v2));
      }else row(k,v);
    });
  }catch(_){}
  el.appendChild(kv);
}

/* ------------------------- global state ------------------------ */
let currentExpense={ kod:null, hash:null, raw:null };
let currentFiles=[];
let selected=new Map();
let nextSlot=0;

const SKEY="pruva.sessions.v2";
let sessions = JSON.parse(localStorage.getItem(SKEY) || '{"Session 1":{"messages":[],"system":""}}');
let curSession = Object.keys(sessions)[0] || "Session 1";
let pendingAttach=[]; // tokens returned by server for this message only

let memHist=[]; // for sparkline

/* ---------------------------- dashboard ------------------------ */
async function dashReload(){
  try{
    const [st, mx, md, dsSum, liveSum] = await Promise.all([
      (await fetch("/api/status")).json(),
      (await fetch("/api/metrics")).json(),
      (await fetch("/api/llm/models")).json(),
      (await fetch("/api/dataset/summary")).json(),
      (await fetch("/api/live/summary")).json(),
    ]);
    const dsList = await (await fetch("/api/dataset")).json();

    // Tiles
    $("#tileUp").textContent = mx.sys?.uptime_h || "—";
    $("#tileMem").textContent = (mx.sys?.mem!=null? mx.sys.mem+"%":"—");
    $("#tileLoad").textContent = (mx.sys?.load? mx.sys.load.map(x=>Number(x).toFixed(2)).join(" / "):"—");
    $("#tileDS").textContent = (dsSum.count!=null? dsSum.count : (dsList.items||[]).length);
    $("#tileDSz").textContent = fmtBytes(dsSum.bytes||0);
    $("#tileDisk").textContent = `${(mx.storage?.disk_free_gb||0).toLocaleString()} GB`;

    // Gateway status structured + raw
    renderKV($("#dashStatusKV"), st);
    $("#dashStatusRaw").textContent = JSON.stringify(st,null,2);

    // Metrics structured + raw
    renderKV($("#dashMetricsKV"), mx);
    $("#dashMetricsRaw").textContent = JSON.stringify(mx,null,2);

    // Models table
    const tb=$("#dashModelsTable tbody"); tb.innerHTML="";
    (md.models||[]).forEach(m=>{
      const tr=document.createElement("tr");
      tr.innerHTML = `<td>${m.name}</td><td>${m.details?.family||"—"}</td><td class="right">${fmtBytes(m.size||m.details?.size||0)}</td>
      <td><details class="disc"><summary>view</summary><pre class="json">${JSON.stringify(m.details||{},null,2)}</pre></details></td>`;
      tb.appendChild(tr);
    });
    $("#dashModelsRaw").textContent = JSON.stringify(md,null,2);

    // Recent events
    const etb=$("#dashEvents tbody"); etb.innerHTML="";
    (liveSum.last_5||[]).forEach(ev=>{
      const stn = Number(ev.status||0);
      const cls = stn>=200 && stn<300 ? "ok" : (stn>=400?"err":"warn");
      const tr=document.createElement("tr");
      tr.innerHTML = `<td class="mono">${humanTime(ev.ts||0)}</td>
                      <td><span class="chip">${ev.kind||""}</span></td>
                      <td><span class="chip ${cls}">${stn}</span></td>
                      <td class="right mono">${Number(ev.ms||0).toFixed(1)}</td>`;
      etb.appendChild(tr);
    });

    // Event summary KV
    const evKV = {
      "events.total": liveSum.total,
      "events.errors": liveSum.errors?.count,
      "events.last_error": liveSum.errors?.last_ts ? humanTime(liveSum.errors.last_ts) : "—",
      "latency.avg_ms": liveSum.latency?.overall?.avg,
      "latency.p50_ms": liveSum.latency?.overall?.p50,
      "latency.p95_ms": liveSum.latency?.overall?.p95,
      "by_kind": liveSum.by_kind,
      "by_status": liveSum.by_status,
    };
    renderKV($("#dashEventKV"), evKV);
    $("#dashEventRaw").textContent = JSON.stringify(liveSum,null,2);

    // Dataset highlights
    const dkv = {
      "count": dsSum.count, "size_bytes": dsSum.bytes,
      "unique_kods": dsSum.unique_kods, "last_ts": dsSum.last_ts ? humanTime(dsSum.last_ts) : "—",
    };
    renderKV($("#dashDatasetKV"), dkv);
    $("#dashDatasetRaw").textContent = JSON.stringify(dsSum.latest||[],null,2);

  }catch(e){
    console.error(e);
  }
}

/* ---------------------------- chat ----------------------------- */
function renderSessions(){
  const sel=$("#sessionSel"); sel.innerHTML="";
  Object.keys(sessions).forEach(name=>{
    const opt=document.createElement("option"); opt.value=name; opt.textContent=name; sel.appendChild(opt);
  });
  sel.value=curSession;
  $("#sysPrompt").value=sessions[curSession]?.system||"";
  renderChat();
}
function saveSessions(){ localStorage.setItem(SKEY, JSON.stringify(sessions)); }

function renderExtractCard(ex){
  const card=document.createElement("div"); card.className="extractCard";
  const items = Array.isArray(ex?.items)? ex.items : [];
  const safe = (v)=> v===null||v===undefined ? "<span class='muted'>null</span>" : String(v);
  card.innerHTML = `
    <div class="row" style="justify-content:space-between">
      <div class="small">Extracted fields</div>
      <div class="row">
        <button class="ghost" id="btnCopyJSON">Copy JSON</button>
        <button class="ghost" id="btnDownloadJSON">Download</button>
      </div>
    </div>
    <div class="extractGrid" style="margin-top:6px">
      <div><div class="small muted">Merchant</div><div class="mono">${safe(ex.merchant)}</div></div>
      <div><div class="small muted">Date</div><div class="mono">${safe(ex.date)}</div></div>
      <div><div class="small muted">Currency</div><div class="mono">${safe(ex.currency)}</div></div>
      <div><div class="small muted">Total</div><div class="mono">${safe(ex.total)}</div></div>
    </div>
    <div style="margin-top:8px">
      <table class="itemsTable">
        <thead><tr><th>Description</th><th>Qty</th><th>Unit</th><th>Line total</th></tr></thead>
        <tbody>
          ${items.map(it=>`<tr><td>${safe(it.description)}</td><td>${safe(it.qty)}</td><td>${safe(it.unit_price)}</td><td>${safe(it.line_total)}</td></tr>`).join("")}
        </tbody>
      </table>
    </div>
    <div class="row" style="justify-content:flex-end;margin-top:8px">
      <button class="secondary" id="btnApply">Send corrections</button>
    </div>
    <details class="disc" style="margin-top:8px"><summary>Raw JSON</summary><pre class="json">${JSON.stringify(ex,null,2)}</pre></details>
  `;
  // wire buttons
  card.querySelector("#btnCopyJSON").onclick=()=>copy(JSON.stringify(ex,null,2));
  card.querySelector("#btnDownloadJSON").onclick=()=>{
    const url = URL.createObjectURL(new Blob([JSON.stringify(ex,null,2)],{type:"application/json"}));
    const a=document.createElement("a"); a.href=url; a.download=`extraction.json`; a.click(); URL.revokeObjectURL(url);
  };
  card.querySelector("#btnApply").onclick=()=>{
    const text=`Correct the extraction to EXACTLY this JSON:\n\`\`\`json\n${JSON.stringify(ex,null,2)}\n\`\`\`\nIf any field is inconsistent with the document, explain briefly.`;
    $("#msgBox").value=text; $("#msgBox").focus();
  };
  return card;
}

function renderChat(){
  const box=$("#chatBox"); box.innerHTML="";
  const msgs=(sessions[curSession]?.messages)||[];
  msgs.forEach(m=>{
    const div=document.createElement("div"); div.className="bubble "+(m.role==="user"?"me":"ai");
    const head = (m.role==="user"?"<b>You</b>":"<b>AI</b>");
    div.innerHTML = head + (m.model?` <span class="tag mono">${m.model}</span>`:"") + "<br>" + (m.content||"").replace(/</g,"&lt;");
    // attachments
    if(m.attach && m.attach.length){
      const a=document.createElement("div"); a.style.marginTop="8px"; a.style.display="flex"; a.style.flexWrap="wrap"; a.style.gap="6px";
      m.attach.forEach(t=>{
        const span=document.createElement("span"); span.className="attach";
        const img=document.createElement("img"); img.src=`/api/llm/file/${encodeURIComponent(curSession)}/${encodeURIComponent(t.token)}`; img.alt=t.name||"file";
        const label=document.createElement("span"); label.textContent = t.name||t.token;
        span.appendChild(img); span.appendChild(label); a.appendChild(span);
      });
      div.appendChild(a);
    }
    // parsed extraction card
    if(m.extract){
      div.appendChild(renderExtractCard(m.extract));
    }
    // raw model response (if available)
    if(m.raw){
      const det=document.createElement("details"); det.className="disc"; det.style.marginTop="8px";
      det.innerHTML=`<summary>Model raw</summary><pre class="json">${JSON.stringify(m.raw,null,2)}</pre>`;
      div.appendChild(det);
      $("#lastChatRaw").textContent = JSON.stringify(m.raw,null,2);
    }
    box.appendChild(div);
  });
  box.scrollTop=box.scrollHeight;
}

function extractFirstJSONBlock(text){
  const code = text.match(/```json\s*([\s\S]*?)```/i);
  if(code){ try{ return JSON.parse(code[1]); }catch(_){ /* continue */ } }
  const i = text.indexOf("{"), j = text.lastIndexOf("}");
  if(i!==-1 && j!==-1 && j>i){ try{ return JSON.parse(text.slice(i,j+1)); }catch(_){ return null; } }
  return null;
}

async function reloadModels(){
  const js = await (await fetch("/api/llm/models")).json().catch(()=>({models:[]}));
  const sel=$("#modelSel"); sel.innerHTML="";
  if((js.models||[]).length===0){
    const opt=document.createElement("option"); opt.value=""; opt.textContent="No models"; sel.appendChild(opt);
  }else{
    (js.models||[]).forEach(m=>{
      const opt=document.createElement("option"); opt.value=m.name; opt.textContent=m.name; sel.appendChild(opt);
    });
  }
  // Also fill models table in APIs page
  const tb=$("#modelsTable tbody"); if(tb){ tb.innerHTML=""; (js.models||[]).forEach(m=>{
    const tr=document.createElement("tr");
    tr.innerHTML = `<td>${m.name}</td><td>${m.details?.family||"—"}</td><td class="right">${fmtBytes(m.size||m.details?.size||0)}</td>
    <td><details class="disc"><summary>view</summary><pre class="json">${JSON.stringify(m.details||{},null,2)}</pre></details></td>`;
    tb.appendChild(tr);
  }); }
  $("#modelsJSON").textContent = JSON.stringify(js,null,2);
}

/* --------------------------- tune/dataset ---------------------- */

function setDates(){
  const end=new Date(); const start=new Date(); start.setDate(end.getDate()-12);
  $("#start").value=start.toISOString().slice(0,10); $("#end").value=end.toISOString().slice(0,10);
}

async function jget(u){ const r=await fetch(u); if(!r.ok) throw new Error("HTTP "+r.status); return r.json(); }
async function jpost(u,body){ const r=await fetch(u,{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)}); const js=await r.json().catch(()=>({})); if(!r.ok||js.error) throw new Error(js.error||("HTTP "+r.status)); return js; }

let lastExpensesCache=[];

function renderExpenses(rowsRaw){
  const rows = Array.isArray(rowsRaw) ? rowsRaw
    : Array.isArray(rowsRaw?.rows) ? rowsRaw.rows
    : Array.isArray(rowsRaw?.data) ? rowsRaw.data
    : Array.isArray(Object.values(rowsRaw||{})) ? Object.values(rowsRaw||{}) : [];
  lastExpensesCache = rows.slice();
  const tb=$("#tblExpenses tbody"); tb.innerHTML="";
  if(rows.length===0){ tb.innerHTML="<tr><td colspan='4' class='muted'>No items</td></tr>"; $("#expCount").textContent="0"; return; }
  rows.forEach(r=>{
    const tr=document.createElement("tr");
    const kod = r.Kod ?? r.kod ?? r.id ?? r.code ?? "";
    const acik = r.Aciklama ?? r.aciklama ?? r.desc ?? "";
    const bol = r.Bolum ?? r.bolum ?? r.dept ?? "";
    const h = r.Hash ?? r.hash ?? r.h ?? "";
    tr.innerHTML=`<td class="mono">${kod}</td><td>${acik}</td><td>${bol}</td><td class="mono">${h}</td>`;
    tr.onclick=()=>openExpense(kod,h);
    tb.appendChild(tr);
  });
  $("#expCount").textContent=String(rows.length);
}

async function loadExpenses(){
  $("#tblExpenses tbody").innerHTML="<tr><td colspan='4' class='muted'>Loading…</td></tr>";
  $("#tblFiles tbody").innerHTML="<tr><td colspan='6'>No files</td></tr>";
  selected.clear(); $("#tabSelected").textContent=`Selected (0)`; $("#btnAdd").disabled=true; $("#btnSelectAll").disabled=true; $("#btnBulkOCR").disabled=true; $("#btnBulkAI").disabled=true;
  const st=$("#start").value, en=$("#end").value;
  try{
    const js=await jget(`/api/expenses?startDate=${encodeURIComponent(st)}&endDate=${encodeURIComponent(en)}`);
    renderExpenses(js);
  }catch(err){
    $("#tblExpenses tbody").innerHTML=`<tr><td colspan='4' class='muted'>Error: ${(err&&err.message)||err}</td></tr>`;
  }
}

function renderFiles(files){
  currentFiles = files || [];
  const tb=$("#tblFiles tbody"); tb.innerHTML="";
  const sum = {count: files?.length||0, total: (files||[]).reduce((a,b)=>a+(b.Size||0),0)};
  $("#filesSummary").textContent = `${sum.count} files • ${fmtBytes(sum.total)}`;
  if(!files || files.length===0){ tb.innerHTML="<tr><td colspan='6'>No files</td></tr>"; $("#btnSelectAll").disabled=true; $("#btnBulkOCR").disabled=true; $("#btnBulkAI").disabled=true; return; }
  files.forEach(f=>{
    const id=f.Kod||f.FileId||f.Id, name=f.OrjinalAdi||f.Original||"", hash=f.Hash||f.FileHash||"", typ=f.MimeType||f.FileType||"", size=f.Size||0;
    const tr=document.createElement("tr");
    const checked = selected.has(id) ? "checked" : "";
    tr.innerHTML=`<td><input type="checkbox" data-id="${id}" ${checked}></td>
      <td class="mono">${id}</td><td>${name}</td><td class="mono">${hash}</td><td class="mono">${typ}</td><td class="right">${fmtBytes(size)}</td>`;
    tr.onclick=(e)=>{
      if(e.target && e.target.tagName==="INPUT") return; // checkbox click
      nextSlot = (nextSlot%4)+1;
      $(`#pv${nextSlot}`).innerHTML=`<img src="/api/preview?kod=${encodeURIComponent(currentExpense.kod)}&fileId=${encodeURIComponent(id)}&fileHash=${encodeURIComponent(hash)}&t=${Date.now()}" alt="">`;
      $("#btnOCR").disabled=false; $("#btnAI").disabled=false;
      $("#btnOCR").onclick=async()=>{
        const r=await jpost("/api/ocr",{kod:currentExpense.kod,fileId:id,fileHash:hash});
        log(`[OCR] ${(r.text||"").slice(0,220)}${(r.text||"").length>220?"…":""}`);
      };
      $("#btnAI").onclick=async()=>{
        const r=await jpost("/api/ai/extract",{kod:currentExpense.kod,fileId:id,fileHash:hash});
        log(`[AI] ${JSON.stringify(r.fields)}`);
      };
    };
    tr.querySelector("input").onchange=(e)=>{
      if(e.target.checked){ selected.set(id, { fileId:id, fileHash:hash }); }
      else{ selected.delete(id); }
      $("#tabSelected").textContent=`Selected (${selected.size})`;
      const haveSel = selected.size>0;
      $("#btnAdd").disabled = !haveSel;
      $("#btnBulkOCR").disabled = !haveSel;
      $("#btnBulkAI").disabled = !haveSel;
    };
    tb.appendChild(tr);
  });
  $("#btnSelectAll").disabled=false;
}

async function openExpense(kod, hash){
  $("#jsonView").textContent="{}"; $("#lastExpenseRaw").textContent="{}";
  $$("#pv1,#pv2,#pv3,#pv4").forEach(el=>el.innerHTML="Select a file");
  nextSlot=0; currentExpense={kod,hash,raw:null}; selected.clear(); $("#tabSelected").textContent=`Selected (0)`; $("#btnAdd").disabled=true; $("#btnBulkOCR").disabled=true; $("#btnBulkAI").disabled=true;
  try{
    const js=await jget(`/api/expense?kod=${encodeURIComponent(kod)}&hash=${encodeURIComponent(hash)}`);
    currentExpense.raw=js.raw||js;
    $("#jsonView").textContent = JSON.stringify(js.raw||js,null,2);
    $("#lastExpenseRaw").textContent = JSON.stringify(js.raw||js,null,2);
    renderFiles(js.files||[]);
  }catch(err){
    $("#tblFiles tbody").innerHTML=`<tr><td colspan='6'>Error loading files</td></tr>`;
  }
}

function log(m){ const el=$("#activity"); if(!el) return; const line=`[${new Date().toLocaleTimeString()}] ${m}`; el.textContent+=(el.textContent?"\n":"")+line; el.scrollTop=el.scrollHeight; }

async function addSelectedToDataset(){
  if(selected.size===0) return;
  const items=[...selected.values()];
  $("#btnAdd").disabled=true;
  const concurrency=3;
  let idx=0, ok=0, fail=0;
  async function worker(){
    while(idx<items.length){
      const me=items[idx++]; const body={kod:currentExpense.kod,fileId:me.fileId,fileHash:me.fileHash,expenseHash:currentExpense.hash};
      let tries=0, done=false;
      while(!done && tries<3){
        tries++;
        try{ await jpost("/api/collect", body); log(`[collect] kod=${currentExpense.kod} fileId=${me.fileId} → saved`); ok++; done=true; }
        catch(e){ log(`[collect] fileId=${me.fileId} error: ${(e&&e.message)||e}`); if(tries>=3){ fail++; done=true; } else { await sleep(600*tries); } }
      }
      $("#bulkProg").style.width = `${Math.round(((ok+fail)/items.length)*100)}%`;
    }
  }
  await Promise.all(new Array(concurrency).fill(0).map(()=>worker()));
  log(`[collect] done ok=${ok} fail=${fail}`);
  $("#btnAdd").disabled=false; $("#bulkProg").style.width="0%";
}

async function bulkRun(kind){
  if(selected.size===0) return;
  const items=[...selected.values()];
  const concurrency=4;
  let idx=0, done=0;
  async function worker(){
    while(idx<items.length){
      const me=items[idx++]; const body={kod:currentExpense.kod,fileId:me.fileId,fileHash:me.fileHash};
      try{ await jpost(kind==="../api/ocr" ? "/api/ocr" : "/api/ai/extract", body); log(`[${kind==="../api/ocr"?"ocr":"ai"}] fileId=${me.fileId} ok`); }
      catch(e){ log(`[${kind}] fileId=${me.fileId} error: ${(e&&e.message)||e}`); }
      done++; $("#bulkProg").style.width = `${Math.round((done/items.length)*100)}%`;
    }
  }
  await Promise.all(new Array(concurrency).fill(0).map(()=>worker()));
}

function wireTabs(){
  $("#tabFiles").onclick=()=>{ $("#paneFiles").style.display="block"; $("#paneJSON").style.display="none"; };
  $("#tabJSON").onclick=()=>{ $("#paneJSON").style.display="block"; $("#paneFiles").style.display="none"; };
  $("#tabSelected").onclick=()=>{
    if(selected.size===0){ alert("No files selected."); return; }
    alert([...selected.keys()].length+" file(s) selected.");
  };
}

/* --------------------------- config ---------------------------- */
async function loadConfig(){
  const js=await (await fetch("/api/config/effective")).json();
  $("#cfgEffective").textContent=JSON.stringify(js,null,2);
  renderKV($("#cfgEffectiveKV"), js);
  const o=js.user_overrides||{};
  $("#ovOllama").value=o.OLLAMA_BASE_URL||""; $("#ovInternal").value=o.INTERNAL_API_BASE||""; $("#ovS3e").value=o.S3_ENDPOINT||""; $("#ovS3b").value=o.S3_BUCKET||""; $("#ovS3r").value=o.S3_REGION||"";
}
async function saveConfig(){
  const body={overrides:{
    OLLAMA_BASE_URL:$("#ovOllama").value.trim()||undefined,
    INTERNAL_API_BASE:$("#ovInternal").value.trim()||undefined,
    S3_ENDPOINT:$("#ovS3e").value.trim()||undefined,
    S3_BUCKET:$("#ovS3b").value.trim()||undefined,
    S3_REGION:$("#ovS3r").value.trim()||undefined
  }};
  const r=await fetch("/api/config/user",{method:"POST",headers:{ "content-type":"application/json" },body:JSON.stringify(body)});
  if(!r.ok){ alert("Save failed"); return; }
  await loadConfig(); alert("Saved. Ollama URL override applies immediately.");
}
async function clearConfig(){ await fetch("/api/config/clear",{method:"POST"}); await loadConfig(); }

/* --------------------------- live api mgmt --------------------- */
let liveCache=[];
async function reloadLive(){
  const js=await (await fetch("/api/live/events")).json();
  liveCache = js.events||[];
  $("#liveCount").textContent = liveCache.length+" events";
  $("#liveJSON").textContent = JSON.stringify(js,null,2);
  renderLiveTable();
}
function renderLiveTable(){
  const q=$("#liveFilter").value.trim();
  const tb=$("#liveTable tbody"); tb.innerHTML="";
  const parts=q? q.split(/\s+/).filter(Boolean):[];
  function match(ev){
    if(parts.length===0) return true;
    const hay = JSON.stringify(ev).toLowerCase();
    return parts.every(p=>{
      if(p.startsWith("kind:")) return (ev.kind||"").toLowerCase().includes(p.slice(5).toLowerCase());
      if(p.startsWith("status:")) return String(ev.status||"").includes(p.slice(7));
      return hay.includes(p.toLowerCase());
    });
  }
  liveCache.filter(match).forEach(ev=>{
    const tr=document.createElement("tr");
    const st=Number(ev.status||0);
    const stChip = st>=200 && st<300 ? "ok" : (st>=400?"err":"warn");
    tr.innerHTML = `<td class="mono">${humanTime(ev.ts||0)}</td>
      <td><span class="chip">${ev.kind||""}</span></td>
      <td><span class="chip ${stChip}">${st}</span></td>
      <td class="right mono">${Number(ev.ms||0).toFixed(1)}</td>
      <td><details class="disc"><summary>meta</summary><pre class="json">${JSON.stringify(ev.meta||{},null,2)}</pre></details></td>`;
    tb.appendChild(tr);
  });
}
function liveToCSV(){
  const cols=["ts","kind","status","ms","meta"];
  const rows = (liveCache||[]).map(e=>[e.ts, e.kind, e.status, e.ms, JSON.stringify(e.meta||{})]);
  const csv = [cols.join(","), ...rows.map(r=>r.map(x=>`"${String(x).replace(/"/g,'""')}"`).join(","))].join("\n");
  const url = URL.createObjectURL(new Blob([csv],{type:"text/csv"}));
  const a=document.createElement("a"); a.href=url; a.download="live_events.csv"; a.click(); URL.revokeObjectURL(url);
}

/* --------------------------- runtime wiring -------------------- */
function drawSpark(canvas, arr, maxPoints=60){
  if(!canvas) return;
  const ctx=canvas.getContext("2d");
  if(!ctx) return;
  const w=canvas.width = canvas.clientWidth;
  const h=canvas.height = canvas.clientHeight;
  ctx.clearRect(0,0,w,h);
  if(arr.length<2) return;
  const data = arr.slice(-maxPoints);
  const max = Math.max(100, ...data);
  const min = Math.min(0, ...data);
  ctx.beginPath();
  data.forEach((v,i)=>{
    const x = (i/(data.length-1))*w;
    const y = h - ((v-min)/(max-min))*h;
    if(i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  });
  ctx.strokeStyle="#2563eb"; ctx.lineWidth=2; ctx.stroke();
}

function wireStats(){
  async function tick(){
    try{
      const [st, mx, md, liveSum] = await Promise.all([
        jget("/api/status"),
        jget("/api/metrics"),
        jget("/api/llm/models"),
        jget("/api/live/summary"),
      ]);
      $("#stat-api").innerHTML=st.internal_api?.msg||"";
      $("#stat-s3").innerHTML=(st.s3?.msg||"");
      $("#stat-sys").innerHTML=`RAM ${mx.sys?.mem??"-"}%<div class="muted">${mx.sys?.uptime_h||""}</div>`;
      $("#stat-docker").textContent=mx.docker?.msg||"—";
      $("#stat-ollama").innerHTML = (md.models?.length>0)
        ? `<span class="chip ok">${md.models.length} models</span>`
        : `<span class="chip warn">no models</span>`;
      $("#stat-events").innerHTML = `${liveSum.total||0} total • p95 ${liveSum.latency?.overall?.p95??"—"} ms`;
      if($("#statusJSON")) $("#statusJSON").textContent=JSON.stringify(st,null,2), renderKV($("#statusKV"), st);
      if($("#metricsJSON")) $("#metricsJSON").textContent=JSON.stringify(mx,null,2), renderKV($("#metricsKV"), mx);
      // sparkline
      if(mx?.sys?.mem!=null){ memHist.push(Number(mx.sys.mem)||0); drawSpark($("#memSpark"), memHist); }
    }catch(_){}
    setTimeout(tick,3000);
  }
  tick();
}

function router(){
  const hash=(location.hash||"#dash").replace("#","");
  $$("#page-dash,#page-tune,#page-dataset,#page-apis,#page-chat,#page-config,#page-live").forEach(el=>el.style.display="none");
  $(`#page-${hash}`)?.style.setProperty("display","block");
  $$("#nav-dash,#nav-tune,#nav-dataset,#nav-apis,#nav-chat,#nav-config,#nav-live").forEach(a=>a.classList.remove("active"));
  $(`#nav-${hash}`)?.classList.add("active");
  if(hash==="dash") dashReload();
  if(hash==="dataset") reloadDataset();
  if(hash==="apis") reloadModels();
  if(hash==="chat"){ renderSessions(); reloadModels(); }
  if(hash==="config"){ loadConfig(); }
  if(hash==="live"){ reloadLive(); }
}

let datasetCache=[];
async function reloadDataset(){
  try{
    const js=await jget("/api/dataset");
    datasetCache = js.items||[];
    renderDataset(datasetCache);
    $("#dsCount").textContent=`${datasetCache.length} items`;
  }catch(err){
    $("#datasetGrid").innerHTML="<div class='muted'>Failed to list dataset</div>";
  }
}
function renderDataset(items){
  const grid=$("#datasetGrid"); grid.innerHTML="";
  items.forEach(it=>{
    const div=document.createElement("div"); div.className="card"; div.innerHTML=`
      <div class="pad">
        <div class="thumb"><img src="/api/dataset/image?id=${encodeURIComponent(it.id)}" alt=""></div>
        <div class="mono" style="margin-top:8px">kod=${it.kod}</div>
        <div class="mono">fileId=${it.fileId}</div>
        <div class="small muted">${it.fileHash}</div>
      </div>`;
    div.style.cursor="pointer";
    div.onclick=async()=>{
      const meta=await jget(`/api/dataset/meta?id=${encodeURIComponent(it.id)}`);
      $("#dsMeta").textContent=JSON.stringify(meta,null,2);
      // structured meta
      const kv=$("#dsMetaKV"); kv.innerHTML="";
      const core = {
        schema: meta.schema, source: meta.source, kod: meta.kod, fileId: meta.fileId, fileHash: meta.fileHash,
        content_type: meta.content_type, size_bytes: meta.size_bytes, ts: meta.ts,
        s3_key_image: meta.s3_key_image, s3_key_meta: meta.s3_key_meta
      };
      renderKV(kv, core);
      // siblings
      const sib=await jget(`/api/dataset/by-expense?kod=${encodeURIComponent(it.kod)}`);
      const sg=$("#dsSiblings"); sg.innerHTML="";
      (sib.items||[]).forEach(s=>{
        const box=document.createElement("div"); box.className="card"; box.innerHTML=`
          <div class="pad">
            <div class="thumb"><img src="/api/dataset/image?id=${encodeURIComponent(s.id)}" alt=""></div>
            <div class="mono" style="margin-top:8px">fileId=${s.fileId}</div>
          </div>`;
        sg.appendChild(box);
      });
    };
    grid.appendChild(div);
  });
}

/* filters & search */
$("#expSearch")?.addEventListener("input", e=>{
  const q=e.target.value.toLowerCase();
  const filtered = lastExpensesCache.filter(r=>{
    const kod=String(r.Kod??r.kod??r.id??"");
    const acik = String(r.Aciklama??r.aciklama??"").toLowerCase();
    const bol = String(r.Bolum??r.bolum??"").toLowerCase();
    return kod.toLowerCase().includes(q)||acik.includes(q)||bol.includes(q);
  });
  const tb=$("#tblExpenses tbody"); tb.innerHTML="";
  filtered.forEach(r=>{
    const tr=document.createElement("tr");
    const kod = r.Kod ?? r.kod ?? r.id ?? r.code ?? "";
    const acik = r.Aciklama ?? r.aciklama ?? r.desc ?? "";
    const bol = r.Bolum ?? r.bolum ?? r.dept ?? "";
    const h = r.Hash ?? r.hash ?? r.h ?? "";
    tr.innerHTML=`<td class="mono">${kod}</td><td>${acik}</td><td>${bol}</td><td class="mono">${h}</td>`;
    tr.onclick=()=>openExpense(kod,h);
    tb.appendChild(tr);
  });
  $("#expCount").textContent=String(filtered.length);
});
$("#dsSearch")?.addEventListener("input", e=>{
  const q=e.target.value.toLowerCase();
  const filtered = datasetCache.filter(it=> String(it.kod).includes(q) || String(it.fileId).includes(q) || String(it.fileHash).toLowerCase().includes(q));
  renderDataset(filtered);
});
$("#liveFilter")?.addEventListener("input", ()=>renderLiveTable());

document.addEventListener("DOMContentLoaded",()=>{
  setDates(); wireStats(); wireTabs(); router();
  window.addEventListener("hashchange",router);

  // dashboard
  $("#dashReload")?.addEventListener("click", dashReload);

  // tune actions
  $("#btnLoad").onclick=loadExpenses;
  $("#btnSelectAll").onclick=()=>{ $$("#tblFiles tbody input[type=checkbox]").forEach(cb=>{ if(!cb.checked){ cb.checked=true; cb.dispatchEvent(new Event("change")); } }); };
  $("#btnAdd").onclick=addSelectedToDataset;
  $("#btnBulkOCR").onclick=()=>bulkRun("../api/ocr");
  $("#btnBulkAI").onclick=()=>bulkRun("../api/ai");

  // chat wiring
  $("#btnSend").onclick=sendChat;
  $("#btnReloadModels").onclick=reloadModels;
  $("#btnExport").onclick=()=>{
    const data = JSON.stringify(sessions[curSession],null,2);
    const url = URL.createObjectURL(new Blob([data],{type:"application/json"}));
    const a=document.createElement("a"); a.href=url; a.download=`${curSession}.json`; a.click(); URL.revokeObjectURL(url);
  };
  $("#btnNew").onclick=()=>{ let n="Session "+(Object.keys(sessions).length+1); sessions[n]={messages:[],system:""}; curSession=n; saveSessions(); renderSessions(); };
  $("#btnDelete").onclick=()=>{ if(confirm("Delete session?")){ delete sessions[curSession]; curSession=Object.keys(sessions)[0]||"Session 1"; if(!sessions[curSession]) sessions[curSession]={messages:[],system:""}; saveSessions(); renderSessions(); }};
  $("#sessionSel").onchange=(e)=>{ curSession=e.target.value; renderChat(); };
  $("#sysPrompt").onchange=(e)=>{ sessions[curSession].system=e.target.value; saveSessions(); };

  // dataset
  $("#btnReloadDataset")?.addEventListener("click",reloadDataset);

  // config
  $("#btnCfgSave")?.addEventListener("click", saveConfig);
  $("#btnCfgClear")?.addEventListener("click", clearConfig);

  // live api mgmt
  $("#btnLiveRefresh")?.addEventListener("click", reloadLive);
  $("#btnLiveClear")?.addEventListener("click", async()=>{ await fetch("/api/live/clear",{method:"POST"}); reloadLive(); });
  $("#btnLiveCSV")?.addEventListener("click", liveToCSV);

  // file upload previews
  $("#filePick").addEventListener("change",()=>uploadFiles());
});
</script>
</body></html>
    """

# --------------------------------------------------------------------------- #
# API used by the UI (status, metrics, dataset, expense, preview, ocr, ai)
# + Config (effective/user overrides)
# + Live API Mgmt (events list & summary) + Overview helpers
# --------------------------------------------------------------------------- #

class CollectIn(BaseModel):
    kod: int
    fileId: int
    fileHash: str
    expenseHash: Optional[str] = None
    convert_to: str = "png"

class FileRef(BaseModel):
    kod: int
    fileId: int
    fileHash: str

@router.get("/favicon.ico")
def favicon():
    return Response(status_code=204)

# ---------------------------- Status/Metrics ------------------------------- #

@router.get("/api/status")
def status(s3: S3Store = Depends(get_s3_store)) -> Dict[str, Any]:
    t0 = time.time()
    out: Dict[str, Any] = {
        "internal_api": {"ok": True, "msg": "client ready"},
        "s3": {"ok": True, "msg": ""},
    }
    try:
        root = _dataset_root(s3)
        out["s3"]["msg"] = f"local: {root}"
    finally:
        _record_api_event("status", 200, (time.time()-t0)*1000)
    return out

@router.get("/api/metrics")
def metrics(s3: S3Store = Depends(get_s3_store)) -> Dict[str, Any]:
    t0 = time.time()
    started = float(os.environ.get("PRUVA_START_TS", _now_ts()))
    uptime_s = max(0.0, _now_ts() - started)
    try:
        load1, load5, load15 = os.getloadavg()
    except Exception:
        load1 = load5 = load15 = 0.0

    mem_pct = None
    try:
        if os.path.exists("/proc/meminfo"):
            mi: Dict[str, str] = {}
            with open("/proc/meminfo", "r") as f:
                for ln in f:
                    k, _, v = ln.partition(":")
                    mi[k.strip()] = v.strip()
            total = float(mi.get("MemTotal", "0 kB").split()[0])
            avail = float(mi.get("MemAvailable", "0 kB").split()[0])
            if total > 0:
                mem_pct = round((1 - (avail / total)) * 100, 1)
    except Exception:
        mem_pct = None

    disk = shutil.disk_usage("/")
    storage = {
        "bucket": getattr(s3, "bucket", None),
        "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
        "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
    }
    _record_api_event("metrics", 200, (time.time()-t0)*1000)
    return {
        "sys": {"uptime_h": f"{uptime_s/3600:.1f} h", "cpu": None, "mem": mem_pct, "load": [load1, load5, load15]},
        "storage": storage,
        "docker": {"msg": "not enabled in gateway (placeholder)"},
    }

# ---------------------------- Expenses -------------------------------------- #

def _extract_files_from_detail(detail: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw = detail.get("data") or {}
    masraf_alt = raw.get("MasrafAlt") or {}
    files: List[Dict[str, Any]] = []
    for _, alt in (masraf_alt or {}).items():
        ds = alt.get("Dosya") or alt.get("Files") or {}
        if isinstance(ds, dict):
            for _, dv in ds.items():
                if isinstance(dv, dict):
                    files.append(
                        {
                            "Kod": dv.get("Kod") or dv.get("FileId") or dv.get("Id"),
                            "OrjinalAdi": dv.get("OrjinalAdi") or dv.get("Adi"),
                            "Hash": dv.get("Hash") or dv.get("FileHash"),
                            "MimeType": dv.get("MimeType") or dv.get("FileType"),
                            "Size": dv.get("Size") or dv.get("FileSize") or 0,
                        }
                    )
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for f in files:
        k = str(f.get("Kod"))
        if not k or not f.get("Hash"):
            continue
        if k in seen:
            continue
        seen.add(k)
        uniq.append(f)
    return uniq, raw

@router.get("/api/expenses")
def list_expenses(
    startDate: str,
    endDate: str,
    client: InternalAPIClient = Depends(get_internal_client),
):
    t0 = time.time()
    try:
        data = client.list_expenses(startDate, endDate)
        return data
    finally:
        _record_api_event("internal:list_expenses", 200, (time.time()-t0)*1000, {"start": startDate, "end": endDate})

@router.get("/api/expense")
def expense(
    kod: int,
    hash: str,
    client: InternalAPIClient = Depends(get_internal_client),
):
    t0 = time.time()
    try:
        detail: Dict[str, Any] = client.expense_json(kod=kod, hash=hash)
        files, _ = _extract_files_from_detail(detail)
        masraf = (detail.get("data") or {}).get("masraf") or {}
        return {"masraf": masraf, "files": files, "raw": detail}
    finally:
        _record_api_event("internal:expense", 200, (time.time()-t0)*1000, {"kod": kod})

@router.get("/api/preview")
def preview(
    kod: int,
    fileId: int,
    fileHash: str,
    client: InternalAPIClient = Depends(get_internal_client),
):
    t0 = time.time()
    try:
        b64 = client.expense_file_base64(kod=kod, file_id=fileId, file_hash=fileHash)
        raw = base64.b64decode(b64, validate=False)
        im = Image.open(io.BytesIO(raw))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        _record_api_event("internal:preview", 200, (time.time()-t0)*1000, {"kod": kod, "fileId": fileId})
        return Response(content=buf.getvalue(), media_type="image/png")
    except InternalAPIError as e:
        _record_api_event("internal:preview", 400, (time.time()-t0)*1000, {"err": str(e)})
        return Response(content=f"preview error: {e}".encode(), status_code=400, media_type="text/plain")
    except Exception as e:
        _record_api_event("internal:preview", 400, (time.time()-t0)*1000, {"err": str(e)})
        return Response(content=f"decode error: {e}".encode(), status_code=400, media_type="text/plain")

def _scan_bytes_compat(av: AVScanner, raw: bytes) -> bool:
    try:
        return bool(av.scan_bytes(raw))
    except (TypeError, AttributeError):
        try:
            return bool(av.scan_bytes(io.BytesIO(raw)))
        except Exception:
            return False
    except Exception:
        return False

# ------------------------ LOCAL SAVE (no S3 creds needed) ------------------- #

def _local_dataset_paths(s3: S3Store, kod: int, fileId: int, fileHash: str) -> Dict[str, pathlib.Path]:
    root = _dataset_root(s3) / "dataset" / f"kod_{kod}" / f"file_{fileId}_{fileHash}"
    root.mkdir(parents=True, exist_ok=True)
    return {"root": root, "image": root / "image.png", "meta": root / "meta.json"}

@router.post("/api/collect")
def collect(
    body: CollectIn = Body(...),
    client: InternalAPIClient = Depends(get_internal_client),
    s3: S3Store = Depends(get_s3_store),
    av: AVScanner = Depends(get_av),
):
    t0 = time.time()
    # retry the download a couple of times
    last_err=None
    for _ in range(3):
        try:
            b64 = client.expense_file_base64(kod=body.kod, file_id=body.fileId, file_hash=body.fileHash)
            break
        except Exception as e:
            last_err=e
            time.sleep(0.6)
    else:
        _record_api_event("collect", 400, (time.time()-t0)*1000, {"err": str(last_err)})
        return JSONResponse({"error": f"download failed: {last_err}"}, status_code=400)

    try:
        raw_bytes = base64.b64decode(b64, validate=False)
    except Exception as e:
        _record_api_event("collect", 400, (time.time()-t0)*1000, {"err": "decode"})
        return JSONResponse({"error": f"base64 decode failed: {e}"}, status_code=400)

    try:
        if _scan_bytes_compat(av, raw_bytes):
            _record_api_event("collect", 400, (time.time()-t0)*1000, {"err": "av"})
            return JSONResponse({"error": "AV scan failed: file infected"}, status_code=400)
    except Exception:
        pass

    try:
        im = Image.open(io.BytesIO(raw_bytes))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        png_bytes = buf.getvalue()
    except Exception as e:
        _record_api_event("collect", 400, (time.time()-t0)*1000, {"err": "image"})
        return JSONResponse({"error": f"image convert failed: {e}"}, status_code=400)

    internal_detail: Dict[str, Any] = {}
    if body.expenseHash:
        try:
            internal_detail = client.expense_json(kod=body.kod, hash=body.expenseHash)
        except Exception:
            internal_detail = {}

    paths = _local_dataset_paths(s3, body.kod, body.fileId, body.fileHash)
    try:
        paths["image"].write_bytes(png_bytes)
    except Exception as e:
        _record_api_event("collect", 500, (time.time()-t0)*1000, {"err": "store_image"})
        return JSONResponse({"error": f"store image failed: {e}"}, status_code=500)

    meta = {
        "schema": "pruva.dataset.v1",
        "source": "internal_api",
        "kod": body.kod,
        "fileId": body.fileId,
        "fileHash": body.fileHash,
        "content_type": "image/png",
        "size_bytes": len(png_bytes),
        "s3_key_image": f"dataset/kod_{body.kod}/file_{body.fileId}_{body.fileHash}/image.png",
        "s3_key_meta":  f"dataset/kod_{body.kod}/file_{body.fileId}_{body.fileHash}/meta.json",
        "internal_detail": internal_detail.get("data", internal_detail),
        "ts": int(_now_ts()),
    }
    try:
        paths["meta"].write_text(_safe_json(meta), encoding="utf-8")
    except Exception as e:
        _record_api_event("collect", 500, (time.time()-t0)*1000, {"err": "store_meta"})
        return JSONResponse({"error": f"store meta failed: {e}"}, status_code=500)

    _record_api_event("collect", 200, (time.time()-t0)*1000, {"kod": body.kod, "fileId": body.fileId})
    return {
        "ok": True,
        "s3_key_image": meta["s3_key_image"],
        "s3_key_meta": meta["s3_key_meta"],
        "path_image": str(paths["image"]),
        "path_meta": str(paths["meta"]),
    }

# ------------------------------ Dataset ------------------------------------- #

@router.get("/api/dataset")
def dataset_list(s3: S3Store = Depends(get_s3_store)) -> Dict[str, Any]:
    root = _dataset_root(s3) / "dataset"
    t0 = time.time()
    items = _scan_items_under(root)
    _record_api_event("dataset:list", 200, (time.time()-t0)*1000, {"count": len(items)})
    return {"items": items}

@router.get("/api/dataset/by-expense")
def dataset_by_expense(kod: int, s3: S3Store = Depends(get_s3_store)) -> Dict[str, Any]:
    return {"items": _scan_items_under(_dataset_root(s3) / "dataset" / f"kod_{kod}")}

@router.get("/api/dataset/image")
def dataset_image(id: str, s3: S3Store = Depends(get_s3_store)):
    root = _dataset_root(s3) / "dataset"
    rel = pathlib.Path(_b64url_dec(id))
    img_path = (root / rel / "image.png").resolve()
    if not img_path.is_file() or root not in img_path.parents:
        return Response(status_code=404)
    return Response(content=img_path.read_bytes(), media_type="image/png")

@router.get("/api/dataset/meta")
def dataset_meta(id: str, s3: S3Store = Depends(get_s3_store)):
    root = _dataset_root(s3) / "dataset"
    rel = pathlib.Path(_b64url_dec(id))
    meta_path = (root / rel / "meta.json").resolve()
    if not meta_path.is_file() or root not in meta_path.parents:
        return JSONResponse({"error": "not found"}, status_code=404)
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return JSONResponse({"error": "meta parse error"}, status_code=400)

@router.get("/api/dataset/summary")
def dataset_summary(s3: S3Store = Depends(get_s3_store)):
    t0 = time.time()
    out = _dataset_summary(s3)
    _record_api_event("dataset:summary", 200, (time.time()-t0)*1000, {"count": out.get("count", 0)})
    return out

# ------------------------------ OCR / AI stub ------------------------------- #

@router.post("/api/ocr")
def ocr_endpoint(body: FileRef, client: InternalAPIClient = Depends(get_internal_client)):
    t0 = time.time()
    try:
        b64 = client.expense_file_base64(kod=body.kod, file_id=body.fileId, file_hash=body.fileHash)
        raw = base64.b64decode(b64, validate=False)
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        out = io.BytesIO()
        im.save(out, format="PNG")
        png_b64 = base64.b64encode(out.getvalue()).decode("ascii")
    except Exception as e:
        _record_api_event("ocr", 400, (time.time()-t0)*1000, {"err": str(e)})
        return JSONResponse({"error": f"OCR input error: {e}"}, status_code=400)

    text = ""
    try:
        import pytesseract  # type: ignore
        text = pytesseract.image_to_string(im) or ""
    except Exception:
        text = ""

    _record_api_event("ocr", 200, (time.time()-t0)*1000)
    return {"ok": True, "text": text, "note": "If empty, install tesseract/pytesseract.", "image_png_base64": png_b64[:200] + "..."}

@router.post("/api/ai/extract")
def ai_extract_endpoint(body: FileRef):
    # Hook in a real vision model here if desired; UI/flow are ready.
    return {
        "ok": True,
        "model": "stub",
        "fields": {"merchant": None, "date": None, "total": None, "currency": None, "items": []},
        "note": "Wire your vision-LLM here; endpoint + UI are ready.",
    }

# --------------------------------------------------------------------------- #
# LLM (Ollama) — models, uploads, chat (English enforced by caller)
# --------------------------------------------------------------------------- #

class ChatMsg(BaseModel):
    role: str
    content: str = ""
    image_tokens: Optional[List[str]] = None

class ChatIn(BaseModel):
    session_id: str
    model: str
    system: Optional[str] = None
    messages: List[ChatMsg]

@router.get("/api/llm/models")
def llm_models() -> Dict[str, Any]:
    url = _get_ollama_base_url()
    js = _http_json("GET", f"{url}/api/tags")
    models = []
    for m in (js.get("models") or []):
        models.append({"name": m.get("name"), "details": m.get("details", {}), "size": m.get("size")})
    if not models:
        return {
            "ok": True,
            "note": "No models from Ollama. Example commands:",
            "commands": ["ollama pull llama3:8b", "ollama pull qwen2.5:7b-instruct", "ollama list"],
            "raw": {"ok": True, "models": [], "raw": js},
        }
    return {"ok": True, "models": models, "raw": js}

@router.post("/api/llm/upload")
def llm_upload(session_id: str = Form(...), files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    updir = _upload_dir(session_id)
    out = []
    for uf in files:
        token = f"{int(_now_ts())}-{secrets.token_hex(6)}-{uf.filename}"
        path = updir / token
        with path.open("wb") as w:
            shutil.copyfileobj(uf.file, w)
        out.append({"token": token, "name": uf.filename, "mime": uf.content_type})
    return {"ok": True, "files": out}

@router.get("/api/llm/file/{session_id}/{token}")
def llm_file(session_id: str, token: str):
    path = (_upload_dir(session_id) / token).resolve()
    root = _upload_dir(session_id).resolve()
    if not path.is_file() or root not in path.parents:
        return Response(status_code=404)
    return Response(content=path.read_bytes(), media_type=_guess_mime(path))

# @router.post("/api/llm/chat")
# def llm_chat(inp: ChatIn):
#     url = _get_ollama_base_url()
#     payload_messages: List[Dict[str, Any]] = []
#     if inp.system:
#         payload_messages.append({"role": "system", "content": inp.system})

#     for m in inp.messages:
#         msg: Dict[str, Any] = {"role": m.role, "content": m.content or ""}
#         imgs: List[str] = []
#         for tok in (m.image_tokens or []):
#             p = (_upload_dir(inp.session_id) / tok).resolve()
#             if p.is_file():
#                 try:
#                     imgs.append(base64.b64encode(p.read_bytes()).decode("ascii"))
#                 except Exception:
#                     pass
#         if imgs:
#             msg["images"] = imgs
#         payload_messages.append(msg)

#     body = {"model": inp.model, "messages": payload_messages, "stream": False}
#     out = _http_json("POST", f"{url}/api/chat", body, timeout=120.0)
#     if out.get("error"):
#         return JSONResponse({"error": out.get("error"), "raw": out}, status_code=int(out.get("status", 500)))

#     reply = ((out.get("message") or {}).get("content")) or ""
#     return {"ok": True, "reply": reply, "raw": out}

# ---- System Prompt (verbatim) ----
SYSTEM_PROMPT = r"""System Prompt — Pruva AI (Invoice/Receipt Extraction)

You are an expert document extraction agent for Pruva AI.
Your job is to read expense receipts/invoices (images and PDFs) and return a precise JSON object with the required fields. The UI may first load a list of expenses and then fetch the actual files (images/PDFs) for each expense; you will receive those files as chat/image context. Extract only what is visible on the documents. If a field is not present, return null (do not guess).

Documents you’ll see

Single-photo receipts, multi-photo receipts, or PDFs (multi-page).

Languages may include Turkish and English. Numeric formats may use comma decimals (e.g., 123,45).

If totals appear multiple times, prefer the one labeled TOPLAM / GENEL TOPLAM / TOTAL. For VAT: KDV.

Output format (return JSON only)

Return a single JSON object with three sections using these exact keys and field names:
{
"Masraf": {
"Kod": null,
"BaslangicTarihi": null,
"BitisTarihi": null,
"Aciklama": null,
"Bolum": null,
"Hash": null
},
"MasrafAlt": [
{
"Kod": null,
"MasrafTarihi": null,
"MasrafTuru": null,
"Butce": null,
"Tedarikci": null,
"Miktar": null,
"Birim": null,
"BirimMasrafTutari": null,
"KDVOrani": null,
"ToplamMasrafTutari": null,
"Aciklama": null
}
],
"Dosya": [
{
"Kod": null,
"Adi": null,
"OrjinalAdi": null,
"Hash": null,
"MimeType": null,
"Size": null,
"Md5": null,
"EklenmeTarihi": null
}
]
}Field guidance

Masraf (Header)

BaslangicTarihi, BitisTarihi: If the document shows a date range, fill both. Else use the main document date for BaslangicTarihi and set BitisTarihi to the same value. Date format: YYYY-MM-DD.

Bolum: Department or cost center if printed; else null.

Aciklama: A short human-readable summary (e.g., vendor + store/city + doc number). Keep under 120 chars.

MasrafAlt (Line Items)

Extract item rows if present (e.g., product lines). If the receipt has no clear rows, make one item summarizing the receipt.

MasrafTarihi: Document date (YYYY-MM-DD).

MasrafTuru: Category if explicit (e.g., “Yemek”, “Konaklama”, “Akaryakıt”). If not labeled, infer conservatively from vendor context; else null.

Tedarikci: Vendor name as printed (normalize extra whitespace).

Miktar + Birim: Quantity & unit if shown (e.g., 1, adet; or 35.20, lt). If missing, use null.

BirimMasrafTutari: Unit price when available; numeric.

KDVOrani: VAT rate as a percent number (e.g., 10, 20). If the document lists multiple rates, pick the dominant one or null if unclear.

ToplamMasrafTutari: The grand total including VAT; numeric.

Dosya (Files)

If the runtime provides file names/ids, copy them here. Otherwise set fields to null. Do not invent file hashes or sizes.

Normalization rules

Numbers: Return as numbers (not strings). Convert 1.234,56 → 1234.56.

Currency: Assume TRY unless the document explicitly shows another currency symbol or code; do not add a currency symbol—just numeric values.

Dates: Output in YYYY-MM-DD. Recognize common formats: dd.mm.yyyy, dd/mm/yyyy, yyyy-mm-dd, etc.

Unknowns: Use null when a value isn’t visible.

No hallucinations: Never infer invoice numbers, file hashes, or departments unless clearly printed.

Multi-page/multi-file docs

Read all provided pages/files as one expense unless obviously separate.

If items continue across pages, merge into a single MasrafAlt array.

If multiple receipts clearly belong to different expenses, still return one JSON covering the files you were given—group content logically into items and reflect a single header.

Quality checklist (before you return)

JSON is valid and matches the schema above.

Dates ISO-formatted; decimals use a dot.

Grand total (ToplamMasrafTutari) matches the document total.

No extra keys; only the fields listed.

Example (illustrative)
{
"Masraf": {
"Kod": null,
"BaslangicTarihi": "2025-10-09",
"BitisTarihi": "2025-10-09",
"Aciklama": "RAMADA ISTANBUL – Fatura 456781",
"Bolum": null,
"Hash": null
},
"MasrafAlt": [
{
"Kod": null,
"MasrafTarihi": "2025-10-09",
"MasrafTuru": "Konaklama",
"Butce": null,
"Tedarikci": "RAMADA",
"Miktar": 1,
"Birim": "gece",
"BirimMasrafTutari": 2150.00,
"KDVOrani": 10,
"ToplamMasrafTutari": 2365.00,
"Aciklama": "Oda + vergi"
}
],
"Dosya": [
{
"Kod": null,
"Adi": null,
"OrjinalAdi": "RAMADA.pdf",
"Hash": null,
"MimeType": "application/pdf",
"Size": null,
"Md5": null,
"EklenmeTarihi": null
}
]
}
"""

# ---- Updated route (injects the system prompt before user/system) ----
@router.post("/api/llm/chat")
def llm_chat(inp: ChatIn):
    url = _get_ollama_base_url()

    # Always start with our official system prompt
    payload_messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    # If caller provided an extra system string, append it AFTER the official one
    if inp.system and inp.system.strip():
        payload_messages.append({"role": "system", "content": inp.system.strip()})

    # Rest of the pipeline unchanged: include messages and inline images
    for m in inp.messages:
        msg: Dict[str, Any] = {"role": m.role, "content": m.content or ""}
        imgs: List[str] = []
        for tok in (m.image_tokens or []):
            p = (_upload_dir(inp.session_id) / tok).resolve()
            if p.is_file():
                try:
                    imgs.append(base64.b64encode(p.read_bytes()).decode("ascii"))
                except Exception:
                    pass
        if imgs:
            msg["images"] = imgs
        payload_messages.append(msg)

    body = {"model": inp.model, "messages": payload_messages, "stream": False}
    out = _http_json("POST", f"{url}/api/chat", body, timeout=120.0)
    if out.get("error"):
        return JSONResponse({"error": out.get("error"), "raw": out}, status_code=int(out.get("status", 500)))

    reply = ((out.get("message") or {}).get("content")) or ""
    return {"ok": True, "reply": reply, "raw": out}

# --------------------------------------------------------------------------- #
# Config API: show effective (env + overrides) and modify overrides
# --------------------------------------------------------------------------- #

class UserOverrides(BaseModel):
    overrides: Dict[str, Any] = {}

@router.get("/api/config/effective")
def config_effective():
    return _get_effective_config()

@router.post("/api/config/user")
def config_user_save(payload: UserOverrides):
    cfg = {"overrides": {k: v for k, v in (payload.overrides or {}).items() if v}}
    _save_user_config(cfg)
    return {"ok": True, "saved": cfg}

@router.post("/api/config/clear")
def config_clear():
    try:
        _config_path().unlink(missing_ok=True)  # py3.8+: set False if not supported
    except TypeError:
        if _config_path().exists():
            _config_path().unlink()
    return {"ok": True}

# --------------------------------------------------------------------------- #
# Live API Mgmt (events) — list & summarized views
# --------------------------------------------------------------------------- #

@router.get("/api/live/events")
def live_events():
    return {"events": list(API_EVENTS)}

@router.post("/api/live/clear")
def live_clear():
    API_EVENTS.clear()
    return {"ok": True}

@router.get("/api/live/summary")
def live_summary():
    t0 = time.time()
    out = _live_summary()
    _record_api_event("live:summary", 200, (time.time()-t0)*1000, {"total": out.get("total", 0)})
    return out
