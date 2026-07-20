"""Scorecard aggregation queries."""
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import Session
from devpilot.models.governance import AIUsageEventORM, CIRunORM, PullRequestORM


def build_scorecard(session: Session, workspace_id: str) -> dict:
    prs = list(session.scalars(select(PullRequestORM).where(PullRequestORM.workspace_id == workspace_id)))
    ci_runs = list(session.scalars(select(CIRunORM).where(CIRunORM.workspace_id == workspace_id)))
    usage = list(session.scalars(select(AIUsageEventORM).where(AIUsageEventORM.workspace_id == workspace_id)))
    total = len(prs)
    merged = [pr for pr in prs if pr.state == "merged" or pr.merged_at]
    assisted = [pr for pr in prs if pr.source_confidence >= 0.5]
    first_runs = {}
    for run in sorted(ci_runs, key=lambda item: ((item.started_at.timestamp() if item.started_at else 0), item.attempt)):
        if run.pull_request_id and run.pull_request_id not in first_runs:
            first_runs[run.pull_request_id] = run
    first_pass = sum(1 for run in first_runs.values() if (run.conclusion or "").lower() in {"success", "passed"})
    rerun_prs = len({run.pull_request_id for run in ci_runs if run.pull_request_id and run.attempt > 1})
    cycles = [(pr.merged_at - pr.opened_at).total_seconds() / 3600 for pr in merged if pr.merged_at and pr.opened_at]
    total_cost = sum(event.cost_usd for event in usage)
    return {
        "ai_assisted_pr_rate": round(len(assisted) / total, 4) if total else 0,
        "source_confidence": round(sum(pr.source_confidence for pr in prs) / total, 4) if total else 0,
        "first_ci_pass_rate": round(first_pass / len(first_runs), 4) if first_runs else 0,
        "rework_rate": round(rerun_prs / total, 4) if total else 0,
        "cycle_time_hours": round(sum(cycles) / len(cycles), 2) if cycles else 0,
        "cost_per_merged_pr_usd": round(total_cost / len(merged), 4) if merged else 0,
        "counts": {"pull_requests": total, "merged": len(merged), "ai_usage_events": len(usage)},
    }
