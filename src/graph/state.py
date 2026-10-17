"""
LangGraph TypedDict State Definition & Pydantic Data Contracts.
Includes Enterprise HITL metadata and Reversible Vault identifiers.
"""
from typing import TypedDict, List, Dict, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field

class TicketPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class TicketCategory(str, Enum):
    BILLING = "BILLING"
    TECHNICAL_SUPPORT = "TECHNICAL_SUPPORT"
    ACCOUNT_ACCESS = "ACCOUNT_ACCESS"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    GENERAL_INQUIRY = "GENERAL_INQUIRY"

class CustomerSentiment(str, Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    FRUSTRATED = "FRUSTRATED"

class IssueClassification(BaseModel):
    category: TicketCategory = Field(description="High-level category of the issue")
    urgency: TicketPriority = Field(description="Derived ticket urgency")
    sentiment: CustomerSentiment = Field(description="Detected customer sentiment")
    summary: str = Field(max_length=120, description="Clean 1-sentence issue summary")
    confidence_score: float = Field(default=0.95, ge=0.0, le=1.0, description="Confidence of classification")

class PIIEntity(BaseModel):
    original_value: str = Field(description="Original sensitive value (internal state only)")
    entity_type: str = Field(description="Entity category: SSN, EMAIL, PHONE, PERSON, ADDRESS, CARD, ORG")
    replacement_token: str = Field(description="Synthetic surrogate token e.g. [PERSON_1]")
    start_char: Optional[int] = None
    end_char: Optional[int] = None

class SemanticMaskingResult(BaseModel):
    masked_body: str = Field(description="Email body with all contextual PII replaced by surrogate tokens")
    extracted_entities: List[PIIEntity] = Field(default_factory=list)

class SanitizedTicketPayload(BaseModel):
    external_job_id: str
    source_system: str = "CUSTOMER_SUPPORT_EMAIL"
    ticket_metadata: IssueClassification
    sanitized_subject: str
    sanitized_body: str
    anonymized_entities: List[Dict[str, str]]
    audit_trail: Dict[str, Any]

class AgentState(TypedDict):
    # Ingestion Metadata
    job_id: str
    email_id: str
    sender: str
    subject: str
    raw_body: str
    received_at: str
    content_hash: str

    # Intermediate Processing States
    presidio_masked_body: str
    surrogate_mapping: Dict[str, str]  # e.g., {"[SSN_1]": "000-12-3456"}
    vault_id: Optional[str]            # AES-256-GCM Vault reference ID

    # LLM Structured Artifacts
    classification: Optional[IssueClassification]
    semantic_mask_result: Optional[SemanticMaskingResult]

    # Final Sanitized Artifacts
    sanitized_subject: str
    sanitized_body: str

    # Human-in-the-Loop (HITL) Governance
    requires_human_review: bool
    human_review_status: Optional[str]  # "PENDING", "APPROVED", "REJECTED"
    human_reviewer_id: Optional[str]
    human_reviewer_notes: Optional[str]
    reviewed_at: Optional[str]

    # Control Flow & Resilience Tracking
    routing_tier: Optional[str]        # "FAST_PATH_DETERMINISTIC" or "SEMANTIC_LLM_PATH"
    needs_semantic_masking: Optional[bool]
    retry_count: int
    max_retries: int
    validation_errors: List[str]
    is_fallback_triggered: bool
    status: str  # "QUEUED", "PROCESSING", "VALIDATING", "PENDING_HUMAN_REVIEW", "SUCCESS", "FALLBACK", "FAILED"
    error_log: List[str]
    dispatched_ticket_id: Optional[str]
