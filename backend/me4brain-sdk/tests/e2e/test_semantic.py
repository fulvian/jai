"""E2E Tests for Semantic Memory Namespace."""

from __future__ import annotations

import uuid
import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
class TestSemanticMemory:
    """Test Semantic Memory namespace operations."""

    async def test_create_entity(self, async_client):
        """Test entity creation."""
        unique_name = f"TestCompany-{uuid.uuid4().hex[:8]}"

        entity = await async_client.semantic.create_entity(
            name=unique_name,
            entity_type="Organization",
            properties={"industry": "Technology"},
        )

        assert entity is not None
        assert entity.id is not None
        assert entity.name == unique_name

    async def test_search_entities(self, async_client):
        """Test semantic entity search."""
        # Create test entity
        unique_name = f"SearchTestCorp-{uuid.uuid4().hex[:8]}"
        entity = await async_client.semantic.create_entity(
            name=unique_name,
            entity_type="Organization",
            properties={"domain": "testing"},
        )

        try:
            # Search
            results = await async_client.semantic.search(
                query="technology company testing",
                limit=10,
                entity_type="Organization",
            )

            assert results is not None

        finally:
            # Note: May need to implement delete_entity
            pass

    async def test_get_entity_by_id(self, async_client):
        """Test retrieving entity by ID."""
        unique_name = f"GetEntity-{uuid.uuid4().hex[:8]}"
        entity = await async_client.semantic.create_entity(
            name=unique_name,
            entity_type="Person",
            properties={"role": "Engineer"},
        )

        retrieved = await async_client.semantic.get_entity(entity.id)

        assert retrieved is not None
        assert retrieved.id == entity.id
        assert retrieved.name == unique_name

    async def test_list_entities_by_type(self, async_client):
        """Test listing entities by type."""
        # Create a test entity
        unique_name = f"ListTest-{uuid.uuid4().hex[:8]}"
        entity = await async_client.semantic.create_entity(
            name=unique_name,
            entity_type="TestProject",
            properties={"status": "active"},
        )

        # List all entities of type TestProject
        result = await async_client.semantic.list_entities(
            entity_type="TestProject",
            limit=100,
        )

        assert result is not None
        assert "entities" in result
        assert "total" in result
        assert result["total"] >= 1

        # Verify our entity is in the list
        entity_ids = [e["id"] for e in result["entities"]]
        assert entity.id in entity_ids

    async def test_list_entities_without_type(self, async_client):
        """Test listing all entities without type filter."""
        # Create a test entity
        unique_name = f"ListAll-{uuid.uuid4().hex[:8]}"
        await async_client.semantic.create_entity(
            name=unique_name,
            entity_type="AnyType",
            properties={},
        )

        # List all entities
        result = await async_client.semantic.list_entities(limit=10)

        assert result is not None
        assert "entities" in result
        assert "total" in result
        assert "limit" in result
        assert result["limit"] == 10

    async def test_create_relation(self, async_client):
        """Test creating relations between entities."""
        # Create two entities
        person = await async_client.semantic.create_entity(
            name=f"Person-{uuid.uuid4().hex[:8]}",
            entity_type="Person",
        )
        company = await async_client.semantic.create_entity(
            name=f"Company-{uuid.uuid4().hex[:8]}",
            entity_type="Organization",
        )

        # Create relation
        relation = await async_client.semantic.create_relation(
            source_id=person.id,
            target_id=company.id,
            relation_type="WORKS_AT",
            properties={"since": "2024"},
            weight=0.9,
        )

        assert relation is not None

    async def test_traverse_graph(self, async_client):
        """Test knowledge graph traversal."""
        # Create connected entities
        e1 = await async_client.semantic.create_entity(
            name=f"Node1-{uuid.uuid4().hex[:8]}",
            entity_type="Concept",
        )
        e2 = await async_client.semantic.create_entity(
            name=f"Node2-{uuid.uuid4().hex[:8]}",
            entity_type="Concept",
        )

        # Connect them
        await async_client.semantic.create_relation(
            source_id=e1.id,
            target_id=e2.id,
            relation_type="RELATED_TO",
        )

        # Traverse
        graph = await async_client.semantic.traverse(
            start_entity=e1.id,
            max_depth=2,
            max_nodes=20,
        )

        assert graph is not None
        assert len(graph.nodes) >= 1

    async def test_pagerank(self, async_client):
        """Test personalized PageRank."""
        # Create some entities
        e1 = await async_client.semantic.create_entity(
            name=f"Seed-{uuid.uuid4().hex[:8]}",
            entity_type="Concept",
        )

        # Run PageRank
        results = await async_client.semantic.pagerank(
            seed_entities=[e1.id],
            top_k=10,
            damping=0.85,
        )

        assert results is not None


@pytest.mark.e2e
@pytest.mark.asyncio
class TestSemanticConsolidation:
    """Test memory consolidation operations."""

    @pytest.mark.slow
    async def test_consolidate_dry_run(self, async_client):
        """Test consolidation in dry run mode."""
        result = await async_client.semantic.consolidate(
            min_importance=0.5,
            max_age_hours=24,
            dry_run=True,
        )

        assert result is not None
        # Dry run should not make changes
