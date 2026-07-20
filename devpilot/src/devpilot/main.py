"""DevPilot FastAPI application factory."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from devpilot.api import api_router
from devpilot.config import AppSettings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = app.state.settings
    issues = settings.production_readiness_issues()
    if issues:
        raise RuntimeError("invalid production configuration: " + "; ".join(issues))
    if settings.environment != "production":
        from devpilot.core.database import init_db
        init_db()
    logger.info("DevPilot started environment={} service={}", settings.environment, settings.service_name)
    yield
    logger.info("DevPilot stopped")


def create_app() -> FastAPI:
    settings = AppSettings()
    from devpilot.core.logging import configure_logging
    configure_logging(settings)
    app = FastAPI(
        title="DevPilot Enterprise AI Engineering API",
        description="AI Coding governance control plane and grounded enterprise knowledge agent",
        version="1.1.0",
        lifespan=lifespan,
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[item.strip() for item in settings.cors_origins.split(",") if item.strip()],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Trace-ID", "X-Workspace-ID", "X-GitHub-Event", "X-GitHub-Delivery", "X-Hub-Signature-256"],
    )
    from devpilot.core.trace_middleware import TraceMiddleware
    from devpilot.core.security_middleware import SecurityMiddleware
    from devpilot.core.tenant_isolation_middleware import TenantIsolationMiddleware
    from devpilot.core.metrics import MetricsMiddleware, metrics_response
    app.add_middleware(TraceMiddleware)
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(TenantIsolationMiddleware)
    app.add_middleware(MetricsMiddleware)

    from devpilot.api.health import router as health_router
    app.include_router(health_router)
    app.include_router(api_router, prefix="/api")
    app.add_api_route("/metrics", metrics_response, methods=["GET"], include_in_schema=False)
    from devpilot.core.telemetry import configure_telemetry
    configure_telemetry(app, settings)
    return app


app = create_app()
