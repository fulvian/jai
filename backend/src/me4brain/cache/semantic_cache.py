"""
Semantic Cache - Embedding-based similarity caching.

Provides semantic similarity matching for cache lookups,
using cosine similarity to find similar cached responses.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog

if TYPE_CHECKING:
    from me4brain.embeddings.bge_m3 import BGEM3Service

logger = structlog.get_logger(__name__)

# Default embedding dimension for BGE-M3
DEFAULT_EMBEDDING_DIM = 1024

# Default similarity threshold (from requirements: 0.85)
DEFAULT_SIMILARITY_THRESHOLD = 0.85


class SemanticCache:
    """Semantic similarity-based cache for domain classification.

    Uses embedding vectors to find similar queries even when the
    exact query string differs. Supports configurable similarity
    thresholds and embedding caching for performance.
    """

    def __init__(
        self,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        embedding_dim: int = DEFAULT_EMBEDDING_DIM,
        embedding_service: BGEM3Service | None = None,
    ) -> None:
        """Initialize SemanticCache.

        Args:
            threshold: Minimum cosine similarity for a match (0.0-1.0)
            embedding_dim: Dimension of embedding vectors
            embedding_service: Optional pre-configured embedding service
        """
        self._threshold = threshold
        self._embedding_dim = embedding_dim
        self._embeddings: BGEM3Service | None = embedding_service
        self._embedding_cache: dict[str, list[float]] = {}
        # Internal cache of query -> cached_response (populated externally)
        self._query_cache: dict[str, dict[str, Any]] = {}

    def set_embedding_service(self, service: BGEM3Service) -> None:
        """Set the embedding service to use.

        Args:
            service: BGEM3Service instance
        """
        self._embeddings = service

    async def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding for text, with in-memory caching.

        Args:
            text: Text to embed

        Returns:
            Numpy array of embeddings
        """
        # Check in-memory cache first
        if text in self._embedding_cache:
            return np.array(self._embedding_cache[text])

        if self._embeddings is None:
            # Lazy load embedding service
            from me4brain.embeddings.bge_m3 import get_embedding_service

            self._embeddings = get_embedding_service()

        # Use embed_query if available (for compatibility with mocks)
        if hasattr(self._embeddings, "embed_query"):
            # Sync method - run in executor
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(None, self._embeddings.embed_query, text)
        elif hasattr(self._embeddings, "embed_query_async"):
            # Async method
            embedding = await self._embeddings.embed_query_async(text)
        else:
            raise AttributeError(
                "Embedding service must have 'embed_query' or 'embed_query_async' method"
            )

        # Ensure it's a numpy array
        if not isinstance(embedding, np.ndarray):
            embedding = np.array(embedding)

        # Cache in memory
        self._embedding_cache[text] = embedding.tolist()

        return embedding

    async def _compute_similarity(self, query1: str, query2: str) -> float:
        """Compute cosine similarity between two queries.

        Args:
            query1: First query text
            query2: Second query text

        Returns:
            Cosine similarity score (0.0-1.0)
        """
        emb1 = await self._get_embedding(query1)
        emb2 = await self._get_embedding(query2)

        # Cosine similarity = dot product of normalized vectors
        # Since BGE-M3 returns L2-normalized embeddings, this is just dot product
        similarity = float(np.dot(emb1, emb2))

        # Clamp to [0, 1] range (should already be, but safety)
        return max(0.0, min(1.0, similarity))

    async def _get_cached_by_embedding(
        self,
        query: str,
    ) -> dict[str, Any] | None:
        """Get cached response by query string.

        This is a placeholder - in real usage this would query the
        cache database. For tests, this is mocked.

        Args:
            query: Query string to look up

        Returns:
            Cached response dict or None
        """
        return self._query_cache.get(query)

    def add_to_cache(self, query: str, cached_response: dict[str, Any]) -> None:
        """Add a query and its response to the internal cache.

        Args:
            query: Query string
            cached_response: Cached response data including cached_embedding
        """
        self._query_cache[query] = cached_response

    async def find_similar(self, query: str) -> dict[str, Any] | None:
        """Find a similar cached response.

        Args:
            query: Query to find similar match for

        Returns:
            Cached data dict if similar match found, None otherwise
        """
        query_embedding = await self._get_embedding(query)

        best_match: dict[str, Any] | None = None
        best_similarity = 0.0

        for _cached_query, cached_data in self._query_cache.items():
            cached_embedding = cached_data.get("cached_embedding")
            if cached_embedding is None:
                continue

            # Compute similarity
            similarity = float(np.dot(query_embedding, np.array(cached_embedding)))

            if similarity >= self._threshold and similarity > best_similarity:
                best_similarity = similarity
                best_match = cached_data

        logger.debug(
            "semantic_cache_search",
            query_preview=query[:50],
            best_similarity=best_similarity,
            threshold=self._threshold,
            found=best_match is not None,
        )

        return best_match

    async def compute_similarity_scores(
        self,
        query: str,
    ) -> list[tuple[str, float]]:
        """Compute similarity scores for all cached queries.

        Args:
            query: Query to compare

        Returns:
            List of (query_string, similarity_score) tuples sorted by score
        """
        query_embedding = await self._get_embedding(query)
        results: list[tuple[str, float]] = []

        for cached_query, cached_data in self._query_cache.items():
            cached_embedding = cached_data.get("cached_embedding")
            if cached_embedding is None:
                continue

            similarity = float(np.dot(query_embedding, np.array(cached_embedding)))
            results.append((cached_query, similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results
