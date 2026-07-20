"""Enterprise knowledge base and assistant APIs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from governforge.core.auth import get_current_user
from governforge.core.database import get_session
from governforge.config import AppSettings
from governforge.core.knowledge import answer_question, classify_question, extract_document, index_article, search_articles, seed_default_articles
from governforge.core.metrics import KNOWLEDGE_ESCALATIONS, KNOWLEDGE_FEEDBACK, KNOWLEDGE_QUERIES
from governforge.core.trace_middleware import get_trace_id
from governforge.core.workspace import get_workspace_id
from governforge.models.governance import (
    AIUsageEventORM,
    GovernanceAuditEventORM,
    KnowledgeArticleORM,
    KnowledgeChunkORM,
    KnowledgeConversationORM,
    KnowledgeEscalationORM,
    KnowledgeFeedbackORM,
    KnowledgeMessageORM,
    WorkspaceORM,
)

router = APIRouter(tags=["knowledge"])
settings = AppSettings()


def _ensure_workspace(session: Session, workspace_id: str) -> None:
    if session.get(WorkspaceORM, workspace_id) is None:
        session.add(WorkspaceORM(id=workspace_id, name=workspace_id, slug=workspace_id.lower().replace("_", "-")[:64]))
        session.flush()


class ArticleCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    content: str = Field(min_length=10, max_length=20000)
    category: str = Field("general", max_length=64)
    tags: list[str] = Field(default_factory=list, max_length=20)
    source_type: str = Field("manual", max_length=32)
    source_uri: str | None = Field(None, max_length=512)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)
    conversation_id: str | None = None


class FeedbackCreate(BaseModel):
    message_id: str
    rating: str = Field(pattern="^(helpful|unhelpful)$")
    comment: str | None = Field(None, max_length=1000)


class EscalationCreate(BaseModel):
    conversation_id: str
    message_id: str | None = None
    reason: str = Field(min_length=2, max_length=2000)
    queue: str = Field("knowledge-experts", min_length=2, max_length=64)


def _manage_knowledge(user: dict) -> None:
    if user.get("role") not in {"admin", "owner", "security"}:
        raise HTTPException(403, "insufficient role for knowledge management")


def _serialize_article(item: KnowledgeArticleORM, chunks: int | None = None) -> dict[str, Any]:
    return {"id": item.id, "title": item.title, "category": item.category, "tags": item.tags, "source_type": item.source_type, "source_uri": item.source_uri, "version": item.version, "active": item.active, "content": item.content, "chunk_count": chunks, "updated_at": item.updated_at}


@router.get("/articles")
def list_articles(session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    items = session.scalars(
        select(KnowledgeArticleORM)
        .where(KnowledgeArticleORM.workspace_id == x_workspace_id, KnowledgeArticleORM.active.is_(True))
        .order_by(desc(KnowledgeArticleORM.updated_at))
        .limit(200)
    ).all()
    counts = dict(session.execute(select(KnowledgeChunkORM.article_id, func.count(KnowledgeChunkORM.id)).where(KnowledgeChunkORM.workspace_id == x_workspace_id).group_by(KnowledgeChunkORM.article_id)).all())
    return [_serialize_article(item, counts.get(item.id, 0)) for item in items]


@router.get("/articles/{article_id}")
def get_article(article_id: str, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict[str, Any]:
    item = session.scalar(select(KnowledgeArticleORM).where(KnowledgeArticleORM.id == article_id, KnowledgeArticleORM.workspace_id == x_workspace_id))
    if item is None:
        raise HTTPException(404, "knowledge article not found")
    count = session.scalar(select(func.count(KnowledgeChunkORM.id)).where(KnowledgeChunkORM.article_id == article_id)) or 0
    return _serialize_article(item, count)


@router.post("/articles")
def create_article(data: ArticleCreate, request: Request, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict[str, Any]:
    _manage_knowledge(user)
    _ensure_workspace(session, x_workspace_id)
    article = KnowledgeArticleORM(
        workspace_id=x_workspace_id,
        title=data.title,
        content=data.content,
        category=data.category,
        tags=data.tags,
        source_type=data.source_type,
        source_uri=data.source_uri,
        created_by=user.get("sub", "unknown"),
    )
    session.add(article)
    session.flush()
    chunk_count = index_article(session, article)
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, actor_id=user.get("sub", "unknown"), event_type="knowledge.article.created", entity_type="knowledge_article", entity_id=article.id, trace_id=get_trace_id(request), payload={"title": article.title, "category": article.category, "chunks": chunk_count}))
    session.commit()
    return {"id": article.id, "title": article.title, "category": article.category, "chunk_count": chunk_count}


@router.put("/articles/{article_id}")
def update_article(article_id: str, data: ArticleCreate, request: Request, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict[str, Any]:
    _manage_knowledge(user)
    article = session.scalar(select(KnowledgeArticleORM).where(KnowledgeArticleORM.id == article_id, KnowledgeArticleORM.workspace_id == x_workspace_id))
    if article is None:
        raise HTTPException(404, "knowledge article not found")
    for field in ("title", "content", "category", "tags", "source_type", "source_uri"):
        setattr(article, field, getattr(data, field))
    article.version += 1
    article.active = True
    chunk_count = index_article(session, article)
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, actor_id=user.get("sub", "unknown"), event_type="knowledge.article.updated", entity_type="knowledge_article", entity_id=article.id, trace_id=get_trace_id(request), payload={"version": article.version, "chunks": chunk_count}))
    session.commit()
    return {"id": article.id, "version": article.version, "chunk_count": chunk_count}


@router.delete("/articles/{article_id}", status_code=204)
def archive_article(article_id: str, request: Request, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> None:
    _manage_knowledge(user)
    article = session.scalar(select(KnowledgeArticleORM).where(KnowledgeArticleORM.id == article_id, KnowledgeArticleORM.workspace_id == x_workspace_id))
    if article is None:
        raise HTTPException(404, "knowledge article not found")
    article.active = False
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, actor_id=user.get("sub", "unknown"), event_type="knowledge.article.archived", entity_type="knowledge_article", entity_id=article.id, trace_id=get_trace_id(request), payload={"version": article.version}))
    session.commit()


@router.post("/documents", status_code=201)
async def upload_document(request: Request, file: UploadFile = File(...), title: str = Form(""), category: str = Form("general"), tags: str = Form(""), session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict[str, Any]:
    _manage_knowledge(user)
    _ensure_workspace(session, x_workspace_id)
    raw = await file.read(settings.knowledge_max_upload_bytes + 1)
    if len(raw) > settings.knowledge_max_upload_bytes:
        raise HTTPException(413, f"document exceeds {settings.knowledge_max_upload_bytes} bytes")
    try:
        content = extract_document(file.filename or "document.txt", __import__("io").BytesIO(raw))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    article = KnowledgeArticleORM(workspace_id=x_workspace_id, title=(title.strip() or (file.filename or "企业文档"))[:255], category=category[:64], tags=[item.strip() for item in tags.split(",") if item.strip()][:20], source_type="upload", source_uri=file.filename, content=content[:200000], created_by=user.get("sub", "unknown"))
    session.add(article)
    session.flush()
    chunk_count = index_article(session, article)
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, actor_id=user.get("sub", "unknown"), event_type="knowledge.document.ingested", entity_type="knowledge_article", entity_id=article.id, trace_id=get_trace_id(request), payload={"filename": file.filename, "bytes": len(raw), "chunks": chunk_count}))
    session.commit()
    return {"id": article.id, "title": article.title, "chunk_count": chunk_count}


@router.post("/seed")
def seed_articles(request: Request, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict[str, int]:
    _manage_knowledge(user)
    _ensure_workspace(session, x_workspace_id)
    count = seed_default_articles(session, x_workspace_id, user.get("sub", "unknown"))
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, actor_id=user.get("sub", "unknown"), event_type="knowledge.seeded", entity_type="workspace", entity_id=x_workspace_id, trace_id=get_trace_id(request), payload={"created": count}))
    session.commit()
    return {"created": count}


@router.get("/conversations")
def list_conversations(session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    items = session.scalars(
        select(KnowledgeConversationORM)
        .where(KnowledgeConversationORM.workspace_id == x_workspace_id, KnowledgeConversationORM.user_id == user.get("sub", "unknown"))
        .order_by(desc(KnowledgeConversationORM.updated_at))
        .limit(50)
    ).all()
    return [{"id": item.id, "title": item.title, "created_at": item.created_at, "updated_at": item.updated_at} for item in items]


@router.get("/conversations/{conversation_id}/messages")
def list_messages(conversation_id: str, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> list[dict[str, Any]]:
    conversation = session.scalar(select(KnowledgeConversationORM).where(KnowledgeConversationORM.id == conversation_id, KnowledgeConversationORM.workspace_id == x_workspace_id, KnowledgeConversationORM.user_id == user.get("sub", "unknown")))
    if conversation is None:
        raise HTTPException(404, "conversation not found")
    items = session.scalars(select(KnowledgeMessageORM).where(KnowledgeMessageORM.conversation_id == conversation_id).order_by(KnowledgeMessageORM.created_at)).all()
    return [{"id": item.id, "role": item.role, "content": item.content, "category": item.category, "citations": item.citations, "confidence": item.confidence, "created_at": item.created_at} for item in items]


@router.post("/chat")
def chat(data: ChatRequest, request: Request, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict[str, Any]:
    _ensure_workspace(session, x_workspace_id)
    actor = user.get("sub", "unknown")
    conversation = session.get(KnowledgeConversationORM, data.conversation_id) if data.conversation_id else None
    if conversation and (conversation.workspace_id != x_workspace_id or conversation.user_id != actor):
        raise HTTPException(404, "conversation not found")
    if conversation is None:
        conversation = KnowledgeConversationORM(workspace_id=x_workspace_id, user_id=actor, title=data.message[:80])
        session.add(conversation)
        session.flush()
    category, category_confidence = classify_question(data.message)
    hits = search_articles(session, x_workspace_id, data.message)
    result = answer_question(data.message, hits, settings)
    citations = [
        {"article_id": hit.article.id, "chunk_id": hit.chunk_id, "title": hit.article.title, "category": hit.article.category, "score": round(hit.score, 2), "snippet": hit.snippet, "source_uri": hit.article.source_uri}
        for hit in hits
    ]
    session.add(KnowledgeMessageORM(workspace_id=x_workspace_id, conversation_id=conversation.id, role="user", content=data.message, category=category, citations=[], confidence=category_confidence))
    assistant_message = KnowledgeMessageORM(workspace_id=x_workspace_id, conversation_id=conversation.id, role="assistant", content=result.answer, category=category, citations=citations, confidence=result.confidence)
    session.add(assistant_message)
    session.flush()
    session.add(AIUsageEventORM(workspace_id=x_workspace_id, external_id=assistant_message.id, provider=result.provider, model=result.model, input_tokens=result.input_tokens, output_tokens=result.output_tokens, cost_usd=result.cost_usd, trace_id=get_trace_id(request), source="knowledge_assistant"))
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, actor_id=actor, event_type="knowledge.chat.completed", entity_type="knowledge_conversation", entity_id=conversation.id, trace_id=get_trace_id(request), payload={"category": category, "confidence": result.confidence, "citations": len(citations), "provider": result.provider, "model": result.model, "fallback_reason": result.fallback_reason}))
    session.commit()
    outcome = "blocked" if result.model == "guardrail" else ("grounded" if citations else "no_answer")
    KNOWLEDGE_QUERIES.labels(category, result.provider, outcome).inc()
    return {
        "conversation_id": conversation.id,
        "message_id": assistant_message.id,
        "answer": result.answer,
        "category": category,
        "confidence": result.confidence,
        "citations": citations,
        "provider": result.provider,
        "model": result.model,
        "cost_usd": result.cost_usd,
        "fallback_reason": result.fallback_reason,
    }


@router.post("/feedback", status_code=201)
def create_feedback(data: FeedbackCreate, request: Request, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict[str, str]:
    actor = user.get("sub", "unknown")
    message = session.scalar(select(KnowledgeMessageORM).join(KnowledgeConversationORM, KnowledgeMessageORM.conversation_id == KnowledgeConversationORM.id).where(KnowledgeMessageORM.id == data.message_id, KnowledgeMessageORM.workspace_id == x_workspace_id, KnowledgeMessageORM.role == "assistant", KnowledgeConversationORM.user_id == actor))
    if message is None:
        raise HTTPException(404, "assistant message not found")
    existing = session.scalar(select(KnowledgeFeedbackORM).where(KnowledgeFeedbackORM.message_id == message.id, KnowledgeFeedbackORM.user_id == actor))
    if existing:
        existing.rating, existing.comment = data.rating, data.comment
        feedback = existing
    else:
        feedback = KnowledgeFeedbackORM(workspace_id=x_workspace_id, message_id=message.id, user_id=actor, rating=data.rating, comment=data.comment)
        session.add(feedback)
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, actor_id=actor, event_type="knowledge.feedback.recorded", entity_type="knowledge_message", entity_id=message.id, trace_id=get_trace_id(request), payload={"rating": data.rating}))
    session.commit()
    KNOWLEDGE_FEEDBACK.labels(data.rating).inc()
    return {"id": feedback.id, "rating": feedback.rating}


@router.post("/escalations", status_code=201)
def create_escalation(data: EscalationCreate, request: Request, session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict[str, str]:
    actor = user.get("sub", "unknown")
    conversation = session.scalar(select(KnowledgeConversationORM).where(KnowledgeConversationORM.id == data.conversation_id, KnowledgeConversationORM.workspace_id == x_workspace_id, KnowledgeConversationORM.user_id == actor))
    if conversation is None:
        raise HTTPException(404, "conversation not found")
    if data.message_id and session.scalar(select(KnowledgeMessageORM.id).where(KnowledgeMessageORM.id == data.message_id, KnowledgeMessageORM.conversation_id == conversation.id)) is None:
        raise HTTPException(404, "message not found")
    item = KnowledgeEscalationORM(workspace_id=x_workspace_id, conversation_id=conversation.id, message_id=data.message_id, requested_by=actor, queue=data.queue, reason=data.reason)
    session.add(item)
    session.flush()
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, actor_id=actor, event_type="knowledge.escalation.created", entity_type="knowledge_escalation", entity_id=item.id, trace_id=get_trace_id(request), payload={"queue": item.queue}))
    session.commit()
    KNOWLEDGE_ESCALATIONS.labels(item.queue).inc()
    return {"id": item.id, "status": item.status, "queue": item.queue}


@router.get("/analytics")
def knowledge_analytics(session: Session = Depends(get_session), x_workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict[str, Any]:
    _manage_knowledge(user)
    def count(model, *conditions):
        return session.scalar(select(func.count(model.id)).where(model.workspace_id == x_workspace_id, *conditions)) or 0
    return {
        "articles": count(KnowledgeArticleORM, KnowledgeArticleORM.active.is_(True)),
        "chunks": count(KnowledgeChunkORM),
        "conversations": count(KnowledgeConversationORM),
        "assistant_messages": count(KnowledgeMessageORM, KnowledgeMessageORM.role == "assistant"),
        "helpful": count(KnowledgeFeedbackORM, KnowledgeFeedbackORM.rating == "helpful"),
        "unhelpful": count(KnowledgeFeedbackORM, KnowledgeFeedbackORM.rating == "unhelpful"),
        "open_escalations": count(KnowledgeEscalationORM, KnowledgeEscalationORM.status == "open"),
    }
