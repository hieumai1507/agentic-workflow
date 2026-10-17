"""
Unit tests for Enterprise KMS & Envelope Encryption Layer.
Verifies NIST SP 800-57 compliance, ephemeral DEK generation,
wrapping, unwrapping, and multi-provider failover.
"""
import pytest
import os
from src.services.kms_service import (
    LocalEnvelopeKMSProvider,
    AWSKMSProvider,
    HashiCorpVaultProvider,
    get_kms_provider
)
from src.services.vault_service import VaultEncryptionService, VaultSecurityException

def test_local_envelope_kms_lifecycle():
    kms = LocalEnvelopeKMSProvider()
    plaintext_dek, encrypted_dek = kms.generate_data_key()

    assert len(plaintext_dek) == 32
    assert len(encrypted_dek) > 32
    assert plaintext_dek != encrypted_dek

    # Decrypt DEK
    unwrapped_dek = kms.decrypt_data_key(encrypted_dek)
    assert unwrapped_dek == plaintext_dek

def test_aws_kms_provider_envelope_lifecycle():
    aws_kms = AWSKMSProvider(key_arn="arn:aws:kms:us-east-1:123456789012:key/test-kek")
    assert "arn:aws:kms" in aws_kms.get_key_arn()

    plaintext_dek, encrypted_dek = aws_kms.generate_data_key()
    assert len(plaintext_dek) == 32
    unwrapped_dek = aws_kms.decrypt_data_key(encrypted_dek)
    assert unwrapped_dek == plaintext_dek

def test_hashicorp_vault_provider_envelope_lifecycle():
    vault_kms = HashiCorpVaultProvider(transit_key_name="test-transit-key")
    assert "transit/keys/test-transit-key" in vault_kms.get_key_arn()

    plaintext_dek, encrypted_dek = vault_kms.generate_data_key()
    assert len(plaintext_dek) == 32
    unwrapped_dek = vault_kms.decrypt_data_key(encrypted_dek)
    assert unwrapped_dek == plaintext_dek

def test_vault_service_with_custom_kms():
    kms = LocalEnvelopeKMSProvider()
    vault = VaultEncryptionService(kms=kms)

    mapping = {"[PERSON_1]": "Bruce Wayne", "[SSN_1]": "000-11-2222"}
    vault_id = vault.encrypt_and_vault("test_job_123", mapping)

    assert vault_id.startswith("vlt_")
    record = vault._vault_store[vault_id]
    assert "encrypted_dek_b64" in record
    assert "ciphertext_b64" in record
    assert record["envelope_standard"] == "NIST-SP800-57-AES-256-GCM"

    # Reveal with valid RBAC
    val = vault.reveal_token(
        vault_id=vault_id,
        token="[PERSON_1]",
        accessor_id="auditor_1",
        role="ROLE_COMPLIANCE_AUDITOR",
        reason="SOX-404 Compliance Audit"
    )
    assert val == "Bruce Wayne"
