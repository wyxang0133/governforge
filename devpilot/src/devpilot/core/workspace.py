"""Authenticated workspace context dependency."""
from fastapi import Header, HTTPException, Request

def get_workspace_id(request: Request, x_workspace_id: str | None = Header(None)) -> str:
    context = getattr(request.state, "tenant_context", None)
    token_workspace = getattr(context, "tenant_id", None)
    if not token_workspace:
        raise HTTPException(401, "workspace context missing")
    if x_workspace_id and x_workspace_id != token_workspace:
        raise HTTPException(403, "cross-workspace access denied")
    return token_workspace
