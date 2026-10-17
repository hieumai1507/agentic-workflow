"""
Health and readiness endpoints.
"""
from fastapi import APIRouter

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "agentic-pii-masking-workflow",
        "version": "1.0.0"
    }
