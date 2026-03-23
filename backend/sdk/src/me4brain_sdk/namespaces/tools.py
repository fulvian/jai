from __future__ import annotations

"""Tools Namespace - Tool search, execution, and management."""

from typing import Any

from me4brain_sdk._http import HTTPClient
from me4brain_sdk.models.tools import Tool, ToolExecution, ToolSearchResult


class ToolsNamespace:
    """Tools operations - search, execute, and manage tools.

    The tools namespace provides access to the unified tool registry
    across all domains (medical, finance, google workspace, etc.).

    Example:
        # Search for tools
        results = await client.tools.search("weather forecast")

        # Execute a tool
        execution = await client.tools.execute(
            tool_id="weather_current",
            parameters={"location": "Milan, IT"},
        )

        # List all tools
        tools = await client.tools.list()
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def list(
        self,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Tool]:
        """List available tools.

        Args:
            category: Filter by category
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of tools
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if category:
            params["category"] = category

        data = await self._http.get("/v1/tools/list", params=params)
        return [Tool.model_validate(t) for t in data.get("tools", [])]

    async def get(self, tool_id: str) -> Tool:
        """Get tool details.

        Args:
            tool_id: Tool identifier

        Returns:
            Tool details
        """
        data = await self._http.get(f"/v1/tools/{tool_id}")
        return Tool.model_validate(data)

    async def search(
        self,
        query: str,
        limit: int = 10,
        category: str | None = None,
        min_score: float = 0.5,
    ) -> list[ToolSearchResult]:
        """Search tools by natural language query.

        Args:
            query: Search query
            limit: Maximum results
            category: Filter by category
            min_score: Minimum relevance score

        Returns:
            List of matching tools with scores
        """
        params: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "min_score": min_score,
        }
        if category:
            params["category"] = category

        data = await self._http.post("/v1/tools/search", json_data=params)
        return [ToolSearchResult.model_validate(t) for t in data.get("tools", [])]

    async def execute(
        self,
        tool_id: str | None = None,
        tool_name: str | None = None,
        parameters: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ToolExecution:
        """Execute a tool.

        Args:
            tool_id: Tool ID (preferred)
            tool_name: Tool name (alternative)
            parameters: Tool parameters
            context: Execution context

        Returns:
            Execution result
        """
        data = await self._http.post(
            "/v1/tools/execute",
            json_data={
                "tool_id": tool_id,
                "tool_name": tool_name,
                "parameters": parameters or {},
                "context": context or {},
            },
        )
        return ToolExecution.model_validate(data)

    async def categories(self) -> list[str]:
        """List tool categories.

        Returns:
            List of category names
        """
        data = await self._http.get("/v1/tools/categories")
        return data.get("categories", [])

    async def by_category(self, category: str) -> list[Tool]:
        """Get tools by category.

        Args:
            category: Category name

        Returns:
            List of tools in category
        """
        data = await self._http.get(f"/v1/tools/category/{category}")
        return [Tool.model_validate(t) for t in data.get("tools", [])]

    async def register(
        self,
        name: str,
        description: str,
        category: str,
        endpoint: str | None = None,
        method: str = "POST",
        api_schema: dict[str, Any] | None = None,
    ) -> Tool:
        """Register a new tool.

        Args:
            name: Tool name
            description: Tool description
            category: Tool category
            endpoint: API endpoint
            method: HTTP method
            api_schema: OpenAPI schema

        Returns:
            Registered tool
        """
        data = await self._http.post(
            "/v1/tools/register",
            json_data={
                "name": name,
                "description": description,
                "category": category,
                "endpoint": endpoint,
                "method": method,
                "api_schema": api_schema or {},
            },
        )
        return Tool.model_validate(data)

    async def delete(self, tool_id: str) -> bool:
        """Delete a tool.

        Args:
            tool_id: Tool identifier

        Returns:
            True if deleted
        """
        await self._http.delete(f"/v1/tools/{tool_id}")
        return True

    async def update_stats(
        self,
        tool_id: str,
        success: bool,
        latency_ms: float,
    ) -> None:
        """Update tool execution statistics.

        Args:
            tool_id: Tool identifier
            success: Whether execution succeeded
            latency_ms: Execution latency
        """
        await self._http.post(
            f"/v1/tools/{tool_id}/stats",
            json_data={
                "success": success,
                "latency_ms": latency_ms,
            },
        )
