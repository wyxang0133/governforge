"""Governance scorecard, policy, approval and audit APIs."""
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from governforge.core.database import get_session
from governforge.core.policy_gate import PolicyEvidence, evaluate_policy
from governforge.core.scorecard import build_scorecard
from governforge.core.metrics import POLICY_DECISIONS
from governforge.core.trace_middleware import get_trace_id
from governforge.core.auth import get_current_user
from governforge.core.access import require_repository_access, require_workspace_role, visible_repository_ids
from governforge.core.budgets import applicable_budgets
from governforge.core.policies import get_effective_policy
from governforge.models.governance import AIUsageEventORM, ApprovalRequestORM, CIRunORM, GovernanceAuditEventORM, OutboxEventORM, PolicyEvaluationORM, PullRequestORM, RepositoryORM, SourceSignalORM, WorkspaceORM
from governforge.core.workspace import get_workspace_id
from governforge.core.pr_governance import evaluate_pull_request_record

def _ensure_workspace(session: Session, workspace_id: str) -> None:
    if session.get(WorkspaceORM, workspace_id) is None:
        session.add(WorkspaceORM(id=workspace_id, name=workspace_id, slug=workspace_id.lower().replace("_", "-")))
        session.flush()

router = APIRouter(tags=["governance"])


class GateRequest(BaseModel):
    pull_request_id: str | None = None
    source_confidence: float = Field(0.0, ge=0, le=1)
    ci_status: str = "unknown"
    security_status: str = "unknown"
    test_coverage: float | None = Field(None, ge=0, le=1)
    sensitive_files: list[str] = Field(default_factory=list)
    estimated_cost_usd: float = Field(0, ge=0)
    human_approved: bool = False
    monthly_budget_exceeded: bool = False
    budget_evidence: list[dict] = Field(default_factory=list)


@router.post("/policy-gate/evaluate")
def evaluate_gate(data: GateRequest, request: Request, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id)) -> dict[str, Any]:
    _ensure_workspace(session, x_workspace_id)
    repository_id = None
    if data.pull_request_id:
        policy_pr = session.scalar(select(PullRequestORM).where(PullRequestORM.id == data.pull_request_id, PullRequestORM.workspace_id == x_workspace_id))
        repository_id = policy_pr.repository_id if policy_pr else None
    policy = get_effective_policy(session, x_workspace_id, repository_id)
    evidence = data.model_dump(exclude={"pull_request_id"})
    result = evaluate_policy(PolicyEvidence(**evidence), cost_budget_usd=policy.cost_budget_usd, min_coverage=policy.min_test_coverage, min_source_confidence=policy.min_source_confidence, require_security_scan=policy.require_security_scan)
    policy_version = f"v{policy.version}"
    POLICY_DECISIONS.labels(result.decision, policy_version).inc()
    evidence["policy_chain"] = policy.policy_chain
    evaluation = PolicyEvaluationORM(workspace_id=x_workspace_id, pull_request_id=data.pull_request_id, policy_id=policy.id, policy_version=policy_version, decision=result.decision, reasons=result.reasons, checks=result.checks, evidence=evidence)
    session.add(evaluation)
    session.flush()
    approval_id = None
    if result.decision in {"review", "block"} and data.pull_request_id:
        approval = ApprovalRequestORM(workspace_id=x_workspace_id, pull_request_id=data.pull_request_id, evaluation_id=evaluation.id, required_role="security" if result.decision == "block" else "owner")
        session.add(approval)
        session.flush()
        approval_id = approval.id
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, event_type="policy.evaluated", entity_type="policy_evaluation", entity_id=evaluation.id, trace_id=get_trace_id(request), payload={"decision": result.decision, "policy_version": policy_version, "approval_id": approval_id}))
    if data.pull_request_id:
        session.add(OutboxEventORM(workspace_id=x_workspace_id, aggregate_type="pull_request", aggregate_id=data.pull_request_id, event_type="github.check.requested", payload={"evaluation_id": evaluation.id, "decision": result.decision, "checks": result.checks, "reasons": result.reasons}))
    session.commit()
    return {"evaluation_id": evaluation.id, "decision": result.decision, "reasons": result.reasons, "checks": result.checks, "approval_id": approval_id, "policy": {"id": policy.id, "version": policy.version, "name": policy.name, "chain": policy.policy_chain}}


