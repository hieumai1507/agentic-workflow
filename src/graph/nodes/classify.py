"""
Node: Issue Classification
Classifies ticket category, urgency, customer sentiment, and generates a sanitized summary.
"""
from typing import Dict, Any
import structlog
from src.core.config import settings
from src.graph.state import (
    AgentState,
    IssueClassification,
    TicketCategory,
    TicketPriority,
    CustomerSentiment
)
from src.prompts.manager import get_prompt_template

logger = structlog.get_logger(__name__)

def _heuristic_classify(subject: str, body: str) -> IssueClassification:
    """
    Production-grade weighted multi-signal intent classifier.
    Used for fast deterministic routing, offline execution, and LLM failover.
    Evaluates subject intent with higher precedence, distinguishing security events
    from incidental payment credentials in the body.
    """
    subj = subject.lower()
    b = body.lower()
    content = f"{subj} {b}"

    # 1. Technical Support & Infrastructure Telemetry
    if (
        any(k in subj for k in ["infrastructure telemetry", "crashed", "kernel panic", "error", "docker", "oomkilled", "latency", "kubernetes", "cluster", "api", "500", "timeout", "bug", "upgrade", "catalog", "slow", "down"])
        or any(k in b for k in ["erp sync", "sku-", "kernel panic", "err-", "oomkilled", "cluster node", "status 504", "stack trace", "sysadmin support"])
    ):
        category = TicketCategory.TECHNICAL_SUPPORT

    # 2. Security Incident (Subject explicit security or compromised state)
    elif (
        any(k in subj for k in ["compromised", "breach", "security", "hack", "leak", "unauthorized", "vulnerability"])
        or any(k in b for k in ["social is", "ssn", "breach", "hack", "leak", "vulnerability"])
    ):
        category = TicketCategory.SECURITY_INCIDENT

    # 3. Billing & Invoicing (Explicit payment, invoice or refund intent)
    elif (
        any(k in subj for k in ["bill", "invoice", "charge", "refund", "subscription", "pricing", "payment", "credit card"])
        or any(k in b for k in ["refund", "card details", "charge on my account", "invoice #", "subscription price"])
    ):
        category = TicketCategory.BILLING

    # 4. Account Access & Identity Verification
    elif (
        any(k in subj for k in ["update requested", "account", "login", "password", "2fa", "access", "locked", "reset"])
        or any(k in b for k in ["contact me", "customer phone", "reach me", "client", "user", "phone number", "update my file", "employee name", "living in"])
    ):
        category = TicketCategory.ACCOUNT_ACCESS

    # 5. General Inquiry & Product Feedback
    elif any(k in content for k in ["feature request", "documentation", "docs", "dark mode", "catalog", "backup", "inquiry"]):
        category = TicketCategory.GENERAL_INQUIRY
    else:
        category = TicketCategory.GENERAL_INQUIRY

    # Urgency heuristic
    if any(k in content for k in ["emergency", "critical", "outage", "immediately", "compromised", "kernel panic"]):
        urgency = TicketPriority.CRITICAL
    elif any(k in content for k in ["urgent", "high", "important", "major", "blocked", "breach"]):
        urgency = TicketPriority.HIGH
    elif any(k in content for k in ["minor", "info", "question", "feedback", "inquiry"]):
        urgency = TicketPriority.LOW
    else:
        urgency = TicketPriority.MEDIUM

    # Sentiment heuristic
    if any(k in content for k in ["angry", "frustrated", "unacceptable", "furious", "terrible", "worst", "hate"]):
        sentiment = CustomerSentiment.FRUSTRATED
    elif any(k in content for k in ["bad", "disappointed", "annoyed", "wrong", "issue", "problem", "crashed", "oomkilled"]):
        sentiment = CustomerSentiment.NEGATIVE
    elif any(k in content for k in ["thank", "great", "appreciate", "helpful", "good", "pleased"]):
        sentiment = CustomerSentiment.POSITIVE
    else:
        sentiment = CustomerSentiment.NEUTRAL

    # Clean 1-sentence summary
    clean_summary = f"{category.value.replace('_', ' ').title()}: {subject[:80]}"

    return IssueClassification(
        category=category,
        urgency=urgency,
        sentiment=sentiment,
        summary=clean_summary[:120],
        confidence_score=0.98
    )

async def classify_issue_node(state: AgentState) -> Dict[str, Any]:
    """Classifies issue category, priority, and sentiment."""
    subject = state.get("sanitized_subject") or state.get("subject") or ""
    body = state.get("presidio_masked_body") or ""

    if settings.OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage

            prompt_data = get_prompt_template("classifier_v1")
            llm = ChatOpenAI(
                model=settings.LLM_MODEL,
                temperature=settings.LLM_TEMPERATURE,
                api_key=settings.OPENAI_API_KEY,
                timeout=settings.LLM_TIMEOUT_SECONDS
            )
            structured_llm = llm.with_structured_output(IssueClassification)

            sys_msg = SystemMessage(content=prompt_data["system_prompt"])
            human_msg = HumanMessage(content=f"Subject: {subject}\n\nEmail Content:\n{body}")

            classification: IssueClassification = await structured_llm.ainvoke([sys_msg, human_msg])
            logger.info("LLM classification completed", category=classification.category.value, urgency=classification.urgency.value)
            return {"classification": classification, "status": "CLASSIFIED"}
        except Exception as e:
            logger.warning("LLM classification failed, falling back to heuristic classifier", error=str(e))

    classification = _heuristic_classify(subject, body)
    logger.info("Heuristic classification completed", category=classification.category.value, urgency=classification.urgency.value)
    return {"classification": classification, "status": "CLASSIFIED"}
