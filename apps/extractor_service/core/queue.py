import json, uuid, redis
from ..config import settings

r = redis.from_url(settings.REDIS_URL, decode_responses=True)
JOBS_STREAM = "extractor:jobs"
EVENTS_PREFIX = "extractor:events:"

def enqueue_job(payload: dict) -> str:
    rid = payload.get("request_id") or str(uuid.uuid4())
    payload["request_id"] = rid
    r.xadd(JOBS_STREAM, {"payload": json.dumps(payload)})
    return rid

def emit_event(rid: str, state: str, progress: float = 0.0, message: str = ""):
    r.xadd(f"{EVENTS_PREFIX}{rid}", {"state": state, "progress": progress, "message": message})
    r.hset(f"extractor:state:{rid}", mapping={"state": state, "progress": progress, "message": message})
