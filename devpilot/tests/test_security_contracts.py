import hashlib
import hmac
import json
from devpilot.core.auth import create_access_token


def test_webhook_rejects_invalid_signature(client, monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "webhook-test-secret")
    body = json.dumps({"repository": {"id": 1}}).encode()
    response = client.post("/api/integrations/github/webhook", content=body, headers={"Content-Type": "application/json", "X-GitHub-Event": "ping", "X-GitHub-Delivery": "bad-signature", "X-Hub-Signature-256": "sha256=invalid"})
    assert response.status_code == 401


def test_webhook_accepts_valid_signature(client, monkeypatch):
    secret = "webhook-test-secret"
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", secret)
    body = json.dumps({"repository": {"id": 2, "full_name": "acme/demo"}}, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    response = client.post("/api/integrations/github/webhook", content=body, headers={"Content-Type": "application/json", "X-GitHub-Event": "ping", "X-GitHub-Delivery": "valid-signature", "X-Hub-Signature-256": signature})
    assert response.status_code == 200


def test_member_cannot_decide_approval(client):
    token = create_access_token({"sub": "member", "tenant_id": "ai_platform", "role": "member", "type": "access"})
    response = client.post("/api/governance/approvals/unknown/decision", headers={"Authorization": f"Bearer {token}"}, json={"decision": "approved", "reason": "not permitted"})
    assert response.status_code == 403


def test_github_installation_cannot_move_between_workspaces(client):
    first = client.post("/api/integrations/github/installations", json={"installation_id": "123", "account_login": "acme"})
    assert first.status_code == 201
    other_token = create_access_token({"sub": "other-admin", "tenant_id": "other", "role": "admin", "type": "access"})
    conflict = client.post(
        "/api/integrations/github/installations",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"installation_id": "123", "account_login": "acme"},
    )
    assert conflict.status_code == 409


def test_registered_installation_overrides_untrusted_workspace_header(client):
    client.post("/api/integrations/github/installations", json={"installation_id": "456", "account_login": "acme"})
    payload = {"installation": {"id": 456}, "repository": {"id": 99, "full_name": "acme/secure"}}
    response = client.post(
        "/api/integrations/github/webhook",
        headers={"X-GitHub-Event": "ping", "X-GitHub-Delivery": "mapped", "X-Workspace-ID": "attacker"},
        json=payload,
    )
    assert response.status_code == 200
    repos = client.get("/api/governance/repositories").json()
    assert repos[0]["full_name"] == "acme/secure"


def test_refresh_token_is_rotated_and_replay_revokes_family(client):
    registered = client.post("/api/auth/register", json={"username": "rotate-user", "password": "Rotate!2026", "tenant_id": "rotate"})
    assert registered.status_code == 200
    original_refresh = registered.json()["refresh_token"]
    rotated = client.post("/api/auth/refresh")
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != original_refresh
    replay = client.post("/api/auth/refresh", json={"refresh_token": original_refresh})
    assert replay.status_code == 401
    # Replaying an ancestor revokes the active token family, not only the old token.
    assert client.post("/api/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]}).status_code == 401


def test_member_only_sees_team_granted_repositories(client):
    from devpilot.core.database import SessionFactory
    from devpilot.core.password_hash import hash_password
    from devpilot.models.user import UserORM
    with SessionFactory() as session:
        session.add(UserORM(username="scoped-member", hashed_password=hash_password("Scoped!2026"), tenant_id="ai_platform", role="member")); session.commit()
    for index, name in ((701, "acme/one"), (702, "acme/two")):
        payload = {"repository": {"id": index, "full_name": name}}
        assert client.post("/api/integrations/github/webhook", headers={"X-GitHub-Event": "ping", "X-GitHub-Delivery": f"repo-{index}"}, json=payload).status_code == 200
    repos = client.get("/api/governance/repositories").json()
    team = client.post("/api/access/teams", json={"name": "Payments", "slug": "payments"}).json()
    client.post(f"/api/access/teams/{team['id']}/members", json={"username": "scoped-member", "role": "member"})
    client.post(f"/api/access/teams/{team['id']}/repositories", json={"repository_id": repos[0]["id"], "permission": "read"})
    member_token = create_access_token({"sub": "scoped-member", "tenant_id": "ai_platform", "role": "member", "type": "access"})
    visible = client.get("/api/governance/repositories", headers={"Authorization": f"Bearer {member_token}"}).json()
    assert [item["id"] for item in visible] == [repos[0]["id"]]
    assert client.get("/api/governance/audit", headers={"Authorization": f"Bearer {member_token}"}).status_code == 403


def test_local_password_auth_can_be_disabled_for_enterprise_sso(client, monkeypatch):
    monkeypatch.setenv("ALLOW_LOCAL_AUTH", "false")
    assert client.get("/api/auth/config").json()["local_auth_enabled"] is False
    response = client.post("/api/auth/login", json={"username": "any-user", "password": "AnyPass!2026"})
    assert response.status_code == 403


def test_scim_deprovisioning_revokes_active_sessions(client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from devpilot.core.database import SessionFactory
    from devpilot.models.user import AuthSessionORM
    monkeypatch.setenv("SCIM_ENABLED", "true"); monkeypatch.setenv("SCIM_BEARER_TOKEN", "scim-test-token")
    headers = {"Authorization": "Bearer scim-test-token"}
    created = client.post("/api/scim/v2/Users", headers=headers, json={"userName": "scim-user", "active": True})
    assert created.status_code == 201
    user_id = int(created.json()["id"])
    with SessionFactory() as session:
        session.add(AuthSessionORM(id="scim-session", user_id=user_id, refresh_jti_hash="x" * 64, expires_at=datetime.now(timezone.utc) + timedelta(days=1))); session.commit()
    disabled = client.patch(f"/api/scim/v2/Users/{user_id}", headers=headers, json={"Operations": [{"op": "Replace", "path": "active", "value": False}]})
    assert disabled.status_code == 200 and disabled.json()["active"] is False
    with SessionFactory() as session:
        assert session.get(AuthSessionORM, "scim-session").revoked_at is not None
