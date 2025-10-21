from __future__ import annotations
import time, threading, uuid
from typing import Dict, Any, List, Optional

class Session:
    def __init__(self, meta: Dict[str, Any]):
        self.id = uuid.uuid4().hex
        self.created = time.time()
        self.updated = self.created
        self.meta = meta
        self.messages: List[Dict[str, str]] = []   # [{"role": "...", "content": "..."}]
        self.data: Dict[str, Any] = {}             # last structured result

class SessionStore:
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = ttl_seconds
        self._by_id: Dict[str, Session] = {}
        self._lock = threading.Lock()

    def _gc(self):
        now = time.time()
        drop = [sid for sid, s in self._by_id.items() if now - s.updated > self.ttl]
        for sid in drop:
            self._by_id.pop(sid, None)

    def create(self, meta: Dict[str, Any]) -> Session:
        with self._lock:
            self._gc()
            s = Session(meta)
            self._by_id[s.id] = s
            return s

    def get(self, sid: str) -> Optional[Session]:
        with self._lock:
            self._gc()
            s = self._by_id.get(sid)
            if s:
                s.updated = time.time()
            return s

    def append(self, sid: str, role: str, content: str):
        s = self.get(sid)
        if not s:
            raise KeyError("session not found")
        s.messages.append({"role": role, "content": content})
        s.updated = time.time()

    def set_data(self, sid: str, data: Dict[str, Any]):
        s = self.get(sid)
        if not s:
            raise KeyError("session not found")
        s.data = data
        s.updated = time.time()
