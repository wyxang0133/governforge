from governforge.core.policy_gate import PolicyEvidence, evaluate_policy


def test_policy_allows_complete_low_risk_evidence():
    result = evaluate_policy(PolicyEvidence(source_confidence=.9, ci_status="passed", security_status="clean", test_coverage=.8, human_approved=True))
    assert result.decision == "allow"
    assert set(result.checks.values()) == {"pass"}


def test_policy_blocks_failed_ci_and_budget():
    result = evaluate_policy(PolicyEvidence(source_confidence=.9, ci_status="failed", security_status="clean", test_coverage=.8, estimated_cost_usd=12, human_approved=True), cost_budget_usd=5)
    assert result.decision == "block"
    assert result.checks["ci_status"] == "block"
    assert result.checks["cost_budget"] == "block"


def test_policy_reviews_incomplete_provenance():
    result = evaluate_policy(PolicyEvidence(ci_status="passed", security_status="clean", test_coverage=.8, human_approved=False))
    assert result.decision == "review"
