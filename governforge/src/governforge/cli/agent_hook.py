"""GovernForge native hook adapter for Codex, Claude Code and custom agents."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

import httpx


def _client() -> httpx.Client:
    base_url = os.getenv("GOVERNFORGE_URL", "http://localhost:8000").rstrip("/")
    token = os.getenv("GOVERNFORGE_AGENT_TOKEN", "")
    if not token:
        raise SystemExit("GOVERNFORGE_AGENT_TOKEN is required")
    headers = {"X-Agent-Token": token, "X-Workspace-ID": os.getenv("GOVERNFORGE_WORKSPACE", "ai_platform")}
    return httpx.Client(base_url=base_url, headers=headers, timeout=30)


def _read_json() -> dict:
    try:
        value = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"invalid hook JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit("hook input must be a JSON object")
    return value


def _sequence(payload: dict) -> int:
    stable = str(payload.get("tool_use_id") or payload.get("tool_call_id") or payload.get("event_id") or
                 json.dumps(payload.get("tool_input") or {}, sort_keys=True))
    return int(hashlib.sha256(stable.encode()).hexdigest()[:8], 16) or 1


def _action(payload: dict) -> tuple[str, str | None, str | None, dict]:
    tool = str(payload.get("tool_name") or payload.get("tool") or "tool_call")
    tool_input = payload.get("tool_input") or payload.get("input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {"value": str(tool_input)}
    command = tool_input.get("cmd") or tool_input.get("command")
    target = tool_input.get("path") or tool_input.get("file_path") or tool_input.get("workdir") or tool
    lower = tool.lower()
    if lower in {"bash", "exec_command", "shell", "powershell"}:
        action_type = "command"
    elif lower in {"apply_patch", "edit", "write", "write_file"}:
        action_type = "file_write"
    elif "read" in lower or "search" in lower or lower in {"glob", "grep"}:
        action_type = "file_read"
    elif "test" in lower:
        action_type = "test"
    else:
        action_type = "tool_call"
    detail = {"tool": tool, "approved_tool": not lower.startswith("mcp__"), "hook_payload": {
        "permission_mode": payload.get("permission_mode"), "model": payload.get("model"),
    }}
    response = payload.get("tool_response") or payload.get("tool_result")
    if response is not None:
        detail["result_summary"] = str(response)[:500]
        detail["failed"] = bool(payload.get("is_error"))
    return action_type, str(target)[:1024] if target else None, str(command)[:10000] if command else None, detail


def _event(provider: str, payload: dict) -> dict:
    hook = str(payload.get("hook_event_name") or payload.get("hook_event") or "")
    session_id = str(payload.get("session_id") or payload.get("conversation_id") or uuid4())
    common = {
        "schema_version": "v1", "event_id": str(payload.get("tool_use_id") or f"{session_id}:{hook}:{uuid4()}"),
        "run_external_id": session_id, "provider": provider,
        "agent_name": "Codex" if provider == "codex" else "Claude Code",
        "requested_by": os.getenv("GOVERNFORGE_ACTOR", os.getenv("USERNAME", "developer")),
        "trace_id": session_id, "timeout_seconds": int(os.getenv("GOVERNFORGE_RUN_TIMEOUT_SECONDS", "900")),
    }
    if hook in {"SessionStart", "UserPromptSubmit"}:
        prompt = payload.get("prompt") or payload.get("user_prompt") or "Coding agent session"
        return {**common, "event_type": "run.started", "task": str(prompt)[:10000]}
    if hook in {"PreToolUse", "PermissionRequest"}:
        action_type, target, command, detail = _action(payload)
        return {**common, "event_type": "action.pre", "sequence": _sequence(payload),
                "action_type": action_type, "target": target, "command": command, "detail": detail}
    if hook == "PostToolUse":
        action_type, target, command, detail = _action(payload)
        return {**common, "event_type": "action.completed", "sequence": _sequence(payload),
                "action_type": action_type, "target": target, "command": command, "detail": detail}
    if hook in {"Stop", "SessionEnd"}:
        return {**common, "event_type": "run.completed", "outcome": "completed", "detail": {}}
    return {**common, "event_type": "run.heartbeat"}


def _hook_output(event_name: str, decision: str, reason: str) -> dict:
    mapped = "allow" if decision == "allow" else "deny"
    return {"hookSpecificOutput": {"hookEventName": event_name, "permissionDecision": mapped,
                                    "permissionDecisionReason": reason},
            "systemMessage": reason}


def _post_event(client: httpx.Client, event: dict) -> dict:
    response = client.post("/api/agent-events/v1/events", json=event)
    response.raise_for_status()
    return response.json()


def run_hook(provider: str) -> None:
    payload = _read_json()
    event = _event(provider, payload)
    hook_name = str(payload.get("hook_event_name") or "")
    try:
        with _client() as client:
            result = _post_event(client, event)
            approval_id = result.get("approval_id")
            if result.get("decision") == "ask" and approval_id:
                deadline = time.monotonic() + int(os.getenv("GOVERNFORGE_APPROVAL_WAIT_SECONDS", "300"))
                while time.monotonic() < deadline:
                    status = client.get(f"/api/agent-events/v1/approvals/{approval_id}").json()
                    if status["status"] == "approved":
                        result = {"decision": "allow", "reason": status.get("reason") or "Approved in GovernForge"}
                        break
                    if status["status"] == "rejected":
                        result = {"decision": "deny", "reason": status.get("reason") or "Rejected in GovernForge"}
                        break
                    time.sleep(2)
                else:
                    result = {"decision": "deny", "reason": "GovernForge approval timed out (fail closed)"}
    except (httpx.HTTPError, KeyError) as exc:
        read_only = event.get("action_type") == "file_read"
        allow_reads = os.getenv("GOVERNFORGE_FAIL_OPEN_READS", "false").lower() == "true"
        result = {"decision": "allow" if read_only and allow_reads else "deny",
                  "reason": f"GovernForge unavailable: {type(exc).__name__}; " +
                            ("read-only fail-open" if read_only and allow_reads else "fail-closed")}
    if hook_name in {"PreToolUse", "PermissionRequest"}:
        print(json.dumps(_hook_output(hook_name, result.get("decision", "allow"),
                                      result.get("reason") or result.get("risk_label") or "GovernForge policy passed"), ensure_ascii=False))


def install(provider: str, root: Path) -> None:
    command = "python -m governforge.cli.agent_hook hook --provider " + provider
    if provider == "codex":
        target = root / ".codex" / "hooks.json"
        data = {"description": "GovernForge coding-agent governance hooks", "hooks": {
            event: [{"matcher": "*", "hooks": [{"type": "command", "command": command, "timeout": 360}]}]
            for event in ("SessionStart", "PreToolUse", "PermissionRequest", "PostToolUse", "Stop")
        }}
    else:
        target = root / ".claude" / "settings.json"
        data = {"hooks": {event: [{"matcher": "*", "hooks": [{"type": "command", "command": command,
                                                                   "timeout": 360}]}]
                          for event in ("SessionStart", "PreToolUse", "PostToolUse", "Stop")}}
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise SystemExit(f"refusing to overwrite existing hook config: {target}")
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(target)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="governforge-agent-hook", description="Govern coding-agent behavior")
    commands = root.add_subparsers(dest="command", required=True)
    hook = commands.add_parser("hook"); hook.add_argument("--provider", choices=["codex", "claude-code"], required=True)
    setup = commands.add_parser("install"); setup.add_argument("--provider", choices=["codex", "claude-code"], required=True); setup.add_argument("--root", default=".")
    return root


def main() -> None:
    args = parser().parse_args()
    if args.command == "hook":
        run_hook(args.provider)
    else:
        install(args.provider, Path(args.root).resolve())


if __name__ == "__main__":
    main()
