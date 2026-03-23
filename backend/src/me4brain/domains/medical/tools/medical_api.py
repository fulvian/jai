"""Medical API Tools.

Wrapper async per le API mediche:
- RxNorm: Info farmaci NIH
- iCite: Metriche citazioni NIH

Tutte le API sono pubbliche (no auth richiesta).
"""

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

TIMEOUT = 15.0
USER_AGENT = "Me4BrAIn/2.0 (AI Research Platform)"


# =============================================================================
# RxNorm (NIH - No Auth)
# =============================================================================


async def rxnorm_drug_info(drug_name: str) -> dict[str, Any]:
    """Ottieni info farmaco da RxNorm.

    Args:
        drug_name: Nome farmaco (es. "aspirin", "metformin")

    Returns:
        dict con info farmaco
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Search for drug
            response = await client.get(
                "https://rxnav.nlm.nih.gov/REST/drugs.json",
                params={"name": drug_name},
            )
            response.raise_for_status()
            data = response.json()

            drug_group = data.get("drugGroup", {})
            concept_group = drug_group.get("conceptGroup", [])

            drugs = []
            for group in concept_group:
                for prop in group.get("conceptProperties", []):
                    drugs.append(
                        {
                            "rxcui": prop.get("rxcui"),
                            "name": prop.get("name"),
                            "tty": prop.get("tty"),  # Term type
                        }
                    )

            return {
                "query": drug_name,
                "drugs": drugs[:10],
                "count": len(drugs),
                "source": "RxNorm",
            }

    except Exception as e:
        logger.error("rxnorm_drug_info_error", error=str(e))
        return {"error": str(e), "source": "RxNorm"}


async def rxnorm_interactions(drug_name_or_rxcui: str) -> dict[str, Any]:
    """Ottieni interazioni farmaco da RxNorm.

    Args:
        drug_name_or_rxcui: Nome farmaco (es. "ibuprofen") o RxNorm Concept ID numerico

    Returns:
        dict con interazioni
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Check if input is RXCUI (numeric) or drug name
            if drug_name_or_rxcui.isdigit():
                rxcui = drug_name_or_rxcui
            else:
                # Lookup RXCUI from drug name
                lookup_response = await client.get(
                    "https://rxnav.nlm.nih.gov/REST/rxcui.json",
                    params={"name": drug_name_or_rxcui},
                )
                lookup_response.raise_for_status()
                lookup_data = lookup_response.json()

                rxcui_list = lookup_data.get("idGroup", {}).get("rxnormId", [])
                if not rxcui_list:
                    return {
                        "error": f"Drug not found: {drug_name_or_rxcui}",
                        "hint": "Try a different spelling or use RXCUI directly",
                        "source": "RxNorm",
                    }
                rxcui = rxcui_list[0]

            response = await client.get(
                "https://rxnav.nlm.nih.gov/REST/interaction/interaction.json",
                params={"rxcui": rxcui},
            )
            response.raise_for_status()
            data = response.json()

            interaction_pairs = data.get("interactionTypeGroup", [])
            interactions = []

            for group in interaction_pairs:
                for itype in group.get("interactionType", []):
                    for pair in itype.get("interactionPair", []):
                        interactions.append(
                            {
                                "description": pair.get("description"),
                                "severity": pair.get("severity"),
                                "drugs": [
                                    c.get("minConceptItem", {}).get("name")
                                    for c in pair.get("interactionConcept", [])
                                ],
                            }
                        )

            return {
                "drug": drug_name_or_rxcui,
                "rxcui": rxcui,
                "interactions": interactions[:20],
                "count": len(interactions),
                "source": "RxNorm",
            }

    except Exception as e:
        logger.error("rxnorm_interactions_error", error=str(e))
        return {"error": str(e), "source": "RxNorm"}


