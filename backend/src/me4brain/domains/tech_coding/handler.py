"""Tech/Coding Domain Handler."""

from typing import Any

import structlog

from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
)

logger = structlog.get_logger(__name__)


class TechCodingHandler(DomainHandler):
    """Handler per sviluppo e programmazione."""

    HANDLED_SERVICES = frozenset(
        {
            "GitHubService",
            "NPMService",
            "PyPIService",
            "StackOverflowService",
            "PistonService",
        }
    )

    TECH_KEYWORDS = frozenset(
        {
            # GitHub
            "github",
            "repo",
            "repository",
            "issue",
            "pull request",
            "pr",
            "commit",
            "branch",
            "fork",
            "star",
            # Packages
            "npm",
            "package",
            "pypi",
            "pip",
            "library",
            "dependency",
            "crates",
            "cargo",
            # Code
            "codice",
            "code",
            "esegui",
            "execute",
            "run",
            "compile",
            "python",
            "javascript",
            "rust",
            "golang",
            # Q&A
            "stackoverflow",
            "errore",
            "error",
            "come",
            "how to",
        }
    )

    @property
    def domain_name(self) -> str:
        return "tech_coding"

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="github",
                description="GitHub repos, issues, code search",
                required_params=["query"],
                optional_params=["owner", "repo"],
            ),
            DomainCapability(
                name="packages",
                description="NPM/PyPI package info",
                required_params=["package_name"],
            ),
            DomainCapability(
                name="stackoverflow",
                description="Stack Overflow Q&A",
                required_params=["query"],
            ),
            DomainCapability(
                name="code_execution",
                description="Execute code (Piston)",
                required_params=["language", "code"],
            ),
        ]

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.VOLATILE

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        """Check if this handler can process the query."""
        query_lower = query.lower()
        matches = sum(1 for kw in self.TECH_KEYWORDS if kw in query_lower)
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
        from .tools.tech_api import execute_tool

        query_lower = query.lower()

        def make_result(data: dict, tool_name: str) -> DomainExecutionResult:
            return DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name=tool_name,
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )

        # GitHub
        if "github" in query_lower or "repo" in query_lower:
            data = await execute_tool("github_search_repos", {"query": query})
            return [make_result(data, "github_search_repos")]

        # NPM
        if "npm" in query_lower or ("package" in query_lower and "javascript" in query_lower):
            data = await execute_tool("npm_search", {"query": query})
            return [make_result(data, "npm_search")]

        # PyPI
        if (
            "pypi" in query_lower
            or "pip" in query_lower
            or ("package" in query_lower and "python" in query_lower)
        ):
            # Try to extract package name
            words = query.split()
            for i, w in enumerate(words):
                if w.lower() in ["pypi", "pip", "package"] and i + 1 < len(words):
                    pkg = words[i + 1]
                    data = await execute_tool("pypi_package", {"name": pkg})
                    return [make_result(data, "pypi_package")]

        # Stack Overflow
        if "stackoverflow" in query_lower or "errore" in query_lower or "error" in query_lower:
            data = await execute_tool("stackoverflow_search", {"query": query})
            return [make_result(data, "stackoverflow_search")]

        # Code execution
        if any(kw in query_lower for kw in ["esegui", "execute", "run"]):
            data = await execute_tool("piston_runtimes", {})
            return [make_result(data, "piston_runtimes")]

        # Default: GitHub search
        data = await execute_tool("github_search_repos", {"query": query})
        return [make_result(data, "github_search_repos")]
