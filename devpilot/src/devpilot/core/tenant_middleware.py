"""DevPilot Pro 租户隔离中间件

基于 JWT 中的 tenant_id 实现数据隔离，
跨租户访问统一返回 404 模糊错误防止枚举攻击。
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional

from devpilot.config import AppSettings
from devpilot.core.auth import get_current_user

settings = AppSettings()

# 租户隔离开关：始终启用
TENANT_ISOLATION_ENABLED = True


@dataclass
class TenantContext:
    """租户上下文

    封装当前请求的租户标识、追踪 ID 和用户 ID，
    供后续 API 层进行数据隔离判断。
    """

    tenant_id: str
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    user_id: Optional[str] = None


def get_tenant_from_request(headers: dict) -> TenantContext:
    """从请求 Headers 提取租户上下文

    优先级：请求头 X-Tenant-ID > AppSettings.default_tenant_id。
    未提供 trace_id 时自动生成。

    Args:
        headers: 请求头字典

    Returns:
        TenantContext 实例
    """
    tenant_id = headers.get("X-Tenant-ID", settings.default_tenant_id)
    trace_id = headers.get("X-Trace-ID", str(uuid.uuid4())[:8])
    return TenantContext(tenant_id=tenant_id, trace_id=trace_id)


def get_tenant_from_token(token_payload: dict) -> TenantContext:
    """从 JWT Token 提取租户上下文

    从 Token 载荷中读取 tenant_id 和 sub（用户 ID），
    未指定 tenant_id 时使用默认值。

    Args:
        token_payload: 解码后的 Token 数据字典

    Returns:
        TenantContext 实例
    """
    tenant_id = token_payload.get("tenant_id", settings.default_tenant_id)
    user_id = token_payload.get("sub")
    trace_id = str(uuid.uuid4())[:8]
    return TenantContext(tenant_id=tenant_id, trace_id=trace_id, user_id=user_id)
