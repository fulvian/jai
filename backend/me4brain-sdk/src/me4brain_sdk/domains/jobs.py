"""Jobs Domain - Remote job listings."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class RemoteJob(BaseModel):
    """Remote job listing."""

    id: int | str
    title: str
    company: str
    description: str | None = None
    location: str | None = None
    salary: str | None = None
    job_type: str | None = None
    url: str | None = None
    posted_at: str | None = None
    tags: list[str] = Field(default_factory=list)


class JobsDomain(BaseDomain):
    """Jobs domain - Remote job listings.

    Example:
        # Search remote jobs
        jobs = await client.domains.jobs.search("python developer")

        # Get job categories
        categories = await client.domains.jobs.categories()
    """

    @property
    def domain_name(self) -> str:
        return "jobs"

    async def search(
        self,
        query: str,
        max_results: int = 20,
        category: str | None = None,
    ) -> list[RemoteJob]:
        """Search remote job listings.

        Args:
            query: Job search query
            max_results: Maximum results
            category: Job category filter

        Returns:
            List of matching jobs
        """
        params: dict[str, Any] = {"query": query, "max_results": max_results}
        if category:
            params["category"] = category
        result = await self._execute_tool("remotive_search", params)
        jobs = result.get("result", {}).get("jobs", [])
        return [RemoteJob.model_validate(j) for j in jobs]

    async def list_jobs(
        self,
        category: str | None = None,
        limit: int = 50,
    ) -> list[RemoteJob]:
        """List available remote jobs.

        Args:
            category: Filter by category
            limit: Maximum jobs

        Returns:
            List of jobs
        """
        params: dict[str, Any] = {"limit": limit}
        if category:
            params["category"] = category
        result = await self._execute_tool("remotive_list", params)
        jobs = result.get("result", {}).get("jobs", [])
        return [RemoteJob.model_validate(j) for j in jobs]

    async def categories(self) -> list[str]:
        """Get available job categories.

        Returns:
            List of category names
        """
        result = await self._execute_tool("remotive_categories", {})
        return result.get("result", {}).get("categories", [])
