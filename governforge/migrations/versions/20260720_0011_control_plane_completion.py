"""complete control-plane data contracts

Revision ID: 20260720_0011
Revises: 20260719_0010
"""
from alembic import op
import sqlalchemy as sa

revision = "20260720_0011"
down_revision = "20260719_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("auto_merge_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("repositories", sa.Column("merge_method", sa.String(16), nullable=False, server_default="squash"))
    op.create_index("ix_repositories_auto_merge_enabled", "repositories", ["auto_merge_enabled"])
    op.add_column("ci_runs", sa.Column("head_sha", sa.String(64)))
    op.create_index("ix_ci_runs_head_sha", "ci_runs", ["head_sha"])
    op.add_column("agent_runs", sa.Column("schema_version", sa.String(16), nullable=False, server_default="v1"))
    op.add_column("agent_runs", sa.Column("payload_hash", sa.String(64)))
    op.add_column("agent_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("agent_runs", sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="900"))
    op.add_column("agent_runs", sa.Column("last_error", sa.Text()))
    op.create_index("ix_agent_runs_heartbeat_at", "agent_runs", ["heartbeat_at"])
    op.add_column("agent_actions", sa.Column("schema_version", sa.String(16), nullable=False, server_default="v1"))
    op.add_column("agent_actions", sa.Column("payload_hash", sa.String(64)))
    op.add_column("outbox_events", sa.Column("dedupe_key", sa.String(255)))
    op.create_index("ix_outbox_events_dedupe_key", "outbox_events", ["dedupe_key"], unique=True)
    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(128), nullable=False), sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("token_prefix", sa.String(20), nullable=False), sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("scopes", sa.JSON(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(128), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "name"),
    )
    op.create_index("ix_integration_credentials_workspace_id", "integration_credentials", ["workspace_id"])
    op.create_index("ix_integration_credentials_token_prefix", "integration_credentials", ["token_prefix"])
    op.create_index("ix_integration_credentials_active", "integration_credentials", ["active"])
    op.create_index("ix_integration_credentials_expires_at", "integration_credentials", ["expires_at"])
    op.create_table(
        "model_routes",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("model_alias", sa.String(128), nullable=False), sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("upstream_model", sa.String(128), nullable=False), sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("api_key_env", sa.String(128), nullable=False), sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False), sa.Column("input_cost_per_million", sa.Float(), nullable=False),
        sa.Column("output_cost_per_million", sa.Float(), nullable=False), sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "model_alias", "priority"),
    )
    op.create_index("ix_model_routes_workspace_id", "model_routes", ["workspace_id"])
    op.create_index("ix_model_routes_model_alias", "model_routes", ["model_alias"])
    op.create_index("ix_model_routes_provider", "model_routes", ["provider"])
    op.create_index("ix_model_routes_enabled", "model_routes", ["enabled"])
    op.create_table(
        "cost_events",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False), sa.Column("category", sa.String(32), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False), sa.Column("minutes", sa.Float(), nullable=False), sa.Column("role", sa.String(64)),
        sa.Column("repository_id", sa.String(36), sa.ForeignKey("repositories.id")), sa.Column("pull_request_id", sa.String(36), sa.ForeignKey("pull_requests.id")),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id")), sa.Column("trace_id", sa.String(128)),
        sa.Column("detail", sa.JSON(), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "external_id"),
    )
    for name, columns in {
        "ix_cost_events_workspace_id": ["workspace_id"], "ix_cost_events_category": ["category"],
        "ix_cost_events_repository_id": ["repository_id"], "ix_cost_events_pull_request_id": ["pull_request_id"],
        "ix_cost_events_run_id": ["run_id"], "ix_cost_events_trace_id": ["trace_id"],
    }.items():
        op.create_index(name, "cost_events", columns)


def downgrade() -> None:
    op.drop_table("cost_events")
    op.drop_table("model_routes")
    op.drop_table("integration_credentials")
    op.drop_index("ix_outbox_events_dedupe_key", table_name="outbox_events"); op.drop_column("outbox_events", "dedupe_key")
    op.drop_column("agent_actions", "payload_hash"); op.drop_column("agent_actions", "schema_version")
    op.drop_index("ix_agent_runs_heartbeat_at", table_name="agent_runs")
    for column in ("last_error", "timeout_seconds", "heartbeat_at", "payload_hash", "schema_version"):
        op.drop_column("agent_runs", column)
    op.drop_index("ix_ci_runs_head_sha", table_name="ci_runs"); op.drop_column("ci_runs", "head_sha")
    op.drop_index("ix_repositories_auto_merge_enabled", table_name="repositories")
    op.drop_column("repositories", "merge_method"); op.drop_column("repositories", "auto_merge_enabled")
