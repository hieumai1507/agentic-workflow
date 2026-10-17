"""
Enterprise De-Anonymization Vault Route.
Enforces Role-Based Access Control (RBAC) and immutable cryptographic audit logging.
"""
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, Header, status
from pydantic import BaseModel, Field
import structlog
from src.services.vault_service import vault_service, VaultSecurityException

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/vault", tags=["Reversible Vault & De-Anonymization"])

class RevealRequest(BaseModel):
    vault_id: str = Field(..., description="Target vault record identifier")
    token: str = Field(..., description="Surrogate token to reveal e.g. [PERSON_1]")
    accessor_id: str = Field(..., description="Employee / Officer ID requesting reveal")
    role: str = Field(..., description="Assigned RBAC role (e.g. ROLE_DPO, ROLE_L3_LEAD)")
    reason: str = Field(..., min_length=10, description="Mandatory business/legal justification for audit trail")

class RevealResponse(BaseModel):
    token: str
    plaintext_value: str
    vault_id: str
    audit_logged: bool = True

@router.post(
    "/reveal",
    response_model=RevealResponse,
    status_code=status.HTTP_200_OK,
    summary="Reveal masked PII token with RBAC authorization and immutable audit logging"
)
async def reveal_token(payload: RevealRequest):
    """
    Authorized de-anonymization gate.
    Decrypts AES-256-GCM ciphertext only if caller possesses an authorized role.
    """
    try:
        plaintext = vault_service.reveal_token(
            vault_id=payload.vault_id,
            token=payload.token,
            accessor_id=payload.accessor_id,
            role=payload.role,
            reason=payload.reason
        )

        return RevealResponse(
            token=payload.token,
            plaintext_value=plaintext,
            vault_id=payload.vault_id,
            audit_logged=True
        )

    except VaultSecurityException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc)
        )

@router.get(
    "/audit-trail",
    response_model=List[Dict[str, Any]],
    summary="Retrieve immutable cryptographic audit trail of all reveal requests"
)
async def get_audit_trail():
    """Returns tamper-evident audit logs of all historical reveal requests."""
    return vault_service.get_audit_trail()
