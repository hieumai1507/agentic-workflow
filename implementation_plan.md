# Implementation Plan: Agentic PII Masking Workflow

**Role:** Lead AI Backend Engineer  
**Status:** Ready for Execution  
**Target Tech Stack:** Python 3.11+, LangGraph 0.2+, LangChain, Redis Streams, FastAPI, Pydantic v2, Microsoft Presidio, TypeSafe AI (Jev)

---

## 1. Project Directory Layout

The codebase follows a modular, domain-driven clean architecture designed for maintainability, testability, and horizontal scaling.

```
agentic-pii-workflow/
├── .github/
│   └── workflows/
│       ├── ci-tests.yml               # Unit, integration, and linting pipeline
│       └── eval-jev.yml               # TypeSafe AI Jev evaluation gate
├── configs/
│   ├── base.yaml                      # Core pipeline configuration
│   ├── prompts/
│       ├── classifier_v1.yaml         # Versioned prompt for intent classification
│       ├── entity_masker_v1.yaml      # Versioned prompt for semantic PII masking
│       └── feedback_retry_v1.yaml     # Self-correction prompt for retry loops
├── docker/
│   ├── Dockerfile.api                 # Container for FastAPI Ingestion Service
│   ├── Dockerfile.worker              # Container for Redis Graph Worker
│   ├── Dockerfile.mock_api            # Container for Mock Jira/Zendesk API
│   └── docker-compose.yml             # Orchestration for Redis, API, Worker, Mock
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py                     # FastAPI application factory
│   │   ├── dependencies.py            # Redis client & security dependencies
│   │   └── routes/
│   │       ├── health.py              # Liveness and readiness probes
│   │       └── ingestion.py           # Webhook intake: POST /api/v1/emails/ingest
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                  # Pydantic BaseSettings management
│   │   ├── exceptions.py              # Custom domain exceptions
│   │   ├── logging.py                 # Structlog with sensitive data redactor
│   │   └── telemetry.py               # OpenTelemetry & LangSmith tracing init
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── builder.py                 # Graph compilation & state machine definition
│   │   ├── state.py                   # TypedDict AgentState & Pydantic models
│   │   ├── nodes/
│   │   │   ├── __init__.py
│   │   │   ├── normalize.py           # Header normalization & SHA hashing
│   │   │   ├── presidio_premask.py    # Microsoft Presidio deterministic scrubber
│   │   │   ├── classify.py            # LLM Issue Classification node
│   │   │   ├── semantic_mask.py       # LLM Semantic Contextual Masking node
│   │   │   ├── validator.py           # Residual PII check & schema validation
│   │   │   ├── fallback.py            # Deterministic emergency redaction node
│   │   │   └── dispatcher.py          # Egress preparation node
│   │   └── edges/
│   │       ├── __init__.py
│   │       └── router.py              # Conditional edges (retry logic, fallback route)
│   ├── prompts/
│   │   ├── __init__.py
│   │   └── manager.py                 # Prompt loading, hydration, and version control
│   ├── services/
│   │   ├── __init__.py
│   │   ├── redis_stream.py            # Redis Streams producer & consumer wrapper
│   │   ├── presidio_service.py        # Presidio Analyzer & Anonymizer engine
│   │   ├── downstream_client.py       # Resilient HTTP client for Jira/Zendesk
│   │   └── idempotency.py             # Distributed lock & deduplication service
│   ├── workers/
│   │   ├── __init__.py
│   │   ├── consumer.py                # Main worker event loop (XREADGROUP / XAUTOCLAIM)
│   │   └── dead_letter.py             # DLQ handler & alert dispatcher
│   └── mock_server/
│       ├── __init__.py
│       └── mock_jira_app.py           # FastAPI server simulating Jira Service Desk
├── tests/
│   ├── conftest.py                    # Pytest fixtures & environment setup
│   ├── unit/
│   │   ├── test_presidio_premask.py
│   │   ├── test_pydantic_schemas.py
│   │   └── test_prompt_manager.py
│   ├── integration/
│   │   ├── test_langgraph_flow.py
│   │   ├── test_redis_consumer.py
│   │   └── test_downstream_client.py
│   └── e2e/
│       └── test_full_pipeline.py
├── evals/
│   ├── __init__.py
│   ├── datasets/
│   │   └── pii_benchmark_100.json     # Curated benchmark dataset of complex emails
│   ├── run_jev_eval.py                # Automated evaluation runner using Jev
│   └── scorecards/                    # Evaluation artifacts and metrics output
├── pyproject.toml                     # Poetry / uv dependency specifications
└── README.md
```

