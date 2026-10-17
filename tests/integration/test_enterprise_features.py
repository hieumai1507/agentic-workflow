"""
Automated Integration Tests for Tier-1 Enterprise Pillars:
1. Persistent Checkpointing & State History (LangGraph)
2. Human-in-the-Loop (HITL) Governance & DPO Approval
3. Reversible AES-256-GCM Vault & RBAC De-Anonymization
4. Prometheus Telemetry & Metrics Exposition
5. Multi-Model Gateway & Circuit Breaker Failover
"""
import pytest
from httpx import AsyncClient, ASGITransport
from langgraph.checkpoint.memory import MemorySaver
from src.api.app import app
from src.graph.builder import build_pii_masking_graph
from src.services.vault_service import vault_service, VaultSecurityException
from src.services.llm_gateway import MultiModelGateway, CircuitState
from src.graph.nodes.hitl_gate import PENDING_REVIEWS

@pytest.mark.asyncio
async def test_persistent_checkpointer_state_recovery(monkeypatch):
    """Verifies that LangGraph checkpointing persists state history under thread_id."""
    from src.services.downstream_client import downstream_client
    async def mock_dispatch(payload):
        return {"id": "chk_jira_1", "key": "SUP-CHK-100", "status": "CREATED"}
    monkeypatch.setattr(downstream_client, "create_ticket", mock_dispatch)

    graph = build_pii_masking_graph(checkpointer=MemorySaver())
    thread_id = "test_thread_checkpoint_001"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "job_id": thread_id,
        "email_id": "em_chk_1",
        "sender": "alice@company.com",
        "subject": "Billing issue",
        "raw_body": "Hello, my phone is 555-0199 and SSN is 123-45-6789.",
        "received_at": "2026-10-17T13:00:00Z",
        "content_hash": "hash_chk_1",
        "retry_count": 0,
        "max_retries": 3,
        "validation_errors": [],
        "is_fallback_triggered": False,
        "requires_human_review": False,
        "status": "PROCESSING",
        "error_log": []
    }

    final_state = await graph.ainvoke(initial_state, config=config)

    # Inspect checkpoint history from graph saver
    saved_checkpoint = graph.get_state(config)
    assert saved_checkpoint is not None
    assert saved_checkpoint.values["status"] in ["SUCCESS", "PENDING_HUMAN_REVIEW"]
    assert "[SSN_1]" in saved_checkpoint.values["sanitized_body"]

@pytest.mark.asyncio
async def test_hitl_security_incident_quarantine_and_dpo_approval(monkeypatch):
    """
    Verifies that SECURITY_INCIDENT tickets are quarantined in PENDING_HUMAN_REVIEW,
    and can be approved via the DPO review endpoint to resume dispatch.
    """
    from src.services.downstream_client import downstream_client
    async def mock_dispatch(payload):
        return {"id": "hitl_jira_123", "key": "SUP-HITL-777", "status": "CREATED"}
    monkeypatch.setattr(downstream_client, "create_ticket", mock_dispatch)

    graph = build_pii_masking_graph()
    job_id = "job_hitl_sec_001"
    config = {"configurable": {"thread_id": job_id}}

    # Security breach email triggering HITL
    security_email = {
        "job_id": job_id,
        "email_id": "em_sec_001",
        "sender": "whistleblower@firm.org",
        "subject": "Critical Security Breach: Unauthorized data leak",
        "raw_body": "Sensitive customer SSN 999-00-1111 was leaked publicly. Contact legal immediately at 555-0999.",
        "received_at": "2026-10-17T13:00:00Z",
        "content_hash": "hash_sec_1",
        "retry_count": 0,
        "max_retries": 3,
        "validation_errors": [],
        "is_fallback_triggered": False,
        "requires_human_review": False,
        "status": "PROCESSING",
        "error_log": []
    }

    final_state = await graph.ainvoke(security_email, config=config)

    # 1. Assert ticket is quarantined
    assert final_state["status"] == "PENDING_HUMAN_REVIEW"
    assert final_state["requires_human_review"] is True
    assert job_id in PENDING_REVIEWS

    # 2. DPO reviews and approves via API
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Check pending list
        resp = await client.get("/api/v1/reviews/pending")
        assert resp.status_code == 200
        jobs = [r["job_id"] for r in resp.json()]
        assert job_id in jobs

        # Approve with DPO officer identity
        approve_resp = await client.post(
            f"/api/v1/reviews/{job_id}/approve",
            json={"reviewer_id": "dpo_officer_sarah", "notes": "Approved after legal verification"}
        )
        assert approve_resp.status_code == 200
        data = approve_resp.json()
        assert data["status"] == "APPROVED"
        assert data["dispatched_ticket_key"] == "SUP-HITL-777"

@pytest.mark.asyncio
async def test_reversible_vault_aes256_and_rbac():
    """
    Verifies AES-256-GCM encryption of surrogate mappings and RBAC enforcement.
    """
    surrogates = {
        "[PERSON_1]": "Johnathan Connor",
        "[SSN_1]": "123-45-6789",
        "[CARD_1]": "4111-2222-3333-4444"
    }

    job_id = "job_vault_test_99"
    vault_id = vault_service.encrypt_and_vault(job_id, surrogates)
    assert vault_id.startswith("vlt_")

    # 1. Unauthorized role (ROLE_INTERN) -> Must be blocked
    with pytest.raises(VaultSecurityException) as exc:
        vault_service.reveal_token(
            vault_id=vault_id,
            token="[SSN_1]",
            accessor_id="intern_bob",
            role="ROLE_INTERN",
            reason="Curiosity"
        )
    assert "lacks PII de-anonymization privilege" in str(exc.value)

    # 2. Authorized role (ROLE_DPO) -> Decrypts successfully
    decrypted_ssn = vault_service.reveal_token(
        vault_id=vault_id,
        token="[SSN_1]",
        accessor_id="officer_alice",
        role="ROLE_DPO",
        reason="Formal regulatory investigation case #4092"
    )
    assert decrypted_ssn == "123-45-6789"

    # 3. Verify audit trail was recorded
    audit_trail = vault_service.get_audit_trail()
    assert len(audit_trail) > 0
    latest = audit_trail[-1]
    assert latest["accessor_id"] == "officer_alice"
    assert latest["token"] == "[SSN_1]"
    assert "integrity_hash" in latest

@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint():
    """Verifies that Prometheus metrics exposition endpoint returns 200 with standard metrics."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        assert "pii_masked_entities_total" in text
        assert "graph_execution_duration_seconds" in text
        assert "hitl_reviews_total" in text

def test_multi_model_circuit_breaker_failover():
    """Verifies Circuit Breaker failover from primary to secondary LLM on consecutive errors."""
    gateway = MultiModelGateway()
    assert gateway.get_active_provider() == gateway.primary_model
    assert gateway.state == CircuitState.CLOSED

    # Simulate 3 consecutive failures
    gateway.record_failure(Exception("OpenAI 503 Outage"))
    gateway.record_failure(Exception("OpenAI 503 Outage"))
    assert gateway.state == CircuitState.CLOSED  # 2 failures, still closed

    gateway.record_failure(Exception("OpenAI 503 Outage"))
    assert gateway.state == CircuitState.OPEN  # 3rd failure trips circuit
    assert gateway.get_active_provider() == gateway.fallback_model

    # Recovery resets circuit
    gateway.record_success()
    assert gateway.state == CircuitState.CLOSED
    assert gateway.get_active_provider() == gateway.primary_model
