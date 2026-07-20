"""Calendar-month budget accounting across workspace, team and repository scopes."""
from datetime import datetime, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from governforge.models.governance import AIUsageEventORM, BudgetAllocationORM, RepositoryGrantORM

def current_period() -> str: return datetime.now(timezone.utc).strftime("%Y-%m")

def period_bounds(period: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(period, "%Y-%m").replace(tzinfo=timezone.utc)
    end = datetime(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1, tzinfo=timezone.utc)
    return start, end

def applicable_budgets(session: Session, workspace_id: str, repository_id: str | None, period: str | None = None) -> list[dict]:
    period = period or current_period(); start, end = period_bounds(period)
    allocations = list(session.scalars(select(BudgetAllocationORM).where(BudgetAllocationORM.workspace_id == workspace_id, BudgetAllocationORM.period == period)))
    team_ids = set(session.scalars(select(RepositoryGrantORM.team_id).where(RepositoryGrantORM.repository_id == repository_id))) if repository_id else set()
    applicable = [a for a in allocations if a.scope_type == "workspace" or (a.scope_type == "repository" and a.scope_id == repository_id) or (a.scope_type == "team" and a.scope_id in team_ids)]
    return [allocation_status(session, item) for item in applicable]

def allocation_status(session: Session, item: BudgetAllocationORM) -> dict:
    start, end = period_bounds(item.period)
    query = select(func.coalesce(func.sum(AIUsageEventORM.cost_usd), 0.0)).where(AIUsageEventORM.workspace_id == item.workspace_id, AIUsageEventORM.occurred_at >= start, AIUsageEventORM.occurred_at < end)
    if item.scope_type == "repository": query = query.where(AIUsageEventORM.repository_id == item.scope_id)
    elif item.scope_type == "team":
        repo_ids = select(RepositoryGrantORM.repository_id).where(RepositoryGrantORM.team_id == item.scope_id)
        query = query.where(AIUsageEventORM.repository_id.in_(repo_ids))
    spent = float(session.scalar(query) or 0); ratio = spent / item.limit_usd if item.limit_usd else (1.0 if spent else 0.0)
    return {"id": item.id, "scope_type": item.scope_type, "scope_id": item.scope_id, "period": item.period, "limit_usd": item.limit_usd, "spent_usd": round(spent, 6), "remaining_usd": round(max(0, item.limit_usd - spent), 6), "usage_ratio": round(ratio, 4), "warning": ratio >= item.warning_ratio, "exceeded": spent > item.limit_usd, "hard_limit": item.hard_limit}
