"""
Chat Completions Route - Multi-turn conversation endpoint.

Integrates conversation memory with the domain classifier for
multi-turn capable chat completions following OpenAI API style.
"""

from __future__ import annotations

from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from me4brain.database import get_session
from me4brain.engine.conversation_manager import ConversationManager

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/chat", tags=["Chat"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ChatMessage(BaseModel):
    """Chat message in a request."""

    role: Literal["user", "assistant", "system"]
    content: str
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    """Request model for chat completions."""

    conversation_id: str | None = Field(
        default=None,
        description="Existing conversation ID. If not provided, a new conversation is created.",
    )
    messages: list[ChatMessage] = Field(
        ...,
        description="List of messages in the conversation",
    )
    model: str | None = Field(
        default=None,
        description="Model to use. If not provided, auto-selected.",
    )
    max_tokens: int = Field(
        default=2000,
        ge=100,
        le=32000,
        description="Maximum tokens in the response",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "conversation_id": "conv_123",
                    "messages": [
                        {"role": "user", "content": "Help me with Python"},
                    ],
                    "model": "llama3",
                }
            ]
        }
    }


class ChatCompletionChoice(BaseModel):
    """A single completion choice."""

    index: int
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    """Response model for chat completions."""

    id: str
    object: str = "chat.completion"
    created: int  # Unix timestamp
    model: str
    choices: list[ChatCompletionChoice]
    conversation_id: str | None = None
    classification: dict[str, Any] | None = None


# =============================================================================
# Route Handlers
# =============================================================================


@router.post(
    "/completions",
    response_model=ChatCompletionResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat completions",
    description="Multi-turn chat completion with conversation memory.",
)
async def create_chat_completion(
    request: ChatCompletionRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatCompletionResponse:
    """Create a chat completion with multi-turn support.

    This endpoint:
    1. Uses existing conversation context if conversation_id provided
    2. Enriches the query with conversation context
    3. Classifies the enriched query using domain classifier
    4. Returns the response with conversation_id for follow-up

    Args:
        request: Chat completion request
        session: Database session

    Returns:
        Chat completion response with conversation_id
    """
    import time

    manager = ConversationManager(session)

    # Get or create conversation
    conversation_id = request.conversation_id
    if conversation_id is None:
        # Create new conversation using first user message
        first_user_msg = next((m for m in request.messages if m.role == "user"), None)
        title = "New Conversation"
        if first_user_msg:
            # Use first 50 chars of first message as title
            title = first_user_msg.content[:50] + (
                "..." if len(first_user_msg.content) > 50 else ""
            )

        conv = await manager.start_conversation(
            user_id="default_user",
            title=title,
        )
        conversation_id = conv.id
    else:
        # Verify conversation exists
        existing = await manager.get_conversation(conversation_id, "default_user")
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {conversation_id} not found",
            )

    # Get conversation context for enrichment
    context = await manager.get_context(conversation_id, max_tokens=1500)

    # Get the latest user message
    latest_user_message = None
    for msg in reversed(request.messages):
        if msg.role == "user":
            latest_user_message = msg.content
            break

    if latest_user_message is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No user message found in request",
        )

    # Enrich query with context if available
    if context:
        enriched_query = f"{context}\n\nCurrent query: {latest_user_message}"
    else:
        enriched_query = latest_user_message

    # Save user message to conversation
    await manager.add_user_message(
        conversation_id=conversation_id,
        content=latest_user_message,
    )

    # TODO: Integrate with domain classifier for actual classification
    # For now, simulate a response and classification
    classification_result = {
        "domain": "general",
        "confidence": 0.8,
        "method": "multi_turn",
        "query": enriched_query,
    }

    # TODO: Actually call LLM and get response
    # For now, return a placeholder response
    assistant_content = f"Echo: {latest_user_message}"

    # Save assistant response to conversation
    await manager.add_assistant_message(
        conversation_id=conversation_id,
        content=assistant_content,
    )

    # Build response
    response = ChatCompletionResponse(
        id=f"chatcmpl_{int(time.time())}",
        created=int(time.time()),
        model=request.model or "auto",
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(
                    role="assistant",
                    content=assistant_content,
                ),
                finish_reason="stop",
            )
        ],
        conversation_id=conversation_id,
        classification=classification_result,
    )

    logger.info(
        "chat_completion_created",
        conversation_id=conversation_id,
        message_count=len(request.messages),
    )

    return response


@router.get(
    "/{conversation_id}/history",
    response_model=dict[str, Any],
    summary="Get chat history",
    description="Get the full chat history for a conversation.",
)
async def get_chat_history(
    conversation_id: str,
    user_id: str = Query(default="default_user"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get full chat history for a conversation.

    Args:
        conversation_id: ID of the conversation
        user_id: Current user ID (from query param)
        session: Database session

    Returns:
        Conversation with messages formatted as chat history
    """

    manager = ConversationManager(session)

    conversation = await manager.get_conversation(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Format messages as chat history
    messages = [
        {
            "role": msg.role.value,
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
        }
        for msg in conversation.messages
    ]

    return {
        "id": conversation.id,
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
        "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
        "messages": messages,
        "message_count": len(messages),
    }
