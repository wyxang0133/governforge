"""GitHub Checks adapter using short-lived GitHub App installation tokens."""
from datetime import datetime, timedelta, timezone
import httpx
import jwt
from governforge.config import AppSettings

_token_cache: dict[str, tuple[str, datetime]] = {}

class GitHubChecksClient:
    def __init__(self, settings: AppSettings | None = None):
        self.settings = settings or AppSettings()

    @property
    def configured(self) -> bool:
        return self.settings.github_checks_enabled and (
            self.settings.github_app_configured
            or bool(self.settings.github_checks_token.get_secret_value())
        )

    def _installation_token(self, installation_id: str | None) -> str:
        static_token = self.settings.github_checks_token.get_secret_value()
        if not self.settings.github_app_configured:
            if not static_token:
                raise RuntimeError("GitHub authentication is not configured")
            return static_token
        if not installation_id:
            raise RuntimeError("GitHub installation id is required for App authentication")
        cached = _token_cache.get(installation_id)
        now = datetime.now(timezone.utc)
        if cached and cached[1] > now + timedelta(minutes=2):
            return cached[0]
        private_key = self.settings.github_app_private_key_value.replace("\\n", "\n")
        app_jwt = jwt.encode(
            {"iat": now - timedelta(seconds=60), "exp": now + timedelta(minutes=9), "iss": self.settings.github_app_id},
            private_key,
            algorithm="RS256",
        )
        response = httpx.post(
            f"{self.settings.github_api_url.rstrip('/')}/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {app_jwt}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        _token_cache[installation_id] = (data["token"], expires_at)
        return data["token"]

    def installation_token(self, installation_id: str) -> str:
        """Return a short-lived installation token for trusted server-side sync."""
        return self._installation_token(installation_id)

    def publish(self, repository: str, head_sha: str, payload: dict, installation_id: str | None = None) -> dict:
        if not self.configured:
            return {"status": "skipped", "reason": "GitHub Checks is not configured"}
        decision = payload.get("decision", "review")
        conclusion = {"allow": "success", "review": "neutral", "block": "failure"}.get(decision, "neutral")
        reasons = payload.get("reasons") or ([payload.get("reason")] if payload.get("reason") else [])
        response = httpx.post(
            f"{self.settings.github_api_url.rstrip('/')}/repos/{repository}/check-runs",
            headers={"Authorization": f"Bearer {self._installation_token(installation_id)}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            json={"name": "GovernForge Policy Gate", "head_sha": head_sha, "status": "completed", "conclusion": conclusion, "output": {"title": f"GovernForge decision: {decision}", "summary": "\n".join(reasons) or "All configured policy checks passed."}},
            timeout=15,
        )
        response.raise_for_status()
        return {"status": "processed", "external_id": str(response.json().get("id", ""))}

    def pull_request_files(self, repository: str, number: int, installation_id: str) -> list[str]:
        token = self._installation_token(installation_id)
        files: list[str] = []
        page = 1
        while page <= 20:
            response = httpx.get(
                f"{self.settings.github_api_url.rstrip('/')}/repos/{repository}/pulls/{number}/files",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                         "X-GitHub-Api-Version": "2022-11-28"}, params={"per_page": 100, "page": page}, timeout=20)
            response.raise_for_status()
            batch = response.json(); files.extend(str(item.get("filename")) for item in batch if item.get("filename"))
            if len(batch) < 100: break
            page += 1
        return files

    def merge(self, repository: str, number: int, head_sha: str, merge_method: str, installation_id: str) -> dict:
        token = self._installation_token(installation_id)
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        pr_response = httpx.get(f"{self.settings.github_api_url.rstrip('/')}/repos/{repository}/pulls/{number}",
                                  headers=headers, timeout=20)
        pr_response.raise_for_status(); remote = pr_response.json()
        if remote.get("state") != "open": return {"status": "skipped", "reason": "PR_NOT_OPEN"}
        if (remote.get("head") or {}).get("sha") != head_sha: return {"status": "skipped", "reason": "HEAD_SHA_CHANGED"}
        if remote.get("mergeable") is False or remote.get("mergeable_state") in {"dirty", "blocked", "behind"}:
            return {"status": "skipped", "reason": f"PR_NOT_MERGEABLE:{remote.get('mergeable_state')}"}
        checks = httpx.get(f"{self.settings.github_api_url.rstrip('/')}/repos/{repository}/commits/{head_sha}/check-runs",
                           headers=headers, params={"per_page": 100}, timeout=20)
        checks.raise_for_status()
        relevant = [item for item in checks.json().get("check_runs", []) if item.get("name") != "GovernForge Policy Gate"]
        if not relevant: return {"status": "skipped", "reason": "REQUIRED_CHECKS_MISSING"}
        allowed = {"success", "neutral", "skipped"}
        if any(item.get("status") != "completed" or item.get("conclusion") not in allowed for item in relevant):
            return {"status": "skipped", "reason": "REQUIRED_CHECKS_NOT_GREEN"}
        response = httpx.put(f"{self.settings.github_api_url.rstrip('/')}/repos/{repository}/pulls/{number}/merge",
            headers=headers, json={"sha": head_sha, "merge_method": merge_method}, timeout=20)
        if response.status_code in {405, 409, 422}:
            return {"status": "skipped", "reason": f"GITHUB_MERGE_REJECTED:{response.status_code}"}
        response.raise_for_status(); data = response.json()
        return {"status": "processed" if data.get("merged") else "skipped",
                "reason": data.get("message"), "merge_sha": data.get("sha")}
