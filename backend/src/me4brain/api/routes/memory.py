"""Memory API Routes.

Endpoints per interazione con il sistema di memoria:
- Store: salva nuovi episodi/entità
- Retrieve: recupera per ID
- Search: ricerca semantica
- Query: interrogazione con ciclo cognitivo completo
"""

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from me4brain.api.middleware.auth import (
    AuthenticatedUser,
    get_current_user,  # noqa: F401 - Required for test dependency overrides
    get_current_user_dev,
)
from me4brain.api.middleware.rate_limit import RATE_LIMITS, limiter
from me4brain.core import run_cognitive_cycle
from me4brain.embeddings import get_embedding_service
from me4brain.memory import (
    Entity,
    Episode,
    Relation,
    get_episodic_memory,
    get_semantic_memory,
    get_working_memory,
)
from me4brain.utils.metrics import track_latency

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/memory", tags=["Memory"])


# =============================================================================
# Request/Response Models
# =============================================================================


class StoreEpisodeRequest(BaseModel):
    """Richiesta per salvare un episodio."""

    content: str = Field(..., min_length=1, max_length=10000)
    source: str = Field(default="api")
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StoreEpisodeResponse(BaseModel):
    """Risposta dopo salvataggio episodio - Episode completo."""

    id: str
    tenant_id: str | None = None
    user_id: str | None = None
    content: str
    summary: str | None = None
    source: str = "conversation"
    importance: float = 0.5
    tags: list[str] = Field(default_factory=list)
    event_time: datetime | None = None
    ingestion_time: datetime | None = None
    created_at: datetime


class StoreEntityRequest(BaseModel):
    """Richiesta per salvare un'entità nel Knowledge Graph."""

    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=50)
    properties: dict[str, Any] = Field(default_factory=dict)


class StoreEntityResponse(BaseModel):
    """Risposta dopo salvataggio entità - Entity completo."""

    id: str
    name: str
    type: str
    tenant_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None


class ListEntitiesResponse(BaseModel):
    """Risposta per listing entità con paginazione."""

    entities: list[StoreEntityResponse]
    total: int
    limit: int
    offset: int


class StoreRelationRequest(BaseModel):
    """Richiesta per creare una relazione."""

    source_id: str
    target_id: str
    type: str = Field(..., min_length=1, max_length=50)
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    properties: dict[str, Any] = Field(default_factory=dict)


class StoreRelationResponse(BaseModel):
    """Risposta dopo creazione relazione - Relation completa."""

    id: str
    source_id: str
    target_id: str
    type: str
    tenant_id: str | None = None
    weight: float = 1.0
    properties: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SearchRequest(BaseModel):
    """Richiesta di ricerca semantica."""

    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=100)
    min_score: float = Field(default=0.5, ge=0.0, le=1.0)
    time_decay: bool = Field(default=True)
    sources: list[str] = Field(
        default=["episodic", "semantic"],
        description="Fonti da cercare: episodic, semantic, procedural",
    )


