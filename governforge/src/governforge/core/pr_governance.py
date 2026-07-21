"""Deterministic, idempotent PR evidence evaluation shared by API and webhooks."""
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from governforge.core.budgets import applicable_budgets
from governforge.core.metrics import POLICY_DECISIONS
from governforge.core.policies import get_effective_policy
from governforge.core.policy_gate import PolicyEvidence, evaluate_policy
from governforge.models.governance import (
    AIUsageEventORM, ApprovalRequestORM, CIRunORM, GovernanceAuditEventORM,
    OutboxEventORM, PolicyEvaluationORM, PullRequestORM, RepositoryORM, SourceSignalORM,
)


def evaluate_pull_request_record(session: Session, workspace_id: str, pr: PullRequestORM, trace_id: str | None) -> dict:
    runs = list(session.scalars(select(CIRunORM).where(CIRunORM.pull_request_id == pr.id)))
    usage = list(session.scalars(select(AIUsageEventORM).where(AIUsageEventORM.pull_request_id == pr.id)))
    signals = list(session.scalars(select(SourceSignalORM).where(SourceSignalORM.pull_request_id == pr.id)))
    policy = get_effective_policy(session, workspace_id, pr.repository_id)
    budget_evidence = applicable_budgets(session, workspace_id, pr.repository_id)
    current_runs = [run for run in runs if not run.head_sha or run.head_sha == pr.head_sha]
    completed = [run for run in current_runs if run.status == "completed" or run.conclusion]
    ci_passed = bool(completed) and all((run.conclusion or "").lower() in {"success", "passed", "neutral", "skipped"} for run in completed)
    security_runs = [run for run in completed if any(word in run.name.lower() for word in ("security", "sast", "dependency", "secret", "trivy"))]
    security_passed = bool(security_runs) and all((run.conclusion or "").lower() in {"success", "passed", "neutral"} for run in security_runs)
    coverages = [run.coverage for run in completed if run.coverage is not None]
    current_signals = [signal for signal in signals if (signal.payload or {}).get("head_sha", pr.head_sha) == pr.head_sha]
    changed_paths = [path for signal in current_signals for path in (signal.payload or {}).get("changed_files", [])]
    sensitive_files = sorted({path for path in changed_paths if any(pattern.lower() in path.lower() for pattern in policy.sensitive_patterns)})
    evidence = {
        "head_sha": pr.head_sha, "source_confidence": pr.source_confidence,
        "ci_status": "passed" if ci_passed else ("failed" if completed else "unknown"),
        "security_status": "clean" if security_passed else "unknown",
        "test_coverage": max(coverages) if coverages else None,
        "sensitive_files": sensitive_files, "estimated_cost_usd": sum(item.cost_usd for item in usage),
        "human_approved": False,
        "monthly_budget_exceeded": any(item["hard_limit"] and item["exceeded"] for item in budget_evidence),
        "budget_evidence": budget_evidence, "changed_files_count": len(set(changed_paths)),
        "evidence_complete": bool(changed_paths) and bool(completed), "policy_chain": policy.policy_chain,
    }
    result = evaluate_policy(PolicyEvidence(**{key: evidence[key] for key in (
        "source_confidence", "ci_status", "security_status", "test_coverage", "sensitive_files",
        "estimated_cost_usd", "human_approved", "monthly_budget_exceeded", "budget_evidence",
    )}), cost_budget_usd=policy.cost_budget_usd, min_coverage=policy.min_test_coverage,
        min_source_confidence=policy.min_source_confidence, require_security_scan=policy.require_security_scan)
    # Evidence completeness is a separate hard gate.  A policy must never allow a
    # PR merely because synthetic/partial CI data happens to satisfy the scoring
    # thresholds; the current SHA must have both changed-file evidence and a
    # completed CI result before any allow decision is possible.
    if not evidence["evidence_complete"]:
        result.checks["evidence_completeness"] = "block"
        result.reasons.append("当前 head SHA 的变更文件或 CI 证据不完整")
        result.decision = "block"
    previous = session.scalar(select(PolicyEvaluationORM).where(
        PolicyEvaluationORM.pull_request_id == pr.id,
    ).order_by(desc(PolicyEvaluationORM.created_at)))
    if previous and previous.evidence and previous.evidence.get("head_sha") == pr.head_sha and previous.evidence == evidence:
        return {"evaluation_id": previous.id, "decision": previous.decision, "reasons": previous.reasons,
                "checks": previous.checks, "duplicate": True, "approval_id": None}
    for approval in session.scalars(select(ApprovalRequestORM).where(
        ApprovalRequestORM.pull_request_id == pr.id, ApprovalRequestORM.status == "pending",
    )):
        approval.status = "superseded"
        approval.reason = "Superseded by newer evidence evaluation"
    policy_version = f"v{policy.version}"
    POLICY_DECISIONS.labels(result.decision, policy_version).inc()
    evaluation = PolicyEvaluationORM(workspace_id=workspace_id, pull_request_id=pr.id, policy_id=policy.id,
        policy_version=policy_version, decision=result.decision, reasons=result.reasons,
        checks=result.checks, evidence=evidence)
    session.add(evaluation); session.flush()
    approval = None
    if result.decision in {"review", "block"}:
        approval = ApprovalRequestORM(workspace_id=workspace_id, pull_request_id=pr.id,
            evaluation_id=evaluation.id, required_role="security" if result.decision == "block" else "owner")
        session.add(approval); session.flush()
    session.add(GovernanceAuditEventORM(workspace_id=workspace_id, event_type="policy.pr.auto_evaluated",
        entity_type="policy_evaluation", entity_id=evaluation.id, trace_id=trace_id,
        payload={"decision": result.decision, "head_sha": pr.head_sha, "approval_id": approval.id if approval else None,
                 "evidence_complete": evidence["evidence_complete"]}))
    session.add(OutboxEventORM(workspace_id=workspace_id, aggregate_type="pull_request", aggregate_id=pr.id,
        event_type="github.check.requested", dedupe_key=f"check:{pr.id}:{pr.head_sha}:{evaluation.id}",
        payload={"evaluation_id": evaluation.id, "decision": result.decision,
                 "checks": result.checks, "reasons": result.reasons, "head_sha": pr.head_sha}))
    repo = session.get(RepositoryORM, pr.repository_id)
    if result.decision == "allow" and repo and repo.auto_merge_enabled:
        session.add(OutboxEventORM(workspace_id=workspace_id, aggregate_type="pull_request", aggregate_id=pr.id,
            event_type="github.merge.requested", dedupe_key=f"merge:{pr.id}:{pr.head_sha}",
            payload={"evaluation_id": evaluation.id, "head_sha": pr.head_sha, "merge_method": repo.merge_method}))
    return {"evaluation_id": evaluation.id, "decision": result.decision, "reasons": result.reasons,
            "checks": result.checks, "approval_id": approval.id if approval else None,
            "policy": {"id": policy.id, "version": policy.version, "name": policy.name, "chain": policy.policy_chain}}
