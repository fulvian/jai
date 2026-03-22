"""Chat request and response models."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""

    message: str = Field(..., min_length=1, description="User message")
    session_id: str | None = Field(None, description="Session ID for context")
    use_memory: bool = Field(True, description="Enable memory layers")


class ChatChunk(BaseModel):
    """SSE chunk model for streaming responses."""

    type: Literal["content", "reasoning", "tool", "sources", "done", "error"]
    content: str | None = None
    tool_name: str | None = None
    tool_result: dict[str, Any] | None = None
    sources: list[dict[str, Any]] | None = None
    error: str | None = None


class Message(BaseModel):
    """Chat message model."""

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str | None = None
    sources: list[dict[str, Any]] | None = None
    tools_used: list[str] | None = None


class SessionInfo(BaseModel):
    """Session information model."""

    session_id: str
    created_at: str | None = None
    message_count: int = 0
    last_message: str | None = None
