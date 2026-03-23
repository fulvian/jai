from unittest.mock import MagicMock, patch

import pytest

from me4brain.core.router import QueryType, RoutingDecision, SemanticRouter


@pytest.fixture
def router() -> SemanticRouter:
    """Crea un router per i test."""
    return SemanticRouter()


def test_pattern_match_various(router: SemanticRouter) -> None:
    """Test pattern matching per vari tipi di query."""
    # Conversational
    qt, conf = router._pattern_match("Ciao!")
    assert qt == QueryType.CONVERSATIONAL

    # Procedural
    qt, conf = router._pattern_match("Come si fa?")
    assert qt == QueryType.PROCEDURAL

    # Relational
    qt, conf = router._pattern_match("Chi è collegato a?")
    assert qt == QueryType.RELATIONAL


def test_route_heuristic_only(router: SemanticRouter) -> None:
    """Test del metodo route principale tramite euristiche."""
    # Quando la query è chiaramente conversazionale, non serve embedding
    result = router.route("Ciao Me4BrAIn")
    assert result.query_type == QueryType.CONVERSATIONAL
    assert result.decision == RoutingDecision.NO_RETRIEVAL
    assert result.confidence >= 0.9


@pytest.mark.parametrize(
    "query,expected_type",
    [
        ("Perché succede questo?", QueryType.CAUSAL),
        ("Quando è accaduto?", QueryType.TEMPORAL),
        ("Come funziona il sistema?", QueryType.PROCEDURAL),
    ],
)
def test_route_patterns(router, query, expected_type):
    result = router.route(query)
    assert result.query_type == expected_type


def test_route_semantic_fallback(router: SemanticRouter) -> None:
    """Test fallback semantico (embedding) quando l'euristica fallisce."""
    # Questa query non matcha nessun pattern euristico
    query = "Il componente X ha una temperatura di 50 gradi."

    with patch("me4brain.core.router.get_embedding_service") as mock_emb_getter:
        mock_emb = MagicMock()
        mock_emb_getter.return_value = mock_emb
        # Mocking semantic classification would be complex internal logic,
        # but the Router.route calls it.
        # For now, we test that it defaults to SIMPLE/VECTOR_ONLY if nothing matches

        result = router.route(query)
        assert result.query_type == QueryType.SIMPLE
        assert result.decision == RoutingDecision.VECTOR_ONLY
        assert "Heuristic" not in result.reasoning or "Default" in result.reasoning
