"""Minimal SCIM 2.0 user lifecycle endpoint for enterprise provisioning."""
from datetime import datetime, timezone
import secrets
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from governforge.config import AppSettings
from governforge.core.database import get_session
from governforge.models.governance import GovernanceAuditEventORM, WorkspaceORM
from governforge.models.user import AuthSessionORM, UserORM

router = APIRouter(tags=["scim"])
USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"

def _authorize(authorization: str = Header("")) -> AppSettings:
    settings = AppSettings(); expected = settings.scim_bearer_token.get_secret_value()
    presented = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not settings.scim_enabled or not expected or not secrets.compare_digest(expected, presented): raise HTTPException(401, "invalid SCIM bearer token")
    return settings

class ScimUserIn(BaseModel):
    userName: str = Field(min_length=3, max_length=64)
    active: bool = True
    displayName: str | None = None

class PatchOperation(BaseModel):
    op: str
    path: str | None = None
    value: object | None = None

class ScimPatch(BaseModel):
    Operations: list[PatchOperation]

def _output(user: UserORM) -> dict:
    return {"schemas": [USER_SCHEMA], "id": str(user.id), "userName": user.username, "active": user.is_active, "meta": {"resourceType": "User"}}

@router.get("/Users")
def list_users(startIndex: int = 1, count: int = 100, session: Session = Depends(get_session), settings: AppSettings = Depends(_authorize)) -> dict:
    items = session.scalars(select(UserORM).where(UserORM.tenant_id == settings.scim_default_workspace).offset(max(0, startIndex - 1)).limit(min(count, 200))).all()
    return {"schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"], "totalResults": len(items), "startIndex": startIndex, "itemsPerPage": len(items), "Resources": [_output(i) for i in items]}

@router.post("/Users", status_code=201)
def create_user(data: ScimUserIn, session: Session = Depends(get_session), settings: AppSettings = Depends(_authorize)) -> dict:
    workspace_id = settings.scim_default_workspace
    if session.get(WorkspaceORM, workspace_id) is None: session.add(WorkspaceORM(id=workspace_id, name=workspace_id, slug=workspace_id.lower().replace("_", "-")[:64])); session.flush()
    if session.scalar(select(UserORM.id).where(UserORM.username == data.userName)): raise HTTPException(409, "SCIM user already exists")
    user = UserORM(username=data.userName, hashed_password="!scim", tenant_id=workspace_id, role="member", is_active=data.active); session.add(user); session.flush()
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id="scim", event_type="auth.scim.user.created", entity_type="user", entity_id=str(user.id), payload={"username": user.username, "active": user.is_active})); session.commit(); return _output(user)

@router.get("/Users/{user_id}")
def get_user(user_id: int, session: Session = Depends(get_session), settings: AppSettings = Depends(_authorize)) -> dict:
    user = session.scalar(select(UserORM).where(UserORM.id == user_id, UserORM.tenant_id == settings.scim_default_workspace))
    if not user: raise HTTPException(404, "SCIM user not found")
    return _output(user)

@router.patch("/Users/{user_id}")
def patch_user(user_id: int, data: ScimPatch, session: Session = Depends(get_session), settings: AppSettings = Depends(_authorize)) -> dict:
    user = session.scalar(select(UserORM).where(UserORM.id == user_id, UserORM.tenant_id == settings.scim_default_workspace))
    if not user: raise HTTPException(404, "SCIM user not found")
    for operation in data.Operations:
        if operation.op.lower() not in {"replace", "add"}: continue
        if (operation.path or "").lower() == "active": user.is_active = bool(operation.value)
        if (operation.path or "").lower() == "username" and operation.value: user.username = str(operation.value)[:64]
    if not user.is_active:
        session.query(AuthSessionORM).filter(AuthSessionORM.user_id == user.id, AuthSessionORM.revoked_at.is_(None)).update({AuthSessionORM.revoked_at: datetime.now(timezone.utc)})
    session.add(GovernanceAuditEventORM(workspace_id=user.tenant_id, actor_id="scim", event_type="auth.scim.user.updated", entity_type="user", entity_id=str(user.id), payload={"username": user.username, "active": user.is_active})); session.commit(); return _output(user)
