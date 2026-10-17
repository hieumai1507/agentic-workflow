"""
Node: Validator
Executes schema validation and secondary residual PII scanning.
"""
from typing import Dict, Any, List
import structlog
from src.graph.state import AgentState
from src.services.presidio_service import SSN_PATTERN, CREDIT_CARD_PATTERN, EMAIL_PATTERN, PHONE_PATTERN

logger = structlog.get_logger(__name__)

async def validate_masked_state_node(state: AgentState) -> Dict[str, Any]:
    """
    Validates the state against two criteria:
    1. Schema integrity (Classification must be non-null and conform to domain bounds).
    2. Zero Residual PII (Sanitized body and subject must not contain high-risk tokens or raw values from surrogate_mapping).
    """
    errors: List[str] = []
    classification = state.get("classification")
    sanitized_body = state.get("sanitized_body") or ""
    sanitized_subject = state.get("sanitized_subject") or state.get("subject") or ""
    surrogate_mapping = state.get("surrogate_mapping") or {}

    # 1. Schema Validation
    if not classification:
        errors.append("Schema error: Missing issue classification object")
    else:
        if not classification.summary or len(classification.summary) > 120:
            errors.append("Schema error: Summary must be between 1 and 120 characters")

    # 2. Residual High-Entropy PII Check
    combined_text = f"{sanitized_subject}\n{sanitized_body}"

    # Check for unmasked SSNs
    if SSN_PATTERN.search(combined_text):
        errors.append("Residual PII: Detected unmasked Social Security Number")

    # Check for unmasked Credit Cards
    if CREDIT_CARD_PATTERN.search(combined_text):
        errors.append("Residual PII: Detected unmasked payment card number")

    # Check for unmasked Emails (excluding synthetic surrogate tokens like [EMAIL_1])
    # Search for actual email patterns
    for email_match in EMAIL_PATTERN.finditer(combined_text):
        match_str = email_match.group(0)
        # Verify it's not part of a token definition
        if not match_str.startswith("[") and not match_str.endswith("]"):
            errors.append(f"Residual PII: Detected unmasked email address: {match_str}")

    # Check that none of the original sensitive values exist in sanitized text
    for token, raw_val in surrogate_mapping.items():
        if raw_val and len(raw_val) > 4 and raw_val in combined_text:
            errors.append(f"Residual PII: Original sensitive value for {token} remains in sanitized output")

    if errors:
        logger.warning(
            "State validation failed",
            job_id=state.get("job_id"),
            errors_count=len(errors),
            errors=errors
        )
    else:
        logger.info("State validation passed successfully", job_id=state.get("job_id"))

    return {
        "validation_errors": errors,
        "status": "VALIDATED" if not errors else "VALIDATION_FAILED"
    }
