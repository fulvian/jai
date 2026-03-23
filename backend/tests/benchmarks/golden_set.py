"""Golden Set for Retrieval System Evaluation.

This module provides a curated set of test cases for evaluating the retrieval
system's accuracy, latency, and quality metrics. The golden set is used for:
- Tool selection recall@10 measurement
- Wrong domain failure detection
- Zero-result rate tracking
- SLO compliance verification

Each entry contains:
- query: The user query text
- expected_domains: List of domains that should handle this query
- expected_tools: List of tool names that should be in top-10 results
- complexity: Query complexity level (simple/medium/complex)
- notes: Additional context about the test case
"""

from dataclasses import dataclass, field
from typing import Literal

# Query complexity levels
Complexity = Literal["simple", "medium", "complex"]


@dataclass(frozen=True)
class GoldenTestCase:
    """A single test case in the golden set.

    Attributes:
        query: The user query text (in Italian or English)
        expected_domains: Domains that should handle this query
        expected_tools: Tool names that should appear in top-10 results
        complexity: Query complexity (simple/medium/complex)
        notes: Additional context or edge cases
    """

    query: str
    expected_domains: list[str]
    expected_tools: list[str] = field(default_factory=list)
    complexity: Complexity = "simple"
    notes: str = ""


# =============================================================================
# GEO_WEATHER Domain Tests
# =============================================================================
GEO_WEATHER_CASES = [
    GoldenTestCase(
        query="meteo Roma oggi",
        expected_domains=["geo_weather"],
        expected_tools=["openmeteo_current"],
        complexity="simple",
        notes="Basic weather query for Rome",
    ),
    GoldenTestCase(
        query="che tempo farà domani a Milano?",
        expected_domains=["geo_weather"],
        expected_tools=["openmeteo_current", "openmeteo_forecast"],
        complexity="simple",
        notes="Forecast query for Milan",
    ),
    GoldenTestCase(
        query="temperatura adesso a Napoli",
        expected_domains=["geo_weather"],
        expected_tools=["openmeteo_current"],
        complexity="simple",
        notes="Current temperature query",
    ),
    GoldenTestCase(
        query="will it rain in Florence this weekend?",
        expected_domains=["geo_weather"],
        expected_tools=["openmeteo_current", "openmeteo_forecast"],
        complexity="simple",
        notes="English weather query",
    ),
    GoldenTestCase(
        query="previsioni neve per le Alpi",
        expected_domains=["geo_weather"],
        expected_tools=["openmeteo_forecast"],
        complexity="medium",
        notes="Snow forecast for Alps region",
    ),
]


# =============================================================================
# FINANCE_CRYPTO Domain Tests
# =============================================================================
FINANCE_CRYPTO_CASES = [
    GoldenTestCase(
        query="prezzo Bitcoin",
        expected_domains=["finance_crypto"],
        expected_tools=["coingecko_price"],
        complexity="simple",
        notes="Basic Bitcoin price",
    ),
    GoldenTestCase(
        query="quanto costa Ethereum adesso?",
        expected_domains=["finance_crypto"],
        expected_tools=["coingecko_price"],
        complexity="simple",
        notes="Ethereum price query",
    ),
    GoldenTestCase(
        query="azioni Apple oggi",
        expected_domains=["finance_crypto"],
        expected_tools=["yahoo_finance_price"],
        complexity="simple",
        notes="Stock price query",
    ),
    GoldenTestCase(
        query="andamento borsa italiana",
        expected_domains=["finance_crypto"],
        expected_tools=["yahoo_finance_search"],
        complexity="medium",
        notes="Italian stock market query",
    ),
    GoldenTestCase(
        query="trading crypto su Binance",
        expected_domains=["finance_crypto"],
        expected_tools=["binance_price", "coingecko_price"],
        complexity="medium",
        notes="Crypto trading platform query",
    ),
    GoldenTestCase(
        query="analisi tecnica Bitcoin",
        expected_domains=["finance_crypto"],
        expected_tools=["yahoo_finance_chart"],
        complexity="complex",
        notes="Technical analysis for crypto",
    ),
    GoldenTestCase(
        query="hyperliquid perpetual BTC",
        expected_domains=["finance_crypto"],
        expected_tools=["hyperliquid_price", "hyperliquid_orderbook"],
        complexity="medium",
        notes="Hyperliquid perpetual query",
    ),
    GoldenTestCase(
        query="stock price TSLA",
        expected_domains=["finance_crypto"],
        expected_tools=["yahoo_finance_price"],
        complexity="simple",
        notes="Tesla stock in English",
    ),
]


