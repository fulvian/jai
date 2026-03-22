"""Public Free APIs - No Auth Required.

Wrappers for APIs that require NO API key:
- Web & Testing: DuckDuckGo, httpbin
- Finance: CoinGecko, Yahoo Finance
- Science: ArXiv, Crossref, Europe PMC, OpenAlex, Semantic Scholar
- Knowledge: Wikipedia, Wikidata, Open Library, Gutenberg, HackerNews
- Geo: Open-Meteo, Nominatim, RestCountries, Sunrise-Sunset, USGS Earthquake
- Utility: IPify, RandomUser, Agify/Genderize
"""

import asyncio
from typing import Any
from urllib.parse import quote_plus

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Shared async client settings
DEFAULT_TIMEOUT = 30.0
USER_AGENT = "Me4BrAIn/2.0 (AI Research Platform; contact@me4brain.ai)"


# =============================================================================
# WEB & TESTING
# =============================================================================


class DuckDuckGoService:
    """DuckDuckGo Instant Answers API (no search)."""

    BASE_URL = "https://api.duckduckgo.com"

    async def instant_answer(self, query: str) -> dict[str, Any]:
        """Get instant answer for a query."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.BASE_URL,
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            return response.json()


class HttpbinService:
    """httpbin.org - HTTP testing service."""

    BASE_URL = "https://httpbin.org"

    async def get_ip(self) -> dict[str, Any]:
        """Get current IP address."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/ip")
            return response.json()

    async def get_headers(self) -> dict[str, Any]:
        """Get request headers."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/headers")
            return response.json()

    async def post_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Post data and see echo."""
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{self.BASE_URL}/post", json=data)
            return response.json()


# =============================================================================
# FINANCE (No Auth)
# =============================================================================


class CoinGeckoService:
    """CoinGecko - Free crypto market data."""

    BASE_URL = "https://api.coingecko.com/api/v3"

    async def get_price(
        self,
        ids: str = "bitcoin,ethereum",
        vs_currencies: str = "usd,eur",
    ) -> dict[str, Any]:
        """Get current prices for coins."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/simple/price",
                params={"ids": ids, "vs_currencies": vs_currencies, "include_24hr_change": "true"},
            )
            return response.json()

    async def get_coin_list(self) -> list[dict[str, Any]]:
        """Get list of all coins."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/coins/list")
            return response.json()

    async def get_coin_info(self, coin_id: str) -> dict[str, Any]:
        """Get detailed coin info."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/coins/{coin_id}",
                params={"localization": "false", "tickers": "false", "community_data": "false"},
            )
            return response.json()

    async def get_market_chart(
        self,
        coin_id: str = "bitcoin",
        vs_currency: str = "usd",
        days: int = 30,
    ) -> dict[str, Any]:
        """Get historical price data."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/coins/{coin_id}/market_chart",
                params={"vs_currency": vs_currency, "days": days},
            )
            return response.json()

    async def get_trending(self) -> dict[str, Any]:
        """Get trending coins."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/search/trending")
            return response.json()


# =============================================================================
# SCIENCE & RESEARCH (No Auth)
# =============================================================================


class ArXivService:
    """ArXiv preprint server API."""

    BASE_URL = "http://export.arxiv.org/api/query"

    async def search(
        self,
        query: str,
        start: int = 0,
        max_results: int = 20,
    ) -> str:
        """Search arXiv papers. Returns Atom XML."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(
                self.BASE_URL,
                params={
                    "search_query": f"all:{query}",
                    "start": start,
                    "max_results": max_results,
                    "sortBy": "relevance",
                },
            )
            return response.text  # Returns Atom XML


class CrossrefService:
    """Crossref DOI metadata API."""

    BASE_URL = "https://api.crossref.org/works"

    async def search(
        self,
        query: str,
        rows: int = 20,
    ) -> dict[str, Any]:
        """Search for works."""
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(
                self.BASE_URL,
                params={"query": query, "rows": rows},
            )
            return response.json()

    async def get_by_doi(self, doi: str) -> dict[str, Any]:
        """Get work by DOI."""
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(f"{self.BASE_URL}/{quote_plus(doi)}")
            return response.json()


