from __future__ import annotations

"""Engine Namespace - Tool Calling Engine interface."""

from typing import Any

from me4brain_sdk._http import HTTPClient
from pydantic import BaseModel


class ToolCallInfo(BaseModel):
    """Info su una chiamata tool eseguita."""

    tool_name: str
    arguments: dict[str, Any] = {}
    success: bool
    latency_ms: float
    error: str | None = None


class EngineQueryResponse(BaseModel):
    """Risposta query dal Tool Calling Engine."""

    query: str
    answer: str
    tools_called: list[ToolCallInfo]
    total_latency_ms: float
    raw_results: list[dict[str, Any]] | None = None


class EngineNamespace:
    """Engine Namespace - Tool Calling Engine API.

    Provides access to the Tool Calling Engine for natural language
    queries that automatically select and execute tools.

    Example:
        response = await client.engine.query(
            query="What's the Bitcoin price?",
            conversation_context="Previous assistant message...",
        )
        print(response.answer)
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def query(
        self,
        query: str,
        conversation_context: str | None = None,
        include_raw_results: bool = False,
        timeout_seconds: float = 30.0,
    ) -> EngineQueryResponse:
        """Execute a natural language query through the Tool Calling Engine.

        Args:
            query: Natural language query
            conversation_context: Previous conversation context for tools
            include_raw_results: Include raw tool JSON in response
            timeout_seconds: Query timeout

        Returns:
            EngineQueryResponse with answer, tools_called, latency
        """
        data = await self._http.post(
            "/v1/engine/query",
            json_data={
                "query": query,
                "conversation_context": conversation_context,
                "include_raw_results": include_raw_results,
                "timeout_seconds": timeout_seconds,
            },
        )
        return EngineQueryResponse.model_validate(data)

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a tool directly by name.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        data = await self._http.post(
            "/v1/engine/call",
            json_data={
                "tool_name": tool_name,
                "arguments": arguments or {},
            },
        )
        return data

    async def list_tools(
        self,
        domain: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """List available tools.

        Args:
            domain: Filter by domain
            category: Filter by category
            search: Search in name/description

        Returns:
            Tool list with total count and domains
        """
        params: dict[str, Any] = {}
        if domain:
            params["domain"] = domain
        if category:
            params["category"] = category
        if search:
            params["search"] = search

        return await self._http.get("/v1/engine/tools", params=params)

    async def get_tool(self, tool_name: str) -> dict[str, Any]:
        """Get details of a specific tool.

        Args:
            tool_name: Tool name

        Returns:
            Tool details
        """
        return await self._http.get(f"/v1/engine/tools/{tool_name}")

    async def stats(self) -> dict[str, Any]:
        """Get catalog statistics.

        Returns:
            Statistics by domain
        """
        return await self._http.get("/v1/engine/stats")
