"""Tests for science_research domain enhancements (P0 and P1 fixes)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from me4brain.domains.science_research.tools import science_api
from me4brain.domains.science_research.handler import ScienceResearchHandler
from me4brain.engine.synthesizer import ResponseSynthesizer
from me4brain.models.tool_result import ToolResult


class TestSemanticScholarEnhancements:
    """Test P0 fix: Temporal filtering and citation count sorting."""

    @pytest.mark.asyncio
    async def test_semanticscholar_search_with_year_filter(self):
        """Test that year_min/year_max filter results correctly."""
        # Mock the httpx.AsyncClient
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "paperId": "1",
                    "title": "Paper 2024",
                    "authors": [{"name": "Author A"}],
                    "year": 2024,
                    "citationCount": 100,
                    "abstract": "Abstract 2024",
                    "openAccessPdf": None,
                },
                {
                    "paperId": "2",
                    "title": "Paper 2023",
                    "authors": [{"name": "Author B"}],
                    "year": 2023,
                    "citationCount": 50,
                    "abstract": "Abstract 2023",
                    "openAccessPdf": None,
                },
                {
                    "paperId": "3",
                    "title": "Paper 2025",
                    "authors": [{"name": "Author C"}],
                    "year": 2025,
                    "citationCount": 200,
                    "abstract": "Abstract 2025",
                    "openAccessPdf": None,
                },
            ]
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            # Test with year_min=2024, year_max=2025
            result = await science_api.semanticscholar_search(
                query="quantum computing",
                max_results=10,
                year_min=2024,
                year_max=2025,
            )

            assert result["count"] == 2
            assert all(p["year"] >= 2024 for p in result["papers"])
            assert all(p["year"] <= 2025 for p in result["papers"])

    @pytest.mark.asyncio
    async def test_semanticscholar_search_sorted_by_citations(self):
        """Test that results are sorted by citation count (descending)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "paperId": "1",
                    "title": "Low Citations",
                    "authors": [{"name": "Author A"}],
                    "year": 2024,
                    "citationCount": 10,
                    "abstract": "Abstract",
                    "openAccessPdf": None,
                },
                {
                    "paperId": "2",
                    "title": "High Citations",
                    "authors": [{"name": "Author B"}],
                    "year": 2024,
                    "citationCount": 500,
                    "abstract": "Abstract",
                    "openAccessPdf": None,
                },
                {
                    "paperId": "3",
                    "title": "Medium Citations",
                    "authors": [{"name": "Author C"}],
                    "year": 2024,
                    "citationCount": 100,
                    "abstract": "Abstract",
                    "openAccessPdf": None,
                },
            ]
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await science_api.semanticscholar_search(
                query="machine learning",
                max_results=10,
            )

            papers = result["papers"]
            citations = [p.get("citation_count", 0) for p in papers]

            # Verify descending order
            assert citations == sorted(citations, reverse=True)
            assert citations == [500, 100, 10]

    @pytest.mark.asyncio
    async def test_semanticscholar_search_includes_paper_id(self):
        """Test that paper_id is included in results for drill-down."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "paperId": "abc123",
                    "title": "Test Paper",
                    "authors": [{"name": "Author"}],
                    "year": 2024,
                    "citationCount": 50,
                    "abstract": "Abstract",
                    "openAccessPdf": None,
                }
            ]
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await science_api.semanticscholar_search(
                query="test",
                max_results=10,
            )

            assert result["papers"][0]["paper_id"] == "abc123"


class TestSynthesizerPartialResponse:
    """Test P0 fix: Synthesizer handling of partial results."""

    def test_generate_partial_response_with_failed_tools(self):
        """Test that partial response provides informative feedback."""
        synthesizer = ResponseSynthesizer(model="test-model")

        # Create mock results
        successful_result = ToolResult(
            tool_name="semanticscholar_search",
            success=True,
            data={"papers": [{"title": "Test"}]},
        )
        failed_result = ToolResult(
            tool_name="web_search",
            success=False,
            error="No results found",
        )

        results = [successful_result, failed_result]

        response = synthesizer._generate_partial_response(
            results=results,
            query="test query",
            failed=[failed_result],
        )

        # Verify response is informative, not generic
        assert "Ho trovato risultati da" in response
        assert "semanticscholar_search" in response
        assert "web_search" in response
        assert "Non sono riuscito" not in response or "Ma non sono riuscito" in response


class TestScienceResearchWebFallback:
    """Test P1 fix: Web search fallback for author queries."""

    def test_is_author_query_detection(self):
        """Test that author-related queries are detected."""
        handler = ScienceResearchHandler()

        # Test various author-related queries
        assert handler._is_author_query("interviste di ricercatori")
        assert handler._is_author_query("talk su quantum computing")
        assert handler._is_author_query("startup di autori")
        assert handler._is_author_query("progetti open-source")

        # Test non-author queries
        assert not handler._is_author_query("paper su machine learning")
        assert not handler._is_author_query("ricerca su AI")

    def test_build_author_search_query(self):
        """Test that web search queries are built correctly."""
        handler = ScienceResearchHandler()

        # Test interview query
        query = "interviste di ricercatori su quantum computing"
        result = handler._build_author_search_query(query)
        assert "interview" in result.lower()

        # Test talk query
        query = "talk su machine learning"
        result = handler._build_author_search_query(query)
        assert "talk" in result.lower() or "conference" in result.lower()

        # Test startup query
        query = "startup di ricercatori su AI"
        result = handler._build_author_search_query(query)
        assert "startup" in result.lower() or "project" in result.lower()

    @pytest.mark.asyncio
    async def test_search_author_web_fallback(self):
        """Test web search fallback execution."""
        handler = ScienceResearchHandler()

        mock_web_result = {
            "results": [
                {
                    "title": "Interview with Dr. Smith",
                    "url": "https://example.com/interview",
                    "snippet": "Dr. Smith discusses quantum computing...",
                }
            ]
        }

        with patch(
            "me4brain.domains.web_search.tools.web_api.duckduckgo_search",
            new_callable=AsyncMock,
        ) as mock_web:
            mock_web.return_value = mock_web_result

            results = await handler._search_author_web(
                query="interviste su quantum computing",
                analysis={},
            )

            assert len(results) > 0
            assert results[0].success
            assert results[0].tool_name == "web_search_fallback"


class TestIntegrationComplexQuery:
    """Integration test for complex multi-step queries."""

    @pytest.mark.asyncio
    async def test_quantum_computing_query_with_filters(self):
        """Test complex query with temporal filtering."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "paperId": "1",
                    "title": "Surface codes: Towards practical large-scale quantum computation",
                    "authors": [
                        {"name": "John Doe"},
                        {"name": "Jane Smith"},
                    ],
                    "year": 2024,
                    "citationCount": 342,
                    "abstract": "Abstract about surface codes",
                    "openAccessPdf": None,
                },
                {
                    "paperId": "2",
                    "title": "Quantum error correction with topological codes",
                    "authors": [{"name": "Alice Johnson"}],
                    "year": 2025,
                    "citationCount": 287,
                    "abstract": "Abstract about topological codes",
                    "openAccessPdf": None,
                },
            ]
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await science_api.semanticscholar_search(
                query="quantum computing error correction",
                max_results=10,
                year_min=2024,
                year_max=2026,
            )

            # Verify results
            assert result["count"] == 2
            assert result["papers"][0]["citation_count"] == 342  # Sorted by citations
            assert result["papers"][1]["citation_count"] == 287
            assert all(p["year"] >= 2024 for p in result["papers"])
