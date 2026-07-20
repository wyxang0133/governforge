"""OpenAI-compatible governed model router and unified TCO ledger."""
from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from governforge.core.access import require_workspace_role
from governforge.core.auth import get_current_user
from governforge.core.budgets import applicable_budgets
from governforge.core.database import get_session
from governforge.core.trace_middleware import get_trace_id
from governforge.core.workspace import get_workspace_id
from governforge.models.governance import (
    AIUsageEventORM, CostEventORM, GovernanceAuditEventORM, IntegrationCredentialORM,
    ModelRouteORM, WorkspaceORM,
)

router = APIRouter(tags=["model-gateway"])
_open_circuits: dict[str, datetime] = {}


class RouteIn(BaseModel):
    model_alias: str = Field(min_length=2, max_length=128, pattern=r"^[a-zA-Z0-9._:-]+$")
    provider: str = Field(min_length=2, max_length=64)
    upstream_model: str = Field(min_length=2, max_length=128)
    base_url: HttpUrl
    api_key_env: str = Field(pattern=r"^MODEL_PROVIDER_[A-Z0-9_]+_API_KEY$")
    priority: int = Field(100, ge=1, le=10000)
    enabled: bool = True
    timeout_seconds: float = Field(30, ge=1, le=120)
    max_retries: int = Field(1, ge=0, le=3)
    input_cost_per_million: float = Field(0, ge=0)
    output_cost_per_million: float = Field(0, ge=0)


class CostIn(BaseModel):
    external_id: str = Field(min_length=2, max_length=128)
    category: str = Field(pattern="^(model|human_review|rework|incident|infrastructure|opportunity)$")
    amount_usd: float = Field(0, ge=0)
    minutes: float = Field(0, ge=0)
    role: str | None = Field(None, max_length=64)
    repository_id: str | None = None
    pull_request_id: str | None = None
    run_id: str | None = None
    trace_id: str | None = Field(None, max_length=128)
    detail: dict = Field(default_factory=dict)


def _machine(session: Session, token: str, workspace_id: str) -> IntegrationCredentialORM:
    digest = hashlib.sha256(token.encode()).hexdigest()
    item = session.scalar(select(IntegrationCredentialORM).where(
        IntegrationCredentialORM.workspace_id == workspace_id,
        IntegrationCredentialORM.token_hash == digest,
        IntegrationCredentialORM.active.is_(True),
    ))
    now = datetime.now(timezone.utc)
    expires_at = item.expires_at if item is not None else None
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if item is None or "model:invoke" not in (item.scopes or []) or (expires_at and expires_at <= now):
        raise HTTPException(401, "invalid, expired or insufficient model credential")
    item.last_used_at = now
    return item


@router.get("/routes")
def list_routes(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict]:
    require_workspace_role(user, "admin", "owner", "security")
    items = session.scalars(select(ModelRouteORM).where(ModelRouteORM.workspace_id == workspace_id).order_by(ModelRouteORM.model_alias, ModelRouteORM.priority)).all()
    return [{"id": item.id, "model_alias": item.model_alias, "provider": item.provider,
             "upstream_model": item.upstream_model, "base_url": item.base_url,
             "api_key_env": item.api_key_env, "secret_configured": bool(os.getenv(item.api_key_env)),
             "priority": item.priority, "enabled": item.enabled, "timeout_seconds": item.timeout_seconds,
             "max_retries": item.max_retries, "input_cost_per_million": item.input_cost_per_million,
             "output_cost_per_million": item.output_cost_per_million} for item in items]


