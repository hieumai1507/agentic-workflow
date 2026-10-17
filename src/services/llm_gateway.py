"""
Multi-Model LLM Gateway with Circuit Breaker Pattern.
Provides automatic failover between primary and secondary AI providers.
"""
import time
from typing import Optional, Dict, Any
import structlog
from src.core.config import settings

logger = structlog.get_logger(__name__)

class CircuitState:
    CLOSED = "CLOSED"      # Normal operation, routing to Primary
    OPEN = "OPEN"          # Tripped, routing to Secondary
    HALF_OPEN = "HALF_OPEN"# Testing primary recovery

class MultiModelGateway:
    def __init__(self):
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.last_failure_time = 0.0
        self.primary_model = settings.LLM_PRIMARY_MODEL
        self.fallback_model = settings.LLM_FALLBACK_MODEL
        self.fail_threshold = settings.CIRCUIT_BREAKER_FAIL_THRESHOLD
        self.recovery_seconds = settings.CIRCUIT_BREAKER_RECOVERY_SECONDS

    def get_active_provider(self) -> str:
        """Determines active model based on circuit breaker state."""
        now = time.time()

        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time > self.recovery_seconds:
                logger.info("Circuit breaker entering HALF_OPEN state. Testing primary provider...")
                self.state = CircuitState.HALF_OPEN
                return self.primary_model
            return self.fallback_model

        return self.primary_model

    def record_success(self):
        """Resets failure counter and closes circuit."""
        if self.state in [CircuitState.OPEN, CircuitState.HALF_OPEN]:
            logger.info("Primary provider recovered successfully. Circuit CLOSED.")
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0

    def record_failure(self, error: Exception):
        """Records error and trips circuit breaker if threshold is exceeded."""
        self.consecutive_failures += 1
        self.last_failure_time = time.time()

        logger.warning(
            "Primary LLM provider failure recorded",
            failures=self.consecutive_failures,
            threshold=self.fail_threshold,
            error=str(error)
        )

        if self.consecutive_failures >= self.fail_threshold:
            self.state = CircuitState.OPEN
            logger.error(
                "CIRCUIT BREAKER TRIPPED! Routing all traffic to fallback provider",
                primary=self.primary_model,
                fallback=self.fallback_model,
                recovery_window=f"{self.recovery_seconds}s"
            )

llm_gateway = MultiModelGateway()
