"""Non-secret operational status and controlled recovery operations."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from governforge.config import AppSettings
from governforge.core.database import get_session
from governforge.core.workspace import get_workspace_id
from governforge.models.governance import GovernanceAuditEventORM, OutboxEventORM
from governforge.core.auth import get_current_user
from governforge.core.access import require_workspace_role

router = APIRouter(tags=["system"])

@router.get("/status")
def status(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id)) -> dict:
    settings = AppSettings()
    pending = session.scalar(select(func.count()).select_from(OutboxEventORM).where(OutboxEventORM.workspace_id == workspace_id, OutboxEventORM.status == "pending")) or 0
    failed = session.scalar(select(func.count()).select_from(OutboxEventORM).where(OutboxEventORM.workspace_id == workspace_id, OutboxEventORM.status == "failed")) or 0
    return {"environment": settings.environment, "workspace_id": workspace_id, "github": {"webhook_secret_configured": bool(settings.github_webhook_secret.get_secret_value()), "checks_enabled": settings.github_checks_enabled, "checks_token_configured": bool(settings.github_checks_token.get_secret_value())}, "knowledge": {"llm_enabled": settings.knowledge_llm_enabled, "model": settings.knowledge_llm_model if settings.knowledge_llm_enabled else "extractive-rag", "api_key_configured": bool(settings.knowledge_llm_api_key.get_secret_value())}, "registration_enabled": settings.allow_self_registration, "readiness_issues": settings.production_readiness_issues(), "outbox": {"pending": pending, "failed": failed}}

@router.get("/outbox/dead-letters")
def dead_letters(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict]:
    require_workspace_role(user, "admin", "owner")
    items = session.scalars(select(OutboxEventORM).where(OutboxEventORM.workspace_id == workspace_id, OutboxEventORM.status == "failed").order_by(desc(OutboxEventORM.created_at)).limit(200)).all()
    return [{"id": i.id, "event_type": i.event_type, "aggregate_type": i.aggregate_type, "aggregate_id": i.aggregate_id, "attempts": i.attempts, "last_error": i.last_error, "created_at": i.created_at} for i in items]

@router.post("/outbox/{event_id}/requeue")
def requeue(event_id: str, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    require_workspace_role(user, "admin", "owner")
    item = session.scalar(select(OutboxEventORM).where(OutboxEventORM.id == event_id, OutboxEventORM.workspace_id == workspace_id))
    if item is None: raise HTTPException(404, "outbox event not found")
    if item.status != "failed": raise HTTPException(409, "only failed events can be requeued")
    previous = {"attempts": item.attempts, "last_error": item.last_error}
    item.status, item.attempts, item.available_at, item.processed_at, item.last_error = "pending", 0, datetime.now(timezone.utc), None, None
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", "unknown"), event_type="outbox.requeued", entity_type="outbox_event", entity_id=item.id, payload=previous)); session.commit()
    return {"id": item.id, "status": item.status}
