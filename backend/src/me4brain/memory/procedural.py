"""Procedural Memory - Skill & Muscle Memory Layer.

Implementa il Layer IV del sistema cognitivo:
- Skill Graph per mappatura Intento -> Tool
- Muscle Memory (Few-Shot cache) per bypass ragionamento
- Reinforcement learning implicito (peso adattivo)
"""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient, models

from me4brain.config import get_settings
from me4brain.engine.hybrid_router.constants import CAPABILITIES_COLLECTION
from me4brain.memory.semantic import SemanticMemory, get_semantic_memory

logger = structlog.get_logger(__name__)


class Tool(BaseModel):
    """Rappresenta un tool/API disponibile."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str
    tenant_id: str

    # Specifiche API
    endpoint: str | None = None
    method: str = "POST"
    api_schema: dict[str, Any] = Field(default_factory=dict)

    # Stato
    status: str = "ACTIVE"  # ACTIVE, DEPRECATED, EXPERIMENTAL
    version: str = "1.0"

    # Metriche
    success_rate: float = 0.5
    avg_latency_ms: float = 0.0
    total_calls: int = 0


class ToolExecution(BaseModel):
    """Record di un'esecuzione di tool (per Muscle Memory)."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    user_id: str

    # Contesto
    intent: str  # Descrizione dell'intento utente
    tool_id: str
    tool_name: str

    # Esecuzione
    input_json: dict[str, Any]
    output_json: dict[str, Any] | None = None
    success: bool = True
    error_message: str | None = None

    # Temporalità
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    latency_ms: float = 0.0


