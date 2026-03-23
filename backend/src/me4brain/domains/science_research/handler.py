"""Science & Research Domain Handler.

Implementazione DomainHandler per ricerca accademica.
Gestisce query su paper, articoli scientifici, DOI.

Volatilità: STABLE (paper non cambiano frequentemente)
Memory-First: Consulta prima memoria per paper già letti
"""

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


class ScienceResearchHandler(DomainHandler):
    """Domain handler per Science e Research queries.

    Capabilities:
    - ArXiv: Preprint search
    - Crossref: DOI lookup
    - OpenAlex: Academic graph
    - PubMed: Biomedical articles
    - Semantic Scholar: Paper citations

    Example queries:
    - "Cerca paper su machine learning"
    - "Articoli recenti su CRISPR"
    - "DOI 10.1038/nature12373"
    """

    HANDLED_SERVICES = frozenset(
        {
            "ArXivService",
            "CrossrefService",
            "EuropePMCService",
            "OpenAlexService",
            "SemanticScholarService",
            "PubMedService",
        }
    )

    SCIENCE_KEYWORDS = frozenset(
        {
            # Research terms
            "paper",
            "papers",
            "articolo",
            "articoli",
            "studio",
            "studi",
            "ricerca",
            "research",
            "pubblicazione",
            "publication",
            "preprint",
            "journal",
            "rivista",
            "abstract",
            # Databases
            "arxiv",
            "pubmed",
            "crossref",
            "doi",
            "openalex",
            "semantic scholar",
            "europe pmc",
            # Fields
            "scienza",
            "science",
            "scientifico",
            "scientific",
            "accademico",
            "academic",
            "università",
            "university",
            "fisica",
            "physics",
            "matematica",
            "math",
            "chimica",
            "chemistry",
            "biologia",
            "biology",
            "medicina",
            "medicine",
            "medical",
            "machine learning",
            "deep learning",
            "ai",
            "neural network",
            "genomics",
            "genetics",
            "genetica",
            "crispr",
            "climate",
            "clima",
            "quantum",
            "quantistico",
        }
    )

    ARXIV_PATTERNS = ["arxiv", "preprint", "physics", "matematica", "cs", "machine learning"]
    PUBMED_PATTERNS = ["pubmed", "medicina", "medical", "biology", "biologia", "crispr", "genetics"]
    DOI_PATTERNS = ["doi", "10."]

    @property
    def domain_name(self) -> str:
        return "science_research"

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.STABLE

    @property
    def default_ttl_hours(self) -> int:
        return 168  # 1 settimana

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="arxiv_search",
                description="Cerca preprint su ArXiv (CS, Physics, Math)",
                keywords=["arxiv", "preprint", "paper"],
                example_queries=["Paper recenti su transformer", "ArXiv machine learning"],
            ),
            DomainCapability(
                name="pubmed_search",
                description="Cerca articoli biomedicali su PubMed",
                keywords=["pubmed", "medicina", "medical"],
                example_queries=["Studi su CRISPR", "Ricerca COVID-19"],
            ),
            DomainCapability(
                name="doi_lookup",
                description="Cerca informazioni da DOI",
                keywords=["doi", "crossref"],
                example_queries=["DOI 10.1038/nature12373"],
            ),
        ]

    async def initialize(self) -> None:
        logger.info("science_research_handler_initialized")

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        query_lower = query.lower()

        entities = analysis.get("entities", [])
        science_entities = sum(
            1 for e in entities if any(kw in str(e).lower() for kw in self.SCIENCE_KEYWORDS)
        )

        keyword_matches = sum(1 for kw in self.SCIENCE_KEYWORDS if kw in query_lower)
        total_matches = science_entities + keyword_matches

        if total_matches == 0:
            return 0.0
        elif total_matches == 1:
            return 0.5
        elif total_matches == 2:
            return 0.7
        elif total_matches <= 4:
            return 0.85
        else:
            return 1.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        query_lower = query.lower()
        start_time = datetime.now(UTC)
        results: list[DomainExecutionResult] = []

        logger.info("science_research_execute", query_preview=query[:50])

        target = self._detect_target(query_lower)

        try:
            if target == "doi":
                results = [await self._execute_doi(query, analysis)]
            elif target == "pubmed":
                results = [await self._execute_pubmed(query, analysis)]
            else:
                # Default: ArXiv + OpenAlex
                results = await self._execute_multi_search(query, analysis)

            # P1 FIX: Web search fallback for author-related queries
            # If no results from science APIs, try web search for interviews/talks/startups
            if not results or all(not r.success for r in results):
                if self._is_author_query(query_lower):
                    logger.info(
                        "science_research_web_fallback",
                        query_preview=query[:50],
                        reason="author_query_no_results",
                    )
                    web_results = await self._search_author_web(query, analysis)
                    if web_results:
                        results.extend(web_results)

        except Exception as e:
            logger.error("science_research_error", error=str(e))
            results = [
                DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name="science_search",
                    error=str(e),
                )
            ]

        latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
        for r in results:
            r.latency_ms = latency_ms

        return results

    def _detect_target(self, query: str) -> str | None:
        if "10." in query or "doi" in query:
            return "doi"
        for p in self.PUBMED_PATTERNS:
            if p in query:
                return "pubmed"
        for p in self.ARXIV_PATTERNS:
            if p in query:
                return "arxiv"
        return None

    async def _execute_multi_search(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Cerca su ArXiv e OpenAlex in parallelo."""
        import asyncio

        from me4brain.domains.science_research.tools import science_api

        search_term = self._extract_search_term(query)

        arxiv_task = science_api.arxiv_search(query=search_term)
        openalex_task = science_api.openalex_search(query=search_term)

        arxiv_result, openalex_result = await asyncio.gather(
            arxiv_task, openalex_task, return_exceptions=True
        )

        results = []
        if isinstance(arxiv_result, dict) and not arxiv_result.get("error"):
            results.append(
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="arxiv_search",
                    data=arxiv_result,
                )
            )
        if isinstance(openalex_result, dict) and not openalex_result.get("error"):
            results.append(
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="openalex_search",
                    data=openalex_result,
                )
            )

        return (
            results
            if results
            else [
                DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name="science_search",
                    error="No results from science APIs",
                )
            ]
        )

    async def _execute_doi(self, query: str, analysis: dict[str, Any]) -> DomainExecutionResult:
        import re

        from me4brain.domains.science_research.tools import science_api

        doi_match = re.search(r"10\.\d{4,}/[^\s]+", query)
        doi = doi_match.group(0) if doi_match else query

        data = await science_api.crossref_doi(doi=doi)
        return DomainExecutionResult(
            success=not data.get("error"),
            domain=self.domain_name,
            tool_name="crossref_doi",
            data=data if not data.get("error") else {},
            error=data.get("error"),
        )

    async def _execute_pubmed(self, query: str, analysis: dict[str, Any]) -> DomainExecutionResult:
        from me4brain.domains.science_research.tools import science_api

        search_term = self._extract_search_term(query)
        data = await science_api.pubmed_search(query=search_term)
        return DomainExecutionResult(
            success=not data.get("error"),
            domain=self.domain_name,
            tool_name="pubmed_search",
            data=data if not data.get("error") else {},
            error=data.get("error"),
        )

    def _extract_search_term(self, query: str) -> str:
        stopwords = [
            "cerca",
            "paper",
            "articoli",
            "su",
            "recenti",
            "studi",
            "ricerca",
            "pubblicazioni",
            "arxiv",
            "pubmed",
        ]
        words = query.lower().split()
        filtered = [w for w in words if w not in stopwords and len(w) > 2]
        return " ".join(filtered) if filtered else query

    def handles_service(self, service_name: str) -> bool:
        return service_name in self.HANDLED_SERVICES

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from me4brain.domains.science_research.tools import science_api

        return await science_api.execute_tool(tool_name, arguments)

    def _is_author_query(self, query: str) -> bool:
        """Detect if query is about authors/interviews/talks/startups.

        P1 FIX: Identify queries that need web search fallback.
        """
        keywords = [
            "autori",
            "interviste",
            "interview",
            "talk",
            "startup",
            "progetti",
            "open-source",
            "github",
            "progetto",
            "articoli divulgativi",
            "blog",
            "medium",
        ]
        return any(kw in query for kw in keywords)

    async def _search_author_web(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Use web_search domain for author-related queries.

        P1 FIX: Fallback to web search when science APIs don't have results
        for interviews, talks, startups, or open-source projects.
        """
        try:
            # Import web_search domain dynamically to avoid circular imports
            from me4brain.domains.web_search.tools import search_api

            # Build targeted search query
            search_query = self._build_author_search_query(query)

            logger.info(
                "science_research_web_search_fallback",
                original_query=query[:50],
                web_search_query=search_query[:50],
            )

            data = await search_api.duckduckgo_instant(query=search_query)

            if data and not data.get("error"):
                return [
                    DomainExecutionResult(
                        success=True,
                        domain=self.domain_name,
                        tool_name="web_search_fallback",
                        data=data,
                    )
                ]
            else:
                return [
                    DomainExecutionResult(
                        success=False,
                        domain=self.domain_name,
                        tool_name="web_search_fallback",
                        error=data.get("error", "No web results found"),
                    )
                ]

        except Exception as e:
            logger.error("science_research_web_search_error", error=str(e))
            return [
                DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name="web_search_fallback",
                    error=str(e),
                )
            ]

    def _build_author_search_query(self, query: str) -> str:
        """Build a targeted web search query from the original query.

        Extracts author names and keywords to create a focused search.
        """
        # Remove common stopwords
        stopwords = [
            "cerca",
            "trova",
            "ricerca",
            "paper",
            "articoli",
            "su",
            "recenti",
            "studi",
            "pubblicazioni",
            "interviste",
            "talk",
            "startup",
            "progetti",
            "open-source",
        ]

        words = query.lower().split()
        filtered = [w for w in words if w not in stopwords and len(w) > 2]

        # Build search query with relevant keywords
        query_lower = query.lower()
        if "intervista" in query_lower or "interviste" in query_lower or "interview" in query_lower:
            search_query = f"{' '.join(filtered)} interview"
        elif "talk" in query_lower:
            search_query = f"{' '.join(filtered)} talk conference"
        elif "startup" in query_lower or "progetto" in query_lower:
            search_query = f"{' '.join(filtered)} startup project"
        else:
            search_query = " ".join(filtered)

        return search_query if search_query.strip() else query
