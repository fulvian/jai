"""Unit tests for ProceduralMemory with mocked dependencies."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from me4brain.memory.procedural import ProceduralMemory, Tool, ToolExecution


@pytest.fixture
def mock_semantic_memory():
    """Create a mock SemanticMemory with async methods and Neo4j driver."""
    mock = AsyncMock()
    mock.add_entity = AsyncMock(return_value="entity_id")
    mock.get_entity = AsyncMock(return_value=None)
    mock.update_entity = AsyncMock()
    mock.initialize = AsyncMock()

    # Mock Neo4j driver with proper async context manager
    session = AsyncMock()

    # Mock result for session.run() - provides valid JSON record and async iteration
    mock_record = MagicMock()
    mock_record.__getitem__ = MagicMock(return_value='{"success_rate": 0.5, "total_calls": 10}')

    # Create async iterator that returns empty list for async for loops
    class AsyncIteratorEmpty:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value=mock_record)
    mock_result.__aiter__ = lambda self: AsyncIteratorEmpty()
    session.run = AsyncMock(return_value=mock_result)

    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(return_value=session)
    async_cm.__aexit__ = AsyncMock(return_value=None)

    driver = MagicMock()
    driver.session.return_value = async_cm

    mock.get_driver = AsyncMock(return_value=driver)

    return mock


@pytest.fixture
def mock_qdrant():
    """Create a mock Qdrant async client."""
    client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.collections = []
    client.get_collections = AsyncMock(return_value=mock_resp)
    client.create_collection = AsyncMock()
    client.upsert = AsyncMock()
    client.query_points = AsyncMock()
    return client


@pytest.fixture
def procedural_memory(mock_semantic_memory, mock_qdrant):
    """Create ProceduralMemory with mocked dependencies."""
    memory = ProceduralMemory(semantic_memory=mock_semantic_memory, qdrant_client=mock_qdrant)
    return memory


class TestTool:
    """Test Tool model."""

    def test_tool_creation(self):
        """Test tool creation with all fields."""
        tool = Tool(
            name="calculator",
            description="Performs calculations",
            tenant_id="t1",
            success_rate=0.95,
            status="ACTIVE",
        )
        assert tool.name == "calculator"
        assert tool.description == "Performs calculations"
        assert tool.success_rate == 0.95
        assert tool.status == "ACTIVE"
        assert tool.id is not None

    def test_tool_defaults(self):
        """Test tool default values."""
        tool = Tool(name="test", description="d", tenant_id="t1")
        assert tool.success_rate == 0.5
        assert tool.status == "ACTIVE"


class TestToolExecution:
    """Test ToolExecution model."""

    def test_execution_creation(self):
        """Test execution record creation."""
        exec_record = ToolExecution(
            tenant_id="t1",
            user_id="u1",
            intent="calculate sum",
            tool_id="tool1",
            tool_name="calculator",
            input_json={"a": 1, "b": 2},
            output_json={"result": 3},
            success=True,
        )
        assert exec_record.intent == "calculate sum"
        assert exec_record.success is True
        assert exec_record.input_json == {"a": 1, "b": 2}


class TestProceduralMemoryInit:
    """Test ProceduralMemory initialization."""

    def test_init_with_dependencies(self, mock_semantic_memory, mock_qdrant):
        """Test initialization with provided dependencies."""
        memory = ProceduralMemory(
            semantic_memory=mock_semantic_memory,
            qdrant_client=mock_qdrant,
        )
        assert memory is not None

    def test_init_without_dependencies(self):
        """Test initialization without dependencies (lazy init)."""
        memory = ProceduralMemory()
        assert memory is not None


class TestProceduralMemoryOperations:
    """Test ProceduralMemory operations."""

    @pytest.mark.asyncio
    async def test_initialize(self, procedural_memory, mock_qdrant):
        """Test initialization creates collection if needed."""
        await procedural_memory.initialize()
        mock_qdrant.get_collections.assert_called()

    @pytest.mark.asyncio
    async def test_register_tool(self, procedural_memory, mock_semantic_memory):
        """Test registering a tool."""
        tool = Tool(name="test_tool", description="A test tool", tenant_id="t1")

        tid = await procedural_memory.register_tool(tool)

        assert tid == tool.id
        mock_semantic_memory.add_entity.assert_called()

    @pytest.mark.asyncio
    async def test_find_tools_for_intent(self, procedural_memory, mock_qdrant):
        """Test finding tools for an intent."""
        # Mock empty Qdrant response
        mock_qdrant.query_points = AsyncMock(return_value=MagicMock(points=[]))

        embedding = [0.1] * 1024
        results = await procedural_memory.find_tools_for_intent(
            tenant_id="t1",
            intent_embedding=embedding,
        )

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_update_tool_weight_success(self, procedural_memory, mock_semantic_memory):
        """Test updating tool weight after success."""
        # Mock entity response
        mock_entity = MagicMock()
        mock_entity.properties = {"success_rate": 0.5}
        mock_semantic_memory.get_entity = AsyncMock(return_value=mock_entity)

        await procedural_memory.update_tool_weight("t1", "tool1", success=True)
        # Method should work without error

    @pytest.mark.asyncio
    async def test_update_tool_weight_failure(self, procedural_memory, mock_semantic_memory):
        """Test updating tool weight after failure."""
        mock_entity = MagicMock()
        mock_entity.properties = {"success_rate": 0.5}
        mock_semantic_memory.get_entity = AsyncMock(return_value=mock_entity)

        await procedural_memory.update_tool_weight("t1", "tool1", success=False)

    @pytest.mark.asyncio
    async def test_save_execution(self, procedural_memory, mock_qdrant):
        """Test saving execution to muscle memory."""
        exec_record = ToolExecution(
            tenant_id="t1",
            user_id="u1",
            intent="test intent",
            tool_id="tool1",
            tool_name="test_tool",
            input_json={"q": "hi"},
            output_json={"a": "hello"},
            success=True,
        )
        embedding = [0.1] * 1024

        await procedural_memory.save_execution(exec_record, embedding)

        mock_qdrant.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_similar_execution(self, procedural_memory, mock_qdrant):
        """Test finding similar execution from muscle memory."""
        # Setup mock response
        mock_point = MagicMock()
        mock_point.id = "exec1"
        mock_point.score = 0.95
        mock_point.payload = {
            "tenant_id": "t1",
            "intent": "test",
            "tool_id": "tool1",
            "tool_name": "test_tool",
            "input_json": {"q": "hi"},
            "executed_at": datetime.now(UTC).isoformat(),
        }

        query_resp = MagicMock()
        query_resp.points = [mock_point]
        mock_qdrant.query_points = AsyncMock(return_value=query_resp)

        embedding = [0.1] * 1024
        hit = await procedural_memory.find_similar_execution("t1", embedding)

        assert hit is not None
        assert hit.tool_name == "test_tool"
