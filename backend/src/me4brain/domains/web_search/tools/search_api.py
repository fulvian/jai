"""Web Search API Tools.

Strategia di Routing:
- DuckDuckGo: Query semplici, alta frequenza, no API key (illimitato)
- Tavily: Query complesse, ricerche deep, estrazione contenuti (1000 credit/mese)
"""

from typing import Any
import os
import httpx
import structlog

logger = structlog.get_logger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY")
TAVILY_BASE_URL = "https://api.tavily.com"
BRAVE_BASE_URL = "https://api.search.brave.com/res/v1/web/search"


# =============================================================================
# DuckDuckGo (Free, Unlimited)
# =============================================================================


async def duckduckgo_instant(query: str) -> dict[str, Any]:
    """DuckDuckGo Instant Answer API con fallback su Wikipedia.

    Gratuito e illimitato. Ideale per:
    - Definizioni rapide
    - Fatti semplici
    - Ricerche ad alta frequenza

    Se DDG fallisce (202, 302, timeout), tenta automaticamente Wikipedia API.
    """
    # ==========================================================================
    # STEP 1: Tentativo DuckDuckGo con parametri corretti
    # ==========================================================================
    ddg_result = await _duckduckgo_api_call(query)

    # Se DDG ha restituito dati utili, ritorna subito
    if not ddg_result.get("error") and (ddg_result.get("abstract") or ddg_result.get("answer")):
        return ddg_result

    # ==========================================================================
    # STEP 2: Fallback su Wikipedia API (gratuita, affidabile)
    # ==========================================================================
    logger.info(
        "duckduckgo_fallback_to_wikipedia",
        reason=ddg_result.get("error"),
        query=query[:50],
    )
    wikipedia_result = await _wikipedia_api_search(query)

    if not wikipedia_result.get("error"):
        return wikipedia_result

    # ==========================================================================
    # STEP 3: Se tutto fallisce, ritorna errore DDG originale
    # ==========================================================================
    return ddg_result


