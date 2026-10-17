"""
Unit tests for YAML prompt manager and formatting.
"""
import pytest
from src.prompts.manager import get_prompt_template, format_retry_feedback

def test_load_existing_prompt_templates():
    classifier_tmpl = get_prompt_template("classifier_v1")
    assert "version" in classifier_tmpl
    assert "system_prompt" in classifier_tmpl
    assert "BILLING" in classifier_tmpl["system_prompt"]

    masker_tmpl = get_prompt_template("entity_masker_v1")
    assert "version" in masker_tmpl
    assert "few_shot_examples" in masker_tmpl
    assert len(masker_tmpl["few_shot_examples"]) > 0

def test_nonexistent_prompt_template_raises_error():
    with pytest.raises(FileNotFoundError):
        get_prompt_template("non_existent_prompt_xyz")

def test_format_retry_feedback():
    errors = [
        "Residual PII: Detected unmasked Social Security Number",
        "Schema error: Summary too long"
    ]
    feedback = format_retry_feedback(errors)
    assert "CRITICAL PREVIOUS FAILURE NOTICE" in feedback
    assert "Residual PII: Detected unmasked Social Security Number" in feedback
    assert "Schema error: Summary too long" in feedback
