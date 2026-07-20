"""Versioned, scope-aware policy configuration and strict inheritance."""
from dataclasses import dataclass
from sqlalchemy import desc, select
from sqlalchemy.orm import Session
from devpilot.models.governance import PolicyDefinitionORM, RepositoryGrantORM

DEFAULT_PATTERNS = [".github/", "infra/", "migrations/", "auth", "security"]

@dataclass
class EffectivePolicy:
    id: str
    version: int
    name: str
    min_source_confidence: float
    min_test_coverage: float
    cost_budget_usd: float
    require_security_scan: bool
    sensitive_patterns: list[str]
    policy_chain: list[dict]

def get_active_policy(session: Session, workspace_id: str, scope_type: str = "workspace", scope_id: str = "*") -> PolicyDefinitionORM:
    policy = session.scalar(select(PolicyDefinitionORM).where(PolicyDefinitionORM.workspace_id == workspace_id, PolicyDefinitionORM.scope_type == scope_type, PolicyDefinitionORM.scope_id == scope_id, PolicyDefinitionORM.active.is_(True)).order_by(desc(PolicyDefinitionORM.version)))
    if policy is None and scope_type == "workspace":
        policy = PolicyDefinitionORM(workspace_id=workspace_id, scope_type="workspace", scope_id="*", version=1, name="Default Policy", active=True, min_source_confidence=.7, min_test_coverage=.6, cost_budget_usd=5, require_security_scan=True, sensitive_patterns=DEFAULT_PATTERNS, created_by="system")
        session.add(policy); session.flush()
    if policy is None: raise LookupError("active scoped policy not found")
    return policy

def get_effective_policy(session: Session, workspace_id: str, repository_id: str | None = None) -> EffectivePolicy:
    workspace = get_active_policy(session, workspace_id)
    layers = [workspace]
    if repository_id:
        team_ids = list(session.scalars(select(RepositoryGrantORM.team_id).where(RepositoryGrantORM.repository_id == repository_id)))
        if team_ids:
            layers.extend(session.scalars(select(PolicyDefinitionORM).where(PolicyDefinitionORM.workspace_id == workspace_id, PolicyDefinitionORM.scope_type == "team", PolicyDefinitionORM.scope_id.in_(team_ids), PolicyDefinitionORM.active.is_(True))).all())
        repository_policy = session.scalar(select(PolicyDefinitionORM).where(PolicyDefinitionORM.workspace_id == workspace_id, PolicyDefinitionORM.scope_type == "repository", PolicyDefinitionORM.scope_id == repository_id, PolicyDefinitionORM.active.is_(True)).order_by(desc(PolicyDefinitionORM.version)))
        if repository_policy: layers.append(repository_policy)
    rank = {"workspace": 0, "team": 1, "repository": 2}
    primary = max(layers, key=lambda p: (rank.get(p.scope_type, 0), p.version))
    chain = [{"id": p.id, "scope_type": p.scope_type, "scope_id": p.scope_id, "version": p.version, "name": p.name} for p in sorted(layers, key=lambda p: (rank.get(p.scope_type, 0), p.scope_id, p.version))]
    return EffectivePolicy(primary.id, primary.version, "Effective Policy", max(p.min_source_confidence for p in layers), max(p.min_test_coverage for p in layers), min(p.cost_budget_usd for p in layers), any(p.require_security_scan for p in layers), sorted({pattern for p in layers for pattern in p.sensitive_patterns}), chain)

def policy_dict(policy: PolicyDefinitionORM) -> dict:
    return {"id": policy.id, "scope_type": policy.scope_type, "scope_id": policy.scope_id, "version": policy.version, "name": policy.name, "active": policy.active, "min_source_confidence": policy.min_source_confidence, "min_test_coverage": policy.min_test_coverage, "cost_budget_usd": policy.cost_budget_usd, "require_security_scan": policy.require_security_scan, "sensitive_patterns": policy.sensitive_patterns, "created_by": policy.created_by, "created_at": policy.created_at}
