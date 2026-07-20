from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from governforge.core.agents import sweep_stale_runs
from governforge.core.database import SessionFactory
from governforge.models.governance import AgentRunORM, CostEventORM, IntegrationCredentialORM


def _agent_credential(client, scopes=None):
    response = client.post("/api/integrations/agent-credentials", json={
        "name": "test-machine", "provider": "test", "expires_in_days": 30,
        "scopes": scopes or ["agent:write"],
    })
    assert response.status_code == 201
    return response.json()["token"]


def test_versioned_agent_event_contract_conflict_approval_and_completion(client):
    token = _agent_credential(client)
    headers = {"X-Agent-Token": token, "X-Workspace-ID": "ai_platform"}
    started = {"schema_version": "v1", "event_id": "event-start-1", "event_type": "run.started",
        "run_external_id": "native-codex-1", "provider": "codex", "agent_name": "Codex",
        "requested_by": "developer", "task": "修改认证并测试", "timeout_seconds": 120}
    first = client.post("/api/agent-events/v1/events", json=started, headers=headers)
    assert first.status_code == 202
    assert client.post("/api/agent-events/v1/events", json=started | {"event_id": "event-start-retry"}, headers=headers).json()["status"] == "duplicate"
    conflict = client.post("/api/agent-events/v1/events", json=started | {"event_id": "event-start-conflict", "task": "different task"}, headers=headers)
    assert conflict.status_code == 409

    risky = {"schema_version": "v1", "event_id": "event-action-1", "event_type": "action.pre",
        "run_external_id": "native-codex-1", "provider": "codex", "agent_name": "Codex",
        "requested_by": "developer", "sequence": 1, "action_type": "file_write", "target": "src/auth/session.py"}
    pre = client.post("/api/agent-events/v1/events", json=risky, headers=headers)
    assert pre.status_code == 202 and pre.json()["decision"] == "ask"
    approval_id = pre.json()["approval_id"]
    assert client.get(f"/api/agent-events/v1/approvals/{approval_id}", headers=headers).json()["status"] == "pending"
    assert client.post(f"/api/agents/approvals/{approval_id}/decision", json={"decision":"approved","reason":"reviewed rollback"}).status_code == 200
    assert client.post("/api/agent-events/v1/events", json=risky | {"event_id":"event-action-retry"}, headers=headers).json()["decision"] == "allow"
    completed_action = client.post("/api/agent-events/v1/events", json=risky | {
        "event_id":"event-action-completed", "event_type":"action.completed"}, headers=headers)
    assert completed_action.status_code == 202

    test_action = risky | {"event_id":"event-test-1", "sequence":2, "action_type":"test", "target":"tests/test_auth.py", "detail":{"conclusion":"passed"}}
    assert client.post("/api/agent-events/v1/events", json=test_action, headers=headers).status_code == 202
    assert client.post("/api/agent-events/v1/events", json=test_action | {"event_id":"event-test-done", "event_type":"action.completed"}, headers=headers).status_code == 202
    finished = client.post("/api/agent-events/v1/events", json={"schema_version":"v1", "event_id":"event-stop-1",
        "event_type":"run.completed", "run_external_id":"native-codex-1", "provider":"codex",
        "agent_name":"Codex", "outcome":"completed"}, headers=headers)
    assert finished.status_code == 202
    assert finished.json()["run_status"] == "completed"


def test_stale_agent_run_times_out_fail_closed(client):
    with SessionFactory() as session:
        run = AgentRunORM(workspace_id="ai_platform", external_id="stale-run", provider="codex",
            agent_name="Codex", task="lost task", requested_by="developer", timeout_seconds=30,
            heartbeat_at=datetime.now(timezone.utc)-timedelta(minutes=2))
        session.add(run); session.commit(); run_id=run.id
    with SessionFactory() as session:
        assert sweep_stale_runs(session) == 1
        session.commit()
        assert session.get(AgentRunORM, run_id).status == "timed_out"


def test_model_gateway_routes_usage_and_tco(client, monkeypatch):
    token = _agent_credential(client, ["model:invoke"])
    monkeypatch.setenv("MODEL_PROVIDER_TEST_API_KEY", "unit-test-key")
    route = client.post("/api/model-gateway/routes", json={"model_alias":"coding-default",
        "provider":"test-provider", "upstream_model":"test-model", "base_url":"https://models.example/v1",
        "api_key_env":"MODEL_PROVIDER_TEST_API_KEY", "priority":100, "timeout_seconds":5,
        "max_retries":0, "input_cost_per_million":2, "output_cost_per_million":4})
    assert route.status_code == 201

    def fake_post(url, **kwargs):
        return httpx.Response(200, json={"id":"chatcmpl-test", "choices":[{"message":{"role":"assistant","content":"ok"}}],
            "usage":{"prompt_tokens":1000,"completion_tokens":500}}, request=httpx.Request("POST", url))
    monkeypatch.setattr("governforge.api.model_gateway.httpx.post", fake_post)
    response = client.post("/api/model-gateway/v1/chat/completions", json={"model":"coding-default",
        "messages":[{"role":"user","content":"hello"}]}, headers={"Authorization":f"Bearer {token}",
        "X-Workspace-ID":"ai_platform", "X-Trace-ID":"trace-model-1"})
    assert response.status_code == 200
    assert response.json()["governance"]["provider"] == "test-provider"
    assert response.json()["governance"]["cost_usd"] == 0.004
    summary = client.get("/api/model-gateway/cost-events")
    assert summary.status_code == 200 and summary.json()["total_usd"] == 0.004
    with SessionFactory() as session:
        assert session.scalar(select(CostEventORM).where(CostEventORM.trace_id == "trace-model-1")) is not None
        assert session.scalar(select(IntegrationCredentialORM).where(IntegrationCredentialORM.name == "test-machine")).token_hash != token
