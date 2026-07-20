"""Team membership and repository grant administration."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from governforge.core.access import require_workspace_role
from governforge.core.auth import get_current_user
from governforge.core.database import get_session
from governforge.core.workspace import get_workspace_id
from governforge.models.governance import GovernanceAuditEventORM, RepositoryGrantORM, RepositoryORM, TeamMembershipORM, TeamORM
from governforge.models.user import UserORM

router = APIRouter(tags=["access"])

class TeamIn(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")

class MemberIn(BaseModel):
    username: str
    role: str = Field("member", pattern="^(member|lead)$")

class GrantIn(BaseModel):
    repository_id: str
    permission: str = Field("read", pattern="^(read|evaluate|admin)$")

def _admin(user: dict = Depends(get_current_user)) -> dict:
    require_workspace_role(user, "admin", "owner")
    return user

@router.get("/teams")
def teams(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), _: dict = Depends(_admin)) -> list[dict]:
    items = session.scalars(select(TeamORM).where(TeamORM.workspace_id == workspace_id).order_by(TeamORM.name)).all()
    return [{"id": i.id, "name": i.name, "slug": i.slug, "created_at": i.created_at} for i in items]

@router.post("/teams", status_code=201)
def create_team(data: TeamIn, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(_admin)) -> dict:
    if session.scalar(select(TeamORM.id).where(TeamORM.workspace_id == workspace_id, TeamORM.slug == data.slug)):
        raise HTTPException(409, "team slug already exists")
    item = TeamORM(workspace_id=workspace_id, **data.model_dump()); session.add(item); session.flush()
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user["sub"], event_type="access.team.created", entity_type="team", entity_id=item.id, payload={"slug": item.slug})); session.commit()
    return {"id": item.id, "name": item.name, "slug": item.slug}

@router.post("/teams/{team_id}/members", status_code=201)
def add_member(team_id: str, data: MemberIn, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(_admin)) -> dict:
    team = session.scalar(select(TeamORM).where(TeamORM.id == team_id, TeamORM.workspace_id == workspace_id)); account = session.scalar(select(UserORM).where(UserORM.username == data.username, UserORM.tenant_id == workspace_id))
    if not team or not account: raise HTTPException(404, "team or user not found")
    item = session.scalar(select(TeamMembershipORM).where(TeamMembershipORM.team_id == team.id, TeamMembershipORM.user_id == account.id)) or TeamMembershipORM(team_id=team.id, user_id=account.id)
    item.role = data.role; session.add(item); session.flush(); session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user["sub"], event_type="access.member.granted", entity_type="team_membership", entity_id=item.id, payload={"team_id": team.id, "username": account.username, "role": item.role})); session.commit()
    return {"id": item.id, "team_id": team.id, "username": account.username, "role": item.role}

@router.post("/teams/{team_id}/repositories", status_code=201)
def grant_repository(team_id: str, data: GrantIn, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(_admin)) -> dict:
    team = session.scalar(select(TeamORM).where(TeamORM.id == team_id, TeamORM.workspace_id == workspace_id)); repo = session.scalar(select(RepositoryORM).where(RepositoryORM.id == data.repository_id, RepositoryORM.workspace_id == workspace_id))
    if not team or not repo: raise HTTPException(404, "team or repository not found")
    item = session.scalar(select(RepositoryGrantORM).where(RepositoryGrantORM.team_id == team.id, RepositoryGrantORM.repository_id == repo.id)) or RepositoryGrantORM(team_id=team.id, repository_id=repo.id)
    item.permission = data.permission; session.add(item); session.flush(); session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user["sub"], event_type="access.repository.granted", entity_type="repository_grant", entity_id=item.id, payload={"team_id": team.id, "repository_id": repo.id, "permission": item.permission})); session.commit()
    return {"id": item.id, "team_id": team.id, "repository_id": repo.id, "permission": item.permission}
