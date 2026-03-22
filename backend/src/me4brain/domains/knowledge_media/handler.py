"""Knowledge & Media Domain Handler."""

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


class KnowledgeMediaHandler(DomainHandler):
    """Domain handler per Knowledge e Media queries."""

    KNOWLEDGE_KEYWORDS = frozenset(
        {
            "wikipedia",
            "wiki",
            "enciclopedia",
            "libro",
            "book",
            "libri",
            "books",
            "hackernews",
            "hacker news",
            "hn",
            "tech news",
            "top stories",
            "stories",
            "openlibrary",
            "open library",
        }
    )

    @property
    def domain_name(self) -> str:
        return "knowledge_media"

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.STABLE

    @property
    def default_ttl_hours(self) -> int:
        return 24

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="wikipedia",
                description="Cerca su Wikipedia",
                keywords=["wikipedia", "wiki"],
                example_queries=["Cos'è la fotosintesi?", "Wikipedia Albert Einstein"],
            ),
            DomainCapability(
                name="hackernews",
                description="Top stories Hacker News",
                keywords=["hackernews", "hn", "tech news"],
                example_queries=["Tech news oggi", "Top HN"],
            ),
        ]

    async def initialize(self) -> None:
        logger.info("knowledge_media_handler_initialized")

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        query_lower = query.lower()
        matches = sum(1 for kw in self.KNOWLEDGE_KEYWORDS if kw in query_lower)
        return min(0.9, matches * 0.4) if matches else 0.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        from me4brain.domains.knowledge_media.tools import knowledge_api

        query_lower = query.lower()
        start_time = datetime.now(UTC)

        try:
            if "hackernews" in query_lower or "hacker news" in query_lower or "hn" in query_lower:
                data = await knowledge_api.hackernews_top()
                tool_name = "hackernews_top"
            elif "libro" in query_lower or "book" in query_lower:
                search_term = self._extract_topic(query)
                data = await knowledge_api.openlibrary_search(query=search_term)
                tool_name = "openlibrary_search"
            else:
                topic = self._extract_topic(query)
                data = await knowledge_api.wikipedia_summary(topic=topic)
                tool_name = "wikipedia_summary"

            return [
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name=tool_name,
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                    latency_ms=(datetime.now(UTC) - start_time).total_seconds() * 1000,
                )
            ]
        except Exception as e:
            return [
                DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name="knowledge",
                    error=str(e),
                )
            ]

    def _extract_topic(self, query: str) -> str:
        stopwords = ["cos'è", "cosa", "chi", "wikipedia", "wiki", "cerca", "libro", "libri"]
        words = query.lower().split()
        return " ".join(w for w in words if w not in stopwords and len(w) > 2)

    def handles_service(self, service_name: str) -> bool:
        return service_name in {"WikipediaService", "HackerNewsService", "OpenLibraryService"}

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from me4brain.domains.knowledge_media.tools import knowledge_api

        return await knowledge_api.execute_tool(tool_name, arguments)
