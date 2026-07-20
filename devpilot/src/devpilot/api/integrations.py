"""Inbound GitHub and LLM Gateway integration endpoints."""
import hashlib
import hmac
import httpx
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from devpilot.config import AppSettings
from devpilot.core.auth import get_current_user
from devpilot.core.database import get_session
from devpilot.core.metrics import WEBHOOK_EVENTS
from devpilot.core.trace_middleware import get_trace_id
from devpilot.models.governance import (
    AIUsageEventORM, CIRunORM, GovernanceAuditEventORM, PullRequestORM,
    GitHubInstallationORM, RepositoryORM, SourceSignalORM, WebhookDeliveryORM, WorkspaceORM,
)
from devpilot.core.workspace import get_workspace_id
from devpilot.core.github_checks import GitHubChecksClient

router = APIRouter(tags=["integrations"])


def _verify_github_signature(body: bytes, signature: str | None) -> None:
    secret = AppSettings().github_webhook_secret.get_secret_value()
    if not secret:
        if AppSettings().environment == "production":
            raise HTTPException(503, "GitHub webhook secret is not configured")
        return
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(401, "invalid GitHub webhook signature")


def _workspace(session: Session, workspace_id: str) -> WorkspaceORM:
    item = session.get(WorkspaceORM, workspace_id)
    if item is None:
        item = WorkspaceORM(id=workspace_id, name=workspace_id, slug=workspace_id.lower().replace("_", "-"))
        session.add(item)
        session.flush()
    return item


def _webhook_workspace(session: Session, payload: dict, development_fallback: str) -> tuple[str, str | None]:
    installation_id = str((payload.get("installation") or {}).get("id") or "") or None
    if installation_id:
        mapping = session.scalar(select(GitHubInstallationORM).where(
            GitHubInstallationORM.installation_id == installation_id,
            GitHubInstallationORM.active.is_(True),
        ))
        if mapping:
            return mapping.workspace_id, installation_id
    if AppSettings().environment == "production":
        raise HTTPException(404, "GitHub App installation is not registered")
    return development_fallback, installation_id


class GitHubInstallationIn(BaseModel):
    installation_id: str = Field(min_length=1, max_length=128)
    account_login: str | None = Field(None, max_length=255)


