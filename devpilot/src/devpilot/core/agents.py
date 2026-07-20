"""Risk taxonomy and deterministic evaluation for enterprise coding agents."""
from __future__ import annotations

from dataclasses import dataclass
import re

from devpilot.models.governance import AgentActionORM

RISK_LABELS = {
    "secret_exposure": "密钥与凭据泄露", "privilege_escalation": "权限扩大", "dependency_risk": "高风险依赖",
    "test_bypass": "测试缺失或绕过", "sensitive_file_change": "敏感文件变更", "cost_anomaly": "模型成本异常",
    "unapproved_tool": "未经批准的工具", "destructive_operation": "破坏性操作", "data_exfiltration": "敏感数据外发",
    "policy_bypass": "策略绕过",
}
SENSITIVE_PATHS = ("auth", "security", "permission", "migration", "alembic", "deploy", ".github/workflows", "terraform", "payment", "secret")
DESTRUCTIVE_COMMANDS = (r"\brm\s+-rf\b", r"\bDROP\s+(TABLE|DATABASE)\b", r"\bgit\s+reset\s+--hard\b", r"\bkubectl\s+delete\b", r"\bRemove-Item\b.*-Recurse")
SECRET_PATTERNS = ("api_key", "private_key", "access_token", ".env", "credentials")
APPROVAL_LEVELS = {"high", "critical"}
LEVEL_WEIGHT = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass(frozen=True)
class RiskResult:
    risk_type: str | None
    level: str
    requires_approval: bool
    reason: str


def classify_action(action_type: str, target: str | None, command: str | None, detail: dict) -> RiskResult:
    text = " ".join([target or "", command or "", str(detail)]).lower()
    if action_type == "test":
        if detail.get("conclusion") in {"failed", "skipped"}:
            return RiskResult("test_bypass", "medium", False, "测试失败或被跳过")
        return RiskResult(None, "low", False, "测试已执行并产生可审计结果")
    if detail.get("policy_bypass"):
        return RiskResult("policy_bypass", "critical", True, "Agent 试图绕过企业策略或审批检查点")
    if action_type == "tool_call" and detail.get("contains_sensitive_data"):
        return RiskResult("data_exfiltration", "critical", True, "外部工具调用可能携带企业敏感数据")
    cost = detail.get("cost_usd")
    limit = detail.get("cost_limit_usd", 5)
    if isinstance(cost, (int, float)) and isinstance(limit, (int, float)) and cost > limit:
        return RiskResult("cost_anomaly", "high", True, "单次 Agent 操作的模型成本超过允许阈值")
    if any(re.search(pattern, command or "", re.IGNORECASE) for pattern in DESTRUCTIVE_COMMANDS):
        return RiskResult("destructive_operation", "critical", True, "检测到删除、强制回滚或破坏性基础设施命令")
    if any(item in text for item in SECRET_PATTERNS):
        return RiskResult("secret_exposure", "critical", True, "操作可能读取、修改或输出密钥凭据")
    if action_type in {"file_write", "file_delete", "command", "tool_call"} and any(path in text for path in SENSITIVE_PATHS):
        return RiskResult("sensitive_file_change", "high", True, "涉及认证、迁移、部署、支付或安全配置")
    if action_type == "tool_call" and not detail.get("approved_tool", False):
        return RiskResult("unapproved_tool", "high", True, "Agent 调用了未登记的外部工具")
    if action_type == "command" and any(word in text for word in ("sudo ", "chmod 777", "setfacl", "admin")):
        return RiskResult("privilege_escalation", "high", True, "命令可能扩大执行权限")
    if action_type == "dependency" and detail.get("severity") in {"high", "critical"}:
        return RiskResult("dependency_risk", detail["severity"], True, "依赖扫描发现高风险漏洞")
    return RiskResult(None, "low", False, "未发现需要阻断的 Agent 行为风险")


def max_level(*levels: str) -> str:
    return max(levels or ("low",), key=lambda value: LEVEL_WEIGHT.get(value, 0))


def evaluate_run(actions: list[AgentActionORM]) -> tuple[float, str, list[dict], dict]:
    findings = [{"type": action.risk_type, "label": RISK_LABELS.get(action.risk_type or "", action.risk_type), "level": action.risk_level, "action_id": action.id, "target": action.target} for action in actions if action.risk_type]
    critical = sum(item["level"] == "critical" for item in findings)
    high = sum(item["level"] == "high" for item in findings)
    medium = sum(item["level"] == "medium" for item in findings)
    tests = [item for item in actions if item.action_type == "test"]
    tests_passed = any((item.detail or {}).get("conclusion") in {"passed", "success"} for item in tests)
    rejected = sum(item.status == "rejected" for item in actions)
    pending = sum(item.status == "waiting_approval" for item in actions)
    score = max(0.0, 100 - critical * 35 - high * 18 - medium * 8 - rejected * 20 - pending * 10 - (0 if tests_passed else 15))
    decision = "block" if critical or rejected else "review" if high or pending or not tests_passed else "allow"
    metrics = {"actions": len(actions), "findings": len(findings), "tests_executed": len(tests), "tests_passed": tests_passed, "approval_required": sum(item.requires_approval for item in actions), "pending_approvals": pending}
    if not tests_passed:
        findings.append({"type": "test_bypass", "label": RISK_LABELS["test_bypass"], "level": "medium", "action_id": None, "target": None})
    return score, decision, findings, metrics
