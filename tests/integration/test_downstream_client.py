"""
Integration tests for resilient downstream HTTP client and Tenacity retries.
"""
import pytest
import httpx
from src.services.downstream_client import DownstreamClient
from src.core.exceptions import TemporaryDownstreamError, DownstreamAPIError

@pytest.mark.asyncio
async def test_downstream_client_retries_on_429(monkeypatch):
    """Verifies that Tenacity retries on HTTP 429 and succeeds when endpoint recovers."""
    client = DownstreamClient(base_url="http://mock-api.local", token="test_token")
    attempts = 0

    async def mock_post(self, url, json=None, headers=None, **kwargs):
        nonlocal attempts
        attempts += 1
        request = httpx.Request("POST", f"http://mock-api.local{url}")
        if attempts < 2:
            return httpx.Response(429, request=request, text="Rate limit exceeded")
        return httpx.Response(201, request=request, json={"id": "mock_id", "key": "SUP-101"})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    payload = {"external_job_id": "test_job_1", "ticket_metadata": {}}
    result = await client.create_ticket(payload)

    assert attempts == 2
    assert result["key"] == "SUP-101"

@pytest.mark.asyncio
async def test_downstream_client_raises_permanent_error_on_400(monkeypatch):
    """Verifies that HTTP 400 immediately raises DownstreamAPIError without useless retries."""
    client = DownstreamClient(base_url="http://mock-api.local", token="test_token")

    async def mock_post(self, url, json=None, headers=None, **kwargs):
        request = httpx.Request("POST", f"http://mock-api.local{url}")
        return httpx.Response(400, request=request, text="Bad Request: Missing field")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    payload = {"external_job_id": "test_bad"}
    with pytest.raises(DownstreamAPIError):
        await client.create_ticket(payload)
