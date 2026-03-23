"""Premium APIs - Require API Keys.

Wrappers for APIs that require API keys (free tier available):
- Finance: Alpha Vantage, Finnhub, Polygon.io
- Space: NASA APOD, NeoWs
- News: NewsData.io, Tavily
- Other: Abstract API
"""

import os
from pathlib import Path
from typing import Any

import httpx
import structlog
from dotenv import load_dotenv

logger = structlog.get_logger(__name__)

# Load .env from project root (backend/)
_project_root = Path(__file__).parent.parent.parent
load_dotenv(_project_root / ".env")


# =============================================================================
# FINANCE APIs
# =============================================================================


class AlphaVantageService:
    """Alpha Vantage - Stock, forex, crypto data (NASDAQ licensed)."""

    BASE_URL = "https://www.alphavantage.co/query"
    API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", os.getenv("API_STORE_ALPHAVANTAGE_KEY", ""))

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Get real-time stock quote."""
        if not self.API_KEY:
            return {"error": "Alpha Vantage API key not configured"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.BASE_URL,
                params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": self.API_KEY},
            )
            return response.json()

    async def get_daily(self, symbol: str, outputsize: str = "compact") -> dict[str, Any]:
        """Get daily time series."""
        if not self.API_KEY:
            return {"error": "Alpha Vantage API key not configured"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.BASE_URL,
                params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "outputsize": outputsize,
                    "apikey": self.API_KEY,
                },
            )
            return response.json()

    async def search_symbol(self, keywords: str) -> dict[str, Any]:
        """Search for stock symbols."""
        if not self.API_KEY:
            return {"error": "Alpha Vantage API key not configured"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.BASE_URL,
                params={"function": "SYMBOL_SEARCH", "keywords": keywords, "apikey": self.API_KEY},
            )
            return response.json()

    async def get_forex_rate(self, from_currency: str, to_currency: str) -> dict[str, Any]:
        """Get forex exchange rate."""
        if not self.API_KEY:
            return {"error": "Alpha Vantage API key not configured"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.BASE_URL,
                params={
                    "function": "CURRENCY_EXCHANGE_RATE",
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                    "apikey": self.API_KEY,
                },
            )
            return response.json()


class FinnhubService:
    """Finnhub - Real-time stock data and fundamentals."""

    BASE_URL = "https://finnhub.io/api/v1"
    API_KEY = os.getenv("FINNHUB_API_KEY", os.getenv("API_STORE_FINNHUB_KEY", ""))

    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """Get real-time quote."""
        if not self.API_KEY:
            return {"error": "Finnhub API key not configured"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/quote",
                params={"symbol": symbol, "token": self.API_KEY},
            )
            return response.json()

    async def get_company_profile(self, symbol: str) -> dict[str, Any]:
        """Get company profile."""
        if not self.API_KEY:
            return {"error": "Finnhub API key not configured"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/stock/profile2",
                params={"symbol": symbol, "token": self.API_KEY},
            )
            return response.json()

    async def get_news(self, category: str = "general") -> list[dict[str, Any]]:
        """Get market news."""
        if not self.API_KEY:
            return [{"error": "Finnhub API key not configured"}]
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/news",
                params={"category": category, "token": self.API_KEY},
            )
            return response.json()

    async def get_sentiment(self, symbol: str) -> dict[str, Any]:
        """Get social sentiment for symbol."""
        if not self.API_KEY:
            return {"error": "Finnhub API key not configured"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/stock/social-sentiment",
                params={"symbol": symbol, "token": self.API_KEY},
            )
            return response.json()


class PolygonService:
    """Polygon.io - Stock, crypto, forex data."""

    BASE_URL = "https://api.polygon.io"
    API_KEY = os.getenv("POLYGON_API_KEY", os.getenv("API_STORE_POLYGON_KEY", ""))

    async def get_ticker_details(self, ticker: str) -> dict[str, Any]:
        """Get ticker details."""
        if not self.API_KEY:
            return {"error": "Polygon API key not configured"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/v3/reference/tickers/{ticker}",
                params={"apiKey": self.API_KEY},
            )
            return response.json()

    async def get_previous_close(self, ticker: str) -> dict[str, Any]:
        """Get previous day's OHLC."""
        if not self.API_KEY:
            return {"error": "Polygon API key not configured"}
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/v2/aggs/ticker/{ticker}/prev",
                params={"apiKey": self.API_KEY},
            )
            return response.json()


# =============================================================================
# SPACE & NASA
# =============================================================================


class NASAService:
    """NASA APIs - APOD, NeoWs, etc."""

    BASE_URL = "https://api.nasa.gov"
    API_KEY = os.getenv("NASA_API_KEY", os.getenv("API_STORE_NASA_KEY", "DEMO_KEY"))

    async def get_apod(self, date: str | None = None) -> dict[str, Any]:
        """Get Astronomy Picture of the Day."""
        params = {"api_key": self.API_KEY}
        if date:
            params["date"] = date
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/planetary/apod", params=params)
            return response.json()

    async def get_neo_feed(self, start_date: str, end_date: str) -> dict[str, Any]:
        """Get Near Earth Objects for date range."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/neo/rest/v1/feed",
                params={
                    "start_date": start_date,
                    "end_date": end_date,
                    "api_key": self.API_KEY,
                },
            )
            return response.json()

    async def search_images(self, query: str) -> dict[str, Any]:
        """Search NASA Image and Video Library."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://images-api.nasa.gov/search",
                params={"q": query, "media_type": "image"},
            )
            return response.json()


# =============================================================================
# NEWS & SEARCH
# =============================================================================


