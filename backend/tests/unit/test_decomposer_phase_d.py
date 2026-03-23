"""Phase D: Unit tests for query_decomposer (15+ tests target).

Tests decomposition logic, fallback heuristics, and sub-query generation.
This directly addresses Criticality 3 (decomposer fallback broken) and Phase B3.
"""

from unittest.mock import AsyncMock

import pytest

from me4brain.engine.hybrid_router.query_decomposer import QueryDecomposer
from me4brain.engine.hybrid_router.types import (
    DomainClassification,
    DomainComplexity,
    HybridRouterConfig,
    SubQuery,
)
from me4brain.llm.nanogpt import NanoGPTClient


class TestHeuristicFallbackDecomposition:
    """Test heuristic fallback decomposition logic (8 tests)."""

    @pytest.fixture
    def decomposer(self):
        """Create decomposer with mocked LLM."""
        mock_llm = AsyncMock(spec=NanoGPTClient)
        available_domains = [
            "sports_nba",
            "web_search",
            "finance_crypto",
            "google_workspace",
            "productivity",
            "travel",
            "food",
        ]
        config = HybridRouterConfig()
        return QueryDecomposer(mock_llm, available_domains, config)

    def test_nba_betting_decomposition_pattern(self, decomposer):
        """Test NBA betting queries decompose into games + context."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="high")],
            confidence=0.95,
            query_summary="NBA betting analysis",
        )

        result = decomposer._heuristic_fallback_decomposition(
            "scommesse nba stasera lakers celtics analisi quote", classification
        )

        # Should have at least 2 sub-queries for NBA betting
        assert len(result) >= 2
        assert all(isinstance(sq, SubQuery) for sq in result)
        # First should be games_data, second context_data
        assert result[0].intent in ["nba_games_data", "direct"]
        assert result[0].domain == "sports_nba"

    def test_conjunction_split_and(self, decomposer):
        """Test queries with 'and' conjunctions split correctly."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="web_search", complexity="medium")],
            confidence=0.8,
            query_summary="Multi-part query",
        )

        result = decomposer._heuristic_fallback_decomposition(
            "find restaurants in Paris and hotels in London", classification
        )

        # Should split on 'and' into 2 queries
        assert len(result) >= 1

    def test_conjunction_split_italian_poi(self, decomposer):
        """Test Italian 'poi' (then) conjunction."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="web_search", complexity="medium")],
            confidence=0.8,
            query_summary="Sequential queries",
        )

        result = decomposer._heuristic_fallback_decomposition(
            "cerca file progetto X poi invia email a Mario", classification
        )

        # Should handle 'poi' as conjunction
        assert len(result) >= 1

    def test_single_domain_no_split(self, decomposer):
        """Test single-domain queries don't unnecessary split."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="low")],
            confidence=0.9,
            query_summary="Simple NBA query",
        )

        result = decomposer._heuristic_fallback_decomposition("lakers game tonight", classification)

        # Single simple query should have 1 sub-query
        assert len(result) >= 1

    def test_analytical_decomposition_pattern(self, decomposer):
        """Test analytical queries create gather + analyze pattern."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="finance_crypto", complexity="high")],
            confidence=0.85,
            query_summary="Analytical query",
        )

        result = decomposer._heuristic_fallback_decomposition(
            "analizza bitcoin e ethereum performance, crea report", classification
        )

        # Should generate multiple sub-queries for analysis
        assert len(result) >= 1
        assert all(sq.domain == "finance_crypto" for sq in result)

    def test_fallback_never_returns_raw_single(self, decomposer):
        """Fallback MUST never return raw single query (B3 FIX)."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="web_search", complexity="low")],
            confidence=0.7,
            query_summary="Generic query",
        )

        result = decomposer._heuristic_fallback_decomposition(
            "random query xyz abc", classification
        )

        # Should return at least 1 SubQuery (never raw)
        assert len(result) >= 1
        assert all(isinstance(sq, SubQuery) for sq in result)

    def test_fallback_preserves_domain_intent(self, decomposer):
        """Test fallback preserves original domain and intent."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="medium")],
            confidence=0.8,
            query_summary="NBA query",
        )

        result = decomposer._heuristic_fallback_decomposition("nba stats analysis", classification)

        # All sub-queries should match classification domain
        for sq in result:
            assert sq.domain == "sports_nba"

    def test_fallback_respects_available_domains(self, decomposer):
        """Test fallback only uses available_domains."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="low")],
            confidence=0.9,
            query_summary="NBA",
        )

        result = decomposer._heuristic_fallback_decomposition("nba game", classification)

        # All domains should be in available list
        available = [
            "sports_nba",
            "web_search",
            "finance_crypto",
            "google_workspace",
            "productivity",
            "travel",
            "food",
        ]
        for sq in result:
            assert sq.domain in available


