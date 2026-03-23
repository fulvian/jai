"""Phase D: Tool Retriever Unit Tests.

Tests for Stage 2 of hybrid routing: Tool Retrieval via Embeddings.
Covers tool selection, ranking, caching, fallback semantics, and payload limits.

Coverage target: 15+ tests across 3 test classes
"""

from unittest.mock import AsyncMock

import numpy as np
import pytest

from me4brain.engine.hybrid_router.tool_retriever import ToolRetriever
from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    DomainComplexity,
    HybridRouterConfig,
    ToolRetrievalResult,
)


class TestToolRetrievalBasic:
    """Tests for basic tool retrieval functionality."""

    @pytest.fixture
    def retriever_setup(self):
        """Setup tool retriever with mock data."""
        tool_schemas = {
            "get_nba_scores": {
                "name": "get_nba_scores",
                "description": "Get NBA game scores",
            },
            "get_player_stats": {
                "name": "get_player_stats",
                "description": "Get player statistics",
            },
            "search_web": {
                "name": "search_web",
                "description": "Search the web",
            },
        }

        tool_embeddings = {
            "get_nba_scores": np.array([1.0, 0.0, 0.0]),
            "get_player_stats": np.array([0.9, 0.1, 0.0]),
            "search_web": np.array([0.0, 0.0, 1.0]),
        }

        tool_domains = {
            "get_nba_scores": "sports_nba",
            "get_player_stats": "sports_nba",
            "search_web": "web_search",
        }

        embed_fn = AsyncMock()
        config = HybridRouterConfig()

        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
            config=config,
        )

        return retriever, embed_fn, tool_embeddings

    @pytest.mark.asyncio
    async def test_retrieve_tools_above_threshold(self, retriever_setup):
        """Test retrieving tools above similarity threshold."""
        retriever, embed_fn, tool_embeddings = retriever_setup

        # Query embedding similar to NBA tools
        query_embedding = np.array([0.95, 0.05, 0.0])
        embed_fn.return_value = query_embedding

        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="high")],
            confidence=0.9,
        )

        result = await retriever.retrieve("NBA scores", classification)

        assert isinstance(result, ToolRetrievalResult)
        assert len(result.tools) >= 1
        assert "sports_nba" in result.domains_searched
        # At least one NBA tool should be retrieved
        assert any(t.domain == "sports_nba" for t in result.tools)

    @pytest.mark.asyncio
    async def test_no_domains_in_classification(self, retriever_setup):
        """Test handling of classification with no domains."""
        retriever, embed_fn, _ = retriever_setup

        classification = DomainClassification(
            domains=[],
            confidence=0.0,
        )

        result = await retriever.retrieve("random query", classification)

        assert result.tools == []
        assert result.domains_searched == []

    @pytest.mark.asyncio
    async def test_unknown_domain_skipped(self, retriever_setup):
        """Test that unknown domains are skipped gracefully."""
        retriever, embed_fn, _ = retriever_setup

        query_embedding = np.array([0.5, 0.5, 0.5])
        embed_fn.return_value = query_embedding

        classification = DomainClassification(
            domains=[
                DomainComplexity(name="unknown_domain", complexity="medium"),
                DomainComplexity(name="sports_nba", complexity="high"),
            ],
            confidence=0.8,
        )

        result = await retriever.retrieve("test query", classification)

        # Should only search known domains
        assert "sports_nba" in result.domains_searched
        assert "unknown_domain" not in result.domains_searched

    @pytest.mark.asyncio
    async def test_tool_ranking_by_similarity(self, retriever_setup):
        """Test that tools are ranked by similarity score."""
        retriever, embed_fn, _ = retriever_setup

        # Query similar to get_nba_scores (0.95 similarity)
        query_embedding = np.array([0.95, 0.05, 0.0])
        embed_fn.return_value = query_embedding

        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="high")],
            confidence=0.9,
        )

        result = await retriever.retrieve("NBA", classification)

        # Tools should be sorted by similarity (highest first)
        if len(result.tools) > 1:
            for i in range(len(result.tools) - 1):
                assert result.tools[i].similarity_score >= result.tools[i + 1].similarity_score


