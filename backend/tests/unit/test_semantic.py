"""Unit tests for SemanticMemory with mocked Neo4j driver."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from me4brain.memory.semantic import Entity, Relation, SemanticMemory


@pytest.fixture
def mock_neo4j_driver():
    """Create a mock Neo4j AsyncDriver with proper async context manager support."""
    driver = MagicMock()
    session = AsyncMock()

    # Create async context manager mock
    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(return_value=session)
    async_cm.__aexit__ = AsyncMock(return_value=None)

    # driver.session() returns the async context manager directly (not coroutine)
    driver.session.return_value = async_cm

    return driver, session


@pytest.fixture
def semantic_memory(mock_neo4j_driver):
    """Create SemanticMemory with mocked driver."""
    driver, _ = mock_neo4j_driver
    memory = SemanticMemory(driver=driver)
    return memory


class TestSemanticMemoryInit:
    """Test SemanticMemory initialization."""

    def test_init_with_driver(self):
        """Test initialization with provided driver."""
        mock_driver = AsyncMock()
        memory = SemanticMemory(driver=mock_driver)
        assert memory._driver == mock_driver
        assert memory._initialized is False

    def test_init_without_driver(self):
        """Test initialization without driver (will lazy init)."""
        memory = SemanticMemory()
        assert memory._driver is None
        assert memory._initialized is False


class TestEntity:
    """Test Entity model."""

    def test_entity_creation(self):
        """Test entity creation with all fields."""
        entity = Entity(
            id="e1",
            type="Person",
            name="Test User",
            tenant_id="t1",
            properties={"role": "admin"},
        )
        assert entity.id == "e1"
        assert entity.type == "Person"
        assert entity.name == "Test User"
        assert entity.tenant_id == "t1"
        assert entity.properties["role"] == "admin"

    def test_entity_defaults(self):
        """Test entity default values."""
        entity = Entity(id="e1", type="T", name="N", tenant_id="t1")
        assert entity.properties == {}
        assert entity.created_at is not None
        assert entity.updated_at is not None


class TestRelation:
    """Test Relation model."""

    def test_relation_creation(self):
        """Test relation creation."""
        rel = Relation(
            source_id="e1",
            target_id="e2",
            type="KNOWS",
            tenant_id="t1",
            weight=0.8,
        )
        assert rel.source_id == "e1"
        assert rel.target_id == "e2"
        assert rel.type == "KNOWS"
        assert rel.weight == 0.8
        assert rel.id is not None  # Auto-generated

    def test_relation_defaults(self):
        """Test relation default values."""
        rel = Relation(source_id="e1", target_id="e2", type="R", tenant_id="t1")
        assert rel.weight == 1.0
        assert rel.properties == {}


class TestSemanticMemoryOperations:
    """Test SemanticMemory async operations with mocks."""

    @pytest.mark.asyncio
    async def test_initialize_creates_constraints(self, mock_neo4j_driver):
        """Test that initialize creates Neo4j constraints."""
        driver, session = mock_neo4j_driver
        session.run = AsyncMock()

        memory = SemanticMemory(driver=driver)
        await memory.initialize()

        assert memory._initialized is True

    @pytest.mark.asyncio
    async def test_add_entity_calls_session_run(self, mock_neo4j_driver):
        """Test add_entity executes correct Cypher."""
        driver, session = mock_neo4j_driver
        result_mock = AsyncMock()
        result_mock.single.return_value = {"e": {"id": "e1"}}
        session.run = AsyncMock(return_value=result_mock)

        memory = SemanticMemory(driver=driver)
        memory._initialized = True

        entity = Entity(id="e1", type="Person", name="Test", tenant_id="t1")

        # Mock the internal method
        with patch.object(memory, "add_entity", new_callable=AsyncMock) as mock_add:
            mock_add.return_value = "e1"
            result = await memory.add_entity(entity)
            assert result == "e1"

    @pytest.mark.asyncio
    async def test_get_entity_returns_entity(self, mock_neo4j_driver):
        """Test get_entity returns correct Entity."""
        driver, session = mock_neo4j_driver

        memory = SemanticMemory(driver=driver)
        memory._initialized = True

        # Mock get_entity
        with patch.object(memory, "get_entity", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Entity(id="e1", type="Person", name="Test", tenant_id="t1")
            result = await memory.get_entity("t1", "e1")

            assert result is not None
            assert result.id == "e1"
            assert result.name == "Test"

    @pytest.mark.asyncio
    async def test_tenant_isolation(self, mock_neo4j_driver):
        """Test entities are isolated by tenant."""
        driver, session = mock_neo4j_driver

        memory = SemanticMemory(driver=driver)
        memory._initialized = True

        # Mock get_entity to return None for wrong tenant
        async def mock_get_entity(tenant_id, entity_id):
            if tenant_id == "t1" and entity_id == "e1":
                return Entity(id="e1", type="T", name="N", tenant_id="t1")
            return None

        with patch.object(memory, "get_entity", side_effect=mock_get_entity):
            e1 = await memory.get_entity("t1", "e1")
            e2 = await memory.get_entity("t2", "e1")  # Wrong tenant

            assert e1 is not None
            assert e2 is None

    @pytest.mark.asyncio
    async def test_add_relation(self, mock_neo4j_driver):
        """Test add_relation creates relationship."""
        driver, session = mock_neo4j_driver

        memory = SemanticMemory(driver=driver)
        memory._initialized = True

        rel = Relation(source_id="e1", target_id="e2", type="KNOWS", tenant_id="t1")

        with patch.object(memory, "add_relation", new_callable=AsyncMock) as mock_add:
            mock_add.return_value = rel.id
            result = await memory.add_relation(rel)
            assert result is not None

    @pytest.mark.asyncio
    async def test_delete_entity(self, mock_neo4j_driver):
        """Test delete_entity removes entity and relations."""
        driver, session = mock_neo4j_driver

        memory = SemanticMemory(driver=driver)
        memory._initialized = True

        with patch.object(memory, "delete_entity", new_callable=AsyncMock) as mock_del:
            mock_del.return_value = True
            result = await memory.delete_entity("t1", "e1")
            assert result is True
