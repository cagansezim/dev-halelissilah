import json
from ..core.storage import get_bytes, put_bytes
from ..config import settings
from ..core.models import RetryPayload

def apply_feedback_and_finalize(rid: str, body: RetryPayload) -> bool:
    try:
        fd = json.loads(get_bytes(f"expenses/{rid}/final_draft.json").decode("utf-8"))
        data = fd.get("final") or {}
        if body.corrections:
            # shallow merge for v1; extend with jsonpath patch later
            for k, v in body.corrections.items():
                if k in data: data[k] = v
        out = {"final": data, "flags": [], "confidence": 0.99}
        put_bytes(f"expenses/{rid}/final.json", json.dumps(out, ensure_ascii=False).encode(), "application/json")
        return True
    except Exception:
        return False
