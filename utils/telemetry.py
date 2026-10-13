from opentelemetry import trace as otel_trace      # renamed: your variable `trace` already exists
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

_provider = None

def init_tracing(endpoint: str = "http://localhost:4318/v1/traces"):
    global _provider
    if _provider is not None:
        return
    _provider = TracerProvider(resource=Resource.create({"service.name": "voice-agent"}))
    _provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint), schedule_delay_millis=1000))
    otel_trace.set_tracer_provider(_provider)

def shutdown_tracing():
    if _provider is not None:
        _provider.shutdown()          # flushes spans still waiting to be sent

tracer = otel_trace.get_tracer("voice-agent")