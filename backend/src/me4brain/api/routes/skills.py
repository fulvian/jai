"""Skills API Routes - Endpoint REST per gestione skill.

Refactoring per utilizzare il nuovo SkillRegistry e il sistema di Universal Tool Sync.
"""

from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from me4brain.config import get_settings
from me4brain.memory.procedural import get_procedural_memory

# Utilizziamo il nuovo sistema di skills
from me4brain.skills import SkillLoader, SkillRegistry
from me4brain.skills.types import SkillDefinition, SkillSource, SkillStatus

logger = structlog.get_logger(__name__)

logger.info("loading_skills_routes")
router = APIRouter(prefix="/skills", tags=["skills"])


@router.get("/ping")
async def ping_skills():
    return {"ping": "pong"}


# Response models
class SkillResponse(BaseModel):
    """Risposta per singola skill compatibile con il nuovo SkillDefinition."""

    id: str
    name: str
    description: str
    type: str  # Mappato da SkillSource (explicit/crystallized)
    enabled: bool
    usage_count: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    confidence: float = 0.5
    version: str | None = None
    code: str | None = None  # Mappato da instructions

    @classmethod
    def from_skill_definition(cls, skill: SkillDefinition) -> "SkillResponse":
        """Mappa SkillDefinition (nuovo) in SkillResponse (legacy compatibile)."""
        return cls(
            id=skill.id,
            name=skill.name,
            description=skill.description,
            type="explicit"
            if skill.metadata.source == SkillSource.LOCAL
            or skill.metadata.source == SkillSource.BUNDLED
            else "crystallized",
            enabled=skill.status != SkillStatus.DISABLED,
            usage_count=0,  # SkillDefinition non traccia queste metriche direttamente in questa versione
            success_count=0,
            success_rate=0.0,
            confidence=0.8,  # Default per le skill validate
            version=skill.metadata.version,
            code=skill.instructions,
        )


class SkillToggleRequest(BaseModel):
    """Request per attivare/disattivare skill."""

    enabled: bool


class SkillListResponse(BaseModel):
    """Risposta per lista skill."""

    skills: list[SkillResponse]
    total: int


class SkillStatsResponse(BaseModel):
    """Statistiche skill system."""

    total_explicit: int
    total_crystallized: int
    total_usage: int
    avg_success_rate: float
    crystallization_rate: float


# ============================================================================
# Lazy loading del registry con Universal Sync
# ============================================================================

_registry: SkillRegistry | None = None


async def get_registry() -> SkillRegistry:
    """Dependency injection per registry con Lazy Initialization e Universal Sync."""
    global _registry
    if _registry is None:
        logger.info("skill_api_registry_initializing")
        loader = SkillLoader()
        _registry = SkillRegistry(loader)
        await _registry.initialize()

        # Universal Tool Sync: Registra le skill scoperte anche in ProceduralMemory (Qdrant)
        # Questo le rende visibili anche sotto /api/tools e all'Engine in modo persistente.
        settings = get_settings()
        procedural = get_procedural_memory()

        sync_count = 0
        for skill in _registry.skills:
            try:
                await _registry.register_with_procedural_memory(
                    skill, procedural, settings.default_tenant_id
                )
                sync_count += 1
            except Exception as e:
                logger.warning("skill_sync_procedural_failed", skill_id=skill.id, error=str(e))

        logger.info("skill_api_universal_sync_complete", total_synced=sync_count)

    return _registry


@router.post("/install", response_model=SkillResponse)
async def install_skill(file: UploadFile = File(...)) -> SkillResponse:
    """
    Upload e installa una skill esplicita da file SKILL.md.
    """
    registry = await get_registry()

    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Il file deve essere in formato .md")

    try:
        # Nota: La logica di installazione fisica su disco dovrebbe essere gestita
        # dal loader o da una utility specifica. Qui simuliamo l'installazione
        # e il rinfresco del registry.

        # In una versione futura: salvare il file in DEFAULT_WORKSPACE_DIR
        # e chiamare registry.refresh()

        await registry.refresh()

        # Troviamo la skill appena caricata (semplificazione)
        skill = registry.skills[-1] if registry.skills else None

        if not skill:
            raise HTTPException(status_code=500, detail="Errore nell'installazione della skill")

        return SkillResponse.from_skill_definition(skill)

    except Exception as e:
        logger.error("skill_install_error", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=SkillListResponse)
async def list_skills(
    type: Literal["explicit", "crystallized"] | None = None,
    enabled_only: bool = Query(True, alias="enabled_only"),
    registry: SkillRegistry = Depends(get_registry),
) -> SkillListResponse:
    """
    Lista tutte le skill scoperte.
    """

    all_skills = registry.skills

    # Filtro compatibile con il vecchio API
    filtered = []
    for s in all_skills:
        # Filtro abilitate
        if enabled_only and s.status == SkillStatus.DISABLED:
            continue

        # Filtro tipo
        if type:
            s_type = (
                "explicit"
                if s.metadata.source == SkillSource.LOCAL
                or s.metadata.source == SkillSource.BUNDLED
                else "crystallized"
            )
            if s_type != type:
                continue

        filtered.append(SkillResponse.from_skill_definition(s))

    return SkillListResponse(skills=filtered, total=len(filtered))


@router.get("/stats", response_model=SkillStatsResponse)
async def skill_stats() -> SkillStatsResponse:
    """
    Statistiche del sistema skill (mappate dal nuovo registry).
    """
    registry = await get_registry()
    stats = registry.get_stats()

    return SkillStatsResponse(
        total_explicit=stats.get("by_source", {}).get("local", 0)
        + stats.get("by_source", {}).get("bundled", 0),
        total_crystallized=stats.get("by_source", {}).get("clawhub", 0),
        total_usage=0,
        avg_success_rate=0.8,  # Default fittizio per ora
        crystallization_rate=0.0,
    )


# ==============================================================================
# Compatibility Endpoints (HITL Flow / Pending)
# ==============================================================================


@router.get("/pending", response_model=list[Any])
async def list_pending_skills() -> list[Any]:
    """Placeholder per compatibilità."""
    return []


@router.get("/approval-stats")
async def approval_stats() -> dict:
    """Placeholder per compatibilità."""
    return {"pending": 0, "approved": 0, "rejected": 0}


@router.get("/{skill_id:path}", response_model=SkillResponse)
async def get_skill(skill_id: str) -> SkillResponse:
    """
    Dettaglio singola skill.
    """
    registry = await get_registry()

    skill = registry.get_skill(skill_id)
    if not skill:
        # Prova a cercare per nome se ID non trova nulla (legacy compat)
        for s in registry.skills:
            if s.name == skill_id:
                skill = s
                break

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' non trovata")

    return SkillResponse.from_skill_definition(skill)


@router.patch("/{skill_id:path}", response_model=SkillResponse)
async def toggle_skill(skill_id: str, request: SkillToggleRequest) -> SkillResponse:
    """
    Abilita/disabilita una skill.
    """
    registry = await get_registry()

    skill = registry.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill non trovata")

    if request.enabled:
        registry.enable_skill(skill_id)
    else:
        registry.disable_skill(skill_id)

    return SkillResponse.from_skill_definition(skill)


@router.delete("/{skill_id:path}")
async def delete_skill(skill_id: str) -> dict[str, str]:
    """
    Elimina una skill (not implemented in new registry yet, just disable).
    """
    registry = await get_registry()

    skill = registry.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill non trovata")

    registry.disable_skill(skill_id)

    logger.info("skill_deleted_via_disable", skill_id=skill_id)
    return {"message": f"Skill {skill_id} disabilitata"}
