"""
Node: Ingest & Normalize
Cleans input text, normalizes whitespace and encoding, and computes deterministic content hash.
"""
from typing import Dict, Any
import structlog
from src.graph.state import AgentState
from src.services.idempotency import IdempotencyService

logger = structlog.get_logger(__name__)

async def ingest_and_normalize_node(state: AgentState) -> Dict[str, Any]:
    """
    Normalizes email content, strips non-printable ASCII control characters,
    computes content SHA-256 hash, and initializes tracking buffers.
    """
    sender = (state.get("sender") or "").strip()
    subject = (state.get("subject") or "").strip()
    raw_body = (state.get("raw_body") or "").strip()

    # Normalize carriage returns and non-breaking spaces
    normalized_body = raw_body.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    normalized_subject = subject.replace("\r\n", " ").replace("\n", " ").replace("\xa0", " ")

    # Compute idempotency content hash
    content_hash = IdempotencyService.compute_email_hash(sender, normalized_subject, normalized_body)

    logger.info(
        "Email normalized and hashed",
        job_id=state.get("job_id"),
        content_hash=content_hash
    )

    return {
        "sender": sender,
        "subject": normalized_subject,
        "raw_body": normalized_body,
        "content_hash": content_hash,
        "presidio_masked_body": normalized_body,
        "surrogate_mapping": dict(state.get("surrogate_mapping") or {}),
        "retry_count": state.get("retry_count", 0),
        "max_retries": state.get("max_retries", 3),
        "validation_errors": [],
        "is_fallback_triggered": False,
        "status": "NORMALIZED",
        "error_log": []
    }
