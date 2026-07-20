"""Backfill chunk index for articles created before the RAG migration."""
from datetime import datetime, timezone
import hashlib
import re
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "20260719_0009"
down_revision = "20260719_0008"
branch_labels = None
depends_on = None


def _chunks(content: str, size: int = 900, overlap: int = 120) -> list[str]:
    text = re.sub(r"\r\n?", "\n", content or "").strip()
    if not text:
        return []
    step = size - overlap
    return [text[start:start + size] for start in range(0, len(text), step)]


def upgrade():
    bind = op.get_bind()
    existing = {row[0] for row in bind.execute(sa.text("SELECT DISTINCT article_id FROM knowledge_chunks"))}
    articles = bind.execute(sa.text("SELECT id, workspace_id, content FROM knowledge_articles WHERE active = :active"), {"active": True}).mappings()
    now = datetime.now(timezone.utc)
    for article in articles:
        if article["id"] in existing:
            continue
        for position, content in enumerate(_chunks(article["content"])):
            bind.execute(
                sa.text("INSERT INTO knowledge_chunks (id, workspace_id, article_id, position, content, token_count, checksum, created_at) VALUES (:id, :workspace_id, :article_id, :position, :content, :token_count, :checksum, :created_at)"),
                {"id": str(uuid4()), "workspace_id": article["workspace_id"], "article_id": article["id"], "position": position, "content": content, "token_count": max(1, len(content) // 4), "checksum": hashlib.sha256(content.encode("utf-8")).hexdigest(), "created_at": now},
            )


def downgrade():
    # Backfilled rows are valid index data and are intentionally retained.
    pass
