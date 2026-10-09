"""Observability: OpenTelemetry spans + MLflow tracing, both optional.
Without the packages the app still records its own per-step trace (shown in the UI).
  OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318  -> spans to Jaeger / any OTLP collector
  MLFLOW_TRACKING_URI=http://localhost:5000          -> traces + eval runs in MLflow
"""
from __future__ import annotations

import contextlib
import os
import time

_tracer = None
_mlflow = None
try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    _prov = TracerProvider(resource=Resource.create({"service.name": "hr-ops-copilot"}))
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        _prov.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
            endpoint=os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"].rstrip("/") + "/v1/traces")))
    trace.set_tracer_provider(_prov)
    _tracer = trace.get_tracer("hr-ops-copilot")
except Exception:  # noqa: BLE001
    _tracer = None
try:
    if os.getenv("MLFLOW_TRACKING_URI"):
        import mlflow
        mlflow.set_experiment(os.getenv("MLFLOW_EXPERIMENT", "hr-ops-copilot"))
        _mlflow = mlflow
except Exception:  # noqa: BLE001
    _mlflow = None


def status() -> dict:
    return {"opentelemetry": bool(_tracer), "otlp_export": bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")) and bool(_tracer),
            "mlflow": bool(_mlflow)}


class Trace:
    """Collects steps for the UI and mirrors each step to OTel / MLflow spans when available."""

    def __init__(self, name: str, attrs: dict | None = None):
        self.steps: list[dict] = []
        self._stack = contextlib.ExitStack()
        if _mlflow is not None:
            with contextlib.suppress(Exception):
                self._stack.enter_context(_mlflow.start_span(name=name))
        if _tracer is not None:
            span = self._stack.enter_context(_tracer.start_as_current_span(name))
            for k, v in (attrs or {}).items():
                span.set_attribute(k, str(v))

    @contextlib.contextmanager
    def step(self, name: str, **attrs):
        t0 = time.perf_counter()
        rec = {"step": name, "summary": "", "ms": 0.0}
        cms = contextlib.ExitStack()
        span = None
        if _tracer is not None:
            span = cms.enter_context(_tracer.start_as_current_span(name))
        if _mlflow is not None:
            with contextlib.suppress(Exception):
                cms.enter_context(_mlflow.start_span(name=name))
        try:
            yield rec
        finally:
            rec["ms"] = round((time.perf_counter() - t0) * 1000, 1)
            if span is not None:
                for k, v in {**attrs, "summary": rec["summary"]}.items():
                    span.set_attribute(k, str(v))
            with contextlib.suppress(Exception):
                cms.close()
            self.steps.append(rec)

    def close(self):
        with contextlib.suppress(Exception):
            self._stack.close()
