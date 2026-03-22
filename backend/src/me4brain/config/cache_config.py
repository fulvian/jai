"""
Cache Configuration - Settings for intelligent query caching.

Provides Pydantic settings for:
- Redis cache connection
- TTL and size limits
- Semantic matching threshold
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default cache TTL (1 hour)
DEFAULT_CACHE_TTL = 3600

# Default max cache entries
DEFAULT_MAX_CACHE_SIZE = 10_000

# Default semantic similarity threshold
DEFAULT_SIMILARITY_THRESHOLD = 0.85


class CacheSettings(BaseSettings):
    """Cache-specific settings."""

    model_config = SettingsConfigDict(
        env_prefix="CACHE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Enable/disable caching
    enabled: bool = Field(
        default=True,
        description="Enable/disable query caching",
    )

    # Redis connection
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )

    # Cache behavior
    default_ttl: int = Field(
        default=DEFAULT_CACHE_TTL,
        description="Default cache TTL in seconds",
    )

    max_cache_size: int = Field(
        default=DEFAULT_MAX_CACHE_SIZE,
        description="Maximum number of cache entries",
    )

    # Semantic caching
    semantic_cache_enabled: bool = Field(
        default=True,
        description="Enable semantic similarity matching",
    )

    semantic_matching_threshold: float = Field(
        default=DEFAULT_SIMILARITY_THRESHOLD,
        description="Minimum cosine similarity for semantic cache hit (0.0-1.0)",
    )

    # Connection pool settings
    redis_pool_size: int = Field(
        default=10,
        description="Redis connection pool size",
    )

    redis_max_overflow: int = Field(
        default=20,
        description="Max overflow connections",
    )

    redis_socket_timeout: float = Field(
        default=5.0,
        description="Redis socket timeout in seconds",
    )


@lru_cache
def get_cache_settings() -> CacheSettings:
    """Get singleton cache settings instance."""
    return CacheSettings()
