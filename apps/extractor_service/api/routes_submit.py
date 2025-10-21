from fastapi import APIRouter
from ..core.models import SubmitRequest, RequestState
from ..core.queue import enqueue_job, emit_event

router = APIRouter()

@router.post("/requests", response_model=RequestState)
def submit(req: SubmitRequest):
    rid = enqueue_job(req.model_dump())
    emit_event(rid, "queued", 0.0, "queued")
    return RequestState(request_id=rid, state="queued", progress=0.0)
