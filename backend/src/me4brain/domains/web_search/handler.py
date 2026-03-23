"""Web Search Domain Handler - DuckDuckGo and web search."""

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


class WebSearchHandler(DomainHandler):
    """Domain handler per web search queries."""

    SEARCH_KEYWORDS = frozenset(
        {
            "cerca",
            "search",
            "google",
            "duckduckgo",
            "ddg",
            "trova",
            "find",
            "web",
            "internet",
            "online",
        }
    )

    @property
    def domain_name(self) -> str:
        return "web_search"

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
                name="smart_search",
                description="Ricerca intelligente (Brave/Tavily/DDG) per news, ricerca o fatti",
                keywords=["cerca", "search", "trova", "web", "online"],
                example_queries=["Cerca le ultime news AI 2026", "Perché Python è lento?"],
            ),
            DomainCapability(
                name="brave_search",
                description="Cerca sul web con Brave Search (ottimo per news)",
                keywords=["brave", "news", "recente"],
                example_queries=["Brave news tech", "Brave search site:github.com python"],
            ),
            DomainCapability(
                name="tavily_search",
                description="Cerca sul web con Tavily (ottimo per ricerca profonda)",
                keywords=["tavily", "ricerca", "perché", "come"],
                example_queries=[
                    "Tavily spiega il quantum computing",
                    "Tavily ricerca mercati energetici",
                ],
            ),
        ]

    async def initialize(self) -> None:
        logger.info("web_search_handler_initialized")

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        matches = sum(1 for kw in self.SEARCH_KEYWORDS if kw in query.lower())
        return min(0.7, matches * 0.25) if matches else 0.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        from me4brain.domains.web_search.tools import search_api

        start = datetime.now(UTC)
        try:
            # Usa la logica intelligente a 3 livelli
            data = await search_api.smart_search(query=query)
            tool_used = data.get("source", "smart_search").lower().replace(" ", "_")

            return [
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name=tool_used,
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                    latency_ms=(datetime.now(UTC) - start).total_seconds() * 1000,
                )
            ]
        except Exception as e:
            return [
                DomainExecutionResult(
                    success=False, domain=self.domain_name, tool_name="smart_search", error=str(e)
                )
            ]

    def handles_service(self, service_name: str) -> bool:
        return service_name == "DuckDuckGoService"

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from me4brain.domains.web_search.tools import search_api

        return await search_api.execute_tool(tool_name, arguments)