async def rxnorm_spelling(drug_name: str) -> dict[str, Any]:
    """Suggerimento spelling per farmaco.

    Args:
        drug_name: Nome farmaco (potenzialmente con typo)

    Returns:
        dict con suggerimenti
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://rxnav.nlm.nih.gov/REST/spellingsuggestions.json",
                params={"name": drug_name},
            )
            response.raise_for_status()
            data = response.json()

            suggestions = (
                data.get("suggestionGroup", {}).get("suggestionList", {}).get("suggestion", [])
            )

            return {
                "query": drug_name,
                "suggestions": suggestions[:10],
                "count": len(suggestions),
                "source": "RxNorm",
            }

    except Exception as e:
        logger.error("rxnorm_spelling_error", error=str(e))
        return {"error": str(e), "source": "RxNorm"}


# =============================================================================
# iCite (NIH - No Auth)
# =============================================================================


async def icite_metrics(pmid: str) -> dict[str, Any]:
    """Ottieni metriche citazioni da iCite.

    Args:
        pmid: PubMed ID

    Returns:
        dict con metriche
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://icite.od.nih.gov/api/pubs",
                params={"pmids": pmid},
            )
            response.raise_for_status()
            data = response.json()

            pubs = data.get("data", [])
            if pubs:
                pub = pubs[0]
                return {
                    "pmid": pub.get("pmid"),
                    "title": pub.get("title"),
                    "year": pub.get("year"),
                    "citation_count": pub.get("citation_count"),
                    "relative_citation_ratio": pub.get("relative_citation_ratio"),
                    "field_citation_rate": pub.get("field_citation_rate"),
                    "expected_citations_per_year": pub.get("expected_citations_per_year"),
                    "is_clinical": pub.get("is_clinical"),
                    "nih_percentile": pub.get("nih_percentile"),
                    "source": "iCite",
                }
            else:
                return {
                    "error": f"PMID not found: {pmid}",
                    "source": "iCite",
                }

    except Exception as e:
        logger.error("icite_metrics_error", error=str(e))
        return {"error": str(e), "source": "iCite"}


async def icite_batch(pmids: str) -> dict[str, Any]:
    """Ottieni metriche per multipli PMID.

    Args:
        pmids: PMIDs separati da virgola (es. "12345,67890")

    Returns:
        dict con metriche per ogni PMID
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://icite.od.nih.gov/api/pubs",
                params={"pmids": pmids},
            )
            response.raise_for_status()
            data = response.json()

            pubs = data.get("data", [])
            metrics = [
                {
                    "pmid": pub.get("pmid"),
                    "title": pub.get("title"),
                    "citation_count": pub.get("citation_count"),
                    "relative_citation_ratio": pub.get("relative_citation_ratio"),
                }
                for pub in pubs
            ]

            return {
                "publications": metrics,
                "count": len(metrics),
                "source": "iCite",
            }

    except Exception as e:
        logger.error("icite_batch_error", error=str(e))
        return {"error": str(e), "source": "iCite"}


# =============================================================================
# PubMed (NCBI E-utilities - Biomedical)
# =============================================================================


async def pubmed_search(query: str, max_results: int = 10) -> dict[str, Any]:
    """Cerca paper biomedici su PubMed.

    Args:
        query: Query di ricerca
        max_results: Numero risultati

    Returns:
        dict con paper biomedici
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


async def pubmed_abstract(pmid: str) -> dict[str, Any]:
    """Ottieni abstract completo da PubMed.

    Args:
        pmid: PubMed ID

    Returns:
        dict con abstract
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                params={
                    "db": "pubmed",
                    "id": pmid,
                    "rettype": "abstract",
                    "retmode": "text",
                },
            )
            response.raise_for_status()

            return {
                "pmid": pmid,
                "abstract": response.text.strip(),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "source": "PubMed",
            }

    except Exception as e:
        logger.error("pubmed_abstract_error", error=str(e))
        return {"error": str(e), "source": "PubMed"}


# =============================================================================
# Europe PMC (Life Sciences)
# =============================================================================


async def europepmc_search(query: str, max_results: int = 10) -> dict[str, Any]:
    """Cerca paper life sciences su Europe PMC.

    Args:
        query: Query di ricerca
        max_results: Numero risultati

    Returns:
        dict con paper life sciences
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
# ClinicalTrials.gov (NIH - No Auth)
# =============================================================================


