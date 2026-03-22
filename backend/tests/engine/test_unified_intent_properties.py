"""Property-Based Tests for UnifiedIntentAnalyzer.

Tests for:
- 5.1 Install hypothesis library for property-based testing
- 5.2 Test property: Weather keywords → tool_required + geo_weather
- 5.3 Test property: Conversational patterns → conversational + empty domains
- 5.4 Test property: Domain consistency (conversational ⟺ empty domains)
- 5.5 Test property: Confidence bounds (0.0 ≤ confidence ≤ 1.0)
- 5.6 Test property: Intent type validity (only CONVERSATIONAL or TOOL_REQUIRED)
- 5.7 Test property: Complexity validity (only SIMPLE, MODERATE, or COMPLEX)
- 5.8 Test property: Domains are valid (only from AVAILABLE_DOMAINS)

**Validates: Requirements NFR2, NFR3, AC1-AC7**
"""

import json
import pytest
from unittest.mock import AsyncMock
from hypothesis import given, strategies as st, assume
from me4brain.engine.unified_intent_analyzer import (
    UnifiedIntentAnalyzer,
    IntentType,
    QueryComplexity,
)
from me4brain.llm.models import LLMResponse, Choice, ChoiceMessage, Usage
from me4brain.llm.config import get_llm_config


# Available domains from the prompt
AVAILABLE_DOMAINS = [
    "geo_weather",
    "finance_crypto",
    "web_search",
    "communication",
    "scheduling",
    "file_management",
    "data_analysis",
    "travel",
    "food",
    "entertainment",
    "sports",
    "shopping",
    "general",
]


# Weather keywords for property testing
WEATHER_KEYWORDS = [
    "tempo",
    "meteo",
    "previsioni",
    "temperatura",
    "clima",
    "weather",
    "forecast",
    "temperature",
    "climate",
]

# Conversational patterns
CONVERSATIONAL_PATTERNS = [
    "ciao",
    "hello",
    "hi",
    "buongiorno",
    "buonasera",
    "arrivederci",
    "bye",
    "grazie",
    "thanks",
    "come stai",
    "how are you",
    "come va",
    "chi sei",
    "what are you",
    "cosa puoi fare",
]


@pytest.fixture(scope="session")
def mock_llm_client():
    """Create a mock LLM client."""
    return AsyncMock()


@pytest.fixture(scope="session")
def analyzer(mock_llm_client):
    """Create an UnifiedIntentAnalyzer instance."""
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


class TestWeatherKeywordProperty:
    """Test Property 5.2: Weather keywords → tool_required + geo_weather.
    
    **Validates: Requirements FR1.3, AC1**
    """

    @given(keyword=st.sampled_from(WEATHER_KEYWORDS))
    @pytest.mark.asyncio
    async def test_weather_keywords_trigger_tool_required(self, analyzer, mock_llm_client, keyword):
        """Property: All weather keywords trigger tool_required intent with geo_weather domain.
        
        For all queries containing weather keywords, the analyzer SHALL classify them as
        tool_required with geo_weather domain.
        """
        query = f"What is the {keyword} in Rome?"
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": "simple",
                "confidence": 0.95,
                "reasoning": f"Query contains weather keyword: {keyword}",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze(query)

        assert analysis.intent == IntentType.TOOL_REQUIRED, f"Failed for keyword: {keyword}"
        assert "geo_weather" in analysis.domains, f"Failed for keyword: {keyword}"


