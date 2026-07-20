"""Scoped policy inheritance and monthly budget allocations."""
from alembic import op
import sqlalchemy as sa

revision = "20260717_0006"
down_revision = "20260717_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("policy_definitions", sa.Column("scope_type", sa.String(24), nullable=False, server_default="workspace"))
    op.add_column("policy_definitions", sa.Column("scope_id", sa.String(64), nullable=False, server_default="*"))
    op.create_index("ix_policy_definitions_scope_type", "policy_definitions", ["scope_type"])
    op.create_index("ix_policy_definitions_scope_id", "policy_definitions", ["scope_id"])
    op.drop_constraint("policy_definitions_workspace_id_version_key", "policy_definitions", type_="unique")
    op.create_unique_constraint("uq_policy_scope_version", "policy_definitions", ["workspace_id", "scope_type", "scope_id", "version"])
    op.create_table("budget_allocations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("scope_type", sa.String(24), nullable=False), sa.Column("scope_id", sa.String(64), nullable=False),
        sa.Column("period", sa.String(7), nullable=False), sa.Column("limit_usd", sa.Float(), nullable=False),
        sa.Column("warning_ratio", sa.Float(), nullable=False), sa.Column("hard_limit", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "scope_type", "scope_id", "period"),
    )
    for name, cols in (("ix_budget_allocations_workspace_id", ["workspace_id"]), ("ix_budget_allocations_scope_type", ["scope_type"]), ("ix_budget_allocations_scope_id", ["scope_id"]), ("ix_budget_allocations_period", ["period"])):
        op.create_index(name, "budget_allocations", cols)


def downgrade():
    op.drop_table("budget_allocations")
    op.drop_constraint("uq_policy_scope_version", "policy_definitions", type_="unique")
    op.create_unique_constraint("policy_definitions_workspace_id_version_key", "policy_definitions", ["workspace_id", "version"])
    op.drop_index("ix_policy_definitions_scope_id", table_name="policy_definitions"); op.drop_index("ix_policy_definitions_scope_type", table_name="policy_definitions")
    op.drop_column("policy_definitions", "scope_id"); op.drop_column("policy_definitions", "scope_type")
