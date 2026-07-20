"""Optional OpenTelemetry export; disabled when no OTLP endpoint is configured."""
from fastapi import FastAPI
from devpilot.config import AppSettings


def configure_telemetry(app: FastAPI, settings: AppSettings) -> None:
    if not settings.otel_exporter_otlp_endpoint:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    from devpilot.core.database import engine
    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name, "deployment.environment": settings.environment}),
        sampler=TraceIdRatioBased(settings.otel_sample_ratio),
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint.rstrip("/") + "/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, excluded_urls="/livez,/health,/metrics")
    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=provider)
