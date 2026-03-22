from __future__ import annotations

"""Working Memory Namespace - Short-term session management."""

from typing import Any
from dataclasses import dataclass

from me4brain_sdk._http import HTTPClient
from me4brain_sdk.models.memory import Session, Turn


@dataclass
class SessionContext:
    """Session context with turns."""

    turns: list[Turn]
    session_id: str


class WorkingNamespace:
    """Working Memory operations - session context management.

    Working memory handles short-term context within a conversation session.
    It provides sliding window context, turn management, and session lifecycle.

    Example:
        # Create a new session
        session = await client.working.create_session(user_id="user-1")

        # Add conversation turns
        await client.working.add_turn(
            session_id=session.id,
            role="user",
            content="Hello, what's the weather?"
        )

        # Get session context
        context = await client.working.get_context(session.id)
    """

    def __init__(self, http: HTTPClient) -> None:
        self._http = http

    async def create_session(
        self,
        user_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Session:
        """Create a new working memory session.

        Args:
            user_id: User identifier
            metadata: Optional session metadata

        Returns:
            Created session
        """
        data = await self._http.post(
            "/v1/working/sessions",
            json_data={
                "user_id": user_id,
                "metadata": metadata or {},
            },
        )
        return Session.model_validate(data)

    async def get_session(self, session_id: str) -> Session:
        """Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session details with turns
        """
        data = await self._http.get(f"/v1/working/sessions/{session_id}")
        return Session.model_validate(data)

    async def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Turn:
        """Add a turn to the session.

        Args:
            session_id: Session identifier
            role: Turn role ("user", "assistant", "system", "tool")
            content: Turn content
            user_id: User identifier (required by backend)
            metadata: Optional turn metadata

        Returns:
            Created turn
        """
        url = f"/v1/working/sessions/{session_id}/messages"
        if user_id:
            url += f"?user_id={user_id}"

        data = await self._http.post(
            url,
            json_data={
                "role": role,
                "content": content,
                "metadata": metadata or {},
            },
        )
        # Return Turn from response or construct from input
        if isinstance(data, dict):
            if "role" in data:
                return Turn.model_validate(data)
            # If API just returns success, construct Turn
            return Turn(role=role, content=content, metadata=metadata or {})
        return Turn(role=role, content=content, metadata=metadata or {})

    async def get_context(
        self,
        session_id: str,
        max_turns: int = 10,
        max_tokens: int | None = None,
    ) -> "SessionContext":
        """Get recent messages from session for context.

        Args:
            session_id: Session identifier
            max_turns: Maximum messages to retrieve
            max_tokens: Optional token limit

        Returns:
            SessionContext with turns
        """
        # Get session which includes messages
        data = await self._http.get(f"/v1/working/sessions/{session_id}")

        # Parse messages from session
        messages = data.get("messages", [])
        turns = []
        for m in messages[-max_turns:]:
            try:
                turns.append(Turn.model_validate(m))
            except Exception:
                # Fallback if validation fails
                turns.append(
                    Turn(
                        role=m.get("role", "user"),
                        content=m.get("content", ""),
                    )
                )

        return SessionContext(turns=turns, session_id=session_id)

    async def update_context(
        self,
        session_id: str,
        context: dict[str, Any],
    ) -> Session:
        """Update session context/metadata.

        Args:
            session_id: Session identifier
            context: Context data to update

        Returns:
            Updated session
        """
        data = await self._http.put(
            f"/v1/working/sessions/{session_id}/context",
            json_data={"context": context},
        )
        return Session.model_validate(data)

    async def delete_session(self, session_id: str, user_id: str | None = None) -> bool:
        """Delete a session.

        Args:
            session_id: Session identifier
            user_id: User identifier (required by backend)

        Returns:
            True if deleted
        """
        url = f"/v1/working/sessions/{session_id}"
        if user_id:
            url += f"?user_id={user_id}"
        await self._http.delete(url)
        return True

    async def list_sessions(
        self,
        user_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Session]:
        """List sessions.

        Args:
            user_id: Filter by user
            limit: Max results
            offset: Pagination offset

        Returns:
            List of sessions
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if user_id:
            params["user_id"] = user_id

        data = await self._http.get("/v1/working/sessions", params=params)
        return [Session.model_validate(s) for s in data.get("sessions", [])]

    async def clear_turns(self, session_id: str) -> bool:
        """Clear all turns from a session.

        Args:
            session_id: Session identifier

        Returns:
            True if cleared
        """
        await self._http.delete(f"/v1/working/sessions/{session_id}/turns")
        return True
