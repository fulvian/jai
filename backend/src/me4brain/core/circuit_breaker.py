"""Circuit Breaker Pattern - Prevenzione cascading failures.

Implementa il pattern Circuit Breaker per:
- Prevenire cascading failures quando un dominio è down
- Fail-fast senza timeout quando circuito aperto
- Auto-recovery dopo periodo di cooldown

Stati:
- CLOSED: Normale operazione, richieste passano
- OPEN: Troppe failures, richieste bloccate
- HALF_OPEN: Test recovery, una richiesta passa

Usage:
    breaker = CircuitBreaker(failure_threshold=3, reset_timeout=60)

    if breaker.is_open():
        return cached_response  # Fail fast

    try:
        result = await call_domain()
        breaker.record_success()
    except Exception:
        breaker.record_failure()
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CircuitState(Enum):
    """Stati del circuit breaker."""

    CLOSED = "CLOSED"  # Normale operazione
    OPEN = "OPEN"  # Bloccato per troppe failures
    HALF_OPEN = "HALF_OPEN"  # Test recovery


@dataclass
class CircuitBreaker:
    """Circuit breaker per singolo dominio.

    Attributes:
        failure_threshold: Numero di failures per aprire circuito
        reset_timeout: Secondi prima di tentare recovery
        domain: Nome dominio per logging
    """

    domain: str
    failure_threshold: int = 3
    reset_timeout: int = 60

    # Stato interno
    failures: int = field(default=0, init=False)
    last_failure_time: float = field(default=0.0, init=False)
    state: CircuitState = field(default=CircuitState.CLOSED, init=False)

    def record_failure(self) -> None:
        """Registra una failure e potenzialmente apre il circuito."""
        self.failures += 1
        self.last_failure_time = time.time()

        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                "circuit_breaker_opened",
                domain=self.domain,
                failures=self.failures,
                threshold=self.failure_threshold,
            )

    def record_success(self) -> None:
        """Registra un successo e resetta il circuito."""
        self.failures = 0
        self.state = CircuitState.CLOSED

        logger.debug(
            "circuit_breaker_success",
            domain=self.domain,
        )

    def is_open(self) -> bool:
        """Verifica se il circuito è aperto (bloccare richieste).

        Returns:
            True se dovrebbe fallire velocemente, False se può procedere
        """
        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self.last_failure_time

            if elapsed > self.reset_timeout:
                # Tenta recovery
                self.state = CircuitState.HALF_OPEN
                logger.info(
                    "circuit_breaker_half_open",
                    domain=self.domain,
                    elapsed_seconds=elapsed,
                )
                return False

            return True

        return False

    def get_status(self) -> dict[str, Any]:
        """Ritorna stato corrente per monitoring."""
        return {
            "domain": self.domain,
            "state": self.state.value,
            "failures": self.failures,
            "last_failure": self.last_failure_time,
            "threshold": self.failure_threshold,
            "reset_timeout": self.reset_timeout,
        }


class CircuitBreakerRegistry:
    """Registry globale per circuit breakers per dominio.

    Singleton che gestisce tutti i circuit breakers.
    """

    _instance: "CircuitBreakerRegistry | None" = None
    _breakers: dict[str, CircuitBreaker]

    def __new__(cls) -> "CircuitBreakerRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._breakers = {}
        return cls._instance

    def get_breaker(
        self,
        domain: str,
        failure_threshold: int = 3,
        reset_timeout: int = 60,
    ) -> CircuitBreaker:
        """Ottiene o crea circuit breaker per dominio."""
        if domain not in self._breakers:
            self._breakers[domain] = CircuitBreaker(
                domain=domain,
                failure_threshold=failure_threshold,
                reset_timeout=reset_timeout,
            )
        return self._breakers[domain]

    def reset_all(self) -> None:
        """Reset tutti i circuit breakers (per testing)."""
        for breaker in self._breakers.values():
            breaker.failures = 0
            breaker.state = CircuitState.CLOSED

    def get_all_status(self) -> list[dict[str, Any]]:
        """Stato di tutti i breakers per monitoring."""
        return [b.get_status() for b in self._breakers.values()]


# Singleton instance
def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Ottiene registry singleton."""
    return CircuitBreakerRegistry()


def get_circuit_breaker(domain: str) -> CircuitBreaker:
    """Shortcut per ottenere breaker per dominio."""
    return get_circuit_breaker_registry().get_breaker(domain)