---

## 2. Phased Implementation Roadmap

### Phase 1: Foundation, Data Contracts & Environment (Milestone 1)
- **Goal:** Establish immutable data contracts, environment setup, and baseline tooling.
- **Tasks:**
  1. Define Pydantic v2 schemas: `RawEmailInput`, `IssueClassification`, `MaskedTicketPayload`, `DownstreamTicketResponse`.
  2. Implement `AgentState` TypedDict adhering to LangGraph guidelines.
  3. Configure Docker Compose environment: Redis 7.2 (with AOF enabled), Mock Jira API, and local test environment.
  4. Implement `src/core/logging.py` with custom regex filters preventing raw PII from printing to logs.
- **Deliverables:** Unit tests validating schema serialization and Dockerized services passing health checks.

### Phase 2: LangGraph Core Pipeline & Masking Nodes (Milestone 2)
- **Goal:** Build the state machine graph, integrating deterministic pre-scrubbing and LLM semantic masking.
- **Tasks:**
  1. Implement `presidio_premask.py` utilizing Microsoft Presidio Analyzer Engine and regex for SSN, phone numbers, and credit cards.
  2. Build `classify.py` using LangChain structured outputs (`with_structured_output(IssueClassification)`).
  3. Build `semantic_mask.py` to identify context-dependent PII (person names, street addresses, company names) and assign deterministic surrogate tokens (`[PERSON_1]`, `[ADDRESS_1]`).
  4. Implement `validator.py` running dual-pass verification (schema conformance + secondary Presidio scan).
  5. Implement `fallback.py` to aggressively redact any remaining entity using strict heuristic replacement if LLM retries fail.
  6. Assemble and compile graph in `builder.py`.
- **Deliverables:** End-to-end graph unit tests passing with simulated LLM fixtures.

### Phase 3: Prompt Management & Structured Output Guardrails (Milestone 3)
- **Goal:** Isolate prompts from code, enforce versioning, and configure self-correction retry feedback loops.
- **Tasks:**
  1. Build `PromptManager` in `src/prompts/manager.py` capable of loading YAML prompt definitions with variable injection.
  2. Author few-shot prompt templates for complex masking cases (e.g., distinguishing between a product name like "Windows 11" vs a user handle "alex_11").
  3. Author `feedback_retry_v1.yaml` that feeds validator errors directly back to the LLM to steer correction.
- **Deliverables:** Regression tests verifying that invalid outputs trigger self-correction prompts.

### Phase 4: Async Ingestion & Background Worker Engine (Milestone 4)
- **Goal:** Implement the distributed queue consumer and ingestion webhook.
- **Tasks:**
  1. Build FastAPI endpoint `POST /api/v1/emails/ingest` with Pydantic validation, SHA-256 idempotency check, and Redis `XADD`.
  2. Implement Redis Streams consumer in `src/workers/consumer.py` using `XREADGROUP`, managing concurrent task limits with `asyncio.Semaphore(16)`.
  3. Implement `XAUTOCLAIM` background task for stale message recovery (>90s) in case of worker node termination.
  4. Implement DLQ forwarding when message attempts exceed 3 retries.
- **Deliverables:** Load test demonstrating ingestion at 1,000 req/sec with immediate 202 Accepted responses.

### Phase 5: Downstream Integration & Mock Jira/Zendesk API (Milestone 5)
- **Goal:** Secure, resilient egress to ticketing APIs.
- **Tasks:**
  1. Build Mock Jira/Zendesk server in `src/mock_server/mock_jira_app.py` simulating authentication, rate limits (HTTP 429), and ticket creation (HTTP 201).
  2. Implement `downstream_client.py` using `httpx.AsyncClient` with Tenacity exponential backoff (jittered retry on 429/503).
  3. Add circuit breaker pattern to halt worker ingestion if Jira/Zendesk API is persistently down.
- **Deliverables:** Integration test simulating downstream HTTP 500 errors and verifying retry/DLQ behavior.

