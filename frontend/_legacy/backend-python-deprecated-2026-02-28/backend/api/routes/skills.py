"""Skills API Routes - Proxy per Me4BrAIn Skills API + ClawHub."""

from typing import Optional

import httpx
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from backend.config import settings

router = APIRouter(prefix="/skills", tags=["skills"])


# ============================================================================
# Response Models
# ============================================================================


class SkillResponse(BaseModel):
    """Risposta per singola skill."""

    id: str
    name: str
    description: str
    type: str = "explicit"  # "explicit" or "crystallized"
    enabled: bool = True
    usage_count: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    confidence: float = 0.0
    version: Optional[str] = None
    # Fields from Me4BrAIn
    endpoint: Optional[str] = None
    status: str = "ACTIVE"

    @classmethod
    def from_me4brain(cls, data: dict) -> "SkillResponse":
        """Map Me4BrAIn SkillInfo to SkillResponse."""
        total_calls = data.get("total_calls", 0)
        success_rate = data.get("success_rate", 0.0)
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            type="explicit",  # Me4BrAIn tools are explicit
            enabled=data.get("status", "ACTIVE") == "ACTIVE",
            usage_count=total_calls,
            success_count=int(total_calls * success_rate),
            success_rate=success_rate,
            confidence=success_rate,  # Use success_rate as confidence
            endpoint=data.get("endpoint"),
            status=data.get("status", "ACTIVE"),
        )


class SkillListResponse(BaseModel):
    """Risposta per lista skill."""

    skills: list[SkillResponse]
    total: int


class SkillStatsResponse(BaseModel):
    """Statistiche skill system."""

    total_explicit: int = 0
    total_crystallized: int = 0
    total_usage: int = 0
    avg_success_rate: float = 0.0
    crystallization_rate: float = 0.0


class SkillToggleRequest(BaseModel):
    """Request per attivare/disattivare skill."""

    enabled: bool


class ClawHubSkill(BaseModel):
    """Skill dal registry ClawHub."""

    slug: str
    name: str
    description: str
    author: Optional[str] = None
    stars: int = 0
    tags: list[str] = []


class ClawHubSearchResponse(BaseModel):
    """Risposta ricerca ClawHub."""

    results: list[ClawHubSkill]
    total: int
    query: str


# ============================================================================
# Me4BrAIn Proxy Routes
# ============================================================================


def _me4brain_url(path: str) -> str:
    """Build Me4BrAIn API URL for procedural skills."""
    return f"{settings.me4brain_url}/v1/procedural{path}"


