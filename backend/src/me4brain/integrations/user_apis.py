"""User API Wrappers.

Custom wrappers for APIs that use the user's harvested keys:
- FRED (Federal Reserve Economic Data)
- PubMed (NCBI E-utilities)
- BallDontLie (NBA Stats)
- The Odds API (Betting Odds)
"""

import os
from pathlib import Path
from typing import Any

import httpx
import structlog
from dotenv import load_dotenv

logger = structlog.get_logger(__name__)

# Load harvested keys
HARVESTED_KEYS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "harvested_keys.env"
if HARVESTED_KEYS_PATH.exists():
    load_dotenv(HARVESTED_KEYS_PATH)


class FREDService:
    """Federal Reserve Economic Data API wrapper.

    Provides access to 800k+ economic time series from FRED.
    Docs: https://fred.stlouisfed.org/docs/api/fred/
    """

    BASE_URL = "https://api.stlouisfed.org/fred"
    API_KEY = os.getenv("API_STORE_FRED_KEY")

    async def search_series(
        self,
        search_text: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search for economic data series.

        Args:
            search_text: Search query (e.g., "GDP", "unemployment rate")
            limit: Max results to return
        """
        if not self.API_KEY:
            return {"error": "FRED API key not configured"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/series/search",
                params={
                    "api_key": self.API_KEY,
                    "file_type": "json",
                    "search_text": search_text,
                    "limit": limit,
                },
            )
            return response.json()

    async def get_series_observations(
        self,
        series_id: str,
        observation_start: str | None = None,
        observation_end: str | None = None,
    ) -> dict[str, Any]:
        """Get observations for a specific series.

        Args:
            series_id: FRED series ID (e.g., "GDP", "UNRATE")
            observation_start: Start date (YYYY-MM-DD)
            observation_end: End date (YYYY-MM-DD)
        """
        if not self.API_KEY:
            return {"error": "FRED API key not configured"}

        params = {
            "api_key": self.API_KEY,
            "file_type": "json",
            "series_id": series_id,
        }
        if observation_start:
            params["observation_start"] = observation_start
        if observation_end:
            params["observation_end"] = observation_end

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/series/observations",
                params=params,
            )
            return response.json()

    async def get_series_info(self, series_id: str) -> dict[str, Any]:
        """Get metadata for a series."""
        if not self.API_KEY:
            return {"error": "FRED API key not configured"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/series",
                params={
                    "api_key": self.API_KEY,
                    "file_type": "json",
                    "series_id": series_id,
                },
            )
            return response.json()


class PubMedService:
    """NCBI PubMed E-utilities API wrapper.

    Access 35M+ biomedical literature citations.
    Docs: https://www.ncbi.nlm.nih.gov/books/NBK25500/
    """

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    API_KEY = os.getenv("API_STORE_PUBMED_KEY")
    TOOL_NAME = os.getenv("API_STORE_PUBMED_TOOL_NAME_KEY", "Me4BrAIn")
    EMAIL = os.getenv("API_STORE_PUBMED_EMAIL_KEY", "")

    async def search(
        self,
        query: str,
        max_results: int = 20,
        sort: str = "relevance",
    ) -> dict[str, Any]:
        """Search PubMed for articles.

        Args:
            query: PubMed search query
            max_results: Maximum number of results
            sort: Sort order (relevance, pub_date)
        """
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "sort": sort,
            "retmode": "json",
            "tool": self.TOOL_NAME,
            "email": self.EMAIL,
        }
        if self.API_KEY:
            params["api_key"] = self.API_KEY

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/esearch.fcgi",
                params=params,
            )
            return response.json()

    async def fetch_abstracts(
        self,
        pmids: list[str],
    ) -> dict[str, Any]:
        """Fetch article details including abstracts.

        Args:
            pmids: List of PubMed IDs
        """
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "json",
            "rettype": "abstract",
            "tool": self.TOOL_NAME,
            "email": self.EMAIL,
        }
        if self.API_KEY:
            params["api_key"] = self.API_KEY

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/efetch.fcgi",
                params=params,
            )
            # efetch returns XML by default for pubmed
            return {"content": response.text}

    async def get_article_summary(self, pmid: str) -> dict[str, Any]:
        """Get summary for a single article."""
        params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "json",
            "tool": self.TOOL_NAME,
            "email": self.EMAIL,
        }
        if self.API_KEY:
            params["api_key"] = self.API_KEY

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/esummary.fcgi",
                params=params,
            )
            return response.json()


class BallDontLieService:
    """NBA Stats API wrapper via BallDontLie.

    Docs: https://www.balldontlie.io/
    """

    BASE_URL = "https://api.balldontlie.io/v1"
    API_KEY = os.getenv("API_STORE_BALLDONTLIE_KEY")

    def _headers(self) -> dict[str, str]:
        if self.API_KEY:
            return {"Authorization": self.API_KEY}
        return {}

    async def get_players(
        self,
        search: str | None = None,
        per_page: int = 25,
    ) -> dict[str, Any]:
        """Search NBA players."""
        params = {"per_page": per_page}
        if search:
            params["search"] = search

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/players",
                params=params,
                headers=self._headers(),
            )
            return response.json()

    async def get_player_stats(
        self,
        player_id: int,
        season: int | None = None,
    ) -> dict[str, Any]:
        """Get stats for a player."""
        params = {"player_ids[]": player_id}
        if season:
            params["seasons[]"] = season

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/season_averages",
                params=params,
                headers=self._headers(),
            )
            return response.json()

    async def get_games(
        self,
        team_id: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """Get NBA games."""
        params = {}
        if team_id:
            params["team_ids[]"] = team_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/games",
                params=params,
                headers=self._headers(),
            )
            return response.json()


class OddsAPIService:
    """The Odds API wrapper for sports betting odds.

    Docs: https://the-odds-api.com/
    """

    BASE_URL = "https://api.the-odds-api.com/v4"
    API_KEY = os.getenv("API_STORE_ODDS_API_KEY")

    async def get_sports(self) -> dict[str, Any]:
        """List available sports."""
        if not self.API_KEY:
            return {"error": "Odds API key not configured"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/sports",
                params={"apiKey": self.API_KEY},
            )
            return response.json()

    async def get_odds(
        self,
        sport: str = "basketball_nba",
        regions: str = "us",
        markets: str = "h2h,spreads",
    ) -> dict[str, Any]:
        """Get odds for a sport.

        Args:
            sport: Sport key (e.g., basketball_nba, americanfootball_nfl)
            regions: Region filter (us, uk, eu, au)
            markets: Markets to fetch (h2h, spreads, totals)
        """
        if not self.API_KEY:
            return {"error": "Odds API key not configured"}

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/sports/{sport}/odds",
                params={
                    "apiKey": self.API_KEY,
                    "regions": regions,
                    "markets": markets,
                },
            )
            return response.json()


# =========================================================================
# TOOL DEFINITIONS FOR API STORE
# =========================================================================

USER_API_TOOLS = [
    # FRED
    {
        "name": "fred_search_series",
        "description": "Search FRED (Federal Reserve Economic Data) for economic time series. Returns series IDs, titles, and metadata.",
        "service": "FREDService",
        "method": "search_series",
        "parameters": {
            "search_text": {
                "type": "string",
                "required": True,
                "description": "Search query (e.g., 'GDP', 'inflation')",
            },
            "limit": {"type": "integer", "default": 20},
        },
    },
    {
        "name": "fred_get_observations",
        "description": "Get historical data points for a FRED economic series.",
        "service": "FREDService",
        "method": "get_series_observations",
        "parameters": {
            "series_id": {
                "type": "string",
                "required": True,
                "description": "FRED series ID (e.g., 'GDP', 'UNRATE')",
            },
            "observation_start": {"type": "string", "description": "Start date YYYY-MM-DD"},
            "observation_end": {"type": "string", "description": "End date YYYY-MM-DD"},
        },
    },
    # PubMed
    {
        "name": "pubmed_search",
        "description": "Search PubMed for biomedical literature. Returns article IDs and counts.",
        "service": "PubMedService",
        "method": "search",
        "parameters": {
            "query": {"type": "string", "required": True, "description": "PubMed search query"},
            "max_results": {"type": "integer", "default": 20},
        },
    },
    {
        "name": "pubmed_get_abstracts",
        "description": "Retrieve article abstracts and details from PubMed.",
        "service": "PubMedService",
        "method": "fetch_abstracts",
        "parameters": {
            "pmids": {"type": "array", "items": {"type": "string"}, "required": True},
        },
    },
    # NBA
    {
        "name": "nba_search_players",
        "description": "Search NBA players by name using BallDontLie API.",
        "service": "BallDontLieService",
        "method": "get_players",
        "parameters": {
            "search": {"type": "string", "description": "Player name to search"},
            "per_page": {"type": "integer", "default": 25},
        },
    },
    {
        "name": "nba_player_stats",
        "description": "Get season statistics for an NBA player.",
        "service": "BallDontLieService",
        "method": "get_player_stats",
        "parameters": {
            "player_id": {"type": "integer", "required": True},
            "season": {"type": "integer", "description": "Season year (e.g., 2024)"},
        },
    },
    {
        "name": "nba_get_games",
        "description": "Get NBA game schedules and scores.",
        "service": "BallDontLieService",
        "method": "get_games",
        "parameters": {
            "team_id": {"type": "integer"},
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
        },
    },
    # Odds
    {
        "name": "odds_get_sports",
        "description": "List available sports for betting odds.",
        "service": "OddsAPIService",
        "method": "get_sports",
        "parameters": {},
    },
    {
        "name": "odds_get_odds",
        "description": "Get betting odds for a specific sport (NBA, NFL, etc.).",
        "service": "OddsAPIService",
        "method": "get_odds",
        "parameters": {
            "sport": {"type": "string", "default": "basketball_nba"},
            "regions": {"type": "string", "default": "us"},
            "markets": {"type": "string", "default": "h2h,spreads"},
        },
    },
]


# Singleton instances
_fred_service: FREDService | None = None
_pubmed_service: PubMedService | None = None
_balldontlie_service: BallDontLieService | None = None
_odds_service: OddsAPIService | None = None


def get_fred_service() -> FREDService:
    global _fred_service
    if _fred_service is None:
        _fred_service = FREDService()
    return _fred_service


def get_pubmed_service() -> PubMedService:
    global _pubmed_service
    if _pubmed_service is None:
        _pubmed_service = PubMedService()
    return _pubmed_service


def get_balldontlie_service() -> BallDontLieService:
    global _balldontlie_service
    if _balldontlie_service is None:
        _balldontlie_service = BallDontLieService()
    return _balldontlie_service


def get_odds_service() -> OddsAPIService:
    global _odds_service
    if _odds_service is None:
        _odds_service = OddsAPIService()
    return _odds_service
