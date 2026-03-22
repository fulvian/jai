# Phase 6: Query Normalizer Tests
# Tests for query normalization and cache key generation

import pytest
from me4brain.cache.query_normalizer import QueryNormalizer, generate_cache_key


class TestQueryNormalizer:
    """Test suite for QueryNormalizer."""

    @pytest.fixture
    def normalizer(self):
        """Create a QueryNormalizer instance."""
        return QueryNormalizer()

    def test_query_normalization_lowercase(self, normalizer):
        """Test that queries are converted to lowercase."""
        query = "What IS the WEATHER Today?"

        normalized = normalizer.normalize(query)

        assert normalized == "what is the weather today?"

    def test_query_normalization_whitespace(self, normalizer):
        """Test that extra whitespace is normalized."""
        query = "What    is   the    weather?"

        normalized = normalizer.normalize(query)

        assert "    " not in normalized
        assert "   " not in normalized

    def test_query_normalization_punctuation(self, normalizer):
        """Test that punctuation is standardized."""
        query = "What's the weather???!!"

        normalized = normalizer.normalize(query)

        # Multiple punctuation should be reduced to single
        assert "???" not in normalized
        assert "!!!" not in normalized

    def test_query_normalization_idempotency(self, normalizer):
        """Test that normalization is idempotent (applying twice gives same result)."""
        query = "What's   the WEATHER???"

        normalized1 = normalizer.normalize(query)
        normalized2 = normalizer.normalize(normalized1)

        assert normalized1 == normalized2

    def test_special_character_handling(self, normalizer):
        """Test that special characters are properly handled."""
        query = "Query with <script>alert('xss')</script> and emojis 🎉"

        normalized = normalizer.normalize(query)

        # Script tags should be removed or escaped
        assert "<script>" not in normalized

    def test_unicode_handling(self, normalizer):
        """Test that unicode characters are preserved."""
        query = "Café résumé naïve"

        normalized = normalizer.normalize(query)

        assert "café" in normalized
        assert "résumé" in normalized
        assert "naïve" in normalized

    def test_leading_trailing_whitespace(self, normalizer):
        """Test that leading/trailing whitespace is removed."""
        query = "   Weather today   "

        normalized = normalizer.normalize(query)

        assert not normalized.startswith(" ")
        assert not normalized.endswith(" ")


class TestCacheKeyGeneration:
    """Test suite for cache key generation."""

    def test_generate_simple_key(self):
        """Test basic cache key generation."""
        key = generate_cache_key("What's the weather?", "llama2", "ollama")

        assert key is not None
        assert len(key) == 64  # SHA256 hex digest
        assert key.isalnum() or all(c in "0123456789abcdef" for c in key)

    def test_cache_key_stability(self):
        """Test that same inputs produce same key."""
        key1 = generate_cache_key("Test query", "llama2", "ollama")
        key2 = generate_cache_key("Test query", "llama2", "ollama")

        assert key1 == key2

    def test_cache_key_differs_with_different_model(self):
        """Test that different models produce different keys."""
        key1 = generate_cache_key("Test query", "llama2", "ollama")
        key2 = generate_cache_key("Test query", "mistral", "ollama")

        assert key1 != key2

    def test_cache_key_differs_with_different_provider(self):
        """Test that different providers produce different keys."""
        key1 = generate_cache_key("Test query", "llama2", "ollama")
        key2 = generate_cache_key("Test query", "llama2", "lmstudio")

        assert key1 != key2

    def test_cache_key_includes_normalized_query(self):
        """Test that cache key includes normalized query."""
        key1 = generate_cache_key("What's the WEATHER?", "llama2", "ollama")
        key2 = generate_cache_key("what's the weather?", "llama2", "ollama")

        # Same normalized query should produce same key
        assert key1 == key2

    def test_cache_key_format(self):
        """Test that cache key is a valid SHA256 hex string."""
        key = generate_cache_key("Test", "model", "provider")

        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)
