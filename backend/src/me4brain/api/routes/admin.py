"""Admin API Routes.

Endpoints per amministrazione e manutenzione:
- Sleep Mode trigger
- Tool management (OpenAPI ingestion)
- Health e metrics
"""

from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from me4brain.api.middleware.auth import AuthenticatedUser, require_role
from me4brain.core.sleep_mode import get_sleep_mode
from me4brain.retrieval import create_openapi_ingester

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ConsolidationRequest(BaseModel):
    """Richiesta di consolidazione manuale."""

    tenant_id: str | None = Field(
        default=None,
        description="Tenant specifico (None = tenant corrente)",
    )
    dry_run: bool = Field(
        default=False,
        description="Se True, simula senza modifiche",
    )


class ConsolidationResponse(BaseModel):
    """Risposta consolidazione."""

    status: str
    job_id: str | None = None
    message: str


class SchedulerRequest(BaseModel):
    """Richiesta per scheduler."""

    action: str = Field(..., pattern="^(start|stop|status)$")
    interval_hours: int = Field(default=6, ge=1, le=24)
    tenant_ids: list[str] | None = None


class OpenAPIIngestionRequest(BaseModel):
    """Richiesta per ingestione OpenAPI."""

    source: str = Field(
        ...,
        description="URL o path al file OpenAPI",
    )
    api_prefix: str | None = Field(
        default=None,
        description="Prefisso per i nomi dei tool",
    )


class OpenAPIIngestionResponse(BaseModel):
    """Risposta ingestione OpenAPI."""

    status: str
    tools_created: int
    tool_ids: list[str]


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/consolidation/trigger")
async def trigger_consolidation(
    request: ConsolidationRequest,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(require_role("admin")),
) -> ConsolidationResponse:
    """Avvia un ciclo di consolidazione manuale.

    Richiede ruolo 'admin'.
    """
    sleep_mode = get_sleep_mode()
    tenant_id = request.tenant_id or user.tenant_id

    if request.dry_run:
        # Esegui in foreground per dry run
        result = await sleep_mode.run_consolidation(tenant_id, dry_run=True)
        return ConsolidationResponse(
            status="completed",
            message=(
                f"Dry run: {result.episodes_processed} episodes, "
                f"{result.entities_created} entities would be created"
            ),
        )

    # Esegui in background
    from uuid import uuid4

    job_id = str(uuid4())

    async def run_consolidation():
        logger.info("background_consolidation_started", job_id=job_id)
        await sleep_mode.run_consolidation(tenant_id, dry_run=False)
        logger.info("background_consolidation_completed", job_id=job_id)

    background_tasks.add_task(run_consolidation)

    return ConsolidationResponse(
        status="started",
        job_id=job_id,
        message=f"Consolidation started for tenant {tenant_id}",
    )


@router.post("/consolidation/scheduler")
async def manage_scheduler(
    request: SchedulerRequest,
    user: AuthenticatedUser = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Gestisce lo scheduler di consolidazione background.

    Azioni:
    - start: Avvia scheduler
    - stop: Ferma scheduler
    - status: Stato corrente
    """
    sleep_mode = get_sleep_mode()

    if request.action == "start":
        await sleep_mode.start_background_scheduler(
            interval_hours=request.interval_hours,
            tenant_ids=request.tenant_ids,
        )
        return {
            "status": "started",
            "interval_hours": request.interval_hours,
        }

    elif request.action == "stop":
        await sleep_mode.stop_background_scheduler()
        return {"status": "stopped"}

    elif request.action == "status":
        return {
            "status": "running" if sleep_mode._running else "stopped",
            "has_task": sleep_mode._task is not None,
        }

    return {"status": "unknown_action"}


@router.post("/tools/ingest", response_model=OpenAPIIngestionResponse)
async def ingest_openapi(
    request: OpenAPIIngestionRequest,
    user: AuthenticatedUser = Depends(require_role("admin")),
) -> OpenAPIIngestionResponse:
    """Ingesta una specifica OpenAPI per registrare tool.

    Automaticamente crea nodi :Tool nel Skill Graph
    per ogni endpoint della specifica.
    """
    ingester = create_openapi_ingester()

    source = request.source

    try:
        if source.startswith("http://") or source.startswith("https://"):
            tool_ids = await ingester.ingest_from_url(
                tenant_id=user.tenant_id,
                url=source,
                api_prefix=request.api_prefix,
            )
        else:
            tool_ids = await ingester.ingest_from_file(
                tenant_id=user.tenant_id,
                file_path=source,
                api_prefix=request.api_prefix,
            )

    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {source}",
        )
    except Exception as e:
        logger.error("openapi_ingestion_error", error=str(e), source=source)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ingestion failed: {e}",
        )

    return OpenAPIIngestionResponse(
        status="completed",
        tools_created=len(tool_ids),
        tool_ids=tool_ids,
    )


@router.get("/stats")
async def get_stats(
    user: AuthenticatedUser = Depends(require_role("admin")),
) -> dict[str, Any]:
    """Statistiche del sistema.

    Ritorna metriche aggregate per il tenant.
    """
    from me4brain.memory import get_episodic_memory, get_semantic_memory

    episodic = get_episodic_memory()
    get_semantic_memory()

    # Conteggio episodi (placeholder - in produzione query Qdrant)
    # Conteggio entità (placeholder - in produzione query KuzuDB)

    return {
        "tenant_id": user.tenant_id,
        "memory": {
            "episodic": {
                "collection": episodic.COLLECTION_NAME,
                # "count": await episodic.count(user.tenant_id),
            },
            "semantic": {
                "database_type": "neo4j",  # Changed from KuzuDB to Neo4j
            },
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
