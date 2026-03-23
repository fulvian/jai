"""Domain Router with Circuit Breaker and Timeout Protection.

Implementa il routing delle query ai domain handlers con:
- Timeout protection (5s default per dominio)
- Circuit breaker per fault isolation
- Fallback graceful degradation

Pattern: Circuit Breaker + Timeout + Retry
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import structlog

from me4brain.core.interfaces import DomainExecutionResult, DomainHandler
from me4brain.core.plugin_registry import PluginRegistry

logger = structlog.get_logger(__name__)


class CircuitState(str, Enum):
    """Stati del circuit breaker."""

    CLOSED = "closed"  # Normale operazione
    OPEN = "open"  # Blocca richieste (troppi fallimenti)
    HALF_OPEN = "half_open"  # Prova una richiesta


@dataclass
class CircuitBreakerStats:
    """Statistiche per circuit breaker di un dominio."""

    domain: str
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: datetime | None = None
    state: CircuitState = CircuitState.CLOSED

    # Configurazione
    failure_threshold: int = 3
    recovery_timeout_seconds: int = 30


@dataclass
class DomainRouterConfig:
    """Configurazione per il domain router."""

    # Timeout per esecuzione dominio
    default_timeout_seconds: float = 5.0

    # Circuit breaker settings
    failure_threshold: int = 3
    recovery_timeout_seconds: int = 30

    # Retry settings
    max_retries: int = 1
    retry_delay_seconds: float = 0.5

    # Fallback
    enable_fallback: bool = True


class DomainRouter:
    """Router query → domain handler con protezione.

    Funzionalità:
    - Route query al miglior handler (score-based)
    - Timeout protection per handler lenti
    - Circuit breaker per handler che falliscono ripetutamente
    - Fallback graceful quando tutti i handler falliscono

    Example:
        router = DomainRouter(registry)
        results = await router.route_and_execute(
            query="Prossima partita Lakers",
            analysis={"entities": ["Lakers", "NBA"]},
            context={}
        )
    """

    def __init__(
        self,
        registry: PluginRegistry,
        config: DomainRouterConfig | None = None,
    ) -> None:
        """Inizializza router.

        Args:
            registry: PluginRegistry per lookup handler
            config: Configurazione opzionale
        """
        self.registry = registry
        self.config = config or DomainRouterConfig()

        # Circuit breaker state per dominio
        self._circuit_stats: dict[str, CircuitBreakerStats] = defaultdict(
            lambda: CircuitBreakerStats(
                domain="unknown",
                failure_threshold=self.config.failure_threshold,
                recovery_timeout_seconds=self.config.recovery_timeout_seconds,
            )
        )

    async def route_and_execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
        timeout: float | None = None,
    ) -> list[DomainExecutionResult]:
        """Route query e esegue sul miglior handler.

        Args:
            query: Query utente
            analysis: Analisi query da LLM
            context: Contesto sessione
            timeout: Timeout override (default: config.default_timeout_seconds)

        Returns:
            Lista risultati esecuzione, vuota se nessun handler disponibile
        """
        timeout = timeout or self.config.default_timeout_seconds

        # 1. Trova miglior handler
        handler = await self.registry.route_query(query, analysis)
        if handler is None:
            logger.warning(
                "no_handler_found",
                query_preview=query[:50],
            )
            return []

        # 2. Check circuit breaker
        if not self._can_execute(handler.domain_name):
            logger.warning(
                "circuit_open",
                domain=handler.domain_name,
                query_preview=query[:50],
            )
            # Try fallback to other handlers
            if self.config.enable_fallback:
                return await self._fallback_execute(query, analysis, context, timeout)
            return [
                DomainExecutionResult(
                    success=False,
                    domain=handler.domain_name,
                    error="Circuit breaker open - domain temporarily unavailable",
                )
            ]

        # 3. Execute con timeout e retry
        return await self._execute_with_protection(handler, query, analysis, context, timeout)

    async def _execute_with_protection(
        self,
        handler: DomainHandler,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
        timeout: float,
    ) -> list[DomainExecutionResult]:
        """Esegue handler con timeout, retry, e circuit breaker tracking."""
        domain = handler.domain_name
        last_error: Exception | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                start_time = datetime.now(UTC)

                # Execute con timeout
                results = await asyncio.wait_for(
                    handler.execute(query, analysis, context),
                    timeout=timeout,
                )

                latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

                # Success: reset circuit breaker
                self._record_success(domain)

                logger.info(
                    "domain_execution_success",
                    domain=domain,
                    latency_ms=round(latency_ms, 2),
                    results_count=len(results),
                )

                return results

            except TimeoutError:
                last_error = TimeoutError(f"Domain {domain} timed out after {timeout}s")
                self._record_failure(domain, "timeout")
                logger.warning(
                    "domain_execution_timeout",
                    domain=domain,
                    timeout=timeout,
                    attempt=attempt + 1,
                )

            except Exception as e:
                last_error = e
                self._record_failure(domain, str(e))
                logger.error(
                    "domain_execution_error",
                    domain=domain,
                    error=str(e),
                    attempt=attempt + 1,
                )

            # Delay before retry
            if attempt < self.config.max_retries:
                await asyncio.sleep(self.config.retry_delay_seconds)

        # All attempts failed
        return [
            DomainExecutionResult(
                success=False,
                domain=domain,
                error=str(last_error) if last_error else "Unknown error",
            )
        ]

    async def _fallback_execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
        timeout: float,
    ) -> list[DomainExecutionResult]:
        """Fallback: prova altri handler disponibili."""
        all_handlers = self.registry.get_all_handlers()

        for handler in all_handlers:
            if not self._can_execute(handler.domain_name):
                continue

            # Check if handler can handle this query
            try:
                score = await asyncio.wait_for(
                    handler.can_handle(query, analysis),
                    timeout=0.5,
                )
                if score < 0.3:  # Lower threshold for fallback
                    continue

                results = await self._execute_with_protection(
                    handler, query, analysis, context, timeout
                )
                if results and any(r.success for r in results):
                    logger.info(
                        "fallback_success",
                        domain=handler.domain_name,
                    )
                    return results

            except Exception as e:
                logger.warning(
                    "fallback_handler_failed",
                    domain=handler.domain_name,
                    error=str(e),
                )

        logger.error("all_handlers_failed", query_preview=query[:50])
        return [
            DomainExecutionResult(
                success=False,
                domain="fallback",
                error="All domain handlers failed or unavailable",
            )
        ]

    def _can_execute(self, domain: str) -> bool:
        """Check se il dominio può eseguire (circuit breaker)."""
        stats = self._circuit_stats[domain]
        stats.domain = domain

        if stats.state == CircuitState.CLOSED:
            return True

        if stats.state == CircuitState.OPEN:
            # Check se è passato recovery timeout
            if stats.last_failure_time:
                recovery_time = stats.last_failure_time + timedelta(
                    seconds=stats.recovery_timeout_seconds
                )
                if datetime.now(UTC) >= recovery_time:
                    # Transition to half-open
                    stats.state = CircuitState.HALF_OPEN
                    logger.info(
                        "circuit_half_open",
                        domain=domain,
                    )
                    return True
            return False

        # HALF_OPEN: allow one request
        return True

    def _record_success(self, domain: str) -> None:
        """Registra successo e resetta circuit breaker se necessario."""
        stats = self._circuit_stats[domain]
        stats.success_count += 1

        if stats.state == CircuitState.HALF_OPEN:
            # Success in half-open: close circuit
            stats.state = CircuitState.CLOSED
            stats.failure_count = 0
            logger.info(
                "circuit_closed",
                domain=domain,
            )

    def _record_failure(self, domain: str, reason: str) -> None:
        """Registra failure e apre circuit se threshold raggiunto."""
        stats = self._circuit_stats[domain]
        stats.failure_count += 1
        stats.last_failure_time = datetime.now(UTC)

        if stats.state == CircuitState.HALF_OPEN:
            # Failure in half-open: reopen circuit
            stats.state = CircuitState.OPEN
            logger.warning(
                "circuit_reopened",
                domain=domain,
                reason=reason,
            )
        elif stats.failure_count >= stats.failure_threshold:
            # Threshold reached: open circuit
            stats.state = CircuitState.OPEN
            logger.warning(
                "circuit_opened",
                domain=domain,
                failure_count=stats.failure_count,
                reason=reason,
            )

    def get_circuit_stats(self, domain: str) -> CircuitBreakerStats:
        """Ottiene statistiche circuit breaker per un dominio."""
        return self._circuit_stats[domain]

    def reset_circuit(self, domain: str) -> None:
        """Reset manuale del circuit breaker per un dominio."""
        if domain in self._circuit_stats:
            self._circuit_stats[domain] = CircuitBreakerStats(
                domain=domain,
                failure_threshold=self.config.failure_threshold,
                recovery_timeout_seconds=self.config.recovery_timeout_seconds,
            )
            logger.info("circuit_reset", domain=domain)
