# apps/gateway/main.py
from __future__ import annotations

import os
import shutil
import time
from typing import Dict, List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse, PlainTextResponse

# Routers
from apps.gateway.router_unified import router as unified_router          # /api/requests* + SSE
from apps.gateway.ui import router as ui_router                           # /ui + dataset/preview/collect/etc
from apps.gateway.pipeline_router import router as pipeline_router        # /api/llm/*
from apps.gateway.ai_chat import router as chat_router                    # /api/chat/*
from apps.gateway.schema import graphql_router                            # /graphql (strawberry.fastapi)

# Security
from packages.security.ip_allowlist import IPAllowlistMiddleware

# simple in-memory request log for live API view
_LOG_RING: List[str] = []


def _log(line: str):
    _LOG_RING.append(line)
    if len(_LOG_RING) > 500:
        del _LOG_RING[: len(_LOG_RING) - 500]


def create_app() -> FastAPI:
    # ---- env/config FIRST (so we can use them in app metadata/routes) ----
    PRUVA_GATEWAY_VERSION = os.environ.get("PRUVA_GATEWAY_VERSION", "dev")
    PRUVA_START_TS = float(os.environ.get("PRUVA_START_TS", str(time.time())))
    ALLOW_STR = os.getenv("ALLOWED_IPS", "")
    allowed_env = [x.strip() for x in ALLOW_STR.split(",") if x.strip()]

    # ---- app ----
    app = FastAPI(title="Pruva Gateway", version=PRUVA_GATEWAY_VERSION)

    # IP allow-list (localhost always allowed by the middleware implementation)
    # If you prefer to always enable it even when env is empty (localhost-only), leave as-is:
    # app.add_middleware(IPAllowlistMiddleware, allowlist=allowed_env)

    # CORS for web clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # tiny middleware to record logs for Live API page
    @app.middleware("http")
    async def _mw_log(request: Request, call_next):
        t0 = time.time()
        resp = await call_next(request)
        dt = (time.time() - t0) * 1000
        _log(f"{request.method} {request.url.path} {resp.status_code} {dt:.1f}ms")
        return resp

    # Root → UI
    @app.get("/", include_in_schema=False)
    def _root():
        return RedirectResponse("/ui")

    # Health
    @app.get("/api/status")
    def status() -> Dict[str, str | bool]:
        return {"ok": True, "service": "gateway", "version": PRUVA_GATEWAY_VERSION}

    # Minimal metrics (system + disk)
    @app.get("/api/metrics")
    def metrics() -> Dict[str, object]:
        started = PRUVA_START_TS
        uptime_s = max(0.0, time.time() - started)

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
        return {
            "sys": {
                "uptime_h": f"{uptime_s/3600:.1f} h",
                "load": [load1, load5, load15],
                "mem": mem_pct,
            },
            "storage": {
                "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1),
                "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 1),
            },
            "docker": {"msg": "not enabled in gateway (placeholder)"},
        }

    # Live API: routes + tail logs
    @app.get("/api/routes")
    def api_routes():
        rs = []
        for r in app.routes:
            try:
                rs.append({
                    "path": getattr(r, "path", getattr(r, "path_format", "")),
                    "methods": list(getattr(r, "methods", []) or []),
                    "name": getattr(r, "name", ""),
                })
            except Exception:
                pass
        return {"ok": True, "routes": rs}

    @app.get("/api/logs")
    def api_logs(n: int = 200):
        if n <= 0:
            n = 1
        return {"ok": True, "lines": _LOG_RING[-n:]}
    @app.get("/api/debug/ip")
    def debug_ip(request: Request):
        return {
            "client_host": request.client.host if request.client else None,
            "xff": request.headers.get("x-forwarded-for"),
            "mode": os.getenv("IP_MODE","private"),
            "trust_xff": os.getenv("IP_TRUST_XFF","1"),
        }

    # Routers (REST)
    app.include_router(unified_router)      # /api/requests*, SSE
    app.include_router(ui_router)           # /ui + helpers
    app.include_router(pipeline_router)     # /api/llm/*
    app.include_router(chat_router)         # /api/chat/*

    # GraphQL endpoint (/graphql)
    app.include_router(graphql_router, prefix="/graphql")

    # Prometheus text endpoint for external scraping (optional)
    try:
        from prometheus_client import generate_latest  # type: ignore
    except Exception:
        generate_latest = None  # type: ignore

    @app.get("/api/metrics/prom", include_in_schema=False)
    def prom_text():
        if generate_latest is None:
            return PlainTextResponse("# prometheus-client not installed\n")
        return PlainTextResponse(generate_latest().decode("utf-8"))

    return app


app = create_app()
