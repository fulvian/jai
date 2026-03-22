"""Memory API Routes.

Endpoints per interazione con Me4Brain Memory System.
"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.services.me4brain_service import get_me4brain_service

router = APIRouter(prefix="/memory", tags=["memory"])


class StoreEpisodeRequest(BaseModel):
    """Request per salvare un episodio."""

    content: str = Field(..., min_length=1, max_length=10000)
    episode_type: str = Field(default="conversation")
    entities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchMemoryRequest(BaseModel):
    """Request per ricerca memoria."""

    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)


class RecallContextRequest(BaseModel):
    """Request per recall contesto utente."""

    topics: list[str] = Field(default_factory=list)


@router.post("/episodes")
async def store_episode(request: StoreEpisodeRequest):
    """Store un episodio nella memoria episodica per auto-learning.

    Usato per salvare fatti importanti, preferenze utente, o riassunti
    di conversazioni.
    """
    service = get_me4brain_service()
    result = await service.store_episode(
        content=request.content,
        episode_type=request.episode_type,
        entities=request.entities,
        metadata=request.metadata,
    )
    return result


@router.post("/search")
async def search_memory(request: SearchMemoryRequest):
    """Cerca nella memoria (episodica + semantica).

    Ritorna risultati rilevanti per la query.
    """
    service = get_me4brain_service()
    results = await service.search_memory(
        query=request.query,
        limit=request.limit,
    )
    return {"query": request.query, "results": results, "count": len(results)}


@router.post("/recall")
async def recall_context(request: RecallContextRequest):
    """Recall contesto utente: preferenze, fatti, topic recenti.

    Usato per personalizzare risposte basandosi su memoria.
    """
    service = get_me4brain_service()
    context = await service.recall_user_context(
        topics=request.topics,
    )
    return context


@router.get("/health")
async def memory_health():
    """Health check per memoria."""
    service = get_me4brain_service()
    # Test connectivity
    try:
        results = await service.search_memory(query="test", limit=1)
        return {"status": "ok", "me4brain_connected": True}
    except Exception as e:
        return {"status": "degraded", "me4brain_connected": False, "error": str(e)}
