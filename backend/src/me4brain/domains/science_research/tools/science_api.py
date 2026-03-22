"""Science & Research API Tools.

Wrapper async per le API accademiche:
- ArXiv: Preprint search
- Crossref: DOI lookup
- OpenAlex: Academic graph
- Europe PMC: Life sciences
- PubMed: Biomedical (richiede API key opzionale)

Tutte le API sono pubbliche (no auth richiesta).
"""

import re
from typing import Any
from urllib.parse import quote_plus

import httpx
import structlog

logger = structlog.get_logger(__name__)

TIMEOUT = 15.0
USER_AGENT = "Me4BrAIn/2.0 (AI Research Platform; mailto:contact@me4brain.ai)"


# =============================================================================
# ArXiv (No Auth)
# =============================================================================


async def arxiv_search(
    query: str,
    max_results: int = 10,
) -> dict[str, Any]:
    """Cerca paper su ArXiv.

    Args:
        query: Query di ricerca
        max_results: Numero risultati

    Returns:
        dict con risultati
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            response = await client.get(
                "https://export.arxiv.org/api/query",
                params={
                    "search_query": f"all:{query}",
                    "start": 0,
                    "max_results": max_results,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
            )
            response.raise_for_status()
            xml_content = response.text

            # Parse XML semplificato
            papers = []
            entries = re.findall(r"<entry>(.*?)</entry>", xml_content, re.DOTALL)

            for entry in entries[:max_results]:
                title = re.search(r"<title>(.*?)</title>", entry, re.DOTALL)
                summary = re.search(r"<summary>(.*?)</summary>", entry, re.DOTALL)
                arxiv_id = re.search(r"<id>http://arxiv.org/abs/(.*?)</id>", entry)
                published = re.search(r"<published>(.*?)</published>", entry)
                authors = re.findall(r"<name>(.*?)</name>", entry)

                papers.append(
                    {
                        "title": title.group(1).strip() if title else "Unknown",
                        "arxiv_id": arxiv_id.group(1) if arxiv_id else None,
                        "summary": (summary.group(1).strip()[:300] + "...") if summary else None,
                        "published": published.group(1) if published else None,
                        "authors": authors[:5],  # Max 5 autori
                        "url": f"https://arxiv.org/abs/{arxiv_id.group(1)}" if arxiv_id else None,
                    }
                )

            return {
                "papers": papers,
                "count": len(papers),
                "query": query,
                "source": "ArXiv",
            }

    except Exception as e:
        logger.error("arxiv_search_error", error=str(e))
        return {"error": str(e), "source": "ArXiv"}


# =============================================================================
# Crossref (No Auth)
# =============================================================================


async def crossref_doi(doi: str) -> dict[str, Any]:
    """Ottieni metadata da DOI via Crossref.

    Args:
        doi: DOI string (es. "10.1038/nature12373")

    Returns:
        dict con metadata
    """
    try:
        # Clean DOI
        doi = doi.strip().replace("https://doi.org/", "").replace("http://doi.org/", "")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"https://api.crossref.org/works/{quote_plus(doi)}",
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            work = data.get("message", {})
            authors = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in work.get("author", [])[:5]
            ]

            return {
                "doi": work.get("DOI"),
                "title": work.get("title", ["Unknown"])[0] if work.get("title") else "Unknown",
                "authors": authors,
                "type": work.get("type"),
                "published": work.get("published-print", {}).get("date-parts", [[]])[0],
                "journal": work.get("container-title", [""])[0]
                if work.get("container-title")
                else None,
                "url": work.get("URL"),
                "citation_count": work.get("is-referenced-by-count"),
                "source": "Crossref",
            }

    except Exception as e:
        logger.error("crossref_doi_error", error=str(e))
        return {"error": str(e), "source": "Crossref"}


async def crossref_search(query: str, max_results: int = 10) -> dict[str, Any]:
    """Cerca paper su Crossref.

    Args:
        query: Query di ricerca
        max_results: Numero risultati
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://api.crossref.org/works",
                params={"query": query, "rows": max_results},
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            items = data.get("message", {}).get("items", [])
            papers = []

            for item in items:
                authors = [
                    f"{a.get('given', '')} {a.get('family', '')}".strip()
                    for a in item.get("author", [])[:3]
                ]
                papers.append(
                    {
                        "doi": item.get("DOI"),
                        "title": item.get("title", ["Unknown"])[0]
                        if item.get("title")
                        else "Unknown",
                        "authors": authors,
                        "type": item.get("type"),
                        "year": item.get("published-print", {}).get("date-parts", [[None]])[0][0],
                    }
                )

            return {
                "papers": papers,
                "count": len(papers),
                "query": query,
                "source": "Crossref",
            }

    except Exception as e:
        logger.error("crossref_search_error", error=str(e))
        return {"error": str(e), "source": "Crossref"}


