"""OpenTelemetry setup: traces, metrics, and logs → Grafana Cloud OTLP gateway (no collector)."""
import logging
import os

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_initialized = False


def _grafana_headers() -> dict[str, str] | None:
    """Build Basic-auth header for Grafana Cloud OTLP gateway, if credentials are set."""
    auth = os.environ.get("GRAFANA_CLOUD_AUTH")  # base64("<instance_id>:<api_key>")
    if auth:
        return {"Authorization": f"Basic {auth}"}
    return None


def setup_telemetry() -> None:
    global _initialized
    if _initialized:
        return

    # Grafana Cloud OTLP gateway — set GRAFANA_CLOUD_OTLP_ENDPOINT in .env
    # e.g. https://otlp-gateway-prod-eu-west-0.grafana.net/otlp
    endpoint = os.environ.get(
        "GRAFANA_CLOUD_OTLP_ENDPOINT",
        os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"),
    )
    service_name = os.environ.get("OTEL_SERVICE_NAME", "cpg-supply-chain")
    environment = os.environ.get("DEPLOYMENT_ENVIRONMENT", "development")
    headers = _grafana_headers() or {}

    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": "cpg",
        "service.version": "1.0.0",
        "deployment.environment": environment,
        "industry": "cpg",
    })

    # --- Traces ---
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", headers=headers)
        )
    )
    trace.set_tracer_provider(tracer_provider)

    # --- Metrics ---
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics", headers=headers),
        export_interval_millis=30_000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # --- Logs ---
    log_provider = LoggerProvider(resource=resource)
    log_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(endpoint=f"{endpoint}/v1/logs", headers=headers)
        )
    )
    set_logger_provider(log_provider)

    # Bridge Python standard logging → OTel logs
    from opentelemetry.sdk._logs import LoggingHandler
    otel_handler = LoggingHandler(level=logging.DEBUG, logger_provider=log_provider)
    logging.getLogger().addHandler(otel_handler)

    # Auto-instrument LangChain / LangGraph
    try:
        from opentelemetry.instrumentation.langchain import LangchainInstrumentor
        LangchainInstrumentor().instrument()
    except ImportError:
        logger.warning("opentelemetry-instrumentation-langchain not installed; LangChain spans disabled")

    _initialized = True
    logger.info("OpenTelemetry initialised → %s (env=%s)", endpoint, environment)