### Phase 6: Automated Evaluation Pipeline with TypeSafe AI (Jev) (Milestone 6)
- **Goal:** Implement deterministic evaluation oracle proving zero PII leakage.
- **Tasks:**
  1. Set up TypeSafe AI SDK (`typesafe-sdk`) or direct REST client pointing to `https://api.typesafe.ai/v1/systemone`.
  2. Build synthetic test dataset of 100 complex support emails (`evals/datasets/pii_benchmark_100.json`).
  3. Build `evals/run_jev_eval.py` to evaluate pipeline output states for residual PII using Jev binary decision questions (`has_pii` -> True/False).
  4. Create GitHub Actions workflow `.github/workflows/eval-jev.yml` blocking merges if Jev detects any PII leakage.
- **Deliverables:** Complete eval report proving 100% PII scrub rate and 0% False Negative Rate.

---

## 3. Deep-Dive Technical Implementation

### 3.1 State Schema & Domain Models (`src/graph/state.py`)

```python
"""
Domain models and LangGraph state definitions for the PII masking pipeline.
"""
from typing import TypedDict, List, Dict, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field, EmailStr

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

class IssueClassification(BaseModel):
    category: TicketCategory = Field(..., description="High-level category of the issue")
    urgency: TicketPriority = Field(..., description="Urgency priority of the ticket")
    sentiment: str = Field(..., description="Customer sentiment (POSITIVE, NEUTRAL, NEGATIVE, FRUSTRATED)")
    summary: str = Field(..., max_length=120, description="Clean 1-sentence summary of the user issue")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence of classification")

class PIIReplacementToken(BaseModel):
    token: str = Field(..., description="Synthetic token e.g. [PERSON_1]")
    entity_type: str = Field(..., description="Entity category: SSN, EMAIL, PHONE, PERSON, ADDRESS, CREDIT_CARD")
    original_value: str = Field(..., description="Raw sensitive value (internal state only)")

class SemanticMaskingResult(BaseModel):
    masked_body: str = Field(..., description="Email body with all contextual PII replaced by surrogate tokens")
    extracted_entities: List[PIIReplacementToken] = Field(default_factory=list)

class AgentState(TypedDict):
    # Metadata & Tracking
    job_id: str
    email_id: str
    sender: str
    subject: str
    raw_body: str
    received_at: str
    content_hash: str

    # Pipeline Working Buffers
    presidio_masked_body: str
    surrogate_mapping: Dict[str, str] # { "[SSN_1]": "000-12-3456" }

    # LLM Structured Artifacts
    classification: Optional[IssueClassification]
    semantic_mask_result: Optional[SemanticMaskingResult]

    # Final Sanitized Output
    sanitized_subject: str
    sanitized_body: str

    # Control Flow & Reliability
    retry_count: int
    max_retries: int
    validation_errors: List[str]
    is_fallback_triggered: bool
    status: str # "QUEUED", "PROCESSING", "VALIDATING", "SUCCESS", "FALLBACK", "FAILED"
    error_log: List[str]
    dispatched_ticket_id: Optional[str]
```

---

### 3.2 LangGraph Graph Construction (`src/graph/builder.py`)

```python
"""
LangGraph Workflow Builder: Assembles nodes, edges, retry loops, and fallback routes.
"""
from langgraph.graph import StateGraph, END
from src.graph.state import AgentState
from src.graph.nodes.normalize import ingest_and_normalize_node
from src.graph.nodes.presidio_premask import presidio_premask_node
from src.graph.nodes.classify import classify_issue_node
from src.graph.nodes.semantic_mask import semantic_mask_node
from src.graph.nodes.validator import validate_masked_state_node
from src.graph.nodes.fallback import fallback_scrubber_node
from src.graph.nodes.dispatcher import dispatch_to_mock_api_node
from src.graph.edges.router import should_continue_or_fallback, should_retry_masking

def build_pii_masking_graph():
    """Compiles and returns the LangGraph state machine."""
    workflow = StateGraph(AgentState)

    # Register Nodes
    workflow.add_node("normalize", ingest_and_normalize_node)
    workflow.add_node("presidio_premask", presidio_premask_node)
    workflow.add_node("classify", classify_issue_node)
    workflow.add_node("semantic_mask", semantic_mask_node)
    workflow.add_node("validator", validate_masked_state_node)
    workflow.add_node("fallback", fallback_scrubber_node)
    workflow.add_node("dispatch", dispatch_to_mock_api_node)

    # Standard Linear Edges
    workflow.set_entry_point("normalize")
    workflow.add_edge("normalize", "presidio_premask")
    workflow.add_edge("presidio_premask", "classify")
    workflow.add_edge("classify", "semantic_mask")
    workflow.add_edge("semantic_mask", "validator")

    # Conditional Validation Routing
    workflow.add_conditional_edges(
        "validator",
        should_continue_or_fallback,
        {
            "dispatch": "dispatch",
            "retry": "semantic_mask",
            "fallback": "fallback"
        }
    )

    # Fallback always routes to dispatch
    workflow.add_edge("fallback", "dispatch")
    workflow.add_edge("dispatch", END)

    app = workflow.compile()
    return app
```

