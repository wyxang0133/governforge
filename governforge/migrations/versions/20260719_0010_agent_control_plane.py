"""Enterprise AI agent run, action, approval and evaluation control plane."""
from alembic import op
import sqlalchemy as sa

revision = "20260719_0010"
down_revision = "20260719_0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("agent_runs",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("repository_id", sa.String(36), sa.ForeignKey("repositories.id")), sa.Column("pull_request_id", sa.String(36), sa.ForeignKey("pull_requests.id")),
        sa.Column("external_id", sa.String(128), nullable=False), sa.Column("provider", sa.String(64), nullable=False), sa.Column("agent_name", sa.String(128), nullable=False),
        sa.Column("task", sa.Text(), nullable=False), sa.Column("plan", sa.JSON(), nullable=False), sa.Column("status", sa.String(24), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False), sa.Column("requested_by", sa.String(128), nullable=False), sa.Column("trace_id", sa.String(128)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("workspace_id", "external_id"))
    for name, cols in (("workspace_id",["workspace_id"]),("repository_id",["repository_id"]),("pull_request_id",["pull_request_id"]),("provider",["provider"]),("status",["status"]),("risk_level",["risk_level"]),("requested_by",["requested_by"]),("trace_id",["trace_id"])):
        op.create_index(f"ix_agent_runs_{name}", "agent_runs", cols)
    op.create_table("agent_actions",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False), sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("action_type", sa.String(32), nullable=False), sa.Column("target", sa.String(1024)), sa.Column("command", sa.Text()),
        sa.Column("status", sa.String(24), nullable=False), sa.Column("risk_type", sa.String(64)), sa.Column("risk_level", sa.String(16), nullable=False), sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("run_id", "sequence"))
    for name in ("workspace_id","run_id","action_type","status","risk_type","risk_level","requires_approval"):
        op.create_index(f"ix_agent_actions_{name}", "agent_actions", [name])
    op.create_table("agent_approvals",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False), sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=False), sa.Column("action_id", sa.String(36), sa.ForeignKey("agent_actions.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False), sa.Column("required_role", sa.String(32), nullable=False), sa.Column("requested_by", sa.String(128), nullable=False), sa.Column("decided_by", sa.String(128)), sa.Column("reason", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("decided_at", sa.DateTime(timezone=True)))
    for name in ("workspace_id","run_id","action_id","status"):
        op.create_index(f"ix_agent_approvals_{name}", "agent_approvals", [name])
    op.create_table("agent_evaluations",
        sa.Column("id", sa.String(36), primary_key=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False), sa.Column("run_id", sa.String(36), sa.ForeignKey("agent_runs.id"), nullable=False, unique=True),
        sa.Column("score", sa.Float(), nullable=False), sa.Column("decision", sa.String(16), nullable=False), sa.Column("findings", sa.JSON(), nullable=False), sa.Column("metrics", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    for name in ("workspace_id","run_id","decision"):
        op.create_index(f"ix_agent_evaluations_{name}", "agent_evaluations", [name])


def downgrade():
    op.drop_table("agent_evaluations")
    op.drop_table("agent_approvals")
    op.drop_table("agent_actions")
    op.drop_table("agent_runs")
