"""Knowledge RAG indexing, feedback and expert escalation."""
from alembic import op
import sqlalchemy as sa

revision = "20260719_0008"
down_revision = "20260719_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("article_id", sa.String(36), sa.ForeignKey("knowledge_articles.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("article_id", "position"),
    )
    for name, cols in (("ix_knowledge_chunks_workspace_id", ["workspace_id"]), ("ix_knowledge_chunks_article_id", ["article_id"]), ("ix_knowledge_chunks_checksum", ["checksum"])):
        op.create_index(name, "knowledge_chunks", cols)
    op.create_table(
        "knowledge_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("knowledge_messages.id"), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("rating", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id", "user_id"),
    )
    for name, cols in (("ix_knowledge_feedback_workspace_id", ["workspace_id"]), ("ix_knowledge_feedback_message_id", ["message_id"]), ("ix_knowledge_feedback_user_id", ["user_id"]), ("ix_knowledge_feedback_rating", ["rating"])):
        op.create_index(name, "knowledge_feedback", cols)
    op.create_table(
        "knowledge_escalations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("knowledge_conversations.id"), nullable=False),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("knowledge_messages.id"), nullable=True),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("queue", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("assigned_to", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    for name, cols in (("ix_knowledge_escalations_workspace_id", ["workspace_id"]), ("ix_knowledge_escalations_conversation_id", ["conversation_id"]), ("ix_knowledge_escalations_message_id", ["message_id"]), ("ix_knowledge_escalations_requested_by", ["requested_by"]), ("ix_knowledge_escalations_queue", ["queue"]), ("ix_knowledge_escalations_status", ["status"])):
        op.create_index(name, "knowledge_escalations", cols)


def downgrade():
    op.drop_table("knowledge_escalations")
    op.drop_table("knowledge_feedback")
    op.drop_table("knowledge_chunks")