# =============================================================================
# OpenAlex (No Auth)
# =============================================================================


async def openalex_search(query: str, max_results: int = 10) -> dict[str, Any]:
    """Cerca paper su OpenAlex.

    Args:
        query: Query di ricerca
        max_results: Numero risultati
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://api.openalex.org/works",
                params={"search": query, "per_page": max_results},
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("results", [])
            papers = []

            for work in results:
                authors = [
                    a.get("author", {}).get("display_name", "Unknown")
                    for a in work.get("authorships", [])[:3]
                ]
                papers.append(
                    {
                        "id": work.get("id"),
                        "doi": work.get("doi"),
                        "title": work.get("title"),
                        "authors": authors,
                        "year": work.get("publication_year"),
                        "cited_by_count": work.get("cited_by_count"),
                        "open_access": work.get("open_access", {}).get("is_oa"),
                    }
                )

            return {
                "papers": papers,
                "count": len(papers),
                "query": query,
                "source": "OpenAlex",
            }

    except Exception as e:
        logger.error("openalex_search_error", error=str(e))
        return {"error": str(e), "source": "OpenAlex"}


# =============================================================================
# Europe PMC (No Auth)
# =============================================================================


async def europepmc_search(query: str, max_results: int = 10) -> dict[str, Any]:
    """Cerca paper su Europe PMC (life sciences).

    Args:
        query: Query di ricerca
        max_results: Numero risultati
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                params={
                    "query": query,
                    "resultType": "lite",
                    "pageSize": max_results,
                    "format": "json",
                },
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("resultList", {}).get("result", [])
            papers = []

            for item in results:
                papers.append(
                    {
                        "pmid": item.get("pmid"),
                        "title": item.get("title"),
                        "authors": item.get("authorString", "").split(", ")[:3],
                        "journal": item.get("journalTitle"),
                        "year": item.get("pubYear"),
                        "source": item.get("source"),
                    }
                )

            return {
                "papers": papers,
                "count": len(papers),
                "query": query,
                "source": "Europe PMC",
            }

    except Exception as e:
        logger.error("europepmc_search_error", error=str(e))
        return {"error": str(e), "source": "Europe PMC"}


# =============================================================================
# PubMed (NCBI E-utilities)
# =============================================================================


