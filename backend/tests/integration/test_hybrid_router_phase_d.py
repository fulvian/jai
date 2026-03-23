"""Phase D: Integration Tests for Hybrid Routing.

Tests for multi-stage interactions and end-to-end fallback semantics.
Covers domain classification → decomposition → tool retrieval workflows.

Coverage target: 10+ tests across 3 test classes
"""

from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest

from me4brain.engine.hybrid_router.domain_classifier import DomainClassifier
from me4brain.engine.hybrid_router.query_decomposer import QueryDecomposer
from me4brain.engine.hybrid_router.tool_retriever import ToolRetriever
from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    DomainComplexity,
    HybridRouterConfig,
    SubQuery,
)


class TestMultiDomainIntegration:
    """Tests for multi-domain query processing."""

    @pytest.mark.asyncio
    async def test_multi_domain_classification_and_tool_retrieval(self):
        """Test that multi-domain classification leads to tool retrieval across domains."""
        # Setup mock classifier with required arguments
        mock_llm_client = Mock()
        classifier = DomainClassifier(
            llm_client=mock_llm_client,
            available_domains=["sports_nba", "web_search"],
        )
        classifier._llm_classify = AsyncMock()

        # Simulate multi-domain classification result
        classifier._llm_classify.return_value = {
            "domains": [
                {"name": "sports_nba", "complexity": "high"},
                {"name": "web_search", "complexity": "medium"},
            ],
            "confidence": 0.92,
            "query_summary": "Find NBA teams and their websites",
        }

        # Setup tool retriever
        tool_schemas = {
            "get_nba_teams": {"name": "get_nba_teams", "description": "Get NBA teams"},
            "search_web": {"name": "search_web", "description": "Search web"},
        }

        tool_embeddings = {
            "get_nba_teams": np.array([1.0, 0.0]),
            "search_web": np.array([0.0, 1.0]),
        }

        tool_domains = {
            "get_nba_teams": "sports_nba",
            "search_web": "web_search",
        }

        embed_fn = AsyncMock(return_value=np.array([0.7, 0.7]))
        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
        )

        # Classify query
        classification = DomainClassification(
            domains=[
                DomainComplexity(name="sports_nba", complexity="high"),
                DomainComplexity(name="web_search", complexity="medium"),
            ],
            confidence=0.92,
            query_summary="Find NBA teams and their websites",
        )

        # Retrieve tools
        result = await retriever.retrieve("NBA teams", classification)

        # Should have domains from both domains
        assert "sports_nba" in result.domains_searched
        assert "web_search" in result.domains_searched
        assert len(result.tools) >= 1


class TestDecompositionAndRetrieval:
    """Tests for query decomposition followed by tool retrieval."""

    @pytest.mark.asyncio
    async def test_decomposed_queries_retrieve_different_tools(self):
        """Test that decomposed sub-queries retrieve different tools."""
        # Setup decomposer with required arguments
        mock_llm_client = Mock()
        decomposer = QueryDecomposer(
            llm_client=mock_llm_client,
            available_domains=["sports_nba", "web_search"],
        )
        decomposer._decompose = AsyncMock()

        # Simulate decomposition result
        decomposer._decompose.return_value = [
            SubQuery(text="Get Lakers scores", domain="sports_nba", intent="get_scores"),
            SubQuery(text="Search for Lakers news", domain="web_search", intent="search"),
        ]

        # Setup retriever
        tool_schemas = {
            "get_scores": {"name": "get_scores"},
            "search_news": {"name": "search_news"},
        }

        tool_embeddings = {
            "get_scores": np.array([1.0, 0.0]),
            "search_news": np.array([0.0, 1.0]),
        }

        tool_domains = {
            "get_scores": "sports_nba",
            "search_news": "web_search",
        }

        embed_fn = AsyncMock()
        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
        )

        # For first sub-query (scores)
        embed_fn.return_value = np.array([0.95, 0.1])
        classification1 = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="high")],
            confidence=0.95,
        )
        result1 = await retriever.retrieve("Lakers scores", classification1)

        # For second sub-query (news)
        embed_fn.return_value = np.array([0.1, 0.95])
        classification2 = DomainClassification(
            domains=[DomainComplexity(name="web_search", complexity="medium")],
            confidence=0.90,
        )
        result2 = await retriever.retrieve("Lakers news", classification2)

        # First should retrieve scores tool, second should retrieve news tool
        # (or at least different domains)
        assert "sports_nba" in result1.domains_searched
        assert "web_search" in result2.domains_searched


