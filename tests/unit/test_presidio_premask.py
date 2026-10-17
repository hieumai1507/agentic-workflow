"""
Unit tests for deterministic Presidio & Regex masking service.
"""
import pytest
from src.services.presidio_service import deterministic_masker

def test_mask_standard_ssn_and_credit_card():
    text = "My SSN is 123-45-6789 and my card is 4111-2222-3333-4444."
    masked, surrogates, entities = deterministic_masker.mask(text)

    assert "[SSN_1]" in masked
    assert "[CARD_1]" in masked
    assert "123-45-6789" not in masked
    assert "4111-2222-3333-4444" not in masked
    assert surrogates["[SSN_1]"] == "123-45-6789"
    assert surrogates["[CARD_1]"] == "4111-2222-3333-4444"

def test_mask_spaced_adversarial_ssn():
    text = "My social is 9 - 8 - 7 - 6 5 - 4 3 2 1. Please update."
    masked, surrogates, _ = deterministic_masker.mask(text)

    assert "[SSN_" in masked
    assert "9 - 8 - 7 - 6 5 - 4 3 2 1" not in masked

def test_mask_emails_standard_and_obfuscated():
    text = "Contact support@example.com or backup [at] domain [dot] org for help."
    masked, surrogates, _ = deterministic_masker.mask(text)

    assert "[EMAIL_1]" in masked
    assert "[EMAIL_2]" in masked
    assert "support@example.com" not in masked
    assert "backup [at] domain [dot] org" not in masked

def test_identical_pii_gets_identical_surrogate_token():
    text = "Please email alex@test.com right away. Once again, that is alex@test.com."
    masked, surrogates, _ = deterministic_masker.mask(text)

    # Must contain [EMAIL_1] twice, not [EMAIL_2]
    assert masked.count("[EMAIL_1]") == 2
    assert "[EMAIL_2]" not in masked
    assert len(surrogates) == 1
    assert surrogates["[EMAIL_1]"] == "alex@test.com"

def test_preserve_error_codes_and_versions():
    text = "Server threw error ERR-902-1249 with release v2.14.0 on port 8080."
    masked, surrogates, _ = deterministic_masker.mask(text)

    assert "ERR-902-1249" in masked
    assert "v2.14.0" in masked
    assert len(surrogates) == 0