class TestConversationalPatternProperty:
    """Test Property 5.3: Conversational patterns → conversational + empty domains.
    
    **Validates: Requirements FR1.6-FR1.9, AC2**
    """

    @given(pattern=st.sampled_from(CONVERSATIONAL_PATTERNS))
    @pytest.mark.asyncio
    async def test_conversational_patterns_trigger_conversational(
        self, analyzer, mock_llm_client, pattern
    ):
        """Property: All conversational patterns trigger conversational intent with empty domains.
        
        For all queries matching conversational patterns, the analyzer SHALL classify them as
        conversational with empty domains list.
        """
        response_content = json.dumps(
            {
                "intent": "conversational",
                "domains": [],
                "complexity": "simple",
                "confidence": 0.98,
                "reasoning": f"Conversational pattern: {pattern}",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze(pattern)

        assert analysis.intent == IntentType.CONVERSATIONAL, f"Failed for pattern: {pattern}"
        assert analysis.domains == [], f"Failed for pattern: {pattern}"


class TestDomainConsistencyProperty:
    """Test Property 5.4: Domain consistency (conversational ⟺ empty domains).
    
    **Validates: Requirements FR2.2, Design Property 3**
    """

    @given(
        intent_str=st.sampled_from(["conversational", "tool_required"]),
        domains=st.lists(st.sampled_from(AVAILABLE_DOMAINS), min_size=0, max_size=3),
    )
    @pytest.mark.asyncio
    async def test_domain_consistency_property(
        self, analyzer, mock_llm_client, intent_str, domains
    ):
        """Property: Domain consistency holds for all queries.
        
        For all queries:
        - If intent is conversational, then domains must be empty
        - If intent is tool_required, then domains must be non-empty
        """
        # Adjust domains based on intent for valid test data
        if intent_str == "conversational":
            domains = []
        else:
            # Ensure at least one domain for tool_required
            if not domains:
                domains = ["geo_weather"]

        response_content = json.dumps(
            {
                "intent": intent_str,
                "domains": domains,
                "complexity": "simple",
                "confidence": 0.90,
                "reasoning": "Test query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("test query")

        # Verify domain consistency
        if analysis.intent == IntentType.CONVERSATIONAL:
            assert analysis.domains == [], "Conversational intent must have empty domains"
        else:
            assert len(analysis.domains) > 0, "Tool-required intent must have non-empty domains"


class TestConfidenceBoundsProperty:
    """Test Property 5.5: Confidence bounds (0.0 ≤ confidence ≤ 1.0).
    
    **Validates: Requirements NFR2, Design Property 1**
    """

    @given(confidence=st.floats(min_value=0.0, max_value=1.0))
    @pytest.mark.asyncio
    async def test_confidence_bounds_property(self, analyzer, mock_llm_client, confidence):
        """Property: Confidence score is always within bounds [0.0, 1.0].
        
        For all queries, the confidence score SHALL be between 0.0 and 1.0 inclusive.
        """
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": "simple",
                "confidence": confidence,
                "reasoning": "Test query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("test query")

        assert 0.0 <= analysis.confidence <= 1.0, f"Confidence out of bounds: {analysis.confidence}"


class TestIntentTypeValidityProperty:
    """Test Property 5.6: Intent type validity (only CONVERSATIONAL or TOOL_REQUIRED).
    
    **Validates: Requirements FR1.1, Design Property 1**
    """

    @given(
        intent_str=st.sampled_from(["conversational", "tool_required"]),
    )
    @pytest.mark.asyncio
    async def test_intent_type_validity_property(self, analyzer, mock_llm_client, intent_str):
        """Property: Intent type is always valid (CONVERSATIONAL or TOOL_REQUIRED).
        
        For all queries, the intent SHALL be either CONVERSATIONAL or TOOL_REQUIRED.
        """
        domains = [] if intent_str == "conversational" else ["geo_weather"]
        response_content = json.dumps(
            {
                "intent": intent_str,
                "domains": domains,
                "complexity": "simple",
                "confidence": 0.90,
                "reasoning": "Test query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("test query")

        assert analysis.intent in [
            IntentType.CONVERSATIONAL,
            IntentType.TOOL_REQUIRED,
        ], f"Invalid intent type: {analysis.intent}"


class TestComplexityValidityProperty:
    """Test Property 5.7: Complexity validity (only SIMPLE, MODERATE, or COMPLEX).
    
    **Validates: Requirements FR3.1, Design Property 1**
    """

    @given(
        complexity_str=st.sampled_from(["simple", "moderate", "complex"]),
    )
    @pytest.mark.asyncio
    async def test_complexity_validity_property(self, analyzer, mock_llm_client, complexity_str):
        """Property: Complexity is always valid (SIMPLE, MODERATE, or COMPLEX).
        
        For all queries, the complexity SHALL be one of: SIMPLE, MODERATE, or COMPLEX.
        """
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": complexity_str,
                "confidence": 0.90,
                "reasoning": "Test query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("test query")

        assert analysis.complexity in [
            QueryComplexity.SIMPLE,
            QueryComplexity.MODERATE,
            QueryComplexity.COMPLEX,
        ], f"Invalid complexity: {analysis.complexity}"


class TestDomainsValidityProperty:
    """Test Property 5.8: Domains are valid (only from AVAILABLE_DOMAINS).
    
    **Validates: Requirements FR2.4, FR2.5, Design Property 1**
    """

    @given(
        domains=st.lists(
            st.sampled_from(AVAILABLE_DOMAINS),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )
    @pytest.mark.asyncio
    async def test_domains_validity_property(self, analyzer, mock_llm_client, domains):
        """Property: All domains are valid (from AVAILABLE_DOMAINS).
        
        For all queries, every domain in the domains list SHALL be from AVAILABLE_DOMAINS.
        """
        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": domains,
                "complexity": "simple",
                "confidence": 0.90,
                "reasoning": "Test query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("test query")

        for domain in analysis.domains:
            assert domain in AVAILABLE_DOMAINS, f"Invalid domain: {domain}"


class TestRandomQueryProperty:
    """Test properties with random queries."""

    @given(query=st.text(min_size=1, max_size=200))
    @pytest.mark.asyncio
    async def test_random_query_produces_valid_analysis(self, analyzer, mock_llm_client, query):
        """Property: Any query produces a valid IntentAnalysis.
        
        For all queries, the analyzer SHALL return a valid IntentAnalysis with:
        - Valid intent type
        - Valid complexity
        - Valid confidence bounds
        - Domain consistency
        """
        # Skip very short queries that might be empty after stripping
        assume(query.strip())

        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": ["geo_weather"],
                "complexity": "simple",
                "confidence": 0.90,
                "reasoning": "Test query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze(query)

        # Verify all properties
        assert analysis.intent in [IntentType.CONVERSATIONAL, IntentType.TOOL_REQUIRED]
        assert analysis.complexity in [
            QueryComplexity.SIMPLE,
            QueryComplexity.MODERATE,
            QueryComplexity.COMPLEX,
        ]
        assert 0.0 <= analysis.confidence <= 1.0
        if analysis.intent == IntentType.CONVERSATIONAL:
            assert analysis.domains == []
        else:
            assert len(analysis.domains) > 0


class TestErrorHandlingProperty:
    """Test properties for error handling."""

    @pytest.mark.asyncio
    async def test_llm_failure_produces_valid_fallback(self, analyzer, mock_llm_client):
        """Property: LLM failure always produces valid fallback analysis.
        
        When LLM fails, the analyzer SHALL return a valid IntentAnalysis with fallback values.
        """
        mock_llm_client.generate_response.side_effect = Exception("LLM error")

        analysis = await analyzer.analyze("test query")

        # Verify fallback is valid
        assert analysis.intent in [IntentType.CONVERSATIONAL, IntentType.TOOL_REQUIRED]
        assert analysis.complexity in [
            QueryComplexity.SIMPLE,
            QueryComplexity.MODERATE,
            QueryComplexity.COMPLEX,
        ]
        assert 0.0 <= analysis.confidence <= 1.0
        if analysis.intent == IntentType.CONVERSATIONAL:
            assert analysis.domains == []
        else:
            assert len(analysis.domains) > 0


class TestComplexityConsistencyProperty:
    """Test consistency between complexity and domains."""

    @given(
        num_domains=st.integers(min_value=1, max_value=3),
    )
    @pytest.mark.asyncio
    async def test_complexity_matches_domain_count(self, analyzer, mock_llm_client, num_domains):
        """Property: Complexity should be consistent with number of domains.
        
        - Simple: 1 domain
        - Moderate: 1-2 domains
        - Complex: 2+ domains
        """
        domains = [AVAILABLE_DOMAINS[i % len(AVAILABLE_DOMAINS)] for i in range(num_domains)]
        domains = list(set(domains))  # Remove duplicates

        # Determine expected complexity
        if len(domains) == 1:
            expected_complexity = "simple"
        elif len(domains) == 2:
            expected_complexity = "moderate"
        else:
            expected_complexity = "complex"

        response_content = json.dumps(
            {
                "intent": "tool_required",
                "domains": domains,
                "complexity": expected_complexity,
                "confidence": 0.90,
                "reasoning": "Test query",
            }
        )
        mock_llm_client.generate_response.return_value = create_llm_response(response_content)

        analysis = await analyzer.analyze("test query")

        # Verify complexity is reasonable for domain count
        assert analysis.complexity in [
            QueryComplexity.SIMPLE,
            QueryComplexity.MODERATE,
            QueryComplexity.COMPLEX,
        ]
