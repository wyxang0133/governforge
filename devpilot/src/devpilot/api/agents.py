"""Agent behavior ingestion, pre-action approval, evaluation and analytics APIs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from devpilot.core.access import require_workspace_role
from devpilot.core.agents import RISK_LABELS, classify_action, evaluate_run, max_level
from devpilot.core.auth import get_current_user
from devpilot.core.database import get_session
from devpilot.core.trace_middleware import get_trace_id
from devpilot.core.workspace import get_workspace_id
from devpilot.models.governance import AgentActionORM, AgentApprovalORM, AgentEvaluationORM, AgentRunORM, GovernanceAuditEventORM, RepositoryORM, WorkspaceORM

router = APIRouter(tags=["agents"])


def _workspace(session: Session, workspace_id: str):
    if session.get(WorkspaceORM, workspace_id) is None:
        session.add(WorkspaceORM(id=workspace_id, name=workspace_id, slug=workspace_id.lower().replace("_", "-")[:64])); session.flush()


class RunCreate(BaseModel):
    external_id: str = Field(min_length=2, max_length=128)
    provider: str = Field(min_length=2, max_length=64)
    agent_name: str = Field(min_length=2, max_length=128)
    task: str = Field(min_length=3, max_length=10000)
    plan: list[str] = Field(default_factory=list, max_length=100)
    repository_id: str | None = None
    pull_request_id: str | None = None
    requested_by: str = Field("developer", max_length=128)
    trace_id: str | None = Field(None, max_length=128)


class ActionCreate(BaseModel):
    sequence: int = Field(ge=1)
    action_type: str = Field(pattern="^(plan|file_read|file_write|file_delete|command|tool_call|dependency|test|pull_request)$")
    target: str | None = Field(None, max_length=1024)
    command: str | None = Field(None, max_length=10000)
    detail: dict = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    reason: str = Field(min_length=2, max_length=2000)


class CompleteRun(BaseModel):
    status: str = Field("completed", pattern="^(completed|failed|cancelled)$")


def _run(session: Session, run_id: str, workspace_id: str) -> AgentRunORM:
    item = session.scalar(select(AgentRunORM).where(AgentRunORM.id == run_id, AgentRunORM.workspace_id == workspace_id))
    if item is None: raise HTTPException(404, "Agent 任务不存在")
    return item


@router.post("/runs", status_code=201)
def create_run(data: RunCreate, request: Request, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    _workspace(session, workspace_id)
    existing = session.scalar(select(AgentRunORM).where(AgentRunORM.workspace_id == workspace_id, AgentRunORM.external_id == data.external_id))
    if existing: return {"id": existing.id, "status": existing.status, "duplicate": True}
    if data.repository_id and session.scalar(select(RepositoryORM.id).where(RepositoryORM.id == data.repository_id, RepositoryORM.workspace_id == workspace_id)) is None:
        raise HTTPException(404, "代码仓库不存在")
    item = AgentRunORM(workspace_id=workspace_id, **data.model_dump())
    session.add(item); session.flush()
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", data.requested_by), event_type="agent.run.started", entity_type="agent_run", entity_id=item.id, trace_id=data.trace_id or get_trace_id(request), payload={"provider": item.provider, "agent_name": item.agent_name, "task": item.task[:200]}))
    session.commit()
    return {"id": item.id, "status": item.status, "risk_level": item.risk_level}


@router.post("/runs/{run_id}/actions", status_code=201)
def add_action(run_id: str, data: ActionCreate, request: Request, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    run = _run(session, run_id, workspace_id)
    existing = session.scalar(select(AgentActionORM).where(AgentActionORM.run_id == run.id, AgentActionORM.sequence == data.sequence))
    if existing: return {"id": existing.id, "status": existing.status, "duplicate": True}
    risk = classify_action(data.action_type, data.target, data.command, data.detail)
    action = AgentActionORM(workspace_id=workspace_id, run_id=run.id, **data.model_dump(), risk_type=risk.risk_type, risk_level=risk.level, requires_approval=risk.requires_approval, status="waiting_approval" if risk.requires_approval else "completed")
    session.add(action); session.flush()
    approval = None
    if risk.requires_approval:
        run.status = "waiting_approval"
        approval = AgentApprovalORM(workspace_id=workspace_id, run_id=run.id, action_id=action.id, requested_by=user.get("sub", run.requested_by), required_role="security" if risk.level == "critical" else "owner")
        session.add(approval); session.flush()
    run.risk_level = max_level(run.risk_level, risk.level)
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", run.requested_by), event_type="agent.action.received", entity_type="agent_action", entity_id=action.id, trace_id=run.trace_id or get_trace_id(request), payload={"type": action.action_type, "target": action.target, "risk_type": risk.risk_type, "risk_level": risk.level, "requires_approval": risk.requires_approval}))
    session.commit()
    return {"id": action.id, "status": action.status, "risk_type": risk.risk_type, "risk_label": RISK_LABELS.get(risk.risk_type or ""), "risk_level": risk.level, "requires_approval": risk.requires_approval, "approval_id": approval.id if approval else None, "reason": risk.reason}


@router.post("/approvals/{approval_id}/decision")
def decide_approval(approval_id: str, data: ApprovalDecision, request: Request, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    approval = session.scalar(select(AgentApprovalORM).where(AgentApprovalORM.id == approval_id, AgentApprovalORM.workspace_id == workspace_id))
    if approval is None: raise HTTPException(404, "Agent 操作审批不存在")
    require_workspace_role(user, "admin", "owner", "security")
    if approval.status != "pending": raise HTTPException(409, "该审批已经处理")
    approval.status, approval.decided_by, approval.reason, approval.decided_at = data.decision, user.get("sub", "unknown"), data.reason, datetime.now(timezone.utc)
    action = session.get(AgentActionORM, approval.action_id); run = session.get(AgentRunORM, approval.run_id)
    action.status = "completed" if data.decision == "approved" else "rejected"
    pending = session.scalar(select(func.count(AgentApprovalORM.id)).where(AgentApprovalORM.run_id == run.id, AgentApprovalORM.status == "pending", AgentApprovalORM.id != approval.id)) or 0
    run.status = "running" if data.decision == "approved" and pending == 0 else ("blocked" if data.decision == "rejected" else run.status)
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", "unknown"), event_type=f"agent.approval.{data.decision}", entity_type="agent_approval", entity_id=approval.id, trace_id=run.trace_id or get_trace_id(request), payload={"run_id": run.id, "action_id": action.id, "reason": data.reason}))
    session.commit()
    return {"id": approval.id, "status": approval.status, "run_status": run.status, "action_status": action.status}


@router.post("/runs/{run_id}/complete")
def complete_run(run_id: str, data: CompleteRun, request: Request, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    run = _run(session, run_id, workspace_id)
    if session.scalar(select(func.count(AgentApprovalORM.id)).where(AgentApprovalORM.run_id == run.id, AgentApprovalORM.status == "pending")):
        raise HTTPException(409, "仍有待处理的高风险操作审批")
    actions = list(session.scalars(select(AgentActionORM).where(AgentActionORM.run_id == run.id).order_by(AgentActionORM.sequence)))
    score, decision, findings, metrics = evaluate_run(actions)
    evaluation = session.scalar(select(AgentEvaluationORM).where(AgentEvaluationORM.run_id == run.id)) or AgentEvaluationORM(workspace_id=workspace_id, run_id=run.id, score=score, decision=decision)
    evaluation.score, evaluation.decision, evaluation.findings, evaluation.metrics = score, decision, findings, metrics
    session.add(evaluation)
    run.status, run.completed_at = ("blocked" if decision == "block" else data.status), datetime.now(timezone.utc)
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", run.requested_by), event_type="agent.run.evaluated", entity_type="agent_run", entity_id=run.id, trace_id=run.trace_id or get_trace_id(request), payload={"score": score, "decision": decision, "findings": len(findings)}))
    session.commit()
    return {"run_id": run.id, "status": run.status, "score": score, "decision": decision, "findings": findings, "metrics": metrics}


@router.get("/runs")
def list_runs(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict]:
    rows = session.execute(select(AgentRunORM, AgentEvaluationORM).outerjoin(AgentEvaluationORM, AgentEvaluationORM.run_id == AgentRunORM.id).where(AgentRunORM.workspace_id == workspace_id).order_by(desc(AgentRunORM.started_at)).limit(200)).all()
    return [{"id": run.id, "external_id": run.external_id, "provider": run.provider, "agent_name": run.agent_name, "task": run.task, "status": run.status, "risk_level": run.risk_level, "requested_by": run.requested_by, "started_at": run.started_at, "completed_at": run.completed_at, "score": evaluation.score if evaluation else None, "decision": evaluation.decision if evaluation else None} for run, evaluation in rows]


@router.get("/runs/{run_id}")
def run_detail(run_id: str, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict[str, Any]:
    run = _run(session, run_id, workspace_id)
    actions = session.scalars(select(AgentActionORM).where(AgentActionORM.run_id == run.id).order_by(AgentActionORM.sequence)).all()
    approvals = session.scalars(select(AgentApprovalORM).where(AgentApprovalORM.run_id == run.id).order_by(AgentApprovalORM.created_at)).all()
    evaluation = session.scalar(select(AgentEvaluationORM).where(AgentEvaluationORM.run_id == run.id))
    return {"id": run.id, "external_id": run.external_id, "provider": run.provider, "agent_name": run.agent_name, "task": run.task, "plan": run.plan, "status": run.status, "risk_level": run.risk_level, "requested_by": run.requested_by, "trace_id": run.trace_id, "started_at": run.started_at, "completed_at": run.completed_at, "actions": [{"id": a.id, "sequence": a.sequence, "action_type": a.action_type, "target": a.target, "command": a.command, "status": a.status, "risk_type": a.risk_type, "risk_label": RISK_LABELS.get(a.risk_type or ""), "risk_level": a.risk_level, "requires_approval": a.requires_approval, "detail": a.detail, "occurred_at": a.occurred_at} for a in actions], "approvals": [{"id": a.id, "action_id": a.action_id, "status": a.status, "required_role": a.required_role, "decided_by": a.decided_by, "reason": a.reason, "created_at": a.created_at} for a in approvals], "evaluation": {"score": evaluation.score, "decision": evaluation.decision, "findings": evaluation.findings, "metrics": evaluation.metrics} if evaluation else None}


@router.get("/approvals")
def list_approvals(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict]:
    require_workspace_role(user, "admin", "owner", "security")
    rows = session.execute(select(AgentApprovalORM, AgentRunORM, AgentActionORM).join(AgentRunORM, AgentApprovalORM.run_id == AgentRunORM.id).join(AgentActionORM, AgentApprovalORM.action_id == AgentActionORM.id).where(AgentApprovalORM.workspace_id == workspace_id).order_by(desc(AgentApprovalORM.created_at)).limit(200)).all()
    return [{"id": item.id, "status": item.status, "required_role": item.required_role, "created_at": item.created_at, "run_id": run.id, "task": run.task, "agent_name": run.agent_name, "action_type": action.action_type, "target": action.target, "risk_type": action.risk_type, "risk_label": RISK_LABELS.get(action.risk_type or ""), "risk_level": action.risk_level} for item, run, action in rows]


@router.get("/analytics")
def analytics(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    runs = list(session.scalars(select(AgentRunORM).where(AgentRunORM.workspace_id == workspace_id)))
    actions = list(session.scalars(select(AgentActionORM).where(AgentActionORM.workspace_id == workspace_id)))
    approvals = list(session.scalars(select(AgentApprovalORM).where(AgentApprovalORM.workspace_id == workspace_id)))
    evaluations = list(session.scalars(select(AgentEvaluationORM).where(AgentEvaluationORM.workspace_id == workspace_id)))
    providers: dict[str, int] = {}; risks: dict[str, int] = {}
    for run in runs: providers[run.provider] = providers.get(run.provider, 0) + 1
    for action in actions:
        if action.risk_type: risks[action.risk_type] = risks.get(action.risk_type, 0) + 1
    decided = [item for item in approvals if item.decided_at]
    sla = sum((item.decided_at - item.created_at).total_seconds() for item in decided) / len(decided) / 60 if decided else 0
    return {"runs": len(runs), "running": sum(item.status in {"running", "waiting_approval"} for item in runs), "high_risk_runs": sum(item.risk_level in {"high", "critical"} for item in runs), "blocked_runs": sum(item.status == "blocked" for item in runs), "actions": len(actions), "pending_approvals": sum(item.status == "pending" for item in approvals), "approval_sla_minutes": round(sla, 1), "average_score": round(sum(item.score for item in evaluations) / len(evaluations), 1) if evaluations else 0, "test_execution_rate": round(sum(bool((item.metrics or {}).get("tests_executed")) for item in evaluations) / len(evaluations), 3) if evaluations else 0, "providers": providers, "risks": [{"type": key, "label": RISK_LABELS.get(key, key), "count": value} for key, value in sorted(risks.items(), key=lambda pair: pair[1], reverse=True)]}


@router.post("/demo", status_code=201)
def seed_demo(request: Request, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    require_workspace_role(user, "admin", "owner")
    _workspace(session, workspace_id)
    external_id = f"demo-agent-{uuid4()}"
    run = AgentRunORM(workspace_id=workspace_id, external_id=external_id, provider="codex", agent_name="Codex", task="升级认证模块并新增用户会话审计", plan=["分析认证模块", "修改会话逻辑", "执行测试", "创建 PR"], requested_by=user.get("sub", "demo"), trace_id=get_trace_id(request))
    session.add(run); session.flush()
    demo = [(1,"plan","认证升级方案",None,{}),(2,"file_read","src/auth/session.py",None,{}),(3,"file_write","migrations/0011_auth_session.sql",None,{}),(4,"test","tests/test_auth.py",None,{"conclusion":"passed"})]
    approval = None
    for sequence, kind, target, command, detail in demo:
        risk = classify_action(kind, target, command, detail); action = AgentActionORM(workspace_id=workspace_id, run_id=run.id, sequence=sequence, action_type=kind, target=target, command=command, detail=detail, risk_type=risk.risk_type, risk_level=risk.level, requires_approval=risk.requires_approval, status="waiting_approval" if risk.requires_approval else "completed")
        session.add(action); session.flush(); run.risk_level = max_level(run.risk_level, risk.level)
        if risk.requires_approval: approval = AgentApprovalORM(workspace_id=workspace_id, run_id=run.id, action_id=action.id, required_role="owner", requested_by=user.get("sub", "demo")); session.add(approval); run.status="waiting_approval"
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", "demo"), event_type="agent.demo.created", entity_type="agent_run", entity_id=run.id, trace_id=get_trace_id(request), payload={"provider":"codex"}))
    session.commit()
    return {"run_id": run.id, "approval_id": approval.id if approval else None, "status": run.status}
