"""Circuit Breaker Pattern Implementation.

Protegge da cascading failures chiudendo circuiti verso servizi non healthy.
"""

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Stati del circuit breaker."""

    CLOSED = "closed"  # Normale - richieste passano
    OPEN = "open"  # Fallito - richieste bloccate
    HALF_OPEN = "half_open"  # Test - alcune richieste passano


@dataclass
class CircuitBreakerConfig:
    """Configurazione circuit breaker."""

    failure_threshold: int = 5  # Fallimenti prima di aprire
    success_threshold: int = 2  # Successi per chiudere da half-open
    timeout_seconds: float = 30.0  # Tempo in OPEN prima di half-open
    half_open_max_calls: int = 3  # Max chiamate in half-open


@dataclass
class CircuitStats:
    """Statistiche del circuito."""

    failures: int = 0
    successes: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None
    total_calls: int = 0
    blocked_calls: int = 0


@dataclass
class CircuitBreaker:
    """Circuit Breaker per un servizio."""

    name: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    state: CircuitState = CircuitState.CLOSED
    stats: CircuitStats = field(default_factory=CircuitStats)
    _last_state_change: float = field(default_factory=time.time)
    _half_open_calls: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def call(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Esegue una chiamata attraverso il circuit breaker."""
        async with self._lock:
            if not self._can_execute():
                self.stats.blocked_calls += 1
                logger.warning(
                    "circuit_breaker_blocked",
                    service=self.name,
                    state=self.state.value,
                )
                raise CircuitOpenError(f"Circuit breaker '{self.name}' is {self.state.value}")

            if self.state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1

        self.stats.total_calls += 1

        try:
            # Esegui la chiamata
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await self._on_success()
            return result

        except Exception as e:
            await self._on_failure(e)
            raise

    def _can_execute(self) -> bool:
        """Verifica se la chiamata può essere eseguita."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Controlla se è tempo di passare a half-open
            if time.time() - self._last_state_change >= self.config.timeout_seconds:
                self._transition_to(CircuitState.HALF_OPEN)
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Limita chiamate in half-open
            return self._half_open_calls < self.config.half_open_max_calls

        return False

    async def _on_success(self) -> None:
        """Chiamato su successo."""
        async with self._lock:
            self.stats.successes += 1
            self.stats.consecutive_successes += 1
            self.stats.consecutive_failures = 0
            self.stats.last_success_time = time.time()

            if self.state == CircuitState.HALF_OPEN:
                if self.stats.consecutive_successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    async def _on_failure(self, error: Exception) -> None:
        """Chiamato su fallimento."""
        async with self._lock:
            self.stats.failures += 1
            self.stats.consecutive_failures += 1
            self.stats.consecutive_successes = 0
            self.stats.last_failure_time = time.time()

            logger.warning(
                "circuit_breaker_failure",
                service=self.name,
                error=str(error)[:100],
                consecutive_failures=self.stats.consecutive_failures,
            )

            if self.state == CircuitState.HALF_OPEN:
                # Qualsiasi fallimento in half-open riapre il circuito
                self._transition_to(CircuitState.OPEN)
            elif self.state == CircuitState.CLOSED:
                if self.stats.consecutive_failures >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transizione a nuovo stato."""
        old_state = self.state
        self.state = new_state
        self._last_state_change = time.time()

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self.stats.consecutive_successes = 0

        logger.info(
            "circuit_breaker_state_change",
            service=self.name,
            old_state=old_state.value,
            new_state=new_state.value,
        )

    def get_status(self) -> dict[str, Any]:
        """Ritorna status del circuito."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failures": self.stats.failures,
            "successes": self.stats.successes,
            "consecutive_failures": self.stats.consecutive_failures,
            "total_calls": self.stats.total_calls,
            "blocked_calls": self.stats.blocked_calls,
        }


class CircuitOpenError(Exception):
    """Eccezione quando il circuito è aperto."""

    pass


# =============================================================================
# Circuit Breaker Registry
# =============================================================================


class CircuitBreakerRegistry:
    """Registry globale dei circuit breaker."""

    _instance: "CircuitBreakerRegistry | None" = None
    _breakers: dict[str, CircuitBreaker]

    def __new__(cls) -> "CircuitBreakerRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._breakers = {}
        return cls._instance

    def get_or_create(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> CircuitBreaker:
        """Ottiene o crea un circuit breaker."""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                config=config or CircuitBreakerConfig(),
            )
        return self._breakers[name]

    def get_all_status(self) -> list[dict[str, Any]]:
        """Ritorna status di tutti i circuiti."""
        return [cb.get_status() for cb in self._breakers.values()]

    def reset(self, name: str) -> bool:
        """Reset manuale di un circuito."""
        if name in self._breakers:
            breaker = self._breakers[name]
            breaker.state = CircuitState.CLOSED
            breaker.stats = CircuitStats()
            logger.info("circuit_breaker_reset", service=name)
            return True
        return False


# Singleton instance
circuit_registry = CircuitBreakerRegistry()


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Ottiene un circuit breaker per nome."""
    return circuit_registry.get_or_create(name)
