"""
Conversation Manager - High-level conversation management.

Provides a high-level interface for managing conversations,
handling context preparation, and integrating with the domain classifier.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from me4brain.database.conversation_repository import ConversationRepository
from me4brain.models.conversation import (
    Conversation,
    ConversationCreate,
    ConversationSummary,
    ConversationUpdate,
    Message,
    MessageCreate,
)


class LLMClientProtocol(Protocol):
    """Protocol for LLM client used in summarization."""

    async def generate(self, prompt: str) -> str:
        """Generate text from prompt."""
        ...


class DomainClassifierProtocol(Protocol):
    """Protocol for domain classifier callable."""

    async def __call__(self, query: str) -> Optional[str]:
        """Classify a query and return domain."""
        ...


class ConversationManager:
    """High-level manager for conversation operations.

    Provides a simplified interface for conversation management,
    handling context preparation for LLM calls and integrating
    with the domain classifier.
    """

    def __init__(
        self,
        session: AsyncSession,
        llm_client: Optional[LLMClientProtocol] = None,
    ):
        """Initialize conversation manager.

        Args:
            session: Database session
            llm_client: Optional LLM client for summarization
        """
        self._repository = ConversationRepository(session)
        self._llm_client = llm_client

    async def start_conversation(
        self,
        user_id: str,
        title: str = "New Conversation",
        metadata: Optional[dict[str, str]] = None,
    ) -> Conversation:
        """Create a new conversation.

        Args:
            user_id: ID of the user creating the conversation
            title: Optional title for the conversation
            metadata: Optional metadata

        Returns:
            Created conversation
        """
        create_data = ConversationCreate(
            title=title,
            metadata=metadata,
        )
        return await self._repository.create_conversation(user_id, create_data)

    async def add_user_message(
        self,
        conversation_id: str,
        content: str,
        metadata: Optional[dict[str, str]] = None,
    ) -> Optional[Message]:
        """Add a user message to a conversation.

        Args:
            conversation_id: ID of the conversation
            content: Message content
            metadata: Optional metadata (model used, etc.)

        Returns:
            Created message if successful, None if conversation not found
        """
        message_data = MessageCreate(
            content=content,
            role="user",
            metadata=metadata,
        )
        return await self._repository.add_message(conversation_id, message_data)

    async def add_assistant_message(
        self,
        conversation_id: str,
        content: str,
        metadata: Optional[dict[str, str]] = None,
    ) -> Optional[Message]:
        """Add an assistant message to a conversation.

        Args:
            conversation_id: ID of the conversation
            content: Message content
            metadata: Optional metadata

        Returns:
            Created message if successful, None if conversation not found
        """
        message_data = MessageCreate(
            content=content,
            role="assistant",
            metadata=metadata,
        )
        return await self._repository.add_message(conversation_id, message_data)

    async def get_context(
        self,
        conversation_id: str,
        max_tokens: int = 2000,
    ) -> Optional[str]:
        """Get conversation context for LLM.

        This prepares the conversation history in a format suitable
        for passing to the LLM, with smart truncation if needed.

        Args:
            conversation_id: ID of the conversation
            max_tokens: Approximate maximum tokens (default 2000)

        Returns:
            Formatted context string if conversation exists, None otherwise
        """
        return await self._repository.get_conversation_context(conversation_id, max_tokens)

    async def get_conversation(
        self,
        conversation_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Conversation]:
        """Get a conversation by ID.

        Args:
            conversation_id: ID of the conversation
            user_id: Optional user ID for authorization

        Returns:
            Conversation if found, None otherwise
        """
        return await self._repository.get_conversation(conversation_id, user_id)

    async def list_conversations(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
        include_archived: bool = False,
    ) -> tuple[list[ConversationSummary], int]:
        """List conversations for a user.

        Args:
            user_id: ID of the user
            limit: Maximum number of results
            offset: Number of results to skip
            include_archived: Whether to include archived conversations

        Returns:
            Tuple of (conversations list, total count)
        """
        result = await self._repository.list_conversations(
            user_id,
            limit=limit,
            offset=offset,
            include_archived=include_archived,
        )
        # Convert Sequence to list for consistent return type
        return list(result[0]), result[1]

    async def update_title(
        self,
        conversation_id: str,
        title: str,
        user_id: Optional[str] = None,
    ) -> Optional[Conversation]:
        """Update a conversation's title.

        Args:
            conversation_id: ID of the conversation
            title: New title
            user_id: Optional user ID for authorization

        Returns:
            Updated conversation if successful, None if not found
        """
        update_data = ConversationUpdate(title=title)
        return await self._repository.update_conversation(conversation_id, update_data, user_id)

    async def archive_conversation(
        self,
        conversation_id: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """Archive a conversation.

        Args:
            conversation_id: ID of the conversation
            user_id: Optional user ID for authorization

        Returns:
            True if successful, False if not found
        """
        return await self._repository.archive_conversation(conversation_id, user_id)

    async def delete_conversation(
        self,
        conversation_id: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """Delete a conversation.

        Args:
            conversation_id: ID of the conversation
            user_id: Optional user ID for authorization

        Returns:
            True if deleted, False if not found
        """
        return await self._repository.delete_conversation(conversation_id, user_id)

    async def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> Optional[list[Message]]:
        """Get messages for a conversation.

        Args:
            conversation_id: ID of the conversation
            limit: Maximum number of messages
            offset: Number of messages to skip

        Returns:
            List of messages if conversation exists, None otherwise
        """
        messages = await self._repository.get_messages(conversation_id, limit=limit, offset=offset)
        return list(messages) if messages is not None else None

    async def classify_with_context(
        self,
        conversation_id: str,
        query: str,
        domain_classifier: Optional[DomainClassifierProtocol] = None,
        max_context_tokens: int = 1500,
    ) -> tuple[Optional[str], Optional[str]]:
        """Classify a query using conversation context.

        If a conversation_id is provided, enriches the query with
        conversation context before classification.

        Args:
            conversation_id: ID of the conversation (optional)
            query: User query to classify
            domain_classifier: Classifier function that takes (query, context) and returns domain
            max_context_tokens: Maximum context tokens for enrichment

        Returns:
            Tuple of (enriched_query, classified_domain) if successful,
            (query, None) if no context, (None, None) if error
        """
        context = None
        if conversation_id:
            context = await self.get_context(conversation_id, max_context_tokens)

        if context:
            enriched_query = f"{context}\n\nCurrent query: {query}"
        else:
            enriched_query = query

        if domain_classifier is not None:
            try:
                domain = await domain_classifier(enriched_query)
                return enriched_query, domain
            except Exception:
                return enriched_query, None

        return enriched_query, None


# Singleton instance
_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager(
    session: AsyncSession,
    llm_client: Optional[LLMClientProtocol] = None,
) -> ConversationManager:
    """Get a ConversationManager instance.

    Args:
        session: Database session
        llm_client: Optional LLM client

    Returns:
        ConversationManager instance
    """
    global _conversation_manager
    _conversation_manager = ConversationManager(session, llm_client)
    return _conversation_manager