async def pubmed_search(query: str, max_results: int = 10) -> dict[str, Any]:
    """Cerca paper su PubMed.

    Args:
        query: Query di ricerca
        max_results: Numero risultati
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # First: search for IDs
            search_response = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={
                    "db": "pubmed",
                    "term": query,
                    "retmax": max_results,
                    "retmode": "json",
                },
            )
            search_response.raise_for_status()
            search_data = search_response.json()

            ids = search_data.get("esearchresult", {}).get("idlist", [])

            if not ids:
                return {"papers": [], "count": 0, "query": query, "source": "PubMed"}

            # Second: fetch summaries
            summary_response = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                params={
                    "db": "pubmed",
                    "id": ",".join(ids),
                    "retmode": "json",
                },
            )
            summary_response.raise_for_status()
            summary_data = summary_response.json()

            papers = []
            result = summary_data.get("result", {})
            for pmid in ids:
                if pmid in result:
                    item = result[pmid]
                    authors = [a.get("name", "") for a in item.get("authors", [])[:3]]
                    papers.append(
                        {
                            "pmid": pmid,
                            "title": item.get("title"),
                            "authors": authors,
                            "journal": item.get("source"),
                            "year": item.get("pubdate", "")[:4],
                            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        }
                    )

            return {
                "papers": papers,
                "count": len(papers),
                "query": query,
                "source": "PubMed",
            }

    except Exception as e:
        logger.error("pubmed_search_error", error=str(e))
        return {"error": str(e), "source": "PubMed"}


# =============================================================================
# Semantic Scholar (No Auth for basic usage)
# =============================================================================


async def semanticscholar_search(
    query: str,
    max_results: int = 10,
    year_min: int | None = None,
    year_max: int | None = None,
) -> dict[str, Any]:
    """Cerca paper su Semantic Scholar con filtri temporali e ordinamento.

    Args:
        query: Query di ricerca
        max_results: Numero risultati
        year_min: Anno minimo di pubblicazione (es. 2024)
        year_max: Anno massimo di pubblicazione (es. 2026)

    Returns:
        dict con risultati ordinati per citation count (decrescente)
    """
    import asyncio

    max_retries = 3

    for attempt in range(max_retries):
        try:
            # Throttle: 1 request per second to avoid rate limits
            if attempt > 0:
                wait_time = 2**attempt  # Exponential backoff: 2, 4, 8 seconds
                logger.info("semanticscholar_retry", attempt=attempt, wait_seconds=wait_time)
                await asyncio.sleep(wait_time)

            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params={
                        "query": query,
                        "limit": max_results,
                        "fields": "paperId,title,authors,year,citationCount,openAccessPdf,abstract",
                    },
                    headers={"User-Agent": USER_AGENT},
                )

                # Handle rate limit specifically
                if response.status_code == 429:
                    if attempt < max_retries - 1:
                        continue  # Retry with backoff
                    return {
                        "error": "Rate limit exceeded. Please try again later.",
                        "source": "Semantic Scholar",
                    }

                response.raise_for_status()
                data = response.json()

                papers = []
                for paper in data.get("data", []):
                    # Apply temporal filtering
                    year = paper.get("year")
                    if year_min and year and year < year_min:
                        continue
                    if year_max and year and year > year_max:
                        continue

                    authors = [a.get("name", "") for a in paper.get("authors", [])[:3]]
                    abstract = paper.get("abstract", "")
                    papers.append(
                        {
                            "paper_id": paper.get("paperId"),
                            "title": paper.get("title"),
                            "authors": authors,
                            "year": paper.get("year"),
                            "citation_count": paper.get("citationCount"),
                            "abstract": (abstract[:200] + "...")
                            if abstract and len(abstract) > 200
                            else abstract,
                            "open_access_pdf": paper.get("openAccessPdf", {}).get("url")
                            if paper.get("openAccessPdf")
                            else None,
                        }
                    )

                # Sort by citation count (descending) - PROBLEMA 6 FIX
                papers.sort(key=lambda p: p.get("citation_count", 0) or 0, reverse=True)

                logger.info(
                    "semanticscholar_search_complete",
                    query=query,
                    results_count=len(papers),
                    year_min=year_min,
                    year_max=year_max,
                )

                return {
                    "papers": papers,
                    "count": len(papers),
                    "query": query,
                    "source": "Semantic Scholar",
                    "filters": {
                        "year_min": year_min,
                        "year_max": year_max,
                    },
                }

        except Exception as e:
            if attempt < max_retries - 1:
                continue
            logger.error("semanticscholar_search_error", error=str(e))
            return {"error": str(e), "source": "Semantic Scholar"}


async def semanticscholar_paper(paper_id: str) -> dict[str, Any]:
    """Ottieni dettagli paper da Semantic Scholar.

    Args:
        paper_id: ID paper Semantic Scholar

    Returns:
        dict con dettagli paper
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}",
                params={
                    "fields": "paperId,title,authors,year,abstract,citationCount,referenceCount,venue,openAccessPdf,tldr",
                },
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            authors = [a.get("name", "") for a in data.get("authors", [])[:5]]
            tldr = data.get("tldr", {})

            return {
                "paper_id": data.get("paperId"),
                "title": data.get("title"),
                "authors": authors,
                "year": data.get("year"),
                "venue": data.get("venue"),
                "abstract": data.get("abstract"),
                "tldr": tldr.get("text") if tldr else None,
                "citation_count": data.get("citationCount"),
                "reference_count": data.get("referenceCount"),
                "open_access_pdf": data.get("openAccessPdf", {}).get("url")
                if data.get("openAccessPdf")
                else None,
                "source": "Semantic Scholar",
            }

    except Exception as e:
        logger.error("semanticscholar_paper_error", error=str(e))
        return {"error": str(e), "source": "Semantic Scholar"}