class ProceduralMemory:
    """Gestisce la memoria procedurale (Skill & Muscle Memory).

    Architettura:
    - Skill Graph (Neo4j): Grafo Intento -> Tool con pesi adattivi
    - Muscle Memory (Qdrant): Cache few-shot di esecuzioni di successo
    """

    COLLECTION_NAME = "muscle_memory"
    TOOLS_COLLECTION = CAPABILITIES_COLLECTION  # Collection unificata per ricerca vettoriale capabilities
    VECTOR_SIZE = 1024

    def __init__(
        self,
        semantic_memory: SemanticMemory | None = None,
        qdrant_client: AsyncQdrantClient | None = None,
    ) -> None:
        """Inizializza Procedural Memory."""
        self._semantic = semantic_memory
        self._qdrant: AsyncQdrantClient | None = qdrant_client

    def get_semantic(self) -> SemanticMemory:
        """Ottiene SemanticMemory (per Skill Graph)."""
        if self._semantic is None:
            self._semantic = get_semantic_memory()
        return self._semantic

    async def get_qdrant(self) -> AsyncQdrantClient:
        """Ottiene client Qdrant (per Muscle Memory)."""
        if self._qdrant is None:
            settings = get_settings()
            self._qdrant = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_http_port,
            )
        return self._qdrant

    async def initialize(self) -> None:
        """Inizializza collection per Muscle Memory e Tools."""
        client = await self.get_qdrant()

        collections = await client.get_collections()
        collection_names = [c.name for c in collections.collections]

        # Muscle Memory collection
        if self.COLLECTION_NAME not in collection_names:
            await client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )

            # Indici per filtering
            await client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="tenant_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            await client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="tool_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            logger.info("muscle_memory_collection_created")

        # Tools collection per ricerca vettoriale veloce
        if self.TOOLS_COLLECTION not in collection_names:
            await client.create_collection(
                collection_name=self.TOOLS_COLLECTION,
                vectors_config=models.VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=models.Distance.COSINE,
                ),
            )

            # Indice per tenant isolation
            await client.create_payload_index(
                collection_name=self.TOOLS_COLLECTION,
                field_name="tenant_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            # Indice per status filtering
            await client.create_payload_index(
                collection_name=self.TOOLS_COLLECTION,
                field_name="status",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            logger.info("tools_collection_created")

    # -------------------------------------------------------------------------
    # Skill Graph (Neo4j)
    # -------------------------------------------------------------------------

    async def register_tool(self, tool: Tool) -> str:
        """Registra un nuovo tool nel Skill Graph.

        Args:
            tool: Il tool da registrare

        Returns:
            ID del tool
        """
        semantic = self.get_semantic()

        from me4brain.memory.semantic import Entity

        entity = Entity(
            id=tool.id,
            type="Tool",
            name=tool.name,
            tenant_id=tool.tenant_id,
            properties={
                "description": tool.description,
                "endpoint": tool.endpoint,
                "method": tool.method,
                "schema_json": tool.api_schema,
                "status": tool.status,
                "version": tool.version,
                "success_rate": tool.success_rate,
                "avg_latency_ms": tool.avg_latency_ms,
                "total_calls": tool.total_calls,
            },
        )

        await semantic.add_entity(entity)
        logger.info("tool_registered", tool_id=tool.id, tool_name=tool.name)

        return tool.id

    async def index_tool_in_qdrant(
        self,
        tool: Tool,
        embedding: list[float],
    ) -> None:
        """Indicizza un tool in Qdrant per ricerca vettoriale veloce.

        Args:
            tool: Il tool da indicizzare
            embedding: Embedding della descrizione del tool
        """
        client = await self.get_qdrant()

        payload = {
            "tool_id": tool.id,
            "name": tool.name,
            "description": tool.description[:500] if tool.description else "",
            "tenant_id": tool.tenant_id,
            "endpoint": tool.endpoint,
            "method": tool.method,
            "status": tool.status,
            "category": tool.name.split("_")[0] if "_" in tool.name else "general",
        }

        await client.upsert(
            collection_name=self.TOOLS_COLLECTION,
            points=[
                models.PointStruct(
                    id=tool.id,
                    vector=embedding,
                    payload=payload,
                )
            ],
        )

        logger.debug("tool_indexed_qdrant", tool_id=tool.id, tool_name=tool.name)

    async def search_tools_in_qdrant(
        self,
        tenant_id: str,
        query_embedding: list[float],
        limit: int = 10,
        min_score: float = 0.3,
    ) -> list[tuple[str, dict, float]]:
        """Cerca tool simili in Qdrant.

        Args:
            tenant_id: ID tenant
            query_embedding: Embedding della query
            limit: Numero massimo di risultati
            min_score: Score minimo per inclusione

        Returns:
            Lista di (tool_id, payload, score)
        """
        client = await self.get_qdrant()

        results = await client.query_points(
            collection_name=self.TOOLS_COLLECTION,
            query=query_embedding,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="tenant_id",
                        match=models.MatchValue(value=tenant_id),
                    ),
                    models.FieldCondition(
                        key="status",
                        match=models.MatchValue(value="ACTIVE"),
                    ),
                ]
            ),
            limit=limit,
            score_threshold=min_score,
            with_payload=True,
        )

        return [
            (str(point.id), point.payload or {}, point.score or 0.0) for point in results.points
        ]

    async def register_intent(
        self,
        tenant_id: str,
        intent: str,
        tool_ids: list[str],
        initial_weight: float = 0.5,
    ) -> str:
        """Registra un intento e lo collega ai tool.

        Args:
            tenant_id: ID tenant
            intent: Descrizione dell'intento
            tool_ids: Lista di tool che risolvono l'intento
            initial_weight: Peso iniziale delle relazioni

        Returns:
            ID dell'intento
        """
        semantic = self.get_semantic()

        from me4brain.memory.semantic import Entity, Relation

        # Crea nodo Intent
        intent_id = str(uuid4())
        intent_entity = Entity(
            id=intent_id,
            type="Intent",
            name=intent,
            tenant_id=tenant_id,
        )
        await semantic.add_entity(intent_entity)

        # Crea relazioni SOLVES (Tool -> Intent)
        for tool_id in tool_ids:
            relation = Relation(
                source_id=tool_id,
                target_id=intent_id,
                type="SOLVES",
                tenant_id=tenant_id,
                weight=initial_weight,
            )
            await semantic.add_relation(relation)

        logger.info(
            "intent_registered",
            intent_id=intent_id,
            intent=intent,
            tools=tool_ids,
        )

        return intent_id

    async def find_tools_for_intent(
        self,
        tenant_id: str,
        intent_embedding: list[float],
        top_k: int = 5,
        min_weight: float = 0.2,
        query_text: str | None = None,
    ) -> list[tuple[Tool, float]]:
        """Trova i tool migliori per un intento usando ricerca semantica.

        Strategia:
        1. Prima cerca in Qdrant (veloce, indice vettoriale)
        2. Se Qdrant non trova abbastanza risultati, fallback su Neo4j

        Args:
            tenant_id: ID tenant
            intent_embedding: Embedding dell'intento (query)
            top_k: Numero massimo di risultati
            min_weight: Score minimo per inclusione
            query_text: Testo originale della query (non usato con Qdrant)

        Returns:
            Lista di (Tool, score) ordinata per relevance
        """
        # Strategia 1: Cerca in Qdrant (veloce, pre-indicizzato)
        try:
            qdrant_results = await self.search_tools_in_qdrant(
                tenant_id=tenant_id,
                query_embedding=intent_embedding,
                limit=top_k * 2,  # Richiedi più risultati per avere margine
                min_score=min_weight,
            )

            if len(qdrant_results) >= top_k // 2:
                # Abbastanza risultati da Qdrant
                results = []
                for tool_id, payload, score in qdrant_results[:top_k]:
                    tool = Tool(
                        id=tool_id,
                        name=payload.get("name", ""),
                        tenant_id=tenant_id,
                        description=payload.get("description", ""),
                        endpoint=payload.get("endpoint"),
                        method=payload.get("method", "POST"),
                        status=payload.get("status", "ACTIVE"),
                    )
                    results.append((tool, score))

                logger.info(
                    "qdrant_tool_search_completed",
                    tenant_id=tenant_id,
                    results=len(results),
                )
                return results

        except Exception as e:
            logger.warning("qdrant_tool_search_failed", error=str(e))
            # Continua con fallback Neo4j

        # Strategia 2: Fallback su Neo4j con calcolo embedding runtime
        return await self._search_tools_neo4j_fallback(
            tenant_id=tenant_id,
            intent_embedding=intent_embedding,
            top_k=top_k,
            min_weight=min_weight,
        )

    async def _search_tools_neo4j_fallback(
        self,
        tenant_id: str,
        intent_embedding: list[float],
        top_k: int = 5,
        min_weight: float = 0.2,
    ) -> list[tuple[Tool, float]]:
        """Fallback: cerca tool in Neo4j con calcolo embedding runtime.

        Usato quando Qdrant non ha risultati o non è disponibile.
        """
        import numpy as np
        from me4brain.embeddings import get_embedding_service

        semantic = self.get_semantic()
        driver = await semantic.get_driver()

        if driver is None:
            logger.warning("neo4j_not_available", fallback="empty_results")
            return []

        # Recupera tutti i tool attivi del tenant
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (t:Entity {type: 'Tool', tenant_id: $tenant_id})
                RETURN t.id, t.name, t.properties
                """,
                {"tenant_id": tenant_id},
            )

            candidates = []
            async for record in result:
                props = json.loads(record[2]) if record[2] else {}

                if props.get("status") != "ACTIVE":
                    continue

                candidates.append(
                    {
                        "id": record[0],
                        "name": record[1],
                        "description": props.get("description", ""),
                        "props": props,
                    }
                )

        if not candidates:
            logger.debug("no_tools_found", tenant_id=tenant_id)
            return []

        # Limita candidati per performance
        MAX_CANDIDATES = 100
        if len(candidates) > MAX_CANDIDATES:
            import random

            random.shuffle(candidates)
            candidates = candidates[:MAX_CANDIDATES]

        # Genera embedding per le descrizioni
        embedding_service = get_embedding_service()
        MAX_DESC_LEN = 200
        descriptions = [(c["description"] or c["name"])[:MAX_DESC_LEN] for c in candidates]

        try:
            BATCH_SIZE = 16
            tool_embeddings = []
            for i in range(0, len(descriptions), BATCH_SIZE):
                batch = descriptions[i : i + BATCH_SIZE]
                batch_embeddings = embedding_service.embed_documents(batch)
                tool_embeddings.extend(batch_embeddings)
        except Exception as e:
            logger.error("embedding_generation_failed", error=str(e))
            return self._fallback_tool_search(candidates, top_k, min_weight)

        # Calcola cosine similarity
        query_vec = np.array(intent_embedding)
        query_norm = np.linalg.norm(query_vec)

        scored_tools = []
        for i, candidate in enumerate(candidates):
            tool_vec = np.array(tool_embeddings[i])
            tool_norm = np.linalg.norm(tool_vec)

            if query_norm == 0 or tool_norm == 0:
                similarity = 0.0
            else:
                similarity = float(np.dot(query_vec, tool_vec) / (query_norm * tool_norm))

            if similarity < min_weight:
                continue

            props = candidate["props"]
            tool = Tool(
                id=candidate["id"],
                name=candidate["name"],
                tenant_id=tenant_id,
                description=props.get("description", ""),
                endpoint=props.get("endpoint"),
                method=props.get("method", "POST"),
                api_schema=props.get("schema_json", {}),
                status=props.get("status", "ACTIVE"),
                success_rate=props.get("success_rate", 0.5),
                avg_latency_ms=props.get("avg_latency_ms", 0.0),
                total_calls=props.get("total_calls", 0),
            )
            scored_tools.append((tool, similarity))

        scored_tools.sort(key=lambda x: x[1], reverse=True)

        logger.info(
            "neo4j_fallback_search_completed",
            candidates=len(candidates),
            results=len(scored_tools[:top_k]),
        )

        return scored_tools[:top_k]

    def _fallback_tool_search(
        self,
        candidates: list[dict],
        top_k: int,
        min_weight: float,
    ) -> list[tuple[Tool, float]]:
        """Fallback search basato su success_rate quando embedding fallisce."""
        tools = []
        for c in candidates:
            props = c["props"]
            success_rate = props.get("success_rate", 0.5)

            if success_rate < min_weight:
                continue

            tool = Tool(
                id=c["id"],
                name=c["name"],
                tenant_id=props.get("tenant_id", ""),
                description=props.get("description", ""),
                endpoint=props.get("endpoint"),
                method=props.get("method", "POST"),
                api_schema=props.get("schema_json", {}),
                status=props.get("status", "ACTIVE"),
                success_rate=success_rate,
            )
            tools.append((tool, success_rate))

        tools.sort(key=lambda x: x[1], reverse=True)
        return tools[:top_k]

    async def update_tool_weight(
        self,
        tenant_id: str,
        tool_id: str,
        success: bool,
    ) -> None:
        """Aggiorna il peso di un tool dopo un'esecuzione.

        Reinforcement learning implicito:
        - Successo: weight += (1 - weight) * 0.1
        - Fallimento: weight *= 0.8

        Args:
            tenant_id: ID tenant
            tool_id: ID del tool
            success: Se l'esecuzione ha avuto successo
        """
        semantic = self.get_semantic()
        driver = await semantic.get_driver()

        # Skip se Neo4j non disponibile
        if driver is None:
            logger.debug("update_tool_weight_skipped", reason="neo4j_unavailable")
            return

        async with driver.session() as session:
            # Recupera tool corrente
            result = await session.run(
                """
                MATCH (t:Entity {id: $tool_id, tenant_id: $tenant_id})
                RETURN t.properties
                """,
                {"tool_id": tool_id, "tenant_id": tenant_id},
            )

            record = await result.single()
            if record is None:
                return

            props = json.loads(record[0]) if record[0] else {}
            current_rate = props.get("success_rate", 0.5)
            total_calls = props.get("total_calls", 0)

            # Aggiorna metriche
            new_rate = current_rate + (1.0 - current_rate) * 0.1 if success else current_rate * 0.8

            props["success_rate"] = max(0.0, min(1.0, new_rate))
            props["total_calls"] = total_calls + 1

            # Salva
            await session.run(
                """
                MATCH (t:Entity {id: $tool_id, tenant_id: $tenant_id})
                SET t.properties = $properties, t.updated_at = datetime($updated_at)
                """,
                {
                    "tool_id": tool_id,
                    "tenant_id": tenant_id,
                    "properties": json.dumps(props),
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )

        logger.debug(
            "tool_weight_updated",
            tool_id=tool_id,
            success=success,
            old_rate=current_rate,
            new_rate=new_rate,
        )

    # -------------------------------------------------------------------------
    # Muscle Memory (Qdrant)
    # -------------------------------------------------------------------------

    async def save_execution(
        self,
        execution: ToolExecution,
        intent_embedding: list[float],
    ) -> str:
        """Salva un'esecuzione di successo per Muscle Memory.

        Solo le esecuzioni di successo vengono salvate come
        "few-shot examples" per bypass del ragionamento.

        Args:
            execution: Record dell'esecuzione
            intent_embedding: Embedding dell'intento

        Returns:
            ID dell'esecuzione salvata
        """
        if not execution.success:
            logger.debug("execution_not_saved", reason="not_successful")
            return ""

        client = await self.get_qdrant()

        payload = {
            "tenant_id": execution.tenant_id,
            "user_id": execution.user_id,
            "intent": execution.intent,
            "tool_id": execution.tool_id,
            "tool_name": execution.tool_name,
            "input_json": execution.input_json,
            "output_json": execution.output_json,
            "executed_at": execution.executed_at.isoformat(),
            "latency_ms": execution.latency_ms,
        }

        await client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[
                models.PointStruct(
                    id=execution.id,
                    vector=intent_embedding,
                    payload=payload,
                )
            ],
        )

        logger.debug(
            "execution_saved",
            execution_id=execution.id,
            tool=execution.tool_name,
        )

        return execution.id

    async def find_similar_execution(
        self,
        tenant_id: str,
        intent_embedding: list[float],
        tool_id: str | None = None,
        min_score: float = 0.85,
    ) -> ToolExecution | None:
        """Cerca un'esecuzione simile per Muscle Memory bypass.

        Se trova un'esecuzione abbastanza simile, l'agente può
        usare lo stesso input_json come template invece di
        ragionare da zero.

        Args:
            tenant_id: ID tenant
            intent_embedding: Embedding dell'intento corrente
            tool_id: Filtra per tool specifico (opzionale)
            min_score: Score minimo per match

        Returns:
            Esecuzione simile o None
        """
        client = await self.get_qdrant()

        # Costruisci filtro
        must_conditions = [
            models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=tenant_id),
            )
        ]

        if tool_id:
            must_conditions.append(
                models.FieldCondition(
                    key="tool_id",
                    match=models.MatchValue(value=tool_id),
                )
            )

        response = await client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=intent_embedding,
            query_filter=models.Filter(must=must_conditions),
            limit=1,
            score_threshold=min_score,
            with_payload=True,
        )

        if not response.points:
            return None

        point = response.points[0]
        payload = point.payload or {}

        execution = ToolExecution(
            id=str(point.id),
            tenant_id=payload.get("tenant_id", tenant_id),
            user_id=payload.get("user_id", ""),
            intent=payload.get("intent", ""),
            tool_id=payload.get("tool_id", ""),
            tool_name=payload.get("tool_name", ""),
            input_json=payload.get("input_json", {}),
            output_json=payload.get("output_json"),
            success=True,
            executed_at=datetime.fromisoformat(payload["executed_at"])
            if "executed_at" in payload
            else datetime.now(UTC),
            latency_ms=payload.get("latency_ms", 0.0),
        )

        logger.info(
            "muscle_memory_hit",
            execution_id=execution.id,
            tool=execution.tool_name,
            score=point.score,
        )

        return execution

    async def close(self) -> None:
        """Chiude le connessioni."""
        if self._qdrant:
            await self._qdrant.close()


# Singleton
_procedural_memory: ProceduralMemory | None = None


def get_procedural_memory() -> ProceduralMemory:
    """Ottiene l'istanza singleton di ProceduralMemory."""
    global _procedural_memory
    if _procedural_memory is None:
        _procedural_memory = ProceduralMemory()
    return _procedural_memory
