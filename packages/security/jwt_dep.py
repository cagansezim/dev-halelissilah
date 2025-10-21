# packages/security/jwt_dep.py
from __future__ import annotations
import os, time, typing as t
from fastapi import Header, HTTPException
import jwt

ALGOS = ["HS256", "RS256"]

ERP_JWT_ALGO = os.getenv("ERP_JWT_ALGO", "HS256")
ERP_JWT_SECRET = os.getenv("ERP_JWT_SECRET", "change-me")   # HS256
ERP_JWT_PUBKEY = os.getenv("ERP_JWT_PUBKEY", "")            # RS256 (optional)
ERP_JWT_AUD = os.getenv("ERP_JWT_AUD", "pruva")

if ERP_JWT_ALGO not in ALGOS:
    ERP_JWT_ALGO = "HS256"

def _decode(token: str) -> dict:
    if ERP_JWT_ALGO == "HS256":
        return jwt.decode(token, ERP_JWT_SECRET, algorithms=["HS256"], audience=ERP_JWT_AUD)
    return jwt.decode(token, ERP_JWT_PUBKEY, algorithms=["RS256"], audience=ERP_JWT_AUD)

def verify_service_jwt(authorization: t.Annotated[str, Header(..., alias="Authorization")]):
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.split()[1]
    try:
        payload = _decode(token)
        if payload.get("type") != "service":
            raise HTTPException(status_code=401, detail="Wrong token type")
        if payload.get("exp", 0) < time.time():
            raise HTTPException(status_code=401, detail="Expired token")
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