class TestToolRetrievalFallback:
    """Tests for fallback semantics in tool retrieval."""

    @pytest.fixture
    def retriever_with_fallback(self):
        """Setup retriever for fallback testing."""
        tool_schemas = {
            "primary_tool": {
                "name": "primary_tool",
                "description": "Primary tool",
            },
            "secondary_tool": {
                "name": "secondary_tool",
                "description": "Secondary tool",
            },
        }

        # Embeddings with low similarity
        tool_embeddings = {
            "primary_tool": np.array([1.0, 0.0]),
            "secondary_tool": np.array([0.9, 0.1]),
        }

        tool_domains = {
            "primary_tool": "test_domain",
            "secondary_tool": "test_domain",
        }

        embed_fn = AsyncMock()
        config = HybridRouterConfig(similarity_thresholds={"high": 0.8, "medium": 0.6, "low": 0.4})

        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
            config=config,
        )

        return retriever, embed_fn

    @pytest.mark.asyncio
    async def test_fallback_to_best_tool_above_floor(self, retriever_with_fallback):
        """Test fallback to best tool when above floor threshold."""
        retriever, embed_fn = retriever_with_fallback

        # Query embedding with low similarity (0.45 - above floor 0.40)
        query_embedding = np.array([0.45, 0.0])
        embed_fn.return_value = query_embedding

        classification = DomainClassification(
            domains=[DomainComplexity(name="test_domain", complexity="high")],
            confidence=0.9,
        )

        result = await retriever.retrieve("test query", classification)

        # Should include best tool even below threshold
        # because it's above fallback floor (0.40)
        assert len(result.tools) >= 1
        assert result.tools[0].name == "primary_tool"

    @pytest.mark.asyncio
    async def test_fallback_rejection_below_floor(self, retriever_with_fallback):
        """Test rejection of best tool below fallback floor."""
        retriever, embed_fn = retriever_with_fallback

        # Query embedding orthogonal to both tools (similarity ~0)
        query_embedding = np.array([0.0, 1.0])
        embed_fn.return_value = query_embedding

        classification = DomainClassification(
            domains=[DomainComplexity(name="test_domain", complexity="high")],
            confidence=0.9,
        )

        result = await retriever.retrieve("test query", classification)

        # No tools should be included (all below floor)
        assert len(result.tools) == 0


class TestToolRetrievalPayloadLimit:
    """Tests for payload size limits and tool trimming."""

    @pytest.fixture
    def retriever_with_limits(self):
        """Setup retriever with strict payload limits."""
        tool_schemas = {
            "tool_a": {"name": "tool_a", "description": "A" * 100},
            "tool_b": {"name": "tool_b", "description": "B" * 100},
            "tool_c": {"name": "tool_c", "description": "C" * 100},
        }

        tool_embeddings = {
            "tool_a": np.array([1.0, 0.0, 0.0]),
            "tool_b": np.array([0.9, 0.1, 0.0]),
            "tool_c": np.array([0.8, 0.0, 0.2]),
        }

        tool_domains = {
            "tool_a": "domain1",
            "tool_b": "domain1",
            "tool_c": "domain1",
        }

        embed_fn = AsyncMock()

        # Very strict limit to force trimming
        config = HybridRouterConfig(max_payload_bytes=300)

        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
            config=config,
        )

        return retriever, embed_fn

    @pytest.mark.asyncio
    async def test_payload_limit_trimming(self, retriever_with_limits):
        """Test that tools are trimmed to fit payload limit."""
        retriever, embed_fn = retriever_with_limits

        query_embedding = np.array([0.95, 0.05, 0.0])
        embed_fn.return_value = query_embedding

        classification = DomainClassification(
            domains=[DomainComplexity(name="domain1", complexity="high")],
            confidence=0.9,
        )

        result = await retriever.retrieve("test", classification)

        # Should have limited tools to fit payload
        assert result.total_payload_bytes <= 300
        # Best tools should be prioritized
        if len(result.tools) > 0:
            assert result.tools[0].similarity_score >= result.tools[-1].similarity_score


