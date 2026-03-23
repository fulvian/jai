"""
Conversation Routes - API endpoints for conversation management.

Provides REST endpoints for:
- Creating conversations
- Listing conversations
- Getting conversation details
- Adding messages
- Updating conversation metadata
- Archiving/deleting conversations
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from me4brain.database import get_session
from me4brain.engine.conversation_manager import ConversationManager
from me4brain.models.conversation import (
    Conversation,
    ConversationCreate,
    ConversationSummary,
    ConversationUpdate,
    Message,
    MessageCreate,
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v1/conversations", tags=["Conversations"])


# For now, use a placeholder user_id extraction
# In production, this would come from authentication middleware
async def get_current_user_id() -> str:
    """Placeholder for user authentication.

    Returns a default user ID. In production, extract from JWT/session.
    """
    return "default_user"


async def get_conversation_manager(
    session: AsyncSession = Depends(get_session),
) -> ConversationManager:
    """Dependency to get ConversationManager instance."""
    return ConversationManager(session)


# =============================================================================
# Conversation CRUD Endpoints
# =============================================================================


@router.post(
    "",
    response_model=Conversation,
    status_code=status.HTTP_201_CREATED,
    summary="Create new conversation",
    description="Create a new conversation for the authenticated user.",
)
async def create_conversation(
    conversation_data: ConversationCreate,
    user_id: str = Depends(get_current_user_id),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> Conversation:
    """Create a new conversation.

    Args:
        conversation_data: Conversation creation request
        user_id: Current user ID (from auth)
        manager: Conversation manager instance

    Returns:
        Created conversation
    """
    conversation = await manager.start_conversation(
        user_id=user_id,
        title=conversation_data.title,
        metadata=conversation_data.metadata,
    )
    logger.info("conversation_created", conversation_id=conversation.id, user_id=user_id)
    return conversation


@router.get(
    "",
    response_model=dict[str, list[ConversationSummary] | int],
    summary="List conversations",
    description="List conversations for the authenticated user.",
)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100, description="Max results to return"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    include_archived: bool = Query(default=False, description="Include archived conversations"),
    user_id: str = Depends(get_current_user_id),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> dict[str, list[ConversationSummary] | int]:
    """List conversations for the current user.

    Args:
        limit: Maximum number of results
        offset: Number of results to skip
        include_archived: Whether to include archived conversations
        user_id: Current user ID
        manager: Conversation manager instance

    Returns:
        Dict with 'conversations' list and 'total' count
    """
    conversations, total = await manager.list_conversations(
        user_id=user_id,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
    )
    return {
        "conversations": conversations,
        "total": total,
    }


@router.get(
    "/{conversation_id}",
    response_model=Conversation,
    summary="Get conversation",
    description="Get a conversation by ID with all messages.",
)
async def get_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> Conversation:
    """Get a conversation by ID.

    Args:
        conversation_id: ID of the conversation
        user_id: Current user ID
        manager: Conversation manager instance

    Returns:
        Conversation with messages

    Raises:
        HTTPException: If conversation not found
    """
    conversation = await manager.get_conversation(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )
    return conversation


@router.patch(
    "/{conversation_id}",
    response_model=Conversation,
    summary="Update conversation",
    description="Update a conversation's title or archived status.",
)
async def update_conversation(
    conversation_id: str,
    update_data: ConversationUpdate,
    user_id: str = Depends(get_current_user_id),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> Conversation:
    """Update a conversation.

    Args:
        conversation_id: ID of the conversation
        update_data: Fields to update
        user_id: Current user ID
        manager: Conversation manager instance

    Returns:
        Updated conversation

    Raises:
        HTTPException: If conversation not found
    """
    conversation = await manager._repository.update_conversation(
        conversation_id, update_data, user_id
    )
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )
    logger.info("conversation_updated", conversation_id=conversation_id)
    return conversation


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete conversation",
    description="Delete a conversation and all its messages.",
)
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> None:
    """Delete a conversation.

    Args:
        conversation_id: ID of the conversation
        user_id: Current user ID
        manager: Conversation manager instance

    Raises:
        HTTPException: If conversation not found
    """
    deleted = await manager.delete_conversation(conversation_id, user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )
    logger.info("conversation_deleted", conversation_id=conversation_id)


# =============================================================================
# Message Endpoints
# =============================================================================


@router.post(
    "/{conversation_id}/messages",
    response_model=Message,
    status_code=status.HTTP_201_CREATED,
    summary="Add message",
    description="Add a message to a conversation.",
)
async def add_message(
    conversation_id: str,
    message_data: MessageCreate,
    user_id: str = Depends(get_current_user_id),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> Message:
    """Add a message to a conversation.

    Args:
        conversation_id: ID of the conversation
        message_data: Message to add
        user_id: Current user ID
        manager: Conversation manager instance

    Returns:
        Created message

    Raises:
        HTTPException: If conversation not found
    """
    # Verify conversation exists and belongs to user
    conversation = await manager.get_conversation(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Add message
    message = await manager.add_user_message(
        conversation_id=conversation_id,
        content=message_data.content,
        metadata=message_data.metadata,
    )

    if message is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add message",
        )

    logger.info(
        "message_added",
        conversation_id=conversation_id,
        message_id=message.id,
        role=message_data.role,
    )
    return message


@router.get(
    "/{conversation_id}/messages",
    response_model=list[Message],
    summary="Get messages",
    description="Get messages from a conversation.",
)
async def get_messages(
    conversation_id: str,
    limit: int = Query(default=50, ge=1, le=500, description="Max messages to return"),
    offset: int = Query(default=0, ge=0, description="Number of messages to skip"),
    user_id: str = Depends(get_current_user_id),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> list[Message]:
    """Get messages for a conversation.

    Args:
        conversation_id: ID of the conversation
        limit: Maximum number of messages
        offset: Number of messages to skip
        user_id: Current user ID
        manager: Conversation manager instance

    Returns:
        List of messages

    Raises:
        HTTPException: If conversation not found
    """
    # Verify conversation exists
    conversation = await manager.get_conversation(conversation_id, user_id)
    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    messages = await manager.get_messages(conversation_id, limit=limit, offset=offset)
    return messages or []


@router.get(
    "/{conversation_id}/context",
    response_model=dict[str, str | int],
    summary="Get conversation context",
    description="Get formatted conversation context for LLM.",
)
async def get_conversation_context(
    conversation_id: str,
    max_tokens: int = Query(default=2000, ge=100, le=10000, description="Max context tokens"),
    user_id: str = Depends(get_current_user_id),
    manager: ConversationManager = Depends(get_conversation_manager),
) -> dict[str, str | int]:
    """Get formatted conversation context for LLM.

    Args:
        conversation_id: ID of the conversation
        max_tokens: Maximum context tokens
        user_id: Current user ID
        manager: Conversation manager instance

    Returns:
        Dict with context string and actual token count

    Raises:
        HTTPException: If conversation not found
    """
    context = await manager.get_context(conversation_id, max_tokens)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found",
        )

    # Approximate token count (chars / 4)
    approx_tokens = len(context) // 4

    return {
        "context": context,
        "approx_tokens": approx_tokens,
    }
