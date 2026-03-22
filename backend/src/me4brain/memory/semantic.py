"""Semantic Memory - Knowledge Graph Layer.

Implementa il Layer III del sistema cognitivo:
- Neo4j come primary graph database
- Personalized PageRank per retrieval associativo
- LlamaIndex-ready per futura integrazione
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import ServiceUnavailable, AuthError
from pydantic import BaseModel, Field

from me4brain.config import get_settings

logger = structlog.get_logger(__name__)


class Entity(BaseModel):
    """Rappresenta un'entità nel Knowledge Graph."""

    id: str
    type: str  # Person, Concept, Document, etc.
    name: str
    tenant_id: str

    # Metadati
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Relation(BaseModel):
    """Rappresenta una relazione tra entità."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    source_id: str
    target_id: str
    type: str  # RELATES_TO, CAUSES, PART_OF, etc.
    tenant_id: str

    # Metadati
    weight: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SemanticMemory:
    """Gestisce la memoria semantica (Knowledge Graph).

    Utilizza Neo4j come database principale:
    - Server mode (concurrent access)
    - Native Cypher support
    - APOC per PageRank e algoritmi avanzati
    - LlamaIndex-ready
    """

    def __init__(self, driver: AsyncDriver | None = None) -> None:
        """Inizializza Semantic Memory.

        Args:
            driver: Driver Neo4j opzionale (per testing/DI)
        """
        self._driver = driver
        self._initialized = False

    async def get_driver(self) -> AsyncDriver | None:
        """Ottiene il driver Neo4j con connection pooling e retry.

        Issue #3 fix: Aggiunto timeout esplicito e retry logic.

        Returns:
            Driver Neo4j o None se non disponibile.
        """
        if self._driver is None:
            settings = get_settings()
            max_retries = 3
            retry_delay = 2  # seconds

            for attempt in range(max_retries):
                try:
                    # Connection pooling config per gestire meglio i timeout
                    self._driver = AsyncGraphDatabase.driver(
                        settings.neo4j_uri,
                        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
                        # Connection pool settings
                        max_connection_lifetime=3600,  # 1 hour
                        max_connection_pool_size=50,
                        connection_acquisition_timeout=60,  # seconds
                        # Timeout settings
                        connection_timeout=30,  # seconds
                    )
                    # Verify connectivity with timeout
                    await self._driver.verify_connectivity()
                    logger.info(
                        "neo4j_connected",
                        uri=settings.neo4j_uri,
                        attempt=attempt + 1,
                    )
                    break

                except ServiceUnavailable as e:
                    if attempt < max_retries - 1:
                        logger.warning(
                            "neo4j_connection_retry",
                            error=str(e),
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            retry_in=retry_delay,
                        )
                        import asyncio

                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        logger.error(
                            "neo4j_connection_failed_after_retries",
                            error=str(e),
                            attempts=max_retries,
                            hint="Verificare che Neo4j sia avviato (docker compose up neo4j)",
                        )
                        self._driver = None
                        return None

                except AuthError as e:
                    logger.error(
                        "neo4j_auth_failed",
                        error=str(e),
                        hint="Verificare NEO4J_USER e NEO4J_PASSWORD",
                    )
                    self._driver = None
                    return None

                except Exception as e:
                    logger.error("neo4j_unexpected_error", error=str(e))
                    self._driver = None
                    return None

        return self._driver

    async def _get_session(self) -> AsyncSession | None:
        """Ottiene una sessione Neo4j."""
        driver = await self.get_driver()
        if driver is None:
            return None
        return driver.session()

    async def initialize(self) -> None:
        """Inizializza lo schema del Knowledge Graph.

        Crea constraints e indexes per Entity e relazioni.
        """
        if self._initialized:
            return

        driver = await self.get_driver()
        if driver is None:
            logger.warning("neo4j_initialize_skipped", reason="driver not available")
            return

        async with driver.session() as session:
            # Constraint per Entity ID univoco
            await session.run("""
                CREATE CONSTRAINT entity_id IF NOT EXISTS
                FOR (e:Entity) REQUIRE e.id IS UNIQUE
            """)

            # Index per tenant_id (multitenancy)
            await session.run("""
                CREATE INDEX entity_tenant IF NOT EXISTS
                FOR (e:Entity) ON (e.tenant_id)
            """)

            # Index per type
            await session.run("""
                CREATE INDEX entity_type IF NOT EXISTS
                FOR (e:Entity) ON (e.type)
            """)

            self._initialized = True
            logger.info("neo4j_schema_initialized")

    async def add_entity(self, entity: Entity) -> str:
        """Aggiunge un'entità al Knowledge Graph.

        Args:
            entity: L'entità da aggiungere

        Returns:
            ID dell'entità
        """
        import json

        driver = await self.get_driver()
        if driver is None:
            raise RuntimeError("Neo4j non disponibile")

        async with driver.session() as session:
            await session.run(
                """
                MERGE (e:Entity {id: $id})
                SET e.type = $type,
                    e.name = $name,
                    e.tenant_id = $tenant_id,
                    e.properties = $properties,
                    e.created_at = datetime($created_at),
                    e.updated_at = datetime($updated_at)
                """,
                {
                    "id": entity.id,
                    "type": entity.type,
                    "name": entity.name,
                    "tenant_id": entity.tenant_id,
                    "properties": json.dumps(entity.properties),
                    "created_at": entity.created_at.isoformat(),
                    "updated_at": entity.updated_at.isoformat(),
                },
            )

        logger.debug(
            "entity_added",
            entity_id=entity.id,
            entity_type=entity.type,
            tenant_id=entity.tenant_id,
        )

        return entity.id

    async def add_relation(self, relation: Relation) -> None:
        """Aggiunge una relazione tra entità.

        Args:
            relation: La relazione da creare
        """
        import json

        driver = await self.get_driver()
        if driver is None:
            raise RuntimeError("Neo4j non disponibile")

        async with driver.session() as session:
            await session.run(
                """
                MATCH (a:Entity {id: $source_id, tenant_id: $tenant_id})
                MATCH (b:Entity {id: $target_id, tenant_id: $tenant_id})
                MERGE (a)-[r:RELATES_TO]->(b)
                SET r.type = $type,
                    r.weight = $weight,
                    r.properties = $properties,
                    r.tenant_id = $tenant_id,
                    r.created_at = datetime($created_at)
                """,
                {
                    "source_id": relation.source_id,
                    "target_id": relation.target_id,
                    "type": relation.type,
                    "weight": relation.weight,
                    "properties": json.dumps(relation.properties),
                    "tenant_id": relation.tenant_id,
                    "created_at": relation.created_at.isoformat(),
                },
            )

        logger.debug(
            "relation_added",
            source=relation.source_id,
            target=relation.target_id,
            type=relation.type,
        )

    async def get_entity(self, tenant_id: str, entity_id: str) -> Entity | None:
        """Recupera un'entità per ID con tenant isolation."""
        import json

        driver = await self.get_driver()
        if driver is None:
            return None

        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (e:Entity {id: $id, tenant_id: $tenant_id})
                RETURN e.id, e.type, e.name, e.tenant_id, e.properties,
                       e.created_at, e.updated_at
                """,
                {"id": entity_id, "tenant_id": tenant_id},
            )

            record = await result.single()
            if record is None:
                return None

            return Entity(
                id=record[0],
                type=record[1],
                name=record[2],
                tenant_id=record[3],
                properties=json.loads(record[4]) if record[4] else {},
                created_at=record[5].to_native() if record[5] else datetime.now(UTC),
                updated_at=record[6].to_native() if record[6] else datetime.now(UTC),
            )

    async def list_entities_by_type(
        self,
        tenant_id: str,
        entity_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Entity], int]:
        """Lista entità per tipo con paginazione.

        Args:
            tenant_id: Tenant isolation
            entity_type: Filtra per tipo (None = tutti)
            limit: Numero massimo entità
            offset: Offset per paginazione

        Returns:
            Tuple (lista entità, conteggio totale)
        """
        import json

        driver = await self.get_driver()
        if driver is None:
            return [], 0

        entities: list[Entity] = []

        async with driver.session() as session:
            # Query con filtro opzionale per tipo
            if entity_type:
                query = """
                    MATCH (e:Entity {tenant_id: $tenant_id, type: $entity_type})
                    RETURN e.id, e.type, e.name, e.tenant_id, e.properties,
                           e.created_at, e.updated_at
                    ORDER BY e.created_at DESC
                    SKIP $offset LIMIT $limit
                """
                count_query = """
                    MATCH (e:Entity {tenant_id: $tenant_id, type: $entity_type})
                    RETURN count(e) as total
                """
                params = {
                    "tenant_id": tenant_id,
                    "entity_type": entity_type,
                    "offset": offset,
                    "limit": limit,
                }
                count_params = {"tenant_id": tenant_id, "entity_type": entity_type}
            else:
                query = """
                    MATCH (e:Entity {tenant_id: $tenant_id})
                    RETURN e.id, e.type, e.name, e.tenant_id, e.properties,
                           e.created_at, e.updated_at
                    ORDER BY e.created_at DESC
                    SKIP $offset LIMIT $limit
                """
                count_query = """
                    MATCH (e:Entity {tenant_id: $tenant_id})
                    RETURN count(e) as total
                """
                params = {
                    "tenant_id": tenant_id,
                    "offset": offset,
                    "limit": limit,
                }
                count_params = {"tenant_id": tenant_id}

            # Esegui query principale
            result = await session.run(query, params)
            async for record in result:
                entities.append(
                    Entity(
                        id=record[0],
                        type=record[1],
                        name=record[2],
                        tenant_id=record[3],
                        properties=json.loads(record[4]) if record[4] else {},
                        created_at=record[5].to_native() if record[5] else datetime.now(UTC),
                        updated_at=record[6].to_native() if record[6] else datetime.now(UTC),
                    )
                )

            # Esegui count query
            count_result = await session.run(count_query, count_params)
            count_record = await count_result.single()
            total = count_record[0] if count_record else 0

        logger.debug(
            "list_entities_by_type",
            tenant_id=tenant_id,
            entity_type=entity_type,
            count=len(entities),
            total=total,
        )

        return entities, total

    async def get_neighbors(
        self,
        tenant_id: str,
        entity_id: str,
        max_depth: int = 2,
        relation_types: list[str] | None = None,
    ) -> list[tuple[Entity, str, float]]:
        """Recupera i vicini di un'entità (1-hop o multi-hop)."""
        import json

        driver = await self.get_driver()
        if driver is None:
            return []

        # Build relationship pattern
        rel_pattern = f"*1..{max_depth}"
        if relation_types:
            type_labels = "|".join(relation_types)
            rel_pattern = f":{type_labels}{rel_pattern}"

        async with driver.session() as session:
            result = await session.run(
                f"""
                MATCH (start:Entity {{id: $entity_id, tenant_id: $tenant_id}})
                      -[{rel_pattern}]->
                      (neighbor:Entity {{tenant_id: $tenant_id}})
                RETURN DISTINCT neighbor.id, neighbor.type, neighbor.name,
                       neighbor.properties
                LIMIT 50
                """,
                {"entity_id": entity_id, "tenant_id": tenant_id},
            )

            neighbors = []
            async for record in result:
                entity = Entity(
                    id=record[0],
                    type=record[1],
                    name=record[2],
                    tenant_id=tenant_id,
                    properties=json.loads(record[3]) if record[3] else {},
                )
                neighbors.append((entity, "RELATES_TO", 1.0))

            return neighbors

    async def personalized_pagerank(
        self,
        tenant_id: str,
        seed_entities: list[str],
        damping: float = 0.85,
        max_iterations: int = 20,
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """Esegue Personalized PageRank per retrieval associativo.

        Simula l'attivazione di nodi distanti nel grafo partendo
        da entità seed, come fa l'ippocampo umano.

        Uses custom implementation since Neo4j Community doesn't include GDS.

        Args:
            tenant_id: ID tenant per isolation
            seed_entities: Lista di ID entità di partenza
            damping: Fattore di damping (0.85 standard)
            max_iterations: Iterazioni massime
            top_k: Numero di risultati

        Returns:
            Lista di (entity_id, score) ordinata per score
        """
        driver = await self.get_driver()
        if driver is None:
            return []

        # Inizializza scores
        scores: dict[str, float] = dict.fromkeys(seed_entities, 1.0)
        visited: set[str] = set()

        async with driver.session() as session:
            for _iteration in range(max_iterations):
                # Ottieni lista degli IDs correnti con score significativo
                current_ids = [
                    eid for eid, score in scores.items() if score > 0.001 and eid not in visited
                ]
                if not current_ids:
                    break

                # Recupera tutti i vicini per tutti i nodi correnti in un colpo solo
                result = await session.run(
                    """
                    MATCH (e:Entity)-[r:RELATES_TO]->(neighbor:Entity)
                    WHERE e.tenant_id = $tenant_id 
                      AND neighbor.tenant_id = $tenant_id
                      AND e.id IN $ids
                    RETURN e.id as source_id, neighbor.id as target_id, r.weight as weight
                    """,
                    {"ids": current_ids, "tenant_id": tenant_id},
                )

                new_scores: dict[str, float] = {}

                # Raggruppa i risultati per sorgente per calcolare il peso totale locale
                propagation_map: dict[str, list[tuple[str, float]]] = {}
                source_total_weights: dict[str, float] = {}

                async for record in result:
                    sid, tid, w = record["source_id"], record["target_id"], record["weight"] or 1.0
                    if sid not in propagation_map:
                        propagation_map[sid] = []
                        source_total_weights[sid] = 0.0
                    propagation_map[sid].append((tid, w))
                    source_total_weights[sid] += w
                    visited.add(sid)

                # Propaga gli score
                for sid, neighbors in propagation_map.items():
                    source_score = scores.get(sid, 0.0)
                    total_w = source_total_weights[sid]

                    for tid, w in neighbors:
                        propagated = source_score * damping * (w / total_w)
                        new_scores[tid] = new_scores.get(tid, 0.0) + propagated

                # Merge scores
                for nid, nscore in new_scores.items():
                    scores[nid] = scores.get(nid, 0.0) + nscore

                # Teleport back to seeds (PPR)
                for seed in seed_entities:
                    scores[seed] = scores.get(seed, 0) + (1 - damping)

        # Normalizza e ordina
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}

        # Escludi seeds e ordina
        ranked = [(eid, score) for eid, score in scores.items() if eid not in seed_entities]
        ranked.sort(key=lambda x: x[1], reverse=True)

        return ranked[:top_k]

    async def delete_entity(self, tenant_id: str, entity_id: str) -> bool:
        """Elimina un'entità e le sue relazioni (GDPR compliance)."""
        driver = await self.get_driver()
        if driver is None:
            return False

        # Verifica esistenza e ownership
        entity = await self.get_entity(tenant_id, entity_id)
        if entity is None:
            return False

        async with driver.session() as session:
            # Elimina nodo e tutte le relazioni (DETACH DELETE)
            await session.run(
                """
                MATCH (e:Entity {id: $entity_id, tenant_id: $tenant_id})
                DETACH DELETE e
                """,
                {"entity_id": entity_id, "tenant_id": tenant_id},
            )

        logger.info(
            "entity_deleted",
            entity_id=entity_id,
            tenant_id=tenant_id,
        )

        return True

    async def traverse_graph(
        self,
        tenant_id: str,
        start_id: str,
        relation_types: list[str] | None = None,
        max_depth: int = 3,
        max_nodes: int = 50,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Traversa il grafo da un nodo di partenza.

        Args:
            tenant_id: Tenant isolation
            start_id: Entity ID di partenza
            relation_types: Tipi di relazione da seguire
            max_depth: Profondità massima
            max_nodes: Numero massimo di nodi

        Returns:
            Tuple (nodes, edges) per la visualizzazione
        """
        import json

        driver = await self.get_driver()
        if driver is None:
            return [], []

        # Build relationship filter
        rel_filter = ""
        if relation_types:
            rel_filter = f"[:{' | '.join(relation_types)}]"
        else:
            rel_filter = ""

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        visited: set[str] = set()

        async with driver.session() as session:
            # BFS traversal - corretta sintassi Neo4j per variable-length paths
            # Se nessun filtro relazione, usa qualsiasi tipo
            if relation_types:
                rel_pattern = f"[r:{' | '.join(relation_types)}*1..{max_depth}]"
            else:
                rel_pattern = f"[r*1..{max_depth}]"

            result = await session.run(
                f"""
                MATCH path = (start:Entity {{id: $start_id, tenant_id: $tenant_id}})
                      -{rel_pattern}->
                      (end:Entity {{tenant_id: $tenant_id}})
                UNWIND nodes(path) AS node
                UNWIND relationships(path) AS rel
                WITH DISTINCT node, rel
                RETURN
                    node.id AS node_id,
                    node.name AS node_name,
                    node.type AS node_type,
                    node.properties AS node_props,
                    startNode(rel).id AS rel_source,
                    endNode(rel).id AS rel_target,
                    type(rel) AS rel_type
                LIMIT $max_nodes
                """,
                {
                    "start_id": start_id,
                    "tenant_id": tenant_id,
                    "max_nodes": max_nodes,
                },
            )

            async for record in result:
                node_id = record["node_id"]
                if node_id not in visited:
                    visited.add(node_id)
                    nodes.append(
                        {
                            "id": node_id,
                            "name": record["node_name"] or "",
                            "type": record["node_type"] or "",
                            "properties": json.loads(record["node_props"])
                            if record["node_props"]
                            else {},
                            "depth": 0,  # Will be calculated
                        }
                    )

                if record["rel_source"] and record["rel_target"]:
                    edges.append(
                        {
                            "source": record["rel_source"],
                            "target": record["rel_target"],
                            "type": record["rel_type"] or "RELATES_TO",
                        }
                    )

        # Add start node if not present
        if start_id not in visited:
            entity = await self.get_entity(tenant_id, start_id)
            if entity:
                nodes.insert(
                    0,
                    {
                        "id": entity.id,
                        "name": entity.name,
                        "type": entity.type,
                        "properties": entity.properties,
                        "depth": 0,
                    },
                )

        logger.debug("graph_traversal", start=start_id, nodes=len(nodes), edges=len(edges))
        return nodes, edges

    async def merge_entities(
        self,
        tenant_id: str,
        entity_ids: list[str],
        target_name: str,
        strategy: str = "keep_all_properties",
    ) -> dict[str, Any]:
        """Unisce entità duplicate mantenendo relazioni.

        Args:
            tenant_id: Tenant isolation
            entity_ids: IDs delle entità da unire
            target_name: Nome per l'entità risultante
            strategy: Strategia merge (keep_all_properties, prefer_first)

        Returns:
            Dict con merged_id e properties unificate
        """
        import json
        from uuid import uuid4

        driver = await self.get_driver()
        if driver is None:
            raise RuntimeError("Neo4j non disponibile")

        # Raccogli proprietà da tutte le entità
        merged_props: dict[str, Any] = {}
        entity_type = "Entity"

        async with driver.session() as session:
            for eid in entity_ids:
                result = await session.run(
                    """
                    MATCH (e:Entity {id: $id, tenant_id: $tenant_id})
                    RETURN e.type, e.properties
                    """,
                    {"id": eid, "tenant_id": tenant_id},
                )
                record = await result.single()
                if record:
                    entity_type = record[0] or entity_type
                    props = json.loads(record[1]) if record[1] else {}
                    if strategy == "keep_all_properties":
                        merged_props.update(props)
                    elif strategy == "prefer_first" and not merged_props:
                        merged_props = props

            # Crea nuova entità merged
            merged_id = f"merged_{uuid4().hex[:8]}"
            await session.run(
                """
                CREATE (e:Entity {
                    id: $id,
                    type: $type,
                    name: $name,
                    tenant_id: $tenant_id,
                    properties: $properties,
                    created_at: datetime(),
                    updated_at: datetime(),
                    merged_from: $merged_from
                })
                """,
                {
                    "id": merged_id,
                    "type": entity_type,
                    "name": target_name,
                    "tenant_id": tenant_id,
                    "properties": json.dumps(merged_props),
                    "merged_from": json.dumps(entity_ids),
                },
            )

            # Sposta relazioni in entrata verso merged
            for eid in entity_ids:
                await session.run(
                    """
                    MATCH (source:Entity)-[r:RELATES_TO]->(old:Entity {id: $old_id})
                    MATCH (merged:Entity {id: $merged_id})
                    WHERE source.id <> $merged_id
                    CREATE (source)-[r2:RELATES_TO]->(merged)
                    SET r2 = properties(r)
                    DELETE r
                    """,
                    {"old_id": eid, "merged_id": merged_id},
                )

                # Sposta relazioni in uscita
                await session.run(
                    """
                    MATCH (old:Entity {id: $old_id})-[r:RELATES_TO]->(target:Entity)
                    MATCH (merged:Entity {id: $merged_id})
                    WHERE target.id <> $merged_id
                    CREATE (merged)-[r2:RELATES_TO]->(target)
                    SET r2 = properties(r)
                    DELETE r
                    """,
                    {"old_id": eid, "merged_id": merged_id},
                )

                # Elimina vecchia entità
                await session.run(
                    """
                    MATCH (e:Entity {id: $id, tenant_id: $tenant_id})
                    DETACH DELETE e
                    """,
                    {"id": eid, "tenant_id": tenant_id},
                )

        logger.info("entities_merged", merged_id=merged_id, count=len(entity_ids))
        return {"merged_id": merged_id, "properties": merged_props}

    async def consolidate_episode(
        self,
        tenant_id: str,
        episode: dict[str, Any],
    ) -> dict[str, int]:
        """Consolida un episodio nel knowledge graph.

        Estrae entità e relazioni dall'episodio e le aggiunge al grafo.

        Args:
            tenant_id: Tenant isolation
            episode: Dati episodio con content, entities, relations

        Returns:
            Dict con conteggio entities e relations create
        """
        from uuid import uuid4

        entities_created = 0
        relations_created = 0

        # Estrai entità dal contenuto (semplificato, usa NER in prod)
        entities_data = episode.get("entities", [])
        for entity_data in entities_data:
            entity = Entity(
                id=entity_data.get("id", f"ent_{uuid4().hex[:8]}"),
                type=entity_data.get("type", "Concept"),
                name=entity_data.get("name", ""),
                tenant_id=tenant_id,
                properties=entity_data.get("properties", {}),
            )
            await self.add_entity(entity)
            entities_created += 1

        # Estrai relazioni
        relations_data = episode.get("relations", [])
        for rel_data in relations_data:
            relation = Relation(
                source_id=rel_data.get("source_id", ""),
                target_id=rel_data.get("target_id", ""),
                type=rel_data.get("type", "RELATES_TO"),
                tenant_id=tenant_id,
                weight=rel_data.get("weight", 1.0),
            )
            if relation.source_id and relation.target_id:
                await self.add_relation(relation)
                relations_created += 1

        logger.debug(
            "episode_consolidated",
            episode_id=episode.get("id"),
            entities=entities_created,
            relations=relations_created,
        )

        return {"entities": entities_created, "relations": relations_created}

    async def search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Ricerca testuale nel knowledge graph.

        Args:
            tenant_id: Tenant isolation
            query: Query di ricerca
            limit: Numero massimo risultati

        Returns:
            Lista di entità matching
        """
        import json

        driver = await self.get_driver()
        if driver is None:
            return []

        results: list[dict[str, Any]] = []

        async with driver.session() as session:
            # Ricerca per nome (case-insensitive)
            result = await session.run(
                """
                MATCH (e:Entity {tenant_id: $tenant_id})
                WHERE toLower(e.name) CONTAINS toLower($query)
                   OR toLower(e.properties) CONTAINS toLower($query)
                RETURN e.id, e.type, e.name, e.properties
                LIMIT $limit
                """,
                {"tenant_id": tenant_id, "query": query, "limit": limit},
            )

            async for record in result:
                results.append(
                    {
                        "id": record[0],
                        "type": record[1],
                        "name": record[2],
                        "properties": json.loads(record[3]) if record[3] else {},
                        "score": 1.0,  # Basic text match
                    }
                )

        return results

    async def close(self) -> None:
        """Chiude le connessioni."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.debug("neo4j_closed")


# Singleton
_semantic_memory: SemanticMemory | None = None


def get_semantic_memory() -> SemanticMemory:
    """Ottiene l'istanza singleton di SemanticMemory."""
    global _semantic_memory
    if _semantic_memory is None:
        _semantic_memory = SemanticMemory()
    return _semantic_memory
