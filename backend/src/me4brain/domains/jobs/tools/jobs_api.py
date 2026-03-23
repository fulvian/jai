"""Jobs API Tools - RemoteOK, Arbeitnow.

100% Gratuiti e senza limiti:
- RemoteOK: Lavori tech remoti
- Arbeitnow: Lavori EU
"""

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

TIMEOUT = 15.0


# =============================================================================
# RemoteOK - Lavori Remoti Tech (100% Gratuito)
# =============================================================================


async def remoteok_jobs(
    tag: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Cerca lavori remoti su RemoteOK.

    Args:
        tag: Categoria/skill (es. "python", "react", "devops")
        limit: Numero massimo risultati

    Returns:
        dict con lavori trovati
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://remoteok.com/api",
                headers={"User-Agent": "Me4BrAIn/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()

            jobs = []
            for j in data[1 : limit + 1]:  # Skip first element (legal notice)
                # Filter by tag if specified
                tags = j.get("tags", [])
                if tag and tag.lower() not in [t.lower() for t in tags]:
                    continue

                jobs.append(
                    {
                        "id": j.get("id"),
                        "company": j.get("company"),
                        "position": j.get("position"),
                        "location": j.get("location"),
                        "salary_min": j.get("salary_min"),
                        "salary_max": j.get("salary_max"),
                        "tags": tags[:5],
                        "url": j.get("url"),
                        "date": j.get("date"),
                    }
                )

                if len(jobs) >= limit:
                    break

            return {
                "tag": tag,
                "jobs": jobs,
                "count": len(jobs),
                "source": "RemoteOK",
            }

    except Exception as e:
        logger.error("remoteok_jobs_error", error=str(e))
        return {"error": str(e), "source": "RemoteOK"}


# =============================================================================
# Arbeitnow - Lavori EU (100% Gratuito)
# =============================================================================


async def arbeitnow_jobs(
    query: str | None = None,
    location: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Cerca lavori su Arbeitnow (focus EU).

    Args:
        query: Keyword ricerca
        location: Località
        limit: Numero massimo risultati

    Returns:
        dict con lavori trovati
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://www.arbeitnow.com/api/job-board-api",
            )
            resp.raise_for_status()
            data = resp.json()

            jobs = []
            for j in data.get("data", []):
                # Filter by query/location
                if query:
                    title_lower = j.get("title", "").lower()
                    if query.lower() not in title_lower:
                        continue

                if location:
                    loc_lower = j.get("location", "").lower()
                    if location.lower() not in loc_lower:
                        continue

                jobs.append(
                    {
                        "slug": j.get("slug"),
                        "company": j.get("company_name"),
                        "title": j.get("title"),
                        "location": j.get("location"),
                        "remote": j.get("remote"),
                        "tags": j.get("tags", [])[:5],
                        "url": j.get("url"),
                        "created_at": j.get("created_at"),
                    }
                )

                if len(jobs) >= limit:
                    break

            return {
                "query": query,
                "location": location,
                "jobs": jobs,
                "count": len(jobs),
                "source": "Arbeitnow",
            }

    except Exception as e:
        logger.error("arbeitnow_jobs_error", error=str(e))
        return {"error": str(e), "source": "Arbeitnow"}


# =============================================================================
# Tool Registry
# =============================================================================

AVAILABLE_TOOLS = {
    "remoteok_jobs": remoteok_jobs,
    "arbeitnow_jobs": arbeitnow_jobs,
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool jobs per nome, filtrando parametri non accettati."""
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {"error": f"Unknown jobs tool: {tool_name}"}

    tool_func = AVAILABLE_TOOLS[tool_name]
    sig = inspect.signature(tool_func)
    valid_params = set(sig.parameters.keys())
    filtered_args = {k: v for k, v in arguments.items() if k in valid_params}

    if len(filtered_args) < len(arguments):
        ignored = set(arguments.keys()) - valid_params
        logger.warning(
            "execute_tool_ignored_params",
            tool=tool_name,
            ignored=list(ignored),
            hint="LLM hallucinated parameters not in function signature",
        )

    return await tool_func(**filtered_args)


# =============================================================================
# Tool Engine Integration
# =============================================================================


def get_tool_definitions() -> list:
    """Generate ToolDefinition objects for all Jobs tools."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        ToolDefinition(
            name="remoteok_jobs",
            description="Search remote tech jobs on RemoteOK. Find remote developer, designer, and tech positions worldwide. Use when user asks 'remote jobs', 'work from home tech positions', 'remote programming jobs'.",
            parameters={
                "tag": ToolParameter(
                    type="string",
                    description="Skill or category filter (e.g., 'python', 'react', 'devops', 'design')",
                    required=False,
                ),
                "limit": ToolParameter(
                    type="integer",
                    description="Maximum number of job listings to return",
                    required=False,
                ),
            },
            domain="jobs",
            category="remote",
        ),
        ToolDefinition(
            name="arbeitnow_jobs",
            description="Search for jobs in Europe on Arbeitnow. Find positions across EU countries. Use when user asks 'jobs in Europe', 'work in Berlin', 'EU tech positions'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Job title or keyword to search",
                    required=False,
                ),
                "location": ToolParameter(
                    type="string",
                    description="City or country (e.g., 'Berlin', 'Remote', 'Germany')",
                    required=False,
                ),
                "limit": ToolParameter(
                    type="integer",
                    description="Maximum number of job listings to return",
                    required=False,
                ),
            },
            domain="jobs",
            category="europe",
        ),
    ]


def get_executors() -> dict:
    """Return mapping of tool names to executor functions."""
    return AVAILABLE_TOOLS
