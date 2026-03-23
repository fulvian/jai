"""Episodic Memory - Long Term Autobiographical Memory.

Implementa il Layer II del sistema cognitivo:
- Qdrant per storage vettoriale degli episodi
- Tiered Multitenancy (payload filtering + shard promotion)
- A-MEM pattern per note atomiche auto-organizzanti
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient, models
from qdrant_client.models import Distance, VectorParams

from me4brain.config import get_settings

logger = structlog.get_logger(__name__)


class Episode(BaseModel):
    """Modello per un episodio di memoria.

    Rappresenta un'unità atomica di memoria episodica
    secondo il pattern A-MEM (Agentic Memory).
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    user_id: str

    # Contenuto
    content: str
    summary: str | None = None

    # Temporalità bitemporale
    event_time: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Quando l'evento è accaduto",
    )
    ingestion_time: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Quando è stato registrato",
    )

    # Metadati
    source: str = "conversation"  # conversation, document, tool, etc.
    importance: float = 0.5  # 0-1, per priorità nel retrieval
    tags: list[str] = Field(default_factory=list)

    # Linking (A-MEM)
    related_episodes: list[str] = Field(
        default_factory=list,
        description="IDs di episodi correlati (auto-linking)",
    )


class EpisodicMemory:
    """Gestisce la memoria episodica a lungo termine.

    Utilizza Qdrant con Tiered Multitenancy:
    - Single collection con payload filtering per tenant piccoli
    - Shard promotion per tenant grandi (>10% del cluster)
    """

    COLLECTION_NAME = "memories"
    VECTOR_SIZE = 1024  # BGE-M3 dimension
    DEFAULT_LIMIT = 10

    def __init__(
        self,
        client: AsyncQdrantClient | None = None,
        embedding_fn: Any | None = None,
    ) -> None:
        """Inizializza Episodic Memory.

        Args:
            client: Client Qdrant opzionale (per testing/DI)
            embedding_fn: Funzione di embedding opzionale
        """
        self._client: AsyncQdrantClient | None = client
        self._embedding_fn = embedding_fn

    async def get_client(self) -> AsyncQdrantClient:
        """Lazy initialization del client Qdrant."""
        if self._client is None:
            settings = get_settings()
            self._client = AsyncQdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_http_port,
                prefer_grpc=True,
                grpc_port=settings.qdrant_grpc_port,
            )
        return self._client

    async def initialize(self) -> None:
        """Inizializza la collection se non esiste.

        Configura:
        - Vettori con HNSW per ricerca veloce
        - Payload indexing per tenant_id (Tiered MT)
        """
        client = await self.get_client()

        # Verifica se collection esiste
        collections = await client.get_collections()
        exists = any(c.name == self.COLLECTION_NAME for c in collections.collections)

        if not exists:
            await client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=Distance.COSINE,
                    on_disk=True,  # Usa mmap per RAM efficiency
                ),
                # Shard key per Tiered Multitenancy
                sharding_method=models.ShardingMethod.AUTO,
                # Ottimizzazioni per M1 Pro
                optimizers_config=models.OptimizersConfigDiff(
                    indexing_threshold=10000,
                    memmap_threshold=50000,
                ),
            )

            # Crea indice sul tenant_id per filtering veloce
            await client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="tenant_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            # Indice su user_id
            await client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="user_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

            # Indice su event_time per range queries
            await client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="event_time",
                field_schema=models.PayloadSchemaType.DATETIME,
            )

            logger.info(
                "episodic_collection_created",
                collection=self.COLLECTION_NAME,
                vector_size=self.VECTOR_SIZE,
            )

    async def add_episode(
        self,
        episode: Episode,
        embedding: list[float],
    ) -> str:
        """Aggiunge un episodio alla memoria.

        Args:
            episode: L'episodio da memorizzare
            embedding: Vettore di embedding del contenuto

        Returns:
            ID dell'episodio creato
        """
        client = await self.get_client()

        # Costruisci payload
        payload = {
            "tenant_id": episode.tenant_id,
            "user_id": episode.user_id,
            "content": episode.content,
            "summary": episode.summary,
            "event_time": episode.event_time.isoformat(),
            "ingestion_time": episode.ingestion_time.isoformat(),
            "source": episode.source,
            "importance": episode.importance,
            "tags": episode.tags,
            "related_episodes": episode.related_episodes,
        }

        # Upsert con shard key selector per Tiered MT
        await client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=[
                models.PointStruct(
                    id=episode.id,
                    vector=embedding,
                    payload=payload,
                )
            ],
            # Shard key selector temporaneamente rimosso per stabilità test
            # shard_key_selector=episode.tenant_id,
        )

        logger.debug(
            "episode_added",
            episode_id=episode.id,
            tenant_id=episode.tenant_id,
            source=episode.source,
        )

        return episode.id

    async def search_similar(
        self,
        tenant_id: str,
        user_id: str | None,
        query_embedding: list[float],
        limit: int = DEFAULT_LIMIT,
        min_score: float = 0.5,
        time_decay: bool = True,
    ) -> list[tuple[Episode, float]]:
        """Cerca episodi simili semanticamente.

        Args:
            tenant_id: ID tenant (obbligatorio per isolation)
            user_id: ID utente (opzionale, filtra ulteriormente)
            query_embedding: Vettore della query
            limit: Numero massimo di risultati
            min_score: Score minimo per inclusione
            time_decay: Applica decay temporale

        Returns:
            Lista di (Episode, score) ordinata per rilevanza
        """
        client = await self.get_client()

        # Costruisci filtro multi-tenant
        must_conditions = [
            models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=tenant_id),
            )
        ]

        if user_id:
            must_conditions.append(
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id),
                )
            )

        # Ricerca con shard key per routing ottimizzato
        response = await client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=query_embedding,
            query_filter=models.Filter(must=must_conditions),
            limit=limit,
            score_threshold=min_score,
            with_payload=True,
            # shard_key_selector=tenant_id,
        )

        episodes = []
        for point in response.points:
            payload = point.payload or {}
            episode = Episode(
                id=str(point.id),
                tenant_id=payload.get("tenant_id", tenant_id),
                user_id=payload.get("user_id", ""),
                content=payload.get("content", ""),
                summary=payload.get("summary"),
                event_time=datetime.fromisoformat(payload["event_time"])
                if "event_time" in payload
                else datetime.now(UTC),
                ingestion_time=datetime.fromisoformat(payload["ingestion_time"])
                if "ingestion_time" in payload
                else datetime.now(UTC),
                source=payload.get("source", "unknown"),
                importance=payload.get("importance", 0.5),
                tags=payload.get("tags", []),
                related_episodes=payload.get("related_episodes", []),
            )

            score = point.score or 0.0

            # Applica time decay (episodi recenti hanno priorità)
            if time_decay:
                age_days = (datetime.now(UTC) - episode.event_time).total_seconds() / 86400
                decay_factor = 1.0 / (1.0 + 0.1 * age_days)  # Decay logaritmico
                score *= decay_factor

            episodes.append((episode, score))

        # Riordina dopo decay
        episodes.sort(key=lambda x: x[1], reverse=True)

        return episodes

    async def get_by_id(
        self,
        tenant_id: str,
        episode_id: str,
    ) -> Episode | None:
        """Recupera un episodio per ID.

        Verifica tenant isolation.
        """
        client = await self.get_client()

        results = await client.retrieve(
            collection_name=self.COLLECTION_NAME,
            ids=[episode_id],
            with_payload=True,
        )

        if not results:
            return None

        point = results[0]
        payload = point.payload or {}

        # Verifica tenant isolation
        if payload.get("tenant_id") != tenant_id:
            logger.warning(
                "episode_access_denied",
                episode_id=episode_id,
                requested_tenant=tenant_id,
                actual_tenant=payload.get("tenant_id"),
            )
            return None

        return Episode(
            id=str(point.id),
            tenant_id=payload.get("tenant_id", tenant_id),
            user_id=payload.get("user_id", ""),
            content=payload.get("content", ""),
            summary=payload.get("summary"),
            source=payload.get("source", "unknown"),
            importance=payload.get("importance", 0.5),
            tags=payload.get("tags", []),
            related_episodes=payload.get("related_episodes", []),
        )

    async def delete_episode(
        self,
        tenant_id: str,
        episode_id: str,
    ) -> bool:
        """Elimina un episodio (GDPR compliance).

        Verifica tenant isolation prima di eliminare.
        """
        # Verifica esistenza e ownership
        episode = await self.get_by_id(tenant_id, episode_id)
        if episode is None:
            return False

        client = await self.get_client()

        await client.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=models.PointIdsList(points=[episode_id]),
        )

        logger.info(
            "episode_deleted",
            episode_id=episode_id,
            tenant_id=tenant_id,
        )

        return True

    async def update_episode(
        self,
        tenant_id: str,
        episode_id: str,
        importance: float | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Episode | None:
        """Aggiorna un episodio esistente.

        Args:
            tenant_id: Tenant isolation
            episode_id: ID episodio da aggiornare
            importance: Nuovo valore importance (opzionale)
            tags: Nuovi tags (opzionale, sostituisce esistenti)
            metadata: Metadata aggiuntivo (opzionale, merged)

        Returns:
            Episodio aggiornato o None se non trovato
        """
        # Verifica esistenza e ownership
        episode = await self.get_by_id(tenant_id, episode_id)
        if episode is None:
            return None

        client = await self.get_client()

        # Prepara payload update
        payload_update: dict[str, Any] = {}
        if importance is not None:
            payload_update["importance"] = importance
        if tags is not None:
            payload_update["tags"] = tags
        if metadata is not None:
            # Merge con metadata esistente
            existing_metadata = {}
            try:
                points = await client.retrieve(
                    collection_name=self.COLLECTION_NAME,
                    ids=[episode_id],
                    with_payload=True,
                )
                if points:
                    existing_metadata = points[0].payload.get("metadata", {})
            except Exception:
                pass
            payload_update["metadata"] = {**existing_metadata, **metadata}

        if not payload_update:
            return episode  # Nessun aggiornamento richiesto

        # Aggiorna payload in Qdrant
        await client.set_payload(
            collection_name=self.COLLECTION_NAME,
            payload=payload_update,
            points=[episode_id],
        )

        logger.info(
            "episode_updated",
            episode_id=episode_id,
            tenant_id=tenant_id,
            fields_updated=list(payload_update.keys()),
        )

        # Restituisci episodio aggiornato
        return await self.get_by_id(tenant_id, episode_id)

    async def get_related_episodes(
        self,
        tenant_id: str,
        episode_id: str,
        limit: int = 5,
    ) -> list[Episode]:
        """Trova episodi correlati semanticamente.

        Args:
            tenant_id: Tenant isolation
            episode_id: ID episodio di riferimento
            limit: Numero massimo di risultati

        Returns:
            Lista di episodi correlati (ordinati per similarità)
        """
        # Recupera episodio originale
        episode = await self.get_by_id(tenant_id, episode_id)
        if episode is None:
            return []

        # Genera embedding del contenuto
        if self._embedding_fn is None:
            logger.warning("no_embedding_function_configured")
            return []

        embedding = await self._embedding_fn(episode.content)

        client = await self.get_client()

        # Cerca episodi simili (escludendo se stesso)
        results = await client.search(
            collection_name=self.COLLECTION_NAME,
            query_vector=embedding,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="tenant_id",
                        match=models.MatchValue(value=tenant_id),
                    ),
                ],
                must_not=[
                    models.HasIdCondition(has_id=[episode_id]),
                ],
            ),
            limit=limit,
            with_payload=True,
        )

        related_episodes = []
        for result in results:
            payload = result.payload or {}
            related_episodes.append(
                Episode(
                    id=str(result.id),
                    tenant_id=payload.get("tenant_id", tenant_id),
                    user_id=payload.get("user_id", ""),
                    content=payload.get("content", ""),
                    summary=payload.get("summary"),
                    event_time=datetime.fromisoformat(payload["event_time"])
                    if payload.get("event_time")
                    else datetime.now(UTC),
                    ingestion_time=datetime.fromisoformat(payload["ingestion_time"])
                    if payload.get("ingestion_time")
                    else datetime.now(UTC),
                    source=payload.get("source", "conversation"),
                    importance=payload.get("importance", 0.5),
                    tags=payload.get("tags", []),
                    related_episodes=payload.get("related_episodes", []),
                )
            )

        logger.debug(
            "related_episodes_found",
            episode_id=episode_id,
            count=len(related_episodes),
        )

        return related_episodes

    async def forget_user(
        self,
        tenant_id: str,
        user_id: str,
    ) -> int:
        """Elimina tutti gli episodi di un utente (GDPR right to be forgotten).

        Returns:
            Numero di episodi eliminati
        """
        client = await self.get_client()

        # Conta prima di eliminare
        count_result = await client.count(
            collection_name=self.COLLECTION_NAME,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="tenant_id",
                        match=models.MatchValue(value=tenant_id),
                    ),
                    models.FieldCondition(
                        key="user_id",
                        match=models.MatchValue(value=user_id),
                    ),
                ]
            ),
        )

        # Elimina con filtro
        await client.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="tenant_id",
                            match=models.MatchValue(value=tenant_id),
                        ),
                        models.FieldCondition(
                            key="user_id",
                            match=models.MatchValue(value=user_id),
                        ),
                    ]
                )
            ),
        )

        deleted_count = count_result.count
        logger.info(
            "user_forgotten",
            tenant_id=tenant_id,
            user_id=user_id,
            episodes_deleted=deleted_count,
        )

        return deleted_count

    async def get_candidates_for_consolidation(
        self,
        tenant_id: str,
        user_id: str,
        min_importance: float = 0.7,
        since: Any = None,
    ) -> list[dict[str, Any]]:
        """Trova episodi candidati per consolidation in semantic memory.

        Args:
            tenant_id: Tenant isolation
            user_id: User isolation
            min_importance: Soglia minima importanza
            since: Data minima (datetime)

        Returns:
            Lista di episodi candidati
        """

        client = await self.get_client()

        # Build filter
        must_conditions = [
            models.FieldCondition(
                key="tenant_id",
                match=models.MatchValue(value=tenant_id),
            ),
            models.FieldCondition(
                key="user_id",
                match=models.MatchValue(value=user_id),
            ),
            models.FieldCondition(
                key="importance",
                range=models.Range(gte=min_importance),
            ),
            models.FieldCondition(
                key="consolidated",
                match=models.MatchValue(value=False),
            ),
        ]

        if since:
            # Qdrant Range richiede valore numerico (timestamp)
            since_ts = since.timestamp() if hasattr(since, "timestamp") else float(since)

            must_conditions.append(
                models.FieldCondition(
                    key="created_at_ts",
                    range=models.Range(gte=since_ts),
                )
            )

        try:
            results = await client.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=models.Filter(must=must_conditions),
                limit=100,
                with_payload=True,
            )

            candidates = []
            for point in results[0]:
                payload = point.payload or {}
                candidates.append(
                    {
                        "id": str(point.id),
                        "content": payload.get("content", ""),
                        "importance": payload.get("importance", 0.5),
                        "entities": payload.get("entities", []),
                        "relations": payload.get("relations", []),
                        "metadata": payload.get("metadata", {}),
                    }
                )

            logger.debug(
                "consolidation_candidates",
                tenant_id=tenant_id,
                count=len(candidates),
            )

            return candidates

        except Exception as e:
            logger.error("get_candidates_failed", error=str(e))
            return []

    async def mark_consolidated(self, episode_id: str) -> bool:
        """Marca un episodio come consolidato.

        Args:
            episode_id: ID episodio

        Returns:
            True se successo
        """
        client = await self.get_client()

        try:
            await client.set_payload(
                collection_name=self.COLLECTION_NAME,
                payload={"consolidated": True},
                points=[episode_id],
            )

            logger.debug("episode_marked_consolidated", episode_id=episode_id)
            return True

        except Exception as e:
            logger.error("mark_consolidated_failed", episode_id=episode_id, error=str(e))
            return False

    async def search(
        self,
        tenant_id: str,
        user_id: str,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Ricerca testuale negli episodi.

        Args:
            tenant_id: Tenant isolation
            user_id: User isolation
            query: Query di ricerca
            limit: Max risultati

        Returns:
            Lista di episodi matching
        """
        from me4brain.embeddings import get_embedding_service

        embedding_service = get_embedding_service()
        query_embedding = embedding_service.embed_document(query)

        results = await self.search_similar(
            tenant_id=tenant_id,
            user_id=user_id,
            query_embedding=query_embedding,
            limit=limit,
        )

        return [
            {
                "id": r[0].id,
                "content": r[0].content,
                "score": r[1],
                "importance": r[0].importance,
                "created_at": r[0].created_at.isoformat() if r[0].created_at else "",
            }
            for r in results
        ]

    async def close(self) -> None:
        """Chiude le connessioni."""
        if self._client:
            await self._client.close()


# Singleton
_episodic_memory: EpisodicMemory | None = None


def get_episodic_memory() -> EpisodicMemory:
    """Ottiene l'istanza singleton di EpisodicMemory."""
    global _episodic_memory
    if _episodic_memory is None:
        _episodic_memory = EpisodicMemory()
    return _episodic_memory
