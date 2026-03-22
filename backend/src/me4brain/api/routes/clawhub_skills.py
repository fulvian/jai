"""ClawHub Skills API Routes - Endpoint REST per skills ClawHub.

Questo modulo espone le skills ClawHub installate tramite REST API
per integrazione con PersAn frontend.
"""

from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/clawhub-skills", tags=["clawhub-skills"])


# ============================================================================
# Response Models
# ============================================================================


class ClawHubSkillResponse(BaseModel):
    """Risposta per singola skill ClawHub."""

    id: str
    name: str
    description: str
    version: Optional[str] = None
    author: Optional[str] = None
    tags: list[str] = []
    source: str  # "bundled" | "local" | "clawhub"
    status: str  # "discovered" | "loading" | "ready" | "error" | "disabled"
    requirements_met: bool = True
    instructions_preview: Optional[str] = None


class ClawHubSkillListResponse(BaseModel):
    """Risposta per lista skills ClawHub."""

    skills: list[ClawHubSkillResponse]
    total: int
    bundled_count: int
    local_count: int


class ClawHubStatsResponse(BaseModel):
    """Statistiche skills ClawHub."""

    total_skills: int
    bundled_skills: int
    local_skills: int  # ClawHub installed
    ready_skills: int
    categories: dict[str, int]  # domain -> count


class SearchResultItem(BaseModel):
    """Risultato ricerca Qdrant."""

    name: str
    description: str
    type: str  # "tool" | "skill"
    domain: str
    score: float
    skill_id: Optional[str] = None


class SearchResponse(BaseModel):
    """Risposta ricerca semantica."""

    results: list[SearchResultItem]
    query: str
    total: int


# ============================================================================
# Lazy loading del registry
# ============================================================================


_skill_registry = None
_skill_loader = None


async def _get_registry():
    """Get or create SkillRegistry instance."""
    global _skill_registry, _skill_loader

    if _skill_registry is None:
        from me4brain.skills import SkillLoader, SkillRegistry

        _skill_loader = SkillLoader()
        _skill_registry = SkillRegistry(_skill_loader)
        await _skill_registry.initialize()

    return _skill_registry


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("", response_model=ClawHubSkillListResponse)
async def list_clawhub_skills(
    source: Optional[str] = Query(None, description="Filter by source: bundled|local"),
    ready_only: bool = Query(True, description="Only show ready skills"),
) -> ClawHubSkillListResponse:
    """
    Lista tutte le skills ClawHub installate.

    Include skills bundled e quelle scaricate da ClawHub CLI.
    """
    try:
        registry = await _get_registry()

        skills = []
        for skill in registry.skills:
            # Filter by source
            if source and skill.metadata.source.value != source:
                continue

            # Filter by readiness
            if ready_only and not skill.all_requirements_met():
                continue

            skills.append(
                ClawHubSkillResponse(
                    id=skill.id,
                    name=skill.name,
                    description=skill.description,
                    version=skill.metadata.version,
                    author=skill.metadata.author,
                    tags=skill.metadata.tags,
                    source=skill.metadata.source.value,
                    status=skill.metadata.status.value,
                    requirements_met=skill.all_requirements_met(),
                    instructions_preview=(skill.instructions[:200] if skill.instructions else None),
                )
            )

        bundled = sum(1 for s in skills if s.source == "bundled")
        local = sum(1 for s in skills if s.source == "local")

        return ClawHubSkillListResponse(
            skills=skills,
            total=len(skills),
            bundled_count=bundled,
            local_count=local,
        )

    except Exception as e:
        logger.error("clawhub_skills_list_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=ClawHubStatsResponse)
async def clawhub_stats() -> ClawHubStatsResponse:
    """
    Statistiche del sistema skills ClawHub.
    """
    try:
        registry = await _get_registry()

        # Count by source
        bundled = sum(1 for s in registry.skills if s.metadata.source.value == "bundled")
        local = sum(1 for s in registry.skills if s.metadata.source.value == "local")
        ready = sum(1 for s in registry.skills if s.all_requirements_met())

        # Count by domain (tags)
        categories: dict[str, int] = {}
        for skill in registry.skills:
            for tag in skill.metadata.tags:
                categories[tag] = categories.get(tag, 0) + 1

        return ClawHubStatsResponse(
            total_skills=len(registry.skills),
            bundled_skills=bundled,
            local_skills=local,
            ready_skills=ready,
            categories=categories,
        )

    except Exception as e:
        logger.error("clawhub_stats_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{skill_id:path}", response_model=ClawHubSkillResponse)
async def get_clawhub_skill(skill_id: str) -> ClawHubSkillResponse:
    """
    Dettaglio singola skill ClawHub.

    Args:
        skill_id: ID della skill (es: @me4brain/Screenshot, local/weather/weather)
    """
    try:
        registry = await _get_registry()

        skill = registry.get_skill(skill_id)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

        return ClawHubSkillResponse(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            version=skill.version,
            author=skill.metadata.author,
            tags=skill.metadata.tags,
            source=skill.metadata.source.value,
            status=skill.metadata.status.value,
            requirements_met=skill.all_requirements_met(),
            instructions_preview=(skill.instructions[:500] if skill.instructions else None),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("clawhub_skill_get_error", skill_id=skill_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_skills() -> dict[str, str]:
    """
    Ricarica tutte le skills (scopre nuove skills installate).
    """
    global _skill_registry, _skill_loader

    try:
        # Reset registry to force reload
        _skill_registry = None
        _skill_loader = None

        registry = await _get_registry()
        await registry.load_all_ready()

        return {
            "message": f"Reloaded {len(registry.skills)} skills",
            "bundled": sum(1 for s in registry.skills if s.metadata.source.value == "bundled"),
            "local": sum(1 for s in registry.skills if s.metadata.source.value == "local"),
        }

    except Exception as e:
        logger.error("clawhub_reload_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/semantic", response_model=SearchResponse)
async def search_skills_semantic(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    type_filter: Optional[str] = Query(None, description="Filter by type: tool|skill"),
) -> SearchResponse:
    """
    Ricerca semantica in tools e skills tramite Qdrant.

    Usa BGE-M3 embeddings per trovare tools/skills rilevanti.
    """
    try:
        from qdrant_client import QdrantClient

        from me4brain.embeddings import get_embedding_service

        # Get embedding
        emb = get_embedding_service()
        vector = emb.embed_query(q)

        # Query Qdrant
        client = QdrantClient(url="http://localhost:6334", timeout=30)
        results = client.query_points(
            collection_name="tools_and_skills",
            query=vector,
            limit=limit * 2 if type_filter else limit,  # Over-fetch if filtering
        )

        items = []
        for point in results.points:
            payload = point.payload
            item_type = payload.get("type", "unknown")

            # Apply type filter
            if type_filter and item_type != type_filter:
                continue

            items.append(
                SearchResultItem(
                    name=payload.get("name", payload.get("tool_name", "N/A")),
                    description=payload.get("description", ""),
                    type=item_type,
                    domain=payload.get("domain", "utility"),
                    score=point.score,
                    skill_id=payload.get("skill_id") if item_type == "skill" else None,
                )
            )

            if len(items) >= limit:
                break

        return SearchResponse(
            results=items,
            query=q,
            total=len(items),
        )

    except Exception as e:
        logger.error("semantic_search_error", query=q, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
