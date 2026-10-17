"""
Node: Semantic Contextual PII Masking
Detects contextual entities (names, physical addresses, organizations, credentials)
and maps them to sequential surrogate tokens.
"""
import re
from typing import Dict, Any, List
import structlog
from src.core.config import settings
from src.graph.state import (
    AgentState,
    SemanticMaskingResult,
    PIIEntity
)
from src.prompts.manager import get_prompt_template, format_retry_feedback

logger = structlog.get_logger(__name__)

# Non-PII entity whitelist (products, software, technical acronyms)
PRODUCT_WHITELIST = {
    "MacBook", "MacBook Pro", "Windows", "Windows 11", "Chrome", "Google Chrome",
    "Firefox", "Safari", "Jira", "Zendesk", "Slack", "Redis", "Docker", "Linux",
    "PostgreSQL", "Python", "FastAPI", "Ubuntu", "AWS", "Azure", "GitHub", "GitLab"
}

# Common name markers and honorifics
NAME_INDICATORS = [
    r"(?:my name is|i am|this is|call me|regards,|sincerely,|thanks,|cheers,|from:?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
    r"(?:for|customer:?|user:?|account holder:?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
    r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b"
]

# Physical address regex
ADDRESS_REGEX = re.compile(
    r"\b\d{1,5}\s+[A-Z][a-zA-Z0-9\s.,]{3,35}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Way|Court|Ct|Circle|Cir)\b(?:[,\s]+[A-Za-z\s]+[,\s]+[A-Z]{2}\b)?",
    re.IGNORECASE
)

def _heuristic_semantic_mask(text: str, current_surrogates: Dict[str, str]) -> SemanticMaskingResult:
    """Heuristic contextual masking for offline execution and testing."""
    masked = text
    entities: List[PIIEntity] = []
    surrogates = dict(current_surrogates)

    person_counter = sum(1 for k in surrogates if k.startswith("[PERSON_")) + 1
    address_counter = sum(1 for k in surrogates if k.startswith("[ADDRESS_")) + 1
    org_counter = sum(1 for k in surrogates if k.startswith("[ORG_")) + 1

    # Invert mapping to reuse tokens for duplicate mentions
    raw_to_token = {v.lower(): k for k, v in surrogates.items()}

    # 1. Physical Addresses
    for match in list(ADDRESS_REGEX.finditer(masked)):
        raw_val = match.group(0).strip()
        lower_val = raw_val.lower()
        if lower_val in raw_to_token:
            token = raw_to_token[lower_val]
        else:
            token = f"[ADDRESS_{address_counter}]"
            address_counter += 1
            surrogates[token] = raw_val
            raw_to_token[lower_val] = token

        entities.append(PIIEntity(
            original_value=raw_val,
            entity_type="ADDRESS",
            replacement_token=token
        ))
        masked = masked.replace(raw_val, token)

    # 2. Person Names with indicators
    for pattern in NAME_INDICATORS:
        for match in re.finditer(pattern, masked, re.IGNORECASE):
            full_match = match.group(0)
            # Find the capitalized name group if present
            candidate = match.group(1) if match.groups() else match.group(0)
            candidate = candidate.strip(".,;: ")

            # Skip whitelisted products or general keywords
            if candidate in PRODUCT_WHITELIST or any(w.lower() in candidate.lower() for w in PRODUCT_WHITELIST):
                continue
            if candidate.lower() in {"customer support", "support team", "hello team", "hi team", "urgent billing"}:
                continue

            lower_cand = candidate.lower()
            if lower_cand in raw_to_token:
                token = raw_to_token[lower_cand]
            else:
                token = f"[PERSON_{person_counter}]"
                person_counter += 1
                surrogates[token] = candidate
                raw_to_token[lower_cand] = token

            entities.append(PIIEntity(
                original_value=candidate,
                entity_type="PERSON",
                replacement_token=token
            ))
            # Safely replace candidate using word boundary
            masked = re.sub(r"\b" + re.escape(candidate) + r"\b", token, masked)

    return SemanticMaskingResult(
        masked_body=masked,
        extracted_entities=entities
    )

async def semantic_mask_node(state: AgentState) -> Dict[str, Any]:
    """Performs semantic entity extraction and pseudonymization."""
    body_to_mask = state.get("presidio_masked_body") or state.get("raw_body") or ""
    surrogates = dict(state.get("surrogate_mapping") or {})
    validation_errors = state.get("validation_errors") or []
    retry_count = state.get("retry_count", 0)

    # If retrying, build feedback context
    retry_feedback = ""
    if validation_errors:
        retry_feedback = "\n\n" + format_retry_feedback(validation_errors)

    if settings.OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage

            prompt_data = get_prompt_template("entity_masker_v1")
            llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                temperature=settings.LLM_TEMPERATURE,
                api_key=settings.OPENAI_API_KEY,
                timeout=settings.LLM_TIMEOUT_SECONDS
            )
            structured_llm = llm.with_structured_output(SemanticMaskingResult)

            sys_content = prompt_data["system_prompt"] + retry_feedback
            human_content = (
                f"Subject: {state.get('sanitized_subject') or state.get('subject')}\n\n"
                f"Pre-masked Body:\n{body_to_mask}"
            )

            result: SemanticMaskingResult = await structured_llm.ainvoke([
                SystemMessage(content=sys_content),
                HumanMessage(content=human_content)
            ])

            for ent in result.extracted_entities:
                surrogates[ent.replacement_token] = ent.original_value

            logger.info("LLM semantic masking completed", entities_count=len(result.extracted_entities))
            return {
                "semantic_mask_result": result,
                "sanitized_body": result.masked_body,
                "surrogate_mapping": surrogates,
                "retry_count": retry_count + (1 if validation_errors else 0),
                "validation_errors": [],
                "status": "SEMANTIC_MASKED"
            }
        except Exception as e:
            logger.warning("LLM semantic masking failed, falling back to heuristic masker", error=str(e))

    result = _heuristic_semantic_mask(body_to_mask, surrogates)
    for ent in result.extracted_entities:
        surrogates[ent.replacement_token] = ent.original_value
        try:
            from src.core.telemetry import PII_MASKED_ENTITIES_TOTAL
            PII_MASKED_ENTITIES_TOTAL.labels(entity_type=ent.entity_type).inc()
        except Exception:
            pass

    logger.info("Heuristic semantic masking completed", entities_count=len(result.extracted_entities))
    return {
        "semantic_mask_result": result,
        "sanitized_body": result.masked_body,
        "surrogate_mapping": surrogates,
        "retry_count": retry_count + (1 if validation_errors else 0),
        "validation_errors": [],
        "status": "SEMANTIC_MASKED"
    }
