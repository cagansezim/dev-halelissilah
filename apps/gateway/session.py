from __future__ import annotations

import threading
import uuid
from typing import Dict, List, Optional

from apps.gateway.schemas import ChatSession, Turn

try:
    import redis  # type: ignore
except Exception:  # pragma: no cover
    redis = None  # type: ignore


class _MemoryIndex:
    def __init__(self):
        self.lock = threading.Lock()
        self.data: Dict[str, str] = {}
        self.order: List[str] = []

    def set(self, key: str, val: str):
        with self.lock:
            self.data[key] = val
            if key not in self.order:
                self.order.append(key)

    def get(self, key: str) -> Optional[str]:
        with self.lock:
            return self.data.get(key)

    def list(self, limit: int) -> List[str]:
        with self.lock:
            return list(reversed(self.order))[:limit]


class SessionStore:
    def __init__(self, url: str = "redis://localhost:6379/0", namespace: str = "sess"):
        self.ns = namespace
        self.mem = _MemoryIndex()
        self.r = None
        if redis is not None:
            try:
                self.r = redis.Redis.from_url(url, decode_responses=True)  # type: ignore
                self.r.ping()
            except Exception:
                self.r = None  # fallback to memory

    def _key(self, sid: str) -> str:
        return f"{self.ns}:{sid}"

    def _save_raw(self, sid: str, raw: str) -> None:
        if self.r:
            self.r.set(self._key(sid), raw)
            try:
                updated = ChatSession.model_validate_json(raw).updated_ts
            except Exception:
                updated = 0.0
            self.r.zadd(f"{self.ns}:index", {sid: updated})
        else:
            self.mem.set(self._key(sid), raw)

    def _load_raw(self, sid: str) -> Optional[str]:
        if self.r:
            return self.r.get(self._key(sid))
        return self.mem.get(self._key(sid))

    def _list_ids(self, limit: int) -> List[str]:
        if self.r:
            return self.r.zrevrange(f"{self.ns}:index", 0, limit - 1)
        keys = [k[len(self.ns) + 1 :] for k in self.mem.list(limit) if k.startswith(self.ns + ":")]
        return keys

    # ---------------------------- API

    def create(self, model: str, title: str = "New session") -> ChatSession:
        sid = uuid.uuid4().hex[:12]
        ss = ChatSession(id=sid, model=model, title=title)
        self.save(ss)
        return ss

    def save(self, ss: ChatSession) -> None:
        self._save_raw(ss.id, ss.model_dump_json())

    def get(self, sid: str) -> Optional[ChatSession]:
        raw = self._load_raw(sid)
        if not raw:
            return None
        return ChatSession.model_validate_json(raw)

    def list(self, limit: int = 100) -> List[ChatSession]:
        out: List[ChatSession] = []
        for sid in self._list_ids(limit):
            ss = self.get(sid)
            if ss:
                out.append(ss)
        return out

    def add_turn(self, sid: str, turn: Turn) -> ChatSession:
        ss = self.get(sid)
        if not ss:
            raise KeyError("session not found")
        ss.turns.append(turn)
        ss.updated_ts = turn.ts
        self.save(ss)
        return ss

    def set_title(self, sid: str, title: str) -> None:
        ss = self.get(sid)
        if not ss:
            return
        ss.title = title
        self.save(ss)
