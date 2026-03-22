from __future__ import annotations

"""Semantic Memory Namespace - Knowledge graph operations."""

from typing import Any

from me4brain_sdk._http import HTTPClient
from me4brain_sdk.models.memory import (
    Entity,
    Relation,
    EntitySearchResult,
    GraphTraversalResult,
    PageRankResult,
)


class SemanticNamespace:
    """Semantic Memory operations - knowledge graph management.

    Semantic memory stores factual knowledge as entities and relations
    in a graph structure (Neo4j). Supports graph traversal, PageRank,
    entity merging, and cross-layer search.

    Example:
        # Search entities
        entities = await client.semantic.search(
            query="Apple Inc",
            limit=5,
        )

        # Traverse knowledge graph
        graph = await client.semantic.traverse(
            start_entity="entity-123",
            max_depth=3,
            relation_types=["WORKS_AT", "KNOWS"],
        )

        # Personalized PageRank
        ranked = await client.semantic.pagerank(
            seed_entities=["entity-1", "entity-2"],
            top_k=10,
        )
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def create_entity(
        self,
        name: str,
        entity_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Entity:
        """Create a new entity in the knowledge graph.

        Args:
            name: Entity name
            entity_type: Entity type (e.g., "Person", "Organization")
            properties: Additional properties

        Returns:
            Created entity
        """
        data = await self._http.post(
            "/v1/memory/entities",
            json_data={
                "name": name,
                "type": entity_type,
                "properties": properties or {},
            },
        )
        return Entity.model_validate(data)

    async def get_entity(self, entity_id: str) -> Entity:
        """Get entity by ID.

        Args:
            entity_id: Entity identifier

        Returns:
            Entity details
        """
        data = await self._http.get(f"/v1/memory/entities/{entity_id}")
        return Entity.model_validate(data)

    async def list_entities(
        self,
        entity_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List entities from the knowledge graph.

        Args:
            entity_type: Filter by entity type (e.g., "Project", "Person")
            limit: Maximum results (1-500)
            offset: Pagination offset

        Returns:
            Dict with entities list, total count, limit, and offset

        Example:
            # List all Projects
            result = await client.semantic.list_entities(
                entity_type="Project",
                limit=100,
            )
            for entity in result["entities"]:
                print(entity["name"])
        """
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }
        if entity_type:
            params["entity_type"] = entity_type

        data = await self._http.get("/v1/memory/entities", params=params)
        return data

    async def search(
        self,
        query: str,
        limit: int = 10,
        entity_type: str | None = None,
        cross_layer: bool = False,
    ) -> list[EntitySearchResult]:
        """Search entities by text query.

        Args:
            query: Search query
            limit: Maximum results
            entity_type: Filter by entity type
            cross_layer: Include results from other memory layers

        Returns:
            List of matching entities with scores
        """
        params: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "cross_layer": cross_layer,
        }
        if entity_type:
            params["entity_type"] = entity_type

        data = await self._http.get("/v1/semantic/search", params=params)

        results = []
        for item in data.get("semantic", []):
            results.append(
                EntitySearchResult(
                    id=item.get("id", ""),
                    content=item.get("name", ""),
                    score=item.get("score", 0.0),
                    metadata=item.get("properties", {}),
                    entity_type=item.get("type"),
                )
            )
        return results

    async def traverse(
        self,
        start_entity: str,
        max_depth: int = 3,
        max_nodes: int = 50,
        relation_types: list[str] | None = None,
    ) -> GraphTraversalResult:
        """Traverse knowledge graph from a starting entity.

        Args:
            start_entity: Entity ID to start from
            max_depth: Maximum traversal depth
            max_nodes: Maximum nodes to return
            relation_types: Filter by relation types

        Returns:
            Graph traversal result with nodes and edges
        """
        data = await self._http.post(
            "/v1/semantic/traverse",
            json_data={
                "start_entity": start_entity,
                "max_depth": max_depth,
                "max_nodes": max_nodes,
                "relation_types": relation_types,
            },
        )
        return GraphTraversalResult.model_validate(data)

    async def pagerank(
        self,
        seed_entities: list[str],
        top_k: int = 10,
        damping: float = 0.85,
    ) -> list[PageRankResult]:
        """Execute Personalized PageRank from seed entities.

        Args:
            seed_entities: Entity IDs to use as seeds
            top_k: Number of top results
            damping: Damping factor (0-1)

        Returns:
            List of entities ranked by PageRank score
        """
        data = await self._http.post(
            "/v1/semantic/pagerank",
            json_data={
                "seed_entities": seed_entities,
                "top_k": top_k,
                "damping": damping,
            },
        )
        return [PageRankResult.model_validate(r) for r in data.get("results", [])]

    async def merge_entities(
        self,
        entity_ids: list[str],
        target_name: str,
        strategy: str = "keep_all_properties",
    ) -> dict[str, Any]:
        """Merge duplicate entities into one.

        Args:
            entity_ids: IDs of entities to merge
            target_name: Name for the merged entity
            strategy: Merge strategy

        Returns:
            Merge result with new entity ID
        """
        data = await self._http.post(
            "/v1/semantic/merge",
            json_data={
                "entity_ids": entity_ids,
                "target_name": target_name,
                "strategy": strategy,
            },
        )
        return data

    async def consolidate(
        self,
        min_importance: float = 0.7,
        max_age_hours: int = 24,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Consolidate important episodes into semantic memory.

        Args:
            min_importance: Minimum importance threshold
            max_age_hours: Maximum episode age
            dry_run: If True, simulate without applying

        Returns:
            Consolidation results
        """
        data = await self._http.post(
            "/v1/semantic/consolidate",
            json_data={
                "min_importance": min_importance,
                "max_age_hours": max_age_hours,
                "dry_run": dry_run,
            },
        )
        return data

    async def create_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        properties: dict[str, Any] | None = None,
        weight: float = 1.0,
    ) -> Relation:
        """Create a relation between entities.

        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            relation_type: Type of relation
            properties: Relation properties
            weight: Relation weight

        Returns:
            Created relation
        """
        data = await self._http.post(
            "/v1/memory/relations",
            json_data={
                "source_id": source_id,
                "target_id": target_id,
                "type": relation_type,
                "properties": properties or {},
                "weight": weight,
            },
        )
        return Relation.model_validate(data)

    async def get_neighbors(
        self,
        entity_id: str,
        relation_types: list[str] | None = None,
        direction: str = "outgoing",
    ) -> list[Entity]:
        """Get neighboring entities.

        Args:
            entity_id: Entity ID
            relation_types: Filter by relation types
            direction: "outgoing", "incoming", or "both"

        Returns:
            List of neighboring entities
        """
        params: dict[str, Any] = {"direction": direction}
        if relation_types:
            params["relation_types"] = ",".join(relation_types)

        data = await self._http.get(
            f"/v1/memory/entities/{entity_id}/neighbors",
            params=params,
        )
        return [Entity.model_validate(e) for e in data.get("entities", [])]
