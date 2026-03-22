"""Jobs Domain Handler."""

from typing import Any

import structlog

from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
)

logger = structlog.get_logger(__name__)


class JobsHandler(DomainHandler):
    """Handler per Lavoro e Carriera."""

    HANDLED_SERVICES = frozenset({"RemoteOKService", "ArbeitnowService"})

    JOBS_KEYWORDS = frozenset(
        {
            "lavoro",
            "job",
            "posizione",
            "carriera",
            "remoto",
            "remote",
            "developer",
            "engineer",
            "hiring",
            "assunzione",
            "stipendio",
            "salary",
            "offerta",
            "vacancy",
        }
    )

    @property
    def domain_name(self) -> str:
        return "jobs"

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="remote_jobs",
                description="Lavori tech remoti (RemoteOK)",
                required_params=[],
                optional_params=["tag"],
            ),
            DomainCapability(
                name="eu_jobs",
                description="Lavori EU (Arbeitnow)",
                required_params=[],
                optional_params=["query", "location"],
            ),
        ]

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.VOLATILE

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        """Check if this handler can process the query."""
        query_lower = query.lower()
        matches = sum(1 for kw in self.JOBS_KEYWORDS if kw in query_lower)
        if matches >= 2:
            return 0.9
        elif matches == 1:
            return 0.7
        return 0.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        from .tools.jobs_api import execute_tool

        query_lower = query.lower()

        # Extract potential tag/skill
        skills = ["python", "react", "javascript", "devops", "golang", "rust", "java"]
        tag = None
        for skill in skills:
            if skill in query_lower:
                tag = skill
                break

        # Use RemoteOK for tech jobs
        if any(kw in query_lower for kw in ["remote", "remoto", "tech"]):
            data = await execute_tool("remoteok_jobs", {"tag": tag})
            tool_name = "remoteok_jobs"
        else:
            # Default to Arbeitnow for EU jobs
            data = await execute_tool("arbeitnow_jobs", {"query": query})
            tool_name = "arbeitnow_jobs"

        return [
            DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name=tool_name,
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )
        ]