@router.get("/scorecard")
def scorecard(session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict[str, Any]:
    require_workspace_role(user, "admin", "owner", "security")
    return {"workspace_id": x_workspace_id, "metrics": build_scorecard(session, x_workspace_id), "dimensions": ["team", "repository", "project", "task"]}


class ApprovalDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    reason: str = Field(min_length=3, max_length=2000)


class RepositoryGovernanceIn(BaseModel):
    auto_merge_enabled: bool
    merge_method: str = Field("squash", pattern="^(merge|squash|rebase)$")


@router.get("/approvals")
def list_approvals(session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict]:
    require_workspace_role(user, "admin", "owner", "security")
    items = session.scalars(select(ApprovalRequestORM).where(ApprovalRequestORM.workspace_id == x_workspace_id).order_by(desc(ApprovalRequestORM.created_at))).all()
    return [{"id": item.id, "pull_request_id": item.pull_request_id, "evaluation_id": item.evaluation_id, "status": item.status, "required_role": item.required_role, "decided_by": item.decided_by, "reason": item.reason, "created_at": item.created_at} for item in items]


@router.post("/approvals/{approval_id}/decision")
def decide_approval(approval_id: str, data: ApprovalDecision, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in {"owner", "security", "admin"}:
        raise HTTPException(403, "insufficient role for approval")
    item = session.scalar(select(ApprovalRequestORM).where(ApprovalRequestORM.id == approval_id, ApprovalRequestORM.workspace_id == x_workspace_id))
    if item is None:
        raise HTTPException(404, "approval not found")
    if item.status != "pending":
        raise HTTPException(409, "approval already decided")
    allowed_roles = {"admin", item.required_role}
    if user.get("role") not in allowed_roles:
        raise HTTPException(403, f"{item.required_role} role required")
    actor_id = user.get("sub", "unknown")
    item.status, item.decided_by, item.reason = data.decision, actor_id, data.reason
    item.decided_at = datetime.now(timezone.utc)
    effective_decision = "allow" if data.decision == "approved" else "block"
    pr = session.get(PullRequestORM, item.pull_request_id)
    repo = session.get(RepositoryORM, pr.repository_id) if pr else None
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, actor_id=actor_id, event_type=f"approval.{data.decision}", entity_type="approval", entity_id=item.id, payload={"reason": data.reason, "evaluation_id": item.evaluation_id, "effective_decision": effective_decision}))
    session.add(OutboxEventORM(workspace_id=x_workspace_id, aggregate_type="pull_request", aggregate_id=item.pull_request_id,
        event_type="github.check.requested", dedupe_key=f"check:{item.pull_request_id}:{pr.head_sha if pr else 'unknown'}:approval:{item.id}",
        payload={"evaluation_id": item.evaluation_id, "approval_id": item.id, "decision": effective_decision,
                 "reason": data.reason, "head_sha": pr.head_sha if pr else None}))
    if data.decision == "approved" and pr and repo and repo.auto_merge_enabled:
        session.add(OutboxEventORM(workspace_id=x_workspace_id, aggregate_type="pull_request", aggregate_id=pr.id,
            event_type="github.merge.requested", dedupe_key=f"merge:{pr.id}:{pr.head_sha}:approval:{item.id}",
            payload={"evaluation_id": item.evaluation_id, "approval_id": item.id, "head_sha": pr.head_sha,
                     "merge_method": repo.merge_method}))
    session.commit()
    return {"id": item.id, "status": item.status, "effective_decision": effective_decision}


