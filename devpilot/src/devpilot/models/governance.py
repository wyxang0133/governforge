"""Persistent domain model for AI Coding governance."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event
from sqlalchemy.orm import Mapped, mapped_column

from devpilot.core.database import Base


def new_id() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceORM(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RepositoryORM(Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("workspace_id", "provider", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    provider: Mapped[str] = mapped_column(String(24), default="github")
    external_id: Mapped[str] = mapped_column(String(128))
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    default_branch: Mapped[str] = mapped_column(String(128), default="main")
    installation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    html_url: Mapped[str | None] = mapped_column(String(512))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GitHubInstallationORM(Base):
    """Trusted mapping from a GitHub App installation to one workspace."""
    __tablename__ = "github_installations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    installation_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    account_login: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TeamORM(Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("workspace_id", "slug"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TeamMembershipORM(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RepositoryGrantORM(Base):
    __tablename__ = "repository_grants"
    __table_args__ = (UniqueConstraint("team_id", "repository_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), index=True)
    repository_id: Mapped[str] = mapped_column(String(36), ForeignKey("repositories.id"), index=True)
    permission: Mapped[str] = mapped_column(String(24), default="read")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PullRequestORM(Base):
    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("repository_id", "external_number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    repository_id: Mapped[str] = mapped_column(String(36), ForeignKey("repositories.id"), index=True)
    external_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(512), default="")
    author: Mapped[str] = mapped_column(String(128), default="unknown")
    state: Mapped[str] = mapped_column(String(24), default="open")
    head_sha: Mapped[str] = mapped_column(String(64), index=True)
    additions: Mapped[int] = mapped_column(Integer, default=0)
    deletions: Mapped[int] = mapped_column(Integer, default=0)
    changed_files: Mapped[int] = mapped_column(Integer, default=0)
    source_confidence: Mapped[float] = mapped_column(Float, default=0)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CIRunORM(Base):
    __tablename__ = "ci_runs"
    __table_args__ = (UniqueConstraint("repository_id", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    repository_id: Mapped[str] = mapped_column(String(36), ForeignKey("repositories.id"))
    pull_request_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("pull_requests.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255), default="ci")
    status: Mapped[str] = mapped_column(String(24), default="queued")
    conclusion: Mapped[str | None] = mapped_column(String(32))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    coverage: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIUsageEventORM(Base):
    __tablename__ = "ai_usage_events"
    __table_args__ = (UniqueConstraint("workspace_id", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    repository_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("repositories.id"), index=True)
    pull_request_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("pull_requests.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    trace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(64), default="gateway")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRunORM(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (UniqueConstraint("workspace_id", "external_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    repository_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("repositories.id"), index=True)
    pull_request_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("pull_requests.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    provider: Mapped[str] = mapped_column(String(64), index=True)
    agent_name: Mapped[str] = mapped_column(String(128))
    task: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    risk_level: Mapped[str] = mapped_column(String(16), default="low", index=True)
    requested_by: Mapped[str] = mapped_column(String(128), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentActionORM(Base):
    __tablename__ = "agent_actions"
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String(32), index=True)
    target: Mapped[str | None] = mapped_column(String(1024))
    command: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="completed", index=True)
    risk_type: Mapped[str | None] = mapped_column(String(64), index=True)
    risk_level: Mapped[str] = mapped_column(String(16), default="low", index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentApprovalORM(Base):
    __tablename__ = "agent_approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id"), index=True)
    action_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_actions.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    required_role: Mapped[str] = mapped_column(String(32), default="security")
    requested_by: Mapped[str] = mapped_column(String(128))
    decided_by: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentEvaluationORM(Base):
    __tablename__ = "agent_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_runs.id"), unique=True, index=True)
    score: Mapped[float] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(16), index=True)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeArticleORM(Base):
    __tablename__ = "knowledge_articles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), default="general", index=True)
    source_type: Mapped[str] = mapped_column(String(32), default="manual")
    source_uri: Mapped[str | None] = mapped_column(String(512))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(128), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class KnowledgeChunkORM(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("article_id", "position"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    article_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_articles.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeConversationORM(Base):
    __tablename__ = "knowledge_conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="New conversation")
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class KnowledgeMessageORM(Base):
    __tablename__ = "knowledge_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), index=True)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeFeedbackORM(Base):
    __tablename__ = "knowledge_feedback"
    __table_args__ = (UniqueConstraint("message_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    message_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_messages.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    rating: Mapped[str] = mapped_column(String(16), index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeEscalationORM(Base):
    __tablename__ = "knowledge_escalations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_conversations.id"), index=True)
    message_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("knowledge_messages.id"), index=True)
    requested_by: Mapped[str] = mapped_column(String(128), index=True)
    queue: Mapped[str] = mapped_column(String(64), default="knowledge-experts", index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookDeliveryORM(Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (UniqueConstraint("provider", "delivery_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(24), default="github")
    delivery_id: Mapped[str] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="received")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PolicyEvaluationORM(Base):
    __tablename__ = "policy_evaluations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    pull_request_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("pull_requests.id"), index=True)
    policy_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("policy_definitions.id"), index=True)
    policy_version: Mapped[str] = mapped_column(String(32), default="v1")
    decision: Mapped[str] = mapped_column(String(16), index=True)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    checks: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApprovalRequestORM(Base):
    __tablename__ = "approval_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    pull_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("pull_requests.id"), index=True)
    evaluation_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_evaluations.id"))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    required_role: Mapped[str] = mapped_column(String(32), default="owner")
    decided_by: Mapped[str | None] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GovernanceAuditEventORM(Base):
    __tablename__ = "governance_audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(128), default="system")
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(128), index=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PolicyDefinitionORM(Base):
    __tablename__ = "policy_definitions"
    __table_args__ = (UniqueConstraint("workspace_id", "scope_type", "scope_id", "version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    scope_type: Mapped[str] = mapped_column(String(24), default="workspace", index=True)
    scope_id: Mapped[str] = mapped_column(String(64), default="*", index=True)
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128), default="Default Policy")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    min_source_confidence: Mapped[float] = mapped_column(Float, default=0.7)
    min_test_coverage: Mapped[float] = mapped_column(Float, default=0.6)
    cost_budget_usd: Mapped[float] = mapped_column(Float, default=5.0)
    require_security_scan: Mapped[bool] = mapped_column(Boolean, default=True)
    sensitive_patterns: Mapped[list] = mapped_column(JSON, default=lambda: [".github/", "infra/", "migrations/", "auth", "security"])
    created_by: Mapped[str] = mapped_column(String(128), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BudgetAllocationORM(Base):
    __tablename__ = "budget_allocations"
    __table_args__ = (UniqueConstraint("workspace_id", "scope_type", "scope_id", "period"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    scope_type: Mapped[str] = mapped_column(String(24), index=True)
    scope_id: Mapped[str] = mapped_column(String(64), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)
    limit_usd: Mapped[float] = mapped_column(Float)
    warning_ratio: Mapped[float] = mapped_column(Float, default=.8)
    hard_limit: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SourceSignalORM(Base):
    __tablename__ = "source_signals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    pull_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("pull_requests.id"), index=True)
    signal_type: Mapped[str] = mapped_column(String(64), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    evidence_ref: Mapped[str | None] = mapped_column(String(512))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutboxEventORM(Base):
    __tablename__ = "outbox_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(String(36), ForeignKey("workspaces.id"), index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64))
    aggregate_id: Mapped[str] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


@event.listens_for(GovernanceAuditEventORM, "before_update")
@event.listens_for(GovernanceAuditEventORM, "before_delete")
def prevent_audit_mutation(*_args):
    raise ValueError("governance audit events are append-only")
