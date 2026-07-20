from sqlalchemy import select

from devpilot.core.database import SessionFactory
from devpilot.core.agents import classify_action
from devpilot.models.governance import AgentActionORM, AgentApprovalORM, AgentEvaluationORM, GovernanceAuditEventORM


def test_agent_run_high_risk_action_requires_approval_and_evaluation(client):
    created = client.post("/api/agents/runs", json={"external_id": "codex-run-1", "provider": "codex", "agent_name": "Codex", "task": "修改认证和数据库迁移", "plan": ["修改文件", "执行测试"], "requested_by": "developer"})
    assert created.status_code == 201
    run_id = created.json()["id"]
    risky = client.post(f"/api/agents/runs/{run_id}/actions", json={"sequence": 1, "action_type": "file_write", "target": "migrations/0011_auth.py", "detail": {}})
    assert risky.status_code == 201
    assert risky.json()["requires_approval"] is True
    assert risky.json()["risk_type"] == "sensitive_file_change"
    assert risky.json()["status"] == "waiting_approval"
    approval_id = risky.json()["approval_id"]

    blocked_complete = client.post(f"/api/agents/runs/{run_id}/complete", json={"status": "completed"})
    assert blocked_complete.status_code == 409
    decision = client.post(f"/api/agents/approvals/{approval_id}/decision", json={"decision": "approved", "reason": "迁移已审查并具备回滚方案"})
    assert decision.status_code == 200
    test_action = client.post(f"/api/agents/runs/{run_id}/actions", json={"sequence": 2, "action_type": "test", "target": "tests/test_auth.py", "detail": {"conclusion": "passed"}})
    assert test_action.status_code == 201
    completed = client.post(f"/api/agents/runs/{run_id}/complete", json={"status": "completed"})
    assert completed.status_code == 200
    assert completed.json()["decision"] == "review"
    assert completed.json()["score"] > 50

    detail = client.get(f"/api/agents/runs/{run_id}")
    assert detail.status_code == 200
    assert len(detail.json()["actions"]) == 2
    assert detail.json()["evaluation"] is not None
    with SessionFactory() as session:
        assert session.scalar(select(AgentEvaluationORM).where(AgentEvaluationORM.run_id == run_id)) is not None
        assert session.scalar(select(GovernanceAuditEventORM).where(GovernanceAuditEventORM.event_type == "agent.run.evaluated")) is not None


def test_destructive_agent_action_can_be_rejected(client):
    run = client.post("/api/agents/runs", json={"external_id": "claude-run-1", "provider": "claude-code", "agent_name": "Claude Code", "task": "清理临时目录"}).json()
    action = client.post(f"/api/agents/runs/{run['id']}/actions", json={"sequence": 1, "action_type": "command", "command": "rm -rf /srv/app", "detail": {}})
    assert action.json()["risk_type"] == "destructive_operation"
    assert action.json()["risk_level"] == "critical"
    rejected = client.post(f"/api/agents/approvals/{action.json()['approval_id']}/decision", json={"decision": "rejected", "reason": "命令范围超出允许工作区"})
    assert rejected.status_code == 200
    assert rejected.json()["run_status"] == "blocked"


def test_agent_demo_dashboard_and_github_connection_status(client):
    demo = client.post("/api/agents/demo")
    assert demo.status_code == 201
    analytics = client.get("/api/agents/analytics")
    assert analytics.status_code == 200
    assert analytics.json()["runs"] == 1
    dashboard = client.get("/api/dashboard/overview")
    assert dashboard.status_code == 200
    assert dashboard.json()["kpis"]["agent_runs"] == 1
    github = client.get("/api/integrations/github/status")
    assert github.status_code == 200
    assert "installations" in github.json()


def test_agent_risk_taxonomy_covers_policy_data_and_cost():
    assert classify_action("tool_call", "external-mcp", None, {"policy_bypass": True}).risk_type == "policy_bypass"
    assert classify_action("tool_call", "external-mcp", None, {"contains_sensitive_data": True, "approved_tool": True}).risk_type == "data_exfiltration"
    assert classify_action("tool_call", "approved-model", None, {"approved_tool": True, "cost_usd": 9, "cost_limit_usd": 5}).risk_type == "cost_anomaly"