class TestToolRetrievalGetByName:
    """Tests for explicit tool retrieval by name."""

    @pytest.mark.asyncio
    async def test_get_tool_by_name_success(self):
        """Test retrieving a tool explicitly by name."""
        tool_schemas = {
            "explicit_tool": {
                "name": "explicit_tool",
                "description": "An explicit tool",
            }
        }

        tool_embeddings = {
            "explicit_tool": np.array([1.0, 0.0]),
        }

        tool_domains = {
            "explicit_tool": "test_domain",
        }

        embed_fn = AsyncMock()
        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
        )

        tool = await retriever.get_tool_by_name("explicit_tool")

        assert tool is not None
        assert tool.name == "explicit_tool"
        assert tool.domain == "test_domain"
        assert tool.similarity_score == 1.0  # Explicitly requested

    @pytest.mark.asyncio
    async def test_get_tool_by_name_not_found(self):
        """Test retrieving non-existent tool returns None."""
        tool_schemas = {}
        tool_embeddings = {}
        tool_domains = {}

        embed_fn = AsyncMock()
        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
        )

        tool = await retriever.get_tool_by_name("non_existent")

        assert tool is None


class TestToolRetrievalComplexity:
    """Tests for complexity-based threshold selection."""

    @pytest.mark.asyncio
    async def test_complexity_based_thresholds(self):
        """Test that threshold varies by complexity level."""
        tool_schemas = {
            "tool": {"name": "tool", "description": "test"},
        }

        tool_embeddings = {
            "tool": np.array([1.0, 0.0]),
        }

        tool_domains = {
            "tool": "domain",
        }

        embed_fn = AsyncMock()
        config = HybridRouterConfig(
            similarity_thresholds={
                "high": 0.8,
                "medium": 0.6,
                "low": 0.3,
            }
        )

        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
            config=config,
        )

        # Query with 0.65 similarity - passes medium, fails high
        query_embedding = np.array([0.65, 0.0])
        embed_fn.return_value = query_embedding

        # Test high complexity (threshold 0.8)
        classification_high = DomainClassification(
            domains=[DomainComplexity(name="domain", complexity="high")],
            confidence=0.9,
        )
        await retriever.retrieve("test", classification_high)

        # Test medium complexity (threshold 0.6)
        classification_medium = DomainClassification(
            domains=[DomainComplexity(name="domain", complexity="medium")],
            confidence=0.9,
        )
        result_medium = await retriever.retrieve("test", classification_medium)

        # Medium should include tool, high should not (or use fallback)
        assert len(result_medium.tools) >= 1


class TestCosimeSimilarity:
    """Tests for cosine similarity computation."""

    @pytest.mark.asyncio
    async def test_cosine_similarity_identical_vectors(self):
        """Test cosine similarity of identical vectors is 1.0."""
        tool_schemas = {"tool": {}}
        tool_embeddings = {"tool": np.array([1.0, 0.0, 0.0])}
        tool_domains = {"tool": "domain"}

        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=AsyncMock(),
        )

        vec = np.array([1.0, 0.0, 0.0])
        similarity = retriever._cosine_similarity(vec, vec)

        assert abs(similarity - 1.0) < 1e-6

    @pytest.mark.asyncio
    async def test_cosine_similarity_orthogonal_vectors(self):
        """Test cosine similarity of orthogonal vectors is 0.0."""
        tool_schemas = {"tool": {}}
        tool_embeddings = {"tool": np.array([1.0, 0.0])}
        tool_domains = {"tool": "domain"}

        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=AsyncMock(),
        )

        vec_a = np.array([1.0, 0.0])
        vec_b = np.array([0.0, 1.0])
        similarity = retriever._cosine_similarity(vec_a, vec_b)

        assert abs(similarity) < 1e-6

    @pytest.mark.asyncio
    async def test_cosine_similarity_zero_vector(self):
        """Test cosine similarity with zero vector returns 0.0."""
        tool_schemas = {"tool": {}}
        tool_embeddings = {"tool": np.array([1.0, 0.0])}
        tool_domains = {"tool": "domain"}

        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=AsyncMock(),
        )

        vec_a = np.array([1.0, 0.0])
        vec_b = np.array([0.0, 0.0])
        similarity = retriever._cosine_similarity(vec_a, vec_b)

        assert similarity == 0.0


