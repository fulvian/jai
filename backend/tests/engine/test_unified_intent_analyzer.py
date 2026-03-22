"""Unit Tests for UnifiedIntentAnalyzer.

Tests for:
- 4.1 Weather query classification (Italian and English)
- 4.2 Conversational query classification (greetings, farewells, small talk)
- 4.3 Price query classification
- 4.4 Search query classification
- 4.5 Multi-domain query classification
- 4.6 Complexity assessment (simple, moderate, complex)
- 4.7 Confidence score calculation
- 4.8 Error handling (LLM failure, JSON parse failure, empty query)
- 4.9 Prompt construction with and without context
- 4.10 Fallback behavior
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from me4brain.engine.unified_intent_analyzer import (
    UnifiedIntentAnalyzer,
    IntentType,
    QueryComplexity,
    IntentAnalysis,
)
from me4brain.llm.models import LLMResponse, Choice, ChoiceMessage, Usage
from me4brain.llm.config import get_llm_config


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    return AsyncMock()


@pytest.fixture
def analyzer(mock_llm_client):
    """Create an UnifiedIntentAnalyzer instance with mock LLM client."""
    config = get_llm_config()
    analyzer = UnifiedIntentAnalyzer(mock_llm_client, config)
    return analyzer


def create_llm_response(content: str) -> LLMResponse:
    """Helper to create LLM response."""
    return LLMResponse(
        model="test-model",
        choices=[
            Choice(
                index=0,
                message=ChoiceMessage(role="assistant", content=content),
            )
        ],
        usage=Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    )


class TestWeatherQueryClassification:
    """Test 4.1: Weather query classification (Italian and English)."""

    @pytest.mark.asyncio
    async def test_weather_query_italian_che_tempo_fa(self, analyzer, mock_llm_client):
        """Test Italian weather query: 'Che tempo fa a Caltanissetta?'"""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": "simple",
                "confidence": 0.95,
                "reasoning": "Weather query asking for current conditions",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("Che tempo fa a Caltanissetta?")

        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "geo_weather" in analysis.domains
        assert analysis.confidence >= 0.8
        assert analysis.complexity == QueryComplexity.SIMPLE

    @pytest.mark.asyncio
    async def test_weather_query_italian_meteo(self, analyzer, mock_llm_client):
        """Test Italian weather query: 'meteo a Roma'"""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": "simple",
                "confidence": 0.92,
                "reasoning": "Weather query for Rome",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("meteo a Roma")

        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "geo_weather" in analysis.domains

    @pytest.mark.asyncio
    async def test_weather_query_english(self, analyzer, mock_llm_client):
        """Test English weather query: 'weather in Milan'"""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": "simple",
                "confidence": 0.93,
                "reasoning": "Weather query for Milan",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("weather in Milan")

        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "geo_weather" in analysis.domains

    @pytest.mark.asyncio
    async def test_weather_query_temperature(self, analyzer, mock_llm_client):
        """Test temperature query: 'temperatura Napoli'"""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": "simple",
                "confidence": 0.91,
                "reasoning": "Temperature query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("temperatura Napoli")

        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "geo_weather" in analysis.domains


class TestConversationalQueryClassification:
    """Test 4.2: Conversational query classification."""

    @pytest.mark.asyncio
    async def test_greeting_ciao(self, analyzer, mock_llm_client):
        """Test greeting: 'ciao'"""
        response_content = json.dumps(
            {
                "intent": "conversational",
                "domains": [],
                "complexity": "simple",
                "confidence": 0.99,
                "reasoning": "Greeting",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("ciao")

        assert analysis.intent == IntentType.CONVERSATIONAL
        assert analysis.domains == []

    @pytest.mark.asyncio
    async def test_greeting_hello(self, analyzer, mock_llm_client):
        """Test greeting: 'hello'"""
        response_content = json.dumps(
            {
                "intent": "conversational",
                "domains": [],
                "complexity": "simple",
                "confidence": 0.98,
                "reasoning": "Greeting",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("hello")

        assert analysis.intent == IntentType.CONVERSATIONAL
        assert analysis.domains == []

    @pytest.mark.asyncio
    async def test_farewell_arrivederci(self, analyzer, mock_llm_client):
        """Test farewell: 'arrivederci'"""
        response_content = json.dumps(
            {
                "intent": "conversational",
                "domains": [],
                "complexity": "simple",
                "confidence": 0.99,
                "reasoning": "Farewell",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("arrivederci")

        assert analysis.intent == IntentType.CONVERSATIONAL
        assert analysis.domains == []

    @pytest.mark.asyncio
    async def test_small_talk_come_stai(self, analyzer, mock_llm_client):
        """Test small talk: 'come stai?'"""
        response_content = json.dumps(
            {
                "intent": "conversational",
                "domains": [],
                "complexity": "simple",
                "confidence": 0.97,
                "reasoning": "Small talk",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("come stai?")

        assert analysis.intent == IntentType.CONVERSATIONAL
        assert analysis.domains == []

    @pytest.mark.asyncio
    async def test_meta_question_chi_sei(self, analyzer, mock_llm_client):
        """Test meta question: 'chi sei?'"""
        response_content = json.dumps(
            {
                "intent": "conversational",
                "domains": [],
                "complexity": "simple",
                "confidence": 0.96,
                "reasoning": "Meta question about bot",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("chi sei?")

        assert analysis.intent == IntentType.CONVERSATIONAL
        assert analysis.domains == []


class TestPriceQueryClassification:
    """Test 4.3: Price query classification."""

    @pytest.mark.asyncio
    async def test_price_query_bitcoin(self, analyzer, mock_llm_client):
        """Test price query: 'qual è il prezzo del Bitcoin?'"""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["finance_crypto"],
                "complexity": "simple",
                "confidence": 0.94,
                "reasoning": "Cryptocurrency price query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("qual è il prezzo del Bitcoin?")

        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "finance_crypto" in analysis.domains

    @pytest.mark.asyncio
    async def test_price_query_ethereum(self, analyzer, mock_llm_client):
        """Test price query: 'prezzo ethereum'"""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["finance_crypto"],
                "complexity": "simple",
                "confidence": 0.93,
                "reasoning": "Cryptocurrency price query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("prezzo ethereum")

        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "finance_crypto" in analysis.domains


class TestSearchQueryClassification:
    """Test 4.4: Search query classification."""

    @pytest.mark.asyncio
    async def test_search_query_news(self, analyzer, mock_llm_client):
        """Test search query: 'cerca notizie su Roma'"""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["web_search"],
                "complexity": "simple",
                "confidence": 0.91,
                "reasoning": "Web search query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("cerca notizie su Roma")

        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "web_search" in analysis.domains

    @pytest.mark.asyncio
    async def test_search_query_english(self, analyzer, mock_llm_client):
        """Test search query: 'search for latest news'"""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["web_search"],
                "complexity": "simple",
                "confidence": 0.90,
                "reasoning": "Web search query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("search for latest news")

        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "web_search" in analysis.domains


class TestMultiDomainQueryClassification:
    """Test 4.5: Multi-domain query classification."""

    @pytest.mark.asyncio
    async def test_weather_and_price_query(self, analyzer, mock_llm_client):
        """Test multi-domain: 'Che tempo fa a Roma e qual è il prezzo del Bitcoin?'"""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather", "finance_crypto"],
                "complexity": "complex",
                "confidence": 0.88,
                "reasoning": "Multi-domain query: weather and cryptocurrency price",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("Che tempo fa a Roma e qual è il prezzo del Bitcoin?")

        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "geo_weather" in analysis.domains
        assert "finance_crypto" in analysis.domains
        assert analysis.complexity == QueryComplexity.COMPLEX

    @pytest.mark.asyncio
    async def test_search_and_weather_query(self, analyzer, mock_llm_client):
        """Test multi-domain: 'cerca notizie sul meteo'"""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["web_search", "geo_weather"],
                "complexity": "moderate",
                "confidence": 0.85,
                "reasoning": "Multi-domain query: search and weather",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("cerca notizie sul meteo")

        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert len(analysis.domains) >= 1


class TestComplexityAssessment:
    """Test 4.6: Complexity assessment."""

    @pytest.mark.asyncio
    async def test_simple_complexity(self, analyzer, mock_llm_client):
        """Test simple complexity: single tool, single domain."""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": "simple",
                "confidence": 0.95,
                "reasoning": "Simple weather query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("meteo Roma")

        assert analysis.complexity == QueryComplexity.SIMPLE

    @pytest.mark.asyncio
    async def test_moderate_complexity(self, analyzer, mock_llm_client):
        """Test moderate complexity: multiple tools, single domain."""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": "moderate",
                "confidence": 0.90,
                "reasoning": "Weather query with forecast",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("meteo Roma e previsioni per domani")

        assert analysis.complexity == QueryComplexity.MODERATE

    @pytest.mark.asyncio
    async def test_complex_complexity(self, analyzer, mock_llm_client):
        """Test complex complexity: multiple tools, multiple domains."""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather", "finance_crypto", "web_search"],
                "complexity": "complex",
                "confidence": 0.85,
                "reasoning": "Complex multi-domain query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze(
            "Che tempo fa a Roma, qual è il prezzo del Bitcoin e quali sono le ultime notizie?"
        )

        assert analysis.complexity == QueryComplexity.COMPLEX


class TestConfidenceScoreCalculation:
    """Test 4.7: Confidence score calculation."""

    @pytest.mark.asyncio
    async def test_high_confidence_score(self, analyzer, mock_llm_client):
        """Test high confidence score."""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": "simple",
                "confidence": 0.98,
                "reasoning": "Clear weather query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("meteo Roma")

        assert analysis.confidence >= 0.95

    @pytest.mark.asyncio
    async def test_medium_confidence_score(self, analyzer, mock_llm_client):
        """Test medium confidence score."""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["web_search"],
                "complexity": "simple",
                "confidence": 0.75,
                "reasoning": "Ambiguous query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("cosa mi consigli?")

        assert 0.0 <= analysis.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_confidence_bounds(self, analyzer, mock_llm_client):
        """Test confidence score is within bounds [0.0, 1.0]."""
        response_content = json.dumps(
            {
                "intent": "conversational",
                "domains": [],
                "complexity": "simple",
                "confidence": 0.99,
                "reasoning": "Greeting",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("ciao")

        assert 0.0 <= analysis.confidence <= 1.0


class TestErrorHandling:
    """Test 4.8: Error handling."""

    @pytest.mark.asyncio
    async def test_llm_api_failure(self, analyzer, mock_llm_client):
        """Test LLM API failure handling."""
        mock_llm_client.generate_response.side_effect = Exception("LLM API error")

        analysis = await analyzer.analyze("meteo Roma")

        # Should fallback to safe default
        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "general" in analysis.domains
        assert analysis.confidence == 0.5
        assert "fallback:" in analysis.reasoning

    @pytest.mark.asyncio
    async def test_json_parse_failure(self, analyzer, mock_llm_client):
        """Test JSON parse failure handling."""
        response_content = "invalid json {{"
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("meteo Roma")

        # Should fallback to safe default
        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "general" in analysis.domains
        assert analysis.confidence == 0.5
        assert "fallback:" in analysis.reasoning

    @pytest.mark.asyncio
    async def test_empty_query(self, analyzer, mock_llm_client):
        """Test empty query handling."""
        # Empty query should be handled before LLM call
        analysis = await analyzer.analyze("")

        # Should return conversational intent
        assert analysis.intent == IntentType.CONVERSATIONAL
        assert analysis.domains == []

    @pytest.mark.asyncio
    async def test_whitespace_only_query(self, analyzer, mock_llm_client):
        """Test whitespace-only query handling."""
        analysis = await analyzer.analyze("   ")

        # Should return conversational intent
        assert analysis.intent == IntentType.CONVERSATIONAL
        assert analysis.domains == []

    @pytest.mark.asyncio
    async def test_invalid_domain_in_response(self, analyzer, mock_llm_client):
        """Test handling of invalid domain in LLM response."""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather", "invalid_domain"],
                "complexity": "simple",
                "confidence": 0.90,
                "reasoning": "Query with invalid domain",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("meteo Roma")

        # Should filter out invalid domains
        assert "geo_weather" in analysis.domains
        assert "invalid_domain" not in analysis.domains


class TestPromptConstruction:
    """Test 4.9: Prompt construction with and without context."""

    def test_prompt_construction_without_context(self, analyzer):
        """Test prompt construction without context."""
        prompt = analyzer._build_intent_prompt("meteo Roma", context=None)

        assert "intent" in prompt.lower()
        assert "conversational" in prompt.lower()
        assert "tool_required" in prompt.lower()
        assert "domains" in prompt.lower()
        assert "geo_weather" in prompt.lower()

    def test_prompt_construction_with_context(self, analyzer):
        """Test prompt construction with context."""
        context = "User is asking about weather in Italy"
        prompt = analyzer._build_intent_prompt("meteo Roma", context=context)

        assert "intent" in prompt.lower()
        assert context in prompt

    def test_prompt_includes_domain_definitions(self, analyzer):
        """Test that prompt includes all domain definitions."""
        prompt = analyzer._build_intent_prompt("test query")

        # Check for key domains
        assert "geo_weather" in prompt
        assert "finance_crypto" in prompt
        assert "web_search" in prompt

    def test_prompt_includes_critical_rules(self, analyzer):
        """Test that prompt includes critical classification rules."""
        prompt = analyzer._build_intent_prompt("test query")

        # Check for critical rules
        assert "weather" in prompt.lower()
        assert "price" in prompt.lower()
        assert "search" in prompt.lower()


class TestFallbackBehavior:
    """Test 4.10: Fallback behavior."""

    @pytest.mark.asyncio
    async def test_fallback_on_llm_timeout(self, analyzer, mock_llm_client):
        """Test fallback behavior on LLM timeout."""
        import asyncio

        async def timeout_side_effect(*args, **kwargs):
            await asyncio.sleep(10)

        mock_llm_client.generate_response.side_effect = asyncio.TimeoutError()

        analysis = await analyzer.analyze("meteo Roma")

        # Should fallback to safe default
        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert "general" in analysis.domains

    @pytest.mark.asyncio
    async def test_fallback_preserves_query_info(self, analyzer, mock_llm_client):
        """Test that fallback preserves query information."""
        mock_llm_client.generate_response.side_effect = Exception("LLM error")

        analysis = await analyzer.analyze("meteo Roma")

        # Fallback should still have valid structure
        assert isinstance(analysis.intent, IntentType)
        assert isinstance(analysis.domains, list)
        assert isinstance(analysis.complexity, QueryComplexity)
        assert isinstance(analysis.confidence, float)
        assert isinstance(analysis.reasoning, str)

    @pytest.mark.asyncio
    async def test_fallback_reasoning_indicates_error(self, analyzer, mock_llm_client):
        """Test that fallback reasoning indicates error occurred."""
        mock_llm_client.generate_response.side_effect = Exception("LLM error")

        analysis = await analyzer.analyze("meteo Roma")

        # Reasoning should indicate fallback
        assert "fallback:" in analysis.reasoning


class TestIntentAnalysisValidation:
    """Test IntentAnalysis validation."""

    @pytest.mark.asyncio
    async def test_conversational_intent_has_empty_domains(self, analyzer, mock_llm_client):
        """Test that conversational intent always has empty domains."""
        response_content = json.dumps(
            {
                "intent": "conversational",
                "domains": [],
                "complexity": "simple",
                "confidence": 0.99,
                "reasoning": "Greeting",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("ciao")

        assert analysis.intent == IntentType.CONVERSATIONAL
        assert analysis.domains == []

    @pytest.mark.asyncio
    async def test_tool_required_intent_has_non_empty_domains(self, analyzer, mock_llm_client):
        """Test that tool_required intent has non-empty domains."""
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": "simple",
                "confidence": 0.95,
                "reasoning": "Weather query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("meteo Roma")

        assert analysis.intent == IntentType.TOOL_REQUIRED
        assert len(analysis.domains) > 0

    def test_intent_analysis_to_dict(self, analyzer):
        """Test IntentAnalysis.to_dict() method."""
        analysis = IntentAnalysis(
            intent=IntentType.TOOL_REQUIRED,
            domains=["geo_weather"],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="Weather query",
        )

        result_dict = analysis.to_dict()

        assert result_dict["intent"] == "tool_required"
        assert "geo_weather" in result_dict["domains"]
        assert result_dict["complexity"] == "simple"
        assert result_dict["confidence"] == 0.95
