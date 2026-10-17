import re
from typing import Dict, Any
import structlog
from src.graph.state import AgentState
from src.services.presidio_service import deterministic_masker
from src.core.config import settings

logger = structlog.get_logger(__name__)

# Contextual indicators that warrant deep semantic LLM scanning
CONTEXTUAL_PII_PATTERNS = [
    re.compile(r"(?:my name is|i am|this is|call me|regards,|sincerely,|thanks,|cheers,|from:?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})", re.IGNORECASE),
    re.compile(r"(?:for|customer:?|user:?|account holder:?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})", re.IGNORECASE),
    re.compile(r"\b\d{1,5}\s+[A-Z][a-zA-Z0-9\s.,]{3,35}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Way|Court|Ct|Circle|Cir)\b", re.IGNORECASE),
    re.compile(r"(?:residing at|living in|address:?)\s+([0-9A-Za-z\s,.-]+)", re.IGNORECASE),
    re.compile(r"\b(?:[a-zA-Z0-9._%+-]+(?:\s*\[at\]\s*|\s*\(at\)\s*)[a-zA-Z0-9.-]+)", re.IGNORECASE),
    re.compile(r"(?:client|employee|user|doctor|lawyer)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)", re.IGNORECASE),
]

async def presidio_premask_node(state: AgentState) -> Dict[str, Any]:
    """
    Scans and masks SSNs, credit cards, phones, and emails.
    Populates initial surrogate_mapping in state.
    Assesses contextual PII complexity to enable Fast-Path routing.
    """
    raw_body = state.get("raw_body") or ""
    initial_surrogates = state.get("surrogate_mapping") or {}

    masked_body, updated_surrogates, entities = deterministic_masker.mask(
        raw_body, initial_surrogates=initial_surrogates
    )

    # Mask subject if it contains high-entropy PII
    masked_subject, updated_surrogates, subject_entities = deterministic_masker.mask(
        state.get("subject") or "", initial_surrogates=updated_surrogates
    )

    all_entities = entities + subject_entities
    for ent in all_entities:
        try:
            from src.core.telemetry import PII_MASKED_ENTITIES_TOTAL
            PII_MASKED_ENTITIES_TOTAL.labels(entity_type=ent.entity_type).inc()
        except Exception:
            pass

    # Complexity Assessment for Cascade Routing (Fast-Path vs Semantic LLM Path)
    combined_clean = f"{masked_subject}\n{masked_body}"
    needs_semantic = False
    if settings.ENABLE_CASCADE_ROUTING:
        for pat in CONTEXTUAL_PII_PATTERNS:
            if pat.search(combined_clean):
                needs_semantic = True
                break
    else:
        needs_semantic = True

    routing_tier = "SEMANTIC_LLM_PATH" if needs_semantic else "FAST_PATH_DETERMINISTIC"

    try:
        from src.core.telemetry import WORKFLOW_ROUTING_TIER_TOTAL
        WORKFLOW_ROUTING_TIER_TOTAL.labels(tier="semantic_llm" if needs_semantic else "fast_path").inc()
    except Exception:
        pass

    logger.info(
        "Deterministic pre-masking completed",
        job_id=state.get("job_id"),
        detected_entities_count=len(all_entities),
        surrogates_count=len(updated_surrogates),
        routing_tier=routing_tier,
        needs_semantic=needs_semantic
    )

    result_payload: Dict[str, Any] = {
        "presidio_masked_body": masked_body,
        "sanitized_subject": masked_subject,
        "surrogate_mapping": updated_surrogates,
        "needs_semantic_masking": needs_semantic,
        "routing_tier": routing_tier,
        "status": "PRE_MASKED"
    }

    # If Fast-Path is active, pre-populate sanitized_body to allow bypassing semantic_mask
    if not needs_semantic:
        result_payload["sanitized_body"] = masked_body

    return result_payload
