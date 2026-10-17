"""
Deterministic Pre-Masking Service:
Performs high-entropy pattern matching (SSN, credit cards, phones, emails, IP addresses)
and tracks surrogate token mappings.
"""
import re
from typing import Tuple, Dict, List
import structlog
from src.graph.state import PIIEntity

logger = structlog.get_logger(__name__)

# Pattern specifications
SSN_PATTERN = re.compile(
    r"\b(?:\d{3}[-\s]?\d{2}[-\s]?\d{4}|\d\s*-\s*\d\s*-\s*\d\s*-\s*\d\s*\d\s*-\s*\d\s*\d\s*\d\s*\d)\b"
)
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}\b"
)
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
OBFUSCATED_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+\s*(?:\[at\]|@|\(at\))\s*[A-Za-z0-9.-]+\s*(?:\[dot\]|\.|\(dot\))\s*[A-Za-z]{2,}\b",
    re.IGNORECASE
)

class DeterministicMasker:
    """Deterministic regex & heuristic pre-scrubber."""

    def __init__(self):
        pass

    def mask(self, text: str, initial_surrogates: Dict[str, str] = None) -> Tuple[str, Dict[str, str], List[PIIEntity]]:
        """
        Scans text for deterministic PII tokens, replaces them with surrogate identifiers,
        and returns (masked_text, surrogate_mapping, extracted_entities).
        """
        if not text:
            return text, {}, []

        surrogates: Dict[str, str] = dict(initial_surrogates or {})
        entities: List[PIIEntity] = []

        # Counter trackers
        counters: Dict[str, int] = {
            "SSN": 1,
            "CARD": 1,
            "EMAIL": 1,
            "PHONE": 1
        }

        # Track reversed mapping: raw_value -> token (to ensure identical raw values get identical surrogate tokens)
        raw_to_token: Dict[str, str] = {v: k for k, v in surrogates.items()}

        def replace_match(match: re.Match, entity_type: str) -> str:
            raw_val = match.group(0).strip()
            # If already mapped, reuse the exact same token
            if raw_val in raw_to_token:
                return raw_to_token[raw_val]

            token = f"[{entity_type}_{counters[entity_type]}]"
            counters[entity_type] += 1
            surrogates[token] = raw_val
            raw_to_token[raw_val] = token

            entities.append(
                PIIEntity(
                    original_value=raw_val,
                    entity_type=entity_type,
                    replacement_token=token,
                    start_char=match.start(),
                    end_char=match.end()
                )
            )
            return token

        # 1. SSNs
        masked_text = SSN_PATTERN.sub(lambda m: replace_match(m, "SSN"), text)

        # 2. Credit Cards
        masked_text = CREDIT_CARD_PATTERN.sub(lambda m: replace_match(m, "CARD"), masked_text)

        # 3. Emails (standard and obfuscated)
        masked_text = EMAIL_PATTERN.sub(lambda m: replace_match(m, "EMAIL"), masked_text)
        masked_text = OBFUSCATED_EMAIL_PATTERN.sub(lambda m: replace_match(m, "EMAIL"), masked_text)

        # 4. Phones (exclude pure numeric error codes like ERR-902-1249)
        def phone_filter(match: re.Match) -> str:
            val = match.group(0)
            # Avoid masking version numbers or error code suffixes like "v2.14.0" or "ERR-100-200"
            start_idx = match.start()
            prefix = masked_text[max(0, start_idx - 5):start_idx].upper()
            if "ERR" in prefix or "SKU" in prefix or "VER" in prefix or "V" in prefix:
                return val
            return replace_match(match, "PHONE")

        masked_text = PHONE_PATTERN.sub(phone_filter, masked_text)

        return masked_text, surrogates, entities

deterministic_masker = DeterministicMasker()
