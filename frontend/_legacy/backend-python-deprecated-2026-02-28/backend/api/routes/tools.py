"""Tools endpoints - Tool Calling Engine catalog access.

Endpoint per esplorare e interrogare il catalogo dei tool disponibili.
"""

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.services.me4brain_service import get_me4brain_service

router = APIRouter()


class ToolSummary(BaseModel):
    """Summary of a tool."""

    name: str
    description: str
    domain: str | None = None
    category: str | None = None


class ToolDetail(BaseModel):
    """Detailed tool information."""

    name: str
    description: str
    domain: str | None = None
    category: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolListResponse(BaseModel):
    """Response for tool listing."""

    tools: list[ToolSummary]
    total: int
    filters: dict[str, str | None]


class CatalogStatsResponse(BaseModel):
    """Response for catalog statistics."""

    total_tools: int
    domains: list[dict[str, Any]]


@router.get("/tools")
async def list_tools(
    domain: str | None = Query(None, description="Filtra per dominio"),
    category: str | None = Query(None, description="Filtra per categoria"),
    search: str | None = Query(None, description="Cerca in nome/descrizione"),
) -> ToolListResponse:
    """
    List available tools in the catalog.

    Filters:
    - domain: "finance_crypto", "geo_weather", "medical", etc.
    - category: "crypto", "weather", "research", etc.
    - search: Free-text search in tool names and descriptions
    """
    me4brain = get_me4brain_service()

    tools = await me4brain.list_tools(
        domain=domain,
        category=category,
        search=search,
    )

    return ToolListResponse(
        tools=[
            ToolSummary(
                name=t.name,
                description=t.description,
                domain=t.domain,
                category=t.category,
            )
            for t in tools
        ],
        total=len(tools),
        filters={"domain": domain, "category": category, "search": search},
    )


@router.get("/tools/stats")
async def get_stats() -> CatalogStatsResponse:
    """
    Get catalog statistics.

    Returns total tools count and per-domain breakdown.
    """
    me4brain = get_me4brain_service()
    stats = await me4brain.get_stats()

    return CatalogStatsResponse(
        total_tools=stats["total_tools"],
        domains=stats["domains"],
    )


@router.get("/tools/{tool_name}")
async def get_tool(tool_name: str) -> ToolDetail:
    """
    Get detailed information about a specific tool.

    Includes full parameter schema with types and descriptions.
    """
    me4brain = get_me4brain_service()
    tool = await me4brain.get_tool(tool_name)

    return ToolDetail(
        name=tool.name,
        description=tool.description,
        domain=tool.domain,
        category=tool.category,
        parameters=tool.parameters,
    )


@router.get("/tools/domains/list")
async def list_domains() -> dict[str, Any]:
    """
    List all available domains with tool counts.
    """
    me4brain = get_me4brain_service()
    stats = await me4brain.get_stats()

    return {
        "domains": [
            {
                "name": d["domain"],
                "tool_count": d["tool_count"],
            }
            for d in stats["domains"]
        ],
        "total_domains": len(stats["domains"]),
        "total_tools": stats["total_tools"],
    }
