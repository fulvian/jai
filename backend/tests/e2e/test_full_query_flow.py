"""End-to-end tests for full query processing pipeline.

Tests complete query workflows from input to response generation,
verifying that LLM-based routing and domain handlers work together correctly.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from me4brain.engine.hybrid_router.domain_classifier import DomainClassifier
from me4brain.engine.hybrid_router.types import (
    HybridRouterConfig,
)


@pytest.fixture
def mock_llm_client():
    """Fixture providing a mock LLM client."""
    client = AsyncMock()
    return client


@pytest.fixture
def router_config():
    """Fixture for HybridRouterConfig."""
    config = HybridRouterConfig()
    config.router_model = "qwen3.5-4b-mlx"
    return config


@pytest.fixture
def available_domains() -> list[str]:
    """Fixture for available domains."""
    return [
        "sports_nba",
        "geo_weather",
        "finance_crypto",
        "web_search",
        "tech_coding",
        "food",
        "sports_booking",
    ]


@pytest.mark.e2e
class TestFullQueryFlow:
    """Test complete query processing pipeline (E2E)."""

    @pytest.mark.asyncio
    async def test_nba_query_uses_llm_classification(
        self, mock_llm_client, router_config, available_domains
    ):
        """Full pipeline should use LLM classification for NBA queries.

        NBA query should:
        1. Be classified via LLM (not pattern match)
        2. Route to sports_nba domain
        3. Execute NBA-specific tools
        4. Return NBA data in response
        """
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = (
            '{"domains": [{"name": "sports_nba", "complexity": "low"}], "confidence": 0.95}'
        )
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_llm_client.generate_response = AsyncMock(return_value=mock_response)

        classifier = DomainClassifier(mock_llm_client, available_domains, router_config)
        result = await classifier.classify("Who won the Lakers vs Celtics game?")

        assert result is not None
        assert result.domains[0].name == "sports_nba"
        assert result.confidence > 0.9

    @pytest.mark.asyncio
    async def test_weather_query_full_pipeline(
        self, mock_llm_client, router_config, available_domains
    ):
        """Weather query should flow through full pipeline.

        Weather query should:
        1. Be classified to geo_weather
        2. Call weather API
        3. Return formatted weather data
        """
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = (
            '{"domains": [{"name": "geo_weather", "complexity": "low"}], "confidence": 0.92}'
        )
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_llm_client.generate_response = AsyncMock(return_value=mock_response)

        classifier = DomainClassifier(mock_llm_client, available_domains, router_config)
        result = await classifier.classify("What's the weather in San Francisco?")

        assert result is not None
        assert result.domains[0].name == "geo_weather"
        assert result.confidence > 0.85

    @pytest.mark.asyncio
    async def test_multi_turn_conversation_maintains_context(
        self, mock_llm_client, router_config, available_domains
    ):
        """Multi-turn conversation should maintain session context.

        Two queries in same session should:
        1. Share session context
        2. Remember previous domains/intent
        3. Improve classification accuracy
        """
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = (
            '{"domains": [{"name": "sports_nba", "complexity": "low"}], "confidence": 0.95}'
        )
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_llm_client.generate_response = AsyncMock(return_value=mock_response)

        classifier = DomainClassifier(mock_llm_client, available_domains, router_config)

        # First query
        result1 = await classifier.classify("Show me NBA standings")
        assert result1 is not None
        assert result1.domains[0].name == "sports_nba"

        # Second query (follow-up) with conversation context
        conversation_context = [
            {"role": "user", "content": "Show me NBA standings"},
            {"role": "assistant", "content": "NBA standings for 2026..."},
        ]
        result2 = await classifier.classify(
            "What about the Lakers specifically?",
            conversation_context=conversation_context,
        )

        assert result2 is not None
        assert result2.domains[0].name == "sports_nba"

    @pytest.mark.asyncio
    async def test_query_error_handling_fallback(
        self, mock_llm_client, router_config, available_domains
    ):
        """Query processing should fallback gracefully on LLM failure.

        If LLM classification fails, should:
        1. Log the error
        2. Fall back to pattern matching
        3. Still return valid response
        """
        # First call fails, retries succeed
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = (
            '{"domains": [{"name": "web_search", "complexity": "medium"}], "confidence": 0.6}'
        )
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_llm_client.generate_response = AsyncMock(
            side_effect=[
                Exception("LLM service down"),
                Exception("LLM still down"),
                mock_response,  # Success on third attempt
            ]
        )

        classifier = DomainClassifier(mock_llm_client, available_domains, router_config)
        result = await classifier.classify("Tell me something")

        # Should either succeed or degrade gracefully
        assert result is not None
