from fastapi import APIRouter
from ..core.models import RetryPayload
from ..llm.apply_feedback import apply_feedback_and_finalize

router = APIRouter()

@router.post("/requests/{rid}/retry")
def retry(rid: str, body: RetryPayload):
    ok = apply_feedback_and_finalize(rid, body)
    return {"ok": ok}
