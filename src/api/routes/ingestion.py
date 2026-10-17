"""
FastAPI Ingestion Endpoint: Webhook for raw customer support emails.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
import redis.asyncio as aioredis
import structlog

from src.core.config import settings
from src.api.dependencies import get_redis_client
from src.services.idempotency import idempotency_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/emails", tags=["Ingestion"])

class RawEmailInput(BaseModel):
    email_id: str = Field(default_factory=lambda: f"em_{uuid.uuid4().hex[:8]}")
    sender: str = Field(..., description="Customer sender email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Raw email body content")
    received_at: Optional[str] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class IngestionResponse(BaseModel):
    job_id: str
    status: str
    content_hash: str
    message: str

@router.post(
    "/ingest",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestionResponse,
    summary="Ingest raw customer support email into async queue"
)
async def ingest_email(
    payload: RawEmailInput,
    redis_client: aioredis.Redis = Depends(get_redis_client)
):
    """
    Validates input schema, checks idempotency hash, and pushes job to Redis Streams.
    """
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    content_hash = idempotency_service.compute_email_hash(
        payload.sender, payload.subject, payload.body
    )

    # 1. Idempotency Check
    is_new = await idempotency_service.acquire_lock(content_hash, job_id)
    if not is_new:
        logger.info("Duplicate email detected. Skipping redundant processing", content_hash=content_hash)
        return IngestionResponse(
            job_id=job_id,
            status="DEDUPLICATED",
            content_hash=content_hash,
            message="Email with identical content was recently ingested. Skipped duplicate processing."
        )

    # 2. Package Stream Message
    stream_payload = {
        "job_id": job_id,
        "email_id": payload.email_id,
        "sender": payload.sender,
        "subject": payload.subject,
        "body": payload.body,
        "received_at": payload.received_at,
        "content_hash": content_hash
    }

    try:
        # 3. Publish to Redis Stream
        await redis_client.xadd(
            settings.STREAM_NAME,
            {"payload": json.dumps(stream_payload)}
        )
        logger.info("Email successfully queued into Redis Stream", job_id=job_id, stream=settings.STREAM_NAME)
    except Exception as exc:
        logger.error("Failed to enqueue message to Redis", job_id=job_id, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Message queuing failed: {str(exc)}"
        )

    return IngestionResponse(
        job_id=job_id,
        status="QUEUED",
        content_hash=content_hash,
        message="Support email accepted and scheduled for PII masking."
    )
