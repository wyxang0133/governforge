"""Inject defensive HTTP response headers.

Input validation belongs to typed endpoint schemas. Mutating Starlette's
immutable query parameter internals is unsafe and can corrupt valid requests.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
class SecurityMiddleware(BaseHTTPMiddleware):
    """Add browser security headers without changing request data."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

        return response
