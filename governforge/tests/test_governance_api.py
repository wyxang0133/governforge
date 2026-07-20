def _pr_payload():
    return {
        "number": 42,
        "repository": {"id": 1001, "full_name": "acme/payments", "default_branch": "main"},
        "pull_request": {
            "number": 42, "title": "Harden payment validation", "state": "open",
            "user": {"login": "octocat"}, "head": {"sha": "abc123"},
            "additions": 20, "deletions": 4, "changed_files": 3,
            "labels": [{"name": "ai-assisted"}],
        },
    }


def test_webhook_is_idempotent_and_updates_scorecard(client):
    headers = {"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "delivery-1", "X-Workspace-ID": "ai_platform"}
    assert client.post("/api/integrations/github/webhook", headers=headers, json=_pr_payload()).json()["status"] == "processed"
    assert client.post("/api/integrations/github/webhook", headers=headers, json=_pr_payload()).json()["status"] == "duplicate"
    data = client.get("/api/governance/scorecard", headers={"X-Workspace-ID": "ai_platform"}).json()
    assert data["metrics"]["counts"]["pull_requests"] == 1
    assert data["metrics"]["ai_assisted_pr_rate"] == 1


def test_gateway_usage_is_idempotent(client):
    payload = {"external_id": "usage-1", "workspace_id": "ai_platform", "provider": "openai", "model": "gpt", "input_tokens": 100, "output_tokens": 20, "cost_usd": .03, "trace_id": "trace-1"}
    assert client.post("/api/integrations/gateway/usage", json=payload).json()["status"] == "accepted"
    assert client.post("/api/integrations/gateway/usage", json=payload).json()["status"] == "duplicate"
    assert len(client.get("/api/governance/usage").json()) == 1


def test_policy_creates_approval_and_audit(client):
    headers = {"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "delivery-policy", "X-Workspace-ID": "ai_platform"}
    client.post("/api/integrations/github/webhook", headers=headers, json=_pr_payload())
    pr_id = client.get("/api/governance/pull-requests").json()[0]["id"]
    gate = client.post("/api/governance/policy-gate/evaluate", json={"pull_request_id": pr_id, "source_confidence": .2, "ci_status": "passed", "security_status": "clean", "test_coverage": .8}).json()
    assert gate["decision"] == "review"
    approval_id = gate["approval_id"]
    decided = client.post(f"/api/governance/approvals/{approval_id}/decision", json={"decision": "approved", "reason": "owner reviewed evidence"})
    assert decided.status_code == 200
    events = client.get("/api/governance/audit").json()
    assert {event["event_type"] for event in events} >= {"policy.evaluated", "approval.approved"}


def test_ci_webhooks_feed_automatic_policy_evaluation(client):
    client.post("/api/integrations/github/webhook", headers={"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "delivery-pr-ci"}, json=_pr_payload())
    pr_id = client.get("/api/governance/pull-requests").json()[0]["id"]
    base = {"repository": {"id": 1001, "full_name": "acme/payments"}}
    for delivery, name, coverage in (("ci-1", "tests", .85), ("ci-2", "security-sast", None)):
        payload = {**base, "check_run": {"id": delivery, "head_sha": "abc123", "name": name, "status": "completed", "conclusion": "success", "coverage": coverage}}
        response = client.post("/api/integrations/github/webhook", headers={"X-GitHub-Event": "check_run", "X-GitHub-Delivery": delivery}, json=payload)
        assert response.status_code == 200
    decision = client.post(f"/api/governance/pull-requests/{pr_id}/evaluate").json()
    assert decision["decision"] == "allow"
    assert decision["checks"]["ci_status"] == "pass"
    assert decision["checks"]["security_status"] == "pass"


def test_cross_workspace_header_is_rejected(client):
    response = client.get("/api/governance/scorecard", headers={"X-Workspace-ID": "another_workspace"})
    assert response.status_code == 403


def test_metrics_exposes_governance_counters(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "governforge_policy_decisions_total" in response.text


def test_policy_versions_are_server_controlled(client):
    policies = client.get("/api/policies").json()
    assert policies[0]["version"] == 1
    created = client.post("/api/policies", json={"name": "Strict Policy", "min_source_confidence": .9, "min_test_coverage": .8, "cost_budget_usd": 2, "require_security_scan": True, "sensitive_patterns": ["infra/"]})
    assert created.status_code == 201
    assert created.json()["version"] == 2
    decision = client.post("/api/governance/policy-gate/evaluate", json={"source_confidence": .8, "ci_status": "passed", "security_status": "clean", "test_coverage": .9, "human_approved": False}).json()
    assert decision["policy"]["version"] == 2
    assert decision["checks"]["source_confidence"] == "review"


def test_pull_request_detail_contains_source_evidence(client):
    client.post("/api/integrations/github/webhook", headers={"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "detail-pr"}, json=_pr_payload())
    pr = client.get("/api/governance/pull-requests").json()[0]
    detail = client.get(f"/api/governance/pull-requests/{pr['id']}").json()
    assert detail["repository"]["full_name"] == "acme/payments"
    assert detail["source_signals"][0]["type"] == "github_label"


def test_outbox_marks_unconfigured_github_check_as_skipped(client):
    from governforge.core.database import SessionFactory
    from governforge.core.outbox import process_outbox_batch
    client.post("/api/integrations/github/webhook", headers={"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "outbox-pr"}, json=_pr_payload())
    pr_id = client.get("/api/governance/pull-requests").json()[0]["id"]
    client.post(f"/api/governance/pull-requests/{pr_id}/evaluate")
    with SessionFactory() as session:
        result = process_outbox_batch(session)
    assert result["skipped"] == 1


def test_ci_evidence_drives_sensitive_file_review(client):
    client.post("/api/integrations/github/webhook", headers={"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "sensitive-pr"}, json=_pr_payload())
    pr_id = client.get("/api/governance/pull-requests").json()[0]["id"]
    evidence = {
        "pull_request_id": pr_id,
        "external_id": "enterprise-ci-sensitive",
        "name": "security-sast",
        "conclusion": "success",
        "coverage": .9,
        "changed_files": ["infra/main.tf"],
        "ai_provenance": True,
        "evidence_ref": "ci://build/42",
    }
    assert client.post("/api/integrations/ci/evidence", json=evidence).status_code == 202
    decision = client.post(f"/api/governance/pull-requests/{pr_id}/evaluate").json()
    assert decision["decision"] == "review"
    assert decision["checks"]["sensitive_files"] == "review"


def test_identity_and_system_status_are_tenant_scoped(client):
    assert client.get("/api/auth/me").json() == {
        "username": "test-user", "workspace_id": "ai_platform", "role": "admin"
    }
    status = client.get("/api/system/status").json()
    assert status["workspace_id"] == "ai_platform"
    assert set(status["outbox"]) == {"pending", "failed"}
    assert "checks_enabled" in status["github"]


def test_failed_outbox_can_be_audited_and_requeued(client):
    from governforge.core.database import SessionFactory
    from governforge.models.governance import OutboxEventORM
    with SessionFactory() as session:
        item = OutboxEventORM(workspace_id="ai_platform", aggregate_type="pull_request", aggregate_id="missing", event_type="github.check.requested", payload={}, status="failed", attempts=5, last_error="simulated outage")
        session.add(item); session.commit(); event_id = item.id
    dead = client.get("/api/system/outbox/dead-letters").json()
    assert dead[0]["id"] == event_id and dead[0]["attempts"] == 5
    assert client.post(f"/api/system/outbox/{event_id}/requeue").json()["status"] == "pending"
    assert any(event["event_type"] == "outbox.requeued" for event in client.get("/api/governance/audit").json())


def test_team_policy_is_strictly_inherited_and_chain_is_preserved(client):
    client.post("/api/integrations/github/webhook", headers={"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "scoped-policy-pr"}, json=_pr_payload())
    repo = client.get("/api/governance/repositories").json()[0]
    pr_id = client.get("/api/governance/pull-requests").json()[0]["id"]
    team = client.post("/api/access/teams", json={"name": "Policy Team", "slug": "policy-team"}).json()
    client.post(f"/api/access/teams/{team['id']}/repositories", json={"repository_id": repo["id"], "permission": "evaluate"})
    created = client.post("/api/policies", json={"name": "Team Strict", "scope_type": "team", "scope_id": team["id"], "min_source_confidence": .9, "min_test_coverage": .8, "cost_budget_usd": 2, "require_security_scan": True, "sensitive_patterns": []})
    assert created.status_code == 201
    decision = client.post("/api/governance/policy-gate/evaluate", json={"pull_request_id": pr_id, "source_confidence": .8, "ci_status": "passed", "security_status": "clean", "test_coverage": .9}).json()
    assert decision["checks"]["source_confidence"] == "review"
    assert [item["scope_type"] for item in decision["policy"]["chain"]] == ["workspace", "team"]


def test_policy_as_code_yaml_round_trip(client):
    client.get("/api/policies")
    exported = client.get("/api/policies/export")
    assert exported.status_code == 200 and "kind: PolicyBundle" in exported.text
    imported = client.post("/api/policies/import", content=exported.text, headers={"Content-Type": "application/yaml"})
    assert imported.status_code == 201
    assert imported.json()["created"][0]["version"] == 2


def test_monthly_hard_budget_blocks_pull_request(client):
    client.post("/api/integrations/github/webhook", headers={"X-GitHub-Event": "pull_request", "X-GitHub-Delivery": "budget-pr"}, json=_pr_payload())
    repo = client.get("/api/governance/repositories").json()[0]; pr_id = client.get("/api/governance/pull-requests").json()[0]["id"]
    budget = client.put("/api/budgets", json={"scope_type": "workspace", "limit_usd": .01, "warning_ratio": .8, "hard_limit": True})
    assert budget.status_code == 200
    usage = {"external_id": "budget-usage", "workspace_id": "ai_platform", "repository_id": repo["id"], "pull_request_id": pr_id, "provider": "openai", "model": "gpt", "cost_usd": 1, "trace_id": "budget-trace"}
    client.post("/api/integrations/gateway/usage", json=usage)
    client.post("/api/integrations/ci/evidence", json={"pull_request_id": pr_id, "external_id": "security-budget", "name": "security-sast", "conclusion": "success", "coverage": .9, "ai_provenance": True})
    decision = client.post(f"/api/governance/pull-requests/{pr_id}/evaluate").json()
    assert decision["decision"] == "block" and decision["checks"]["monthly_budget"] == "block"
