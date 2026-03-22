"""
Query Normalizer - Normalize queries for better cache hits.

Provides:
- Query normalization (lowercase, whitespace, punctuation)
- Cache key generation using SHA256 hash
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Final

# Cache key prefix
CACHE_KEY_PREFIX = "domain"

# Regex for normalizing whitespace
WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")

# Regex for normalizing punctuation (multiple punctuation -> single)
PUNCTUATION_RE: Final[re.Pattern[str]] = re.compile(r"([!?.])\1+")


class QueryNormalizer:
    """Normalizes queries for consistent cache key generation.

    Normalization includes:
    - Convert to lowercase
    - Normalize unicode characters (NFC normalization)
    - Remove extra whitespace
    - Standardize punctuation
    - Remove leading/trailing whitespace
    - Remove script tags for security (XSS prevention)
    """

    def normalize(self, query: str) -> str:
        """Normalize a query string.

        Args:
            query: Raw query string

        Returns:
            Normalized query string
        """
        if not query:
            return ""

        # Normalize unicode (NFC -> NFC is same, but handles composed forms)
        normalized = unicodedata.normalize("NFC", query)

        # Convert to lowercase
        normalized = normalized.lower()

        # Remove script tags and content for security
        normalized = re.sub(
            r"<script[^>]*>.*?</script>", "", normalized, flags=re.IGNORECASE | re.DOTALL
        )
        normalized = re.sub(r"<[^>]+>", "", normalized)

        # Normalize whitespace (multiple spaces -> single)
        normalized = WHITESPACE_RE.sub(" ", normalized)

        # Normalize punctuation (multiple !? -> single)
        normalized = PUNCTUATION_RE.sub(r"\1", normalized)

        # Remove leading/trailing whitespace
        normalized = normalized.strip()

        return normalized

    def __call__(self, query: str) -> str:
        """Allow QueryNormalizer to be called as a function.

        Args:
            query: Raw query string

        Returns:
            Normalized query string
        """
        return self.normalize(query)


def generate_cache_key(query: str, model: str, provider: str) -> str:
    """Generate a deterministic cache key for a query.

    The key is a SHA256 hash of the normalized query combined with
    the model and provider to ensure uniqueness across different
    LLM configurations.

    Args:
        query: The user query (will be normalized)
        model: LLM model name (e.g., "llama2", "mistral")
        provider: LLM provider name (e.g., "ollama", "lmstudio")

    Returns:
        64-character hex string (SHA256 digest)
    """
    normalizer = QueryNormalizer()
    normalized_query = normalizer.normalize(query)

    # Combine normalized query with model and provider
    key_input = f"{normalized_query}:{model}:{provider}"

    # Generate SHA256 hash
    hash_obj = hashlib.sha256(key_input.encode("utf-8"))
    return hash_obj.hexdigest()
