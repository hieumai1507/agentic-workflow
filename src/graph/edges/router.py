"""
Conditional edge routing logic for LangGraph workflow.
Includes Enterprise Human-in-the-Loop (HITL) routing.
"""
import structlog
from src.graph.state import AgentState, TicketCategory
from src.core.config import settings

logger = structlog.get_logger(__name__)

def route_masking_tier(state: AgentState) -> str:
    """
    Tiered Processing / Cascade Routing conditional edge:
    - 'fast_path': Presidio pre-masking completely eliminated all structured PII,
                   and no ambiguous contextual entities were detected. Bypasses
                   the expensive semantic LLM node, saving ~1,500 tokens/call.
    - 'semantic_path': Contextual entities (names, street addresses, obfuscations)
                       detected; invokes LLM semantic extraction.
    """
    needs_semantic = state.get("needs_semantic_masking")
    if settings.ENABLE_CASCADE_ROUTING and needs_semantic is False:
        logger.info(
            "Cascade Routing: Activating Fast-Path (bypassing semantic LLM)",
            job_id=state.get("job_id"),
            routing_tier="FAST_PATH_DETERMINISTIC"
        )
        return "fast_path"

    logger.info(
        "Cascade Routing: Activating Deep Semantic LLM Path",
        job_id=state.get("job_id"),
        routing_tier="SEMANTIC_LLM_PATH"
    )
    return "semantic_path"

def should_continue_or_fallback(state: AgentState) -> str:
    """
    Evaluates validator node outputs to route the workflow:
    - 'human_review': Sensitive category (e.g. SECURITY_INCIDENT) requiring DPO sign-off.
    - 'dispatch': All validation checks passed, clean non-sensitive ticket ready for egress.
    - 'retry': Errors detected and retries available (< max_retries).
    - 'fallback': Max retries exhausted, divert to deterministic fallback scrubber.
    """
    errors = state.get("validation_errors", [])
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)
    classification = state.get("classification")

    if not errors:
        # Enterprise HITL Governance: Route Security Incidents to Human Review
        if (
            settings.ENABLE_HITL_FOR_SECURITY_INCIDENTS
            and classification
            and classification.category == TicketCategory.SECURITY_INCIDENT
        ):
            logger.warning("Routing Security Incident to Human Review Gate", job_id=state.get("job_id"))
            return "human_review"

        logger.info("Validation passed, proceeding to dispatch", job_id=state.get("job_id"))
        return "dispatch"

    if retry_count < max_retries:
        logger.warning(
            "Validation errors detected. Triggering self-correction retry",
            job_id=state.get("job_id"),
            retry_count=retry_count + 1,
            max_retries=max_retries,
            errors=errors
        )
        return "retry"

    logger.error(
        "Max retries exhausted. Diverting to deterministic fallback scrubber",
        job_id=state.get("job_id"),
        retry_count=retry_count,
        errors=errors
    )
    return "fallback"