# =============================================================================
# SPORTS_NBA Domain Tests
# =============================================================================
SPORTS_NBA_CASES = [
    GoldenTestCase(
        query="Lakers vs Celtics risultato",
        expected_domains=["sports_nba"],
        expected_tools=["nba_live_scores", "nba_team_schedule"],
        complexity="simple",
        notes="NBA game result query",
    ),
    GoldenTestCase(
        query="statistiche LeBron James",
        expected_domains=["sports_nba"],
        expected_tools=["nba_player_stats"],
        complexity="simple",
        notes="Player statistics query",
    ),
    GoldenTestCase(
        query="scommessa NBA stasera",
        expected_domains=["sports_nba"],
        expected_tools=["nba_betting_odds"],
        complexity="medium",
        notes="NBA betting query in Italian",
    ),
    GoldenTestCase(
        query="odds for Warriors game",
        expected_domains=["sports_nba"],
        expected_tools=["nba_betting_odds"],
        complexity="simple",
        notes="NBA odds in English",
    ),
    GoldenTestCase(
        query="pronostico scommesse NBA oggi",
        expected_domains=["sports_nba"],
        expected_tools=["nba_betting_odds", "nba_expert_picks"],
        complexity="medium",
        notes="NBA betting tips in Italian",
    ),
    GoldenTestCase(
        query="nba over under picks",
        expected_domains=["sports_nba"],
        expected_tools=["nba_betting_odds"],
        complexity="simple",
        notes="Over/under betting query",
    ),
    GoldenTestCase(
        query="picks NBA stasera",
        expected_domains=["sports_nba"],
        expected_tools=["nba_expert_picks"],
        complexity="simple",
        notes="Expert picks in Italian",
    ),
    GoldenTestCase(
        query="warriors vs suns preview",
        expected_domains=["sports_nba"],
        expected_tools=["nba_live_scores", "nba_team_schedule"],
        complexity="simple",
        notes="Team matchup in English",
    ),
    GoldenTestCase(
        query="punto spread Nets oggi",
        expected_domains=["sports_nba"],
        expected_tools=["nba_betting_odds"],
        complexity="simple",
        notes="Point spread query in Italian",
    ),
    GoldenTestCase(
        query="sistema scommesse NBA",
        expected_domains=["sports_nba"],
        expected_tools=["nba_expert_picks", "nba_betting_odds"],
        complexity="complex",
        notes="Betting system query",
    ),
]


# =============================================================================
# WEB_SEARCH Domain Tests
# =============================================================================
WEB_SEARCH_CASES = [
    GoldenTestCase(
        query="cerca informazioni su AI",
        expected_domains=["web_search"],
        expected_tools=["web_search"],
        complexity="simple",
        notes="Generic search query",
    ),
    GoldenTestCase(
        query="notizie ultima ora",
        expected_domains=["web_search"],
        expected_tools=["web_search"],
        complexity="simple",
        notes="News search",
    ),
    GoldenTestCase(
        query="find restaurant near me",
        expected_domains=["web_search"],
        expected_tools=["web_search"],
        complexity="simple",
        notes="Local search in English",
    ),
    GoldenTestCase(
        query="who is the president of Italy",
        expected_domains=["web_search"],
        expected_tools=["web_search"],
        complexity="simple",
        notes="Fact lookup in English",
    ),
]


# =============================================================================
# GOOGLE_WORKSPACE Domain Tests
# =============================================================================
GOOGLE_WORKSPACE_CASES = [
    GoldenTestCase(
        query="invia email a Mario",
        expected_domains=["google_workspace"],
        expected_tools=["gmail_send"],
        complexity="simple",
        notes="Send email task",
    ),
    GoldenTestCase(
        query="leggi miei messaggi gmail",
        expected_domains=["google_workspace"],
        expected_tools=["gmail_search"],
        complexity="simple",
        notes="Read emails",
    ),
    GoldenTestCase(
        query="appuntamento domani alle 10",
        expected_domains=["google_workspace"],
        expected_tools=["calendar_create_event"],
        complexity="simple",
        notes="Calendar scheduling",
    ),
    GoldenTestCase(
        query="mostra eventi calendario oggi",
        expected_domains=["google_workspace"],
        expected_tools=["calendar_list_events"],
        complexity="simple",
        notes="List today's events",
    ),
    GoldenTestCase(
        query="crea documento su Google Drive",
        expected_domains=["google_workspace"],
        expected_tools=["drive_create_document"],
        complexity="simple",
        notes="Create document",
    ),
    GoldenTestCase(
        query="cerca file su drive",
        expected_domains=["google_workspace"],
        expected_tools=["drive_search_files"],
        complexity="simple",
        notes="Search files on Drive",
    ),
]


