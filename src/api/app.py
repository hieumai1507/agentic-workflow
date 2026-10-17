"""
FastAPI application factory and middleware registration.
Includes Enterprise routes for Metrics, HITL Governance, and De-Anonymization Vault.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.config import settings
from src.api.routes.health import router as health_router
from src.api.routes.ingestion import router as ingestion_router
from src.api.routes.metrics import router as metrics_router
from src.api.routes.reviews import router as reviews_router
from src.api.routes.vault import router as vault_router

def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.APP_NAME} (Enterprise Edition)",
        description="Enterprise Asynchronous Agentic PII Masking Workflow with LangGraph, Vault KMS & HITL Governance",
        version="2.0.0"
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Core Routes
    app.include_router(health_router)
    app.include_router(ingestion_router)

    # Enterprise Pillars
    app.include_router(metrics_router)
    app.include_router(reviews_router)
    app.include_router(vault_router)

    return app

app = create_app()