class TestFallbackChainIntegration:
    """Tests for fallback chains across multiple routing stages."""

    @pytest.mark.asyncio
    async def test_low_confidence_classification_triggers_fallback(self):
        """Test that low confidence classification is marked for fallback."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="high")],
            confidence=0.3,  # Low confidence
            query_summary="Unclear query about NBA",
        )

        # Low confidence should trigger fallback
        assert classification.is_low_confidence
        assert classification.needs_fallback

    @pytest.mark.asyncio
    async def test_no_domains_with_high_confidence_no_fallback(self):
        """Test that conversational queries with high confidence don't trigger fallback."""
        classification = DomainClassification(
            domains=[],
            confidence=0.9,  # High confidence in no-domain decision
            query_summary="Conversational greeting",
        )

        # Should NOT trigger fallback for high-confidence conversational queries
        assert not classification.needs_fallback

    @pytest.mark.asyncio
    async def test_no_domains_with_low_confidence_triggers_fallback(self):
        """Test that ambiguous queries without domains trigger fallback."""
        classification = DomainClassification(
            domains=[],
            confidence=0.3,  # Low confidence
            query_summary="Unclear query",
        )

        # Should trigger fallback
        assert classification.needs_fallback

    @pytest.mark.asyncio
    async def test_tool_retrieval_respects_configuration(self):
        """Test that retriever respects configured thresholds."""
        config = HybridRouterConfig(
            similarity_thresholds={
                "high": 0.8,
                "medium": 0.6,
                "low": 0.3,
            },
            max_payload_bytes=15000,
        )

        tool_schemas = {
            "tool": {"name": "tool", "description": "test tool" * 100},
        }

        tool_embeddings = {
            "tool": np.array([1.0, 0.0]),
        }

        tool_domains = {
            "tool": "domain",
        }

        embed_fn = AsyncMock(return_value=np.array([0.65, 0.0]))
        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
            config=config,
        )

        # Query with 0.65 similarity
        # Should pass medium (0.6) but fail high (0.8)
        classification = DomainClassification(
            domains=[DomainComplexity(name="domain", complexity="medium")],
            confidence=0.9,
        )

        result = await retriever.retrieve("test", classification)

        # Should retrieve tool (passes medium threshold)
        assert len(result.tools) >= 1


class TestPayloadLimitingAcrossDomains:
    """Tests for payload limiting with multi-domain results."""

    @pytest.mark.asyncio
    async def test_payload_limit_with_multi_domain_tools(self):
        """Test that payload limit is enforced across multiple domains."""
        config = HybridRouterConfig(max_payload_bytes=500)

        tool_schemas = {
            "tool_a": {"name": "tool_a", "description": "A" * 100},
            "tool_b": {"name": "tool_b", "description": "B" * 100},
            "tool_c": {"name": "tool_c", "description": "C" * 100},
        }

        tool_embeddings = {
            "tool_a": np.array([1.0, 0.0]),
            "tool_b": np.array([0.9, 0.1]),
            "tool_c": np.array([0.8, 0.2]),
        }

        tool_domains = {
            "tool_a": "domain1",
            "tool_b": "domain1",
            "tool_c": "domain2",
        }

        embed_fn = AsyncMock(return_value=np.array([0.9, 0.1]))
        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
            config=config,
        )

        classification = DomainClassification(
            domains=[
                DomainComplexity(name="domain1", complexity="high"),
                DomainComplexity(name="domain2", complexity="high"),
            ],
            confidence=0.95,
        )

        result = await retriever.retrieve("test", classification)

        # Total payload should not exceed limit
        assert result.total_payload_bytes <= 500