async def clinicaltrials_search(
    condition: str,
    status: str = "RECRUITING",
    max_results: int = 10,
) -> dict[str, Any]:
    """Cerca trial clinici da ClinicalTrials.gov API v2.

    Args:
        condition: Condizione/malattia da cercare (es. "Alzheimer", "diabetes")
        status: Stato trial (RECRUITING, COMPLETED, etc.)
        max_results: Numero massimo risultati

    Returns:
        dict con lista trial clinici
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # ClinicalTrials.gov API v2
            response = await client.get(
                "https://clinicaltrials.gov/api/v2/studies",
                params={
                    "query.cond": condition,
                    "filter.overallStatus": status,
                    "pageSize": min(max_results, 50),
                    "fields": "NCTId,BriefTitle,OverallStatus,Phase,EnrollmentCount,StartDate,Condition,InterventionName,LeadSponsorName",
                },
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            studies = data.get("studies", [])
            trials = []

            for study in studies:
                protocol = study.get("protocolSection", {})
                identification = protocol.get("identificationModule", {})
                status_module = protocol.get("statusModule", {})
                design = protocol.get("designModule", {})
                description = protocol.get("descriptionModule", {})
                sponsor = protocol.get("sponsorCollaboratorsModule", {})

                # Estrai interventi
                arms = protocol.get("armsInterventionsModule", {})
                interventions = [i.get("name", "") for i in arms.get("interventions", [])]

                trials.append(
                    {
                        "nct_id": identification.get("nctId"),
                        "title": identification.get("briefTitle"),
                        "status": status_module.get("overallStatus"),
                        "phase": design.get("phases", []),
                        "enrollment": design.get("enrollmentInfo", {}).get("count"),
                        "start_date": status_module.get("startDateStruct", {}).get("date"),
                        "conditions": protocol.get("conditionsModule", {}).get("conditions", []),
                        "interventions": interventions[:3],  # Max 3
                        "sponsor": sponsor.get("leadSponsor", {}).get("name"),
                    }
                )

            return {
                "query": condition,
                "status_filter": status,
                "trials": trials,
                "count": len(trials),
                "total_found": data.get("totalCount", len(trials)),
                "source": "ClinicalTrials.gov",
            }

    except Exception as e:
        logger.error("clinicaltrials_search_error", error=str(e))
        return {"error": str(e), "source": "ClinicalTrials.gov"}


# =============================================================================
# Tool Registry
# =============================================================================

AVAILABLE_TOOLS = {
    # RxNorm
    "rxnorm_drug_info": rxnorm_drug_info,
    "rxnorm_interactions": rxnorm_interactions,
    "rxnorm_spelling": rxnorm_spelling,
    # iCite
    "icite_metrics": icite_metrics,
    "icite_batch": icite_batch,
    # PubMed (Biomedical)
    "pubmed_search": pubmed_search,
    "pubmed_abstract": pubmed_abstract,
    # Europe PMC (Life Sciences)
    "europepmc_search": europepmc_search,
    # ClinicalTrials.gov
    "clinicaltrials_search": clinicaltrials_search,
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool medical per nome.

    Filtra automaticamente parametri non accettati dalla funzione.
    """
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {
            "error": f"Unknown medical tool: {tool_name}",
            "available": list(AVAILABLE_TOOLS.keys()),
        }

    tool_func = AVAILABLE_TOOLS[tool_name]

    # Filter arguments to only those the function accepts
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
    """Generate ToolDefinition objects for all Medical tools."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        # RxNorm
        ToolDefinition(
            name="rxnorm_drug_info",
            description="Look up drug information from the NIH RxNorm database. Returns drug names, classifications, RXCUI codes, and formulations. Use when user asks about a medication, drug, prescription, or medicine by name (e.g., 'what is aspirin', 'info about metformin').",
            parameters={
                "drug_name": ToolParameter(
                    type="string",
                    description="Drug/medication name (e.g., 'aspirin', 'lisinopril', 'metformin')",
                    required=True,
                ),
            },
            domain="medical",
            category="drugs",
        ),
        ToolDefinition(
            name="rxnorm_interactions",
            description="Check for drug interactions and contraindications using RxNorm. Returns potential interactions with severity levels. Use when user asks 'can I take X with Y', 'drug interactions', or 'is it safe to combine medications'.",
            parameters={
                "drug_name_or_rxcui": ToolParameter(
                    type="string",
                    description="Drug name (e.g., 'ibuprofen') or RxNorm RXCUI code",
                    required=True,
                ),
            },
            domain="medical",
            category="drugs",
        ),
        ToolDefinition(
            name="rxnorm_spelling",
            description="Get spelling suggestions for drug names with typos. Helps correct misspelled medication names. Use when drug name might be misspelled or unclear.",
            parameters={
                "drug_name": ToolParameter(
                    type="string",
                    description="Drug name that may contain typos or misspellings",
                    required=True,
                ),
            },
            domain="medical",
            category="drugs",
        ),
        # iCite
        ToolDefinition(
            name="icite_metrics",
            description="Get citation metrics for a biomedical publication from NIH iCite. Returns citation count, Relative Citation Ratio (RCR), and NIH percentile. Use when user asks about impact or citations of a PubMed article.",
            parameters={
                "pmid": ToolParameter(
                    type="string",
                    description="PubMed ID of the article (e.g., '12345678')",
                    required=True,
                ),
            },
            domain="medical",
            category="research",
        ),
        ToolDefinition(
            name="icite_batch",
            description="Get citation metrics for multiple publications at once. Batch processing for iCite. Use when comparing impact of several papers.",
            parameters={
                "pmids": ToolParameter(
                    type="array",
                    description="Comma-separated list of PubMed IDs (e.g., '12345,67890')",
                    required=True,
                ),
            },
            domain="medical",
            category="research",
        ),
        # PubMed
        ToolDefinition(
            name="pubmed_search",
            description="Search biomedical literature on PubMed (NCBI). Find research papers, clinical studies, reviews by topic. Use when user asks for medical research, scientific papers, or academic articles about health topics.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Search query (e.g., 'diabetes treatment', 'COVID-19 vaccines')",
                    required=True,
                ),
                "max_results": ToolParameter(
                    type="integer",
                    description="Maximum number of papers to return (default 10)",
                    required=False,
                ),
            },
            domain="medical",
            category="research",
        ),
        ToolDefinition(
            name="pubmed_abstract",
            description="Get the full abstract text of a PubMed article by its PMID. Use when user wants to read the summary of a specific medical research paper.",
            parameters={
                "pmid": ToolParameter(
                    type="string", description="PubMed ID of the article", required=True
                ),
            },
            domain="medical",
            category="research",
        ),
        # Europe PMC
        ToolDefinition(
            name="europepmc_search",
            description="Search life sciences literature on Europe PMC. Covers biomedical and biological research from worldwide sources. Use when user asks 'ricerca scientifica su X', 'life sciences papers', 'biomedical research', 'articoli scientifici', or broad biology searches.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Search query for life sciences papers",
                    required=True,
                ),
                "max_results": ToolParameter(
                    type="integer",
                    description="Maximum number of papers to return",
                    required=False,
                ),
            },
            domain="medical",
            category="research",
        ),
        # ClinicalTrials.gov
        ToolDefinition(
            name="clinicaltrials_search",
            description="Search clinical trials on ClinicalTrials.gov. Find ongoing or completed medical research studies by disease or condition. Use when user asks about clinical trials, experimental treatments, or 'studies for X disease'.",
            parameters={
                "condition": ToolParameter(
                    type="string",
                    description="Disease or condition to search (e.g., 'cancer', 'Alzheimer's', 'diabetes')",
                    required=True,
                ),
                "status": ToolParameter(
                    type="string",
                    description="Trial status filter: RECRUITING, COMPLETED, ACTIVE_NOT_RECRUITING, etc.",
                    required=False,
                ),
                "max_results": ToolParameter(
                    type="integer",
                    description="Maximum number of trials to return",
                    required=False,
                ),
            },
            domain="medical",
            category="trials",
        ),
    ]


def get_executors() -> dict:
    """Return mapping of tool names to executor functions."""
    return AVAILABLE_TOOLS
