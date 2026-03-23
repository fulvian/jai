"""Health Checker - Component health checks per Me4BrAIn."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import structlog

from me4brain.core.monitoring.types import ComponentHealth, HealthReport, HealthStatus

logger = structlog.get_logger(__name__)


class HealthChecker:
    """
    Health checker per componenti Me4BrAIn.

    Componenti monitorati:
    - Redis (Working Memory)
    - Qdrant (Episodic/Procedural Memory)
    - Neo4j (Semantic Memory)
    - LLM API (NanoGPT)
    """

    def __init__(self, timeout_seconds: float = 5.0):
        """
        Inizializza checker.

        Args:
            timeout_seconds: Timeout per ogni check
        """
        self.timeout = timeout_seconds
        self._checks: dict[str, Callable] = {}
        self._last_report: HealthReport | None = None
        self._register_default_checks()

    def _register_default_checks(self) -> None:
        """Registra check di default."""
        self.register("redis", self._check_redis)
        self.register("qdrant", self._check_qdrant)
        self.register("neo4j", self._check_neo4j)
        # LLM check è opzionale (può essere costoso)

    def register(self, name: str, check_fn: Callable) -> None:
        """
        Registra nuovo check.

        Args:
            name: Nome componente
            check_fn: Funzione async che ritorna ComponentHealth
        """
        self._checks[name] = check_fn
        logger.debug("health_check_registered", component=name)

    async def check_component(self, name: str) -> ComponentHealth:
        """
        Esegue check singolo componente.

        Args:
            name: Nome componente

        Returns:
            Stato salute componente
        """
        check_fn = self._checks.get(name)
        if not check_fn:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNKNOWN,
                message="Check not registered",
            )

        start = time.time()
        try:
            result = await asyncio.wait_for(
                check_fn(),
                timeout=self.timeout,
            )
            result.latency_ms = (time.time() - start) * 1000
            return result

        except TimeoutError:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check timed out after {self.timeout}s",
                latency_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=(time.time() - start) * 1000,
            )

    async def check_all(self) -> HealthReport:
        """
        Esegue tutti i check.

        Returns:
            Report aggregato
        """
        tasks = [self.check_component(name) for name in self._checks]
        components = await asyncio.gather(*tasks)
        report = HealthReport.from_components(list(components))
        self._last_report = report

        logger.info(
            "health_check_complete",
            status=report.status.value,
            components={c.name: c.status.value for c in components},
        )

        return report

    async def is_healthy(self) -> bool:
        """Check rapido se sistema healthy."""
        report = await self.check_all()
        return report.status == HealthStatus.HEALTHY

    async def is_ready(self) -> bool:
        """
        Readiness probe.

        Il sistema è ready se almeno Redis è up.
        """
        redis_health = await self.check_component("redis")
        return redis_health.status == HealthStatus.HEALTHY

    # --- Default Checks ---

    async def _check_redis(self) -> ComponentHealth:
        """Check Redis connectivity."""
        try:
            from redis.asyncio import Redis

            redis = Redis.from_url("redis://localhost:6379", socket_timeout=2)
            await redis.ping()
            await redis.aclose()

            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Connected",
            )

        except Exception as e:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )

    async def _check_qdrant(self) -> ComponentHealth:
        """Check Qdrant connectivity."""
        try:
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    "http://localhost:6333/collections",
                    timeout=aiohttp.ClientTimeout(total=2),
                ) as resp,
            ):
                if resp.status == 200:
                    return ComponentHealth(
                        name="qdrant",
                        status=HealthStatus.HEALTHY,
                        message="Connected",
                    )
                return ComponentHealth(
                    name="qdrant",
                    status=HealthStatus.DEGRADED,
                    message=f"Status {resp.status}",
                )

        except Exception as e:
            return ComponentHealth(
                name="qdrant",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )

    async def _check_neo4j(self) -> ComponentHealth:
        """Check Neo4j connectivity using configured settings."""
        try:
            from neo4j import AsyncGraphDatabase

            from me4brain.config import get_settings

            settings = get_settings()
            driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(
                    settings.neo4j_user,
                    settings.neo4j_password.get_secret_value(),
                ),
                connection_timeout=5,
                max_connection_pool_size=1,
            )

            async with driver.session() as session:
                result = await session.run("RETURN 1 as n, size(labels(n)) as check")
                record = await result.single()
                await result.consume()

            await driver.close()

            return ComponentHealth(
                name="neo4j",
                status=HealthStatus.HEALTHY,
                message="Connected",
            )

        except Exception as e:
            return ComponentHealth(
                name="neo4j",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )

    async def _check_llm(self) -> ComponentHealth:
        """Check LLM API (opzionale, costoso)."""
        try:
            import aiohttp

            # Check NanoGPT health
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    "https://nano-gpt.com/api/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp,
            ):
                if resp.status == 200:
                    return ComponentHealth(
                        name="llm",
                        status=HealthStatus.HEALTHY,
                        message="API reachable",
                    )
                return ComponentHealth(
                    name="llm",
                    status=HealthStatus.DEGRADED,
                    message=f"Status {resp.status}",
                )

        except Exception as e:
            return ComponentHealth(
                name="llm",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )


# Singleton
_health_checker: HealthChecker | None = None


def get_health_checker() -> HealthChecker:
    """Ottiene checker globale."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
