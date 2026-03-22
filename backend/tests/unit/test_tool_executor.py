import pytest
import respx
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from me4brain.retrieval.tool_executor import ToolExecutor, ExecutionRequest
from me4brain.memory.procedural import Tool, ToolExecution
from me4brain.memory.semantic import Entity


@pytest.fixture
def mock_procedural():
    proc = MagicMock()
    semantic = AsyncMock()  # Changed to AsyncMock
    proc.get_semantic = MagicMock(return_value=semantic)
    proc.find_similar_execution = AsyncMock()
    proc.save_execution = AsyncMock()
    proc.update_tool_weight = AsyncMock()  # Also async
    return proc


@pytest.fixture
def executor(mock_procedural):
    return ToolExecutor(procedural_memory=mock_procedural)


@pytest.mark.asyncio
async def test_execute_muscle_memory_hit(executor, mock_procedural):
    # Setup mock hit
    mock_execution = MagicMock()
    mock_execution.intent = "search for something"
    mock_execution.tool_name = "TestTool"
    mock_execution.output_json = {"result": "ok"}
    mock_execution.input_json = {"arg": 1}

    mock_procedural.find_similar_execution.return_value = mock_execution

    with patch("me4brain.retrieval.tool_executor.get_embedding_service") as mock_emb_getter:
        emb = MagicMock()
        mock_emb_getter.return_value = emb
        emb.embed_query.return_value = [0.1] * 1024

        request = ExecutionRequest(
            tenant_id="t1",
            user_id="u1",
            intent="search for something",
            tool_id="tool_123",
            arguments={"query": "test"},
        )

        result = await executor.execute(request, use_muscle_memory=True)

    assert result.success is True
    assert result.from_muscle_memory is True
    assert result.result["cached"] is True
    mock_procedural.find_similar_execution.assert_called_once()


@pytest.mark.asyncio
@respx.mock
async def test_execute_http_success(executor, mock_procedural):
    # Setup muscle memory miss
    mock_procedural.find_similar_execution.return_value = None

    # Setup tool info
    semantic = mock_procedural.get_semantic.return_value
    mock_entity = Entity(
        id="tool_123",
        name="TestTool",
        type="Tool",
        tenant_id="t1",
        properties={
            "endpoint": "https://api.example.com/test",
            "method": "POST",
            "description": "A test tool",
        },
    )
    semantic.get_entity.return_value = mock_entity

    # Mock HTTP call
    respx.post("https://api.example.com/test").respond(json={"status": "success"})

    with patch("me4brain.retrieval.tool_executor.get_embedding_service") as mock_emb_getter:
        emb = MagicMock()
        mock_emb_getter.return_value = emb
        emb.embed_query.return_value = [0.1] * 1024

        request = ExecutionRequest(
            tenant_id="t1",
            user_id="u1",
            intent="run tool",
            tool_id="tool_123",
            arguments={"body": {"input": "data"}},
        )

        result = await executor.execute(request, use_muscle_memory=True)

    assert result.success is True
    assert result.result == {"status": "success"}
    assert result.from_muscle_memory is False
    mock_procedural.update_tool_weight.assert_called_with(
        tenant_id="t1", tool_id="tool_123", success=True
    )
    mock_procedural.save_execution.assert_called_once()


@pytest.mark.asyncio
async def test_execute_tool_not_found(executor, mock_procedural):
    mock_procedural.find_similar_execution.return_value = None
    semantic = mock_procedural.get_semantic.return_value
    semantic.get_entity.return_value = None

    with patch("me4brain.retrieval.tool_executor.get_embedding_service") as mock_emb_getter:
        emb = MagicMock()
        mock_emb_getter.return_value = emb
        emb.embed_query.return_value = [0.1] * 1024

        request = ExecutionRequest(
            tenant_id="t1", user_id="u1", intent="run tool", tool_id="missing", arguments={}
        )

        result = await executor.execute(request)

    assert result.success is False
    assert "Tool not found" in result.error
