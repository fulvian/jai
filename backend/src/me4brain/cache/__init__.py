"""
Cache Module - Intelligent Query Caching with Semantic Matching.

Provides:
- CacheManager: Redis-backed caching with TTL support
- SemanticCache: Embedding-based similarity caching
- QueryNormalizer: Query normalization for better cache hits
- CachedResponse: Pydantic model for cached classification results
"""

from me4brain.cache.cache_manager import CacheManager, CachedResponse
from me4brain.cache.query_normalizer import QueryNormalizer, generate_cache_key
from me4brain.cache.semantic_cache import SemanticCache

__all__ = [
    "CacheManager",
    "CachedResponse",
    "QueryNormalizer",
    "generate_cache_key",
    "SemanticCache",
]
