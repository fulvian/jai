"""Knowledge/Media Domain - Wikipedia, News, Encyclopedia."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class WikipediaArticle(BaseModel):
    """Wikipedia article."""

    title: str
    summary: str
    url: str
    page_id: int | None = None
    categories: list[str] = Field(default_factory=list)
    language: str = "en"


class NewsArticle(BaseModel):
    """News article."""

    title: str
    description: str | None = None
    url: str
    source: str | None = None
    published_at: str | None = None
    image_url: str | None = None


class KnowledgeMediaDomain(BaseDomain):
    """Knowledge/Media domain - Wikipedia, News, Encyclopedia.

    Example:
        # Wikipedia article
        article = await client.domains.knowledge_media.wikipedia("Python programming")

        # Search news
        news = await client.domains.knowledge_media.news_search("AI technology")
    """

    @property
    def domain_name(self) -> str:
        return "knowledge_media"

    async def wikipedia(
        self,
        query: str,
        language: str = "en",
        sentences: int = 5,
    ) -> WikipediaArticle:
        """Get Wikipedia article summary.

        Args:
            query: Article title or search term
            language: Language code
            sentences: Number of summary sentences

        Returns:
            Wikipedia article with summary
        """
        result = await self._execute_tool(
            "wikipedia_summary",
            {"query": query, "language": language, "sentences": sentences},
        )
        return WikipediaArticle.model_validate(result.get("result", {}))

    async def wikipedia_search(
        self,
        query: str,
        language: str = "en",
        max_results: int = 10,
    ) -> list[str]:
        """Search Wikipedia article titles.

        Args:
            query: Search query
            language: Language code
            max_results: Maximum results

        Returns:
            List of matching article titles
        """
        result = await self._execute_tool(
            "wikipedia_search",
            {"query": query, "language": language, "max_results": max_results},
        )
        return result.get("result", {}).get("titles", [])

    async def news_search(
        self,
        query: str,
        language: str = "en",
        max_results: int = 10,
    ) -> list[NewsArticle]:
        """Search news articles.

        Args:
            query: News search query
            language: Language code
            max_results: Maximum results

        Returns:
            List of news articles
        """
        result = await self._execute_tool(
            "news_search",
            {"query": query, "language": language, "max_results": max_results},
        )
        articles = result.get("result", {}).get("articles", [])
        return [NewsArticle.model_validate(a) for a in articles]

    async def news_top_headlines(
        self,
        country: str = "us",
        category: str | None = None,
        max_results: int = 10,
    ) -> list[NewsArticle]:
        """Get top news headlines.

        Args:
            country: Country code
            category: News category (business, entertainment, health, etc.)
            max_results: Maximum results

        Returns:
            List of top headlines
        """
        params: dict[str, Any] = {"country": country, "max_results": max_results}
        if category:
            params["category"] = category
        result = await self._execute_tool("news_headlines", params)
        articles = result.get("result", {}).get("articles", [])
        return [NewsArticle.model_validate(a) for a in articles]
