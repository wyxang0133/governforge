"""Reliable Outbox processor for external side effects."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from governforge.core.github_checks import GitHubChecksClient
from governforge.core.metrics import OUTBOX_EVENTS
from governforge.models.governance import ApprovalRequestORM, CIRunORM, GovernanceAuditEventORM, OutboxEventORM, PolicyEvaluationORM, PullRequestORM, RepositoryORM

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
            pr = session.get(PullRequestORM, event.aggregate_id)
            repo = session.get(RepositoryORM, pr.repository_id) if pr else None
            if not pr or not repo: raise ValueError("pull request or repository not found")
            if event.event_type == "github.check.requested":
                if event.payload.get("head_sha") and event.payload["head_sha"] != pr.head_sha:
                    result = {"status": "skipped", "reason": "STALE_HEAD_SHA"}
                else:
                    result = client.publish(repo.full_name, pr.head_sha, event.payload, repo.installation_id)
            elif event.event_type == "github.merge.requested":
                if not repo.auto_merge_enabled:
                    result = {"status": "skipped", "reason": "AUTO_MERGE_DISABLED"}
                elif event.payload.get("head_sha") != pr.head_sha:
                    result = {"status": "skipped", "reason": "HEAD_SHA_CHANGED"}
                elif pr.state != "open":
                    result = {"status": "skipped", "reason": "PR_NOT_OPEN"}
                else:
                    evaluation = session.get(PolicyEvaluationORM, event.payload.get("evaluation_id"))
                    pending = session.scalar(select(ApprovalRequestORM.id).where(
                        ApprovalRequestORM.pull_request_id == pr.id,
                        ApprovalRequestORM.status == "pending",
                    ))
                    runs = list(session.scalars(select(CIRunORM).where(
                        CIRunORM.pull_request_id == pr.id,
                        (CIRunORM.head_sha == pr.head_sha) | CIRunORM.head_sha.is_(None),
                    )))
                    completed = [run for run in runs if run.status == "completed" or run.conclusion]
                    green = bool(completed) and all((run.conclusion or "").lower() in {"success", "passed", "neutral", "skipped"} for run in completed)
                    override = session.get(ApprovalRequestORM, event.payload.get("approval_id")) if event.payload.get("approval_id") else None
                    policy_allowed = bool(evaluation and (evaluation.decision == "allow" or (override and override.status == "approved")))
                    if not policy_allowed: result = {"status": "skipped", "reason": "POLICY_NOT_ALLOW"}
                    elif pending: result = {"status": "skipped", "reason": "APPROVAL_PENDING"}
                    elif not green: result = {"status": "skipped", "reason": "CI_NOT_GREEN"}
                    elif not repo.installation_id: result = {"status": "skipped", "reason": "INSTALLATION_MISSING"}
                    else: result = client.merge(repo.full_name, pr.external_number, pr.head_sha,
                                                event.payload.get("merge_method", "squash"), repo.installation_id)
            else:
                raise ValueError(f"unsupported outbox event: {event.event_type}")
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