class NewsDataService:
    """NewsData.io - News aggregator."""

    BASE_URL = "https://newsdata.io/api/1"
    API_KEY = os.getenv("NEWSDATA_API_KEY", os.getenv("API_STORE_NEWSDATA_KEY", ""))

    async def get_news(
        self,
        query: str | None = None,
        country: str = "it",
        language: str = "it,en",
        category: str | None = None,
    ) -> dict[str, Any]:
        """Get news articles."""
        if not self.API_KEY:
            return {"error": "NewsData API key not configured"}
        params = {"apikey": self.API_KEY, "country": country, "language": language}
        if query:
            params["q"] = query
        if category:
            params["category"] = category
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.BASE_URL}/news", params=params)
            return response.json()


class TavilyService:
    """Tavily - LLM-optimized search API."""

    BASE_URL = "https://api.tavily.com"
    API_KEY = os.getenv("TAVILY_API_KEY", os.getenv("API_STORE_TAVILY_KEY", ""))

    async def search(
        self,
        query: str,
        search_depth: str = "basic",
        include_answer: bool = True,
        max_results: int = 5,
    ) -> dict[str, Any]:
        """Search the web with LLM-optimized results."""
        if not self.API_KEY:
            return {"error": "Tavily API key not configured"}
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/search",
                json={
                    "api_key": self.API_KEY,
                    "query": query,
                    "search_depth": search_depth,
                    "include_answer": include_answer,
                    "max_results": max_results,
                },
            )
            return response.json()


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

PREMIUM_API_TOOLS = [
    # Alpha Vantage
    {
        "name": "alphavantage_quote",
        "description": "Get real-time stock quote from Alpha Vantage",
        "service": "AlphaVantageService",
        "method": "get_quote",
        "parameters": {
            "symbol": {
                "type": "string",
                "required": True,
                "description": "Stock symbol (e.g., AAPL, MSFT)",
            }
        },
    },
    {
        "name": "alphavantage_daily",
        "description": "Get daily stock price history",
        "service": "AlphaVantageService",
        "method": "get_daily",
        "parameters": {"symbol": {"type": "string", "required": True}},
    },
    {
        "name": "alphavantage_search",
        "description": "Search for stock symbols by company name",
        "service": "AlphaVantageService",
        "method": "search_symbol",
        "parameters": {"keywords": {"type": "string", "required": True}},
    },
    {
        "name": "alphavantage_forex",
        "description": "Get forex exchange rate",
        "service": "AlphaVantageService",
        "method": "get_forex_rate",
        "parameters": {
            "from_currency": {"type": "string", "required": True},
            "to_currency": {"type": "string", "required": True},
        },
    },
    # Finnhub
    {
        "name": "finnhub_quote",
        "description": "Get real-time stock quote from Finnhub",
        "service": "FinnhubService",
        "method": "get_quote",
        "parameters": {"symbol": {"type": "string", "required": True}},
    },
    {
        "name": "finnhub_company",
        "description": "Get company profile and info",
        "service": "FinnhubService",
        "method": "get_company_profile",
        "parameters": {"symbol": {"type": "string", "required": True}},
    },
    {
        "name": "finnhub_news",
        "description": "Get market news",
        "service": "FinnhubService",
        "method": "get_news",
        "parameters": {"category": {"type": "string", "default": "general"}},
    },
    {
        "name": "finnhub_sentiment",
        "description": "Get social sentiment for a stock",
        "service": "FinnhubService",
        "method": "get_sentiment",
        "parameters": {"symbol": {"type": "string", "required": True}},
    },
    # Polygon
    {
        "name": "polygon_ticker",
        "description": "Get ticker details from Polygon",
        "service": "PolygonService",
        "method": "get_ticker_details",
        "parameters": {"ticker": {"type": "string", "required": True}},
    },
    {
        "name": "polygon_close",
        "description": "Get previous day close price",
        "service": "PolygonService",
        "method": "get_previous_close",
        "parameters": {"ticker": {"type": "string", "required": True}},
    },
    # NASA
    {
        "name": "nasa_apod",
        "description": "Get NASA Astronomy Picture of the Day",
        "service": "NASAService",
        "method": "get_apod",
        "parameters": {"date": {"type": "string", "description": "Date YYYY-MM-DD (optional)"}},
    },
    {
        "name": "nasa_neo",
        "description": "Get Near Earth Objects for date range",
        "service": "NASAService",
        "method": "get_neo_feed",
        "parameters": {
            "start_date": {"type": "string", "required": True},
            "end_date": {"type": "string", "required": True},
        },
    },
    {
        "name": "nasa_images",
        "description": "Search NASA image library",
        "service": "NASAService",
        "method": "search_images",
        "parameters": {"query": {"type": "string", "required": True}},
    },
    # News & Search
    {
        "name": "newsdata_search",
        "description": "Search news from 85k+ sources",
        "service": "NewsDataService",
        "method": "get_news",
        "parameters": {"query": {"type": "string"}, "country": {"type": "string", "default": "it"}},
    },
    {
        "name": "tavily_search",
        "description": "LLM-optimized web search with Tavily",
        "service": "TavilyService",
        "method": "search",
        "parameters": {"query": {"type": "string", "required": True}},
    },
]


# Singletons
_premium_services: dict[str, Any] = {}


def get_premium_service(service_name: str) -> Any:
    """Get or create a premium service instance."""
    if service_name not in _premium_services:
        service_class = globals().get(service_name)
        if service_class:
            _premium_services[service_name] = service_class()
    return _premium_services.get(service_name)