---

### 3.3 Conditional Routing Logic (`src/graph/edges/router.py`)

```python
"""
Conditional edge evaluation for self-healing loops and fallbacks.
"""
import structlog
from src.graph.state import AgentState

logger = structlog.get_logger(__name__)

def should_continue_or_fallback(state: AgentState) -> str:
    """
    Evaluates validator node outputs to determine whether to proceed,
    retry the LLM masking step, or execute deterministic fallback.
    """
    errors = state.get("validation_errors", [])
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 3)

    if not errors:
        logger.info("Validation passed successfully", job_id=state["job_id"])
        return "dispatch"

    if retry_count < max_retries:
        logger.warning(
            "Validation errors detected. Triggering self-correction retry",
            job_id=state["job_id"],
            retry_count=retry_count + 1,
            errors=errors
        )
        return "retry"

    logger.error(
        "Max retries exhausted. Diverting to deterministic fallback scrubber",
        job_id=state["job_id"],
        retry_count=retry_count,
        errors=errors
    )
    return "fallback"
```

---

### 3.4 Prompt Management & Structured Output Guardrails

#### 3.4.1 Prompt Template (`configs/prompts/entity_masker_v1.yaml`)

```yaml
version: "1.0.0"
description: "Zero-leakage prompt for contextual entity recognition and pseudonymization"
system_prompt: |
  You are an expert Data Privacy and Anonymization Engine.
  Your sole responsibility is to identify sensitive Personally Identifiable Information (PII)
  and replace it with deterministic, sequential surrogate tokens.

  Entity Categories to Redact:
  - [PERSON_N]: Names of individuals (customers, employees, family members).
  - [ADDRESS_N]: Physical street addresses, apartment numbers, zip codes, and geographic locations.
  - [ORG_N]: Sensitive organization, workplace, or employer names.
  - [CREDENTIAL_N]: Usernames, passwords, PINs, security question answers.

  Rules:
  1. DO NOT redact general software or product names (e.g., 'MacBook Pro', 'Google Chrome', 'Windows').
  2. If the same person or entity appears multiple times, use the IDENTICAL surrogate token consistently.
  3. Pre-masked tokens like [SSN_1] or [PHONE_1] must be preserved verbatim.
  4. Return strictly valid structured JSON matching the provided schema. Do not include markdown codeblocks or conversational text.

few_shot_examples:
  - input: "Hello, my name is Arthur Dent and I live at 155 Country Lane, Cottington. Please help my wife Trillian."
    output:
      masked_body: "Hello, my name is [PERSON_1] and I live at [ADDRESS_1]. Please help my wife [PERSON_2]."
      extracted_entities:
        - token: "[PERSON_1]"
          entity_type: "PERSON"
          original_value: "Arthur Dent"
        - token: "[ADDRESS_1]"
          entity_type: "ADDRESS"
          original_value: "155 Country Lane, Cottington"
        - token: "[PERSON_2]"
          entity_type: "PERSON"
          original_value: "Trillian"
```

#### 3.4.2 LLM Invocation with Self-Correction Feedback (`src/graph/nodes/semantic_mask.py`)

