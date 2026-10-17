"""
Application configuration management using Pydantic Settings.
Includes Enterprise configurations for Vault KMS, HITL, and OpenTelemetry.
"""
import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Agentic PII Masking Workflow"
    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"

    # Redis configuration
    REDIS_URL: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    STREAM_NAME: str = "email_ingestion_stream"
    GROUP_NAME: str = "agentic_masking_workers"
    DLQ_STREAM_NAME: str = "email_dlq_stream"
    WORKER_ID: str = Field(default="worker_1", alias="WORKER_ID")
    MAX_CONCURRENT_TASKS: int = 16
    IDLE_TIME_FOR_AUTOCLAIM_MS: int = 90_000

    # LLM configuration & Multi-Model Gateway
    OPENAI_API_KEY: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    LLM_PRIMARY_MODEL: str = "gpt-4o-mini"
    LLM_FALLBACK_MODEL: str = "claude-3-5-sonnet-20241022"
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_RETRIES: int = 3
    LLM_TIMEOUT_SECONDS: float = 15.0
    CIRCUIT_BREAKER_FAIL_THRESHOLD: int = 3
    CIRCUIT_BREAKER_RECOVERY_SECONDS: int = 60

    # Enterprise Cloud KMS & Envelope Encryption
    KMS_PROVIDER: str = Field(default="local_envelope", alias="KMS_PROVIDER") # "aws_kms", "hashicorp_vault", "local_envelope"
    AWS_KMS_KEY_ARN: str = Field(
        default="arn:aws:kms:us-east-1:123456789012:key/mrk-pii-vault-master-kek",
        alias="AWS_KMS_KEY_ARN"
    )
    AWS_REGION: str = Field(default="us-east-1", alias="AWS_REGION")
    HASHICORP_VAULT_ADDR: str = Field(default="http://127.0.0.1:8200", alias="HASHICORP_VAULT_ADDR")
    HASHICORP_VAULT_TOKEN: Optional[str] = Field(default=None, alias="HASHICORP_VAULT_TOKEN")
    HASHICORP_TRANSIT_KEY: str = Field(default="pii-vault-transit-kek", alias="HASHICORP_TRANSIT_KEY")
    VAULT_MASTER_KEY: str = Field(
        default="dGhpcy1pcy1hLXNlY3VyZS0zMi1ieXRlLXZhdWx0LWtleSE=", # Base64 32-byte key for local envelope KMS
        alias="VAULT_MASTER_KEY"
    )
    VAULT_STORAGE_TTL_SECONDS: int = 86400 * 30 # 30 days retention

    # Cascade Routing / Tiered Processing (Token & Latency Optimization)
    ENABLE_CASCADE_ROUTING: bool = True # Route deterministic/clean emails via Fast-Path, bypassing LLM

    # Human-in-the-Loop (HITL) Governance
    ENABLE_HITL_FOR_SECURITY_INCIDENTS: bool = True
    HITL_CONFIDENCE_THRESHOLD: float = 0.90 # Cases below this trigger human review

    # Downstream API (Mock Jira/Zendesk)
    DOWNSTREAM_API_BASE_URL: str = Field(default="http://localhost:8001", alias="DOWNSTREAM_API_BASE_URL")
    DOWNSTREAM_API_TOKEN: str = "mock_jira_token_secure_9921"
    DOWNSTREAM_TIMEOUT: float = 10.0

    # TypeSafe AI (Jev) Evaluator
    TYPESAFE_API_KEY: Optional[str] = Field(default=None, alias="TYPESAFE_API_KEY")
    TYPESAFE_ENDPOINT: str = "https://api.typesafe.ai/v1/systemone"
    TYPESAFE_MODEL: str = "jev-1.13"
    JEV_CONFIDENCE_THRESHOLD: float = 0.90

settings = Settings()