class SearchResult(BaseModel):
    """Singolo risultato di ricerca."""

    id: str
    source: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Risposta ricerca."""

    query: str
    results: list[SearchResult]
    total: int


class QueryRequest(BaseModel):
    """Richiesta di query cognitiva completa."""

    query: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = Field(
        default=None,
        description="Session ID per continuità conversazione",
    )
    max_iterations: int = Field(default=5, ge=1, le=10)
    stream: bool = Field(
        default=False,
        description="Se True, restituisce risposta SSE streaming",
    )


class ReasoningStep(BaseModel):
    """Singolo step di ragionamento."""

    step: int
    action: str  # "query_analysis", "routing", "retrieval", "tool_execution", "synthesis"
    description: str
    duration_ms: float = 0.0


class ToolExecution(BaseModel):
    """Dettagli esecuzione tool."""

    tool_name: str
    success: bool
    latency_ms: float = 0.0
    from_muscle_memory: bool = False


class MemoryHits(BaseModel):
    """Conteggio hit per memory layer."""

    episodic_count: int = 0
    semantic_count: int = 0
    procedural_count: int = 0


class ConflictInfo(BaseModel):
    """Info su conflitto rilevato nel retrieval."""

    conflicting_sources: list[str] = Field(default_factory=list)
    conflict_type: str = ""
    resolution_strategy: str = ""


class QueryResponse(BaseModel):
    """Risposta query cognitiva con reasoning dettagliato completo."""

    response: str
    confidence: float
    sources: list[str]
    session_id: str
    thread_id: str

    # Reasoning details
    reasoning_steps: list[ReasoningStep] = Field(default_factory=list)
    tools_used: list[ToolExecution] = Field(default_factory=list)
    memory_hits: MemoryHits = Field(default_factory=MemoryHits)

    # Routing info
    query_type: str = "simple"
    routing_decision: str = "vector_only"

    # Timing
    total_duration_ms: float = 0.0

    # NEW: Campi CognitiveState precedentemente non esposti
    lightrag_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Risultati da LightRAG hybrid retrieval",
    )
    has_conflict: bool = Field(
        default=False,
        description="True se rilevato conflitto tra fonti",
    )
    conflict_info: ConflictInfo | None = Field(
        default=None,
        description="Dettagli sul conflitto se presente",
    )
    routing_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence del routing decision",
    )
    graph_traversal_path: list[str] = Field(
        default_factory=list,
        description="Path traversato nel knowledge graph",
    )
    iteration_count: int = Field(
        default=0,
        ge=0,
        description="Numero iterazioni del ciclo cognitivo",
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/episodes",
    response_model=StoreEpisodeResponse,
    status_code=status.HTTP_201_CREATED,
)
@track_latency("POST", "/memory/episodes", "default")
async def store_episode(
    request: StoreEpisodeRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> StoreEpisodeResponse:
    """Salva un nuovo episodio nella memoria episodica."""
    episodic = get_episodic_memory()
    embedding_service = get_embedding_service()

    # Genera embedding
    embedding = embedding_service.embed_document(request.content)

    # Crea episodio
    episode = Episode(
        id=str(uuid4()),
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        content=request.content,
        source=request.source,
        tags=request.tags,
        importance=request.metadata.get("importance", 0.5) if request.metadata else 0.5,
    )

    # Salva con embedding
    episode_id = await episodic.add_episode(episode, embedding)

    logger.info(
        "episode_stored",
        episode_id=episode_id,
        tenant_id=user.tenant_id,
        content_length=len(request.content),
    )

    return StoreEpisodeResponse(
        id=episode_id,
        tenant_id=episode.tenant_id,
        user_id=episode.user_id,
        content=episode.content,
        summary=episode.summary,
        source=episode.source,
        importance=episode.importance,
        tags=episode.tags,
        event_time=episode.event_time,
        ingestion_time=episode.ingestion_time,
        created_at=episode.event_time,
    )


@router.get("/episodes/{episode_id}")
async def get_episode(
    episode_id: str,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> dict[str, Any]:
    """Recupera un episodio per ID."""
    episodic = get_episodic_memory()

    episode = await episodic.get_by_id(user.tenant_id, episode_id)

    if episode is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: {episode_id}",
        )

    return {
        "id": episode.id,
        "content": episode.content,
        "source": episode.source,
        "tags": episode.tags,
        "event_time": episode.event_time.isoformat(),
        "importance": episode.importance,
    }


@router.delete("/episodes/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_episode(
    episode_id: str,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> None:
    """Elimina un episodio."""
    episodic = get_episodic_memory()

    deleted = await episodic.delete_episode(user.tenant_id, episode_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: {episode_id}",
        )


class UpdateEpisodeRequest(BaseModel):
    """Richiesta per aggiornare un episodio."""

    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class UpdateEpisodeResponse(BaseModel):
    """Risposta dopo aggiornamento episodio."""

    id: str
    content: str
    source: str
    tags: list[str]
    importance: float
    event_time: str
    updated: bool = True


@router.put("/episodes/{episode_id}", response_model=UpdateEpisodeResponse)
async def update_episode(
    episode_id: str,
    request: UpdateEpisodeRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> UpdateEpisodeResponse:
    """Aggiorna un episodio esistente."""
    episodic = get_episodic_memory()

    updated_episode = await episodic.update_episode(
        tenant_id=user.tenant_id,
        episode_id=episode_id,
        importance=request.importance,
        tags=request.tags,
        metadata=request.metadata,
    )

    if updated_episode is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: {episode_id}",
        )

    return UpdateEpisodeResponse(
        id=updated_episode.id,
        content=updated_episode.content,
        source=updated_episode.source,
        tags=updated_episode.tags,
        importance=updated_episode.importance,
        event_time=updated_episode.event_time.isoformat(),
    )


class RelatedEpisodesResponse(BaseModel):
    """Risposta con episodi correlati."""

    episode_id: str
    episodes: list[dict[str, Any]]
    count: int


@router.get("/episodes/{episode_id}/related", response_model=RelatedEpisodesResponse)
async def get_related_episodes(
    episode_id: str,
    limit: int = 5,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> RelatedEpisodesResponse:
    """Recupera episodi correlati semanticamente."""
    episodic = get_episodic_memory()

    # Verifica che l'episodio esista
    episode = await episodic.get_by_id(user.tenant_id, episode_id)
    if episode is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Episode not found: {episode_id}",
        )

    related = await episodic.get_related_episodes(
        tenant_id=user.tenant_id,
        episode_id=episode_id,
        limit=limit,
    )

    return RelatedEpisodesResponse(
        episode_id=episode_id,
        episodes=[
            {
                "id": ep.id,
                "content": ep.content,
                "source": ep.source,
                "importance": ep.importance,
                "tags": ep.tags,
                "event_time": ep.event_time.isoformat(),
            }
            for ep in related
        ],
        count=len(related),
    )


@router.post(
    "/entities",
    response_model=StoreEntityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def store_entity(
    request: StoreEntityRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> StoreEntityResponse:
    """Salva una nuova entità nel Knowledge Graph."""
    semantic = get_semantic_memory()

    entity = Entity(
        id=str(uuid4()),
        type=request.type,
        name=request.name,
        tenant_id=user.tenant_id,
        properties=request.properties,
    )

    entity_id = await semantic.add_entity(entity)

    logger.info(
        "entity_stored",
        entity_id=entity_id,
        entity_type=request.type,
        tenant_id=user.tenant_id,
    )

    return StoreEntityResponse(
        id=entity_id,
        name=entity.name,
        type=entity.type,
        tenant_id=entity.tenant_id,
        properties=entity.properties,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.get("/entities", response_model=ListEntitiesResponse)
async def list_entities(
    entity_type: str | None = Query(default=None, description="Filtra per tipo entità"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> ListEntitiesResponse:
    """Lista entità del Knowledge Graph con paginazione.

    Se entity_type è specificato, filtra per quel tipo.
    Senza entity_type, ritorna tutte le entità.
    """
    semantic = get_semantic_memory()

    entities, total = await semantic.list_entities_by_type(
        tenant_id=user.tenant_id,
        entity_type=entity_type,
        limit=limit,
        offset=offset,
    )

    return ListEntitiesResponse(
        entities=[
            StoreEntityResponse(
                id=e.id,
                name=e.name,
                type=e.type,
                tenant_id=e.tenant_id,
                properties=e.properties,
                created_at=e.created_at,
                updated_at=e.updated_at,
            )
            for e in entities
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/entities/{entity_id}")
async def get_entity(
    entity_id: str,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> dict[str, Any]:
    """Recupera un'entità per ID."""
    semantic = get_semantic_memory()

    entity = await semantic.get_entity(user.tenant_id, entity_id)

    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity not found: {entity_id}",
        )

    return {
        "id": entity.id,
        "type": entity.type,
        "name": entity.name,
        "properties": entity.properties,
        "created_at": entity.created_at.isoformat(),
    }


