"""Tests for graceful degradation levels in domain classification.

Tests the DegradationLevel enum and classify_with_degradation() method
that allow the classifier to degrade gracefully when full LLM fails.
"""

import json
from unittest.mock import AsyncMock

import pytest

from me4brain.engine.hybrid_router.domain_classifier import (
    DegradationLevel,
    DomainClassifier,
)
from me4brain.engine.hybrid_router.types import (
    HybridRouterConfig,
)
from me4brain.llm.models import Choice, ChoiceMessage, LLMResponse
from me4brain.llm.nanogpt import NanoGPTClient


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Create a mock LLM client."""
    return AsyncMock(spec=NanoGPTClient)


def create_mock_response(json_content: dict) -> LLMResponse:
    """Create a mock LLMResponse with JSON content."""
    choice = Choice(message=ChoiceMessage(role="assistant", content=json.dumps(json_content)))
    return LLMResponse(model="test-model", choices=[choice])


@pytest.fixture
def classifier(mock_llm_client: AsyncMock) -> DomainClassifier:
    """Create a DomainClassifier instance."""
    config = HybridRouterConfig(
        router_model="qwen3:14b",
        decomposition_model="qwen3:14b",
        fallback_domains=["web_search"],
    )
    available_domains = [
        "geo_weather",
        "finance_crypto",
        "sports_nba",
        "web_search",
        "google_workspace",
    ]
    return DomainClassifier(mock_llm_client, available_domains, config)


class TestDegradationLevelEnum:
    """Test the DegradationLevel enum definition."""

    def test_degradation_level_has_four_levels(self) -> None:
        """DegradationLevel should have exactly 4 levels."""
        levels = list(DegradationLevel)
        assert len(levels) == 4

    def test_degradation_level_order(self) -> None:
        """Levels should be ordered from FULL_LLM to KEYWORD_ONLY."""
        assert DegradationLevel.FULL_LLM.value == 0
        assert DegradationLevel.SIMPLIFIED_LLM.value == 1
        assert DegradationLevel.HYBRID.value == 2
        assert DegradationLevel.KEYWORD_ONLY.value == 3

    def test_degradation_levels_are_comparable(self) -> None:
        """Degradation levels should be comparable by value."""
        assert DegradationLevel.FULL_LLM.value < DegradationLevel.KEYWORD_ONLY.value
        assert DegradationLevel.SIMPLIFIED_LLM.value < DegradationLevel.HYBRID.value
        assert DegradationLevel.FULL_LLM.value < DegradationLevel.KEYWORD_ONLY.value


class TestClassifyWithDegradation:
    """Test the classify_with_degradation method."""

    @pytest.mark.asyncio
    async def test_classify_with_degradation_full_llm_success(
        self, classifier: DomainClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should succeed at FULL_LLM level when response is valid."""
        # Setup mock to return valid classification
        response_json = {
            "domains": [{"name": "sports_nba", "complexity": "high"}],
            "confidence": 0.95,
            "query_summary": "NBA betting query",
        }
        mock_llm_client.generate_response.return_value = create_mock_response(response_json)

        result = await classifier.classify_with_degradation(
            query="NBA predictions for Lakers vs Celtics",
            max_degradation=DegradationLevel.KEYWORD_ONLY,
        )

        assert result is not None
        assert "sports_nba" in result.domain_names

    @pytest.mark.asyncio
    async def test_classify_with_degradation_stops_on_high_confidence(
        self, classifier: DomainClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should stop degrading if confidence exceeds 0.5."""
        high_confidence_response = {
            "domains": [{"name": "google_workspace", "complexity": "low"}],
            "confidence": 0.92,
            "query_summary": "Gmail query",
        }
        mock_llm_client.generate_response.return_value = create_mock_response(
            high_confidence_response
        )

        result = await classifier.classify_with_degradation(
            query="Send email to John",
            max_degradation=DegradationLevel.KEYWORD_ONLY,
        )

        assert result is not None
        assert result.confidence == 0.92
        # Should have stopped at first attempt (high confidence)
        assert mock_llm_client.generate_response.call_count == 1

    @pytest.mark.asyncio
    async def test_classify_with_degradation_falls_back_to_keyword(
        self, classifier: DomainClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should use keyword fallback when all LLM levels fail."""
        # Mock raises exception to simulate all LLM calls failing
        mock_llm_client.generate_response.side_effect = Exception("Connection failed")

        result = await classifier.classify_with_degradation(
            query="Meteo a Milano domani",
            max_degradation=DegradationLevel.KEYWORD_ONLY,
        )

        # Should still return classification via keyword detection
        assert result is not None
        assert "geo_weather" in result.domain_names
        assert result.confidence == 0.6  # Fallback confidence

    @pytest.mark.asyncio
    async def test_classify_with_degradation_max_level_respected(
        self, classifier: DomainClassifier, mock_llm_client: AsyncMock
    ) -> None:
        """Should respect max_degradation parameter."""
        valid_response = {
            "domains": [{"name": "web_search", "complexity": "low"}],
            "confidence": 0.8,
            "query_summary": "Search query",
        }
        mock_llm_client.generate_response.return_value = create_mock_response(valid_response)

        # Restrict to FULL_LLM only
        result = await classifier.classify_with_degradation(
            query="Find information about Python",
            max_degradation=DegradationLevel.FULL_LLM,
        )

        assert result is not None
        # Should have called LLM only once (FULL_LLM level)
        assert mock_llm_client.generate_response.call_count == 1

    @pytest.mark.asyncio
    async def test_degradation_level_names_match_enum(self) -> None:
        """Verify all degradation levels have proper names."""
        assert DegradationLevel.FULL_LLM.name == "FULL_LLM"
        assert DegradationLevel.SIMPLIFIED_LLM.name == "SIMPLIFIED_LLM"
        assert DegradationLevel.HYBRID.name == "HYBRID"
        assert DegradationLevel.KEYWORD_ONLY.name == "KEYWORD_ONLY"
