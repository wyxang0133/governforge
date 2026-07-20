"""Local JWT authentication for development and standalone deployments.

Production installations can replace this router with an OIDC adapter while
retaining the same claims: sub, tenant_id and role.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from devpilot.config import AppSettings
from devpilot.core.auth import create_access_token, decode_access_token, get_current_user
from devpilot.core.database import get_session
from devpilot.core.password_hash import hash_password, verify_password
from devpilot.models.user import AuthSessionORM, UserORM
from devpilot.models.governance import GovernanceAuditEventORM, WorkspaceORM
from devpilot.core.oidc import authorization_request, exchange_and_validate

router = APIRouter(tags=["auth"])

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    tenant_id: str = Field("ai_platform", max_length=64)

class RefreshRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

def _tokens(user: UserORM, session: Session) -> tuple[TokenResponse, AuthSessionORM]:
    settings = AppSettings()
    claims = {"sub": user.username, "tenant_id": user.tenant_id, "role": user.role}
    session_id, refresh_jti = str(uuid4()), str(uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days)
    record = AuthSessionORM(id=session_id, user_id=user.id, refresh_jti_hash=hashlib.sha256(refresh_jti.encode()).hexdigest(), expires_at=expires_at)
    session.add(record)
    tokens = TokenResponse(
        access_token=create_access_token({**claims, "type": "access", "sid": session_id}, timedelta(minutes=settings.jwt_expire_minutes)),
        refresh_token=create_access_token({**claims, "type": "refresh", "sid": session_id, "jti": refresh_jti}, timedelta(days=settings.refresh_token_days)),
    )
    return tokens, record

def _set_auth_cookies(response: Response, tokens: TokenResponse) -> None:
    settings = AppSettings()
    secure = settings.environment == "production"
    response.set_cookie("devpilot_access", tokens.access_token, httponly=True, secure=secure, samesite="strict", max_age=settings.jwt_expire_minutes * 60, path="/")
    response.set_cookie("devpilot_refresh", tokens.refresh_token, httponly=True, secure=secure, samesite="strict", max_age=settings.refresh_token_days * 86400, path="/api/auth")

@router.post("/register", response_model=TokenResponse)
def register(data: Credentials, response: Response, session: Session = Depends(get_session)):
    if not AppSettings().allow_local_auth or not AppSettings().allow_self_registration:
        raise HTTPException(403, "Self registration is disabled")
    if session.scalar(select(UserORM).where(UserORM.username == data.username)):
        raise HTTPException(409, "用户名已存在")
    has_admin = session.scalar(select(UserORM.id).where(UserORM.tenant_id == data.tenant_id, UserORM.role.in_(["admin", "owner"])).limit(1))
    user = UserORM(username=data.username, hashed_password=hash_password(data.password), tenant_id=data.tenant_id, role="member" if has_admin else "admin")
    session.add(user); session.commit(); session.refresh(user)
    tokens, _ = _tokens(user, session); session.commit(); _set_auth_cookies(response, tokens); return tokens

@router.post("/login", response_model=TokenResponse)
def login(data: Credentials, response: Response, session: Session = Depends(get_session)):
    if not AppSettings().allow_local_auth:
        raise HTTPException(403, "Local password authentication is disabled")
    user = session.scalar(select(UserORM).where(UserORM.username == data.username))
    if user is None or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "用户名或密码错误")
    if not user.is_active:
        raise HTTPException(403, "账号已禁用")
    tokens, _ = _tokens(user, session); session.commit(); _set_auth_cookies(response, tokens); return tokens

@router.post("/refresh", response_model=TokenResponse)
def refresh(response: Response, request: Request, data: RefreshRequest | None = None, session: Session = Depends(get_session)):
    refresh_token = data.refresh_token if data else request.cookies.get("devpilot_refresh")
    if not refresh_token:
        raise HTTPException(401, "缺少 Refresh Token")
    payload = decode_access_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(401, "Refresh Token 无效")
    user = session.scalar(select(UserORM).where(UserORM.username == payload.get("sub"), UserORM.tenant_id == payload.get("tenant_id")))
    if user is None or not user.is_active:
        raise HTTPException(401, "用户不存在或已禁用")
    record = session.get(AuthSessionORM, payload.get("sid"))
    presented_hash = hashlib.sha256(str(payload.get("jti", "")).encode()).hexdigest()
    now = datetime.now(timezone.utc)
    expires_at = record.expires_at.replace(tzinfo=timezone.utc) if record and record.expires_at.tzinfo is None else (record.expires_at if record else now)
    if record is None or record.user_id != user.id or record.revoked_at is not None or record.refresh_jti_hash != presented_hash or expires_at <= now:
        session.query(AuthSessionORM).filter(AuthSessionORM.user_id == user.id, AuthSessionORM.revoked_at.is_(None)).update({AuthSessionORM.revoked_at: now})
        session.commit()
        response.delete_cookie("devpilot_access", path="/"); response.delete_cookie("devpilot_refresh", path="/api/auth")
        raise HTTPException(401, "Refresh Token 已失效或检测到重放")
    tokens, replacement = _tokens(user, session)
    record.revoked_at, record.replaced_by, record.last_used_at = now, replacement.id, now
    session.commit(); _set_auth_cookies(response, tokens); return tokens

@router.post("/logout", status_code=204)
def logout(response: Response, request: Request, session: Session = Depends(get_session)) -> Response:
    token = request.cookies.get("devpilot_refresh")
    if token:
        try:
            payload = decode_access_token(token)
            record = session.get(AuthSessionORM, payload.get("sid"))
            if record and record.revoked_at is None:
                record.revoked_at = datetime.now(timezone.utc); session.commit()
        except HTTPException:
            pass
    response.delete_cookie("devpilot_access", path="/")
    response.delete_cookie("devpilot_refresh", path="/api/auth")
    response.status_code = 204
    return response

@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return {"username": user.get("sub"), "workspace_id": user.get("tenant_id"), "role": user.get("role", "member")}


@router.get("/config")
def auth_config() -> dict:
    settings = AppSettings()
    return {"local_auth_enabled": settings.allow_local_auth, "self_registration_enabled": settings.allow_local_auth and settings.allow_self_registration, "oidc_enabled": settings.oidc_enabled}


@router.get("/oidc/login")
def oidc_login() -> RedirectResponse:
    settings = AppSettings()
    if not settings.oidc_enabled or not settings.oidc_issuer or not settings.oidc_client_id:
        raise HTTPException(404, "OIDC is not configured")
    try:
        url, state, nonce, verifier = authorization_request(settings)
    except Exception as exc:
        raise HTTPException(503, "OIDC discovery failed") from exc
    response = RedirectResponse(url, status_code=302)
    secure = settings.environment == "production"
    for name, value in (("devpilot_oidc_state", state), ("devpilot_oidc_nonce", nonce), ("devpilot_oidc_verifier", verifier)):
        response.set_cookie(name, value, httponly=True, secure=secure, samesite="lax", max_age=600, path="/api/auth/oidc")
    return response


@router.get("/oidc/callback")
def oidc_callback(code: str, state: str, request: Request, session: Session = Depends(get_session)) -> RedirectResponse:
    settings = AppSettings()
    expected_state = request.cookies.get("devpilot_oidc_state")
    nonce, verifier = request.cookies.get("devpilot_oidc_nonce"), request.cookies.get("devpilot_oidc_verifier")
    if not expected_state or not nonce or not verifier or not secrets.compare_digest(expected_state, state):
        raise HTTPException(400, "OIDC state validation failed")
    try:
        claims = exchange_and_validate(settings, code, verifier, nonce)
    except Exception as exc:
        raise HTTPException(401, "OIDC token validation failed") from exc
    username = str(claims.get("preferred_username") or claims.get("email") or claims["sub"])[:64]
    workspace_id = str(claims.get(settings.oidc_workspace_claim) or settings.oidc_default_workspace)[:64]
    claimed_role = str(claims.get(settings.oidc_role_claim) or "member")
    role = claimed_role if claimed_role in {"member", "security", "admin", "owner"} else "member"
    if session.get(WorkspaceORM, workspace_id) is None:
        session.add(WorkspaceORM(id=workspace_id, name=workspace_id, slug=workspace_id.lower().replace("_", "-")[:64])); session.flush()
    user = session.scalar(select(UserORM).where(UserORM.username == username))
    if user and user.tenant_id != workspace_id:
        raise HTTPException(409, "OIDC identity is already bound to another workspace")
    if user is None:
        user = UserORM(username=username, hashed_password="!oidc", tenant_id=workspace_id, role=role); session.add(user); session.flush()
    user.role, user.is_active = role, True
    tokens, _ = _tokens(user, session)
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=username, event_type="auth.oidc.login", entity_type="user", entity_id=str(user.id), payload={"issuer": settings.oidc_issuer, "subject": claims["sub"]})); session.commit()
    response = RedirectResponse("/", status_code=302); _set_auth_cookies(response, tokens)
    for name in ("devpilot_oidc_state", "devpilot_oidc_nonce", "devpilot_oidc_verifier"): response.delete_cookie(name, path="/api/auth/oidc")
    return response