async def _duckduckgo_api_call(query: str) -> dict[str, Any]:
    """Chiamata diretta a DuckDuckGo API con parametri corretti."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,  # Skip disambiguation pages
                    "t": "me4brain",  # app_name (required by DDG ToS)
                },
            )

            # Check status code
            if resp.status_code != 200:
                logger.warning(
                    "duckduckgo_http_error",
                    status=resp.status_code,
                    query=query[:50],
                )
                return {"error": f"HTTP {resp.status_code}", "source": "DuckDuckGo"}

            # Check response is not empty
            if not resp.text or resp.text.strip() == "":
                logger.warning("duckduckgo_empty_response", query=query[:50])
                return {"error": "Empty response", "source": "DuckDuckGo"}

            # Safe JSON parsing
            try:
                data = resp.json()
            except Exception as json_err:
                logger.error(
                    "duckduckgo_json_parse_error",
                    error=str(json_err),
                    body_preview=resp.text[:200],
                    query=query[:50],
                )
                return {
                    "error": f"JSON parse error: {json_err}",
                    "source": "DuckDuckGo",
                }

            return {
                "heading": data.get("Heading"),
                "abstract": data.get("Abstract"),
                "abstract_source": data.get("AbstractSource"),
                "answer": data.get("Answer"),
                "related_topics": [
                    t.get("Text") for t in data.get("RelatedTopics", [])[:5] if t.get("Text")
                ],
                "source": "DuckDuckGo",
                "credits_used": 0,
            }
    except Exception as e:
        logger.error("duckduckgo_error", error=str(e))
        return {"error": str(e), "source": "DuckDuckGo"}


async def _wikipedia_api_search(query: str) -> dict[str, Any]:
    """Fallback: Wikipedia API (gratuita, affidabile, no auth).

    Usa Wikipedia OpenSearch API per trovare articoli rilevanti,
    poi recupera il summary dell'articolo più rilevante.

    NOTA: Wikipedia richiede User-Agent header valido (policy).

    Strategia: Estrae parole chiave dalla query e prova varianti.
    """
    headers = {
        "User-Agent": "Me4BrAIn/1.0 (https://github.com/me4brain; me4brain@example.com)",
    }

    # Traduzione IT->EN per termini culinari comuni
    it_to_en = {
        "ricetta": "recipe",
        "ricette": "recipes",
        "pasta": "pasta",
        "carne": "meat",
        "verdura": "vegetable",
        "verdure": "vegetables",
        "vegetariana": "vegetarian",
        "vegetariano": "vegetarian",
        "cucina": "cooking",
        "cucinare": "cook",
        "ingredienti": "ingredients",
        "ingredient": "ingredient",
    }

    # Stopwords italiane da rimuovere
    stopwords = {
        "trovami",
        "cerca",
        "una",
        "del",
        "della",
        "per",
        "la",
        "qual",
        "quale",
        "quanti",
        "come",
        "cosa",
        "cos",
        "fammi",
        "fare",
        "quando",
        "dove",
        "chi",
        "che",
        "quello",
        "questa",
        "qui",
        "adesso",
        "ora",
        "poi",
        "con",
        "però",
        "ma",
        "essere",
        "sono",
        "un",
        "alla",
        "al",
        "ai",
    }

    # Termini generici da deprioritizzare (cercare dopo i termini specifici)
    generic_terms = {
        "recipe",
        "recipes",
        "ingredient",
        "ingredients",
        "cook",
        "cooking",
        "make",
        "how",
    }

    # Aggettivi da deprioritizzare (meno specifici dei nomi di piatti)
    adjective_terms = {
        "vegetarian",
        "vegetariana",
        "vegetariano",
        "vegan",
        "traditional",
        "tradizionale",
        "homemade",
        "fatto",
        "casa",
        "easy",
        "semplice",
        "quick",
        "veloce",
        "authentic",
        "autentico",
        "best",
        "migliore",
    }

    import re

    words = re.findall(r"\b[a-zA-ZàèéìòùÀÈÉÌÒÙ]{3,}\b", query.lower())

    # Costruisci query: traduci + rimuovi stopwords
    translated = []
    for w in words:
        if w in stopwords:
            continue
        if w in it_to_en:
            translated.append(it_to_en[w])
        else:
            translated.append(w)

    # Separa termini: specifici (non aggettivi) > aggettivi > generici
    all_specific = [t for t in translated if t not in generic_terms]
    noun_terms = sorted(
        [t for t in all_specific if t not in adjective_terms],
        key=len,
        reverse=True,
    )
    adj_terms = sorted(
        [t for t in all_specific if t in adjective_terms],
        key=len,
        reverse=True,
    )
    generic_in_query = [t for t in translated if t in generic_terms]

    # Genera varianti di query da provare
    # Strategia: privilegia nomi di piatti > aggettivi > termini generici
    query_variants = []

    if noun_terms or adj_terms:
        all_specific_sorted = noun_terms + adj_terms
        # Variante 1: singoli NOMI prima - spesso più specifici delle combinazioni
        for t in noun_terms[:3]:
            query_variants.append(t)
        # Variante 2: combinazione di 2 termini specifici
        if len(all_specific_sorted) >= 2:
            query_variants.append(" ".join(all_specific_sorted[:2]))
        # Variante 3: combinazione di 4 termini
        query_variants.append(" ".join(all_specific_sorted[:4]))
        # Variante 4: singoli aggettivi (se non ci sono nomi)
        if not noun_terms:
            for t in adj_terms[:2]:
                query_variants.append(t)
        # Variante 5: combinazione nome + generico
        if generic_in_query and noun_terms:
            combo = f"{noun_terms[0]} {generic_in_query[0]}"
            if combo not in query_variants:
                query_variants.append(combo)

    # Fallback: termini originali se nessun termine specifico
    if not query_variants and translated:
        query_variants.append(" ".join(translated[:4]))
        if len(translated) >= 2:
            query_variants.append(" ".join(translated[:2]))
        query_variants.append(translated[0])

    # Rimuovi duplicati mantenendo l'ordine
    seen = set()
    query_variants = [x for x in query_variants if not (x in seen or seen.add(x))]

    logger.info("wikipedia_search_variants", original=query[:50], variants=query_variants)

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            # Prova ogni variante fino a trovare risultati
            for search_query in query_variants:
                search_resp = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "opensearch",
                        "search": search_query,
                        "limit": 3,
                        "namespace": 0,
                        "format": "json",
                    },
                )

                if search_resp.status_code != 200:
                    continue

                search_data = search_resp.json()
                if len(search_data) < 4 or not search_data[1]:
                    continue

                # Trovato risultati! Ottieni summary
                titles = search_data[1]
                urls = search_data[3] if len(search_data) > 3 else []

                summary_resp = await client.get(
                    "https://en.wikipedia.org/api/rest_v1/page/summary/"
                    + titles[0].replace(" ", "_"),
                )

                if summary_resp.status_code == 200:
                    summary_data = summary_resp.json()
                    logger.info("wikipedia_search_success", query=search_query, title=titles[0])
                    return {
                        "heading": summary_data.get("title", titles[0]),
                        "abstract": summary_data.get("extract", ""),
                        "abstract_source": "Wikipedia",
                        "answer": None,
                        "url": summary_data.get("content_urls", {})
                        .get("desktop", {})
                        .get("page", urls[0] if urls else None),
                        "related_topics": titles[1:] if len(titles) > 1 else [],
                        "source": "Wikipedia (via DuckDuckGo fallback)",
                        "credits_used": 0,
                    }
                else:
                    # Fallback a descrizione base
                    return {
                        "heading": titles[0],
                        "abstract": search_data[2][0] if search_data[2] else "",
                        "abstract_source": "Wikipedia",
                        "answer": None,
                        "url": urls[0] if urls else None,
                        "related_topics": titles[1:] if len(titles) > 1 else [],
                        "source": "Wikipedia (via DuckDuckGo fallback)",
                        "credits_used": 0,
                    }

            # Nessuna variante ha dato risultati
            return {"error": "No Wikipedia results", "source": "Wikipedia"}

    except Exception as e:
        logger.error("wikipedia_api_error", error=str(e))
        return {"error": str(e), "source": "Wikipedia"}


# =============================================================================
# Brave Search (5000 queries/month - Free Tier)
# =============================================================================


async def brave_search(
    query: str,
    count: int = 5,
    search_lang: str = "it",
    country: str = "it",
) -> dict[str, Any]:
    """Brave Search API - Ideale per news e query ampie/broad.

    Free tier: 5000 queries/month.
    """
    if not BRAVE_SEARCH_API_KEY:
        return {
            "error": "BRAVE_SEARCH_API_KEY non configurata in .env",
            "source": "Brave",
        }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                BRAVE_BASE_URL,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
                },
                params={
                    "q": query,
                    "count": count,
                    "search_lang": search_lang,
                    "country": country,
                    "spellcheck": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            # Brave formats results in web.results
            web_results = data.get("web", {}).get("results", [])
            for r in web_results:
                results.append(
                    {
                        "title": r.get("title"),
                        "url": r.get("url"),
                        "description": r.get("description"),
                        "age": r.get("page_age"),
                    }
                )

            return {
                "query": query,
                "results": results,
                "results_count": len(results),
                "source": "Brave Search",
                "credits_used": 1,
            }
    except Exception as e:
        logger.error("brave_search_error", error=str(e))
        return {"error": str(e), "source": "Brave"}


# =============================================================================
# Tavily (1000 credits/mese - Developer Plan)
# =============================================================================


async def tavily_search(
    query: str,
    search_depth: str = "basic",
    topic: str = "general",
    max_results: int = 5,
    include_answer: bool = True,
    include_raw_content: bool = False,
    time_range: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Tavily Search API - Ricerca web avanzata con AI.

    Costo: 1 credit (basic/fast) o 2 credits (advanced)

    Ideale per:
    - Ricerche complesse che richiedono contesto
    - Query che necessitano risposta sintetizzata
    - Ricerche con filtri temporali o di dominio
    - Query di notizie/finanza

    Args:
        query: Query di ricerca
        search_depth: basic (1 credit), advanced (2 credits), fast, ultra-fast
        topic: general, news, finance
        max_results: 1-20 risultati
        include_answer: Includi risposta AI sintetizzata
        include_raw_content: Includi contenuto raw markdown
        time_range: day, week, month, year
        include_domains: Lista domini da includere
        exclude_domains: Lista domini da escludere
    """
    if not TAVILY_API_KEY:
        return {
            "error": "TAVILY_API_KEY non configurata in .env",
            "source": "Tavily",
        }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "query": query,
                "search_depth": search_depth,
                "topic": topic,
                "max_results": max_results,
                "include_answer": include_answer,
                "include_raw_content": include_raw_content,
            }

            if time_range:
                payload["time_range"] = time_range
            if include_domains:
                payload["include_domains"] = include_domains
            if exclude_domains:
                payload["exclude_domains"] = exclude_domains

            resp = await client.post(
                f"{TAVILY_BASE_URL}/search",
                headers={
                    "Authorization": f"Bearer {TAVILY_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            # Estrai risultati
            results = []
            for r in data.get("results", []):
                results.append(
                    {
                        "title": r.get("title"),
                        "url": r.get("url"),
                        "content": r.get("content"),
                        "score": r.get("score"),
                    }
                )

            credits_used = data.get("usage", {}).get("credits", 1)

            return {
                "query": data.get("query"),
                "answer": data.get("answer"),
                "results": results,
                "results_count": len(results),
                "response_time": data.get("response_time"),
                "credits_used": credits_used,
                "source": "Tavily",
            }

    except httpx.HTTPStatusError as e:
        logger.error("tavily_http_error", status=e.response.status_code, error=str(e))
        return {"error": f"HTTP {e.response.status_code}: {str(e)}", "source": "Tavily"}
    except Exception as e:
        logger.error("tavily_search_error", error=str(e))
        return {"error": str(e), "source": "Tavily"}


async def tavily_extract(
    urls: list[str],
    include_images: bool = False,
) -> dict[str, Any]:
    """Tavily Extract API - Estrae contenuto pulito da URL.

    Costo: 1 credit per URL

    Ideale per:
    - Estrarre contenuto da pagine web specifiche
    - Analisi di articoli/documenti online

    Args:
        urls: Lista URL da estrarre (max 10)
        include_images: Includi immagini
    """
    if not TAVILY_API_KEY:
        return {
            "error": "TAVILY_API_KEY non configurata in .env",
            "source": "Tavily Extract",
        }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{TAVILY_BASE_URL}/extract",
                headers={
                    "Authorization": f"Bearer {TAVILY_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "urls": urls[:10],  # Max 10 URLs
                    "include_images": include_images,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            extracts = []
            for r in data.get("results", []):
                extracts.append(
                    {
                        "url": r.get("url"),
                        "raw_content": r.get("raw_content", "")[:5000],  # Limita a 5k chars
                    }
                )

            return {
                "extracts": extracts,
                "count": len(extracts),
                "credits_used": len(urls),
                "source": "Tavily Extract",
            }

    except Exception as e:
        logger.error("tavily_extract_error", error=str(e))
        return {"error": str(e), "source": "Tavily Extract"}


async def smart_search(
    query: str,
    force_provider: str | None = None,
) -> dict[str, Any]:
    """Smart Search - Routing intelligente a 3 livelli (Brave, Tavily, DDG).

    Logica routing:
    1. News/Broad/Site: Brave Search (5000 q/mo)
    2. Research/Deep/Complex: Tavily (1000 q/mo)
    3. Quick Facts/Fallback/Def: DuckDuckGo (Unlimited)
    """
    # Se forzato, usa quel provider
    if force_provider:
        p = force_provider.lower()
        if p == "tavily" and TAVILY_API_KEY:
            return await tavily_search(query)
        if p == "brave" and BRAVE_SEARCH_API_KEY:
            return await brave_search(query)
        return await duckduckgo_instant(query)

    query_lower = query.lower()
    word_count = len(query.split())

    # TIER 1: Brave per News e Broad queries
    is_news = any(k in query_lower for k in ["news", "latest", "ultim", "oggi", "2025", "2026"])
    is_site = "site:" in query_lower

    if (is_news or is_site or word_count in [4, 5]) and BRAVE_SEARCH_API_KEY:
        logger.info("smart_search_routing", tier="Brave", reason="News/Broad")
        return await brave_search(query)

    # TIER 2: Tavily per ricerche profonde e complesse
    is_complex = word_count > 7 or any(
        k in query_lower for k in ["perché", "come", "analisi", "confronto", "differenza", "spiega"]
    )

    if is_complex and TAVILY_API_KEY:
        logger.info("smart_search_routing", tier="Tavily", reason="Complex/Research")
        return await tavily_search(query)

    # TIER 3: DDG per facts e tutto il resto
    logger.info("smart_search_routing", tier="DuckDuckGo", reason="Fact/Quick/Fallback")
    return await duckduckgo_instant(query)


# =============================================================================
# Tool Registry
# =============================================================================

AVAILABLE_TOOLS = {
    # Free (unlimited)
    "duckduckgo_instant": duckduckgo_instant,
    # Premium (Limited)
    "brave_search": brave_search,
    "tavily_search": tavily_search,
    "tavily_extract": tavily_extract,
    # Smart routing
    "smart_search": smart_search,
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool search per nome, filtrando parametri non accettati."""
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {"error": f"Unknown search tool: {tool_name}"}

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
# Engine Integration - Tool Definitions for auto-discovery
# =============================================================================


def get_tool_definitions() -> list:
    """Get tool definitions for ToolCallingEngine auto-discovery."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        ToolDefinition(
            name="duckduckgo_instant",
            description="Quick web search using DuckDuckGo for instant answers, definitions, facts, and Wikipedia summaries. Free and rate-limit-free. Use when user asks simple factual questions, 'what is X', definitions, or quick lookups.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Search query (e.g., 'capital of France', 'define photosynthesis')",
                    required=True,
                ),
            },
            domain="web_search",
            category="search",
        ),
        ToolDefinition(
            name="tavily_search",
            description="AI-powered web search using Tavily for complex queries, recent news, and in-depth research. Returns summarized content with source citations. Use when user needs current events, detailed research, news articles, or complex multi-topic searches.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Search query (e.g., 'latest AI developments 2024', 'climate change effects')",
                    required=True,
                ),
                "search_depth": ToolParameter(
                    type="string",
                    description="Search thoroughness: 'basic' (fast) or 'advanced' (comprehensive)",
                    required=False,
                    default="basic",
                    enum=["basic", "advanced"],
                ),
                "topic": ToolParameter(
                    type="string",
                    description="Topic category for optimized results",
                    required=False,
                    default="general",
                    enum=["general", "news", "finance"],
                ),
                "max_results": ToolParameter(
                    type="integer",
                    description="Number of results (1-20, default 5)",
                    required=False,
                    default="5",
                ),
            },
            domain="web_search",
            category="search",
        ),
        ToolDefinition(
            name="tavily_extract",
            description="Extract clean readable content from web page URLs. Converts HTML pages to structured text, removing ads and navigation. Use when user provides a URL and wants the content read or summarized.",
            parameters={
                "urls": ToolParameter(
                    type="array",
                    description="List of URLs to extract content from (max 10)",
                    required=True,
                ),
            },
            domain="web_search",
            category="extract",
        ),
        ToolDefinition(
            name="brave_search",
            description="Web search optimized for news, latest events (2025/2026), and broad queries. Use for recent news, finding websites, or general information when DDG is too limited.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Search query",
                    required=True,
                ),
            },
            domain="web_search",
            category="search",
        ),
        ToolDefinition(
            name="smart_search",
            description="Intelligent web search that automatically routes between DuckDuckGo, Brave, and Tavily based on query complexity and intent. Use for any general web search query.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Search query for web",
                    required=True,
                ),
                "force_provider": ToolParameter(
                    type="string",
                    description="Override auto-routing: 'duckduckgo', 'brave', or 'tavily'",
                    required=False,
                    enum=["duckduckgo", "brave", "tavily"],
                ),
            },
            domain="web_search",
            category="search",
        ),
    ]


def get_executors() -> dict:
    """Get executor functions for ToolCallingEngine."""
    return {
        "duckduckgo_instant": duckduckgo_instant,
        "brave_search": brave_search,
        "tavily_search": tavily_search,
        "tavily_extract": tavily_extract,
        "smart_search": smart_search,
    }
