"""
FastAPI route dependencies (Redis connection pooling and security).
"""
from typing import Optional
import redis.asyncio as aioredis
from src.core.config import settings

_redis_pool: Optional[aioredis.Redis] = None

async def get_redis_client() -> aioredis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_pool
