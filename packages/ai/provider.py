from __future__ import annotations
import base64
import json
import re
import os
from typing import List, Dict, Any, Optional
import httpx

# ---------- helpers ------------------------------------------------------------

def _first_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Extract the first JSON object from LLM text."""
    m = re.search(r"```(?:json)?\s*({.*?})\s*```", text, re.S | re.I)
    raw = m.group(1) if m else None
    if not raw:
        m = re.search(r"(\{.*\})", text, re.S)
        raw = m.group(1) if m else None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        raw = re.sub(r",(\s*[}\]])", r"\1", raw)  # strip trailing commas
        try:
            return json.loads(raw)
        except Exception:
            return None

# ---------- provider -----------------------------------------------------------

class LLMProvider:
    def extract_json(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        raise NotImplementedError

    def extract_json_vision(self, messages: List[Dict[str, Any]], images: List[bytes]) -> Dict[str, Any]:
        """Vision variant. Default: raise if not implemented."""
        raise NotImplementedError

# Ollama API: /api/chat supports `images` on user message for vision models
# See https://github.com/ollama/ollama/blob/main/docs/api.md#generate-a-chat-completion

class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, text_model: str, vision_model: Optional[str] = None):
        self.base = base_url.rstrip("/")
        self.text_model = text_model
        self.vision_model = vision_model or text_model

    def _chat(self, model: str, messages: List[Dict[str, Any]], timeout: float = 120.0) -> str:
        url = f"{self.base}/api/chat"
        payload = {"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.1}}
        with httpx.Client(timeout=timeout) as cli:
            r = cli.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        return (data.get("message") or {}).get("content", "") or ""

    def extract_json(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        content = self._chat(self.text_model, messages)
        js = _first_json_block(content)
        if js is None:
            raise RuntimeError("LLM did not return JSON")
        return js

    def extract_json_vision(self, messages: List[Dict[str, Any]], images: List[bytes]) -> Dict[str, Any]:
        if not images:
            return self.extract_json(messages)
        # Add images to the last user message (Ollama expects data URLs)
        msgs = list(messages)
        for i in range(len(msgs)-1, -1, -1):
            if msgs[i].get("role") == "user":
                imgs = []
                for raw in images:
                    b64 = base64.b64encode(raw).decode("ascii")
                    imgs.append(f"data:image/png;base64,{b64}")
                msgs[i] = {**msgs[i], "images": imgs}
                break
        content = self._chat(self.vision_model, msgs)
        js = _first_json_block(content)
        if js is None:
            raise RuntimeError("Vision LLM did not return JSON")
        return js

def build_provider_from_env() -> Optional[LLMProvider]:
    if os.getenv("USE_LLM", "false").lower() not in ("1", "true", "yes"):
        return None
    prov = os.getenv("LLM_PROVIDER", "ollama").lower()
    if prov == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
        text = os.getenv("OLLAMA_TEXT_MODEL", "qwen2.5:7b-instruct-q4_K_M")
        vis  = os.getenv("OLLAMA_VISION_MODEL") or text
        return OllamaProvider(base, text, vis)
    return None
