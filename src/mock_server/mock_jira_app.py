"""
Mock Jira / Zendesk Service Desk API Server.
Simulates authentication, payload verification, rate-limiting (429), and issue creation.
"""
from typing import Dict, Any, List
import uuid
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

app = FastAPI(title="Mock Jira & Zendesk Ticketing API", version="1.0.0")

# In-memory ticket storage
CREATED_TICKETS: Dict[str, Dict[str, Any]] = {}

# Test hooks for transient error simulation
SIMULATE_RATE_LIMIT_ONCE = False
SIMULATE_OUTAGE = False

class TicketMetadata(BaseModel):
    category: str
    priority: str
    sentiment: str
    summary: str

class SanitizedContent(BaseModel):
    subject: str
    scrubbed_body: str
    anonymized_entities: List[Dict[str, str]]

class TicketCreatePayload(BaseModel):
    external_job_id: str
    source_system: str
    ticket_metadata: TicketMetadata
    sanitized_content: SanitizedContent
    audit_trail: Dict[str, Any]

@app.get("/health")
async def health():
    return {"status": "ok", "tickets_count": len(CREATED_TICKETS)}

@app.post("/rest/api/3/issue", status_code=status.HTTP_201_CREATED)
async def create_issue(payload: TicketCreatePayload, authorization: str = Header(None)):
    global SIMULATE_RATE_LIMIT_ONCE, SIMULATE_OUTAGE

    if not authorization or "Bearer" not in authorization:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing Bearer Token")

    if SIMULATE_OUTAGE:
        raise HTTPException(status_code=503, detail="Service Unavailable: Mock Jira Outage")

    if SIMULATE_RATE_LIMIT_ONCE:
        SIMULATE_RATE_LIMIT_ONCE = False
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please retry later.")

    ticket_number = len(CREATED_TICKETS) + 1001
    ticket_key = f"SUP-{ticket_number}"
    ticket_id = str(uuid.uuid4())

    ticket_record = {
        "id": ticket_id,
        "key": ticket_key,
        "payload": payload.model_dump(),
        "created_at": "2026-10-17T13:00:00Z"
    }
    CREATED_TICKETS[ticket_key] = ticket_record

    return {
        "id": ticket_id,
        "key": ticket_key,
        "self": f"http://localhost:8001/rest/api/3/issue/{ticket_key}",
        "status": "CREATED"
    }

@app.get("/rest/api/3/issue/{key}")
async def get_issue(key: str):
    if key not in CREATED_TICKETS:
        raise HTTPException(status_code=404, detail="Issue not found")
    return CREATED_TICKETS[key]

@app.delete("/rest/api/3/test/reset")
async def reset_test_state():
    global SIMULATE_RATE_LIMIT_ONCE, SIMULATE_OUTAGE
    CREATED_TICKETS.clear()
    SIMULATE_RATE_LIMIT_ONCE = False
    SIMULATE_OUTAGE = False
    return {"status": "reset"}
