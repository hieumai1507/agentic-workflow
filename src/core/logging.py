"""
Structured logging configuration with automated sensitive PII redactor.
"""
import re
import structlog
import logging
import sys

# High-entropy PII pattern matchers
SSN_REGEX = re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")
CREDIT_CARD_REGEX = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_REGEX = re.compile(r"\b(?:\+?(\d{1,3}))?[-. (]*(\d{3})[-. )]*(\d{3})[-. ]*(\d{4})\b")

def redact_sensitive_strings(text: str) -> str:
    """Replaces sensitive patterns with generic redacted markers."""
    if not isinstance(text, str):
        return text
    text = SSN_REGEX.sub("[SSN_REDACTED]", text)
    text = CREDIT_CARD_REGEX.sub("[CARD_REDACTED]", text)
    text = EMAIL_REGEX.sub("[EMAIL_REDACTED]", text)
    text = PHONE_REGEX.sub("[PHONE_REDACTED]", text)
    return text

def pii_scrubbing_processor(logger, method_name, event_dict):
    """Structlog processor that sanitizes all string values in event_dict."""
    for key, val in list(event_dict.items()):
        if isinstance(val, str):
            event_dict[key] = redact_sensitive_strings(val)
        elif isinstance(val, dict):
            event_dict[key] = {k: redact_sensitive_strings(v) if isinstance(v, str) else v for k, v in val.items()}
    return event_dict

def setup_logging():
    """Initializes structured logging with PII scrubbing processor."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            pii_scrubbing_processor,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True
    )

setup_logging()
logger = structlog.get_logger("agentic_pii_workflow")
