"""
Unit tests for Cascade Routing / Tiered Processing (Fast-Path vs Semantic LLM Path).
Validates token cost optimization and latency reduction by bypassing expensive
LLM nodes when deterministic Presidio scrubbing is sufficient.
"""
import pytest
from src.graph.builder import build_pii_masking_graph
from src.graph.edges.router import route_masking_tier
from src.services.downstream_client import downstream_client

@pytest.mark.asyncio
async def test_fast_path_activated_for_pure_technical_alert(monkeypatch):
    """Verifies that an infrastructure alert with no contextual PII takes the Fast Path."""
    async def mock_dispatch(payload):
        return {"id": "fast_ticket_1", "key": "SUP-FAST-01", "status": "CREATED"}
    monkeypatch.setattr(downstream_client, "create_ticket", mock_dispatch)

    graph = build_pii_masking_graph()
    state = {
        "job_id": "job_fast_001",
        "email_id": "em_fast_001",
        "sender": "alerts@devops-corp.internal",
        "subject": "Infrastructure Telemetry: Kubernetes pod crashed with OOMKilled",
        "raw_body": "Container redis-cache-0 on node k8s-worker-12 exceeded 512MB RAM. Exit code 137.",
        "received_at": "2026-10-17T14:00:00Z",
        "content_hash": "hash_fast_1",
        "retry_count": 0,
        "max_retries": 3,
        "validation_errors": [],
        "is_fallback_triggered": False,
        "status": "PROCESSING",
        "error_log": []
    }

    final_state = await graph.ainvoke(state)

    assert final_state["routing_tier"] == "FAST_PATH_DETERMINISTIC"
    assert final_state["needs_semantic_masking"] is False
    # Semantic mask result should be None because node was bypassed!
    assert final_state.get("semantic_mask_result") is None
    assert final_state["status"] == "SUCCESS"
    assert "redis-cache-0" in final_state["sanitized_body"]

@pytest.mark.asyncio
async def test_semantic_path_activated_for_contextual_pii(monkeypatch):
    """Verifies that an email with personal name indicators is routed to Semantic Masking."""
    async def mock_dispatch(payload):
        return {"id": "sem_ticket_2", "key": "SUP-SEM-02", "status": "CREATED"}
    monkeypatch.setattr(downstream_client, "create_ticket", mock_dispatch)

    graph = build_pii_masking_graph()
    state = {
        "job_id": "job_sem_002",
        "email_id": "em_sem_002",
        "sender": "customer@vip.com",
        "subject": "Account Inquiry",
        "raw_body": "Hello support, my name is Arthur Dent. Please check my status.",
        "received_at": "2026-10-17T14:00:00Z",
        "content_hash": "hash_sem_2",
        "retry_count": 0,
        "max_retries": 3,
        "validation_errors": [],
        "is_fallback_triggered": False,
        "status": "PROCESSING",
        "error_log": []
    }

    final_state = await graph.ainvoke(state)

    assert final_state["routing_tier"] == "SEMANTIC_LLM_PATH"
    assert final_state["needs_semantic_masking"] is True
    assert final_state.get("semantic_mask_result") is not None
    assert "[PERSON_1]" in final_state["sanitized_body"]
    assert "Arthur Dent" not in final_state["sanitized_body"]

def test_route_masking_tier_logic():
    """Unit test for the router function directly."""
    # Fast-Path case
    fast_state = {"job_id": "test_1", "needs_semantic_masking": False}
    assert route_masking_tier(fast_state) == "fast_path"

    # Semantic Path case
    semantic_state = {"job_id": "test_2", "needs_semantic_masking": True}
    assert route_masking_tier(semantic_state) == "semantic_path"
