"""Trusted GitHub App installation mappings and database audit immutability."""
from alembic import op
import sqlalchemy as sa

revision = "20260717_0003"
down_revision = "20260717_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "github_installations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("installation_id", sa.String(128), nullable=False, unique=True),
        sa.Column("account_login", sa.String(255)),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_github_installations_workspace_id", "github_installations", ["workspace_id"])
    op.create_index("ix_github_installations_installation_id", "github_installations", ["installation_id"])
    op.create_index("ix_github_installations_active", "github_installations", ["active"])
    # ORM guards accidental changes; PostgreSQL additionally enforces the
    # append-only contract against raw SQL and compromised application paths.
    op.execute("""
    CREATE OR REPLACE FUNCTION devpilot_prevent_audit_mutation() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'governance_audit_events is append-only'; END;
    $$ LANGUAGE plpgsql
    """)
    op.execute("""
    CREATE TRIGGER governance_audit_events_append_only
    BEFORE UPDATE OR DELETE ON governance_audit_events
    FOR EACH ROW EXECUTE FUNCTION devpilot_prevent_audit_mutation();
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS governance_audit_events_append_only ON governance_audit_events")
    op.execute("DROP FUNCTION IF EXISTS devpilot_prevent_audit_mutation()")
    op.drop_table("github_installations")
