"""
Conversation Models - Pydantic models for conversation persistence.

Provides data models for:
- Message: Individual messages in a conversation
- Conversation: A conversation with multiple messages
- ConversationSummary: Lightweight summary for listing
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Role of a message sender."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(BaseModel):
    """Individual message in a conversation.

    Represents a single turn in a multi-turn conversation.
    """

    id: str = Field(..., description="Unique message identifier (UUID)")
    role: MessageRole = Field(..., description="Sender role (user/assistant/system)")
    content: str = Field(..., min_length=1, description="Message content")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the message was created",
    )
    metadata: Optional[dict[str, str]] = Field(
        default=None,
        description="Additional metadata (model used, tokens, etc.)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "msg_123e4567-e89b-12d3-a456-426614174000",
                    "role": "user",
                    "content": "Help me write a Python function",
                    "timestamp": "2026-03-22T10:30:00Z",
                    "metadata": {"model": "llama3", "tokens": "45"},
                }
            ]
        }
    }


class Conversation(BaseModel):
    """A conversation containing multiple messages.

    Represents a complete conversation thread with full message history.
    """

    id: str = Field(..., description="Unique conversation identifier (UUID)")
    user_id: str = Field(..., description="Owner of this conversation")
    title: str = Field(
        default="New Conversation",
        max_length=512,
        description="Conversation title/summary",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the conversation was created",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last time the conversation was modified",
    )
    messages: list[Message] = Field(
        default_factory=list,
        description="All messages in this conversation",
    )
    archived: bool = Field(
        default=False,
        description="Whether this conversation is archived",
    )
    metadata: Optional[dict[str, str]] = Field(
        default=None,
        description="Additional metadata (tags, labels, etc.)",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "conv_123e4567-e89b-12d3-a456-426614174000",
                    "user_id": "user_abc123",
                    "title": "Python Help Session",
                    "created_at": "2026-03-22T09:00:00Z",
                    "updated_at": "2026-03-22T10:45:00Z",
                    "messages": [],
                    "archived": False,
                    "metadata": {"source": "web_ui"},
                }
            ]
        }
    }


class ConversationSummary(BaseModel):
    """Lightweight conversation summary for listing.

    Used when listing conversations without full message history.
    """

    id: str = Field(..., description="Conversation ID")
    title: str = Field(..., description="Conversation title")
    updated_at: datetime = Field(..., description="Last update time")
    message_count: int = Field(..., ge=0, description="Number of messages")
    archived: bool = Field(default=False, description="Whether archived")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "conv_123e4567-e89b-12d3-a456-426614174000",
                    "title": "Python Help Session",
                    "updated_at": "2026-03-22T10:45:00Z",
                    "message_count": 12,
                    "archived": False,
                }
            ]
        }
    }


class ConversationCreate(BaseModel):
    """Request model for creating a new conversation."""

    title: str = Field(
        default="New Conversation",
        max_length=512,
        description="Initial conversation title",
    )
    metadata: Optional[dict[str, str]] = Field(
        default=None,
        description="Optional metadata",
    )


class MessageCreate(BaseModel):
    """Request model for adding a message to a conversation."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=100000,
        description="Message content",
    )
    role: Literal["user", "assistant", "system"] = Field(
        default="user",
        description="Message role",
    )
    metadata: Optional[dict[str, str]] = Field(
        default=None,
        description="Optional metadata",
    )


class ConversationUpdate(BaseModel):
    """Request model for updating a conversation."""

    title: Optional[str] = Field(
        default=None,
        max_length=512,
        description="New title (if provided)",
    )
    archived: Optional[bool] = Field(
        default=None,
        description="Archive status (if provided)",
    )
    metadata: Optional[dict[str, str]] = Field(
        default=None,
        description="Updated metadata (if provided)",
    )
