Pruva Invoice Extraction – README.md

End-to-end, containerized pipeline for fetching client expenses from your internal API, ingesting files (PDF / IMG / MSG), extracting structured data, creating comparison & progress reports, and reviewing everything in a built-in web UI.
Includes parallel LLM and DocAI execution (vLLM/OpenAI-style chat + local OCR/PDF text + HF Document AI), with artifactized runs in MinIO.
0) TL;DR – Quick Start
# Prereqs
# - Docker Desktop 4.25+ (Linux/macOS/Windows)
# - ~8 GB free RAM
# - (Optional) An OpenAI-compatible LLM endpoint (vLLM, OpenAI, Groq, Ollama-openai)

# 1) Boot the stack
docker compose up --build -d

# 2) Create S3 bucket (one-time)
docker exec -it minio mc alias set local http://minio:9000 minioadmin minioadmin
docker exec -it minio mc mb --ignore-existing local/pruva-files

# 3) Open the app (Gateway + UI)
# macOS:
open http://localhost:8080
# Linux:
xdg-open http://localhost:8080
1) What’s in this repo

Core modules the app already ships with (as uploaded):
apps/
  gateway/
    main.py                # FastAPI app factory, uvicorn, middleware
    ui.py                  # Lightweight UI views/handlers
    pipeline_router.py     # REST surface for pipeline control

packages/
  security/
    ip_allowlist.py        # IP allowlist middleware (can disable)
    jwt_dep.py             # JWT dependency for FastAPI routes
    signer.py              # JWT mint helper for local/dev
  pipeline/
    client.py              # Internal ERP/API client
    provider.py            # High-level facade for fetching clients/expenses
    router_unified.py      # Pipeline routes (mounted by gateway)
    worker_unified.py      # Orchestrates background work (async/threads)
    engine.py              # Extraction engine orchestration
    models.py              # Pydantic models (DTOs)
    schema.py              # Pydantic schemas
    schemas.py             # (same family) schema variants
    events_bus.py          # In-process pub/sub for progress + logs
  ai/
    ai_chat.py             # LLM helpers (OpenAI/vLLM/Ollama-compatible)

infra/
  docker-compose.yml       # Services: gateway, extractor (if split), minio, clamav, redis
Dockerfile
Makefile
Services (docker-compose):

gateway: FastAPI app exposing REST + the UI; mounts extraction endpoints and orchestrates runs.

clamav: Virus scanning of uploaded/fetched files.

minio: S3 object storage for raw files, normalized JSON, reports & artifacts.

redis: Cache + queue/state.

extractor (optional): If split from gateway; in this repo the worker logic is unified and callable in-proc.

Ports: gateway:8080, minio:9000 (API) / 9001 (Console), clamav:3310, redis:6379

2) Architecture
┌─────────── UI (Browser) ───────────┐
│                                    │
│  Clients ▸ Expenses ▸ Run pipeline │
│         ▸ Reports ▸ Artifacts      │
└───────────────┬────────────────────┘
                │ HTTP (JWT)
        ┌───────▼───────────────────────────────────────────┐
        │                    GATEWAY                        │
        │       FastAPI + uvicorn + middleware              │
        │  - Auth (JWT)           - Optional IP Allowlist   │
        │  - File routing         - Progress endpoints      │
        │  - REST API             - Static reports          │
        └───┬───────────────┬───────────────┬──────────────┘
            │               │               │
            │               │               │
     ┌──────▼─────┐   ┌─────▼─────┐   ┌────▼─────┐
     │  Redis     │   │  ClamAV    │   │  MinIO   │
     │ cache/q    │   │ scan files │   │  S3      │
     └────┬───────┘   └────┬───────┘   └────┬─────┘
          │                │                │
          │    ┌───────────▼───────────┐    │
          └────►   PIPELINE ENGINE     ◄────┘
               │ (engine/worker/router)│
               │  - ingest             │
               │  - parse/ocr/pdftext  │
               │  - parallel LLM/DocAI │
               │  - normalize to JSON  │
               │  - compare & report   │
               └────────────────────────┘
3) Functional Flow (End-to-End)

Select client → GET /api/clients (via provider.Client.list_clients() / client.py).

Select expense → GET /api/clients/{client_id}/expenses to pick expenseKod.

Run pipeline → POST /api/pipeline/run with {client_id, expenseKod, options}.

Ingestion (per expense item):

Fetch description and attachments via internal API.

Scan with ClamAV; store /raw/ in MinIO.

Extraction:

Plan pages/parts → parallel:

PDF→Text (extract literal text & layout)

PDF→IMG (page images for OCR/DocAI)

IMG→OCR

MSG→body + embedded attachments (then recurse)

Build contexts (semantic chunks) for LLM.

Fire parallel LLMs:

Chat-completion model (vLLM/OpenAI-style) for schema filling + reasoning.

DocAI models (HF pipelines like Donut/LayoutLMv3/LayoutParser) for field detection.

Merge results with heuristics and rule checks.

Normalize → write normalized/{client}/{expenseKod}/{expense_item_id}.json.

Compare & Report:

Compare against ERP values / baseline runs.

Generate HTML comparison + progress reports → reports/{client}/{expenseKod}/{run_id}/index.html.

UI review:

View status, diffs, failures; download artifacts.

4) API Surface (Gateway)

(Mounted from router_unified.py / pipeline_router.py; your UI already uses these.)

Health/meta

GET /api/status

GET /api/metrics

GET /api/live/summary

GET /api/llm/models (exposes configured LLM backends)

Discovery

GET /api/clients

GET /api/clients/{client_id}/expenses

Pipeline control

POST /api/pipeline/run
{
  "client_id": "ACME",
  "expenseKod": "TRVL-2025-10",
  "options": {
    "rebuild": false,
    "skip_scan": false,
    "llm_preset": "default",
    "concurrency": 4
  }
}
GET /api/pipeline/runs/{run_id}

Reports

GET /api/reports/{client_id}/{expenseKod}/latest

GET /api/reports/{client_id}/{expenseKod}/{run_id}
5) Security
JWT

Env (dev defaults):

IP Allowlist

Local/dev: disabled by default. If needed:

IP_MODE=off | private | explicit

IP_ALLOWLIST=10.0.0.0/8,192.168.0.0/16,...

IP_TRUST_XFF=0|1

If you previously saw 403: IP not allowed, ensure IP_MODE=off for dev.