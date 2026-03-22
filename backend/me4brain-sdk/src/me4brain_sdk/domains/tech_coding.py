"""Tech/Coding Domain - GitHub, StackOverflow, Code Execution."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class GitHubRepo(BaseModel):
    """GitHub repository."""

    name: str
    full_name: str
    description: str | None = None
    url: str
    stars: int = 0
    forks: int = 0
    language: str | None = None
    topics: list[str] = Field(default_factory=list)


class StackOverflowQuestion(BaseModel):
    """StackOverflow question."""

    question_id: int
    title: str
    score: int = 0
    answer_count: int = 0
    is_answered: bool = False
    link: str
    tags: list[str] = Field(default_factory=list)


class CodeExecutionResult(BaseModel):
    """Code execution result."""

    language: str
    version: str | None = None
    output: str
    stderr: str | None = None
    exit_code: int = 0
    execution_time_ms: float = 0.0


class TechCodingDomain(BaseDomain):
    """Tech/Coding domain - GitHub, StackOverflow, code execution.

    Example:
        # Search GitHub
        repos = await client.domains.tech_coding.github_search("fastapi async")

        # Execute code
        result = await client.domains.tech_coding.execute_code(
            code="print('Hello')", language="python"
        )
    """

    @property
    def domain_name(self) -> str:
        return "tech_coding"

    async def github_search(
        self,
        query: str,
        max_results: int = 10,
        sort: str = "stars",
    ) -> list[GitHubRepo]:
        """Search GitHub repositories.

        Args:
            query: Search query
            max_results: Maximum results
            sort: Sort by "stars", "forks", "updated"

        Returns:
            List of repositories
        """
        result = await self._execute_tool(
            "github_search_repos",
            {"query": query, "max_results": max_results, "sort": sort},
        )
        repos = result.get("result", {}).get("repositories", [])
        return [GitHubRepo.model_validate(r) for r in repos]

    async def github_user(self, username: str) -> dict[str, Any]:
        """Get GitHub user profile.

        Args:
            username: GitHub username

        Returns:
            User profile data
        """
        result = await self._execute_tool("github_user", {"username": username})
        return result.get("result", {})

    async def stackoverflow_search(
        self,
        query: str,
        max_results: int = 10,
        tagged: list[str] | None = None,
    ) -> list[StackOverflowQuestion]:
        """Search StackOverflow questions.

        Args:
            query: Search query
            max_results: Maximum results
            tagged: Filter by tags

        Returns:
            List of questions
        """
        result = await self._execute_tool(
            "stackoverflow_search",
            {"query": query, "max_results": max_results, "tagged": tagged or []},
        )
        questions = result.get("result", {}).get("questions", [])
        return [StackOverflowQuestion.model_validate(q) for q in questions]

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        stdin: str | None = None,
    ) -> CodeExecutionResult:
        """Execute code in a sandbox.

        Args:
            code: Code to execute
            language: Programming language
            stdin: Optional stdin input

        Returns:
            Execution result
        """
        result = await self._execute_tool(
            "code_execute",
            {"code": code, "language": language, "stdin": stdin},
        )
        return CodeExecutionResult.model_validate(result.get("result", {}))

    async def npm_package(self, package_name: str) -> dict[str, Any]:
        """Get NPM package info.

        Args:
            package_name: Package name

        Returns:
            Package information
        """
        result = await self._execute_tool("npm_package", {"package_name": package_name})
        return result.get("result", {})

    async def pypi_package(self, package_name: str) -> dict[str, Any]:
        """Get PyPI package info.

        Args:
            package_name: Package name

        Returns:
            Package information
        """
        result = await self._execute_tool("pypi_package", {"package_name": package_name})
        return result.get("result", {})
