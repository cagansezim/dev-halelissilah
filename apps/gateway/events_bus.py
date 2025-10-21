# apps/gateway/events_bus.py
from __future__ import annotations
import os, json, time, typing as t
import redis

_redis = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)

def new_request(kind: str) -> str:
    import uuid
    rid = uuid.uuid4().hex
    _redis.hset(f"req:{rid}", mapping={"kind": kind, "state": "queued", "progress": "0"})
    return rid

def set_state(rid: str, state: str, progress: float = 0.0, result: dict | None = None, error: str | None = None):
    payload = {"state": state, "progress": f"{progress:.3f}"}
    if result is not None:
        payload["result"] = json.dumps(result, ensure_ascii=False)
    if error:
        payload["error"] = error
    _redis.hset(f"req:{rid}", mapping=payload)
    evt = {"ts": int(time.time()), "request_id": rid, "state": state, "progress": progress, "error": error}
    _redis.xadd(f"events:{rid}", {"data": json.dumps(evt, ensure_ascii=False)})

def get_status(rid: str) -> dict:
    h = _redis.hgetall(f"req:{rid}") or {}
    if "result" in h:
        h["result"] = json.loads(h["result"])
    if "progress" in h:
        try: h["progress"] = float(h["progress"])
        except Exception: h["progress"] = 0.0
    return h

def enqueue(kind: str, rid: str, payload: dict):
    _redis.lpush("jobs", json.dumps({"kind": kind, "request_id": rid, **(payload or {})}, ensure_ascii=False))

def stream_events(rid: str, last_id: str = "$", block_ms: int = 15000):
    key = f"events:{rid}"
    while True:
        msgs = _redis.xread({key: last_id}, block=block_ms, count=10)
        if not msgs:
            yield None
            continue
        for _, records in msgs:
            for (msg_id, fields) in records:
                last_id = msg_id
                yield fields.get("data", "{}")
