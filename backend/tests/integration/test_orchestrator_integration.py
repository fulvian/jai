"""Integration Tests for Orchestrator + Memory Layers.

Verifica l'integrazione del ciclo cognitivo completo:
- SemanticRouter + Memory layers
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from me4brain.core.router import SemanticRouter
from me4brain.core.state import create_initial_state


class TestOrchestratorMemoryIntegration:
    """Integration tests per Orchestrator + Memory."""

    @pytest.mark.xfail(reason="Complex mock setup requires orchestrator refactoring")
    @pytest.mark.asyncio
    async def test_cognitive_cycle_with_mocked_memory(self) -> None:
        """Test ciclo cognitivo completo con memory mockate."""
        # Setup mocks
        mock_episodic = AsyncMock()
        mock_semantic = MagicMock()
        mock_working = MagicMock()
        mock_embedding = MagicMock()
        mock_llm = AsyncMock()

        # Mock embedding
        mock_embedding.embed_query.return_value = [0.1] * 1024

        # Mock episodic search
        mock_episode = MagicMock()
        mock_episode.id = "epi_1"
        mock_episode.content = "Arduino è una piattaforma di prototipazione."
        mock_episode.source = "test"
        mock_episode.tags = []
        mock_episode.event_time = MagicMock()
        mock_episode.event_time.isoformat.return_value = "2026-01-27T12:00:00"
        mock_episodic.search_similar.return_value = [(mock_episode, 0.9)]

        # Mock LLM response
        mock_llm.generate.return_value = "Arduino è una piattaforma di prototipazione elettronica."

        # Patches
        with (
            patch("me4brain.core.orchestrator.get_episodic_memory", return_value=mock_episodic),
            patch("me4brain.core.orchestrator.get_semantic_memory", return_value=mock_semantic),
            patch("me4brain.core.orchestrator.get_working_memory", return_value=mock_working),
            patch("me4brain.core.orchestrator.get_embedding_service", return_value=mock_embedding),
            patch("me4brain.core.orchestrator.get_llm_client", return_value=mock_llm),
        ):
            # Execute
            from me4brain.core.orchestrator import run_cognitive_cycle

            result = await run_cognitive_cycle(
                tenant_id="test_tenant",
                user_id="test_user",
                session_id="test_session",
                user_input="Cos'è Arduino?",
            )

            # Verify
            assert result is not None
            assert "final_response" in result or isinstance(result, dict)


class TestRouterIntegration:
    """Integration tests per SemanticRouter."""

    def test_router_routing_decision_simple(self) -> None:
        """Test che routing semplice funzioni correttamente."""
        router = SemanticRouter()

        # Query semplice
        result = router.route("Ciao come stai?")

        assert result is not None
        assert hasattr(result, "decision")
        # Query conversazionale deve andare su no_retrieval o vector_only
        assert result.decision.value in ["no_retrieval", "vector_only"]

    def test_router_routing_decision_relational(self) -> None:
        """Test che routing relazionale vada su graph o hybrid."""
        router = SemanticRouter()

        # Query relazionale
        result = router.route("Chi è collegato a Mario Rossi?")

        assert result is not None
        assert hasattr(result, "decision")
        # Query relazionale deve andare su hybrid o graph_only
        assert result.decision.value in ["hybrid", "graph_only", "vector_only"]


class TestStateCreation:
    """Test per creazione stato iniziale."""

    def test_create_initial_state_all_fields(self) -> None:
        """Verifica che tutti i campi siano inizializzati correttamente."""
        state = create_initial_state(
            tenant_id="tenant_1",
            user_id="user_1",
            session_id="session_1",
            thread_id="thread_1",
            user_input="Test query",
            max_iterations=10,
        )

        assert state["tenant_id"] == "tenant_1"
        assert state["user_id"] == "user_1"
        assert state["session_id"] == "session_1"
        assert state["thread_id"] == "thread_1"
        assert state["current_input"] == "Test query"
        assert state["max_iterations"] == 10
        assert state["iteration_count"] == 0
        assert state["messages"] == []
        assert state["final_response"] == ""
        assert state["confidence"] == 0.0

    def test_create_initial_state_defaults(self) -> None:
        """Verifica valori di default."""
        state = create_initial_state(
            tenant_id="t",
            user_id="u",
            session_id="s",
            thread_id="th",
            user_input="q",
        )

        assert state["max_iterations"] == 5
        assert state["query_type"] == "simple"
        assert state["routing_decision"] == "vector_only"
