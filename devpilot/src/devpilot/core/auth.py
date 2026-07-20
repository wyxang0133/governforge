"""JWT authentication primitives."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from devpilot.config import AppSettings

security_scheme = HTTPBearer(auto_error=False)

def _get_settings() -> AppSettings:
    return AppSettings()

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    settings = _get_settings()
    if not settings.jwt_key:
        raise RuntimeError("JWT_SECRET_KEY is required")
    now = datetime.now(timezone.utc)
    payload = {**data, "iat": now, "exp": now + (expires_delta or timedelta(minutes=settings.jwt_expire_minutes)), "jti": data.get("jti") or str(uuid4())}
    return jwt.encode(payload, settings.jwt_key, algorithm=settings.jwt_algorithm)

def decode_access_token(token: str) -> dict:
    settings = _get_settings()
    try:
        return jwt.decode(token, settings.jwt_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(401, "Token 已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(401, "Token 无效") from exc

def verify_access_token(token: str) -> Optional[dict]:
    try:
        return decode_access_token(token)
    except HTTPException:
        return None

def get_current_user(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)) -> dict:
    token = credentials.credentials if credentials else request.cookies.get("devpilot_access")
    if not token:
        raise HTTPException(401, "缺少认证 Token")
    payload = decode_access_token(token)
    if payload.get("type", "access") != "access":
        raise HTTPException(401, "Token 类型无效")
    return payload