```python
"""
Semantic Masking Node with Pydantic structured output and retry context.
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from src.graph.state import AgentState, SemanticMaskingResult
from src.prompts.manager import get_prompt_template

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
structured_llm = llm.with_structured_output(SemanticMaskingResult)

async def semantic_mask_node(state: AgentState) -> Dict[str, Any]:
    """Runs semantic masking, injecting previous errors if retrying."""
    prompt_config = get_prompt_template("entity_masker_v1")
    
    # Check if this is a retry invocation
    retry_feedback = ""
    if state.get("validation_errors"):
        retry_feedback = (
            f"\n\nCRITICAL PREVIOUS FAILURE NOTICE:\n"
            f"Your previous masking attempt failed validation due to the following reasons:\n"
            f"- " + "\n- ".join(state["validation_errors"]) + "\n"
            f"You MUST fix these residual PII leaks or schema errors immediately."
        )

    system_msg = SystemMessage(content=prompt_config["system_prompt"] + retry_feedback)
    human_msg = HumanMessage(
        content=f"Subject: {state['subject']}\n\nBody to Mask:\n{state['presidio_masked_body']}"
    )

    result: SemanticMaskingResult = await structured_llm.ainvoke([system_msg, human_msg])

    # Merge surrogate mappings
    updated_surrogates = dict(state.get("surrogate_mapping", {}))
    for entity in result.extracted_entities:
        updated_surrogates[entity.token] = entity.original_value

    return {
        "semantic_mask_result": result,
        "sanitized_body": result.masked_body,
        "surrogate_mapping": updated_surrogates,
        "retry_count": state.get("retry_count", 0) + (1 if state.get("validation_errors") else 0),
        "validation_errors": [] # Clear errors for next validation pass
    }
```

---

### 3.5 High-Throughput Redis Streams Consumer Loop (`src/workers/consumer.py`)

```python
"""
Redis Streams Consumer with XREADGROUP, concurrency throttling, and crash recovery.
"""
import asyncio
import json
import structlog
import redis.asyncio as aioredis
from src.core.config import settings
from src.graph.builder import build_pii_masking_graph

logger = structlog.get_logger(__name__)

STREAM_NAME = "email_ingestion_stream"
GROUP_NAME = "agentic_masking_workers"
CONSUMER_NAME = f"worker_{settings.WORKER_ID}"
MAX_CONCURRENT_TASKS = 16
IDLE_TIME_FOR_AUTOCLAIM_MS = 90_000

graph_app = build_pii_masking_graph()
semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

async def process_message(redis_client: aioredis.Redis, msg_id: str, raw_payload: dict):
    """Processes an individual message through the compiled LangGraph pipeline."""
    async with semaphore:
        job_id = raw_payload.get("job_id")
        logger.info("Executing LangGraph for job", job_id=job_id, msg_id=msg_id)
        
        initial_state = {
            "job_id": job_id,
            "email_id": raw_payload.get("email_id"),
            "sender": raw_payload.get("sender"),
            "subject": raw_payload.get("subject"),
            "raw_body": raw_payload.get("body"),
            "received_at": raw_payload.get("received_at"),
            "content_hash": raw_payload.get("content_hash"),
            "retry_count": 0,
            "max_retries": 3,
            "validation_errors": [],
            "is_fallback_triggered": False,
            "status": "PROCESSING",
            "error_log": []
        }

        try:
            final_state = await graph_app.ainvoke(initial_state)
            
            if final_state.get("status") == "SUCCESS":
                # Acknowledge message upon successful execution
                await redis_client.xack(STREAM_NAME, GROUP_NAME, msg_id)
                logger.info("Job completed and acknowledged", job_id=job_id, msg_id=msg_id)
            else:
                # Route to Dead-Letter Queue
                await route_to_dlq(redis_client, msg_id, raw_payload, final_state.get("error_log"))
                await redis_client.xack(STREAM_NAME, GROUP_NAME, msg_id)

        except Exception as exc:
            logger.exception("Uncaught exception in graph execution", job_id=job_id, error=str(exc))
            await route_to_dlq(redis_client, msg_id, raw_payload, [str(exc)])
            await redis_client.xack(STREAM_NAME, GROUP_NAME, msg_id)

async def route_to_dlq(redis_client: aioredis.Redis, msg_id: str, raw_payload: dict, error_log: list):
    """Stores poison pill payloads in the DLQ stream."""
    dlq_payload = {
        "original_message_id": msg_id,
        "payload": json.dumps(raw_payload),
        "errors": json.dumps(error_log)
    }
    await redis_client.xadd("email_dlq_stream", dlq_payload)
    logger.error("Message routed to DLQ", msg_id=msg_id)

async def run_worker():
    """Main consumer loop reading from Redis Streams."""
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    # Create stream group if not exists
    try:
        await redis_client.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
    except aioredis.ResponseError:
        pass # Group already exists

    logger.info("Redis worker initialized", group=GROUP_NAME, consumer=CONSUMER_NAME)

    while True:
        try:
            # 1. Autoclaim messages from dead workers
            claims = await redis_client.xautoclaim(
                STREAM_NAME, GROUP_NAME, CONSUMER_NAME,
                min_idle_time=IDLE_TIME_FOR_AUTOCLAIM_MS,
                start_id="0-0", count=5
            )
            claimed_messages = claims[1]
            for msg_id, data in claimed_messages:
                payload = json.loads(data["payload"])
                asyncio.create_task(process_message(redis_client, msg_id, payload))

            # 2. Read new messages
            streams = await redis_client.xreadgroup(
                GROUP_NAME, CONSUMER_NAME,
                {STREAM_NAME: ">"}, count=10, block=2000
            )

            if streams:
                for _, messages in streams:
                    for msg_id, data in messages:
                        payload = json.loads(data["payload"])
                        asyncio.create_task(process_message(redis_client, msg_id, payload))

        except Exception as e:
            logger.error("Error in consumer loop", error=str(e))
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(run_worker())
```

