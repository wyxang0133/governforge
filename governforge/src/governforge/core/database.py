"""SQLAlchemy engine and session lifecycle."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from governforge.config import AppSettings

settings = AppSettings()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}, pool_pre_ping=True)
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_session():
    with SessionFactory() as session:
        yield session

def init_db():
    """Create local development/test tables; production uses Alembic."""
    from governforge.models.user import UserORM  # noqa: F401
    from governforge.models.governance import (  # noqa: F401
        WorkspaceORM, RepositoryORM, PullRequestORM, CIRunORM, AIUsageEventORM,
        KnowledgeArticleORM, KnowledgeChunkORM, KnowledgeConversationORM, KnowledgeMessageORM,
        KnowledgeFeedbackORM, KnowledgeEscalationORM,
        AgentRunORM, AgentActionORM, AgentApprovalORM, AgentEvaluationORM,
        WebhookDeliveryORM, PolicyEvaluationORM, ApprovalRequestORM,
        GovernanceAuditEventORM, PolicyDefinitionORM, SourceSignalORM,
        OutboxEventORM,
    )
    Base.metadata.create_all(bind=engine)
