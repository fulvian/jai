import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from me4brain.engine.hybrid_router.router import HybridToolRouter
from me4brain.engine.hybrid_router.types import HybridRouterConfig, RetrievedTool, SubQuery


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.generate_response = AsyncMock()
    return client


@pytest.fixture
def router(mock_llm_client):
    config = HybridRouterConfig(use_llamaindex_retriever=True)
    mock_index_instance = MagicMock()
    mock_index_instance.get_stats.return_value = {"total_tools": 10}
    mock_index_instance.add_tool = AsyncMock()

    router = HybridToolRouter(
        llm_client=mock_llm_client, config=config, tool_index=mock_index_instance
    )
    router._use_llamaindex = True
    router._initialized = True

    # Initialize internal components as Mocks
    router._classifier = MagicMock()
    router._classifier.classify_with_fallback = AsyncMock()

    router._retriever = MagicMock()
    router._retriever.retrieve = AsyncMock()
    router._retriever.retrieve_global_topk = AsyncMock()
    router._retriever.retrieve_multi_intent = AsyncMock()

    router._decomposer = MagicMock()
    router._decomposer.decompose = AsyncMock()

    return router


def test_multi_intent_threshold_calibration(router):
    """Test Fix P5: Multi-intent threshold should be 3."""
    # 1 verb -> False
    assert router._has_multiple_intents("Cerca email") is False

    # 2 verbs -> True (Lowered threshold from 3 to 2 for better decomposition coverage)
    assert router._has_multiple_intents("Cerca email e trova documenti") is True

    # 3 verbs -> True
    assert router._has_multiple_intents("Cerca email, trova documenti e crea un report") is True


@pytest.mark.asyncio
async def test_add_tool_delegation_llamaindex(router):
    """Test Fix P1: add_tool should delegate to ToolIndexManager when use_llamaindex is True."""
    schema = {"function": {"name": "test_tool", "description": "A test tool"}}
    await router.add_tool("test_tool", schema, "test_domain")

    # Verify it called ToolIndexManager.add_tool
    router._tool_index.add_tool.assert_called_once_with("test_tool", schema, "test_domain")

    # Verify domain was added
    assert "test_domain" in router._available_domains


def test_get_stats_llamaindex(router):
    """Test Fix P2: get_stats should fetch from ToolIndexManager when LlamaIndex is active."""
    stats = router.get_stats()

    assert stats["initialized"] is True
    assert stats["tools_embedded"] == 10
    router._tool_index.get_stats.assert_called_once()


@pytest.mark.asyncio
async def test_route_basic(router, mock_llm_client):
    """Test basic routing flow."""
    # Mock classification result
    mock_classif = MagicMock()
    mock_classif.domain_names = ["finance"]
    mock_classif.confidence = 0.9
    mock_classif.is_multi_domain = True
    mock_classif.needs_fallback = False

    router._classifier.classify_with_fallback.return_value = (mock_classif, False)

    # Mock retriever response
    mock_retrieval = MagicMock()
    mock_retrieval.tools = [
        RetrievedTool(
            name="stock_quote",
            domain="finance",
            similarity_score=0.8,
            schema={"function": {"name": "stock_quote"}},
        )
    ]
    mock_retrieval.tool_count = 1
    mock_retrieval.domains_searched = ["finance"]
    mock_retrieval.get_schemas.return_value = [{"function": {"name": "stock_quote"}}]

    router._retriever.retrieve.return_value = mock_retrieval

    # Build a proper mock response for tool calls
    mock_tc = MagicMock()
    mock_tc.id = "call_1"
    mock_tc.function = MagicMock()
    mock_tc.function.name = "stock_quote"  # Explicitly set attribute
    mock_tc.function.arguments = '{"symbol": "AAPL"}'

    mock_message = MagicMock()
    mock_message.tool_calls = [mock_tc]

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]

    mock_llm_client.generate_response.return_value = mock_resp

    tasks = await router.route("What is the price of AAPL?")

    assert len(tasks) == 1
    assert tasks[0].tool_name == "stock_quote"
    assert tasks[0].arguments == {"symbol": "AAPL"}


@pytest.mark.asyncio
async def test_route_uses_rewritten_query_across_stages(router, mock_llm_client):
    """Ensure rewritten query is used for decomposition/retrieval/selection."""
    # Arrange classification
    mock_classif = MagicMock()
    mock_classif.domain_names = ["finance"]
    mock_classif.confidence = 0.95
    mock_classif.is_multi_domain = True
    mock_classif.needs_fallback = False
    mock_classif.domains = [MagicMock(name="finance")]
    router._classifier.classify_with_fallback.return_value = (mock_classif, False)

    # Force Stage 0 rewrite
    router._context_rewriter = MagicMock()
    router._context_rewriter.rewrite = AsyncMock(
        return_value=MagicMock(was_rewritten=True, rewritten_query="rewritten finance query")
    )
    router._intent_analyzer = MagicMock()
    mock_intent = MagicMock()
    mock_intent.intent_type.value = "data_retrieval"
    mock_intent.data_requirements.needs_real_time_data = True
    mock_intent.data_requirements.needs_external_api = True
    mock_intent.confidence = 0.9
    mock_intent.suggested_domains = ["finance"]
    router._intent_analyzer.analyze = AsyncMock(return_value=mock_intent)

    # Ensure decomposition path is active
    router._config.use_query_decomposition = True
    router._use_llamaindex = False
    router._decomposer.decompose.return_value = [
        SubQuery(text="rewritten finance query", domain="finance", intent="analysis")
    ]

    # Mock retrieval
    mock_retrieval = MagicMock()
    mock_retrieval.tools = [
        RetrievedTool(
            name="stock_quote",
            domain="finance",
            similarity_score=0.8,
            schema={"function": {"name": "stock_quote"}},
        )
    ]
    mock_retrieval.tool_count = 1
    mock_retrieval.domains_searched = ["finance"]
    mock_retrieval.total_payload_bytes = 123
    router._retriever.retrieve.return_value = mock_retrieval

    # Mock tool-call response
    mock_tc = MagicMock()
    mock_tc.id = "call_1"
    mock_tc.function = MagicMock()
    mock_tc.function.name = "stock_quote"
    mock_tc.function.arguments = '{"symbol": "AAPL"}'
    mock_message = MagicMock()
    mock_message.tool_calls = [mock_tc]
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_llm_client.generate_response.return_value = mock_resp

    # Act
    await router.route("original query", conversation_history=[{"role": "user", "content": "ctx"}])

    # Assert rewritten query is used by decomposition and retrieval
    router._decomposer.decompose.assert_called_once()
    assert router._decomposer.decompose.call_args[0][0] == "rewritten finance query"
    router._retriever.retrieve.assert_called_once()
    assert router._retriever.retrieve.call_args[0][0] == "rewritten finance query"
