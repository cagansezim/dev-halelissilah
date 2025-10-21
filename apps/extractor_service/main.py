from fastapi import FastAPI
from .api import routes_submit, routes_status, routes_retry, routes_review

app = FastAPI(title="Pruva Expense Extractor", version="1.0.0")
app.include_router(routes_submit.router, prefix="/extractor", tags=["submit"])
app.include_router(routes_status.router, prefix="/extractor", tags=["status"])
app.include_router(routes_retry.router,  prefix="/extractor", tags=["retry"])
app.include_router(routes_review.router, prefix="/extractor", tags=["review"])

@app.get("/health")
def health():
    return {"ok": True, "service": "extractor"}