@router.get("/github/status")
def github_status(session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    settings = AppSettings()
    installations = session.scalars(select(GitHubInstallationORM).where(GitHubInstallationORM.workspace_id == workspace_id).order_by(desc(GitHubInstallationORM.created_at))).all()
    repositories = session.scalars(select(RepositoryORM).where(RepositoryORM.workspace_id == workspace_id, RepositoryORM.provider == "github").order_by(RepositoryORM.full_name)).all()
    return {
        "configured": settings.github_app_configured and bool(settings.github_webhook_secret.get_secret_value()),
        "app_id_configured": bool(settings.github_app_id), "private_key_configured": bool(settings.github_app_private_key_value),
        "webhook_secret_configured": bool(settings.github_webhook_secret.get_secret_value()), "checks_enabled": settings.github_checks_enabled,
        "app_slug": settings.github_app_slug, "install_url": f"https://github.com/apps/{settings.github_app_slug}/installations/new" if settings.github_app_slug else None,
        "installations": [{"id": item.id, "installation_id": item.installation_id, "account_login": item.account_login, "active": item.active, "created_at": item.created_at} for item in installations],
        "repositories": [{"id": item.id, "full_name": item.full_name, "installation_id": item.installation_id, "active": item.active, "html_url": item.html_url} for item in repositories],
    }


@router.post("/github/installations", status_code=201)
def register_github_installation(
    data: GitHubInstallationIn,
    session: Session = Depends(get_session),
    workspace_id: str = Depends(get_workspace_id),
    user: dict = Depends(get_current_user),
) -> dict:
    if user.get("role") not in {"admin", "owner"}:
        raise HTTPException(403, "admin or owner role required")
    _workspace(session, workspace_id)
    existing = session.scalar(select(GitHubInstallationORM).where(GitHubInstallationORM.installation_id == data.installation_id))
    if existing and existing.workspace_id != workspace_id:
        raise HTTPException(409, "installation is already assigned to another workspace")
    item = existing or GitHubInstallationORM(
        workspace_id=workspace_id,
        installation_id=data.installation_id,
        created_by=user.get("sub", "unknown"),
    )
    item.account_login = data.account_login
    item.active = True
    session.add(item)
    session.flush()
    session.add(GovernanceAuditEventORM(
        workspace_id=workspace_id, actor_id=user.get("sub", "unknown"),
        event_type="integration.github.installation.registered",
        entity_type="github_installation", entity_id=item.id,
        payload={"installation_id": item.installation_id, "account_login": item.account_login},
    ))
    session.commit()
    return {"id": item.id, "installation_id": item.installation_id, "account_login": item.account_login, "active": item.active}


@router.post("/github/installations/{installation_id}/sync")
def sync_github_repositories(installation_id: str, request: Request, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in {"admin", "owner"}: raise HTTPException(403, "admin or owner role required")
    mapping = session.scalar(select(GitHubInstallationORM).where(GitHubInstallationORM.workspace_id == workspace_id, GitHubInstallationORM.installation_id == installation_id, GitHubInstallationORM.active.is_(True)))
    if mapping is None: raise HTTPException(404, "GitHub installation is not registered")
    client = GitHubChecksClient()
    if not client.settings.github_app_configured: raise HTTPException(503, "GitHub App ID/private key is not configured")
    try:
        response = httpx.get(f"{client.settings.github_api_url.rstrip('/')}/installation/repositories", headers={"Authorization": f"Bearer {client.installation_token(installation_id)}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}, timeout=20)
        response.raise_for_status(); payload = response.json()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"GitHub repository sync failed: {type(exc).__name__}") from exc
    count = 0
    for data in payload.get("repositories", []):
        external_id = str(data.get("id", "")); item = session.scalar(select(RepositoryORM).where(RepositoryORM.workspace_id == workspace_id, RepositoryORM.provider == "github", RepositoryORM.external_id == external_id))
        if item is None:
            item = RepositoryORM(workspace_id=workspace_id, provider="github", external_id=external_id, full_name=data.get("full_name", "unknown")); session.add(item)
        item.full_name, item.default_branch, item.installation_id, item.html_url, item.active = data.get("full_name", item.full_name), data.get("default_branch", "main"), installation_id, data.get("html_url"), True; count += 1
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", "unknown"), event_type="integration.github.repositories.synced", entity_type="github_installation", entity_id=mapping.id, trace_id=get_trace_id(request), payload={"repositories": count}))
    session.commit(); return {"installation_id": installation_id, "repositories": count}


@router.delete("/github/installations/{installation_id}", status_code=204)
def disconnect_github_installation(installation_id: str, request: Request, session: Session = Depends(get_session), workspace_id: str = Depends(get_workspace_id), user: dict = Depends(get_current_user)) -> None:
    if user.get("role") not in {"admin", "owner"}: raise HTTPException(403, "admin or owner role required")
    item = session.scalar(select(GitHubInstallationORM).where(GitHubInstallationORM.workspace_id == workspace_id, GitHubInstallationORM.installation_id == installation_id))
    if item is None: raise HTTPException(404, "GitHub installation is not registered")
    item.active = False
    for repo in session.scalars(select(RepositoryORM).where(RepositoryORM.workspace_id == workspace_id, RepositoryORM.installation_id == installation_id)):
        repo.active = False
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, actor_id=user.get("sub", "unknown"), event_type="integration.github.disconnected", entity_type="github_installation", entity_id=item.id, trace_id=get_trace_id(request), payload={"installation_id": installation_id}))
    session.commit()


@router.post("/github/webhook")
async def github_webhook(
    request: Request,
    session: Session = Depends(get_session),
    x_github_event: str = Header("unknown"),
    x_github_delivery: str = Header(...),
    x_hub_signature_256: str | None = Header(None),
    x_workspace_id: str = Header("ai_platform"),
) -> dict[str, Any]:
    body = await request.body()
    _verify_github_signature(body, x_hub_signature_256)
    if session.scalar(select(WebhookDeliveryORM).where(WebhookDeliveryORM.delivery_id == x_github_delivery)):
        WEBHOOK_EVENTS.labels("github", x_github_event, "duplicate").inc()
        return {"status": "duplicate", "delivery_id": x_github_delivery}
    payload = await request.json()
    x_workspace_id, installation_id = _webhook_workspace(session, payload, x_workspace_id)
    _workspace(session, x_workspace_id)
    delivery = WebhookDeliveryORM(delivery_id=x_github_delivery, event_type=x_github_event)
    session.add(delivery)
    repo_data = payload.get("repository") or {}
    external_repo_id = str(repo_data.get("id", ""))
    repo = session.scalar(select(RepositoryORM).where(
        RepositoryORM.workspace_id == x_workspace_id,
        RepositoryORM.external_id == external_repo_id,
    ))
    if repo is None and external_repo_id:
        repo = RepositoryORM(workspace_id=x_workspace_id, external_id=external_repo_id, full_name=repo_data.get("full_name", "unknown"), default_branch=repo_data.get("default_branch", "main"))
        session.add(repo)
        session.flush()
    if repo:
        repo.full_name = repo_data.get("full_name", repo.full_name)
        repo.html_url = repo_data.get("html_url", repo.html_url)
        repo.installation_id = installation_id or repo.installation_id
    if x_github_event == "pull_request" and repo:
        data = payload.get("pull_request") or {}
        number = int(payload.get("number") or data.get("number"))
        pr = session.scalar(select(PullRequestORM).where(PullRequestORM.repository_id == repo.id, PullRequestORM.external_number == number))
        if pr is None:
            pr = PullRequestORM(workspace_id=x_workspace_id, repository_id=repo.id, external_number=number, head_sha=(data.get("head") or {}).get("sha", ""))
            session.add(pr)
        pr.title = data.get("title", "")
        pr.author = (data.get("user") or {}).get("login", "unknown")
        pr.state = "merged" if data.get("merged") else data.get("state", "open")
        pr.additions, pr.deletions, pr.changed_files = data.get("additions", 0), data.get("deletions", 0), data.get("changed_files", 0)
        session.flush()
        label_names = {label.get("name") for label in (data.get("labels") or []) if isinstance(label, dict)}
        if "ai-assisted" in label_names:
            pr.source_confidence = max(pr.source_confidence or 0.0, 0.7)
            session.add(SourceSignalORM(workspace_id=x_workspace_id, pull_request_id=pr.id, signal_type="github_label", confidence=0.7, evidence_ref=f"github:{repo.full_name}#{number}", payload={"label": "ai-assisted"}))
        else:
            pr.source_confidence = pr.source_confidence or 0.0
        if data.get("merged_at"):
            pr.merged_at = datetime.fromisoformat(data["merged_at"].replace("Z", "+00:00"))
    elif x_github_event in {"check_run", "workflow_run"} and repo:
        data = payload.get(x_github_event) or {}
        head_sha = data.get("head_sha") or data.get("head_commit", {}).get("id", "")
        pr = session.scalar(select(PullRequestORM).where(PullRequestORM.repository_id == repo.id, PullRequestORM.head_sha == head_sha))
        external_id = str(data.get("id", ""))
        run = session.scalar(select(CIRunORM).where(CIRunORM.repository_id == repo.id, CIRunORM.external_id == external_id))
        if run is None:
            previous = session.scalars(select(CIRunORM).where(CIRunORM.pull_request_id == (pr.id if pr else None))).all()
            run = CIRunORM(workspace_id=x_workspace_id, repository_id=repo.id, pull_request_id=pr.id if pr else None, external_id=external_id, attempt=len(previous) + 1)
            session.add(run)
        run.name = data.get("name", x_github_event)
        run.status = data.get("status", "queued")
        run.conclusion = data.get("conclusion")
        run.coverage = data.get("coverage")
    session.add(GovernanceAuditEventORM(workspace_id=x_workspace_id, event_type="integration.github.received", entity_type="webhook", entity_id=x_github_delivery, trace_id=get_trace_id(request), payload={"event": x_github_event}))
    delivery.status = "processed"
    session.commit()
    WEBHOOK_EVENTS.labels("github", x_github_event, "processed").inc()
    return {"status": "processed", "delivery_id": x_github_delivery}


class UsageIn(BaseModel):
    external_id: str
    workspace_id: str = "ai_platform"
    repository_id: str | None = None
    pull_request_id: str | None = None
    provider: str
    model: str
    input_tokens: int = Field(0, ge=0)
    output_tokens: int = Field(0, ge=0)
    cost_usd: float = Field(0, ge=0)
    trace_id: str | None = None
    source: str = "gateway"


class CIEvidenceIn(BaseModel):
    pull_request_id: str
    external_id: str
    name: str = "enterprise-ci"
    conclusion: str
    coverage: float | None = Field(None, ge=0, le=1)
    changed_files: list[str] = Field(default_factory=list, max_length=2000)
    ai_provenance: bool = False
    evidence_ref: str | None = None


@router.post("/gateway/usage", status_code=202)
def ingest_usage(data: UsageIn, request: Request, session: Session = Depends(get_session)) -> dict:
    # TenantIsolationMiddleware authenticates this endpoint. The body workspace
    # is additionally checked to prevent cross-tenant event injection.
    context = getattr(request.state, "tenant_context", None)
    if getattr(context, "tenant_id", None) != data.workspace_id:
        raise HTTPException(403, "cross-workspace usage injection denied")
    _workspace(session, data.workspace_id)
    existing = session.scalar(select(AIUsageEventORM).where(AIUsageEventORM.workspace_id == data.workspace_id, AIUsageEventORM.external_id == data.external_id))
    if existing:
        return {"status": "duplicate", "id": existing.id}
    event = AIUsageEventORM(**data.model_dump())
    session.add(event)
    session.flush()
    if data.pull_request_id:
        pr = session.get(PullRequestORM, data.pull_request_id)
        if pr and pr.workspace_id == data.workspace_id:
            pr.source_confidence = max(pr.source_confidence or 0.0, 0.95)
            session.add(SourceSignalORM(workspace_id=data.workspace_id, pull_request_id=pr.id, signal_type="gateway_trace", confidence=0.95, evidence_ref=data.trace_id, payload={"provider": data.provider, "model": data.model, "usage_event_id": event.id}))
    session.add(GovernanceAuditEventORM(workspace_id=data.workspace_id, event_type="integration.gateway.usage", entity_type="ai_usage_event", entity_id=event.id, trace_id=data.trace_id, payload={"model": data.model, "cost_usd": data.cost_usd}))
    session.commit()
    return {"status": "accepted", "id": event.id}


@router.post("/ci/evidence", status_code=202)
def ingest_ci_evidence(data: CIEvidenceIn, request: Request, session: Session = Depends(get_session)) -> dict:
    context = getattr(request.state, "tenant_context", None)
    workspace_id = getattr(context, "tenant_id", None)
    pr = session.scalar(select(PullRequestORM).where(PullRequestORM.id == data.pull_request_id, PullRequestORM.workspace_id == workspace_id))
    if pr is None: raise HTTPException(404, "pull request not found")
    run = session.scalar(select(CIRunORM).where(CIRunORM.repository_id == pr.repository_id, CIRunORM.external_id == data.external_id))
    if run is None:
        run = CIRunORM(workspace_id=workspace_id, repository_id=pr.repository_id, pull_request_id=pr.id, external_id=data.external_id, name=data.name, status="completed", conclusion=data.conclusion, coverage=data.coverage)
        session.add(run)
    else:
        run.status, run.conclusion, run.coverage = "completed", data.conclusion, data.coverage
    if data.ai_provenance:
        pr.source_confidence = max(pr.source_confidence or 0, .9)
        session.add(SourceSignalORM(workspace_id=workspace_id, pull_request_id=pr.id, signal_type="ci_provenance", confidence=.9, evidence_ref=data.evidence_ref, payload={"changed_files": data.changed_files, "external_id": data.external_id}))
    elif data.changed_files:
        session.add(SourceSignalORM(workspace_id=workspace_id, pull_request_id=pr.id, signal_type="ci_evidence", confidence=0, evidence_ref=data.evidence_ref, payload={"changed_files": data.changed_files, "external_id": data.external_id}))
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, event_type="integration.ci.evidence", entity_type="pull_request", entity_id=pr.id, trace_id=get_trace_id(request), payload={"external_id": data.external_id, "conclusion": data.conclusion, "coverage": data.coverage, "file_count": len(data.changed_files)}))
    session.commit()
    return {"status": "accepted", "ci_run_id": run.id}
