from __future__ import annotations

"""Synchronous wrapper for AsyncMe4BrAInClient.

Provides a blocking API for use in sync contexts.
Uses anyio for async-to-sync conversion.
"""

from typing import Any, Iterator
import anyio
from functools import wraps

from me4brain_sdk.client import AsyncMe4BrAInClient
from me4brain_sdk.models.cognitive import QueryResponse, StreamChunk


def _run_sync(coro):
    """Run async coroutine synchronously."""
    return anyio.from_thread.run_sync(lambda: anyio.run(coro))


class SyncNamespaceWrapper:
    """Wraps async namespace methods to be synchronous."""

    def __init__(self, async_namespace: Any) -> None:
        self._async = async_namespace

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._async, name)
        if callable(attr):

            @wraps(attr)
            def sync_method(*args, **kwargs):
                return anyio.from_thread.run(lambda: attr(*args, **kwargs))

            return sync_method
        return attr


class Me4BrAInClient:
    """Synchronous client for Me4BrAIn Agentic Memory Platform.

    Provides the same API as AsyncMe4BrAInClient but with blocking calls.
    Suitable for use in non-async contexts.

    Example:
        with Me4BrAInClient(
            base_url="http://localhost:8100",
            api_key="your-key",
        ) as client:
            response = client.query("What did we discuss?")
            print(response.answer)
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        tenant_id: str | None = None,
        user_id: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        pool_connections: int = 100,
        pool_maxsize: int = 100,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize synchronous client.

        Args:
            base_url: Base URL of Me4BrAIn API
            api_key: API key for authentication
            tenant_id: Default tenant ID
            user_id: Default user ID
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            pool_connections: Connection pool size
            pool_maxsize: Max connections per host
            extra_headers: Additional headers
        """
        self._async_client = AsyncMe4BrAInClient(
            base_url=base_url,
            api_key=api_key,
            tenant_id=tenant_id,
            user_id=user_id,
            timeout=timeout,
            max_retries=max_retries,
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
            extra_headers=extra_headers,
        )

    def close(self) -> None:
        """Close the client."""
        anyio.from_thread.run(self._async_client.close)

    def __enter__(self) -> "Me4BrAInClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    @property
    def working(self) -> SyncNamespaceWrapper:
        """Working Memory namespace."""
        return SyncNamespaceWrapper(self._async_client.working)

    @property
    def episodic(self) -> SyncNamespaceWrapper:
        """Episodic Memory namespace."""
        return SyncNamespaceWrapper(self._async_client.episodic)

    @property
    def semantic(self) -> SyncNamespaceWrapper:
        """Semantic Memory namespace."""
        return SyncNamespaceWrapper(self._async_client.semantic)

    @property
    def procedural(self) -> SyncNamespaceWrapper:
        """Procedural Memory namespace."""
        return SyncNamespaceWrapper(self._async_client.procedural)

    @property
    def cognitive(self) -> SyncNamespaceWrapper:
        """Cognitive namespace."""
        return SyncNamespaceWrapper(self._async_client.cognitive)

    @property
    def tools(self) -> SyncNamespaceWrapper:
        """Tools namespace."""
        return SyncNamespaceWrapper(self._async_client.tools)

    @property
    def admin(self) -> SyncNamespaceWrapper:
        """Admin namespace."""
        return SyncNamespaceWrapper(self._async_client.admin)

    @property
    def engine(self) -> SyncNamespaceWrapper:
        """Engine namespace - Tool Calling Engine."""
        return SyncNamespaceWrapper(self._async_client.engine)

    def health(self) -> dict[str, Any]:
        """Check API health."""
        return anyio.from_thread.run(self._async_client.health)

    def query(
        self,
        query: str,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> QueryResponse:
        """Execute cognitive query.

        Args:
            query: Natural language query
            session_id: Optional session ID
            **kwargs: Additional parameters

        Returns:
            Query response
        """
        return anyio.from_thread.run(
            lambda: self._async_client.query(query, session_id=session_id, **kwargs)
        )

    def query_stream(
        self,
        query: str,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> Iterator[StreamChunk]:
        """Streaming query (synchronous iterator).

        Args:
            query: Natural language query
            session_id: Optional session ID
            **kwargs: Additional parameters

        Yields:
            Stream chunks
        """

        async def collect():
            chunks = []
            async for chunk in self._async_client.cognitive.query_stream(
                query, session_id=session_id, **kwargs
            ):
                chunks.append(chunk)
            return chunks

        chunks = anyio.from_thread.run(collect)
        for chunk in chunks:
            yield chunk
