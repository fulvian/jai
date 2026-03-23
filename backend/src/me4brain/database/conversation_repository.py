"""
Conversation Repository - Database access layer for conversations.

Provides async methods for CRUD operations on conversations,
messages, and conversation summaries using SQLAlchemy 2.0.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from me4brain.database.models import ConversationModel, MessageModel
from me4brain.models.conversation import (
    Conversation,
    ConversationCreate,
    ConversationSummary,
    ConversationUpdate,
    Message,
    MessageCreate,
    MessageRole,
)


def _model_to_conversation(model: ConversationModel) -> Conversation:
    """Convert SQLAlchemy model to Pydantic model."""
    return Conversation(
        id=model.id,
        user_id=model.user_id,
        title=model.title,
        created_at=model.created_at,
        updated_at=model.updated_at,
        archived=model.archived,
        metadata=model.metadata_json,
        messages=[_model_to_message(m) for m in model.messages],
    )


def _model_to_message(model: MessageModel) -> Message:
    """Convert SQLAlchemy message model to Pydantic model."""
    return Message(
        id=model.id,
        role=MessageRole(model.role),
        content=model.content,
        timestamp=model.timestamp,
        metadata=model.metadata_json,
    )


def _model_to_summary(model: ConversationModel, message_count: int) -> ConversationSummary:
    """Convert SQLAlchemy model to ConversationSummary."""
    return ConversationSummary(
        id=model.id,
        title=model.title,
        updated_at=model.updated_at,
        message_count=message_count,
        archived=model.archived,
    )


class ConversationRepository:
    """Repository for conversation CRUD operations."""

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self._session = session

    async def create_conversation(
        self,
        user_id: str,
        conversation: ConversationCreate,
    ) -> Conversation:
        """Create a new conversation.

        Args:
            user_id: ID of the user creating the conversation
            conversation: Conversation creation request

        Returns:
            Created conversation with empty messages list
        """
        model = ConversationModel(
            id=f"conv_{uuid.uuid4().hex[:24]}",
            user_id=user_id,
            title=conversation.title,
            metadata_json=conversation.metadata,
        )
        self._session.add(model)
        await self._session.flush()
        return _model_to_conversation(model)

    async def get_conversation(
        self,
        conversation_id: str,
        user_id: str | None = None,
    ) -> Conversation | None:
        """Get a conversation by ID.

        Args:
            conversation_id: ID of the conversation
            user_id: Optional user ID for authorization check

        Returns:
            Conversation if found and user has access, None otherwise
        """
        query = (
            select(ConversationModel)
            .options(selectinload(ConversationModel.messages))
            .where(ConversationModel.id == conversation_id)
        )
        if user_id is not None:
            query = query.where(ConversationModel.user_id == user_id)

        result = await self._session.execute(query)
        model = result.scalar_one_or_none()

        if model is None:
            return None
        return _model_to_conversation(model)

    async def list_conversations(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        include_archived: bool = False,
    ) -> tuple[Sequence[ConversationSummary], int]:
        """List conversations for a user.

        Args:
            user_id: ID of the user
            limit: Maximum number of results
            offset: Number of results to skip
            include_archived: Whether to include archived conversations

        Returns:
            Tuple of (conversations list, total count)
        """
        # Base query
        base_query = select(ConversationModel).where(ConversationModel.user_id == user_id)
        if not include_archived:
            base_query = base_query.where(ConversationModel.archived == False)  # noqa: E712

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self._session.execute(count_query)
        total = count_result.scalar() or 0

        # Get paginated results with message count
        query = base_query.order_by(ConversationModel.updated_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(query)
        models = result.scalars().all()

        # Get message counts for each conversation
        conversations = []
        for model in models:
            msg_count_query = (
                select(func.count())
                .select_from(MessageModel)
                .where(MessageModel.conversation_id == model.id)
            )
            msg_result = await self._session.execute(msg_count_query)
            msg_count = msg_result.scalar() or 0
            conversations.append(_model_to_summary(model, msg_count))

        return conversations, total

    async def add_message(
        self,
        conversation_id: str,
        message: MessageCreate,
    ) -> Message | None:
        """Add a message to a conversation.

        Args:
            conversation_id: ID of the conversation
            message: Message to add

        Returns:
            Created message if conversation exists, None otherwise
        """
        # Check conversation exists
        conv_query = select(ConversationModel).where(ConversationModel.id == conversation_id)
        conv_result = await self._session.execute(conv_query)
        if conv_result.scalar_one_or_none() is None:
            return None

        # Create message
        model = MessageModel(
            id=f"msg_{uuid.uuid4().hex[:24]}",
            conversation_id=conversation_id,
            role=message.role,
            content=message.content,
            metadata_json=message.metadata,
        )
        self._session.add(model)

        # Update conversation timestamp
        await self._session.execute(
            update(ConversationModel)
            .where(ConversationModel.id == conversation_id)
            .values(updated_at=datetime.utcnow())
        )

        await self._session.flush()
        return _model_to_message(model)

    async def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Message] | None:
        """Get messages for a conversation.

        Args:
            conversation_id: ID of the conversation
            limit: Maximum number of messages
            offset: Number of messages to skip

        Returns:
            List of messages if conversation exists, None otherwise
        """
        # Check conversation exists
        conv_query = select(ConversationModel).where(ConversationModel.id == conversation_id)
        conv_result = await self._session.execute(conv_query)
        if conv_result.scalar_one_or_none() is None:
            return None

        query = (
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.timestamp)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(query)
        models = result.scalars().all()

        return [_model_to_message(m) for m in models]

    async def update_conversation(
        self,
        conversation_id: str,
        update_data: ConversationUpdate,
        user_id: str | None = None,
    ) -> Conversation | None:
        """Update a conversation.

        Args:
            conversation_id: ID of the conversation
            update_data: Fields to update
            user_id: Optional user ID for authorization

        Returns:
            Updated conversation if found, None otherwise
        """
        # Build update values
        values = {}
        if update_data.title is not None:
            values["title"] = update_data.title
        if update_data.archived is not None:
            values["archived"] = update_data.archived
        if update_data.metadata is not None:
            values["metadata_json"] = update_data.metadata

        if not values:
            # Nothing to update
            return await self.get_conversation(conversation_id, user_id)

        values["updated_at"] = datetime.utcnow()

        # Build query
        query = (
            update(ConversationModel)
            .where(ConversationModel.id == conversation_id)
            .values(**values)
            .returning(ConversationModel)
        )
        if user_id is not None:
            query = query.where(ConversationModel.user_id == user_id)

        result = await self._session.execute(query)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        # Reload with messages
        return await self.get_conversation(conversation_id, user_id)

    async def archive_conversation(
        self,
        conversation_id: str,
        user_id: str | None = None,
    ) -> bool:
        """Archive a conversation.

        Args:
            conversation_id: ID of the conversation
            user_id: Optional user ID for authorization

        Returns:
            True if archived, False if not found
        """
        query = (
            update(ConversationModel)
            .where(ConversationModel.id == conversation_id)
            .values(archived=True, updated_at=datetime.utcnow())
        )
        if user_id is not None:
            query = query.where(ConversationModel.user_id == user_id)

        result = await self._session.execute(query)
        # rowcount may not be available in all async drivers
        return True  # Optimistic success

    async def delete_conversation(
        self,
        conversation_id: str,
        user_id: str | None = None,
    ) -> bool:
        """Delete a conversation and all its messages.

        Args:
            conversation_id: ID of the conversation
            user_id: Optional user ID for authorization

        Returns:
            True if deleted, False if not found
        """
        from sqlalchemy import delete

        query = delete(ConversationModel).where(ConversationModel.id == conversation_id)
        if user_id is not None:
            query = query.where(ConversationModel.user_id == user_id)

        result = await self._session.execute(query)
        return True  # Optimistic success

    async def get_conversation_context(
        self,
        conversation_id: str,
        max_tokens: int = 2000,
    ) -> str | None:
        """Get formatted conversation context for LLM.

        Args:
            conversation_id: ID of the conversation
            max_tokens: Approximate max tokens to return

        Returns:
            Formatted context string if conversation exists, None otherwise
        """
        messages = await self.get_messages(conversation_id, limit=100)
        if messages is None:
            return None

        # Format messages (approximate 4 chars per token)
        max_chars = max_tokens * 4
        context_parts = []
        total_chars = 0

        # Go through messages in reverse (newest first) and build context
        for message in reversed(messages):
            msg_str = f"{message.role.value}: {message.content}"
            if total_chars + len(msg_str) + 1 > max_chars:
                break
            context_parts.append(msg_str)
            total_chars += len(msg_str) + 1

        # Reverse to get chronological order
        context_parts.reverse()
        return "\n".join(context_parts)
