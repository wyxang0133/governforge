"""Team membership and repository-scoped grants."""
from alembic import op
import sqlalchemy as sa

revision = "20260717_0005"
down_revision = "20260717_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("teams", sa.Column("id", sa.String(36), primary_key=True), sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False), sa.Column("name", sa.String(128), nullable=False), sa.Column("slug", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("workspace_id", "slug"))
    op.create_index("ix_teams_workspace_id", "teams", ["workspace_id"])
    op.create_table("team_memberships", sa.Column("id", sa.String(36), primary_key=True), sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id"), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("role", sa.String(32), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("team_id", "user_id"))
    op.create_index("ix_team_memberships_team_id", "team_memberships", ["team_id"]); op.create_index("ix_team_memberships_user_id", "team_memberships", ["user_id"])
    op.create_table("repository_grants", sa.Column("id", sa.String(36), primary_key=True), sa.Column("team_id", sa.String(36), sa.ForeignKey("teams.id"), nullable=False), sa.Column("repository_id", sa.String(36), sa.ForeignKey("repositories.id"), nullable=False), sa.Column("permission", sa.String(24), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("team_id", "repository_id"))
    op.create_index("ix_repository_grants_team_id", "repository_grants", ["team_id"]); op.create_index("ix_repository_grants_repository_id", "repository_grants", ["repository_id"])


def downgrade():
    op.drop_table("repository_grants"); op.drop_table("team_memberships"); op.drop_table("teams")
