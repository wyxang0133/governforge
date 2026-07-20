"""Correlation ID propagation."""
import re
from uuid import uuid4
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

VALID_TRACE = re.compile(r"^[A-Za-z0-9_.:-]{8,128}$")

class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Trace-ID", "")
        trace_id = incoming if VALID_TRACE.fullmatch(incoming) else uuid4().hex
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response

def get_trace_id(request: Request) -> str:
    return getattr(request.state, "trace_id", "unknown")