class EuropePMCService:
    """Europe PMC - Life sciences literature."""

    BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"

    async def search(
        self,
        query: str,
        result_type: str = "core",
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Search Europe PMC."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{self.BASE_URL}/search",
                params={
                    "query": query,
                    "resultType": result_type,
                    "pageSize": page_size,
                    "format": "json",
                },
            )
            return response.json()


class OpenAlexService:
    """OpenAlex - Open research knowledge graph."""

    BASE_URL = "https://api.openalex.org"

    async def search_works(
        self,
        query: str,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """Search for academic works."""
        async with httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT}
        ) as client:
            response = await client.get(
                f"{self.BASE_URL}/works",
                params={"search": query, "per_page": per_page},
            )
            return response.json()

    async def get_author(self, author_id: str) -> dict[str, Any]:
        """Get author by OpenAlex ID."""
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(f"{self.BASE_URL}/authors/{author_id}")
            return response.json()

    async def search_authors(self, query: str, per_page: int = 10) -> dict[str, Any]:
        """Search for authors."""
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(
                f"{self.BASE_URL}/authors",
                params={"search": query, "per_page": per_page},
            )
            return response.json()


class SemanticScholarService:
    """Semantic Scholar Academic Graph API."""

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    async def search_papers(
        self,
        query: str,
        limit: int = 20,
        fields: str = "title,authors,year,abstract,citationCount",
    ) -> dict[str, Any]:
        """Search for papers."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(
                f"{self.BASE_URL}/paper/search",
                params={"query": query, "limit": limit, "fields": fields},
            )
            return response.json()

    async def get_paper(
        self,
        paper_id: str,
        fields: str = "title,authors,year,abstract,citationCount,references",
    ) -> dict[str, Any]:
        """Get paper by ID (S2 ID, DOI, ArXiv, etc.)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/paper/{paper_id}",
                params={"fields": fields},
            )
            return response.json()


# =============================================================================
# KNOWLEDGE & LITERATURE
# =============================================================================


class WikipediaService:
    """Wikipedia REST API."""

    BASE_URL = "https://en.wikipedia.org/api/rest_v1"

    async def get_summary(self, title: str) -> dict[str, Any]:
        """Get article summary."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/page/summary/{quote_plus(title)}")
            return response.json()

    async def search(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Search Wikipedia."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": limit,
                    "format": "json",
                },
            )
            return response.json()


class OpenLibraryService:
    """Open Library - Books metadata."""

    BASE_URL = "https://openlibrary.org"

    async def search_books(self, query: str, limit: int = 20) -> dict[str, Any]:
        """Search for books."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/search.json",
                params={"q": query, "limit": limit},
            )
            return response.json()

    async def get_book_by_isbn(self, isbn: str) -> dict[str, Any]:
        """Get book by ISBN."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/isbn/{isbn}.json")
            return response.json()


class HackerNewsService:
    """Hacker News Firebase API."""

    BASE_URL = "https://hacker-news.firebaseio.com/v0"

    async def get_top_stories(self, limit: int = 30) -> list[int]:
        """Get top story IDs."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/topstories.json")
            return response.json()[:limit]

    async def get_item(self, item_id: int) -> dict[str, Any]:
        """Get item (story, comment, etc.)."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/item/{item_id}.json")
            return response.json()

    async def get_top_stories_full(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get top stories with full details."""
        ids = await self.get_top_stories(limit)
        stories = []
        for item_id in ids:
            story = await self.get_item(item_id)
            if story:
                stories.append(story)
        return stories


# =============================================================================
# GEO, WEATHER & ENVIRONMENT
# =============================================================================


class OpenMeteoService:
    """Open-Meteo - Free weather API."""

    BASE_URL = "https://api.open-meteo.com/v1"

    async def get_weather(
        self,
        latitude: float,
        longitude: float,
        current: str = "temperature_2m,wind_speed_10m,relative_humidity_2m",
    ) -> dict[str, Any]:
        """Get current weather."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": current,
                },
            )
            return response.json()

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ) -> dict[str, Any]:
        """Get weather forecast."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                    "forecast_days": days,
                },
            )
            return response.json()


