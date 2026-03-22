"""Procedural Memory API Routes.

Endpoints per gestione skills, tool mapping e muscle memory:
- Skills: list, get, register
- Intent mapping: get intent → tool mapping
- Muscle memory: cache patterns
"""

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from me4brain.api.middleware.auth import (
    AuthenticatedUser,
    get_current_user_dev as get_current_user,
)
from me4brain.memory.procedural import ProceduralMemory, Tool

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/procedural", tags=["Procedural Memory"])


# =============================================================================
# Request/Response Models
# =============================================================================


class SkillInfo(BaseModel):
    """Informazioni su uno skill/tool."""

    id: str
    name: str
    description: str
    endpoint: str | None = None
    status: str = "ACTIVE"
    success_rate: float = 0.5
    avg_latency_ms: float = 0.0
    total_calls: int = 0


class SkillsListResponse(BaseModel):
    """Lista skills."""

    skills: list[SkillInfo]
    count: int


class RegisterSkillRequest(BaseModel):
    """Richiesta registrazione nuovo skill."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=10, max_length=2000)
    endpoint: str | None = None
    method: str = "POST"
    api_schema: dict[str, Any] = Field(default_factory=dict)


class IntentToolMapping(BaseModel):
    """Mapping intent → tool."""

    intent: str
    matched_tools: list[str]
    confidence: float


class IntentMapResponse(BaseModel):
    """Lista mapping intent → tools."""

    mappings: list[IntentToolMapping]
    count: int


class MuscleMemoryPattern(BaseModel):
    """Pattern muscle memory (few-shot cache)."""

    intent: str
    tool_name: str
    success_count: int
    last_used: str


class MuscleMemoryResponse(BaseModel):
    """Cache muscle memory."""

    patterns: list[MuscleMemoryPattern]
    count: int


# =============================================================================
# Singleton ProceduralMemory
# =============================================================================

_procedural_memory: ProceduralMemory | None = None


async def get_procedural_memory() -> ProceduralMemory:
    """Lazy init ProceduralMemory."""
    global _procedural_memory
    if _procedural_memory is None:
        _procedural_memory = ProceduralMemory()
        await _procedural_memory.initialize()
    return _procedural_memory


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/skills", response_model=SkillsListResponse)
async def list_skills(
    limit: int = 100,
    offset: int = 0,
    user: AuthenticatedUser = Depends(get_current_user),
    pm: ProceduralMemory = Depends(get_procedural_memory),
) -> SkillsListResponse:
    """Lista tutti gli skills/tools registrati."""
    # Usa scroll invece di search per ottenere tutti i tools
    qdrant = await pm.get_qdrant()

    try:
        from qdrant_client import models

        results = await qdrant.scroll(
            collection_name="me4brain_capabilities",
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="tenant_id",
                        match=models.MatchValue(value=user.tenant_id),
                    ),
                ]
            ),
            limit=limit,
            offset=offset,
            with_payload=True,
        )

        skills = []
        if results and results[0]:
            for point in results[0]:
                payload = point.payload or {}
                skills.append(
                    SkillInfo(
                        id=str(point.id),
                        name=payload.get("name", ""),
                        description=payload.get("description", ""),
                        endpoint=payload.get("endpoint"),
                        status=payload.get("status", "ACTIVE"),
                        success_rate=payload.get("success_rate", 0.5),
                        avg_latency_ms=payload.get("avg_latency_ms", 0.0),
                        total_calls=payload.get("total_calls", 0),
                    )
                )

        return SkillsListResponse(skills=skills, count=len(skills))
    except Exception as e:
        logger.warning("skills_list_fallback", error=str(e))
        # Fallback se collection non esiste
        return SkillsListResponse(skills=[], count=0)


@router.get("/skills/{skill_id}", response_model=SkillInfo)
async def get_skill(
    skill_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    pm: ProceduralMemory = Depends(get_procedural_memory),
) -> SkillInfo:
    """Ottiene dettagli di uno skill specifico."""
    qdrant = await pm.get_qdrant()

    try:
        result = await qdrant.retrieve(
            collection_name="me4brain_capabilities",
            ids=[skill_id],
            with_payload=True,
        )

        if not result:
            raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

        point = result[0]
        payload = point.payload or {}

        return SkillInfo(
            id=skill_id,
            name=payload.get("name", ""),
            description=payload.get("description", ""),
            endpoint=payload.get("endpoint"),
            status=payload.get("status", "ACTIVE"),
            success_rate=payload.get("success_rate", 0.5),
            avg_latency_ms=payload.get("avg_latency_ms", 0.0),
            total_calls=payload.get("total_calls", 0),
        )
    except Exception as e:
        logger.error("skill_get_error", skill_id=skill_id, error=str(e))
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")


@router.post("/skills", response_model=SkillInfo)
async def register_skill(
    request: RegisterSkillRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    pm: ProceduralMemory = Depends(get_procedural_memory),
) -> SkillInfo:
    """Registra un nuovo skill/tool."""
    tool = Tool(
        name=request.name,
        description=request.description,
        tenant_id=user.tenant_id,
        endpoint=request.endpoint,
        method=request.method,
        api_schema=request.api_schema,
    )

    tool_id = await pm.register_tool(tool)

    logger.info(
        "skill_registered",
        tool_id=tool_id,
        name=request.name,
        tenant_id=user.tenant_id,
    )

    return SkillInfo(
        id=tool_id,
        name=request.name,
        description=request.description,
        endpoint=request.endpoint,
        status="ACTIVE",
    )


@router.delete("/skills/{skill_id}")
async def delete_skill(
    skill_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    pm: ProceduralMemory = Depends(get_procedural_memory),
) -> dict[str, Any]:
    """Elimina uno skill (soft delete via status)."""
    # Per ora facciamo soft delete aggiornando status
    # In futuro implementare delete effettivo
    qdrant = await pm.get_qdrant()

    try:
        # Verifica esistenza
        result = await qdrant.retrieve(
            collection_name="me4brain_capabilities",
            ids=[skill_id],
            with_payload=True,
        )

        if not result:
            raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

        # Delete effettivo da Qdrant
        from qdrant_client.models import PointIdsList

        await qdrant.delete(
            collection_name="me4brain_capabilities",
            points_selector=PointIdsList(points=[skill_id]),
        )

        logger.info("skill_deleted", skill_id=skill_id, tenant_id=user.tenant_id)
        return {"deleted": True, "skill_id": skill_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("skill_delete_error", skill_id=skill_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intent-map", response_model=IntentMapResponse)
async def get_intent_map(
    query: str | None = None,
    limit: int = 20,
    user: AuthenticatedUser = Depends(get_current_user),
    pm: ProceduralMemory = Depends(get_procedural_memory),
) -> IntentMapResponse:
    """Ottiene il mapping intent → tools.

    Se query è specificato, trova i tools per quell'intent.
    """
    if query:
        # Cerca tools per intent usando il metodo che gestisce internamente l'embedding
        try:
            results = await pm.search_tools(
                tenant_id=user.tenant_id,
                query=query,
                top_k=limit,
            )

            mappings = [
                IntentToolMapping(
                    intent=query,
                    matched_tools=[t.get("name", t.get("id", "")) for t in results],
                    confidence=sum(t.get("score", 0.5) for t in results) / max(len(results), 1),
                )
            ]
        except Exception as e:
            logger.warning("intent_map_error", error=str(e))
            mappings = []
    else:
        # Ritorna mapping vuoto senza query
        mappings = []

    return IntentMapResponse(mappings=mappings, count=len(mappings))


@router.get("/muscle-memory", response_model=MuscleMemoryResponse)
async def get_muscle_memory(
    limit: int = 50,
    user: AuthenticatedUser = Depends(get_current_user),
    pm: ProceduralMemory = Depends(get_procedural_memory),
) -> MuscleMemoryResponse:
    """Ottiene i pattern muscle memory (few-shot cache)."""
    # Muscle memory è stored in collection me4brain_muscle_memory
    qdrant = await pm.get_qdrant()

    try:
        # Scroll through muscle memory collection
        results = await qdrant.scroll(
            collection_name="me4brain_muscle_memory",
            limit=limit,
            with_payload=True,
            scroll_filter={"must": [{"key": "tenant_id", "match": {"value": user.tenant_id}}]},
        )

        patterns = []
        if results and results[0]:
            for point in results[0]:
                payload = point.payload or {}
                patterns.append(
                    MuscleMemoryPattern(
                        intent=payload.get("intent", ""),
                        tool_name=payload.get("tool_name", ""),
                        success_count=payload.get("success_count", 1),
                        last_used=payload.get("executed_at", ""),
                    )
                )

        return MuscleMemoryResponse(patterns=patterns, count=len(patterns))
    except Exception as e:
        logger.warning("muscle_memory_read_error", error=str(e))
        # Collection potrebbe non esistere ancora
        return MuscleMemoryResponse(patterns=[], count=0)


@router.delete("/muscle-memory")
async def clear_muscle_memory(
    user: AuthenticatedUser = Depends(get_current_user),
    pm: ProceduralMemory = Depends(get_procedural_memory),
) -> dict[str, Any]:
    """Pulisce la cache muscle memory per il tenant."""
    qdrant = await pm.get_qdrant()

    try:
        # Elimina tutti i punti del tenant
        await qdrant.delete(
            collection_name="me4brain_muscle_memory",
            points_selector={
                "filter": {"must": [{"key": "tenant_id", "match": {"value": user.tenant_id}}]}
            },
        )

        logger.info("muscle_memory_cleared", tenant_id=user.tenant_id)
        return {"cleared": True, "tenant_id": user.tenant_id}
    except Exception as e:
        logger.error("muscle_memory_clear_error", error=str(e))
        return {"cleared": False, "error": str(e)}