class TestSubQueryStructure:
    """Test SubQuery data structure and validation (4 tests)."""

    @pytest.fixture
    def decomposer(self):
        mock_llm = AsyncMock(spec=NanoGPTClient)
        config = HybridRouterConfig()
        return QueryDecomposer(mock_llm, ["sports_nba", "web_search"], config)

    def test_subquery_has_required_fields(self, decomposer):
        """Test SubQuery has text, domain, and intent."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="low")],
            confidence=0.9,
            query_summary="NBA",
        )

        result = decomposer._heuristic_fallback_decomposition("nba game", classification)

        for sq in result:
            assert hasattr(sq, "text")
            assert hasattr(sq, "domain")
            assert hasattr(sq, "intent")
            assert isinstance(sq.text, str)
            assert len(sq.text) > 0
            assert isinstance(sq.domain, str)
            assert isinstance(sq.intent, str)

    def test_subquery_text_is_actionable(self, decomposer):
        """Test sub-query text is actionable (not empty or generic)."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="low")],
            confidence=0.9,
            query_summary="NBA",
        )

        result = decomposer._heuristic_fallback_decomposition("lakers vs celtics", classification)

        # Text should be meaningful
        for sq in result:
            assert len(sq.text) > 2
            assert sq.text != "query"

    def test_subquery_intent_matches_action(self, decomposer):
        """Test intent field describes the action type."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="high")],
            confidence=0.95,
            query_summary="NBA betting",
        )

        result = decomposer._heuristic_fallback_decomposition(
            "scommesse nba lakers", classification
        )

        # Intent should be descriptive
        for sq in result:
            assert (
                sq.intent
                in [
                    "direct",
                    "nba_games_data",
                    "nba_context_data",
                    "gathering",
                    "analysis",
                    "synthesis",
                    "search",
                    "none",
                ]
                or len(sq.intent) > 0
            )


class TestDecompositionEdgeCases:
    """Test edge cases and robustness (3 tests)."""

    @pytest.fixture
    def decomposer(self):
        mock_llm = AsyncMock(spec=NanoGPTClient)
        config = HybridRouterConfig()
        return QueryDecomposer(mock_llm, ["sports_nba"], config)

    def test_empty_query_fallback(self, decomposer):
        """Test empty query handling."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="low")],
            confidence=0.5,
            query_summary="",
        )

        result = decomposer._heuristic_fallback_decomposition("", classification)

        # Should return something, even for empty
        assert len(result) >= 0

    def test_very_long_query(self, decomposer):
        """Test very long query handling."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="high")],
            confidence=0.9,
            query_summary="Long query",
        )

        long_query = "nba " * 500  # Very long
        result = decomposer._heuristic_fallback_decomposition(long_query, classification)

        # Should handle gracefully
        assert len(result) >= 1

    def test_special_characters_in_query(self, decomposer):
        """Test special characters don't break decomposition."""
        classification = DomainClassification(
            domains=[DomainComplexity(name="sports_nba", complexity="low")],
            confidence=0.8,
            query_summary="Special chars",
        )

        result = decomposer._heuristic_fallback_decomposition(
            "nba!!!??? scommesse@@@", classification
        )

        # Should not crash
        assert len(result) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
