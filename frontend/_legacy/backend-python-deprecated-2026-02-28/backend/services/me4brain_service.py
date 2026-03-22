"""Me4BrAIn SDK Service - Tool Calling Engine Integration.

Wrapper per la nuova SDK con Il Tool Calling Engine.
Sessioni persistenti via API Working Memory di Me4Brain.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import httpx
from me4brain_sdk import AsyncMe4BrAInClient, EngineQueryResponse, ToolInfo

from backend.config import settings

import structlog

logger = structlog.get_logger(__name__)


class Me4BrAInService:
    """
    Service wrapper for Me4BrAIn Tool Calling Engine.

    Provides methods for:
    - Natural language queries (engine.query)
    - Direct tool calls (engine.call)
    - Tool listing and stats (engine.list_tools, engine.stats)
    - Local session management (in-memory per semplicità)
    """

    def __init__(self):
        """Initialize service with settings."""
        self.base_url = settings.me4brain_url
        self.api_key = settings.me4brain_api_key
        self._client: Me4BrAInClient | None = None
        self._http_client: httpx.AsyncClient | None = None

        # In-memory fallback (usato solo se Me4Brain non disponibile)
        self._sessions: dict[str, dict[str, Any]] = {}
        self._use_me4brain_sessions = True  # Usa API Working Memory

        # Local cache for custom session titles (persisted to JSON file)
        self._titles_cache_file = Path("data/session_titles.json")
        self._custom_titles: dict[str, str] = self._load_titles_cache()

    def _load_titles_cache(self) -> dict[str, str]:
        """Load custom titles from JSON file."""
        try:
            if self._titles_cache_file.exists():
                data = json.loads(self._titles_cache_file.read_text())
                logger.info("titles_cache_loaded", count=len(data), titles=list(data.keys()))
                return data
            else:
                logger.info("titles_cache_file_not_found", path=str(self._titles_cache_file))
        except Exception as e:
            logger.warning("titles_cache_load_failed", error=str(e))
        return {}

    def _save_titles_cache(self) -> None:
        """Save custom titles to JSON file."""
        try:
            self._titles_cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._titles_cache_file.write_text(json.dumps(self._custom_titles, indent=2))
        except Exception as e:
            logger.warning("titles_cache_save_failed", error=str(e))

    async def _get_client(self) -> AsyncMe4BrAInClient:
        """Get or create Me4BrAIn client."""
        if self._client is None:
            self._client = AsyncMe4BrAInClient(
                base_url=self.base_url,
                api_key=self.api_key if self.api_key else None,
                timeout=settings.me4brain_timeout,  # Use config timeout (240s)
            )
        return self._client

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client for Working Memory API."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )
        return self._http_client

    async def close(self):
        """Close the client connections."""
        if self._client:
            await self._client.close()
            self._client = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    # === Health Check ===

    async def check_health(self) -> dict[str, Any]:
        """Check Me4BrAIn service health."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                response = await http_client.get(f"{self.base_url}/health")
                if response.status_code == 200:
                    return {"status": "connected", "url": self.base_url}
                return {
                    "status": "error",
                    "code": response.status_code,
                    "url": self.base_url,
                }
        except httpx.ConnectError:
            return {
                "status": "disconnected",
                "error": "Connection refused",
                "url": self.base_url,
            }
        except httpx.TimeoutException:
            return {
                "status": "timeout",
                "error": "Request timed out",
                "url": self.base_url,
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "url": self.base_url}

    def _extract_entities(self, messages: list[dict[str, Any]]) -> list[str]:
        """Extract key entities from conversation for context enrichment.

        Extracts:
        - Proper names (capitalized words)
        - Dates and times
        - Crypto/stock tickers
        - Email addresses
        - Tool mentions

        Returns:
            List of unique entities found
        """
        import re

        entities = set()
        text = " ".join(m.get("content", "") for m in messages)

        # Email addresses
        emails = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", text)
        entities.update(emails[:3])

        # Crypto tickers (BTC, ETH, SOL, etc.)
        crypto_tickers = re.findall(
            r"\b(BTC|ETH|SOL|XRP|ADA|DOGE|MATIC|LINK|DOT|AVAX)\b", text.upper()
        )
        entities.update(crypto_tickers[:5])

        # Stock tickers ($AAPL, $MSFT, etc.)
        stock_tickers = re.findall(r"\$([A-Z]{1,5})\b", text.upper())
        entities.update(f"${t}" for t in stock_tickers[:5])

        # Dates (YYYY-MM-DD, DD/MM/YYYY, etc.)
        dates = re.findall(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b", text)
        entities.update(dates[:3])

        # Tool mentions (underscored names like gmail_search, drive_list)
        tool_mentions = re.findall(r"\b([a-z]+_[a-z_]+)\b", text.lower())
        # Filter common tool-like patterns
        tool_mentions = [t for t in tool_mentions if len(t) > 5 and len(t) < 30]
        entities.update(tool_mentions[:5])

        # Proper names (capitalized words, 2+ chars, not at sentence start)
        proper_names = re.findall(r"(?<=[a-z]\s)([A-Z][a-z]{2,15})\b", text)
        entities.update(proper_names[:5])

        # Domain-specific: flight numbers, IATA codes
        flight_codes = re.findall(r"\b([A-Z]{2,3}\d{3,4})\b", text)
        entities.update(flight_codes[:3])

        # IATA airport codes
        iata_codes = re.findall(
            r"\b(FCO|JFK|LAX|LHR|CDG|AMS|FRA|MXP|BCN|MAD|ORD|DFW|ATL|DEN|SFO|SEA|MIA|BOS|EWR|DCA)\b",
            text.upper(),
        )
        entities.update(iata_codes[:3])

        return list(entities)

    # === Tool Calling Engine ===

    async def query(
        self,
        query: str,
        session_id: str | None = None,
        include_raw_results: bool = False,
        timeout_seconds: float | None = None,
    ) -> EngineQueryResponse:
        """
        Execute a natural language query through the Tool Calling Engine.

        Args:
            query: Natural language query
            session_id: Session ID for conversation context
            include_raw_results: Include raw tool JSON in response
            timeout_seconds: Query timeout

        Returns:
            EngineQueryResponse with answer, tools_called, latency
        """
        # Recupera contesto conversazione se session_id fornito
        # Best practice 2026: 60-70% context budget per history = 5 user + 3 assistant
        conversation_context = None
        if session_id:
            try:
                context = await self.get_session_context(session_id, max_turns=15)
                messages = context.get("messages", [])

                # Separa messaggi per ruolo
                user_messages = [m for m in messages if m.get("role") == "user"]
                assistant_messages = [m for m in messages if m.get("role") == "assistant"]

                # Estrai entità chiave per entity tracking (nomi, date, tool mentions)
                entities = self._extract_entities(messages)

                # Costruisci context: ultimi 5 user + 3 assistant
                context_parts = []

                # Entity summary se presente
                if entities:
                    context_parts.append(f"[ENTITIES: {', '.join(entities[:10])}]")

                # User messages (ultimi 5, max 500 chars ciascuno)
                if user_messages:
                    for m in user_messages[-5:]:
                        content = m.get("content", "")[:500]
                        context_parts.append(f"[USER]: {content}")

                # Assistant messages (ultimi 3, max 3000 chars ciascuno)
                if assistant_messages:
                    for m in assistant_messages[-3:]:
                        content = m.get("content", "")[:3000]
                        context_parts.append(f"[ASSISTANT]: {content}")

                if context_parts:
                    conversation_context = "\n---\n".join(context_parts)

            except Exception as e:
                # Non bloccare query se fallisce recupero contesto
                print(f"Warning: failed to get session context: {e}")

        client = await self._get_client()
        return await client.engine.query(
            query=query,
            conversation_context=conversation_context,
            include_raw_results=include_raw_results,
            timeout_seconds=timeout_seconds or settings.me4brain_timeout,
        )

    async def query_stream(
        self,
        query: str,
        session_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Relay Me4BrAIn Tool Calling Engine streaming in real-time.

        This is a thin proxy that streams events from Me4BrAIn's native
        SSE implementation directly to the frontend:
        - thinking: LLM reasoning steps
        - plan: tool selection
        - step_start/step_complete: tool execution
        - content: token-by-token LLM output
        - done: stream completion

        TTFT: < 200ms (first thinking event in ~50-100ms)
        """
        client = await self._get_client()

        async for event in client.engine.query_stream(
            query=query,
            session_id=session_id,
        ):
            yield event

    async def call_tool(
        self,
        tool_name: str,
        **arguments: Any,
    ) -> Any:
        """
        Call a tool directly by name.

        Args:
            tool_name: Name of the tool
            **arguments: Tool arguments

        Returns:
            Tool result
        """
        client = await self._get_client()
        return await client.engine.call(tool_name, **arguments)

    async def list_tools(
        self,
        domain: str | None = None,
        category: str | None = None,
        search: str | None = None,
    ) -> list[ToolInfo]:
        """
        List available tools with optional filters.

        Args:
            domain: Filter by domain
            category: Filter by category
            search: Search in name/description

        Returns:
            List of ToolInfo
        """
        client = await self._get_client()
        return await client.engine.list_tools(
            domain=domain,
            category=category,
            search=search,
        )

    async def get_tool(self, tool_name: str) -> ToolInfo:
        """Get details of a specific tool."""
        client = await self._get_client()
        return await client.engine.get_tool(tool_name)

    async def get_stats(self) -> dict[str, Any]:
        """Get catalog statistics."""
        client = await self._get_client()
        stats = await client.engine.stats()
        return {
            "total_tools": stats.total_tools,
            "domains": [
                {
                    "domain": d.domain,
                    "tool_count": d.tool_count,
                    "tools": d.tools,
                }
                for d in stats.domains
            ],
        }

    # === Session Management (via Me4Brain Working Memory API) ===

    async def create_session(self, user_id: str = "default") -> dict[str, Any]:
        """Create a new chat session via Me4Brain Working Memory."""
        if self._use_me4brain_sessions:
            try:
                http = await self._get_http_client()
                response = await http.post(
                    "/v1/working/sessions",
                    json={"user_id": user_id, "metadata": {}},
                )
                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        "session_created_via_me4brain",
                        session_id=data.get("session_id"),
                    )
                    return {
                        "session_id": data.get("session_id"),
                        "user_id": data.get("user_id", user_id),
                    }
            except Exception as e:
                logger.warning("me4brain_session_create_failed_fallback", error=str(e))

        # Fallback: in-memory
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = {
            "id": session_id,
            "user_id": user_id,
            "created_at": datetime.now(UTC).isoformat(),
            "turns": [],
        }
        return {"session_id": session_id, "user_id": user_id}

    async def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str = "default",
    ) -> None:
        """Add a conversation turn to session via Me4Brain."""
        # Map roles per API Me4Brain
        api_role = role if role in ("user", "assistant", "system", "tool") else "user"

        if self._use_me4brain_sessions:
            try:
                http = await self._get_http_client()
                response = await http.post(
                    f"/v1/working/sessions/{session_id}/messages",
                    params={"user_id": user_id},
                    json={"role": api_role, "content": content, "metadata": {}},
                )
                if response.status_code == 200:
                    logger.debug("turn_added_via_me4brain", session_id=session_id, role=role)
                    return
            except Exception as e:
                logger.warning("me4brain_add_turn_failed_fallback", error=str(e))

        # Fallback: in-memory
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "id": session_id,
                "user_id": user_id,
                "created_at": datetime.now(UTC).isoformat(),
                "turns": [],
            }

        self._sessions[session_id]["turns"].append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    async def get_session_context(
        self,
        session_id: str,
        max_turns: int = 20,
    ) -> dict[str, Any]:
        """Get session context (recent turns) from Me4Brain."""
        if self._use_me4brain_sessions:
            try:
                http = await self._get_http_client()
                response = await http.get(
                    f"/v1/working/sessions/{session_id}/messages",
                    params={"user_id": "default", "count": max_turns},
                )
                if response.status_code == 200:
                    data = response.json()
                    # Map to expected format
                    turns = [
                        {
                            "role": m.get("role"),
                            "content": m.get("content"),
                            "timestamp": m.get("timestamp"),
                        }
                        for m in data.get("messages", [])
                    ]
                    return {"session_id": session_id, "turns": turns}
            except Exception as e:
                logger.warning("me4brain_get_context_failed_fallback", error=str(e))

        # Fallback: in-memory
        if session_id not in self._sessions:
            return {"turns": [], "session_id": session_id}

        session = self._sessions[session_id]
        return {
            "session_id": session_id,
            "turns": session["turns"][-max_turns:],
        }

    async def list_sessions(
        self,
        user_id: str = "default",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List user sessions via Me4Brain Working Memory API with auto-generated titles."""
        if self._use_me4brain_sessions:
            try:
                http = await self._get_http_client()
                response = await http.get(
                    "/v1/working/sessions",
                    params={"user_id": user_id, "limit": limit},
                )
                if response.status_code == 200:
                    data = response.json()
                    sessions = data.get("sessions", [])
                    logger.info("sessions_listed_via_me4brain", count=len(sessions))

                    # Enrich sessions with titles
                    enriched_sessions = []
                    for s in sessions:
                        session_id = s.get("session_id") or s.get("id")

                        # Priority 1: Custom title from local cache
                        title = self._custom_titles.get(session_id)
                        if title:
                            logger.debug("custom_title_found", session_id=session_id, title=title)
                        else:
                            logger.debug(
                                "no_custom_title",
                                session_id=session_id,
                                cache_keys=list(self._custom_titles.keys()),
                            )

                        # Priority 2: Title from Me4Brain metadata
                        if not title:
                            title = s.get("metadata", {}).get("title")

                        # Priority 3: Extract from first user message
                        if not title:
                            title = await self._extract_session_title(session_id, http)

                        enriched_sessions.append(
                            {
                                "session_id": session_id,
                                "created_at": s.get("created_at"),
                                "updated_at": s.get("updated_at"),
                                "message_count": s.get("message_count", 0),
                                "title": title or "Nuova conversazione",
                            }
                        )

                    return enriched_sessions
            except Exception as e:
                logger.warning("me4brain_list_sessions_failed_fallback", error=str(e))

        # Fallback: in-memory with title extraction
        user_sessions = []
        for s in self._sessions.values():
            if s["user_id"] == user_id:
                # Extract title from first user message
                title = "Nuova conversazione"
                for turn in s.get("turns", []):
                    if turn.get("role") == "user":
                        title = self._truncate_title(turn.get("content", ""))
                        break
                user_sessions.append(
                    {
                        "session_id": s["id"],
                        "created_at": s["created_at"],
                        "message_count": len(s["turns"]),
                        "title": title,
                    }
                )
        return user_sessions[:limit]

    async def _extract_session_title(self, session_id: str, http) -> str | None:
        """Extract title from first user message of a session."""
        try:
            response = await http.get(f"/v1/working/sessions/{session_id}")
            if response.status_code == 200:
                data = response.json()
                messages = data.get("messages", [])
                # Find first user message
                for msg in messages:
                    if msg.get("role") == "user":
                        return self._truncate_title(msg.get("content", ""))
        except Exception as e:
            logger.debug("title_extraction_failed", session_id=session_id, error=str(e))
        return None

    def _truncate_title(self, content: str, max_length: int = 50) -> str:
        """Truncate content to create a readable title."""
        # Clean whitespace and newlines
        title = " ".join(content.split())
        if len(title) > max_length:
            return title[: max_length - 3] + "..."
        return title

    async def delete_session(self, session_id: str, user_id: str = "default") -> bool:
        """Delete a session via Me4Brain Working Memory API."""
        if self._use_me4brain_sessions:
            try:
                http = await self._get_http_client()
                response = await http.delete(
                    f"/v1/working/sessions/{session_id}",
                    params={"user_id": user_id},
                )
                if response.status_code in (200, 204):
                    logger.info("session_deleted_via_me4brain", session_id=session_id)
                    # Also remove custom title from cache
                    if session_id in self._custom_titles:
                        del self._custom_titles[session_id]
                        self._save_titles_cache()
                    return True
            except Exception as e:
                logger.warning("me4brain_delete_session_failed", error=str(e))

        # Fallback: in-memory
        if session_id in self._sessions:
            del self._sessions[session_id]
            # Also remove custom title from cache
            if session_id in self._custom_titles:
                del self._custom_titles[session_id]
                self._save_titles_cache()
            return True
        return False

    async def update_session_title(
        self,
        session_id: str,
        title: str,
        user_id: str = "default",
    ) -> bool:
        """Update session title via Me4Brain PATCH endpoint or local cache fallback."""
        if self._use_me4brain_sessions:
            try:
                http = await self._get_http_client()
                response = await http.patch(
                    f"/v1/working/sessions/{session_id}",
                    params={"user_id": user_id},
                    json={"title": title},
                )
                if response.status_code == 200:
                    logger.info(
                        "session_title_updated_via_me4brain",
                        session_id=session_id,
                        title=title,
                    )
                    # Also update local cache for consistency
                    self._custom_titles[session_id] = title
                    self._save_titles_cache()
                    return True
            except Exception as e:
                logger.warning("me4brain_update_title_failed_fallback", error=str(e))

        # Fallback: local cache (for older Me4Brain versions)
        self._custom_titles[session_id] = title
        self._save_titles_cache()

        logger.info(
            "session_title_updated_locally",
            session_id=session_id,
            title=title,
        )
        return True

    # === Episodic Memory (Auto-Learning) ===

    async def store_episode(
        self,
        content: str,
        episode_type: str = "conversation",
        entities: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        user_id: str = "default",
    ) -> dict[str, Any]:
        """Store an episode in Me4Brain's episodic memory for auto-learning.

        Args:
            content: Text content of the episode (summary)
            episode_type: Type of episode (conversation, preference, fact)
            entities: List of entity names mentioned
            metadata: Additional metadata
            user_id: User ID for the episode

        Returns:
            Episode storage result
        """
        try:
            http = await self._get_http_client()
            response = await http.post(
                "/v1/memory/episodes",
                json={
                    "content": content,
                    "episode_type": episode_type,
                    "entities": entities or [],
                    "events": [],
                    "metadata": metadata or {},
                },
            )
            if response.status_code in (200, 201):
                data = response.json()
                logger.info(
                    "episode_stored",
                    episode_id=data.get("episode_id"),
                    episode_type=episode_type,
                )
                return data
        except Exception as e:
            logger.warning("store_episode_failed", error=str(e))

        return {"success": False, "error": "Failed to store episode"}

    async def search_memory(
        self,
        query: str,
        limit: int = 10,
        user_id: str = "default",
    ) -> list[dict[str, Any]]:
        """Search Me4Brain's memory (episodic + semantic) for relevant information.

        Args:
            query: Search query
            limit: Max results to return
            user_id: User ID for context

        Returns:
            List of memory search results
        """
        try:
            http = await self._get_http_client()
            response = await http.post(
                "/v1/memory/search",
                json={
                    "query": query,
                    "limit": limit,
                },
            )
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                logger.info("memory_search_complete", count=len(results))
                return results
        except Exception as e:
            logger.warning("memory_search_failed", error=str(e))

        return []

    async def recall_user_context(
        self,
        user_id: str = "default",
        topics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Recall user preferences, facts, and relevant context from memory.

        Args:
            user_id: User ID
            topics: Optional list of topics to focus recall on

        Returns:
            User context with preferences and facts
        """
        context = {
            "preferences": [],
            "facts": [],
            "recent_topics": [],
        }

        # Search for user preferences
        if topics:
            for topic in topics[:3]:  # Limit to 3 topics
                results = await self.search_memory(
                    query=f"user preference {topic}",
                    limit=3,
                    user_id=user_id,
                )
                for r in results:
                    if r.get("score", 0) > 0.7:
                        context["preferences"].append(r.get("content", ""))

        # Get recent conversation topics
        session_context = await self.get_session_context(
            session_id=f"user-{user_id}",
            max_turns=5,
        )
        context["recent_topics"] = [
            t["content"][:100] for t in session_context.get("turns", []) if t.get("role") == "user"
        ]

        return context


# Singleton instance
_me4brain_service: Me4BrAInService | None = None


def get_me4brain_service() -> Me4BrAInService:
    """Get Me4BrAInService singleton."""
    global _me4brain_service
    if _me4brain_service is None:
        _me4brain_service = Me4BrAInService()
    return _me4brain_service
