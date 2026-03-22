"""Science/Research Domain - arXiv, Semantic Scholar, Academic search."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class ArxivPaper(BaseModel):
    """arXiv paper."""

    arxiv_id: str
    title: str
    summary: str
    authors: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    published: str | None = None
    pdf_url: str | None = None


class SemanticScholarPaper(BaseModel):
    """Semantic Scholar paper."""

    paper_id: str
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    citation_count: int = 0
    url: str | None = None


class ScienceResearchDomain(BaseDomain):
    """Science/Research domain - arXiv, Semantic Scholar, academic search.

    Example:
        # Search arXiv
        papers = await client.domains.science_research.arxiv("transformer attention")

        # Semantic Scholar
        papers = await client.domains.science_research.semantic_scholar("BERT")
    """

    @property
    def domain_name(self) -> str:
        return "science_research"

    async def arxiv(
        self,
        query: str,
        max_results: int = 10,
        sort_by: str = "relevance",
    ) -> list[ArxivPaper]:
        """Search arXiv papers.

        Args:
            query: Search query
            max_results: Maximum results
            sort_by: "relevance", "lastUpdatedDate", "submittedDate"

        Returns:
            List of papers
        """
        result = await self._execute_tool(
            "arxiv_search",
            {"query": query, "max_results": max_results, "sort_by": sort_by},
        )
        papers = result.get("result", {}).get("papers", [])
        return [ArxivPaper.model_validate(p) for p in papers]

    async def semantic_scholar(
        self,
        query: str,
        max_results: int = 10,
        year: int | None = None,
    ) -> list[SemanticScholarPaper]:
        """Search Semantic Scholar.

        Args:
            query: Search query
            max_results: Maximum results
            year: Filter by year

        Returns:
            List of papers
        """
        params: dict[str, Any] = {"query": query, "max_results": max_results}
        if year:
            params["year"] = year

        result = await self._execute_tool("semantic_scholar_search", params)
        papers = result.get("result", {}).get("papers", [])
        return [SemanticScholarPaper.model_validate(p) for p in papers]

    async def paper_citations(
        self,
        paper_id: str,
        max_results: int = 20,
    ) -> list[SemanticScholarPaper]:
        """Get paper citations.

        Args:
            paper_id: Paper ID (Semantic Scholar or DOI)
            max_results: Maximum results

        Returns:
            List of citing papers
        """
        result = await self._execute_tool(
            "paper_citations",
            {"paper_id": paper_id, "max_results": max_results},
        )
        papers = result.get("result", {}).get("citations", [])
        return [SemanticScholarPaper.model_validate(p) for p in papers]

    async def paper_references(
        self,
        paper_id: str,
        max_results: int = 20,
    ) -> list[SemanticScholarPaper]:
        """Get paper references.

        Args:
            paper_id: Paper ID
            max_results: Maximum results

        Returns:
            List of referenced papers
        """
        result = await self._execute_tool(
            "paper_references",
            {"paper_id": paper_id, "max_results": max_results},
        )
        papers = result.get("result", {}).get("references", [])
        return [SemanticScholarPaper.model_validate(p) for p in papers]