@router.get("/", response_model=SkillListResponse)
async def list_skills(
    type: Optional[str] = Query(
        None, description="Filter by type: explicit|crystallized"
    ),
    enabled_only: bool = Query(True, description="Only show enabled skills"),
) -> SkillListResponse:
    """
    Lista tutte le skill installate.

    Proxy to Me4BrAIn GET /v1/procedural/skills
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(_me4brain_url("/skills"))
            response.raise_for_status()
            data = response.json()

            skills = [SkillResponse.from_me4brain(s) for s in data.get("skills", [])]

            # Apply filters
            if type:
                skills = [s for s in skills if s.type == type]
            if enabled_only:
                skills = [s for s in skills if s.enabled]

            return SkillListResponse(skills=skills, total=len(skills))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 500:
                # Me4BrAIn internal error - return empty list
                return SkillListResponse(skills=[], total=0)
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")


@router.get("/stats", response_model=SkillStatsResponse)
async def skill_stats() -> SkillStatsResponse:
    """
    Statistiche aggregate del sistema skill.

    Calcola stats da lista skills.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(_me4brain_url("/skills"))
            response.raise_for_status()
            data = response.json()

            skills_data = data.get("skills", [])
            total_usage = sum(s.get("total_calls", 0) for s in skills_data)
            success_rates = [
                s.get("success_rate", 0)
                for s in skills_data
                if s.get("total_calls", 0) > 0
            ]
            avg_success = (
                sum(success_rates) / len(success_rates) if success_rates else 0.0
            )

            return SkillStatsResponse(
                total_explicit=len(skills_data),
                total_crystallized=0,  # Me4BrAIn doesn't have crystallized yet
                total_usage=total_usage,
                avg_success_rate=avg_success,
                crystallization_rate=0.0,
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 500:
                return SkillStatsResponse()
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(skill_id: str) -> SkillResponse:
    """
    Dettaglio singola skill.

    Proxy to Me4BrAIn GET /v1/procedural/skills/{id}
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(_me4brain_url(f"/skills/{skill_id}"))
            response.raise_for_status()
            return SkillResponse.from_me4brain(response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Skill not found")
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")


@router.patch("/{skill_id}", response_model=SkillResponse)
async def toggle_skill(skill_id: str, request: SkillToggleRequest) -> SkillResponse:
    """
    Abilita/disabilita una skill.

    Nota: Me4BrAIn non supporta toggle diretto, soft delete via status.
    """
    # Me4BrAIn non ha PATCH per skills - per ora ritorniamo errore
    raise HTTPException(
        status_code=501, detail="Toggle skill not implemented in Me4BrAIn yet"
    )


@router.delete("/{skill_id}")
async def delete_skill(skill_id: str) -> dict[str, str]:
    """
    Elimina una skill.

    Proxy to Me4BrAIn DELETE /v1/procedural/skills/{id}
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.delete(_me4brain_url(f"/skills/{skill_id}"))
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Skill not found")
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")


@router.post("/install", response_model=SkillResponse)
async def install_skill(file: UploadFile = File(...)) -> SkillResponse:
    """
    Upload e installa una skill da file SKILL.md.

    Nota: Me4BrAIn procedural non supporta upload SKILL.md,
    usa POST /v1/procedural/skills con name/description.
    """
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="File must be .md format")

    content = await file.read()
    content_str = content.decode("utf-8")

    # Parse SKILL.md frontmatter
    # Basic YAML frontmatter parsing
    name = file.filename.replace(".md", "").replace("SKILL", "custom_skill")
    description = content_str[:500] if content_str else "Uploaded skill"

    # Extract name/description from frontmatter if present
    if content_str.startswith("---"):
        lines = content_str.split("\n")
        for line in lines[1:]:
            if line.strip() == "---":
                break
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip().strip("\"'")
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip().strip("\"'")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                _me4brain_url("/skills"),
                json={"name": name, "description": description},
            )
            response.raise_for_status()
            return SkillResponse.from_me4brain(response.json())
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")


# ============================================================================
# ClawHub.ai Integration
# ============================================================================

CLAWHUB_API_URL = "https://clawhub.ai/api"


@router.get("/search/clawhub", response_model=ClawHubSearchResponse)
async def search_clawhub(
    q: str = Query(..., description="Search query"),
    limit: int = Query(20, ge=1, le=50),
) -> ClawHubSearchResponse:
    """
    Cerca skill su ClawHub.ai registry.

    Note: ClawHub.ai potrebbe non avere un'API pubblica ufficiale.
    Questa è una struttura predisposta per quando sarà disponibile.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # TODO: Verificare endpoint API ClawHub reale
            # Per ora ritorna risultati mock/placeholder
            response = await client.get(
                f"{CLAWHUB_API_URL}/skills/search",
                params={"q": q, "limit": limit},
            )

            if response.status_code == 200:
                data = response.json()
                return ClawHubSearchResponse(
                    results=[ClawHubSkill(**s) for s in data.get("skills", [])],
                    total=data.get("total", 0),
                    query=q,
                )
            else:
                # Fallback: ClawHub API non disponibile
                return ClawHubSearchResponse(
                    results=[],
                    total=0,
                    query=q,
                )
        except httpx.HTTPError:
            # ClawHub non raggiungibile, ritorna vuoto
            return ClawHubSearchResponse(
                results=[],
                total=0,
                query=q,
            )


@router.post("/pull/{slug}")
async def pull_clawhub_skill(slug: str) -> dict[str, str]:
    """
    Scarica e installa una skill da ClawHub.ai.

    Workflow:
    1. Scarica SKILL.md dal registry ClawHub
    2. Parse e registra in Me4BrAIn
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            # 1. Scarica SKILL.md da ClawHub
            # TODO: Verificare URL reale per download skill
            skill_url = f"https://clawhub.ai/skills/{slug}/SKILL.md"

            download_response = await client.get(skill_url)
            if download_response.status_code != 200:
                raise HTTPException(
                    status_code=404,
                    detail=f"Skill '{slug}' not found on ClawHub",
                )

            skill_content = download_response.text

            # 2. Parse SKILL.md e registra
            name = slug
            description = skill_content[:500]

            if skill_content.startswith("---"):
                lines = skill_content.split("\n")
                for line in lines[1:]:
                    if line.strip() == "---":
                        break
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip().strip("\"'")
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip().strip("\"'")

            install_response = await client.post(
                _me4brain_url("/skills"),
                json={"name": name, "description": description},
            )
            install_response.raise_for_status()

            return {
                "message": f"Skill '{slug}' installed successfully",
                "skill_id": install_response.json().get("id"),
            }

        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to install skill: {e}",
            )


