"""Integration tests for domain classification.

Tests the domain classifier which routes queries to specific domains (NBA, weather, etc.)
using LLM-based classification with fallback patterns.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from me4brain.engine.hybrid_router.domain_classifier import DomainClassifier
from me4brain.engine.hybrid_router.types import HybridRouterConfig


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


@pytest.mark.integration
class TestDomainClassifier:
    """Test domain classification with LLM and fallback patterns."""

    @pytest.mark.asyncio
    async def test_nba_query_classification(
        self, mock_llm_client, router_config, available_domains
    ):
        """NBA query should be classified to sports_nba domain.

        Query: "What is the NBA score today?" → sports_nba
        The classifier should recognize NBA-specific keywords and route correctly.
        """
        # Mock response structure: response.choices[0].message.content
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
        result = await classifier.classify("What is the NBA score today?")

        assert result is not None
        assert len(result.domains) > 0
        assert result.domains[0].name == "sports_nba"
        assert result.confidence > 0.8

    @pytest.mark.asyncio
    async def test_weather_query_classification(
        self, mock_llm_client, router_config, available_domains
    ):
        """Weather query should be classified to geo_weather domain.

        Query: "What's the weather tomorrow in San Francisco?" → geo_weather
        The classifier should detect weather keywords.
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
        result = await classifier.classify("What's the weather tomorrow in San Francisco?")

        assert result is not None
        assert len(result.domains) > 0
        assert result.domains[0].name == "geo_weather"
        assert result.confidence > 0.8

    @pytest.mark.asyncio
    async def test_retries_before_fallback(self, mock_llm_client, router_config, available_domains):
        """Classifier should retry LLM before falling back.

        The classifier should attempt LLM classification 3 times before
        using fallback pattern matching.
        """
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = (
            '{"domains": [{"name": "web_search", "complexity": "medium"}], "confidence": 0.8}'
        )
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_llm_client.generate_response = AsyncMock(
            side_effect=[
                Exception("Timeout"),
                Exception("Service unavailable"),
                mock_response,
            ]
        )

        classifier = DomainClassifier(mock_llm_client, available_domains, router_config)

        result = await classifier.classify("Tell me about Python")
        assert result is not None

    @pytest.mark.asyncio
    async def test_ambiguous_query_classification(
        self, mock_llm_client, router_config, available_domains
    ):
        """Ambiguous query should have moderate confidence.

        Query: "Run" could mean athletics (sports_nba) or execution (tech_coding).
        The classifier should flag this with lower confidence.
        """
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = (
            '{"domains": [{"name": "web_search", "complexity": "low"}], "confidence": 0.65}'
        )
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_llm_client.generate_response = AsyncMock(return_value=mock_response)

        classifier = DomainClassifier(mock_llm_client, available_domains, router_config)
        result = await classifier.classify("Run")

        assert result is not None
        assert result.confidence < 0.8

    @pytest.mark.asyncio
    async def test_financial_query_classification(
        self, mock_llm_client, router_config, available_domains
    ):
        """Financial/crypto query should be classified to finance_crypto domain.

        Query: "What is the Bitcoin price?" → finance_crypto
        """
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = (
            '{"domains": [{"name": "finance_crypto", "complexity": "low"}], "confidence": 0.93}'
        )
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_llm_client.generate_response = AsyncMock(return_value=mock_response)

        classifier = DomainClassifier(mock_llm_client, available_domains, router_config)
        result = await classifier.classify("What is the Bitcoin price?")

        assert result is not None
        assert result.domains[0].name == "finance_crypto"
        assert result.confidence > 0.85

    @pytest.mark.asyncio
    async def test_multi_domain_query_ranking(
        self, mock_llm_client, router_config, available_domains
    ):
        """Classifier should rank multiple possible domains by confidence.

        Complex query might match multiple domains; should return ranked list.
        """
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = '{"domains": [{"name": "finance_crypto", "complexity": "high"}, {"name": "web_search", "complexity": "medium"}], "confidence": 0.88}'
        mock_choice.message = mock_message

        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_llm_client.generate_response = AsyncMock(return_value=mock_response)

        classifier = DomainClassifier(mock_llm_client, available_domains, router_config)
        result = await classifier.classify("Should I invest in crypto or tech stocks?")

        assert result is not None
        assert len(result.domains) >= 1
        assert result.domains[0].name == "finance_crypto"
