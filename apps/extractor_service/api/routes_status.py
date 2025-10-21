from fastapi import APIRouter
import redis
from ..config import settings

router = APIRouter()
r = redis.from_url(settings.REDIS_URL, decode_responses=True)

@router.get("/requests/{rid}")
def status(rid: str):
    return r.hgetall(f"extractor:state:{rid}") or {"request_id": rid, "state": "unknown"}