class NominatimService:
    """OpenStreetMap Nominatim geocoding."""

    BASE_URL = "https://nominatim.openstreetmap.org"

    async def geocode(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Geocode an address."""
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(
                f"{self.BASE_URL}/search",
                params={"q": query, "format": "json", "limit": limit},
            )
            return response.json()

    async def reverse_geocode(self, lat: float, lon: float) -> dict[str, Any]:
        """Reverse geocode coordinates."""
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
            response = await client.get(
                f"{self.BASE_URL}/reverse",
                params={"lat": lat, "lon": lon, "format": "json"},
            )
            return response.json()


class RestCountriesService:
    """REST Countries API."""

    BASE_URL = "https://restcountries.com/v3.1"

    async def get_all(self) -> list[dict[str, Any]]:
        """Get all countries."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/all")
            return response.json()

    async def get_by_name(self, name: str) -> list[dict[str, Any]]:
        """Get country by name."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/name/{quote_plus(name)}")
            return response.json()

    async def get_by_code(self, code: str) -> dict[str, Any]:
        """Get country by ISO code."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/alpha/{code}")
            return response.json()


class SunriseSunsetService:
    """Sunrise-Sunset API."""

    BASE_URL = "https://api.sunrise-sunset.org/json"

    async def get_times(self, lat: float, lng: float, date: str = "today") -> dict[str, Any]:
        """Get sunrise/sunset times."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.BASE_URL,
                params={"lat": lat, "lng": lng, "date": date, "formatted": 0},
            )
            return response.json()


class USGSEarthquakeService:
    """USGS Earthquake Catalog API."""

    BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1"

    async def get_recent(
        self,
        min_magnitude: float = 4.0,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Get recent earthquakes."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/query",
                params={
                    "format": "geojson",
                    "minmagnitude": min_magnitude,
                    "limit": limit,
                    "orderby": "time",
                },
            )
            return response.json()


class NagerDateService:
    """Nager.Date - Public holidays API."""

    BASE_URL = "https://date.nager.at/api/v3"

    async def get_holidays(self, year: int, country_code: str = "IT") -> list[dict[str, Any]]:
        """Get public holidays for a country."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/PublicHolidays/{year}/{country_code}")
            return response.json()

    async def get_available_countries(self) -> list[dict[str, Any]]:
        """Get available countries."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/AvailableCountries")
            return response.json()


# =============================================================================
# UTILITY & MISC
# =============================================================================


class IPifyService:
    """IPify - Public IP lookup."""

    async def get_ip(self) -> dict[str, str]:
        """Get public IP address."""
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.ipify.org?format=json")
            return response.json()


class RandomUserService:
    """RandomUser.me - Generate random user data."""

    BASE_URL = "https://randomuser.me/api"

    async def get_users(
        self,
        results: int = 10,
        nationality: str | None = None,
    ) -> dict[str, Any]:
        """Get random users."""
        params = {"results": results}
        if nationality:
            params["nat"] = nationality
        async with httpx.AsyncClient() as client:
            response = await client.get(self.BASE_URL, params=params)
            return response.json()


class AgifyService:
    """Agify.io - Predict age from name."""

    async def predict_age(self, name: str, country_id: str | None = None) -> dict[str, Any]:
        """Predict age for a name."""
        params = {"name": name}
        if country_id:
            params["country_id"] = country_id
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.agify.io", params=params)
            return response.json()


class GenderizeService:
    """Genderize.io - Predict gender from name."""

    async def predict_gender(self, name: str, country_id: str | None = None) -> dict[str, Any]:
        """Predict gender for a name."""
        params = {"name": name}
        if country_id:
            params["country_id"] = country_id
        async with httpx.AsyncClient() as client:
            response = await client.get("https://api.genderize.io", params=params)
            return response.json()


# =============================================================================
# SPORTS - NBA (Free via nba_api library)
# =============================================================================


class NBAStatsService:
    """NBA Stats API - Free access to NBA statistics via nba_api library.

    Uses the nba_api Python package (pip install nba_api) which provides
    free access to NBA.com stats without requiring an API key.

    Pattern follows nba-predictor-streamlit:
    - nba_api for stats/historical data
    - BallDontLie for scheduling (separate service)
    """

    async def get_player_career_stats(self, player_id: int) -> dict[str, Any]:
        """Get career statistics for a player."""
        try:
            from nba_api.stats.endpoints import playercareerstats

            # Run sync API call in thread pool
            def fetch():
                career = playercareerstats.PlayerCareerStats(player_id=player_id)
                return career.get_normalized_dict()

            result = await asyncio.get_event_loop().run_in_executor(None, fetch)
            return {
                "player_id": player_id,
                "career_totals": result.get("CareerTotalsRegularSeason", []),
                "season_totals": result.get("SeasonTotalsRegularSeason", []),
                "source": "NBA Stats API (nba_api)",
            }
        except ImportError:
            return {"error": "nba_api not installed. Run: pip install nba_api"}
        except Exception as e:
            return {"error": str(e), "player_id": player_id}

    async def search_players(self, query: str) -> dict[str, Any]:
        """Search for NBA players by name."""
        try:
            from nba_api.stats.static import players

            all_players = players.get_players()
            query_lower = query.lower()
            matches = [p for p in all_players if query_lower in p["full_name"].lower()][
                :20
            ]  # Limit to 20 results

            return {
                "query": query,
                "count": len(matches),
                "players": matches,
                "source": "NBA Stats API (nba_api)",
            }
        except ImportError:
            return {"error": "nba_api not installed. Run: pip install nba_api"}
        except Exception as e:
            return {"error": str(e)}

    async def get_team_roster(self, team_id: int, season: str = "2024-25") -> dict[str, Any]:
        """Get team roster for a season."""
        try:
            from nba_api.stats.endpoints import commonteamroster

            def fetch():
                roster = commonteamroster.CommonTeamRoster(team_id=team_id, season=season)
                return roster.get_normalized_dict()

            result = await asyncio.get_event_loop().run_in_executor(None, fetch)
            return {
                "team_id": team_id,
                "season": season,
                "roster": result.get("CommonTeamRoster", []),
                "coaches": result.get("Coaches", []),
                "source": "NBA Stats API (nba_api)",
            }
        except ImportError:
            return {"error": "nba_api not installed. Run: pip install nba_api"}
        except Exception as e:
            return {"error": str(e), "team_id": team_id}

    async def get_teams(self) -> dict[str, Any]:
        """Get all NBA teams."""
        try:
            from nba_api.stats.static import teams

            all_teams = teams.get_teams()
            return {
                "count": len(all_teams),
                "teams": all_teams,
                "source": "NBA Stats API (nba_api)",
            }
        except ImportError:
            return {"error": "nba_api not installed. Run: pip install nba_api"}
        except Exception as e:
            return {"error": str(e)}

    async def get_game_boxscore(self, game_id: str) -> dict[str, Any]:
        """Get boxscore for a specific game."""
        try:
            from nba_api.stats.endpoints import boxscoretraditionalv2

            def fetch():
                boxscore = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
                return boxscore.get_normalized_dict()

            result = await asyncio.get_event_loop().run_in_executor(None, fetch)
            return {
                "game_id": game_id,
                "player_stats": result.get("PlayerStats", []),
                "team_stats": result.get("TeamStats", []),
                "source": "NBA Stats API (nba_api)",
            }
        except ImportError:
            return {"error": "nba_api not installed. Run: pip install nba_api"}
        except Exception as e:
            return {"error": str(e), "game_id": game_id}

    async def get_live_scoreboard(self) -> dict[str, Any]:
        """Get today's live scoreboard."""
        try:
            from nba_api.live.nba.endpoints import scoreboard

            def fetch():
                board = scoreboard.ScoreBoard()
                return board.get_dict()

            result = await asyncio.get_event_loop().run_in_executor(None, fetch)
            games = result.get("scoreboard", {}).get("games", [])
            return {
                "game_date": result.get("scoreboard", {}).get("gameDate", ""),
                "games_count": len(games),
                "games": games,
                "source": "NBA Live API (nba_api)",
            }
        except ImportError:
            return {"error": "nba_api not installed. Run: pip install nba_api"}
        except Exception as e:
            return {"error": str(e)}


