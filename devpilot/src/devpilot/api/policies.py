"""Scoped, versioned governance policies and Policy-as-Code YAML."""
from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
import yaml
from devpilot.core.access import require_workspace_role
from devpilot.core.auth import get_current_user
from devpilot.core.database import get_session
from devpilot.core.policies import get_active_policy, policy_dict
from devpilot.core.trace_middleware import get_trace_id
from devpilot.core.workspace import get_workspace_id
from devpilot.models.governance import GovernanceAuditEventORM, PolicyDefinitionORM, RepositoryORM, TeamORM, WorkspaceORM

router = APIRouter(tags=["policies"])

class PolicyCreate(BaseModel):
    name: str = Field(min_length=3, max_length=128)
    scope_type: str = Field("workspace", pattern="^(workspace|team|repository)$")
    scope_id: str = Field("*", max_length=64)
    min_source_confidence: float = Field(.7, ge=0, le=1)
    min_test_coverage: float = Field(.6, ge=0, le=1)
    cost_budget_usd: float = Field(5, ge=0)
    require_security_scan: bool = True
    sensitive_patterns: list[str] = Field(default_factory=list, max_length=100)

def _validate_scope(session: Session, workspace_id: str, scope_type: str, scope_id: str) -> str:
    if scope_type == "workspace": return "*"
    model = TeamORM if scope_type == "team" else RepositoryORM
    if not session.scalar(select(model.id).where(model.id == scope_id, model.workspace_id == workspace_id)):
        raise HTTPException(404, f"{scope_type} scope not found")
    return scope_id

def _create(data: PolicyCreate, request: Request, session: Session, workspace_id: str, actor: str) -> PolicyDefinitionORM:
    scope_id = _validate_scope(session, workspace_id, data.scope_type, data.scope_id)
    existing = list(session.scalars(select(PolicyDefinitionORM).where(PolicyDefinitionORM.workspace_id == workspace_id, PolicyDefinitionORM.scope_type == data.scope_type, PolicyDefinitionORM.scope_id == scope_id)))
    for item in existing: item.active = False
    values = data.model_dump(exclude={"name", "scope_id"})
    policy = PolicyDefinitionORM(workspace_id=workspace_id, scope_id=scope_id, version=max([item.version for item in existing], default=0)+1, name=data.name, active=True, created_by=actor, **values)
    session.add(policy); session.flush()
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=actor, event_type="policy.version.created", entity_type="policy", entity_id=policy.id, trace_id=get_trace_id(request), payload={"version": policy.version, "name": policy.name, "scope_type": policy.scope_type, "scope_id": policy.scope_id}))
    return policy

@router.get("")
def list_policies(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict]:
    require_workspace_role(user, "admin", "owner", "security")
    if session.get(WorkspaceORM, workspace_id) is None: session.add(WorkspaceORM(id=workspace_id, name=workspace_id, slug=workspace_id.replace("_", "-"))); session.flush()
    get_active_policy(session, workspace_id); session.commit()
    return [policy_dict(item) for item in session.scalars(select(PolicyDefinitionORM).where(PolicyDefinitionORM.workspace_id == workspace_id).order_by(PolicyDefinitionORM.scope_type, PolicyDefinitionORM.scope_id, desc(PolicyDefinitionORM.version))).all()]

@router.post("", status_code=201)
def create_policy(data: PolicyCreate, request: Request, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    require_workspace_role(user, "owner", "admin")
    if session.get(WorkspaceORM, workspace_id) is None: session.add(WorkspaceORM(id=workspace_id, name=workspace_id, slug=workspace_id.replace("_", "-"))); session.flush()
    policy = _create(data, request, session, workspace_id, user.get("sub", "unknown")); session.commit(); return policy_dict(policy)

@router.get("/export")
def export_policies(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> Response:
    require_workspace_role(user, "admin", "owner", "security")
    items = session.scalars(select(PolicyDefinitionORM).where(PolicyDefinitionORM.workspace_id == workspace_id, PolicyDefinitionORM.active.is_(True))).all()
    fields = ("name", "scope_type", "scope_id", "min_source_confidence", "min_test_coverage", "cost_budget_usd", "require_security_scan", "sensitive_patterns")
    return Response(yaml.safe_dump({"apiVersion": "devpilot.io/v1", "kind": "PolicyBundle", "policies": [{field: getattr(item, field) for field in fields} for item in items]}, allow_unicode=True, sort_keys=False), media_type="application/yaml")

@router.post("/import", status_code=201)
def import_policies(request: Request, document: str = Body(..., media_type="application/yaml"), session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    require_workspace_role(user, "admin", "owner")
    try: payload = yaml.safe_load(document)
    except yaml.YAMLError as exc: raise HTTPException(422, "invalid policy YAML") from exc
    if not isinstance(payload, dict) or payload.get("apiVersion") != "devpilot.io/v1" or payload.get("kind") != "PolicyBundle": raise HTTPException(422, "unsupported policy bundle")
    policies = [PolicyCreate.model_validate(item) for item in payload.get("policies", [])]
    if not policies: raise HTTPException(422, "policy bundle is empty")
    created = [_create(item, request, session, workspace_id, user.get("sub", "unknown")) for item in policies]
    session.commit(); return {"created": [policy_dict(item) for item in created]}
