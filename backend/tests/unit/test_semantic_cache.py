# Phase 6: Semantic Cache Tests
# Tests for semantic similarity-based caching

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

from me4brain.cache.semantic_cache import SemanticCache


class TestSemanticCache:
    """Test suite for SemanticCache with embedding similarity."""

    @pytest.fixture
    def mock_embeddings(self):
        """Create mock embeddings module."""
        mock = MagicMock()
        mock.embed_query = MagicMock(return_value=[0.1, 0.2, 0.3])
        mock.embed_query_async = AsyncMock(return_value=[0.1, 0.2, 0.3])
        return mock

    @pytest.fixture
    def semantic_cache(self, mock_embeddings):
        """Create a SemanticCache with mocked dependencies."""
        cache = SemanticCache(threshold=0.85, embedding_dim=384)
        cache._embeddings = mock_embeddings
        return cache

    @pytest.mark.asyncio
    async def test_embedding_generation(self, semantic_cache, mock_embeddings):
        """Test that embeddings are generated for queries."""
        query = "What is the weather today?"

        embedding = await semantic_cache._get_embedding(query)

        assert embedding is not None
        assert isinstance(embedding, np.ndarray)
        # Uses embed_query (sync method run in executor)
        mock_embeddings.embed_query.assert_called_once_with(query)

    @pytest.mark.asyncio
    async def test_similarity_matching(self, semantic_cache):
        """Test cosine similarity matching between queries."""
        query1 = "How will the Lakers play tonight?"
        query2 = "What's the Lakers' game prediction?"

        # Mock embeddings with high similarity (>0.85)
        # Using nearly identical vectors
        with patch.object(
            semantic_cache,
            "_get_embedding",
            side_effect=[np.array([0.9, 0.1, 0.2]), np.array([0.92, 0.08, 0.18])],
        ):
            similarity = await semantic_cache._compute_similarity(query1, query2)

            # 0.9*0.92 + 0.1*0.08 + 0.2*0.18 = 0.828 + 0.008 + 0.036 = 0.872 > 0.85
            assert similarity > 0.85

    @pytest.mark.asyncio
    async def test_threshold_enforcement(self, semantic_cache):
        """Test that threshold is properly enforced."""
        query1 = "What is Python?"
        query2 = "Tell me about snakes and reptiles"

        # Mock embeddings with low similarity
        with patch.object(
            semantic_cache,
            "_get_embedding",
            side_effect=[np.array([0.9, 0.1, 0.2]), np.array([0.1, 0.85, 0.8])],
        ):
            similarity = await semantic_cache._compute_similarity(query1, query2)

            assert similarity < 0.85  # Should be below threshold

    @pytest.mark.asyncio
    async def test_embedding_caching(self, semantic_cache, mock_embeddings):
        """Test that generated embeddings are cached."""
        query = "NBA Finals prediction"

        # First call should generate embedding
        await semantic_cache._get_embedding(query)
        # Second call should return cached
        await semantic_cache._get_embedding(query)

        # Only one actual call to the embeddings service
        assert mock_embeddings.embed_query.call_count == 1

    @pytest.mark.asyncio
    async def test_false_positive_rate(self, semantic_cache):
        """Test that semantically different queries don't match."""
        query1 = "Buy 100 shares of Apple stock"
        query2 = "How to cook pasta carbonara"

        with patch.object(
            semantic_cache,
            "_get_embedding",
            side_effect=[np.array([0.9, 0.05, 0.05]), np.array([0.1, 0.1, 0.85])],
        ):
            similarity = await semantic_cache._compute_similarity(query1, query2)

            assert similarity < 0.5  # Should be very different

    @pytest.mark.asyncio
    async def test_embedding_latency(self, semantic_cache, mock_embeddings):
        """Test that embedding generation is reasonably fast."""
        import time

        mock_embeddings.embed_query.return_value = [0.1] * 384

        start = time.time()
        await semantic_cache._get_embedding("Test query")
        elapsed = time.time() - start

        # Should complete in under 50ms (threshold from requirements)
        assert elapsed < 0.05

    @pytest.mark.asyncio
    async def test_find_similar_returns_cached_response(self, semantic_cache):
        """Test find_similar returns cached response when found."""
        cached_response = {
            "domain": "sports_nba",
            "confidence": 0.95,
            "cached_embedding": [0.9, 0.1, 0.2],  # List for JSON serialization
        }

        # Add the cached query to the internal cache
        semantic_cache._query_cache["Lakers game tonight"] = cached_response

        # Patch _get_embedding to return a vector similar to cached_embedding
        # 0.9*0.92 + 0.1*0.08 + 0.2*0.18 = 0.872 > 0.85 threshold
        with patch.object(
            semantic_cache, "_get_embedding", return_value=np.array([0.92, 0.08, 0.18])
        ):
            result = await semantic_cache.find_similar("Lakers game tonight")

            assert result is not None
            assert result["domain"] == "sports_nba"

    @pytest.mark.asyncio
    async def test_find_similar_returns_none_when_no_match(self, semantic_cache):
        """Test find_similar returns None when no similar query found."""
        # Add a cached query but patch _get_embedding to return very different vector
        cached_response = {
            "domain": "sports_nba",
            "confidence": 0.95,
            "cached_embedding": [0.9, 0.1, 0.2],
        }
        semantic_cache._query_cache["Lakers game"] = cached_response

        # Return a very different embedding (similarity will be low)
        with patch.object(
            semantic_cache, "_get_embedding", return_value=np.array([0.1, 0.1, 0.85])
        ):
            result = await semantic_cache.find_similar("Python programming")

            assert result is None
