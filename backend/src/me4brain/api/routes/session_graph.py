"""Session Graph API Routes.

Endpoint per il Session Knowledge Graph:
- Ingestione sessioni nel grafo
- Cluster tematici e topic browsing
- Ricerca semantica sessioni
- Sessioni correlate
- Prompt Library CRUD
- Migrazione/reindex
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from me4brain.api.middleware.auth import AuthenticatedUser, get_current_user_dev
from me4brain.memory.session_graph import (
    PromptTemplateNode,
    get_session_graph,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/sessions/graph", tags=["Session Graph"])


# =============================================================================
# Request/Response Models
# =============================================================================


class IngestSessionRequest(BaseModel):
    """Richiesta di ingestione sessione nel grafo."""

    session_id: str = Field(..., description="ID univoco della sessione")
    title: str = Field(default="Nuova Chat", description="Titolo della sessione")
    turns: list[dict[str, Any]] = Field(
        ..., description="Lista di turns [{role, content, timestamp?}]"
    )
    created_at: str | None = Field(default=None, description="Timestamp creazione ISO")
    updated_at: str | None = Field(default=None, description="Timestamp aggiornamento ISO")


class IngestSessionResponse(BaseModel):
    """Risposta ingestione."""

    session_id: str
    turn_count: int
    status: str = "ingested"


class TopicResponse(BaseModel):
    """Topic con conteggio sessioni."""

    id: str
    name: str
    session_count: int


class ClusterResponse(BaseModel):
    """Cluster tematico."""

    id: str
    name: str
    description: str
    session_count: int
    topics: list[str]
    session_ids: list[str]


class SessionResultResponse(BaseModel):
    """Risultato ricerca sessione."""

    session_id: str
    title: str
    score: float
    topics: list[str]
    cluster_name: str
    turn_count: int
    updated_at: str


class SearchRequest(BaseModel):
    """Richiesta ricerca semantica."""

    query: str = Field(..., min_length=1, description="Query di ricerca")
    top_k: int = Field(default=10, ge=1, le=50)
    use_reranking: bool = Field(
        default=True,
        description="Attiva LLM reranking (più preciso ma più lento)",
    )


class PromptTemplateRequest(BaseModel):
    """Richiesta creazione/aggiornamento prompt."""

    id: str | None = Field(default=None, description="ID (auto-generato se omesso)")
    label: str = Field(..., min_length=1, description="Nome del prompt")
    content: str = Field(..., min_length=1, description="Contenuto del prompt")
    category: str = Field(default="general", description="Categoria")
    variables: list[str] = Field(default_factory=list, description="Variabili nel prompt")
    topics: list[str] = Field(default_factory=list, description="Topic associati")


class PromptTemplateResponse(BaseModel):
    """Risposta prompt template."""

    id: str
    label: str
    content: str
    category: str
    topics: list[str]
    usage_count: int
    last_used_at: str | None = None
    variables: list[str]


class ReindexRequest(BaseModel):
    """Richiesta reindex di tutte le sessioni esistenti."""

    sessions: list[dict[str, Any]] = Field(
        ..., description="Lista sessioni {id, title, turns[], created_at, updated_at}"
    )


class ReindexResponse(BaseModel):
    """Report di migrazione."""

    total: int
    success: int
    errors: int
    clusters_created: int = 0
    error_details: list[dict[str, str]] = Field(default_factory=list)


class ConnectedNodeResponse(BaseModel):
    """Nodo connesso nel grafo — punto di esplorazione esterna."""

    id: str
    name: str
    node_type: str = Field(description="Tipo nodo: 'topic' | 'session' | 'cluster'")
    connection_score: float
    relation_type: str
    shared_sessions: int
    description: str


# =============================================================================
# Session Graph Endpoints
# =============================================================================


@router.post("/ingest", response_model=IngestSessionResponse)
async def ingest_session(
    request: IngestSessionRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> IngestSessionResponse:
    """Indicizza una sessione nel grafo.

    Crea/aggiorna nodi Session + Turn con embeddings,
    estrae topic automaticamente e calcola similarità.
    """
    graph = get_session_graph()

    try:
        result = await graph.ingest_session(
            session_id=request.session_id,
            tenant_id=user.tenant_id,
            title=request.title,
            turns=request.turns,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )

        return IngestSessionResponse(
            session_id=result.id,
            turn_count=result.turn_count,
            status="ingested",
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Neo4j non disponibile: {e}",
        )
    except Exception as e:
        logger.error("ingest_session_failed", error=str(e), session_id=request.session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestione fallita: {e}",
        )


@router.get("/clusters", response_model=list[ClusterResponse])
async def get_clusters(
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> list[ClusterResponse]:
    """Recupera i cluster tematici del tenant.

    Restituisce le sessioni raggruppate per affinità semantica.
    """
    graph = get_session_graph()

    try:
        clusters = await graph.get_session_clusters(user.tenant_id)

        return [
            ClusterResponse(
                id=c.id,
                name=c.name,
                description=c.description,
                session_count=c.session_count,
                topics=c.topics,
                session_ids=c.session_ids,
            )
            for c in clusters
        ]

    except Exception as e:
        logger.error("get_clusters_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recupero cluster fallito: {e}",
        )


@router.get("/related/{session_id}", response_model=list[SessionResultResponse])
async def get_related_sessions(
    session_id: str,
    limit: int = Query(default=5, ge=1, le=20),
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> list[SessionResultResponse]:
    """Recupera sessioni correlate a quella specificata.

    Usa graph traversal + embedding similarity.
    """
    graph = get_session_graph()

    try:
        results = await graph.get_related_sessions(
            session_id=session_id,
            tenant_id=user.tenant_id,
            limit=limit,
        )

        return [
            SessionResultResponse(
                session_id=r.session_id,
                title=r.title,
                score=r.score,
                topics=r.topics,
                cluster_name=r.cluster_name,
                turn_count=r.turn_count,
                updated_at=r.updated_at,
            )
            for r in results
        ]

    except Exception as e:
        logger.error("get_related_failed", error=str(e), session_id=session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recupero sessioni correlate fallito: {e}",
        )


@router.get("/connected-nodes/{session_id}", response_model=list[ConnectedNodeResponse])
async def get_connected_nodes(
    session_id: str,
    top_k: int = Query(default=3, ge=1, le=10),
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> list[ConnectedNodeResponse]:
    """Recupera i nodi più connessi a una sessione nel grafo.

    Restituisce topic hub, sessioni 2-hop e cluster come punti
    di partenza per esplorare il Knowledge Graph.
    """
    graph = get_session_graph()

    try:
        nodes = await graph.get_connected_nodes(
            session_id=session_id,
            tenant_id=user.tenant_id,
            top_k=top_k,
        )

        return [
            ConnectedNodeResponse(
                id=n.id,
                name=n.name,
                node_type=n.node_type,
                connection_score=n.connection_score,
                relation_type=n.relation_type,
                shared_sessions=n.shared_sessions,
                description=n.description,
            )
            for n in nodes
        ]

    except Exception as e:
        logger.error("get_connected_nodes_failed", error=str(e), session_id=session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recupero nodi connessi fallito: {e}",
        )


@router.post("/search", response_model=list[SessionResultResponse])
async def search_sessions(
    request: SearchRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> list[SessionResultResponse]:
    """Ricerca semantica sessioni con pipeline 5-stage.

    1. BGE-M3 Embedding
    2. Neo4j Vector Search
    3. Graph Boost
    4. LLM Reranking (opzionale)
    5. Risultati ordinati per rilevanza
    """
    graph = get_session_graph()

    try:
        results = await graph.search_sessions_semantic(
            query=request.query,
            tenant_id=user.tenant_id,
            top_k=request.top_k,
            use_reranking=request.use_reranking,
        )

        return [
            SessionResultResponse(
                session_id=r.session_id,
                title=r.title,
                score=r.score,
                topics=r.topics,
                cluster_name=r.cluster_name,
                turn_count=r.turn_count,
                updated_at=r.updated_at,
            )
            for r in results
        ]

    except Exception as e:
        logger.error("search_sessions_failed", error=str(e), query=request.query[:50])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ricerca sessioni fallita: {e}",
        )


@router.get("/topics", response_model=list[TopicResponse])
async def get_topics(
    limit: int = Query(default=50, ge=1, le=200),
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> list[TopicResponse]:
    """Lista topic con conteggio sessioni."""
    graph = get_session_graph()

    try:
        topics = await graph.get_topics(
            tenant_id=user.tenant_id,
            limit=limit,
        )

        return [
            TopicResponse(
                id=t["id"],
                name=t["name"],
                session_count=t["session_count"],
            )
            for t in topics
        ]

    except Exception as e:
        logger.error("get_topics_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recupero topic fallito: {e}",
        )


@router.post("/reindex", response_model=ReindexResponse)
async def reindex_sessions(
    request: ReindexRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> ReindexResponse:
    """Reindicizza tutte le sessioni esistenti nel grafo.

    Per migrazione da Redis-only al sistema graph-based.
    Processo potenzialmente lungo per molte sessioni.
    """
    graph = get_session_graph()

    try:
        report = await graph.reindex_all_sessions(
            tenant_id=user.tenant_id,
            sessions=request.sessions,
        )

        return ReindexResponse(
            total=report["total"],
            success=report["success"],
            errors=report["errors"],
            clusters_created=report.get("clusters_created", 0),
            error_details=report.get("error_details", []),
        )

    except Exception as e:
        logger.error("reindex_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Reindex fallito: {e}",
        )


@router.post("/detect-communities", response_model=list[ClusterResponse])
async def detect_communities(
    min_cluster_size: int = Query(default=2, ge=2, le=10),
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> list[ClusterResponse]:
    """Esegue community detection (Louvain) per creare cluster tematici.

    Ricalcola i cluster basandosi sulle relazioni correnti nel grafo.
    """
    graph = get_session_graph()

    try:
        clusters = await graph.detect_communities(
            tenant_id=user.tenant_id,
            min_cluster_size=min_cluster_size,
        )

        return [
            ClusterResponse(
                id=c.id,
                name=c.name,
                description=c.description,
                session_count=c.session_count,
                topics=c.topics,
                session_ids=c.session_ids,
            )
            for c in clusters
        ]

    except Exception as e:
        logger.error("detect_communities_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Community detection fallita: {e}",
        )


# =============================================================================
# Prompt Library Endpoints
# =============================================================================

prompt_router = APIRouter(prefix="/prompts/library", tags=["Prompt Library"])


@prompt_router.get("", response_model=list[PromptTemplateResponse])
async def get_prompt_library(
    category: str | None = Query(default=None, description="Filtro per categoria"),
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> list[PromptTemplateResponse]:
    """Recupera la libreria prompt navigabile."""
    graph = get_session_graph()

    try:
        prompts = await graph.get_prompt_library(
            tenant_id=user.tenant_id,
            category=category,
        )

        return [
            PromptTemplateResponse(
                id=p["id"],
                label=p["label"],
                content=p["content"],
                category=p["category"],
                topics=p["topics"],
                usage_count=p["usage_count"],
                last_used_at=p.get("last_used_at"),
                variables=p.get("variables", []),
            )
            for p in prompts
        ]

    except Exception as e:
        logger.error("get_prompt_library_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Recupero prompt library fallito: {e}",
        )


@prompt_router.post("", response_model=dict[str, str])
async def save_prompt_template(
    request: PromptTemplateRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> dict[str, str]:
    """Crea o aggiorna un prompt template nel grafo."""
    graph = get_session_graph()

    try:
        prompt = PromptTemplateNode(
            id=request.id or "",
            label=request.label,
            content=request.content,
            category=request.category,
            tenant_id=user.tenant_id,
            variables=request.variables,
            topics=request.topics,
        )

        prompt_id = await graph.save_prompt_template(prompt)

        return {"id": prompt_id, "status": "saved"}

    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error("save_prompt_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Salvataggio prompt fallito: {e}",
        )


@prompt_router.post("/search", response_model=list[dict[str, Any]])
async def search_prompts(
    request: SearchRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> list[dict[str, Any]]:
    """Ricerca semantica prompt."""
    graph = get_session_graph()

    try:
        return await graph.search_prompts_semantic(
            query=request.query,
            tenant_id=user.tenant_id,
            top_k=request.top_k,
        )

    except Exception as e:
        logger.error("search_prompts_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ricerca prompt fallita: {e}",
        )


@prompt_router.get("/suggest/{session_id}", response_model=list[dict[str, Any]])
async def suggest_prompts(
    session_id: str,
    top_k: int = Query(default=3, ge=1, le=10),
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> list[dict[str, Any]]:
    """Suggerisce prompt rilevanti per la sessione corrente."""
    graph = get_session_graph()

    try:
        return await graph.suggest_prompts_for_session(
            session_id=session_id,
            tenant_id=user.tenant_id,
            top_k=top_k,
        )

    except Exception as e:
        logger.error("suggest_prompts_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Suggerimenti prompt falliti: {e}",
        )
