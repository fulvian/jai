"""Web Search Domain - Tavily, DuckDuckGo, Wikipedia."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class SearchResult(BaseModel):
    """Web search result."""

    title: str
    url: str
    snippet: str
    score: float = 0.0


class WikipediaArticle(BaseModel):
    """Wikipedia article."""

    title: str
    summary: str
    url: str
    page_id: int | None = None
    categories: list[str] = Field(default_factory=list)


class WebSearchDomain(BaseDomain):
    """Web Search domain - Tavily, DuckDuckGo, Wikipedia.

    Example:
        # Tavily search
        results = await client.domains.web_search.tavily("AI news 2024")

        # Wikipedia lookup
        article = await client.domains.web_search.wikipedia("Artificial Intelligence")
    """

    @property
    def domain_name(self) -> str:
        return "web_search"

    async def tavily(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
    ) -> list[SearchResult]:
        """Search with Tavily API.

        Args:
            query: Search query
            max_results: Maximum results
            search_depth: "basic" or "advanced"

        Returns:
            List of search results
        """
        result = await self._execute_tool(
            "tavily_search",
            {"query": query, "max_results": max_results, "search_depth": search_depth},
        )
        results = result.get("result", {}).get("results", [])
        return [SearchResult.model_validate(r) for r in results]

    async def duckduckgo(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[SearchResult]:
        """Search with DuckDuckGo.

        Args:
            query: Search query
            max_results: Maximum results

        Returns:
            List of search results
        """
        result = await self._execute_tool(
            "duckduckgo_search",
            {"query": query, "max_results": max_results},
        )
        results = result.get("result", {}).get("results", [])
        return [SearchResult.model_validate(r) for r in results]

    async def wikipedia(
        self,
        query: str,
        sentences: int = 5,
    ) -> WikipediaArticle:
        """Get Wikipedia article.

        Args:
            query: Article title or search term
            sentences: Summary sentences

        Returns:
            Wikipedia article with summary
        """
        result = await self._execute_tool(
            "wikipedia_search",
            {"query": query, "sentences": sentences},
        )
        return WikipediaArticle.model_validate(result.get("result", {}))

    async def news(
        self,
        query: str,
        max_results: int = 10,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Search news articles.

        Args:
            query: News search query
            max_results: Maximum results
            language: Language code

        Returns:
            List of news articles
        """
        result = await self._execute_tool(
            "news_search",
            {"query": query, "max_results": max_results, "language": language},
        )
        return result.get("result", {}).get("articles", [])