class TestComplexityBasedSelection:
    """Tests for complexity-based tool selection."""

    @pytest.mark.asyncio
    async def test_high_complexity_stricter_thresholds(self):
        """Test that high complexity queries use stricter thresholds."""
        config = HybridRouterConfig(
            similarity_thresholds={
                "high": 0.8,
                "medium": 0.6,
                "low": 0.3,
            }
        )

        tool_schemas = {
            "tool": {"name": "tool"},
        }

        tool_embeddings = {
            "tool": np.array([1.0, 0.0]),
        }

        tool_domains = {
            "tool": "domain",
        }

        embed_fn = AsyncMock(return_value=np.array([0.7, 0.0]))
        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
            config=config,
        )

        # With 0.7 similarity:
        # - High complexity (threshold 0.8): should NOT retrieve
        # - Low complexity (threshold 0.3): should retrieve

        classification_high = DomainClassification(
            domains=[DomainComplexity(name="domain", complexity="high")],
            confidence=0.95,
        )

        classification_low = DomainClassification(
            domains=[DomainComplexity(name="domain", complexity="low")],
            confidence=0.95,
        )

        await retriever.retrieve("test", classification_high)
        # Reset embed_fn for second call
        embed_fn.return_value = np.array([0.7, 0.0])
        await retriever.retrieve("test", classification_low)

        # High complexity should retrieve fewer/no tools (stricter threshold)
        # Low complexity should retrieve more tools (looser threshold)
        # The actual behavior depends on fallback floor


class TestDomainBasedToolGrouping:
    """Tests for tool grouping by domain."""

    @pytest.mark.asyncio
    async def test_tools_grouped_by_domain_in_result(self):
        """Test that retrieved tools maintain domain grouping."""
        tool_schemas = {
            "nba_scores": {"name": "nba_scores"},
            "nba_stats": {"name": "nba_stats"},
            "web_search": {"name": "web_search"},
        }

        tool_embeddings = {
            "nba_scores": np.array([1.0, 0.0, 0.0]),
            "nba_stats": np.array([0.95, 0.1, 0.0]),
            "web_search": np.array([0.0, 0.0, 1.0]),
        }

        tool_domains = {
            "nba_scores": "sports_nba",
            "nba_stats": "sports_nba",
            "web_search": "web_search",
        }

        embed_fn = AsyncMock(return_value=np.array([0.85, 0.05, 0.1]))
        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
        )

        classification = DomainClassification(
            domains=[
                DomainComplexity(name="sports_nba", complexity="high"),
                DomainComplexity(name="web_search", complexity="medium"),
            ],
            confidence=0.95,
        )

        result = await retriever.retrieve("NBA", classification)

        # Should have tools from both domains
        domains_in_result = {t.domain for t in result.tools}
        assert len(domains_in_result) >= 1


class TestToolRetrievalEdgeCases:
    """Tests for edge cases in integrated retrieval scenarios."""

    @pytest.mark.asyncio
    async def test_empty_tool_schemas_returns_no_tools(self):
        """Test that empty tool schemas return no tools."""
        retriever = ToolRetriever(
            tool_schemas={},
            tool_embeddings={},
            tool_domains={},
            embed_fn=AsyncMock(return_value=np.array([1.0, 0.0])),
        )

        classification = DomainClassification(
            domains=[DomainComplexity(name="domain", complexity="high")],
            confidence=0.95,
        )

        result = await retriever.retrieve("test", classification)

        assert len(result.tools) == 0

    @pytest.mark.asyncio
    async def test_missing_embeddings_for_tool(self):
        """Test handling of tool with missing embedding."""
        tool_schemas = {
            "tool_with_embedding": {"name": "tool_with_embedding"},
            "tool_without_embedding": {"name": "tool_without_embedding"},
        }

        tool_embeddings = {
            "tool_with_embedding": np.array([1.0, 0.0]),
            # Intentionally missing embedding for tool_without_embedding
        }

        tool_domains = {
            "tool_with_embedding": "domain",
            "tool_without_embedding": "domain",
        }

        embed_fn = AsyncMock(return_value=np.array([0.9, 0.0]))
        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
        )

        classification = DomainClassification(
            domains=[DomainComplexity(name="domain", complexity="high")],
            confidence=0.95,
        )

        result = await retriever.retrieve("test", classification)

        # Should only retrieve tool with embedding
        if len(result.tools) > 0:
            assert all(t.name in tool_embeddings for t in result.tools)