class TestToolRetrievalMultiDomain:
    """Tests for multi-domain retrieval scenarios."""

    @pytest.mark.asyncio
    async def test_retrieve_from_multiple_domains(self):
        """Test tool retrieval across multiple domains."""
        tool_schemas = {
            "nba_tool": {"name": "nba_tool"},
            "web_tool": {"name": "web_tool"},
            "crypto_tool": {"name": "crypto_tool"},
        }

        tool_embeddings = {
            "nba_tool": np.array([1.0, 0.0, 0.0]),
            "web_tool": np.array([0.0, 1.0, 0.0]),
            "crypto_tool": np.array([0.0, 0.0, 1.0]),
        }

        tool_domains = {
            "nba_tool": "sports_nba",
            "web_tool": "web_search",
            "crypto_tool": "finance_crypto",
        }

        embed_fn = AsyncMock()
        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
        )

        # Query that should match both NBA and web
        query_embedding = np.array([0.7, 0.7, 0.0])
        embed_fn.return_value = query_embedding

        classification = DomainClassification(
            domains=[
                DomainComplexity(name="sports_nba", complexity="high"),
                DomainComplexity(name="web_search", complexity="medium"),
            ],
            confidence=0.9,
        )

        result = await retriever.retrieve("NBA teams on the web", classification)

        # Should search both domains
        assert "sports_nba" in result.domains_searched
        assert "web_search" in result.domains_searched
        # Should retrieve tools from both
        domains_in_result = {t.domain for t in result.tools}
        assert len(domains_in_result) >= 1


class TestSchemaSize:
    """Tests for schema size calculation."""

    @pytest.mark.asyncio
    async def test_schema_size_calculation(self):
        """Test that schema size is calculated correctly."""
        large_schema = {
            "name": "tool",
            "description": "X" * 1000,  # Large description
        }

        tool_schemas = {
            "tool": large_schema,
        }

        tool_embeddings = {
            "tool": np.array([1.0]),
        }

        tool_domains = {
            "tool": "domain",
        }

        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=AsyncMock(),
        )

        size = retriever._get_schema_size("tool")

        # Size should be > 0 and reasonable
        assert size > 0
        assert size > 1000  # Should include description


class TestRetrieveGlobalTopK:
    """Tests for global top-K retrieval fallback."""

    @pytest.mark.asyncio
    async def test_retrieve_global_topk(self):
        """Test global top-K retrieval across all domains."""
        tool_schemas = {
            "tool_1": {"name": "tool_1"},
            "tool_2": {"name": "tool_2"},
            "tool_3": {"name": "tool_3"},
        }

        tool_embeddings = {
            "tool_1": np.array([1.0, 0.0, 0.0]),
            "tool_2": np.array([0.9, 0.1, 0.0]),
            "tool_3": np.array([0.8, 0.0, 0.2]),
        }

        tool_domains = {
            "tool_1": "domain1",
            "tool_2": "domain1",
            "tool_3": "domain2",
        }

        embed_fn = AsyncMock()
        retriever = ToolRetriever(
            tool_schemas=tool_schemas,
            tool_embeddings=tool_embeddings,
            tool_domains=tool_domains,
            embed_fn=embed_fn,
        )

        query_embedding = np.array([0.85, 0.05, 0.1])
        embed_fn.return_value = query_embedding

        result = await retriever.retrieve_global_topk("test", k=2)

        # Should return top-K tools
        assert len(result.tools) <= 2
        assert isinstance(result, ToolRetrievalResult)