async def semanticscholar_citations(
    paper_id: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Ottieni citazioni di un paper.

    Args:
        paper_id: ID paper
        limit: Numero citazioni

    Returns:
        dict con citazioni
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations",
                params={
                    "fields": "paperId,title,year,citationCount",
                    "limit": limit,
                },
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            citations = []
            for item in data.get("data", []):
                citing_paper = item.get("citingPaper", {})
                citations.append(
                    {
                        "paper_id": citing_paper.get("paperId"),
                        "title": citing_paper.get("title"),
                        "year": citing_paper.get("year"),
                        "citation_count": citing_paper.get("citationCount"),
                    }
                )

            return {
                "paper_id": paper_id,
                "citations": citations,
                "count": len(citations),
                "source": "Semantic Scholar",
            }

    except Exception as e:
        logger.error("semanticscholar_citations_error", error=str(e))
        return {"error": str(e), "source": "Semantic Scholar"}


# =============================================================================
# Tool Registry
# =============================================================================

AVAILABLE_TOOLS = {
    # Letteratura accademica generale
    "arxiv_search": arxiv_search,
    "crossref_doi": crossref_doi,
    "crossref_search": crossref_search,
    "openalex_search": openalex_search,
    # Semantic Scholar
    "semanticscholar_search": semanticscholar_search,
    "semanticscholar_paper": semanticscholar_paper,
    "semanticscholar_citations": semanticscholar_citations,
    # NOTE: pubmed_search e europepmc_search sono in medical domain
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool science per nome, filtrando parametri non accettati."""
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {"error": f"Unknown science tool: {tool_name}"}

    tool_func = AVAILABLE_TOOLS[tool_name]
    sig = inspect.signature(tool_func)
    valid_params = set(sig.parameters.keys())
    filtered_args = {k: v for k, v in arguments.items() if k in valid_params}

    if len(filtered_args) < len(arguments):
        ignored = set(arguments.keys()) - valid_params
        logger.warning(
            "execute_tool_ignored_params",
            tool=tool_name,
            ignored=list(ignored),
            hint="LLM hallucinated parameters not in function signature",
        )

    return await tool_func(**filtered_args)


# =============================================================================
# Tool Engine Integration
# =============================================================================


def get_tool_definitions() -> list:
    """Generate ToolDefinition objects for all Science Research tools."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        # ArXiv
        ToolDefinition(
            name="arxiv_search",
            description="Search for scientific preprints on ArXiv (physics, math, CS, biology, etc.). Find cutting-edge research papers. Use when user asks 'research papers on X', 'ArXiv papers about Y', 'scientific preprints'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Research topic or keywords to search",
                    required=True,
                ),
                "max_results": ToolParameter(
                    type="integer",
                    description="Maximum papers to return (default 10)",
                    required=False,
                ),
            },
            domain="science",
            category="preprints",
        ),
        # Crossref
        ToolDefinition(
            name="crossref_doi",
            description="Get paper metadata by DOI from Crossref. Returns authors, title, journal, citations. Use when user has a DOI like '10.1038/...' and needs full paper details.",
            parameters={
                "doi": ToolParameter(
                    type="string",
                    description="DOI of the article (e.g., '10.1038/nature12373')",
                    required=True,
                ),
            },
            domain="science",
            category="papers",
        ),
        ToolDefinition(
            name="crossref_search",
            description="Search academic papers in Crossref database. Find peer-reviewed articles across all disciplines. Use when user asks 'find papers on X', 'academic research about Y'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Research topic or keywords to search",
                    required=True,
                ),
                "rows": ToolParameter(
                    type="integer",
                    description="Number of results to return",
                    required=False,
                ),
            },
            domain="science",
            category="papers",
        ),
        # OpenAlex
        ToolDefinition(
            name="openalex_search",
            description="Search OpenAlex academic graph for papers, authors, and institutions. AI-powered academic search. Use when user asks 'papers by author X', 'research from institution Y', 'open access papers'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Research topic, author name, or keywords",
                    required=True,
                ),
                "filter_type": ToolParameter(
                    type="string",
                    description="Filter type: 'works' (papers), 'authors', 'institutions'",
                    required=False,
                ),
            },
            domain="science",
            category="academic_graph",
        ),
        # Semantic Scholar
        ToolDefinition(
            name="semanticscholar_search",
            description="Search papers on Semantic Scholar with AI-powered relevance ranking. Find highly cited papers with abstracts, sorted by citation count. Supports temporal filtering. Use when user asks 'best papers on X', 'most cited research about Y', 'papers from last 2 years'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Research topic or keywords to search",
                    required=True,
                ),
                "limit": ToolParameter(
                    type="integer",
                    description="Maximum results to return",
                    required=False,
                ),
                "year_min": ToolParameter(
                    type="integer",
                    description="Minimum publication year (e.g., 2024 for 'last 2 years')",
                    required=False,
                ),
                "year_max": ToolParameter(
                    type="integer",
                    description="Maximum publication year (e.g., 2026)",
                    required=False,
                ),
            },
            domain="science",
            category="papers",
        ),
        ToolDefinition(
            name="semanticscholar_paper",
            description="Get complete paper details from Semantic Scholar by ID. Returns abstract, TLDR, citations, references. Use when user needs full details about a specific paper.",
            parameters={
                "paper_id": ToolParameter(
                    type="string",
                    description="Paper ID (Semantic Scholar ID, DOI, ArXiv ID, etc.)",
                    required=True,
                ),
            },
            domain="science",
            category="papers",
        ),
        ToolDefinition(
            name="semanticscholar_citations",
            description="Get papers that cite a specific article. Track research impact and related work. Use when user asks 'who cited this paper', 'research that builds on X'.",
            parameters={
                "paper_id": ToolParameter(
                    type="string",
                    description="Paper ID to find citations for",
                    required=True,
                ),
                "limit": ToolParameter(
                    type="integer",
                    description="Maximum citations to return",
                    required=False,
                ),
            },
            domain="science",
            category="papers",
        ),
    ]


def get_executors() -> dict:
    """Return mapping of tool names to executor functions."""
    return AVAILABLE_TOOLS
