"""Enterprise knowledge assistant."""
from alembic import op
import sqlalchemy as sa

revision = "20260719_0007"
down_revision = "20260717_0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_articles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_uri", sa.String(512), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, cols in (
        ("ix_knowledge_articles_workspace_id", ["workspace_id"]),
        ("ix_knowledge_articles_title", ["title"]),
        ("ix_knowledge_articles_category", ["category"]),
        ("ix_knowledge_articles_active", ["active"]),
    ):
        op.create_index(name, "knowledge_articles", cols)

    op.create_table(
        "knowledge_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_conversations_workspace_id", "knowledge_conversations", ["workspace_id"])
    op.create_index("ix_knowledge_conversations_user_id", "knowledge_conversations", ["user_id"])

    op.create_table(
        "knowledge_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("knowledge_conversations.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name, cols in (
        ("ix_knowledge_messages_workspace_id", ["workspace_id"]),
        ("ix_knowledge_messages_conversation_id", ["conversation_id"]),
        ("ix_knowledge_messages_role", ["role"]),
        ("ix_knowledge_messages_category", ["category"]),
    ):
        op.create_index(name, "knowledge_messages", cols)


def downgrade():
    op.drop_table("knowledge_messages")
    op.drop_table("knowledge_conversations")
    op.drop_table("knowledge_articles")
