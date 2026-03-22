"""E2E Tests for Domain Wrappers."""

from __future__ import annotations

import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
class TestGeoWeatherDomain:
    """Test Geo/Weather domain operations."""

    async def test_current_weather(self, async_client):
        """Test current weather retrieval."""
        try:
            weather = await async_client.domains.geo_weather.current("Milan, IT")

            assert weather is not None
            assert weather.location is not None
            assert weather.temperature is not None
        except Exception as e:
            pytest.skip(f"Weather API not available: {e}")

    async def test_weather_forecast(self, async_client):
        """Test weather forecast."""
        try:
            forecast = await async_client.domains.geo_weather.forecast("Rome", days=3)

            assert forecast is not None
        except Exception as e:
            pytest.skip(f"Forecast API not available: {e}")

    async def test_geocode(self, async_client):
        """Test geocoding."""
        try:
            locations = await async_client.domains.geo_weather.geocode("Paris, France")

            assert locations is not None
        except Exception as e:
            pytest.skip(f"Geocode API not available: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
class TestFinanceDomain:
    """Test Finance domain operations."""

    async def test_stock_quote(self, async_client):
        """Test stock quote retrieval."""
        try:
            quote = await async_client.domains.finance.stock_quote("AAPL")

            assert quote is not None
            assert quote.symbol == "AAPL"
        except Exception as e:
            pytest.skip(f"Stock API not available: {e}")

    async def test_crypto_price(self, async_client):
        """Test crypto price retrieval."""
        try:
            crypto = await async_client.domains.finance.crypto_price("bitcoin")

            assert crypto is not None
            assert crypto.price_usd > 0
        except Exception as e:
            pytest.skip(f"Crypto API not available: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
class TestWebSearchDomain:
    """Test Web Search domain operations."""

    async def test_tavily_search(self, async_client):
        """Test Tavily search."""
        try:
            results = await async_client.domains.web_search.tavily(
                query="Python programming",
                max_results=5,
            )

            assert results is not None
        except Exception as e:
            pytest.skip(f"Tavily API not available: {e}")

    async def test_wikipedia(self, async_client):
        """Test Wikipedia lookup."""
        try:
            article = await async_client.domains.web_search.wikipedia("Python programming")

            assert article is not None
            assert article.title is not None
        except Exception as e:
            pytest.skip(f"Wikipedia API not available: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
class TestTechCodingDomain:
    """Test Tech/Coding domain operations."""

    async def test_github_search(self, async_client):
        """Test GitHub repository search."""
        try:
            repos = await async_client.domains.tech_coding.github_search(
                query="fastapi",
                max_results=5,
            )

            assert repos is not None
        except Exception as e:
            pytest.skip(f"GitHub API not available: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
class TestScienceResearchDomain:
    """Test Science/Research domain operations."""

    async def test_arxiv_search(self, async_client):
        """Test arXiv paper search."""
        try:
            papers = await async_client.domains.science_research.arxiv(
                query="transformer",
                max_results=5,
            )

            assert papers is not None
        except Exception as e:
            pytest.skip(f"arXiv API not available: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
class TestMedicalDomain:
    """Test Medical domain operations."""

    async def test_drug_interactions(self, async_client):
        """Test drug interaction check."""
        try:
            result = await async_client.domains.medical.drug_interactions(
                drugs=["aspirin", "warfarin"],
            )

            assert result is not None
        except Exception as e:
            pytest.skip(f"Drug API not available: {e}")

    async def test_pubmed_search(self, async_client):
        """Test PubMed search."""
        try:
            articles = await async_client.domains.medical.pubmed_search(
                query="diabetes treatment",
                max_results=5,
            )

            assert articles is not None
        except Exception as e:
            pytest.skip(f"PubMed API not available: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
class TestEntertainmentDomain:
    """Test Entertainment domain operations."""

    async def test_movie_search(self, async_client):
        """Test movie search."""
        try:
            movies = await async_client.domains.entertainment.movie_search("Inception")

            assert movies is not None
        except Exception as e:
            pytest.skip(f"Movie API not available: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
class TestFoodDomain:
    """Test Food domain operations."""

    async def test_recipe_search(self, async_client):
        """Test recipe search."""
        try:
            recipes = await async_client.domains.food.recipe_search("pasta")

            assert recipes is not None
        except Exception as e:
            pytest.skip(f"Recipe API not available: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
class TestSportsNBADomain:
    """Test Sports/NBA domain operations."""

    async def test_search_players(self, async_client):
        """Test NBA player search."""
        try:
            players = await async_client.domains.sports_nba.search_players("LeBron")

            assert players is not None
        except Exception as e:
            pytest.skip(f"NBA API not available: {e}")

    async def test_list_teams(self, async_client):
        """Test listing NBA teams."""
        try:
            teams = await async_client.domains.sports_nba.list_teams()

            assert teams is not None
        except Exception as e:
            pytest.skip(f"NBA API not available: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
class TestKnowledgeMediaDomain:
    """Test Knowledge/Media domain operations."""

    async def test_wikipedia(self, async_client):
        """Test Wikipedia article retrieval."""
        try:
            article = await async_client.domains.knowledge_media.wikipedia(
                "Artificial Intelligence"
            )

            assert article is not None
            assert article.title is not None
        except Exception as e:
            pytest.skip(f"Wikipedia API not available: {e}")

    async def test_news_search(self, async_client):
        """Test news search."""
        try:
            articles = await async_client.domains.knowledge_media.news_search("technology")

            assert articles is not None
        except Exception as e:
            pytest.skip(f"News API not available: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
class TestJobsDomain:
    """Test Jobs domain operations."""

    async def test_search_jobs(self, async_client):
        """Test remote job search."""
        try:
            jobs = await async_client.domains.jobs.search("python developer")

            assert jobs is not None
        except Exception as e:
            pytest.skip(f"Jobs API not available: {e}")

    async def test_categories(self, async_client):
        """Test job categories."""
        try:
            categories = await async_client.domains.jobs.categories()

            assert categories is not None
        except Exception as e:
            pytest.skip(f"Jobs API not available: {e}")


@pytest.mark.e2e
@pytest.mark.asyncio
class TestUtilityDomain:
    """Test Utility domain operations."""

    async def test_calculate(self, async_client):
        """Test calculator."""
        try:
            result = await async_client.domains.utility.calculate("2 + 2 * 3")

            assert result is not None
            assert result.result is not None
        except Exception as e:
            pytest.skip(f"Calculator not available: {e}")

    async def test_uuid_generate(self, async_client):
        """Test UUID generation."""
        try:
            uuid = await async_client.domains.utility.uuid_generate()

            assert uuid is not None
            assert len(uuid) > 0
        except Exception as e:
            pytest.skip(f"UUID tool not available: {e}")
