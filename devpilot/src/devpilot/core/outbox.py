"""Reliable Outbox processor for external side effects."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from devpilot.core.github_checks import GitHubChecksClient
from devpilot.core.metrics import OUTBOX_EVENTS
from devpilot.models.governance import GovernanceAuditEventORM, OutboxEventORM, PullRequestORM, RepositoryORM

def process_outbox_batch(session: Session, limit: int = 50) -> dict:
    now = datetime.now(timezone.utc)
    # PostgreSQL workers lock different rows, so horizontally scaling the
    # worker cannot publish the same external side effect twice. SQLAlchemy
    # safely ignores this clause for the SQLite test database.
    events = list(session.scalars(
        select(OutboxEventORM)
        .where(OutboxEventORM.status == "pending", OutboxEventORM.available_at <= now)
        .order_by(OutboxEventORM.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ))
    client = GitHubChecksClient()
    processed = skipped = failed = 0
    for event in events:
        event.attempts += 1
        try:
            if event.event_type != "github.check.requested":
                raise ValueError(f"unsupported outbox event: {event.event_type}")
            pr = session.get(PullRequestORM, event.aggregate_id)
            repo = session.get(RepositoryORM, pr.repository_id) if pr else None
            if not pr or not repo: raise ValueError("pull request or repository not found")
            result = client.publish(repo.full_name, pr.head_sha, event.payload, repo.installation_id)
            event.status = result["status"]
            event.processed_at = now
            event.last_error = result.get("reason")
            processed += event.status == "processed"
            skipped += event.status == "skipped"
            OUTBOX_EVENTS.labels(event.status).inc()
            session.add(GovernanceAuditEventORM(workspace_id=event.workspace_id, event_type=f"outbox.{event.status}", entity_type="outbox_event", entity_id=event.id, payload=result))
        except Exception as exc:
            event.last_error = str(exc)[:2000]
            if event.attempts >= 5:
                event.status = "failed"; failed += 1
                OUTBOX_EVENTS.labels("failed").inc()
            else:
                event.available_at = now + timedelta(seconds=min(300, 2 ** event.attempts))
    session.commit()
    return {"selected": len(events), "processed": processed, "skipped": skipped, "failed": failed}
