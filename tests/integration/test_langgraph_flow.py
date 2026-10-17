"""
Integration tests for LangGraph state machine execution, retries, and fallbacks.
"""
import pytest
from src.graph.builder import build_pii_masking_graph
from src.graph.state import AgentState
from src.graph.edges.router import should_continue_or_fallback

@pytest.mark.asyncio
async def test_full_graph_happy_path(monkeypatch):
    """Verifies complete execution from normalize to dispatch."""
    # Mock downstream client to return mock ticket
    from src.services.downstream_client import downstream_client
    async def mock_create_ticket(payload):
        return {"id": "test_id_101", "key": "SUP-101", "status": "CREATED"}
    monkeypatch.setattr(downstream_client, "create_ticket", mock_create_ticket)

    graph = build_pii_masking_graph()
    initial_state = {
        "job_id": "job_test_001",
        "email_id": "em_test_001",
        "sender": "sarah.connor@resistance.org",
        "subject": "Help with billing charge for Sarah Connor",
        "raw_body": "Hello, my name is Sarah Connor. My phone is 415-555-0199 and SSN is 123-45-6789. Card 4111-2222-3333-4444.",
        "received_at": "2026-10-17T13:00:00Z",
        "content_hash": "",
        "retry_count": 0,
        "max_retries": 3,
        "validation_errors": [],
        "is_fallback_triggered": False,
        "status": "PROCESSING",
        "error_log": []
    }

    final_state = await graph.ainvoke(initial_state)

    assert final_state["status"] == "SUCCESS"
    assert final_state["dispatched_ticket_id"] == "SUP-101"
    # Ensure sensitive items are scrubbed
    assert "123-45-6789" not in final_state["sanitized_body"]
    assert "4111-2222-3333-4444" not in final_state["sanitized_body"]
    assert "[SSN_1]" in final_state["sanitized_body"]
    assert "[CARD_1]" in final_state["sanitized_body"]
    assert final_state["classification"] is not None

def test_router_edge_conditions():
    """Validates conditional router edge states."""
    # Case 1: No errors -> dispatch
    state_clean = {"validation_errors": [], "retry_count": 0, "max_retries": 3}
    assert should_continue_or_fallback(state_clean) == "dispatch"

    # Case 2: Errors and retry available -> retry
    state_retry = {"validation_errors": ["Residual SSN detected"], "retry_count": 1, "max_retries": 3}
    assert should_continue_or_fallback(state_retry) == "retry"

    # Case 3: Errors and retries exhausted -> fallback
    state_exhausted = {"validation_errors": ["Residual SSN detected"], "retry_count": 3, "max_retries": 3}
    assert should_continue_or_fallback(state_exhausted) == "fallback"

@pytest.mark.asyncio
async def test_fallback_node_execution():
    """Tests that fallback scrubber aggressively redacts lingering data."""
    from src.graph.nodes.fallback import fallback_scrubber_node

    dirty_state = {
        "job_id": "job_fallback_001",
        "sanitized_body": "Lingering SSN 999-88-7777 and phone 555-123-4567 in text",
        "sanitized_subject": "Secret account for 111-22-3333",
        "surrogate_mapping": {},
        "retry_count": 3,
        "validation_errors": ["Persistent residual leak"]
    }

    scrubbed = await fallback_scrubber_node(dirty_state)

    assert scrubbed["is_fallback_triggered"] is True
    assert "999-88-7777" not in scrubbed["sanitized_body"]
    assert "[REDACTED_SSN]" in scrubbed["sanitized_body"]
    assert "111-22-3333" not in scrubbed["sanitized_subject"]
