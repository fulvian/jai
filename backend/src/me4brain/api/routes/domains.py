"""Domain API Routes - Espone i domain handlers via REST.

Endpoints:
- GET /domains - Lista tutti i domini disponibili
- GET /domains/{domain} - Info specifico dominio
- POST /domains/{domain}/query - Esegue query su dominio
- POST /domains/{domain}/execute - Esegue tool specifico

Questo wrapper permette accesso esterno all'architettura modulare.
"""

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/domains", tags=["domains"])


# =============================================================================
# Request/Response Models
# =============================================================================


class QueryRequest(BaseModel):
    """Richiesta query a dominio."""

    query: str = Field(..., description="Query in linguaggio naturale")
    context: dict[str, Any] = Field(default_factory=dict, description="Contesto aggiuntivo")
    tenant_id: str = Field(default="default", description="Tenant ID")


class ToolExecuteRequest(BaseModel):
    """Richiesta esecuzione tool."""

    tool_name: str = Field(..., description="Nome del tool da eseguire")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Argomenti tool")


class DomainInfo(BaseModel):
    """Info su un dominio."""

    name: str
    volatility: str
    ttl_hours: int
    capabilities: list[dict[str, Any]]


class QueryResponse(BaseModel):
    """Risposta a query."""

    success: bool
    domain: str
    results: list[dict[str, Any]]
    latency_ms: float


class ToolResponse(BaseModel):
    """Risposta esecuzione tool."""

    success: bool
    tool_name: str
    data: dict[str, Any] | None
    error: str | None


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[DomainInfo])
async def list_domains(tenant_id: str = "default") -> list[DomainInfo]:
    """Lista tutti i domini disponibili."""
    from me4brain.core.plugin_registry import PluginRegistry

    try:
        registry = await PluginRegistry.get_instance(tenant_id)
        domains = []

        for name, handler in registry._handlers.items():
            domains.append(
                DomainInfo(
                    name=name,
                    volatility=handler.volatility.value,
                    ttl_hours=handler.default_ttl_hours,
                    capabilities=[
                        {
                            "name": c.name,
                            "description": c.description,
                            "keywords": c.keywords,
                        }
                        for c in handler.capabilities
                    ],
                )
            )

        logger.info("domains_listed", count=len(domains), tenant_id=tenant_id)
        return domains

    except Exception as e:
        logger.error("domains_list_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{domain_name}", response_model=DomainInfo)
async def get_domain(domain_name: str, tenant_id: str = "default") -> DomainInfo:
    """Ottieni info su un dominio specifico."""
    from me4brain.core.plugin_registry import PluginRegistry

    try:
        registry = await PluginRegistry.get_instance(tenant_id)
        handler = registry.get_handler(domain_name)

        if handler is None:
            raise HTTPException(status_code=404, detail=f"Domain not found: {domain_name}")

        return DomainInfo(
            name=handler.domain_name,
            volatility=handler.volatility.value,
            ttl_hours=handler.default_ttl_hours,
            capabilities=[
                {
                    "name": c.name,
                    "description": c.description,
                    "keywords": c.keywords,
                }
                for c in handler.capabilities
            ],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("domain_get_error", domain=domain_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{domain_name}/query", response_model=QueryResponse)
async def query_domain(domain_name: str, request: QueryRequest) -> QueryResponse:
    """Esegue query su un dominio specifico."""
    from datetime import UTC, datetime

    from me4brain.core.plugin_registry import PluginRegistry
    from me4brain.domains.adaptive_guardrails import apply_response_guardrails

    start_time = datetime.now(UTC)

    try:
        registry = await PluginRegistry.get_instance(request.tenant_id)
        handler = registry.get_handler(domain_name)

        if handler is None:
            raise HTTPException(status_code=404, detail=f"Domain not found: {domain_name}")

        # Analisi query semplificata
        analysis = {"entities": [], "query": request.query}

        # Esegui query
        results = await handler.execute(
            query=request.query,
            analysis=analysis,
            context=request.context,
        )

        # Apply adaptive response guardrails to manage size and prevent truncation
        guardrailed_results = [apply_response_guardrails(r, domain_name) for r in results]

        latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        logger.info(
            "domain_query_executed",
            domain=domain_name,
            query_preview=request.query[:50],
            results_count=len(guardrailed_results),
            latency_ms=latency_ms,
        )

        return QueryResponse(
            success=any(r.success for r in guardrailed_results),
            domain=domain_name,
            results=[
                {
                    "tool": r.tool_name,
                    "success": r.success,
                    "data": r.data,
                    "error": r.error,
                }
                for r in guardrailed_results
            ],
            latency_ms=latency_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("domain_query_error", domain=domain_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{domain_name}/execute", response_model=ToolResponse)
async def execute_tool(domain_name: str, request: ToolExecuteRequest) -> ToolResponse:
    """Esegue un tool specifico su un dominio."""
    from me4brain.core.plugin_registry import PluginRegistry

    try:
        registry = await PluginRegistry.get_instance("default")
        handler = registry.get_handler(domain_name)

        if handler is None:
            raise HTTPException(status_code=404, detail=f"Domain not found: {domain_name}")

        result = await handler.execute_tool(request.tool_name, request.arguments)

        logger.info(
            "tool_executed",
            domain=domain_name,
            tool=request.tool_name,
            success=not result.get("error"),
        )

        return ToolResponse(
            success=not result.get("error"),
            tool_name=request.tool_name,
            data=result if not result.get("error") else None,
            error=result.get("error"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("tool_execute_error", domain=domain_name, tool=request.tool_name, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/route")
async def route_query(request: QueryRequest) -> dict[str, Any]:
    """Determina il dominio migliore per una query.

    Utile per capire quale dominio gestirà una query
    prima di eseguirla.
    """
    from me4brain.core.plugin_registry import PluginRegistry

    try:
        registry = await PluginRegistry.get_instance(request.tenant_id)

        analysis = {"entities": []}
        handler = await registry.route_query(request.query, analysis)

        if handler is None:
            return {
                "query": request.query,
                "routed_to": None,
                "reason": "No domain matched query",
            }

        # Ottieni score
        score = await handler.can_handle(request.query, analysis)

        return {
            "query": request.query,
            "routed_to": handler.domain_name,
            "score": score,
            "capabilities": [c.name for c in handler.capabilities],
        }

    except Exception as e:
        logger.error("route_query_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
