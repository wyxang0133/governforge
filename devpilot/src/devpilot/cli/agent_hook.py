"""Universal Agent hook CLI for Codex, Claude Code, Cursor and custom agents."""
from __future__ import annotations

import argparse
import json
import os
import sys

import httpx


def _client() -> tuple[httpx.Client, str]:
    base_url = os.getenv("DEVPILOT_URL", "http://localhost:8000").rstrip("/")
    token = os.getenv("DEVPILOT_TOKEN", "")
    if not token:
        raise SystemExit("DEVPILOT_TOKEN is required")
    headers = {"Authorization": f"Bearer {token}", "X-Workspace-ID": os.getenv("DEVPILOT_WORKSPACE", "ai_platform")}
    return httpx.Client(base_url=base_url, headers=headers, timeout=20), base_url


def _json(value: str) -> dict:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise argparse.ArgumentTypeError("detail must be a JSON object")
    return payload


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="devpilot-agent-hook", description="Report coding-agent behavior to DevPilot")
    commands = root.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start"); start.add_argument("--external-id", required=True); start.add_argument("--provider", required=True); start.add_argument("--agent-name", required=True); start.add_argument("--task", required=True); start.add_argument("--requested-by", default="developer"); start.add_argument("--repository-id"); start.add_argument("--plan", action="append", default=[])
    action = commands.add_parser("action"); action.add_argument("--run-id", required=True); action.add_argument("--sequence", required=True, type=int); action.add_argument("--type", required=True, choices=["plan","file_read","file_write","file_delete","command","tool_call","dependency","test","pull_request"]); action.add_argument("--target"); action.add_argument("--command-text"); action.add_argument("--detail", type=_json, default={})
    complete = commands.add_parser("complete"); complete.add_argument("--run-id", required=True); complete.add_argument("--status", choices=["completed","failed","cancelled"], default="completed")
    return root


def main() -> None:
    args = parser().parse_args(); client, _ = _client()
    try:
        if args.command == "start":
            response = client.post("/api/agents/runs", json={"external_id": args.external_id, "provider": args.provider, "agent_name": args.agent_name, "task": args.task, "requested_by": args.requested_by, "repository_id": args.repository_id, "plan": args.plan})
        elif args.command == "action":
            response = client.post(f"/api/agents/runs/{args.run_id}/actions", json={"sequence": args.sequence, "action_type": args.type, "target": args.target, "command": args.command_text, "detail": args.detail})
        else:
            response = client.post(f"/api/agents/runs/{args.run_id}/complete", json={"status": args.status})
        response.raise_for_status(); print(json.dumps(response.json(), ensure_ascii=False))
    except httpx.HTTPStatusError as exc:
        print(exc.response.text, file=sys.stderr); raise SystemExit(1) from exc
    finally:
        client.close()


if __name__ == "__main__":
    main()
