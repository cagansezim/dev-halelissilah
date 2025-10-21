import json, asyncio, redis
from ..config import settings
from ..core.queue import r, JOBS_STREAM, emit_event
from .stages import run_pipeline

def start_worker_loop():
    last_id = "0-0"
    while True:
        streams = r.xread({JOBS_STREAM: last_id}, block=5000, count=1)
        if not streams: continue
        _, messages = streams[0]
        for msg_id, fields in messages:
            payload = json.loads(fields["payload"]); rid = payload["request_id"]
            try:
                emit_event(rid, "processing", 0.05, "ingesting")
                final_draft = asyncio.get_event_loop().run_until_complete(run_pipeline(payload, rid))
                if (not final_draft.get("flags")) and final_draft.get("confidence",0)>=settings.CONF_THRESHOLD:
                    emit_event(rid, "done", 1.0, "auto-approved")
                else:
                    emit_event(rid, "needs_review", 0.8, "human review required")
            except Exception as e:
                emit_event(rid, "failed", 1.0, f"error: {e}")
            last_id = msg_id
