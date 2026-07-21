from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from governforge.core.agents import sweep_stale_runs
from governforge.core.database import SessionFactory
from governforge.models.governance import AgentRunORM, AIUsageEventORM, CostEventORM, IntegrationCredentialORM


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


def test_model_gateway_fails_over_to_next_priority_and_marks_degraded(client, monkeypatch):
    token = _agent_credential(client, ["model:invoke"])
    monkeypatch.setenv("MODEL_PROVIDER_PRIMARY_API_KEY", "primary-key")
    monkeypatch.setenv("MODEL_PROVIDER_SECONDARY_API_KEY", "secondary-key")
    payload = {"model_alias": "fallback-test", "upstream_model": "test-model", "timeout_seconds": 5,
               "max_retries": 0, "input_cost_per_million": 1, "output_cost_per_million": 1}
    for priority, provider, env_name in ((10, "primary", "MODEL_PROVIDER_PRIMARY_API_KEY"),
                                         (20, "secondary", "MODEL_PROVIDER_SECONDARY_API_KEY")):
        response = client.post("/api/model-gateway/routes", json=payload | {
            "provider": provider, "priority": priority, "base_url": "https://models.example/v1",
            "api_key_env": env_name,
        })
        assert response.status_code == 201

    calls: list[str] = []

    def fake_post(url, **kwargs):
        calls.append(kwargs["headers"]["Authorization"])
        if len(calls) == 1:
            return httpx.Response(503, json={"error": "primary unavailable"}, request=httpx.Request("POST", url))
        return httpx.Response(200, json={"id": "fallback", "choices": [],
                                        "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
                             request=httpx.Request("POST", url))

    monkeypatch.setattr("governforge.api.model_gateway.httpx.post", fake_post)
    response = client.post("/api/model-gateway/v1/chat/completions",
                           json={"model": "fallback-test", "messages": [{"role": "user", "content": "ping"}]},
                           headers={"Authorization": f"Bearer {token}", "X-Workspace-ID": "ai_platform",
                                    "X-Trace-ID": "trace-fallback-1"})
    assert response.status_code == 200
    assert response.json()["governance"]["provider"] == "secondary"
    assert response.json()["governance"]["degraded"] is True
    assert calls == ["Bearer primary-key", "Bearer secondary-key"]


def test_model_gateway_hard_budget_blocks_before_upstream(client, monkeypatch):
    token = _agent_credential(client, ["model:invoke"])
    monkeypatch.setenv("MODEL_PROVIDER_BUDGET_API_KEY", "budget-key")
    route = client.post("/api/model-gateway/routes", json={
        "model_alias": "budget-test", "provider": "budget", "upstream_model": "test-model",
        "base_url": "https://models.example/v1", "api_key_env": "MODEL_PROVIDER_BUDGET_API_KEY",
        "priority": 10, "timeout_seconds": 5, "max_retries": 0,
    })
    assert route.status_code == 201
    budget = client.put("/api/budgets", json={"scope_type": "workspace", "scope_id": "*",
                                                "period": "2026-07", "limit_usd": 0.01,
                                                "warning_ratio": 0.8, "hard_limit": True})
    assert budget.status_code in (200, 201)
    with SessionFactory() as session:
        session.add(AIUsageEventORM(workspace_id="ai_platform", external_id="budget-spend-1",
                                    provider="budget", model="test-model", input_tokens=1,
                                    output_tokens=1, cost_usd=1, source="test"))
        session.commit()
    monkeypatch.setattr("governforge.api.model_gateway.httpx.post",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("upstream must not be called")))
    response = client.post("/api/model-gateway/v1/chat/completions",
                           json={"model": "budget-test", "messages": [{"role": "user", "content": "blocked"}]},
                           headers={"Authorization": f"Bearer {token}", "X-Workspace-ID": "ai_platform"})
    assert response.status_code == 402
    assert response.json()["detail"] == "MODEL_BUDGET_EXCEEDED"
