"""Me4BrAIn SDK - Sync Client.

Synchronous wrapper around the async Me4BrAInClient.

Usage:
    from me4brain_sdk import Me4BrAInSyncClient

    with Me4BrAInSyncClient() as client:
        response = client.engine.query("Qual è il prezzo del Bitcoin?")
        print(response.answer)
"""

from __future__ import annotations

import asyncio
from typing import Any, TypeVar

from me4brain_sdk.client import (
    CatalogStats,
    EngineQueryResponse,
    Me4BrAInClient,
    ToolInfo,
)
from me4brain_sdk.config import Me4BrAInConfig

T = TypeVar("T")


def _run_sync(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_running_loop()
        # If we're in an async context, create a new thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop, can use asyncio.run
        return asyncio.run(coro)


class SyncEngineNamespace:
    """Synchronous Tool Calling Engine namespace."""

    def __init__(self, client: Me4BrAInSyncClient) -> None:
        self._client = client

    def query(
        self,
        query: str,
        *,
        include_raw_results: bool = False,
        timeout_seconds: float = 30.0,
    ) -> EngineQueryResponse:
        """Execute a natural language query (sync version).

        Args:
            query: Natural language query
            include_raw_results: Include raw tool results in response
            timeout_seconds: Timeout for the query

        Returns:
            EngineQueryResponse with answer and tools info
        """
        return _run_sync(
            self._client._async_client.engine.query(
                query,
                include_raw_results=include_raw_results,
                timeout_seconds=timeout_seconds,
            )
        )

    def call(self, tool_name: str, **arguments: Any) -> Any:
        """Call a tool directly by name (sync version).

        Args:
            tool_name: Name of the tool to call
            **arguments: Tool arguments

        Returns:
            Tool result
        """
        return _run_sync(self._client._async_client.engine.call(tool_name, **arguments))

    def list_tools(
        self,
        *,
        domain: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> list[ToolInfo]:
        """List available tools (sync version).

        Args:
            domain: Filter by domain
            category: Filter by category
            search: Search in names/descriptions

        Returns:
            List of ToolInfo
        """
        return _run_sync(
            self._client._async_client.engine.list_tools(
                domain=domain,
                category=category,
                search=search,
            )
        )

    def get_tool(self, tool_name: str) -> ToolInfo:
        """Get tool details (sync version)."""
        return _run_sync(self._client._async_client.engine.get_tool(tool_name))

    def stats(self) -> CatalogStats:
        """Get catalog statistics (sync version)."""
        return _run_sync(self._client._async_client.engine.stats())


class Me4BrAInSyncClient:
    """Synchronous client for Me4BrAIn API.

    Wrapper around Me4BrAInClient for non-async contexts.

    Usage:
        with Me4BrAInSyncClient() as client:
            response = client.engine.query("Bitcoin price?")
            print(response.answer)
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        tenant_id: str | None = None,
        timeout: float | None = None,
        config: Me4BrAInConfig | None = None,
    ) -> None:
        """Initialize the sync client.

        Args:
            base_url: API base URL
            api_key: API key for authentication
            tenant_id: Tenant ID
            timeout: Request timeout
            config: Full configuration object
        """
        self._async_client = Me4BrAInClient(
            base_url=base_url,
            api_key=api_key,
            tenant_id=tenant_id,
            timeout=timeout,
            config=config,
        )
        self._engine: SyncEngineNamespace | None = None

    @property
    def engine(self) -> SyncEngineNamespace:
        """Access Tool Calling Engine endpoints."""
        if self._engine is None:
            self._engine = SyncEngineNamespace(self)
        return self._engine

    def close(self) -> None:
        """Close the client."""
        _run_sync(self._async_client.close())

    def __enter__(self) -> Me4BrAInSyncClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
