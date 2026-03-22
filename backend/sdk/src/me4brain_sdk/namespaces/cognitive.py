from __future__ import annotations

"""Cognitive Namespace - Query interface with reasoning."""

from typing import Any, AsyncIterator

from me4brain_sdk._http import HTTPClient
from me4brain_sdk.models.cognitive import QueryResponse, StreamChunk


class CognitiveNamespace:
    """Cognitive Interface - Natural language queries with memory integration.

    The cognitive namespace provides the main query interface that:
    - Retrieves relevant context from all memory layers
    - Executes reasoning chains
    - Invokes tools as needed
    - Returns answers with full provenance

    Example:
        # Simple query
        response = await client.cognitive.query(
            query="What did we discuss about the budget?",
            session_id="session-123",
        )
        print(response.answer)
        print(f"Sources: {len(response.episodic_results)} episodes")

        # Streaming query
        async for chunk in client.cognitive.query_stream(
            query="Summarize all project meetings",
        ):
            print(chunk.content, end="", flush=True)
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def query(
        self,
        query: str,
        session_id: str | None = None,
        user_id: str | None = None,
        use_episodic: bool = True,
        use_semantic: bool = True,
        use_procedural: bool = True,
        memory_limit: int = 10,
        min_relevance: float = 0.5,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QueryResponse:
        """Execute a cognitive query with memory integration.

        Args:
            query: Natural language query
            session_id: Optional session for context
            user_id: Optional user ID
            use_episodic: Include episodic memory
            use_semantic: Include semantic memory
            use_procedural: Include procedural memory
            memory_limit: Max memory items per layer
            min_relevance: Minimum relevance threshold
            context: Additional context
            metadata: Request metadata

        Returns:
            Query response with answer and provenance
        """
        data = await self._http.post(
            "/v1/memory/query",
            json_data={
                "query": query,
                "session_id": session_id,
                "max_iterations": 5,  # Backend default
            },
        )
        return QueryResponse.model_validate(data)

    async def query_stream(
        self,
        query: str,
        session_id: str | None = None,
        user_id: str | None = None,
        use_episodic: bool = True,
        use_semantic: bool = True,
        use_procedural: bool = True,
        memory_limit: int = 10,
        min_relevance: float = 0.5,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Execute a streaming cognitive query.

        Yields chunks as the answer is generated, including:
        - Content tokens
        - Reasoning steps
        - Tool calls

        Args:
            query: Natural language query
            session_id: Optional session for context
            user_id: Optional user ID
            use_episodic: Include episodic memory
            use_semantic: Include semantic memory
            use_procedural: Include procedural memory
            memory_limit: Max memory items per layer
            min_relevance: Minimum relevance threshold
            context: Additional context

        Yields:
            Stream chunks with content and metadata
        """
        async for chunk_data in self._http.stream(
            "POST",
            "/v1/memory/query/stream",
            json_data={
                "query": query,
                "session_id": session_id,
            },
        ):
            yield StreamChunk.model_validate(chunk_data)

    async def reason(
        self,
        query: str,
        context: list[dict[str, Any]] | None = None,
        max_steps: int = 5,
    ) -> QueryResponse:
        """Execute multi-step reasoning query.

        Uses chain-of-thought reasoning with tool access.

        Args:
            query: Query to reason about
            context: Optional context items
            max_steps: Maximum reasoning steps

        Returns:
            Response with reasoning trace
        """
        data = await self._http.post(
            "/v1/cognitive/reason",
            json_data={
                "query": query,
                "context": context or [],
                "max_steps": max_steps,
            },
        )
        return QueryResponse.model_validate(data)

    async def plan(
        self,
        goal: str,
        constraints: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a plan to achieve a goal.

        Args:
            goal: Goal to achieve
            constraints: Optional constraints

        Returns:
            Plan with steps
        """
        data = await self._http.post(
            "/v1/cognitive/plan",
            json_data={
                "goal": goal,
                "constraints": constraints or [],
            },
        )
        return data
