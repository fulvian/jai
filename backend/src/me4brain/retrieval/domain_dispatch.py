"""Domain Dispatch Bridge - Delega esecuzione ai DomainHandler.

Questo modulo funge da bridge tra tool_executor.py legacy e
la nuova architettura modulare basata su DomainHandler.

Quando un tool viene chiamato, il bridge:
1. Identifica il domain handler appropriato
2. Delega l'esecuzione al domain handler
3. Ritorna il risultato o fallback a handler legacy
"""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Mappa service_name -> domain_name (intent-based domains)
SERVICE_TO_DOMAIN: dict[str, str] = {
    # Finance
    "CoinGeckoService": "finance",
    "BinanceService": "finance",
    "YahooFinanceService": "finance",
    "FinnhubService": "finance",
    "AlphaVantageService": "finance",
    "PolygonService": "finance",
    "TwelveDataService": "finance",
    "FREDService": "finance",
    "EDGARService": "finance",
    # Science
    "ArXivService": "science",
    "CrossrefService": "science",
    "SemanticScholarService": "science",
    "EuropePMCService": "science",
    "PubMedService": "science",
    "OpenAlexService": "science",
    # Weather/Geo
    "OpenMeteoService": "geo_weather",
    "USGSEarthquakeService": "geo_weather",
    "NagerDateService": "geo_weather",
    "NominatimService": "geo_weather",
    "SunriseSunsetService": "geo_weather",
    # Search (knowledge/media)
    "WikipediaService": "search",
    "HackerNewsService": "search",
    "OpenLibraryService": "search",
    # Sports
    "BallDontLieService": "sports",
    "NBAStatsService": "sports",
    "TheOddsAPIService": "sports",
    "ESPNService": "sports",
    # Google Workspace (intent-based sub-domains)
    "GoogleDriveService": "file_management",
    "GoogleGmailService": "communication",
    "GoogleCalendarService": "scheduling",
    "GoogleDocsService": "content_creation",
    "GoogleSheetsService": "data_analysis",
    "GoogleSlidesService": "content_creation",
    "GoogleMeetService": "scheduling",
    "GoogleFormsService": "content_creation",
    "GoogleClassroomService": "content_creation",
    # Web Search
    "DuckDuckGoService": "web_search",
    # System (utility)
    "HttpbinService": "system",
    "IPifyService": "system",
}

# Mappa service.method -> domain tool name
METHOD_TO_TOOL: dict[str, str] = {
    # CoinGecko
    "CoinGeckoService.get_price": "coingecko_price",
    "CoinGeckoService.get_trending": "coingecko_trending",
    "CoinGeckoService.get_chart": "coingecko_chart",
    # Binance
    "BinanceService.get_price": "binance_price",
    "BinanceService.get_24h_ticker": "binance_ticker_24h",
    # Yahoo Finance
    "YahooFinanceService.get_quote": "yahoo_finance_quote",
    # Finnhub
    "FinnhubService.get_news": "finnhub_news",
    "FinnhubService.get_quote": "finnhub_quote",
    # ArXiv
    "ArXivService.search": "arxiv_search",
    # Crossref
    "CrossrefService.search": "crossref_search",
    "CrossrefService.get_by_doi": "crossref_doi",
    # OpenAlex
    "OpenAlexService.search_works": "openalex_search",
    # PubMed
    "PubMedService.search": "pubmed_search",
    # Europe PMC
    "EuropePMCService.search": "europepmc_search",
    # Meteo
    "OpenMeteoService.get_weather": "openmeteo_weather",
    "USGSEarthquakeService.get_recent": "usgs_earthquakes",
    "NagerDateService.get_holidays": "nager_holidays",
    # Knowledge
    "WikipediaService.get_summary": "wikipedia_summary",
    "HackerNewsService.get_top": "hackernews_top",
    "OpenLibraryService.search": "openlibrary_search",
    # Web Search
    "DuckDuckGoService.instant_answer": "duckduckgo_instant",
    # Utility
    "HttpbinService.get_ip": "get_ip",
    "HttpbinService.get_headers": "get_headers",
}

# Registry cache per domain handlers
_domain_registry: Any = None


async def get_domain_registry(tenant_id: str = "default") -> Any:
    """Ottiene singleton PluginRegistry."""
    global _domain_registry
    if _domain_registry is None:
        from me4brain.core.plugin_registry import PluginRegistry

        _domain_registry = await PluginRegistry.get_instance(tenant_id)
    return _domain_registry


async def dispatch_to_domain(
    service_name: str,
    method_name: str,
    arguments: dict[str, Any],
    tenant_id: str = "default",
) -> dict[str, Any] | None:
    """Tenta dispatch a domain handler.

    Returns:
        dict risultato se handled, None se deve usare fallback legacy
    """
    domain_name = SERVICE_TO_DOMAIN.get(service_name)
    if not domain_name:
        return None

    tool_key = f"{service_name}.{method_name}"
    tool_name = METHOD_TO_TOOL.get(tool_key)

    if not tool_name:
        logger.debug(
            "domain_dispatch_no_tool_mapping",
            service=service_name,
            method=method_name,
        )
        return None

    try:
        registry = await get_domain_registry(tenant_id)
        handler = registry.get_handler(domain_name)

        if handler is None:
            return None

        result = await handler.execute_tool(tool_name, arguments)

        logger.info(
            "domain_dispatch_success",
            domain=domain_name,
            tool=tool_name,
        )

        return result

    except Exception as e:
        logger.warning(
            "domain_dispatch_error",
            domain=domain_name,
            tool=tool_name,
            error=str(e),
        )
        return None


def is_domain_handled(service_name: str) -> bool:
    """Check se servizio è gestito da domain handler."""
    return service_name in SERVICE_TO_DOMAIN