# =============================================================================
# TOOL DEFINITIONS FOR API STORE
# =============================================================================

PUBLIC_API_TOOLS = [
    # Web & Testing
    {
        "name": "duckduckgo_instant",
        "description": "Get instant answers from DuckDuckGo",
        "service": "DuckDuckGoService",
        "method": "instant_answer",
        "parameters": {"query": {"type": "string", "required": True}},
    },
    {
        "name": "httpbin_ip",
        "description": "Get current public IP address via httpbin",
        "service": "HttpbinService",
        "method": "get_ip",
        "parameters": {},
    },
    # Finance - Crypto
    {
        "name": "coingecko_price",
        "description": "Get cryptocurrency prices (Bitcoin, Ethereum, etc.)",
        "service": "CoinGeckoService",
        "method": "get_price",
        "parameters": {
            "ids": {"type": "string", "default": "bitcoin,ethereum"},
            "vs_currencies": {"type": "string", "default": "usd"},
        },
    },
    {
        "name": "coingecko_trending",
        "description": "Get trending cryptocurrencies",
        "service": "CoinGeckoService",
        "method": "get_trending",
        "parameters": {},
    },
    {
        "name": "coingecko_chart",
        "description": "Get historical price chart for a coin",
        "service": "CoinGeckoService",
        "method": "get_market_chart",
        "parameters": {
            "coin_id": {"type": "string", "required": True},
            "days": {"type": "integer", "default": 30},
        },
    },
    # Science
    {
        "name": "arxiv_search",
        "description": "Search arXiv preprints (CS, Math, Physics)",
        "service": "ArXivService",
        "method": "search",
        "parameters": {
            "query": {"type": "string", "required": True},
            "max_results": {"type": "integer", "default": 20},
        },
    },
    {
        "name": "crossref_search",
        "description": "Search Crossref for academic papers by DOI/metadata",
        "service": "CrossrefService",
        "method": "search",
        "parameters": {"query": {"type": "string", "required": True}},
    },
    {
        "name": "crossref_doi",
        "description": "Get paper metadata by DOI",
        "service": "CrossrefService",
        "method": "get_by_doi",
        "parameters": {"doi": {"type": "string", "required": True}},
    },
    {
        "name": "europepmc_search",
        "description": "Search Europe PMC for life sciences papers",
        "service": "EuropePMCService",
        "method": "search",
        "parameters": {"query": {"type": "string", "required": True}},
    },
    {
        "name": "openalex_works",
        "description": "Search OpenAlex academic knowledge graph",
        "service": "OpenAlexService",
        "method": "search_works",
        "parameters": {"query": {"type": "string", "required": True}},
    },
    {
        "name": "openalex_authors",
        "description": "Search for academic authors in OpenAlex",
        "service": "OpenAlexService",
        "method": "search_authors",
        "parameters": {"query": {"type": "string", "required": True}},
    },
    {
        "name": "semantic_scholar_search",
        "description": "Search Semantic Scholar for papers",
        "service": "SemanticScholarService",
        "method": "search_papers",
        "parameters": {"query": {"type": "string", "required": True}},
    },
    {
        "name": "semantic_scholar_paper",
        "description": "Get paper details from Semantic Scholar",
        "service": "SemanticScholarService",
        "method": "get_paper",
        "parameters": {"paper_id": {"type": "string", "required": True}},
    },
    # Knowledge
    {
        "name": "wikipedia_summary",
        "description": "Get Wikipedia article summary",
        "service": "WikipediaService",
        "method": "get_summary",
        "parameters": {"title": {"type": "string", "required": True}},
    },
    {
        "name": "wikipedia_search",
        "description": "Search Wikipedia articles",
        "service": "WikipediaService",
        "method": "search",
        "parameters": {"query": {"type": "string", "required": True}},
    },
    {
        "name": "openlibrary_search",
        "description": "Search for books in Open Library",
        "service": "OpenLibraryService",
        "method": "search_books",
        "parameters": {"query": {"type": "string", "required": True}},
    },
    {
        "name": "openlibrary_isbn",
        "description": "Get book by ISBN from Open Library",
        "service": "OpenLibraryService",
        "method": "get_book_by_isbn",
        "parameters": {"isbn": {"type": "string", "required": True}},
    },
    {
        "name": "hackernews_top",
        "description": "Get top Hacker News stories",
        "service": "HackerNewsService",
        "method": "get_top_stories_full",
        "parameters": {"limit": {"type": "integer", "default": 10}},
    },
    # Geo & Weather
    {
        "name": "openmeteo_weather",
        "description": "Get current weather for coordinates",
        "service": "OpenMeteoService",
        "method": "get_weather",
        "parameters": {
            "latitude": {"type": "number", "required": True},
            "longitude": {"type": "number", "required": True},
        },
    },
    {
        "name": "openmeteo_forecast",
        "description": "Get weather forecast for coordinates",
        "service": "OpenMeteoService",
        "method": "get_forecast",
        "parameters": {
            "latitude": {"type": "number", "required": True},
            "longitude": {"type": "number", "required": True},
            "days": {"type": "integer", "default": 7},
        },
    },
    {
        "name": "nominatim_geocode",
        "description": "Geocode address to coordinates (OpenStreetMap)",
        "service": "NominatimService",
        "method": "geocode",
        "parameters": {"query": {"type": "string", "required": True}},
    },
    {
        "name": "nominatim_reverse",
        "description": "Reverse geocode coordinates to address",
        "service": "NominatimService",
        "method": "reverse_geocode",
        "parameters": {
            "lat": {"type": "number", "required": True},
            "lon": {"type": "number", "required": True},
        },
    },
    {
        "name": "restcountries_name",
        "description": "Get country info by name",
        "service": "RestCountriesService",
        "method": "get_by_name",
        "parameters": {"name": {"type": "string", "required": True}},
    },
    {
        "name": "sunrise_sunset",
        "description": "Get sunrise and sunset times for location",
        "service": "SunriseSunsetService",
        "method": "get_times",
        "parameters": {
            "lat": {"type": "number", "required": True},
            "lng": {"type": "number", "required": True},
        },
    },
    {
        "name": "usgs_earthquakes",
        "description": "Get recent earthquakes from USGS",
        "service": "USGSEarthquakeService",
        "method": "get_recent",
        "parameters": {"min_magnitude": {"type": "number", "default": 4.0}},
    },
    {
        "name": "nagerdate_holidays",
        "description": "Get public holidays for a country",
        "service": "NagerDateService",
        "method": "get_holidays",
        "parameters": {
            "year": {"type": "integer", "required": True},
            "country_code": {"type": "string", "default": "IT"},
        },
    },
    # Utility
    {
        "name": "ipify_ip",
        "description": "Get your public IP address",
        "service": "IPifyService",
        "method": "get_ip",
        "parameters": {},
    },
    {
        "name": "randomuser_generate",
        "description": "Generate random fake user data",
        "service": "RandomUserService",
        "method": "get_users",
        "parameters": {"results": {"type": "integer", "default": 5}},
    },
    {
        "name": "agify_age",
        "description": "Predict age from a name",
        "service": "AgifyService",
        "method": "predict_age",
        "parameters": {"name": {"type": "string", "required": True}},
    },
    {
        "name": "genderize_gender",
        "description": "Predict gender from a name",
        "service": "GenderizeService",
        "method": "predict_gender",
        "parameters": {"name": {"type": "string", "required": True}},
    },
    # NBA Stats (Free via nba_api - no API key required)
    {
        "name": "nba_search_players",
        "description": "Search NBA players by name (free, no API key)",
        "service": "NBAStatsService",
        "method": "search_players",
        "parameters": {"query": {"type": "string", "required": True}},
    },
    {
        "name": "nba_player_career_stats",
        "description": "Get NBA player career statistics by player ID (free)",
        "service": "NBAStatsService",
        "method": "get_player_career_stats",
        "parameters": {"player_id": {"type": "integer", "required": True}},
    },
    {
        "name": "nba_teams",
        "description": "Get all NBA teams with IDs and info (free)",
        "service": "NBAStatsService",
        "method": "get_teams",
        "parameters": {},
    },
    {
        "name": "nba_team_roster",
        "description": "Get NBA team roster for a season (free)",
        "service": "NBAStatsService",
        "method": "get_team_roster",
        "parameters": {
            "team_id": {"type": "integer", "required": True},
            "season": {"type": "string", "default": "2024-25"},
        },
    },
    {
        "name": "nba_game_boxscore",
        "description": "Get NBA game boxscore with player/team stats (free)",
        "service": "NBAStatsService",
        "method": "get_game_boxscore",
        "parameters": {"game_id": {"type": "string", "required": True}},
    },
    {
        "name": "nba_live_scoreboard",
        "description": "Get today's NBA live scoreboard with game status (free)",
        "service": "NBAStatsService",
        "method": "get_live_scoreboard",
        "parameters": {},
    },
]


# Singleton instances
_services: dict[str, Any] = {}


def get_service(service_name: str) -> Any:
    """Get or create a service instance."""
    if service_name not in _services:
        service_class = globals().get(service_name)
        if service_class:
            _services[service_name] = service_class()
    return _services.get(service_name)
