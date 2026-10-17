"""
Enterprise Telemetry, Observability & Prometheus Metrics Exporter.
Tracks execution latency histograms, masked entity counters, and HITL governance metrics.
"""
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# 1. Masked Entities Counter
PII_MASKED_ENTITIES_TOTAL = Counter(
    "pii_masked_entities_total",
    "Total count of masked PII entities scrubbed across the pipeline",
    ["entity_type"]
)

# 2. Graph Execution Latency Histogram
GRAPH_EXECUTION_SECONDS = Histogram(
    "graph_execution_duration_seconds",
    "End-to-end execution latency of the LangGraph workflow",
    ["status"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# 3. Human-in-the-Loop Review Counter
HITL_REVIEWS_TOTAL = Counter(
    "hitl_reviews_total",
    "Count of human-in-the-loop governance reviews",
    ["action"]  # "pending", "approved", "rejected"
)

# 4. Self-Correction Retries Counter
RETRY_ATTEMPTS_TOTAL = Counter(
    "retry_loop_attempts_total",
    "Count of self-healing retry iterations triggered by validator failures",
    ["reason"]
)

# 5. Dead-Letter Queue Counter
DLQ_QUARANTINE_TOTAL = Counter(
    "dlq_quarantine_total",
    "Total count of messages routed to the Dead-Letter Queue"
)

# 6. Cascade Routing Tier Counter (Fast-Path vs Semantic LLM Path)
WORKFLOW_ROUTING_TIER_TOTAL = Counter(
    "workflow_routing_tier_total",
    "Count of tickets routed via Fast-Path vs Deep Semantic LLM Path",
    ["tier"]  # "fast_path", "semantic_llm"
)

def export_prometheus_metrics() -> tuple[bytes, str]:
    """Returns the Prometheus metrics payload and content-type header."""
    return generate_latest(), CONTENT_TYPE_LATEST
