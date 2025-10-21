from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/review/{rid}", response_class=HTMLResponse)
def review_page(rid: str, request: Request):
    return f"""<html><body><h3>Review {rid}</h3>
    <p>Use your admin UI or POST /extractor/requests/{rid}/retry with corrections.</p></body></html>"""
