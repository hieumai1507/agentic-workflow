"""
Human-in-the-Loop (HITL) Governance Review Routes.
Provides endpoints for DPO / Security Officers to inspect and approve quarantined tickets.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Header, status
from pydantic import BaseModel, Field
import structlog

from src.graph.nodes.hitl_gate import PENDING_REVIEWS
from src.services.downstream_client import downstream_client
from src.core.telemetry import HITL_REVIEWS_TOTAL

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/reviews", tags=["Human-in-the-Loop Governance"])

class ReviewActionPayload(BaseModel):
    reviewer_id: str = Field(..., description="ID of the reviewing DPO / Security Officer")
    notes: Optional[str] = Field(default="", description="Auditable approval or rejection rationale")

class ReviewRecordResponse(BaseModel):
    job_id: str
    email_id: Optional[str]
    sender: Optional[str]
    subject: Optional[str]
    scrubbed_body: Optional[str]
    category: str
    urgency: str
    vault_id: Optional[str]
    submitted_at: str
    status: str

@router.get("/pending", response_model=List[ReviewRecordResponse], summary="List all quarantined tickets awaiting DPO approval")
async def list_pending_reviews():
    """Returns all tickets currently quarantined in PENDING_HUMAN_REVIEW status."""
    return [v for v in PENDING_REVIEWS.values() if v.get("status") == "PENDING"]

@router.post("/{job_id}/approve", status_code=status.HTTP_200_OK, summary="Approve quarantined ticket and resume downstream dispatch")
async def approve_ticket(job_id: str, payload: ReviewActionPayload):
    """
    DPO approval gate: resumes execution, dispatches sanitized ticket to Mock Jira,
    and updates governance audit trail.
    """
    if job_id not in PENDING_REVIEWS:
        raise HTTPException(status_code=404, detail=f"No pending review found for job '{job_id}'.")

    record = PENDING_REVIEWS[job_id]
    if record["status"] != "PENDING":
        raise HTTPException(status_code=400, detail=f"Job '{job_id}' is already {record['status']}.")

    # Dispatch to downstream Jira API
    egress_payload = {
        "external_job_id": job_id,
        "source_system": "CUSTOMER_SUPPORT_EMAIL",
        "ticket_metadata": {
            "category": record["category"],
            "priority": record["urgency"],
            "sentiment": "NEUTRAL",
            "summary": f"[HITL Approved] {record['subject'][:80]}"
        },
        "sanitized_content": {
            "subject": record["subject"],
            "scrubbed_body": record["scrubbed_body"] or "",
            "anonymized_entities": []
        },
        "audit_trail": {
            "hitl_approved": True,
            "approved_by": payload.reviewer_id,
            "approval_notes": payload.notes,
            "approved_at": datetime.now(timezone.utc).isoformat()
        }
    }

    try:
        jira_resp = await downstream_client.create_ticket(egress_payload)
        ticket_key = jira_resp.get("key", "SUP-HITL-APPROVED")

        record["status"] = "APPROVED"
        record["approved_by"] = payload.reviewer_id
        record["approval_notes"] = payload.notes
        record["dispatched_ticket_key"] = ticket_key

        HITL_REVIEWS_TOTAL.labels(action="approved").inc()

        logger.info(
            "Quarantined ticket approved by human reviewer and dispatched to Jira",
            job_id=job_id,
            reviewer=payload.reviewer_id,
            ticket_key=ticket_key
        )

        return {
            "status": "APPROVED",
            "job_id": job_id,
            "dispatched_ticket_key": ticket_key,
            "approved_at": record.get("approved_at", datetime.now(timezone.utc).isoformat())
        }

    except Exception as exc:
        logger.error("Failed to dispatch approved ticket downstream", job_id=job_id, error=str(exc))
        raise HTTPException(status_code=502, detail=f"Downstream dispatch failed: {str(exc)}")

@router.post("/{job_id}/reject", status_code=status.HTTP_200_OK, summary="Reject quarantined ticket and cancel downstream dispatch")
async def reject_ticket(job_id: str, payload: ReviewActionPayload):
    """Rejects the quarantined ticket, preventing any downstream dispatch."""
    if job_id not in PENDING_REVIEWS:
        raise HTTPException(status_code=404, detail=f"No pending review found for job '{job_id}'.")

    record = PENDING_REVIEWS[job_id]
    record["status"] = "REJECTED"
    record["rejected_by"] = payload.reviewer_id
    record["rejection_notes"] = payload.notes

    HITL_REVIEWS_TOTAL.labels(action="rejected").inc()

    logger.warning("Quarantined ticket rejected by human reviewer", job_id=job_id, reviewer=payload.reviewer_id)

    return {
        "status": "REJECTED",
        "job_id": job_id,
        "rejected_by": payload.reviewer_id,
        "notes": payload.notes
    }
