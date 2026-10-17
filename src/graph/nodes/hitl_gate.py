"""
Node: Human-in-the-Loop (HITL) Governance Gate.
Pauses workflow execution for high-risk categories (e.g. SECURITY_INCIDENT)
or low-confidence classifications, awaiting DPO review and sign-off.
"""
from typing import Dict, Any
from datetime import datetime, timezone
import structlog
from src.graph.state import AgentState, TicketCategory
from src.services.vault_service import vault_service
from src.core.telemetry import HITL_REVIEWS_TOTAL

logger = structlog.get_logger(__name__)

# Registry of tickets pending human approval
PENDING_REVIEWS: Dict[str, Dict[str, Any]] = {}

async def human_review_gate_node(state: AgentState) -> Dict[str, Any]:
    """
    Evaluates state for mandatory human sign-off.
    Vaults sensitive PII mapping and transitions state to PENDING_HUMAN_REVIEW.
    """
    job_id = state.get("job_id")
    classification = state.get("classification")
    surrogate_mapping = state.get("surrogate_mapping") or {}

    # Encrypt sensitive PII in Vault
    vault_id = vault_service.encrypt_and_vault(job_id, surrogate_mapping)

    logger.warning(
        "HITL REVIEW TRIGGERED: Ticket quarantined awaiting DPO sign-off",
        job_id=job_id,
        category=classification.category.value if classification else "UNKNOWN",
        vault_id=vault_id
    )

    HITL_REVIEWS_TOTAL.labels(action="pending").inc()

    review_record = {
        "job_id": job_id,
        "email_id": state.get("email_id"),
        "sender": state.get("sender"),
        "subject": state.get("sanitized_subject") or state.get("subject"),
        "scrubbed_body": state.get("sanitized_body"),
        "category": classification.category.value if classification else "GENERAL_INQUIRY",
        "urgency": classification.urgency.value if classification else "MEDIUM",
        "vault_id": vault_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "status": "PENDING"
    }
    PENDING_REVIEWS[job_id] = review_record

    return {
        "requires_human_review": True,
        "human_review_status": "PENDING",
        "vault_id": vault_id,
        "status": "PENDING_HUMAN_REVIEW"
    }
