"""
Resilient client for dispatching sanitized tickets to downstream Jira/Zendesk API.
"""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import structlog
from src.core.config import settings
from src.core.exceptions import TemporaryDownstreamError, DownstreamAPIError

logger = structlog.get_logger(__name__)

class DownstreamClient:
    """Async client communicating with Mock Jira/Zendesk API."""

    def __init__(self, base_url: str = None, token: str = None):
        self.base_url = base_url or settings.DOWNSTREAM_API_BASE_URL
        self.token = token or settings.DOWNSTREAM_API_TOKEN

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=1, max=5),
        retry=retry_if_exception_type(TemporaryDownstreamError),
        reraise=True
    )
    async def create_ticket(self, payload: dict) -> dict:
        """
        Dispatches sanitized ticket to downstream API with exponential backoff.
        Raises TemporaryDownstreamError on 429/502/503/504 for Tenacity retry.
        """
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=settings.DOWNSTREAM_TIMEOUT,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
        ) as client:
            try:
                response = await client.post("/rest/api/3/issue", json=payload)

                if response.status_code in [429, 502, 503, 504]:
                    logger.warning(
                        "Transient downstream error. Retrying...",
                        status_code=response.status_code,
                        url=str(response.url)
                    )
                    raise TemporaryDownstreamError(f"HTTP {response.status_code}: {response.text}")

                if response.status_code >= 400:
                    logger.error(
                        "Permanent downstream error",
                        status_code=response.status_code,
                        detail=response.text
                    )
                    raise DownstreamAPIError(f"HTTP {response.status_code}: {response.text}")

                return response.json()

            except httpx.RequestError as exc:
                logger.warning("Downstream network error. Retrying...", error=str(exc))
                raise TemporaryDownstreamError(f"Network error: {str(exc)}") from exc

downstream_client = DownstreamClient()
