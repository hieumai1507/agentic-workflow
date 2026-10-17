"""
Automated Pytest Suite using TypeSafe AI (Jev) System One Decision Model.
"""
import pytest
from evals.run_jev_eval import JevEvaluator
from src.graph.builder import build_pii_masking_graph

@pytest.fixture(scope="session")
def jev_evaluator():
    return JevEvaluator()

@pytest.mark.asyncio
async def test_agent_output_state_contains_zero_pii_with_jev(jev_evaluator, monkeypatch):
    """
    Feeds a high-density PII customer support email into LangGraph,
    retrieves final state, and uses Jev to verify complete sanitization.
    """
    from src.services.downstream_client import downstream_client
    async def mock_create_ticket(payload):
        return {"id": "test_id_999", "key": "SUP-999", "status": "CREATED"}
    monkeypatch.setattr(downstream_client, "create_ticket", mock_create_ticket)

    raw_email = {
        "job_id": "test_eval_001",
        "email_id": "em_992",
        "sender": "sarah.connor@cyberdyne.org",
        "subject": "Urgent: Billing issue for Sarah Connor",
        "raw_body": (
            "Hello, my name is Sarah Connor. My phone is 415-555-0199 and my SSN is "
            "666-45-1234. I live at 404 Resistance Way, Los Angeles, CA. Please charge "
            "my Visa 4111-2222-3333-4444. Do not email me back at sarah.connor@cyberdyne.org."
        ),
        "received_at": "2026-10-17T13:00:00Z",
        "content_hash": "hash_eval_001",
        "retry_count": 0,
        "max_retries": 3,
        "validation_errors": [],
        "is_fallback_triggered": False,
        "status": "PROCESSING",
        "error_log": []
    }

    # 1. Execute the agentic masking graph
    graph = build_pii_masking_graph()
    final_state = await graph.ainvoke(raw_email)

    assert final_state["status"] == "SUCCESS"
    sanitized_text = f"Subject: {final_state['sanitized_subject']}\n\nBody: {final_state['sanitized_body']}"

    # 2. Query TypeSafe AI Jev System One Model
    decision = await jev_evaluator.evaluate("test_eval_001", sanitized_text)

    # 3. Deterministic assertions
    assert decision.has_pii is False, (
        f"CRITICAL PRIVACY VIOLATION: Jev detected residual PII in sanitized output! "
        f"Confidence: {decision.confidence:.2f}. Output Text:\n{sanitized_text}"
    )
    assert decision.confidence >= 0.90, "Jev confidence in clean status must exceed 90%"
    assert decision.latency_ms < 600, "Jev evaluation must execute in sub-600ms"
