import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from me4brain.core.orchestrator import (
    embed_input,
    route_query,
    retrieve_lightrag,
    check_muscle_memory,
    resolve_conflicts,
    generate_response,
    run_cognitive_cycle,
)
from me4brain.core.router import RouterResult, QueryType, RoutingDecision
from me4brain.retrieval.lightrag import LightRAGResult
from me4brain.core.conflict import ConflictSource, ConflictResolution
from datetime import UTC, datetime


@pytest.fixture
def mock_state():
    return {"current_input": "Test query", "tenant_id": "t1", "user_id": "u1", "session_id": "s1"}


@pytest.fixture
def mock_orchestrator_deps():
    with (
        patch("me4brain.core.orchestrator.get_embedding_service") as mock_emb_getter,
        patch("me4brain.core.orchestrator.get_semantic_router") as mock_router_getter,
        patch("me4brain.core.orchestrator.get_lightrag_engine") as mock_lightrag_getter,
    ):
        emb = MagicMock()
        router = MagicMock()
        engine = AsyncMock()

        mock_emb_getter.return_value = emb
        mock_router_getter.return_value = router
        mock_lightrag_getter.return_value = engine

        yield emb, router, engine


@pytest.mark.asyncio
async def test_embed_input_node(mock_state, mock_orchestrator_deps):
    emb, _, _ = mock_orchestrator_deps
    emb.embed_query.return_value = [0.1] * 1024

    result = await embed_input(mock_state)

    assert "current_input_embedding" in result
    assert len(result["current_input_embedding"]) == 1024
    emb.embed_query.assert_called_once_with("Test query")


@pytest.mark.asyncio
async def test_route_query_node(mock_state, mock_orchestrator_deps):
    _, router, _ = mock_orchestrator_deps
    router.route.return_value = RouterResult(
        query_type=QueryType.SIMPLE,
        decision=RoutingDecision.HYBRID,
        confidence=0.9,
        reasoning="Test reasoning",
    )

    state_with_emb = {**mock_state, "current_input_embedding": [0.1] * 1024}
    result = await route_query(state_with_emb)

    assert result["query_type"] == "simple"
    assert result["routing_decision"] == "hybrid"
    assert result["routing_confidence"] == 0.9


@pytest.mark.asyncio
async def test_retrieve_lightrag_node(mock_state, mock_orchestrator_deps):
    _, _, engine = mock_orchestrator_deps
    engine.dual_retrieval.return_value = [LightRAGResult(content="c1", source="local", score=1.0)]

    result = await retrieve_lightrag(mock_state)

    assert len(result["lightrag_results"]) == 1
    assert result["lightrag_results"][0]["content"] == "c1"
    engine.dual_retrieval.assert_called_once()


@pytest.mark.asyncio
async def test_check_muscle_memory_node(mock_state):
    with patch("me4brain.core.orchestrator.get_procedural_memory") as mock_getter:
        proc = AsyncMock()
        mock_getter.return_value = proc

        # Test Miss
        state = {**mock_state, "routing_decision": "vector_only"}
        result = await check_muscle_memory(state)
        assert result["muscle_memory_hit"] is False

        # Test Hit
        state = {
            **mock_state,
            "routing_decision": "tool_required",
            "current_input_embedding": [0.1],
        }
        mock_exec = MagicMock()
        mock_exec.tool_name = "t1"
        mock_exec.tool_id = "tid1"
        mock_exec.input_json = {}
        mock_exec.intent = "intent"
        proc.find_similar_execution.return_value = mock_exec

        result = await check_muscle_memory(state)
        assert result["muscle_memory_hit"] is True
        assert result["selected_tool"]["tool_name"] == "t1"


@pytest.mark.asyncio
async def test_resolve_conflicts_node(mock_state):
    with patch("me4brain.core.orchestrator.get_conflict_resolver") as mock_getter:
        resolver = MagicMock()
        mock_getter.return_value = resolver

        # Case 1: No overlap/LightRAG results
        state = {**mock_state, "lightrag_results": [{"content": "c1", "source": "local"}]}
        result = await resolve_conflicts(state)
        assert result["has_conflict"] is False

        # Case 2: Conflict detected
        state = {
            **mock_state,
            "episodic_results": [{"content": "A", "score": 0.9, "metadata": {}}],
            "semantic_results": [{"content": "B", "score": 0.8, "metadata": {}}],
        }
        resolver.detect_conflict.return_value = True
        mock_res = MagicMock(spec=ConflictResolution)
        mock_res.winner = MagicMock()
        mock_res.winner.source_type = "episodic"
        mock_res.strategy = "recency"
        mock_res.confidence = 0.9
        mock_res.explanation = "because"
        resolver.resolve.return_value = mock_res

        result = await resolve_conflicts(state)
        assert result["has_conflict"] is True
        assert result["conflict_info"]["resolution"] == "episodic"


@pytest.mark.asyncio
async def test_generate_response_node(mock_state):
    # Mock LLM Client
    with (
        patch("me4brain.llm.NanoGPTClient") as mock_client_cls,
        patch("me4brain.llm.get_llm_config") as mock_config_getter,
    ):
        mock_config = MagicMock()
        mock_config.nanogpt_api_key = "test"
        mock_config.nanogpt_base_url = "http://test"
        mock_config.model_primary_thinking = "test-model"
        mock_config_getter.return_value = mock_config

        client = AsyncMock()
        mock_client_cls.return_value = client
        mock_resp = MagicMock()
        mock_resp.content = "Answer"
        mock_resp.reasoning = "Because"
        mock_resp.latency_ms = 100
        client.generate_response.return_value = mock_resp

        state = {
            **mock_state,
            "lightrag_results": [{"content": "c1", "source": "local"}],
            "routing_confidence": 0.9,
        }

        result = await generate_response(state)
        assert "final_response" in result
        assert result["final_response"] == "Answer"
        assert result["confidence"] > 0


@pytest.mark.asyncio
async def test_run_cognitive_cycle_minimal(mock_state):
    # Mocking the graph execution to bypass complexity but verify the entry point
    # In a real unit test we might want to mock the whole Graph,
    # but here we test the wrapper run_cognitive_cycle.
    with patch("me4brain.core.orchestrator.StateGraph") as mock_graph_cls:
        mock_app = MagicMock()
        mock_app.ainvoke = AsyncMock()
        mock_app.ainvoke.return_value = {"final_response": "Done"}

        mock_graph = MagicMock()
        mock_graph.compile.return_value = mock_app
        mock_graph_cls.return_value = mock_graph

        result = await run_cognitive_cycle(
            tenant_id="t1", user_id="u1", session_id="s1", user_input="test"
        )

        assert result["final_response"] == "Done"