# =============================================================================
# FOOD Domain Tests
# =============================================================================
FOOD_CASES = [
    GoldenTestCase(
        query="ristorante giapponese vicino a me",
        expected_domains=["food"],
        expected_tools=["yelp_search"],
        complexity="simple",
        notes="Japanese restaurant search",
    ),
    GoldenTestCase(
        query="menu pizza Roma",
        expected_domains=["food"],
        expected_tools=["yelp_search"],
        complexity="simple",
        notes="Menu search",
    ),
    GoldenTestCase(
        query="prenota tavolo per 4 persone",
        expected_domains=["food"],
        expected_tools=["yelp_search"],
        complexity="medium",
        notes="Restaurant reservation",
    ),
]


# =============================================================================
# TRAVEL Domain Tests
# =============================================================================
TRAVEL_CASES = [
    GoldenTestCase(
        query="volo Milano Roma domani",
        expected_domains=["travel"],
        expected_tools=["amadeus_flight_search"],
        complexity="medium",
        notes="Flight search one-way",
    ),
    GoldenTestCase(
        query="prenota hotel a Firenze",
        expected_domains=["travel"],
        expected_tools=["booking_hotel_search"],
        complexity="medium",
        notes="Hotel booking",
    ),
    GoldenTestCase(
        query="flight from Rome to Paris",
        expected_domains=["travel"],
        expected_tools=["amadeus_flight_search"],
        complexity="medium",
        notes="International flight in English",
    ),
]


# =============================================================================
# SPORTS_BOOKING Domain Tests
# =============================================================================
SPORTS_BOOKING_CASES = [
    GoldenTestCase(
        query="prenota campo tennis",
        expected_domains=["sports_booking"],
        expected_tools=["playtomic_search"],
        complexity="simple",
        notes="Tennis court booking",
    ),
    GoldenTestCase(
        query="cerca campi padel Milano",
        expected_domains=["sports_booking"],
        expected_tools=["playtomic_search"],
        complexity="simple",
        notes="Padel court search",
    ),
    GoldenTestCase(
        query="prenota calcetto per stasera",
        expected_domains=["sports_booking"],
        expected_tools=["playtomic_search"],
        complexity="simple",
        notes="Football pitch booking",
    ),
]


# =============================================================================
# SCIENCE_RESEARCH Domain Tests
# =============================================================================
SCIENCE_RESEARCH_CASES = [
    GoldenTestCase(
        query="cerca paper su machine learning",
        expected_domains=["science_research"],
        expected_tools=["arxiv_search"],
        complexity="simple",
        notes="ArXiv paper search",
    ),
    GoldenTestCase(
        query="pubmed ricerca su cancro",
        expected_domains=["science_research"],
        expected_tools=["pubmed_search"],
        complexity="medium",
        notes="Medical research search",
    ),
    GoldenTestCase(
        query="studio scientifico su clima",
        expected_domains=["science_research"],
        expected_tools=["arxiv_search"],
        complexity="medium",
        notes="Climate science paper",
    ),
]


# =============================================================================
# MEDICAL Domain Tests
# =============================================================================
MEDICAL_CASES = [
    GoldenTestCase(
        query="sintomi influenza",
        expected_domains=["medical"],
        expected_tools=["pubmed_search"],
        complexity="simple",
        notes="Flu symptoms lookup",
    ),
    GoldenTestCase(
        query="effetti collaterali farmaco",
        expected_domains=["medical"],
        expected_tools=["pubmed_search"],
        complexity="medium",
        notes="Drug side effects",
    ),
]


# =============================================================================
# ENTERTAINMENT Domain Tests
# =============================================================================
ENTERTAINMENT_CASES = [
    GoldenTestCase(
        query="film da vedere stasera",
        expected_domains=["entertainment"],
        expected_tools=["tmdb_movie_search"],
        complexity="simple",
        notes="Movie recommendation",
    ),
    GoldenTestCase(
        query=" serie tv nuove su Netflix",
        expected_domains=["entertainment"],
        expected_tools=["tmdb_tv_search"],
        complexity="simple",
        notes="TV show search",
    ),
    GoldenTestCase(
        query="musica jazz rilassante",
        expected_domains=["entertainment"],
        expected_tools=["spotify_search"],
        complexity="simple",
        notes="Music search",
    ),
]


# =============================================================================
# KNOWLEDGE_MEDIA Domain Tests
# =============================================================================
KNOWLEDGE_MEDIA_CASES = [
    GoldenTestCase(
        query="spiega il funzionamento dei bitcoin",
        expected_domains=["knowledge_media"],
        expected_tools=["wikipedia_search"],
        complexity="simple",
        notes="Knowledge explanation",
    ),
    GoldenTestCase(
        query="wiki storia di Roma",
        expected_domains=["knowledge_media"],
        expected_tools=["wikipedia_search"],
        complexity="simple",
        notes="Historical wiki query",
    ),
]


