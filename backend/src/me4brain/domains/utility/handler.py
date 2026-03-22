"""Utility Domain Handler - General purpose tools."""

from datetime import UTC, datetime
from typing import Any
import structlog
from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
)

logger = structlog.get_logger(__name__)


class UtilityHandler(DomainHandler):
    """Domain handler per utility queries."""

    UTILITY_KEYWORDS = frozenset(
        {
            "ip",
            "indirizzo",
            "headers",
            "http",
            "test",
            "ping",
            "uuid",
            "random",
            "generare",
            "generate",
            # Proactive keywords
            "monitor",
            "agente",
            "agent",
            "avvisami",
            "alert",
            "notifica",
            "notify",
            "reminder",
            "ricordami",
            "controlla",
            "check",
            "automatico",
            "autonomous",
        }
    )

    @property
    def domain_name(self) -> str:
        return "utility"

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.REAL_TIME

    @property
    def default_ttl_hours(self) -> int:
        return 1

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="network_info",
                description="Info IP e network",
                keywords=["ip", "headers"],
                example_queries=["Qual è il mio IP?"],
            ),
        ]

    async def initialize(self) -> None:
        logger.info("utility_handler_initialized")

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        matches = sum(1 for kw in self.UTILITY_KEYWORDS if kw in query.lower())
        return min(0.8, matches * 0.3) if matches else 0.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        from me4brain.domains.utility.tools import utility_api

        start = datetime.now(UTC)
        try:
            data = await utility_api.get_ip()
            return [
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="get_ip",
                    data=data,
                    latency_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                )
            ]
        except Exception as e:
            return [
                DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name="utility",
                    error=str(e),
                )
            ]

    def handles_service(self, service_name: str) -> bool:
        return service_name == "HttpbinService"

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        from me4brain.domains.utility.tools import utility_api

        return await utility_api.execute_tool(tool_name, arguments)
