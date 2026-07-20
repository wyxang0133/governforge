"""Workspace roles and repository-scoped authorization."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from governforge.models.governance import RepositoryGrantORM, TeamMembershipORM
from governforge.models.user import UserORM

PRIVILEGED_ROLES = {"admin", "owner", "security"}


def require_workspace_role(user: dict, *roles: str) -> None:
    if user.get("role") not in set(roles):
        raise HTTPException(403, "insufficient workspace role")


def visible_repository_ids(session: Session, workspace_id: str, user: dict) -> set[str] | None:
    if user.get("role") in PRIVILEGED_ROLES:
        return None
    account = session.scalar(select(UserORM).where(UserORM.username == user.get("sub"), UserORM.tenant_id == workspace_id))
    if account is None:
        return set()
    return set(session.scalars(select(RepositoryGrantORM.repository_id).join(TeamMembershipORM, TeamMembershipORM.team_id == RepositoryGrantORM.team_id).where(TeamMembershipORM.user_id == account.id)))


def require_repository_access(session: Session, workspace_id: str, user: dict, repository_id: str) -> None:
    scope = visible_repository_ids(session, workspace_id, user)
    if scope is not None and repository_id not in scope:
        raise HTTPException(404, "repository not found")