@router.post("/routes", status_code=201)
def create_route(data: RouteIn, request: Request, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    require_workspace_role(user, "admin", "owner")
    if session.get(WorkspaceORM, workspace_id) is None:
        session.add(WorkspaceORM(id=workspace_id, name=workspace_id, slug=workspace_id.lower().replace("_", "-")[:64])); session.flush()
    exists = session.scalar(select(ModelRouteORM).where(ModelRouteORM.workspace_id == workspace_id,
        ModelRouteORM.model_alias == data.model_alias, ModelRouteORM.priority == data.priority))
    if exists:
        raise HTTPException(409, "route alias and priority already exist")
    item = ModelRouteORM(workspace_id=workspace_id, created_by=user.get("sub", "unknown"),
                         **(data.model_dump(mode="json") | {"base_url": str(data.base_url).rstrip("/")}))
    session.add(item); session.flush()
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", "unknown"),
        event_type="model.route.created", entity_type="model_route", entity_id=item.id,
        trace_id=get_trace_id(request), payload={"alias": item.model_alias, "provider": item.provider,
        "priority": item.priority, "api_key_env": item.api_key_env}))
    session.commit()
    return {"id": item.id, "model_alias": item.model_alias, "provider": item.provider, "priority": item.priority}


@router.delete("/routes/{route_id}", status_code=204)
def disable_route(route_id: str, request: Request, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> None:
    require_workspace_role(user, "admin", "owner")
    item = session.scalar(select(ModelRouteORM).where(ModelRouteORM.id == route_id, ModelRouteORM.workspace_id == workspace_id))
    if item is None:
        raise HTTPException(404, "model route not found")
    item.enabled = False
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", "unknown"),
        event_type="model.route.disabled", entity_type="model_route", entity_id=item.id,
        trace_id=get_trace_id(request), payload={"alias": item.model_alias, "provider": item.provider}))
    session.commit()


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    session: Session = Depends(get_session),
    authorization: str = Header(...),
    x_workspace_id: str = Header(...),
    x_repository_id: str | None = Header(None),
    x_pull_request_id: str | None = Header(None),
    x_agent_run_id: str | None = Header(None),
) -> dict:
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    credential = _machine(session, token, x_workspace_id)
    payload = await request.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise HTTPException(422, "messages must be an array")
    if payload.get("stream"):
        raise HTTPException(422, "streaming is not enabled for the governed v1 route")
    alias = str(payload.get("model") or "")
    routes = list(session.scalars(select(ModelRouteORM).where(
        ModelRouteORM.workspace_id == x_workspace_id, ModelRouteORM.model_alias == alias,
        ModelRouteORM.enabled.is_(True),
    ).order_by(ModelRouteORM.priority)))
    if not routes:
        raise HTTPException(404, "MODEL_ROUTE_NOT_FOUND")
    budget = applicable_budgets(session, x_workspace_id, x_repository_id)
    if any(item["hard_limit"] and item["remaining_usd"] <= 0 for item in budget):
        raise HTTPException(402, "MODEL_BUDGET_EXCEEDED")
    trace_id = request.headers.get("x-trace-id") or get_trace_id(request) or str(uuid4())
    errors: list[str] = []
    started = time.perf_counter()
    for route in routes:
        if _open_circuits.get(route.id, datetime.min.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc):
            errors.append(f"{route.provider}:circuit_open"); continue
        api_key = os.getenv(route.api_key_env, "")
        if not api_key:
            errors.append(f"{route.provider}:secret_missing"); continue
        upstream_payload = dict(payload); upstream_payload["model"] = route.upstream_model
        for attempt in range(route.max_retries + 1):
            try:
                response = httpx.post(f"{route.base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                             "X-Trace-ID": trace_id}, json=upstream_payload, timeout=route.timeout_seconds)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError("retryable upstream response", request=response.request, response=response)
                response.raise_for_status(); result = response.json()
                usage = result.get("usage") or {}
                input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
                cost = input_tokens * route.input_cost_per_million / 1_000_000 + output_tokens * route.output_cost_per_million / 1_000_000
                event_id = f"gateway:{trace_id}:{route.id}"
                session.add(AIUsageEventORM(workspace_id=x_workspace_id, repository_id=x_repository_id,
                    pull_request_id=x_pull_request_id, external_id=event_id, provider=route.provider,
                    model=route.upstream_model, input_tokens=input_tokens, output_tokens=output_tokens,
                    cost_usd=cost, trace_id=trace_id, source="governforge_gateway"))
                session.add(CostEventORM(workspace_id=x_workspace_id, external_id=event_id, category="model",
                    amount_usd=cost, repository_id=x_repository_id, pull_request_id=x_pull_request_id,
                    run_id=x_agent_run_id, trace_id=trace_id,
                    detail={"alias": alias, "provider": route.provider, "route_id": route.id,
                            "latency_ms": round((time.perf_counter() - started) * 1000, 1), "attempt": attempt + 1}))
                session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id,
                    actor_id=f"credential:{credential.id}", event_type="model.request.completed",
                    entity_type="model_route", entity_id=route.id, trace_id=trace_id,
                    payload={"alias": alias, "provider": route.provider, "cost_usd": round(cost, 8),
                             "degraded": route != routes[0], "content_stored": False}))
                session.commit()
                result["governance"] = {"trace_id": trace_id, "provider": route.provider,
                    "route_id": route.id, "degraded": route != routes[0], "cost_usd": round(cost, 8)}
                return result
            except (httpx.HTTPError, ValueError) as exc:
                errors.append(f"{route.provider}:{type(exc).__name__}:attempt{attempt + 1}")
                if attempt < route.max_retries:
                    time.sleep(min(2, .25 * (2 ** attempt)))
        _open_circuits[route.id] = datetime.now(timezone.utc) + timedelta(seconds=30)
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, actor_id=f"credential:{credential.id}",
        event_type="model.request.failed", entity_type="model_alias", entity_id=alias, trace_id=trace_id,
        payload={"routes_attempted": len(routes), "errors": errors[-10:], "content_stored": False}))
    session.commit()
    raise HTTPException(503, "MODEL_UPSTREAM_UNAVAILABLE")