@router.post(
    "/relations",
    response_model=StoreRelationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def store_relation(
    request: StoreRelationRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> StoreRelationResponse:
    """Crea una relazione tra entità."""
    semantic = get_semantic_memory()

    relation = Relation(
        source_id=request.source_id,
        target_id=request.target_id,
        type=request.type,
        tenant_id=user.tenant_id,
        weight=request.weight,
        properties=request.properties,
    )

    await semantic.add_relation(relation)

    logger.info(
        "relation_stored",
        source=request.source_id,
        target=request.target_id,
        type=request.type,
    )

    return StoreRelationResponse(
        id=relation.id,
        source_id=relation.source_id,
        target_id=relation.target_id,
        type=relation.type,
        tenant_id=relation.tenant_id,
        weight=relation.weight,
        properties=relation.properties,
        created_at=relation.created_at,
    )


@router.post("/search", response_model=SearchResponse)
@track_latency("POST", "/memory/search", "default")
async def search_memory(
    request: SearchRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> SearchResponse:
    """Ricerca semantica nella memoria."""
    embedding_service = get_embedding_service()
    query_embedding = embedding_service.embed_query(request.query)

    results: list[SearchResult] = []

    # Ricerca episodica
    if "episodic" in request.sources:
        episodic = get_episodic_memory()
        episodes = await episodic.search_similar(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            query_embedding=query_embedding,
            limit=request.limit,
            min_score=request.min_score,
            time_decay=request.time_decay,
        )

        for episode, score in episodes:
            results.append(
                SearchResult(
                    id=episode.id,
                    source="episodic",
                    content=episode.content,
                    score=score,
                    metadata={
                        "event_time": episode.event_time.isoformat(),
                        "source": episode.source,
                        "tags": episode.tags,
                    },
                )
            )

    # Ricerca semantica (PPR)
    if "semantic" in request.sources:
        semantic = get_semantic_memory()
        working = get_working_memory()

        # Usa entità dalla sessione come seed
        # (In assenza, skip PPR)
        graph = working.get_session_graph(
            user.tenant_id,
            user.user_id,
            "default_session",
        )

        seed_entities = list(graph.nodes())[:5]
        if seed_entities:
            ppr_results = await semantic.personalized_pagerank(
                tenant_id=user.tenant_id,
                seed_entities=seed_entities,
                top_k=request.limit,
            )

            for entity_id, score in ppr_results:
                if score >= request.min_score:
                    entity = await semantic.get_entity(user.tenant_id, entity_id)
                    if entity:
                        results.append(
                            SearchResult(
                                id=entity.id,
                                source="semantic",
                                content=f"{entity.name}: {entity.properties}",
                                score=score,
                                metadata={"type": entity.type},
                            )
                        )

    # Ordina per score
    results.sort(key=lambda r: r.score, reverse=True)
    results = results[: request.limit]

    return SearchResponse(
        query=request.query,
        results=results,
        total=len(results),
    )


@router.post("/query", response_model=QueryResponse)
@limiter.limit(RATE_LIMITS["cognitive"])
@track_latency("POST", "/memory/query", "default")
async def cognitive_query(
    request: Request,
    query_request: QueryRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> QueryResponse:
    """Esegue una query con il ciclo cognitivo completo.

    Questo endpoint attiva l'intero pipeline:
    - Embedding
    - Routing (Vector/Graph/Hybrid)
    - Retrieval
    - Conflict Resolution
    - Response Generation

    Response include reasoning steps dettagliati per debugging/observability.
    """
    import time

    start_time = time.time()
    session_id = query_request.session_id or str(uuid4())

    # Esegui ciclo cognitivo
    final_state = await run_cognitive_cycle(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        session_id=session_id,
        user_input=query_request.query,
    )

    total_duration_ms = (time.time() - start_time) * 1000

    # Costruisci reasoning steps dal CognitiveState
    reasoning_steps_raw = final_state.get("reasoning_steps", [])
    reasoning_steps = []
    for i, step_desc in enumerate(reasoning_steps_raw):
        reasoning_steps.append(
            ReasoningStep(
                step=i + 1,
                action="reasoning",
                description=str(step_desc),
            )
        )

    # Aggiungi step standard basati sul routing
    if final_state.get("routing_decision"):
        reasoning_steps.insert(
            0,
            ReasoningStep(
                step=0,
                action="routing",
                description=f"Query classificata come '{final_state.get('query_type', 'simple')}', strategia: {final_state.get('routing_decision', 'vector_only')}",
            ),
        )

    # Tools usati
    tools_used = []
    tool_result = final_state.get("tool_result")
    if tool_result:
        tools_used.append(
            ToolExecution(
                tool_name=tool_result.get("tool_name", "unknown"),
                success=tool_result.get("success", False),
                latency_ms=tool_result.get("latency_ms", 0.0),
                from_muscle_memory=final_state.get("muscle_memory_hit", False),
            )
        )

    # Memory hits
    memory_hits = MemoryHits(
        episodic_count=len(final_state.get("episodic_results", [])),
        semantic_count=len(final_state.get("semantic_results", [])),
        procedural_count=len(final_state.get("procedural_results", [])),
    )

    # NEW: Costruisci ConflictInfo se presente conflitto
    conflict_info = None
    if final_state.get("has_conflict"):
        conflict_info = ConflictInfo(
            conflicting_sources=final_state.get("conflict_sources", []),
            conflict_type=final_state.get("conflict_type", ""),
            resolution_strategy=final_state.get("resolution_strategy", ""),
        )

    return QueryResponse(
        response=final_state.get("final_response", ""),
        confidence=final_state.get("confidence", 0.0),
        sources=final_state.get("sources_used", []),
        session_id=session_id,
        thread_id=final_state.get("thread_id", ""),
        reasoning_steps=reasoning_steps,
        tools_used=tools_used,
        memory_hits=memory_hits,
        query_type=final_state.get("query_type", "simple"),
        routing_decision=final_state.get("routing_decision", "vector_only"),
        total_duration_ms=total_duration_ms,
        # NEW: Campi CognitiveState aggiuntivi
        lightrag_results=final_state.get("lightrag_results", []),
        has_conflict=final_state.get("has_conflict", False),
        conflict_info=conflict_info,
        routing_confidence=final_state.get("routing_confidence", 0.0),
        graph_traversal_path=final_state.get("graph_traversal_path", []),
        iteration_count=final_state.get("iteration_count", 0),
    )


@router.delete("/user", status_code=status.HTTP_204_NO_CONTENT)
async def forget_user(
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> None:
    """GDPR: elimina tutti i dati dell'utente.

    Questa operazione è irreversibile.
    """
    episodic = get_episodic_memory()

    await episodic.forget_user(user.tenant_id, user.user_id)

    logger.info(
        "user_data_deleted",
        user_id=user.user_id,
        tenant_id=user.tenant_id,
    )


# =============================================================================
# Streaming Endpoint
# =============================================================================


class StreamChunkResponse(BaseModel):
    """Singolo chunk dello stream."""

    chunk_type: str  # "content", "reasoning", "tool", "done"
    content: str | None = None
    reasoning_step: dict | None = None
    tool_call: dict | None = None
    metadata: dict | None = None


async def stream_cognitive_response(
    tenant_id: str,
    user_id: str,
    query: str,
    session_id: str,
) -> AsyncGenerator[str, None]:
    """Genera stream di chunks SSE per la risposta cognitiva.

    Usa STREAMING REALE per la sintesi finale, riducendo
    Time to First Byte da 5-15s a <500ms.
    """
    import json

    from me4brain.core.cognitive_pipeline import (
        analyze_query,
        execute_semantic_tool_loop,
        retrieve_memory_context,
        synthesize_response_stream,
    )
    from me4brain.llm.config import get_llm_config
    from me4brain.llm.nanogpt import get_llm_client
    from me4brain.retrieval.tool_executor import get_tool_executor

    thread_id = str(uuid4())
    config = get_llm_config()
    llm_client = get_llm_client()
    executor = get_tool_executor()
    embedding_service = get_embedding_service()

    # Chunk 1: conferma inizio
    yield f"data: {json.dumps({'chunk_type': 'start', 'session_id': session_id, 'thread_id': thread_id})}\n\n"

    try:
        # Fase 1: Analisi query (non-streaming, veloce ~200ms)
        yield f"data: {json.dumps({'chunk_type': 'status', 'content': 'Analizzando query...'})}\n\n"
        analysis = await analyze_query(query, llm_client, config)
        yield f"data: {json.dumps({'chunk_type': 'analysis', 'analysis': analysis})}\n\n"

        # Fase 2: Esecuzione tool (non-streaming, durata variabile)
        yield f"data: {json.dumps({'chunk_type': 'status', 'content': 'Eseguendo tool...'})}\n\n"
        collected_data = await execute_semantic_tool_loop(
            tenant_id=tenant_id,
            user_id=user_id,
            user_query=query,
            executor=executor,
            embedding_service=embedding_service,
            llm_client=llm_client,
            config=config,
            analysis=analysis,  # Riuso analysis per evitare doppia chiamata LLM
        )

        # Chunk tool results
        for data in collected_data:
            if data.get("success"):
                yield f"data: {json.dumps({'chunk_type': 'tool', 'tool_call': {'tool': data.get('tool_name'), 'success': True}})}\n\n"

        # Fase 3: Recupero memoria
        # Estrai valori entità (entities può essere list[dict] o list[str])
        raw_entities = analysis.get("entities", [])
        entity_values = [
            e.get("value") if isinstance(e, dict) else str(e) for e in raw_entities if e
        ]
        memory_context = await retrieve_memory_context(
            tenant_id=tenant_id,
            user_id=user_id,
            entities=entity_values,
            embedding_service=embedding_service,
        )

        # Fase 4: SINTESI STREAMING REALE 🎯
        yield f"data: {json.dumps({'chunk_type': 'status', 'content': 'Generando risposta...'})}\n\n"

        full_response = ""
        async for token in synthesize_response_stream(
            query=query,
            analysis=analysis,
            collected_data=collected_data,
            memory_context=memory_context,
            llm_client=llm_client,
            config=config,
        ):
            full_response += token
            # Streaming reale token-by-token!
            yield f"data: {json.dumps({'chunk_type': 'content', 'content': token})}\n\n"

        # Chunk finale: done
        yield f"data: {json.dumps({'chunk_type': 'done', 'confidence': 0.9})}\n\n"

    except Exception as e:
        logger.error("stream_error", error=str(e))
        yield f"data: {json.dumps({'chunk_type': 'error', 'content': str(e)})}\n\n"


@router.post("/query/stream")
@limiter.limit(RATE_LIMITS["cognitive"])
async def cognitive_query_stream(
    request: Request,
    query_request: QueryRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> StreamingResponse:
    """Esegue una query cognitiva con risposta streaming SSE.

    Restituisce chunks progressivi durante l'elaborazione.
    """
    session_id = query_request.session_id or str(uuid4())

    return StreamingResponse(
        stream_cognitive_response(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            query=query_request.query,
            session_id=session_id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
