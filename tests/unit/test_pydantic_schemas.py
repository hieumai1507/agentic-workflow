"""
Unit tests for Pydantic schema validation and constraints.
"""
import pytest
from pydantic import ValidationError
from src.graph.state import (
    IssueClassification,
    TicketCategory,
    TicketPriority,
    CustomerSentiment,
    PIIEntity
)

def test_valid_issue_classification():
    data = {
        "category": "BILLING",
        "urgency": "HIGH",
        "sentiment": "FRUSTRATED",
        "summary": "Customer charged twice for subscription renewal",
        "confidence_score": 0.98
    }
    model = IssueClassification(**data)
    assert model.category == TicketCategory.BILLING
    assert model.urgency == TicketPriority.HIGH
    assert model.sentiment == CustomerSentiment.FRUSTRATED
    assert model.summary == "Customer charged twice for subscription renewal"

def test_invalid_category_raises_validation_error():
    with pytest.raises(ValidationError):
        IssueClassification(
            category="UNKNOWN_CATEGORY",
            urgency="LOW",
            sentiment="NEUTRAL",
            summary="Test summary"
        )

def test_summary_length_cap():
    with pytest.raises(ValidationError):
        IssueClassification(
            category="GENERAL_INQUIRY",
            urgency="LOW",
            sentiment="NEUTRAL",
            summary="A" * 150  # Max is 120
        )

def test_pii_entity_model():
    entity = PIIEntity(
        original_value="John Doe",
        entity_type="PERSON",
        replacement_token="[PERSON_1]",
        start_char=10,
        end_char=18
    )
    assert entity.replacement_token == "[PERSON_1]"
    assert entity.original_value == "John Doe"
