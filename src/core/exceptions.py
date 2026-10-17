"""
Domain-specific exceptions for the Agentic PII Masking Workflow.
"""

class WorkflowBaseException(Exception):
    """Base exception for all workflow domain errors."""
    pass

class SchemaValidationError(WorkflowBaseException):
    """Raised when LLM output violates Pydantic schema validation."""
    pass

class ResidualPIIDetectedError(WorkflowBaseException):
    """Raised when validation gate detects residual unmasked PII."""
    pass

class MaxRetriesExceededError(WorkflowBaseException):
    """Raised when LLM self-correction retries are exhausted."""
    pass

class DownstreamAPIError(WorkflowBaseException):
    """Raised when downstream Jira/Zendesk API fails permanently."""
    pass

class TemporaryDownstreamError(DownstreamAPIError):
    """Raised on 429/503 for Tenacity exponential retries."""
    pass

class IdempotencyViolationError(WorkflowBaseException):
    """Raised when duplicate email hash is detected."""
    pass
