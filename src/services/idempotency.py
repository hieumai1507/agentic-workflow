"""
Idempotency and deduplication service using Redis TTL locks.
"""
import hashlib
from typing import Optional
import redis.asyncio as aioredis
import structlog
from src.core.config import settings

logger = structlog.get_logger(__name__)

class IdempotencyService:
    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self._redis = redis_client

    async def get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        return self._redis

    @staticmethod
    def compute_email_hash(sender: str, subject: str, body: str) -> str:
        """Computes deterministic SHA-256 hash of normalized email contents."""
        content = f"{sender.strip().lower()}|{subject.strip()}|{body.strip()}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def acquire_lock(self, content_hash: str, job_id: str, ttl_seconds: int = 86400) -> bool:
        """
        Attempts to acquire an idempotency lock for 24h using SET NX.
        Returns True if acquired (new request), False if already processed (duplicate).
        """
        try:
            r = await self.get_redis()
            key = f"pii:idempotency:{content_hash}"
            acquired = await r.set(key, job_id, nx=True, ex=ttl_seconds)
            return bool(acquired)
        except Exception as e:
            logger.warning("Redis idempotency check unavailable, allowing execution", error=str(e))
            return True

    async def close(self):
        if self._redis:
            await self._redis.close()

idempotency_service = IdempotencyService()