@router.get("/audit")
def list_audit(limit: int = Query(100, ge=1, le=500), session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict]:
    require_workspace_role(user, "admin", "owner", "security")
    items = session.scalars(select(GovernanceAuditEventORM).where(GovernanceAuditEventORM.workspace_id == x_workspace_id).order_by(desc(GovernanceAuditEventORM.created_at)).limit(limit)).all()
    return [{"id": item.id, "actor_id": item.actor_id, "event_type": item.event_type, "entity_type": item.entity_type, "entity_id": item.entity_id, "trace_id": item.trace_id, "payload": item.payload, "created_at": item.created_at} for item in items]


@router.get("/pull-requests")
def list_pull_requests(session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict]:
    latest_decision = (
        select(PolicyEvaluationORM.decision)
        .where(PolicyEvaluationORM.pull_request_id == PullRequestORM.id)
        .order_by(desc(PolicyEvaluationORM.created_at))
        .limit(1)
        .correlate(PullRequestORM)
        .scalar_subquery()
    )
    query = (
        select(PullRequestORM, RepositoryORM.full_name, latest_decision.label("decision"))
        .outerjoin(RepositoryORM, RepositoryORM.id == PullRequestORM.repository_id)
        .where(PullRequestORM.workspace_id == x_workspace_id)
    )
    scope = visible_repository_ids(session, x_workspace_id, user)
    if scope is not None: query = query.where(PullRequestORM.repository_id.in_(scope))
    rows = session.execute(query.order_by(desc(PullRequestORM.updated_at)).limit(200)).all()
    return [
        {
            "id": item.id,
            "repository_id": item.repository_id,
            "repository": repository_name,
            "number": item.external_number,
            "title": item.title,
            "author": item.author,
            "state": item.state,
            "head_sha": item.head_sha,
            "source_confidence": item.source_confidence,
            "changed_files": item.changed_files,
            "decision": decision,
            "risk_level": {"block": "critical", "review": "high", "allow": "low"}.get(decision),
            "updated_at": item.updated_at,
        }
        for item, repository_name, decision in rows
    ]


@router.get("/repositories")
def list_repositories(session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict]:
    query = select(RepositoryORM).where(RepositoryORM.workspace_id == x_workspace_id)
    scope = visible_repository_ids(session, x_workspace_id, user)
    if scope is not None: query = query.where(RepositoryORM.id.in_(scope))
    items = session.scalars(query.order_by(RepositoryORM.full_name)).all()
    return [{"id": item.id, "provider": item.provider, "external_id": item.external_id, "full_name": item.full_name, "default_branch": item.default_branch, "installation_id": item.installation_id, "html_url": item.html_url, "active": item.active, "auto_merge_enabled": item.auto_merge_enabled, "merge_method": item.merge_method, "created_at": item.created_at} for item in items]


@router.patch("/repositories/{repository_id}/governance")
def update_repository_governance(repository_id: str, data: RepositoryGovernanceIn, request: Request,
    session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id),
    user: dict = Depends(get_current_user)) -> dict:
    require_workspace_role(user, "admin", "owner")
    item = session.scalar(select(RepositoryORM).where(RepositoryORM.id == repository_id,
        RepositoryORM.workspace_id == x_workspace_id))
    if item is None: raise HTTPException(404, "repository not found")
    before = {"auto_merge_enabled": item.auto_merge_enabled, "merge_method": item.merge_method}
    item.auto_merge_enabled, item.merge_method = data.auto_merge_enabled, data.merge_method
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, actor_id=user.get("sub", "unknown"),
        event_type="repository.governance.updated", entity_type="repository", entity_id=item.id,
        trace_id=get_trace_id(request), payload={"before": before, "after": data.model_dump()}))
    session.commit()
    return {"id": item.id, "auto_merge_enabled": item.auto_merge_enabled, "merge_method": item.merge_method}


