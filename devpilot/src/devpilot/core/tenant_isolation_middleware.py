"""DevPilot Pro 租户隔离中间件

在请求进入业务逻辑前，从 JWT Token 中提取租户上下文并注入到 request.state。
公开路径（health check 等）无需认证，JWT 无效时返回 401 而非回退到默认租户。
"""

import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from devpilot.core.auth import decode_access_token
from devpilot.core.tenant_middleware import (
    TENANT_ISOLATION_ENABLED,
    TenantContext,
    get_tenant_from_token,
    settings,
)

# 不需要 JWT 认证的公开路径
PUBLIC_PATHS = {"/health", "/api/health", "/metrics", "/api/auth", "/api/scim", "/api/integrations/github/webhook"}


class TenantIsolationMiddleware(BaseHTTPMiddleware):
    """租户隔离中间件

    从 JWT Token 中提取 tenant_id 和 user_id，注入到 request.state.tenant_context。
    公开路径（/health, /metrics）跳过认证。
    其他路径 JWT 无效时返回 401，不静默回退。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 公开路径：生成匿名租户上下文
        if any(path.startswith(pub) for pub in PUBLIC_PATHS):
            request.state.tenant_context = TenantContext(
                tenant_id=settings.default_tenant_id,
                trace_id=str(uuid.uuid4())[:8],
            )
            return await call_next(request)

        # 需要认证的路径
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else request.cookies.get("devpilot_access")
        if token:
            try:
                payload = decode_access_token(token)
                tenant_context = get_tenant_from_token(payload)
                request.state.tenant_context = tenant_context
            except Exception:
                # decode_access_token 已抛出 HTTPException(401)，直接返回
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Token 无效或已过期"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        else:
            return JSONResponse(
                status_code=401,
                content={"detail": "缺少认证 Token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)
