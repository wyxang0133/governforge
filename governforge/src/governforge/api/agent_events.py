"""Versioned machine-to-machine event contract for coding-agent hooks."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from governforge.core.agents import RISK_LABELS, classify_action, evaluate_run, max_level
from governforge.core.database import get_session
from governforge.core.trace_middleware import get_trace_id
from governforge.models.governance import (
    AgentActionORM, AgentApprovalORM, AgentEvaluationORM, AgentRunORM,
    GovernanceAuditEventORM, IntegrationCredentialORM, WorkspaceORM,
)

router = APIRouter(tags=["agent-events"])


class AgentEventV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    event_id: str = Field(min_length=4, max_length=128)
    event_type: Literal["run.started", "run.heartbeat", "action.pre", "action.completed", "run.completed"]
    run_external_id: str = Field(min_length=2, max_length=128)
    provider: str = Field(min_length=2, max_length=64)
    agent_name: str = Field(min_length=2, max_length=128)
    requested_by: str = Field("developer", max_length=128)
    task: str | None = Field(None, max_length=10000)
    plan: list[str] = Field(default_factory=list, max_length=100)
    repository_id: str | None = None
    pull_request_id: str | None = None
    sequence: int | None = Field(None, ge=1)
    action_type: str | None = Field(None, pattern="^(plan|file_read|file_write|file_delete|command|tool_call|dependency|test|pull_request)$")
    target: str | None = Field(None, max_length=1024)
    command: str | None = Field(None, max_length=10000)
    detail: dict = Field(default_factory=dict)
    outcome: Literal["completed", "failed", "cancelled"] | None = None
    timeout_seconds: int = Field(900, ge=30, le=86400)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trace_id: str | None = Field(None, max_length=128)


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _authenticate_machine(session: Session, token: str, workspace_id: str) -> IntegrationCredentialORM:
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
    if item is None or (expires_at and expires_at <= now) or "agent:write" not in (item.scopes or []):
        raise HTTPException(401, "invalid, expired or insufficient agent credential")
    item.last_used_at = now
    return item


def _workspace(session: Session, workspace_id: str) -> None:
    if session.get(WorkspaceORM, workspace_id) is None:
        session.add(WorkspaceORM(id=workspace_id, name=workspace_id, slug=workspace_id.lower().replace("_", "-")[:64]))
        session.flush()


@router.get("/v1/approvals/{approval_id}")
def machine_approval_status(
    approval_id: str,
    session: Session = Depends(get_session),
    x_agent_token: str = Header(...),
    x_workspace_id: str = Header(...),
) -> dict:
    _authenticate_machine(session, x_agent_token, x_workspace_id)
    item = session.scalar(select(AgentApprovalORM).where(
        AgentApprovalORM.id == approval_id,
        AgentApprovalORM.workspace_id == x_workspace_id,
    ))
    if item is None:
        raise HTTPException(404, "approval not found")
    session.commit()
    return {"id": item.id, "status": item.status, "reason": item.reason,
            "decided_by": item.decided_by, "decided_at": item.decided_at}


@router.post("/v1/events", status_code=202)
def ingest_agent_event(
    data: AgentEventV1,
    request: Request,
    session: Session = Depends(get_session),
    x_agent_token: str = Header(...),
    x_workspace_id: str = Header(...),
) -> dict:
    credential = _authenticate_machine(session, x_agent_token, x_workspace_id)
    _workspace(session, x_workspace_id)
    run = session.scalar(select(AgentRunORM).where(
        AgentRunORM.workspace_id == x_workspace_id,
        AgentRunORM.external_id == data.run_external_id,
    ))
    event_hash = _hash(data.model_dump(mode="json", exclude={"occurred_at", "event_id"}))
    if data.event_type == "run.started":
        if run:
            if run.payload_hash and run.payload_hash != event_hash:
                raise HTTPException(409, "EVIDENCE_CONFLICT: run idempotency key has a different payload")
            return {"status": "duplicate", "run_id": run.id, "run_status": run.status}
        if not data.task:
            raise HTTPException(422, "task is required for run.started")
        run = AgentRunORM(
            workspace_id=x_workspace_id, external_id=data.run_external_id, schema_version=data.schema_version,
            payload_hash=event_hash, provider=data.provider, agent_name=data.agent_name, task=data.task,
            plan=data.plan, repository_id=data.repository_id, pull_request_id=data.pull_request_id,
            requested_by=data.requested_by, trace_id=data.trace_id or get_trace_id(request),
            heartbeat_at=data.occurred_at, timeout_seconds=data.timeout_seconds,
        )
        session.add(run); session.flush()
        result = {"status": "accepted", "run_id": run.id, "run_status": run.status, "decision": "allow"}
    else:
        if run is None:
            raise HTTPException(409, "run.started must be accepted before subsequent events")
        previous_heartbeat = run.heartbeat_at or data.occurred_at
        if previous_heartbeat.tzinfo is None:
            previous_heartbeat = previous_heartbeat.replace(tzinfo=timezone.utc)
        run.heartbeat_at = max(previous_heartbeat, data.occurred_at)
        if data.event_type == "run.heartbeat":
            result = {"status": "accepted", "run_id": run.id, "run_status": run.status}
        elif data.event_type in {"action.pre", "action.completed"}:
            if data.sequence is None or data.action_type is None:
                raise HTTPException(422, "sequence and action_type are required for action events")
            action = session.scalar(select(AgentActionORM).where(
                AgentActionORM.run_id == run.id, AgentActionORM.sequence == data.sequence,
            ))
            action_payload = data.model_dump(mode="json", include={"sequence", "action_type", "target", "command", "detail"})
            action_hash = _hash(action_payload)
            if action and data.event_type == "action.pre":
                if action.payload_hash and action.payload_hash != action_hash:
                    raise HTTPException(409, "EVIDENCE_CONFLICT: action sequence has a different payload")
                result = {"status": "duplicate", "run_id": run.id, "action_id": action.id,
                          "decision": "ask" if action.requires_approval and action.status == "waiting_approval" else
                                      ("deny" if action.status == "rejected" else "allow")}
            else:
                risk = classify_action(data.action_type, data.target, data.command, data.detail)
                if action is None:
                    action = AgentActionORM(
                        workspace_id=x_workspace_id, run_id=run.id, sequence=data.sequence,
                        schema_version=data.schema_version, payload_hash=action_hash, action_type=data.action_type,
                        target=data.target, command=data.command, detail=data.detail,
                        risk_type=risk.risk_type, risk_level=risk.level, requires_approval=risk.requires_approval,
                        status="waiting_approval" if data.event_type == "action.pre" and risk.requires_approval else "completed",
                        occurred_at=data.occurred_at,
                    )
                    session.add(action); session.flush()
                elif data.event_type == "action.completed":
                    if action.status in {"waiting_approval", "rejected"}:
                        raise HTTPException(409, "action was not approved for execution")
                    action.status = "failed" if data.detail.get("failed") else "completed"
                    action.detail = {**(action.detail or {}), **data.detail}
                approval = None
                if data.event_type == "action.pre" and risk.requires_approval and action.status == "waiting_approval":
                    approval = session.scalar(select(AgentApprovalORM).where(AgentApprovalORM.action_id == action.id))
                    if approval is None:
                        approval = AgentApprovalORM(
                            workspace_id=x_workspace_id, run_id=run.id, action_id=action.id,
                            requested_by=data.requested_by,
                            required_role="security" if risk.level == "critical" else "owner",
                        )
                        session.add(approval); session.flush()
                    run.status = "waiting_approval"
                run.risk_level = max_level(run.risk_level, risk.level)
                result = {"status": "accepted", "run_id": run.id, "action_id": action.id,
                          "decision": "ask" if approval else "allow", "approval_id": approval.id if approval else None,
                          "risk_type": risk.risk_type, "risk_label": RISK_LABELS.get(risk.risk_type or ""),
                          "risk_level": risk.level, "reason": risk.reason}
        else:
            pending = session.scalar(select(func.count(AgentApprovalORM.id)).where(
                AgentApprovalORM.run_id == run.id, AgentApprovalORM.status == "pending",
            )) or 0
            if pending:
                raise HTTPException(409, "pending high-risk approvals prevent run completion")
            actions = list(session.scalars(select(AgentActionORM).where(AgentActionORM.run_id == run.id).order_by(AgentActionORM.sequence)))
            score, decision, findings, metrics = evaluate_run(actions)
            evaluation = session.scalar(select(AgentEvaluationORM).where(AgentEvaluationORM.run_id == run.id))
            if evaluation is None:
                evaluation = AgentEvaluationORM(workspace_id=x_workspace_id, run_id=run.id, score=score, decision=decision)
                session.add(evaluation)
            evaluation.score, evaluation.decision, evaluation.findings, evaluation.metrics = score, decision, findings, metrics
            run.status = "blocked" if decision == "block" else (data.outcome or "completed")
            run.completed_at = data.occurred_at
            run.last_error = data.detail.get("error") if data.outcome == "failed" else None
            result = {"status": "accepted", "run_id": run.id, "run_status": run.status,
                      "decision": decision, "score": score, "findings": findings, "metrics": metrics}
    session.add(GovernanceAuditEventORM(
        workspace_id=x_workspace_id, actor_id=f"credential:{credential.id}",
        event_type=f"agent.event.{data.event_type}", entity_type="agent_run",
        entity_id=run.id, trace_id=data.trace_id or run.trace_id or get_trace_id(request),
        payload={"event_id": data.event_id, "schema_version": data.schema_version,
                 "provider": data.provider, "decision": result.get("decision")},
    ))
    session.commit()
    return result