---

### 3.6 Downstream API Client (`src/services/downstream_client.py`)

```python
"""
Resilient client for Jira/Zendesk API with Tenacity retries and circuit breakers.
"""
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import structlog
from src.core.config import settings

logger = structlog.get_logger(__name__)

class TemporaryDownstreamError(Exception):
    pass

class DownstreamClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=settings.DOWNSTREAM_API_BASE_URL,
            timeout=10.0,
            headers={"Authorization": f"Bearer {settings.DOWNSTREAM_API_TOKEN}"}
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(TemporaryDownstreamError)
    )
    async def create_support_ticket(self, payload: dict) -> dict:
        """Dispatches clean ticket payload to mock Jira/Zendesk API."""
        try:
            response = await self.client.post("/rest/api/3/issue", json=payload)
            
            if response.status_code in [429, 502, 503, 504]:
                logger.warning("Transient error from ticketing API. Retrying...", status_code=response.status_code)
                raise TemporaryDownstreamError(f"HTTP {response.status_code}")

            response.raise_for_status()
            return response.json()

        except httpx.RequestError as exc:
            logger.error("Network failure communicating with downstream API", error=str(exc))
            raise TemporaryDownstreamError(str(exc)) from exc
```

---

## 4. Dependencies & Environment Configuration (`pyproject.toml`)

```toml
[tool.poetry]
name = "agentic-pii-masking-workflow"
version = "0.1.0"
description = "Production-grade asynchronous Agentic PII Masking Workflow using LangGraph and TypeSafe AI"
authors = ["Lead AI Backend Engineer <lead@engineering.internal>"]
python = "^3.11"

[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.111.0"
uvicorn = {extras = ["standard"], version = "^0.30.0"}
langgraph = "^0.2.16"
langchain = "^0.2.7"
langchain-openai = "^0.1.14"
pydantic = "^2.8.2"
pydantic-settings = "^2.3.4"
redis = {extras = ["hiredis"], version = "^5.0.7"}
presidio-analyzer = "^2.2.355"
presidio-anonymizer = "^2.2.355"
httpx = "^0.27.0"
tenacity = "^8.5.0"
structlog = "^24.2.0"
opentelemetry-api = "^1.25.0"
opentelemetry-sdk = "^1.25.0"
typesafe-sdk = "^0.2.4"

[tool.poetry.group.dev.dependencies]
pytest = "^8.2.2"
pytest-asyncio = "^0.23.7"
pytest-mock = "^3.14.0"
black = "^24.4.2"
ruff = "^0.5.1"
mypy = "^1.10.1"

[build-system]
requires = ["poetry-core>=1.0.0"]
build-backend = "poetry.core.masonry.api"
```

---

## 5. Verification & Acceptance Criteria

| Stage | Criteria | Verification Command |
| :--- | :--- | :--- |
| **Lint & Types** | Zero MyPy errors in strict mode; Ruff clean | `ruff check src/ && mypy --strict src/` |
| **Unit Testing** | Coverage > 90% across nodes, state schemas, and edges | `pytest tests/unit --cov=src` |
| **Graph Self-Correction** | 100% of simulated hallucinations correctly trigger retry node | `pytest tests/integration/test_langgraph_flow.py -k test_retry` |
| **Throughput & Queues** | Ingestion accepts 1,000 req/sec; worker completes queue without unhandled crashes | `locust -f tests/load/locustfile.py --headless -u 100 -r 20` |
| **Deterministic Egress** | Zero residual SSN, Phone, or Email tokens detected in mock Jira output payloads | Verified via automated test suite and Jev eval pipeline |
