"""Monthly budget allocation and consumption APIs."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from devpilot.core.access import require_workspace_role
from devpilot.core.auth import get_current_user
from devpilot.core.budgets import allocation_status, applicable_budgets, current_period, period_bounds
from devpilot.core.database import get_session
from devpilot.core.workspace import get_workspace_id
from devpilot.models.governance import BudgetAllocationORM, GovernanceAuditEventORM, RepositoryORM, TeamORM

router = APIRouter(tags=["budgets"])

class BudgetIn(BaseModel):
    scope_type: str = Field("workspace", pattern="^(workspace|team|repository)$")
    scope_id: str = "*"
    period: str = Field(default_factory=current_period, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    limit_usd: float = Field(gt=0)
    warning_ratio: float = Field(.8, gt=0, le=1)
    hard_limit: bool = True

@router.get("")
def list_budgets(period: str | None = None, repository_id: str | None = None, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict]:
    require_workspace_role(user, "admin", "owner", "security")
    try: period_bounds(period or current_period())
    except ValueError as exc: raise HTTPException(422, "period must be YYYY-MM") from exc
    if repository_id is None:
        items = session.scalars(select(BudgetAllocationORM).where(BudgetAllocationORM.workspace_id == workspace_id, BudgetAllocationORM.period == (period or current_period()))).all()
        return [allocation_status(session, item) for item in items]
    return applicable_budgets(session, workspace_id, repository_id, period)

@router.put("")
def set_budget(data: BudgetIn, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    require_workspace_role(user, "admin", "owner")
    scope_id = "*" if data.scope_type == "workspace" else data.scope_id
    model = TeamORM if data.scope_type == "team" else RepositoryORM
    if data.scope_type != "workspace" and not session.scalar(select(model.id).where(model.id == scope_id, model.workspace_id == workspace_id)): raise HTTPException(404, "budget scope not found")
    item = session.scalar(select(BudgetAllocationORM).where(BudgetAllocationORM.workspace_id == workspace_id, BudgetAllocationORM.scope_type == data.scope_type, BudgetAllocationORM.scope_id == scope_id, BudgetAllocationORM.period == data.period))
    before = None
    if item: before = {"limit_usd": item.limit_usd, "warning_ratio": item.warning_ratio, "hard_limit": item.hard_limit}
    else: item = BudgetAllocationORM(workspace_id=workspace_id, scope_type=data.scope_type, scope_id=scope_id, period=data.period, created_by=user.get("sub", "unknown")); session.add(item)
    item.limit_usd, item.warning_ratio, item.hard_limit = data.limit_usd, data.warning_ratio, data.hard_limit; session.flush()
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", "unknown"), event_type="budget.allocation.set", entity_type="budget_allocation", entity_id=item.id, payload={"before": before, "after": data.model_dump() | {"scope_id": scope_id}})); session.commit()
    return allocation_status(session, item)
