"""Provider-neutral AI Coding policy engine."""
from dataclasses import dataclass, field

@dataclass
class PolicyEvidence:
    source_confidence: float = 0.0
    ci_status: str = "unknown"
    security_status: str = "unknown"
    test_coverage: float | None = None
    sensitive_files: list[str] = field(default_factory=list)
    estimated_cost_usd: float = 0.0
    human_approved: bool = False
    monthly_budget_exceeded: bool = False
    budget_evidence: list[dict] = field(default_factory=list)

@dataclass
class PolicyDecision:
    decision: str
    reasons: list[str]
    checks: dict[str, str]

def evaluate_policy(
    evidence: PolicyEvidence,
    *,
    cost_budget_usd: float = 5.0,
    min_coverage: float = 0.6,
    min_source_confidence: float = 0.7,
    require_security_scan: bool = True,
) -> PolicyDecision:
    checks: dict[str, str] = {}
    reasons: list[str] = []
    checks["source_confidence"] = "pass" if evidence.source_confidence >= min_source_confidence else "review"
    if checks["source_confidence"] == "review": reasons.append("AI 来源可信度不足")
    checks["ci_status"] = "pass" if evidence.ci_status.lower() == "passed" else "block"
    if checks["ci_status"] == "block": reasons.append("CI 未通过")
    security_ok = evidence.security_status.lower() in {"passed", "clean"}
    checks["security_status"] = "pass" if security_ok or not require_security_scan else "block"
    if checks["security_status"] == "block": reasons.append("安全扫描未通过或缺少结果")
    coverage_ok = evidence.test_coverage is not None and evidence.test_coverage >= min_coverage
    checks["test_coverage"] = "pass" if coverage_ok else "review"
    if not coverage_ok: reasons.append("测试覆盖率不足")
    checks["sensitive_files"] = "review" if evidence.sensitive_files else "pass"
    if evidence.sensitive_files: reasons.append("变更包含敏感文件")
    checks["cost_budget"] = "pass" if evidence.estimated_cost_usd <= cost_budget_usd else "block"
    if checks["cost_budget"] == "block": reasons.append("预估成本超过预算")
    checks["monthly_budget"] = "block" if evidence.monthly_budget_exceeded else "pass"
    if checks["monthly_budget"] == "block": reasons.append("月度预算硬上限已超出")
    approval_required = any(value == "review" for key, value in checks.items() if key != "human_approval")
    checks["human_approval"] = "pass" if evidence.human_approved or not approval_required else "review"
    if approval_required and not evidence.human_approved: reasons.append("需要人工审批")
    decision = "block" if "block" in checks.values() else ("review" if "review" in checks.values() else "allow")
    return PolicyDecision(decision, reasons, checks)
