"""
Prometheus Metrics Route.
Exposes real-time latency histograms, PII entity counters, and governance metrics.
"""
from fastapi import APIRouter, Response
from src.core.telemetry import export_prometheus_metrics

router = APIRouter(tags=["Observability"])

@router.get("/metrics", summary="Prometheus telemetry exposition endpoint")
def get_metrics():
    """Returns standard Prometheus metrics payload for scraping."""
    content, content_type = export_prometheus_metrics()
    return Response(content=content, media_type=content_type)