# ============================================================================
# ClawHub Skills Integration (New API)
# ============================================================================


def _me4brain_clawhub_url(path: str) -> str:
    """Build Me4BrAIn API URL for ClawHub skills."""
    return f"{settings.me4brain_url}/v1/clawhub-skills{path}"


class ClawHubSkillDetail(BaseModel):
    """Dettaglio skill ClawHub."""

    id: str
    name: str
    description: str
    version: Optional[str] = None
    author: Optional[str] = None
    tags: list[str] = []
    source: str
    status: str
    requirements_met: bool = True
    instructions_preview: Optional[str] = None


class ClawHubListResponse(BaseModel):
    """Risposta lista skills ClawHub."""

    skills: list[ClawHubSkillDetail]
    total: int
    bundled_count: int
    local_count: int


class ClawHubStatsResponse(BaseModel):
    """Statistiche skills ClawHub."""

    total_skills: int
    bundled_skills: int
    local_skills: int
    ready_skills: int
    categories: dict[str, int]


class SemanticSearchResult(BaseModel):
    """Risultato ricerca semantica."""

    name: str
    description: str
    type: str
    domain: str
    score: float
    skill_id: Optional[str] = None


class SemanticSearchResponse(BaseModel):
    """Risposta ricerca semantica."""

    results: list[SemanticSearchResult]
    query: str
    total: int


@router.get("/clawhub", response_model=ClawHubListResponse)
async def list_clawhub_skills(
    source: Optional[str] = Query(None, description="Filter by source: bundled|local"),
    ready_only: bool = Query(True, description="Only show ready skills"),
) -> ClawHubListResponse:
    """
    Lista tutte le skills ClawHub installate in Me4BrAIn.

    Include skills bundled e quelle scaricate da ClawHub CLI.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            params = {}
            if source:
                params["source"] = source
            params["ready_only"] = str(ready_only).lower()

            response = await client.get(
                _me4brain_clawhub_url("/"),
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            return ClawHubListResponse(
                skills=[ClawHubSkillDetail(**s) for s in data.get("skills", [])],
                total=data.get("total", 0),
                bundled_count=data.get("bundled_count", 0),
                local_count=data.get("local_count", 0),
            )
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")


@router.get("/clawhub/stats", response_model=ClawHubStatsResponse)
async def clawhub_stats() -> ClawHubStatsResponse:
    """
    Statistiche del sistema skills ClawHub.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(_me4brain_clawhub_url("/stats"))
            response.raise_for_status()
            data = response.json()

            return ClawHubStatsResponse(
                total_skills=data.get("total_skills", 0),
                bundled_skills=data.get("bundled_skills", 0),
                local_skills=data.get("local_skills", 0),
                ready_skills=data.get("ready_skills", 0),
                categories=data.get("categories", {}),
            )
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")


@router.get("/clawhub/search", response_model=SemanticSearchResponse)
async def search_skills_semantic(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    type_filter: Optional[str] = Query(None, description="Filter: tool|skill"),
) -> SemanticSearchResponse:
    """
    Ricerca semantica in tools e skills tramite Qdrant (BGE-M3).
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            params = {"q": q, "limit": limit}
            if type_filter:
                params["type_filter"] = type_filter

            response = await client.get(
                _me4brain_clawhub_url("/search/semantic"),
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            return SemanticSearchResponse(
                results=[SemanticSearchResult(**r) for r in data.get("results", [])],
                query=data.get("query", q),
                total=data.get("total", 0),
            )
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")


@router.post("/clawhub/reload")
async def reload_clawhub_skills() -> dict[str, str]:
    """
    Ricarica tutte le skills ClawHub (scopre nuove skills installate).
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(_me4brain_clawhub_url("/reload"))
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")


@router.get("/clawhub/{skill_id:path}", response_model=ClawHubSkillDetail)
async def get_clawhub_skill(skill_id: str) -> ClawHubSkillDetail:
    """
    Dettaglio singola skill ClawHub.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(_me4brain_clawhub_url(f"/{skill_id}"))
            response.raise_for_status()
            return ClawHubSkillDetail(**response.json())
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Skill not found")
            raise HTTPException(status_code=502, detail=f"Me4BrAIn error: {e}")
