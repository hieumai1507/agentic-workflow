"""
End-to-End tests verifying ingestion webhook, deduplication, and downstream mock Jira interaction.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from src.api.app import app
from src.mock_server.mock_jira_app import app as mock_jira_app, CREATED_TICKETS
from src.api.dependencies import get_redis_client
from src.services.downstream_client import downstream_client
from src.services.idempotency import idempotency_service
from src.workers.consumer import process_stream_message
import json

@pytest.mark.asyncio
async def test_e2e_webhook_ingestion_and_deduplication(monkeypatch):
    """
    Simulates:
    1. Ingestion via FastAPI webhook
    2. Redis idempotency check
    3. Duplicate submission detection
    """
    # Mock Redis client in memory
    memory_store = {}
    class MockRedis:
        async def set(self, key, val, nx=False, ex=None):
            if nx and key in memory_store:
                return False
            memory_store[key] = val
            return True
        async def xadd(self, stream, data):
            return "171000-0"
        async def xack(self, stream, group, msg_id):
            return 1
        async def close(self):
            pass

    mock_r = MockRedis()
    app.dependency_overrides[get_redis_client] = lambda: mock_r
    idempotency_service._redis = mock_r

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "email_id": "em_test_e2e_1",
            "sender": "bruce.wayne@waynecorp.com",
            "subject": "Wayne Enterprises Server Access",
            "body": "Hello, this is Bruce Wayne. My mobile is 555-0199 and SSN is 111-22-3333. Please reset access."
        }

        # First ingestion -> 202 Accepted, QUEUED
        resp1 = await client.post("/api/v1/emails/ingest", json=payload)
        assert resp1.status_code == 202
        data1 = resp1.json()
        assert data1["status"] == "QUEUED"

        # Second ingestion with exact same content -> 202 Accepted, DEDUPLICATED
        resp2 = await client.post("/api/v1/emails/ingest", json=payload)
        assert resp2.status_code == 202
        data2 = resp2.json()
        assert data2["status"] == "DEDUPLICATED"

@pytest.mark.asyncio
async def test_e2e_pipeline_to_mock_jira(monkeypatch):
    """
    Executes worker message processing with real mock Jira ASGI app.
    """
    CREATED_TICKETS.clear()

    # Route downstream_client calls directly into mock_jira_app
    async def mock_create(payload):
        async with AsyncClient(transport=ASGITransport(app=mock_jira_app), base_url="http://localhost:8001") as mc:
            resp = await mc.post(
                "/rest/api/3/issue",
                json=payload,
                headers={"Authorization": "Bearer mock_jira_token_secure_9921"}
            )
            return resp.json()

    monkeypatch.setattr(downstream_client, "create_ticket", mock_create)

    class MockRedisWorker:
        async def xack(self, stream, group, msg_id):
            return 1

    stream_payload = {
        "job_id": "job_e2e_100",
        "email_id": "em_100",
        "sender": "clark.kent@dailyplanet.com",
        "subject": "Subscription Renewal for Clark Kent",
        "body": "Hi, I am Clark Kent. Please charge my Visa 4111-2222-3333-4444. My phone is 555-0144.",
        "received_at": "2026-10-17T13:00:00Z",
        "content_hash": "hash_100"
    }

    final_state = await process_stream_message(MockRedisWorker(), "171000-1", stream_payload)

    assert final_state["status"] == "SUCCESS"
    assert "SUP-1001" in CREATED_TICKETS
    ticket = CREATED_TICKETS["SUP-1001"]

    # Verify sanitized content inside Mock Jira
    scrubbed_body = ticket["payload"]["sanitized_content"]["scrubbed_body"]
    assert "4111-2222-3333-4444" not in scrubbed_body
    assert "[CARD_1]" in scrubbed_body
    assert ticket["payload"]["ticket_metadata"]["category"] == "BILLING"