# =============================================================================
# TECH_CODING Domain Tests
# =============================================================================
TECH_CODING_CASES = [
    GoldenTestCase(
        query="documentazione API REST",
        expected_domains=["tech_coding"],
        expected_tools=["web_search"],
        complexity="simple",
        notes="API documentation search",
    ),
    GoldenTestCase(
        query="stackoverflow error python",
        expected_domains=["tech_coding"],
        expected_tools=["web_search"],
        complexity="simple",
        notes="Programming Q&A",
    ),
]


# =============================================================================
# JOBS Domain Tests
# =============================================================================
JOBS_CASES = [
    GoldenTestCase(
        query="cerco lavoro sviluppatore Python",
        expected_domains=["jobs"],
        expected_tools=["web_search"],
        complexity="simple",
        notes="Job search",
    ),
    GoldenTestCase(
        query="offerte di lavoro remote",
        expected_domains=["jobs"],
        expected_tools=["web_search"],
        complexity="simple",
        notes="Remote job search",
    ),
]


# =============================================================================
# SHOPPING Domain Tests (should redirect to web_search)
# =============================================================================
SHOPPING_CASES = [
    GoldenTestCase(
        query="compra iPhone su Amazon",
        expected_domains=["web_search"],  # Should redirect from shopping
        expected_tools=["web_search"],
        complexity="simple",
        notes="Shopping query should redirect to web_search",
    ),
    GoldenTestCase(
        query="cerca offerta Samsung Galaxy",
        expected_domains=["web_search"],  # Should redirect from shopping
        expected_tools=["web_search"],
        complexity="simple",
        notes="Product search should redirect",
    ),
]


# =============================================================================
# PRODUCTIVITY Domain Tests (should redirect to web_search)
# =============================================================================
PRODUCTIVITY_CASES = [
    GoldenTestCase(
        query="crea nota promemoria",
        expected_domains=["web_search"],  # Should redirect if no real tools
        expected_tools=["web_search"],
        complexity="simple",
        notes="Note-taking query",
    ),
]


# =============================================================================
# COMPLEX/MULTI-DOMAIN Tests
# =============================================================================
COMPLEX_CASES = [
    GoldenTestCase(
        query="voglio investire in crypto e sapere il meteo a Roma",
        expected_domains=["finance_crypto", "geo_weather"],
        expected_tools=[],
        complexity="complex",
        notes="Multi-domain query",
    ),
    GoldenTestCase(
        query="prenota volo e hotel per weekend a Parigi e cercca ristorante",
        expected_domains=["travel", "food"],
        expected_tools=[],
        complexity="complex",
        notes="Three-domain query",
    ),
]


# =============================================================================
# COMPLETE GOLDEN SET
# =============================================================================

GOLDEN_SET: list[GoldenTestCase] = (
    GEO_WEATHER_CASES
    + FINANCE_CRYPTO_CASES
    + SPORTS_NBA_CASES
    + WEB_SEARCH_CASES
    + GOOGLE_WORKSPACE_CASES
    + FOOD_CASES
    + TRAVEL_CASES
    + SPORTS_BOOKING_CASES
    + SCIENCE_RESEARCH_CASES
    + MEDICAL_CASES
    + ENTERTAINMENT_CASES
    + KNOWLEDGE_MEDIA_CASES
    + TECH_CODING_CASES
    + JOBS_CASES
    + SHOPPING_CASES
    + PRODUCTIVITY_CASES
    + COMPLEX_CASES
)


# =============================================================================
# GOLDEN SET METADATA
# =============================================================================

GOLDEN_SET_STATS = {
    "total_cases": len(GOLDEN_SET),
    "by_domain": {
        "geo_weather": len(GEO_WEATHER_CASES),
        "finance_crypto": len(FINANCE_CRYPTO_CASES),
        "sports_nba": len(SPORTS_NBA_CASES),
        "web_search": len(WEB_SEARCH_CASES),
        "google_workspace": len(GOOGLE_WORKSPACE_CASES),
        "food": len(FOOD_CASES),
        "travel": len(TRAVEL_CASES),
        "sports_booking": len(SPORTS_BOOKING_CASES),
        "science_research": len(SCIENCE_RESEARCH_CASES),
        "medical": len(MEDICAL_CASES),
        "entertainment": len(ENTERTAINMENT_CASES),
        "knowledge_media": len(KNOWLEDGE_MEDIA_CASES),
        "tech_coding": len(TECH_CODING_CASES),
        "jobs": len(JOBS_CASES),
        "shopping": len(SHOPPING_CASES),
        "productivity": len(PRODUCTIVITY_CASES),
        "complex": len(COMPLEX_CASES),
    },
    "by_complexity": {
        "simple": sum(1 for c in GOLDEN_SET if c.complexity == "simple"),
        "medium": sum(1 for c in GOLDEN_SET if c.complexity == "medium"),
        "complex": sum(1 for c in GOLDEN_SET if c.complexity == "complex"),
    },
}
