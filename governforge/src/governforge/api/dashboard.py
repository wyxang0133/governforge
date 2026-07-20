"""Executive management dashboard aggregations."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from governforge.core.agents import RISK_LABELS
from governforge.core.auth import get_current_user
from governforge.core.database import get_session
from governforge.core.workspace import get_workspace_id
from governforge.models.governance import AIUsageEventORM, AgentActionORM, AgentApprovalORM, AgentEvaluationORM, AgentRunORM, ApprovalRequestORM, PolicyEvaluationORM, PullRequestORM, RepositoryORM

router = APIRouter(tags=["dashboard"])


@router.get("/overview")
def overview(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    now = datetime.now(timezone.utc); start = now - timedelta(days=29)
    prs = list(session.scalars(select(PullRequestORM).where(PullRequestORM.workspace_id == workspace_id)))
    evaluations = list(session.scalars(select(PolicyEvaluationORM).where(PolicyEvaluationORM.workspace_id == workspace_id)))
    usage = list(session.scalars(select(AIUsageEventORM).where(AIUsageEventORM.workspace_id == workspace_id)))
    runs = list(session.scalars(select(AgentRunORM).where(AgentRunORM.workspace_id == workspace_id)))
    actions = list(session.scalars(select(AgentActionORM).where(AgentActionORM.workspace_id == workspace_id)))
    agent_evals = list(session.scalars(select(AgentEvaluationORM).where(AgentEvaluationORM.workspace_id == workspace_id)))
    pr_approvals = list(session.scalars(select(ApprovalRequestORM).where(ApprovalRequestORM.workspace_id == workspace_id)))
    agent_approvals = list(session.scalars(select(AgentApprovalORM).where(AgentApprovalORM.workspace_id == workspace_id)))
    repositories = list(session.scalars(select(RepositoryORM).where(RepositoryORM.workspace_id == workspace_id, RepositoryORM.active.is_(True))))
    cost_by_day: dict[str, float] = defaultdict(float); model_cost: dict[str, dict] = {}
    for event in usage:
        day = event.occurred_at.date().isoformat()
        if event.occurred_at >= start: cost_by_day[day] += event.cost_usd
        key = f"{event.provider}/{event.model}"; bucket = model_cost.setdefault(key, {"model": key, "calls": 0, "tokens": 0, "cost_usd": 0.0})
        bucket["calls"] += 1; bucket["tokens"] += event.input_tokens + event.output_tokens; bucket["cost_usd"] += event.cost_usd
    risk_counts: dict[str, int] = defaultdict(int)
    for action in actions:
        if action.risk_type: risk_counts[action.risk_type] += 1
    approval_minutes = []
    for item in [*pr_approvals, *agent_approvals]:
        if item.decided_at: approval_minutes.append((item.decided_at - item.created_at).total_seconds() / 60)
    blocked_prs = len({item.pull_request_id for item in evaluations if item.decision == "block" and item.pull_request_id})
    return {
        "kpis": {"repositories": len(repositories), "pull_requests": len(prs), "risk_pull_requests": len({item.pull_request_id for item in evaluations if item.decision in {"review", "block"} and item.pull_request_id}), "blocked_pull_requests": blocked_prs, "agent_runs": len(runs), "high_risk_agent_runs": sum(item.risk_level in {"high", "critical"} for item in runs), "pending_approvals": sum(item.status == "pending" for item in [*pr_approvals, *agent_approvals]), "approval_sla_minutes": round(sum(approval_minutes) / len(approval_minutes), 1) if approval_minutes else 0, "total_cost_usd": round(sum(item.cost_usd for item in usage), 4), "average_agent_score": round(sum(item.score for item in agent_evals) / len(agent_evals), 1) if agent_evals else 0},
        "cost_trend": [{"date": (start.date() + timedelta(days=index)).isoformat(), "cost_usd": round(cost_by_day.get((start.date() + timedelta(days=index)).isoformat(), 0), 4)} for index in range(30)],
        "model_distribution": sorted([{**item, "cost_usd": round(item["cost_usd"], 4)} for item in model_cost.values()], key=lambda item: item["calls"], reverse=True),
        "risk_distribution": [{"type": key, "label": RISK_LABELS.get(key, key), "count": value} for key, value in sorted(risk_counts.items(), key=lambda pair: pair[1], reverse=True)],
        "agent_status": [{"status": status, "count": sum(item.status == status for item in runs)} for status in ("running", "waiting_approval", "completed", "blocked", "failed")],
    }
