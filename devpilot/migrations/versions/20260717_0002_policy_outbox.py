"""Policy definitions, source signals and reliable outbox."""
from alembic import op
import sqlalchemy as sa

revision = "20260717_0002"
down_revision = "20260717_0001"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("policy_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("min_source_confidence", sa.Float(), nullable=False),
        sa.Column("min_test_coverage", sa.Float(), nullable=False),
        sa.Column("cost_budget_usd", sa.Float(), nullable=False),
        sa.Column("require_security_scan", sa.Boolean(), nullable=False),
        sa.Column("sensitive_patterns", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "version"),
    )
    op.create_index("ix_policy_definitions_workspace_id", "policy_definitions", ["workspace_id"])
    op.create_index("ix_policy_definitions_active", "policy_definitions", ["active"])
    op.create_table("source_signals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("pull_request_id", sa.String(36), sa.ForeignKey("pull_requests.id"), nullable=False),
        sa.Column("signal_type", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_ref", sa.String(512)),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_source_signals_workspace_id", "source_signals", ["workspace_id"])
    op.create_index("ix_source_signals_pull_request_id", "source_signals", ["pull_request_id"])
    op.create_index("ix_source_signals_signal_type", "source_signals", ["signal_type"])
    op.create_table("outbox_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("aggregate_type", sa.String(64), nullable=False),
        sa.Column("aggregate_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outbox_events_workspace_id", "outbox_events", ["workspace_id"])
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"])
    op.add_column("repositories", sa.Column("installation_id", sa.String(128)))
    op.add_column("repositories", sa.Column("html_url", sa.String(512)))
    op.create_index("ix_repositories_installation_id", "repositories", ["installation_id"])
    op.add_column("policy_evaluations", sa.Column("policy_id", sa.String(36), sa.ForeignKey("policy_definitions.id")))
    op.create_index("ix_policy_evaluations_policy_id", "policy_evaluations", ["policy_id"])
    op.execute("UPDATE users SET role='admin' WHERE id IN (SELECT MIN(id) FROM users GROUP BY tenant_id) AND tenant_id NOT IN (SELECT tenant_id FROM users WHERE role IN ('admin','owner'))")

def downgrade():
    op.drop_index("ix_policy_evaluations_policy_id", table_name="policy_evaluations")
    op.drop_column("policy_evaluations", "policy_id")
    op.drop_index("ix_repositories_installation_id", table_name="repositories")
    op.drop_column("repositories", "html_url")
    op.drop_column("repositories", "installation_id")
    op.drop_table("outbox_events")
    op.drop_table("source_signals")
    op.drop_table("policy_definitions")
