from __future__ import annotations

"""Async Me4BrAIn Client - Main entry point for the SDK.

Usage:
    async with AsyncMe4BrAInClient(
        base_url="http://localhost:8100",
        api_key="your-api-key",
    ) as client:
        response = await client.cognitive.query("What did we discuss?")
"""

from typing import Any

from me4brain_sdk._http import HTTPClient
from me4brain_sdk.namespaces.working import WorkingNamespace
from me4brain_sdk.namespaces.episodic import EpisodicNamespace
from me4brain_sdk.namespaces.semantic import SemanticNamespace
from me4brain_sdk.namespaces.procedural import ProceduralNamespace
from me4brain_sdk.namespaces.cognitive import CognitiveNamespace
from me4brain_sdk.namespaces.tools import ToolsNamespace
from me4brain_sdk.namespaces.admin import AdminNamespace
from me4brain_sdk.namespaces.engine import EngineNamespace


class AsyncMe4BrAInClient:
    """Async client for Me4BrAIn Agentic Memory Platform.

    Provides access to all memory layers and cognitive capabilities:
    - working: Short-term session memory
    - episodic: Long-term autobiographical memory
    - semantic: Knowledge graph entities/relations
    - procedural: Skills and tool management
    - cognitive: Query interface with reasoning
    - tools: Tool search and execution
    - admin: Administration and backup

    Example:
        async with AsyncMe4BrAInClient(
            base_url="http://localhost:8100",
            api_key="your-key",
        ) as client:
            # Cognitive query
            response = await client.cognitive.query("Summarize recent meetings")

            # Memory search
            episodes = await client.episodic.search("project discussion")

            # Knowledge graph
            entities = await client.semantic.search("John Smith")
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
        """Initialize Me4BrAIn client.

        Args:
            base_url: Base URL of Me4BrAIn API (e.g., "http://localhost:8100")
            api_key: API key for authentication
            tenant_id: Default tenant ID for multi-tenancy
            user_id: Default user ID for user-scoped operations
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
            pool_connections: HTTP connection pool size
            pool_maxsize: Max connections per host
            extra_headers: Additional headers to include in all requests
        """
        self._http = HTTPClient(
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

        # Initialize namespaces
        self._working = WorkingNamespace(self._http)
        self._episodic = EpisodicNamespace(self._http)
        self._semantic = SemanticNamespace(self._http)
        self._procedural = ProceduralNamespace(self._http)
        self._cognitive = CognitiveNamespace(self._http)
        self._tools = ToolsNamespace(self._http)
        self._admin = AdminNamespace(self._http)
        self._engine = EngineNamespace(self._http)

    async def close(self) -> None:
        """Close the client and release resources."""
        await self._http.close()

    async def __aenter__(self) -> "AsyncMe4BrAInClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    # =========================================================================
    # Namespace Properties
    # =========================================================================

    @property
    def working(self) -> WorkingNamespace:
        """Working Memory - Short-term session context.

        Example:
            session = await client.working.create_session(user_id="user-1")
            await client.working.add_turn(session.id, role="user", content="Hello!")
        """
        return self._working

    @property
    def episodic(self) -> EpisodicNamespace:
        """Episodic Memory - Long-term autobiographical memories.

        Example:
            episodes = await client.episodic.search("meeting with John")
            await client.episodic.store(content="Had lunch with John at noon")
        """
        return self._episodic

    @property
    def semantic(self) -> SemanticNamespace:
        """Semantic Memory - Knowledge graph entities and relations.

        Example:
            entities = await client.semantic.search("Apple Inc")
            graph = await client.semantic.traverse("entity-123", max_depth=2)
        """
        return self._semantic

    @property
    def procedural(self) -> ProceduralNamespace:
        """Procedural Memory - Skills, tools, and learned patterns.

        Example:
            skills = await client.procedural.list_skills()
            tools = await client.procedural.search_tools("weather forecast")
        """
        return self._procedural

    @property
    def cognitive(self) -> CognitiveNamespace:
        """Cognitive Interface - Query with reasoning and memory integration.

        Example:
            response = await client.cognitive.query("What's our Q4 budget?")
            async for chunk in client.cognitive.query_stream("Summarize project"):
                print(chunk.content, end="")
        """
        return self._cognitive

    @property
    def tools(self) -> ToolsNamespace:
        """Tools - Search, execute, and manage tools.

        Example:
            results = await client.tools.search("calculator")
            execution = await client.tools.execute("calculator", {"expression": "2+2"})
        """
        return self._tools

    @property
    def admin(self) -> AdminNamespace:
        """Admin - Statistics, backup, and system management.

        Example:
            stats = await client.admin.stats()
            await client.admin.create_backup()
        """
        return self._admin

    @property
    def engine(self) -> EngineNamespace:
        """Engine - Tool Calling Engine for NL queries.

        Example:
            response = await client.engine.query(
                "Prezzo Bitcoin e meteo Roma",
                conversation_context="Previous response...",
            )
            print(response.answer)
        """
        return self._engine

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    async def health(self) -> dict[str, Any]:
        """Check API health status.

        Returns:
            Health status with service statuses
        """
        return await self._http.get("/health")

    async def query(
        self,
        query: str,
        session_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Shortcut for cognitive.query().

        Args:
            query: Natural language query
            session_id: Optional session for context
            **kwargs: Additional parameters

        Returns:
            QueryResponse with answer and metadata
        """
        return await self._cognitive.query(query, session_id=session_id, **kwargs)
