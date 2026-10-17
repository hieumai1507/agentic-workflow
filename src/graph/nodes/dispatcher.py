"""
Node: Dispatcher
Formats sanitized payload and executes resilient HTTP egress to Mock Jira/Zendesk API.
"""
from typing import Dict, Any
import structlog
from src.graph.state import AgentState, SanitizedTicketPayload, IssueClassification, TicketCategory, TicketPriority, CustomerSentiment
from src.services.downstream_client import downstream_client

logger = structlog.get_logger(__name__)

async def dispatch_to_mock_api_node(state: AgentState) -> Dict[str, Any]:
    """
    Constructs the final sanitized ticket payload and posts it to Mock Jira/Zendesk.
    """
    job_id = state.get("job_id")
    classification = state.get("classification") or IssueClassification(
        category=TicketCategory.GENERAL_INQUIRY,
        urgency=TicketPriority.MEDIUM,
        sentiment=CustomerSentiment.NEUTRAL,
        summary=f"Inquiry: {state.get('sanitized_subject', '')[:80]}",
        confidence_score=0.9
    )

    # Build clean anonymized entities list (only tokens and entity_types, NEVER raw values)
    surrogate_mapping = state.get("surrogate_mapping") or {}
    anonymized_entities = []
    for token in surrogate_mapping.keys():
        entity_type = token.strip("[]").split("_")[0]
        anonymized_entities.append({"token": token, "entity_type": entity_type})

    payload = {
        "external_job_id": job_id,
        "source_system": "CUSTOMER_SUPPORT_EMAIL",
        "ticket_metadata": {
            "category": classification.category.value,
            "priority": classification.urgency.value,
            "sentiment": classification.sentiment.value,
            "summary": classification.summary
        },
        "sanitized_content": {
            "subject": state.get("sanitized_subject") or state.get("subject"),
            "scrubbed_body": state.get("sanitized_body") or "",
            "anonymized_entities": anonymized_entities
        },
        "audit_trail": {
            "pii_detected_count": len(anonymized_entities),
            "fallback_triggered": state.get("is_fallback_triggered", False),
            "retry_count": state.get("retry_count", 0),
            "graph_version": "1.0.0"
        }
    }

    try:
        response = await downstream_client.create_ticket(payload)
        ticket_id = response.get("key") or response.get("id") or "MOCK-TICKET-OK"
        logger.info(
            "Sanitized ticket successfully created in downstream system",
            job_id=job_id,
            ticket_id=ticket_id
        )
        return {
            "dispatched_ticket_id": str(ticket_id),
            "status": "SUCCESS"
        }
    except Exception as exc:
        logger.error("Failed to dispatch ticket downstream", job_id=job_id, error=str(exc))
        return {
            "status": "DISPATCH_FAILED",
            "error_log": state.get("error_log", []) + [f"Dispatch error: {str(exc)}"]
        }