@router.post("/cost-events", status_code=201)
def create_cost_event(data: CostIn, request: Request, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    require_workspace_role(user, "admin", "owner", "security")
    existing = session.scalar(select(CostEventORM).where(CostEventORM.workspace_id == workspace_id,
                                                         CostEventORM.external_id == data.external_id))
    if existing:
        return {"id": existing.id, "duplicate": True}
    item = CostEventORM(workspace_id=workspace_id, **data.model_dump())
    session.add(item); session.flush()
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", "unknown"),
        event_type="cost.recorded", entity_type="cost_event", entity_id=item.id,
        trace_id=data.trace_id or get_trace_id(request), payload={"category": data.category, "amount_usd": data.amount_usd,
        "minutes": data.minutes, "role": data.role}))
    session.commit()
    return {"id": item.id, "category": item.category, "amount_usd": item.amount_usd}


@router.get("/cost-events")
def cost_summary(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    require_workspace_role(user, "admin", "owner", "security")
    rows = session.execute(select(CostEventORM.category, func.sum(CostEventORM.amount_usd),
        func.sum(CostEventORM.minutes), func.count(CostEventORM.id)).where(
        CostEventORM.workspace_id == workspace_id).group_by(CostEventORM.category)).all()
    recent = session.scalars(select(CostEventORM).where(CostEventORM.workspace_id == workspace_id).order_by(
        desc(CostEventORM.occurred_at)).limit(100)).all()
    return {"total_usd": round(sum(float(row[1] or 0) for row in rows), 6),
            "categories": [{"category": row[0], "amount_usd": round(float(row[1] or 0), 6),
                            "minutes": round(float(row[2] or 0), 1), "events": row[3]} for row in rows],
            "recent": [{"id": item.id, "category": item.category, "amount_usd": item.amount_usd,
                        "minutes": item.minutes, "role": item.role, "trace_id": item.trace_id,
                        "occurred_at": item.occurred_at} for item in recent]}
