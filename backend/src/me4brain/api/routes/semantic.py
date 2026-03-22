"""Semantic Memory API Routes.

Endpoint avanzati per il Knowledge Graph: PPR, traversal, merge, consolidation.
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from me4brain.api.middleware.auth import AuthenticatedUser, get_current_user_dev
from me4brain.memory import get_episodic_memory, get_semantic_memory

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/semantic", tags=["Semantic Memory"])


# =============================================================================
# Models
# =============================================================================


class PageRankRequest(BaseModel):
    """Richiesta Personalized PageRank."""

    seed_entities: list[str] = Field(
        ...,
        min_length=1,
        description="Entity IDs da usare come seeds per PPR",
    )
    top_k: int = Field(default=10, ge=1, le=100)
    damping: float = Field(default=0.85, ge=0.0, le=1.0)


class PageRankResult(BaseModel):
    """Risultato PPR per singola entità."""

    entity_id: str
    name: str
    entity_type: str
    score: float
    properties: dict[str, Any] = Field(default_factory=dict)


class PageRankResponse(BaseModel):
    """Risposta PPR."""

    seeds: list[str]
    results: list[PageRankResult]
    total: int


class TraversalRequest(BaseModel):
    """Richiesta graph traversal."""

    start_entity: str = Field(..., description="Entity ID di partenza")
    relation_types: list[str] | None = Field(
        default=None,
        description="Tipi di relazione da seguire (None = tutti)",
    )
    max_depth: int = Field(default=3, ge=1, le=10)
    max_nodes: int = Field(default=50, ge=1, le=200)


class TraversalNode(BaseModel):
    """Nodo nel traversal path."""

    entity_id: str
    name: str
    entity_type: str
    depth: int
    relation_from: str | None = None


class TraversalResponse(BaseModel):
    """Risposta traversal."""

    start_entity: str
    nodes: list[TraversalNode]
    edges: list[dict[str, str]]
    total_nodes: int


class MergeRequest(BaseModel):
    """Richiesta merge entità duplicate."""

    entity_ids: list[str] = Field(
        ...,
        min_length=2,
        description="IDs delle entità da unire",
    )
    target_name: str = Field(
        ...,
        min_length=1,
        description="Nome per l'entità risultante",
    )
    strategy: str = Field(
        default="keep_all_properties",
        description="Strategia merge: 'keep_all_properties', 'prefer_first', 'prefer_latest'",
    )


class MergeResponse(BaseModel):
    """Risposta merge."""

    merged_entity_id: str
    merged_count: int
    properties: dict[str, Any]


class ConsolidationRequest(BaseModel):
    """Richiesta consolidation episodic → semantic."""

    min_importance: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Soglia minima importanza per consolidare",
    )
    max_age_hours: int = Field(
        default=24,
        ge=1,
        description="Età massima episodi da considerare",
    )
    dry_run: bool = Field(
        default=False,
        description="Se True, simula senza applicare",
    )


class ConsolidationResult(BaseModel):
    """Risultato consolidation."""

    episodes_processed: int
    entities_created: int
    relations_created: int
    dry_run: bool


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/pagerank", response_model=PageRankResponse)
async def personalized_pagerank(
    request: PageRankRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> PageRankResponse:
    """Esegue Personalized PageRank dal knowledge graph.

    Utile per trovare entità rilevanti a partire da un set di seeds.
    """
    semantic = get_semantic_memory()

    try:
        # Esegui PPR usando Neo4j/KuzuDB
        results = await semantic.personalized_pagerank(
            tenant_id=user.tenant_id,
            seed_entities=request.seed_entities,
            top_k=request.top_k,
            damping=request.damping,
        )

        pagerank_results = [
            PageRankResult(
                entity_id=r["id"],
                name=r.get("name", ""),
                entity_type=r.get("type", ""),
                score=r.get("score", 0.0),
                properties=r.get("properties", {}),
            )
            for r in results
        ]

        logger.info(
            "pagerank_executed",
            seeds=request.seed_entities,
            results_count=len(pagerank_results),
        )

        return PageRankResponse(
            seeds=request.seed_entities,
            results=pagerank_results,
            total=len(pagerank_results),
        )

    except Exception as e:
        logger.error("pagerank_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PageRank failed: {e}",
        )


@router.post("/traverse", response_model=TraversalResponse)
async def graph_traversal(
    request: TraversalRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> TraversalResponse:
    """Esegue traversal del knowledge graph da un'entità.

    Restituisce tutti i nodi raggiungibili entro max_depth hop.
    """
    semantic = get_semantic_memory()

    try:
        nodes, edges = await semantic.traverse_graph(
            tenant_id=user.tenant_id,
            start_id=request.start_entity,
            relation_types=request.relation_types,
            max_depth=request.max_depth,
            max_nodes=request.max_nodes,
        )

        traversal_nodes = [
            TraversalNode(
                entity_id=n["id"],
                name=n.get("name", ""),
                entity_type=n.get("type", ""),
                depth=n.get("depth", 0),
                relation_from=n.get("relation_from"),
            )
            for n in nodes
        ]

        logger.info(
            "traversal_executed",
            start=request.start_entity,
            nodes_found=len(traversal_nodes),
        )

        return TraversalResponse(
            start_entity=request.start_entity,
            nodes=traversal_nodes,
            edges=edges,
            total_nodes=len(traversal_nodes),
        )

    except Exception as e:
        logger.error("traversal_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Traversal failed: {e}",
        )


@router.post("/merge", response_model=MergeResponse)
async def merge_entities(
    request: MergeRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> MergeResponse:
    """Unisce entità duplicate in una singola entità.

    Mantiene tutte le relazioni e proprietà secondo la strategia scelta.
    """
    semantic = get_semantic_memory()

    try:
        result = await semantic.merge_entities(
            tenant_id=user.tenant_id,
            entity_ids=request.entity_ids,
            target_name=request.target_name,
            strategy=request.strategy,
        )

        logger.info(
            "entities_merged",
            merged_ids=request.entity_ids,
            result_id=result["merged_id"],
        )

        return MergeResponse(
            merged_entity_id=result["merged_id"],
            merged_count=len(request.entity_ids),
            properties=result.get("properties", {}),
        )

    except Exception as e:
        logger.error("merge_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Merge failed: {e}",
        )


@router.post("/consolidate", response_model=ConsolidationResult)
async def consolidate_to_semantic(
    request: ConsolidationRequest,
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> ConsolidationResult:
    """Consolida episodi importanti nel knowledge graph semantico.

    Processo:
    1. Seleziona episodi con importance >= min_importance
    2. Estrae entità e relazioni
    3. Merge nel knowledge graph permanente
    """
    episodic = get_episodic_memory()
    semantic = get_semantic_memory()

    try:
        # Trova episodi candidati
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(hours=request.max_age_hours)

        candidates = await episodic.get_candidates_for_consolidation(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            min_importance=request.min_importance,
            since=cutoff,
        )

        if request.dry_run:
            return ConsolidationResult(
                episodes_processed=len(candidates),
                entities_created=0,
                relations_created=0,
                dry_run=True,
            )

        # Consolida ogni episodio
        entities_created = 0
        relations_created = 0

        for episode in candidates:
            result = await semantic.consolidate_episode(
                tenant_id=user.tenant_id,
                episode=episode,
            )
            entities_created += result.get("entities", 0)
            relations_created += result.get("relations", 0)

            # Marca episodio come consolidato
            await episodic.mark_consolidated(episode["id"])

        logger.info(
            "consolidation_complete",
            episodes=len(candidates),
            entities=entities_created,
            relations=relations_created,
        )

        return ConsolidationResult(
            episodes_processed=len(candidates),
            entities_created=entities_created,
            relations_created=relations_created,
            dry_run=False,
        )

    except Exception as e:
        logger.error("consolidation_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Consolidation failed: {e}",
        )


@router.get("/search")
async def cross_layer_search(
    query: str = Query(..., min_length=1),
    cross_layer: bool = Query(default=False, description="Ricerca cross-layer"),
    limit: int = Query(default=10, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user_dev),
) -> dict[str, Any]:
    """Ricerca ibrida nel knowledge graph.

    Con cross_layer=True, cerca in tutti i memory layer.
    """
    semantic = get_semantic_memory()
    results: dict[str, Any] = {"query": query, "cross_layer": cross_layer}

    # Ricerca semantica
    semantic_results = await semantic.search(
        tenant_id=user.tenant_id,
        query=query,
        limit=limit,
    )
    results["semantic"] = semantic_results

    if cross_layer:
        # Aggiungi ricerca episodica
        episodic = get_episodic_memory()
        episodic_results = await episodic.search(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            query=query,
            limit=limit,
        )
        results["episodic"] = episodic_results

        # Aggiungi ricerca procedurale
        from me4brain.memory import get_procedural_memory

        procedural = get_procedural_memory()
        proc_results = await procedural.search_tools(query, limit=limit)
        results["procedural"] = proc_results

    return results
