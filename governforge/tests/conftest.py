"""Shared test fixtures with a self-contained SQLite database."""
import os

test_database_url = os.getenv("TEST_DATABASE_URL")
if test_database_url:
    database_name = test_database_url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not database_name.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must target a database ending in _test")
    os.environ["DATABASE_URL"] = test_database_url
else:
    os.environ.setdefault("DATABASE_URL", "sqlite:///./governforge_test.db")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-with-at-least-32-bytes")
os.environ.setdefault("METRICS_PASSWORD", "test-metrics")

import pytest
from fastapi.testclient import TestClient

from governforge.main import create_app


@pytest.fixture(scope="session")
def app():
    from governforge.core.database import Base, engine, init_db
    from governforge.models import governance, user  # noqa: F401
    Base.metadata.drop_all(bind=engine)
    init_db()
    return create_app()


@pytest.fixture
def clean_tasks(app):
    from governforge.core.database import engine
    from sqlalchemy import text
    with engine.begin() as connection:
        for table in ("governance_audit_events", "outbox_events", "cost_events", "model_routes", "integration_credentials", "agent_evaluations", "agent_approvals", "agent_actions", "agent_runs", "approval_requests", "policy_evaluations", "source_signals", "budget_allocations", "policy_definitions", "knowledge_feedback", "knowledge_escalations", "knowledge_messages", "knowledge_conversations", "knowledge_chunks", "knowledge_articles", "ai_usage_events", "ci_runs", "pull_requests", "repository_grants", "team_memberships", "teams", "webhook_deliveries", "repositories", "github_installations", "auth_sessions", "users"):
            connection.execute(text(f"DELETE FROM {table}"))
    yield


@pytest.fixture
def client(clean_tasks, app) -> TestClient:
    with TestClient(app) as test_client:
        from governforge.core.auth import create_access_token
        test_client.headers["Authorization"] = f"Bearer {create_access_token({'sub': 'test-user', 'tenant_id': 'ai_platform', 'role': 'admin', 'type': 'access'})}"
        yield test_client
