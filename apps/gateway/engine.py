# apps/gateway/engine.py
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

import httpx

from packages.shared.settings import settings


def _detect_ollama_base() -> str:
    """
    Resolve Ollama base URL from:
      1) OLLAMA_HOST env
      2) settings.OLLAMA_HOST or settings.OLLAMA_BASE
      3) default 'http://ollama:11434'
    """
    env = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL")
    if env:
        return env.rstrip("/")

    for attr in ("OLLAMA_HOST", "OLLAMA_BASE", "OLLAMA_BASE_URL"):
        val: Optional[str] = getattr(settings, attr, None)  # type: ignore[attr-defined]
        if val:
            return str(val).rstrip("/")

    return "http://ollama:11434"


class Engine:
    """
    Minimal HTTP client for Ollama that works across SDK versions.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def list_models(self) -> Dict[str, Any]:
        with httpx.Client(timeout=30) as c:
            r = c.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            return r.json()

    def chat(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        stream: bool = False,
    ) -> Dict[str, Any] | Iterable[Dict[str, Any]]:
        payload = {"model": model, "messages": messages, "stream": bool(stream)}
        with httpx.Client(timeout=None) as c:
            if stream:
                # generator of JSON lines
                with c.stream("POST", f"{self.base_url}/api/chat", json=payload) as s:
                    for line in s.iter_lines():
                        if not line:
                            continue
                        yield httpx.Response(200, content=line).json()
            else:
                r = c.post(f"{self.base_url}/api/chat", json=payload)
                r.raise_for_status()
                return r.json()


_engine_singleton: Optional[Engine] = None

def get_engine() -> Engine:
    """
    Lazy singleton so callers can do: engine = Depends(get_engine)
    """
    global _engine_singleton
    if _engine_singleton is None:
        _engine_singleton = Engine(base_url=_detect_ollama_base())
    return _engine_singleton