@router.get("/pull-requests/{pull_request_id}")
def pull_request_detail(pull_request_id: str, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    pr = session.scalar(select(PullRequestORM).where(PullRequestORM.id == pull_request_id, PullRequestORM.workspace_id == x_workspace_id))
    if pr is None: raise HTTPException(404, "pull request not found")
    require_repository_access(session, x_workspace_id, user, pr.repository_id)
    repo = session.get(RepositoryORM, pr.repository_id)
    runs = session.scalars(select(CIRunORM).where(CIRunORM.pull_request_id == pr.id).order_by(CIRunORM.started_at)).all()
    usage = session.scalars(select(AIUsageEventORM).where(AIUsageEventORM.pull_request_id == pr.id).order_by(AIUsageEventORM.occurred_at)).all()
    signals = session.scalars(select(SourceSignalORM).where(SourceSignalORM.pull_request_id == pr.id).order_by(SourceSignalORM.created_at)).all()
    evaluations = session.scalars(select(PolicyEvaluationORM).where(PolicyEvaluationORM.pull_request_id == pr.id).order_by(desc(PolicyEvaluationORM.created_at))).all()
    approvals = session.scalars(select(ApprovalRequestORM).where(ApprovalRequestORM.pull_request_id == pr.id).order_by(desc(ApprovalRequestORM.created_at))).all()
    return {"id": pr.id, "number": pr.external_number, "title": pr.title, "author": pr.author, "state": pr.state, "head_sha": pr.head_sha, "source_confidence": pr.source_confidence, "changes": {"additions": pr.additions, "deletions": pr.deletions, "files": pr.changed_files}, "repository": {"id": repo.id, "full_name": repo.full_name, "html_url": repo.html_url} if repo else None, "ci_runs": [{"id": r.id, "name": r.name, "status": r.status, "conclusion": r.conclusion, "attempt": r.attempt, "coverage": r.coverage} for r in runs], "usage": [{"id": u.id, "provider": u.provider, "model": u.model, "tokens": u.input_tokens + u.output_tokens, "cost_usd": u.cost_usd, "trace_id": u.trace_id} for u in usage], "source_signals": [{"id": s.id, "type": s.signal_type, "confidence": s.confidence, "evidence_ref": s.evidence_ref} for s in signals], "evaluations": [{"id": e.id, "policy_version": e.policy_version, "decision": e.decision, "reasons": e.reasons, "checks": e.checks, "created_at": e.created_at} for e in evaluations], "approvals": [{"id": a.id, "status": a.status, "required_role": a.required_role, "decided_by": a.decided_by, "reason": a.reason} for a in approvals]}


@router.get("/usage")
def list_usage(session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict]:
    query = select(AIUsageEventORM).where(AIUsageEventORM.workspace_id == x_workspace_id)
    scope = visible_repository_ids(session, x_workspace_id, user)
    if scope is not None: query = query.where(AIUsageEventORM.repository_id.in_(scope))
    items = session.scalars(query.order_by(desc(AIUsageEventORM.occurred_at)).limit(200)).all()
    return [{"id": item.id, "provider": item.provider, "model": item.model, "input_tokens": item.input_tokens, "output_tokens": item.output_tokens, "cost_usd": item.cost_usd, "trace_id": item.trace_id, "source": item.source, "occurred_at": item.occurred_at} for item in items]


@router.post("/pull-requests/{pull_request_id}/evaluate")
def evaluate_pull_request(pull_request_id: str, request: Request, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    pr = session.scalar(select(PullRequestORM).where(PullRequestORM.id == pull_request_id, PullRequestORM.workspace_id == x_workspace_id))
    if pr is None:
        raise HTTPException(404, "pull request not found")
    require_repository_access(session, x_workspace_id, user, pr.repository_id)
    result = evaluate_pull_request_record(session, x_workspace_id, pr, get_trace_id(request))
    session.commit()
    return result
