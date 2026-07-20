"""Low-cardinality Prometheus metrics."""
from time import perf_counter
from fastapi import Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

HTTP_REQUESTS = Counter("devpilot_http_requests_total", "HTTP requests", ["method", "path", "status"])
HTTP_LATENCY = Histogram("devpilot_http_request_duration_seconds", "HTTP latency", ["method", "path"])
POLICY_DECISIONS = Counter("devpilot_policy_decisions_total", "Policy decisions", ["decision", "version"])
WEBHOOK_EVENTS = Counter("devpilot_webhook_events_total", "Webhook events", ["provider", "event", "status"])
OUTBOX_EVENTS = Counter("devpilot_outbox_events_total", "Outbox processing outcomes", ["status"])
OUTBOX_BATCH_ERRORS = Counter("devpilot_outbox_batch_errors_total", "Uncaught outbox batch errors")
OUTBOX_LAST_SUCCESS = Gauge("devpilot_outbox_last_success_unixtime", "Unix time of the last successful outbox batch")
OUTBOX_BATCH_SIZE = Histogram("devpilot_outbox_batch_size", "Selected events per outbox batch", buckets=(0, 1, 5, 10, 25, 50))
KNOWLEDGE_QUERIES = Counter("devpilot_knowledge_queries_total", "Knowledge assistant outcomes", ["category", "provider", "outcome"])
KNOWLEDGE_FEEDBACK = Counter("devpilot_knowledge_feedback_total", "Knowledge assistant feedback", ["rating"])
KNOWLEDGE_ESCALATIONS = Counter("devpilot_knowledge_escalations_total", "Knowledge assistant expert escalations", ["queue"])

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = perf_counter()
        status = 500
        try:
            response = await call_next(request); status = response.status_code; return response
        finally:
            route = request.scope.get("route"); path = getattr(route, "path", request.url.path); duration = perf_counter() - started
            HTTP_REQUESTS.labels(request.method, path, str(status)).inc(); HTTP_LATENCY.labels(request.method, path).observe(duration)
            logger.bind(trace_id=getattr(request.state, "trace_id", "unknown"), method=request.method, path=path, status=status, duration_ms=round(duration * 1000, 2)).info("http.request")

def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
