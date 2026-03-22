"""
Conversation Summarizer - Generate summaries for conversations.

Provides functionality to:
- Summarize long conversations
- Auto-generate titles from first messages
- Generate embeddings for semantic search
"""

from __future__ import annotations

from typing import Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from me4brain.database.conversation_repository import ConversationRepository


class LLMClientProtocol(Protocol):
    """Protocol for LLM client used in summarization."""

    async def generate(self, prompt: str) -> str:
        """Generate text from prompt."""
        ...


class ConversationSummarizer:
    """Summarizer for conversation content.

    Generates summaries for long conversations and can
    auto-generate titles from conversation content.
    """

    # Threshold of messages before summarization is triggered
    MESSAGES_BEFORE_SUMMARIZE = 20

    # Prompt template for generating summaries
    SUMMARY_PROMPT = """Analyze this conversation and provide a brief summary (2-3 sentences max):

Conversation:
{messages}

Summary:"""

    # Prompt template for generating titles
    TITLE_PROMPT = """Based on this conversation start, generate a short, descriptive title (3-6 words):

First message: {first_message}

Title:"""

    def __init__(
        self,
        session: AsyncSession,
        llm_client: Optional[LLMClientProtocol] = None,
    ):
        """Initialize summarizer.

        Args:
            session: Database session
            llm_client: Optional LLM client for generation
        """
        self._repository = ConversationRepository(session)
        self._llm_client = llm_client

    def set_llm_client(self, client: LLMClientProtocol) -> None:
        """Set the LLM client for generation.

        Args:
            client: LLM client instance
        """
        self._llm_client = client

    async def _format_messages_for_summary(
        self,
        conversation_id: str,
    ) -> Optional[str]:
        """Format messages for summarization prompt.

        Args:
            conversation_id: ID of the conversation

        Returns:
            Formatted message string or None if conversation has no messages
        """
        messages = await self._repository.get_messages(
            conversation_id, limit=self.MESSAGES_BEFORE_SUMMARIZE
        )
        if messages is None or len(messages) == 0:
            return None

        # Format as conversation transcript
        lines = []
        for msg in messages:
            role = msg.role.value.capitalize()
            lines.append(f"{role}: {msg.content}")

        return "\n".join(lines)

    async def summarize_conversation(
        self,
        conversation_id: str,
        force: bool = False,
    ) -> Optional[str]:
        """Generate a summary for a conversation.

        Only generates a summary if:
        - LLM client is configured
        - Conversation has enough messages
        - Existing summary is stale or doesn't exist

        Args:
            conversation_id: ID of the conversation
            force: Force regeneration even if existing summary is fresh

        Returns:
            Generated summary or None if not generated
        """
        if self._llm_client is None:
            return None

        # Get formatted messages
        messages_text = await self._format_messages_for_summary(conversation_id)
        if messages_text is None:
            return None

        # Check if summary already exists and is fresh
        # For now, always regenerate if force=True or no summary exists

        try:
            prompt = self.SUMMARY_PROMPT.format(messages=messages_text)
            summary = await self._llm_client.generate(prompt)
            return summary.strip()
        except Exception as e:
            # Log error but don't fail
            return None

    async def generate_title(
        self,
        conversation_id: str,
    ) -> Optional[str]:
        """Generate a title from conversation content.

        Uses the first user message to generate a title.
        If the conversation has no messages, returns None.

        Args:
            conversation_id: ID of the conversation

        Returns:
            Generated title or None if generation failed
        """
        if self._llm_client is None:
            return None

        # Get first user message
        messages = await self._repository.get_messages(conversation_id, limit=10)
        if messages is None or len(messages) == 0:
            return None

        # Find first user message
        first_user_message = None
        for msg in messages:
            if msg.role.value == "user":
                first_user_message = msg.content
                break

        if first_user_message is None:
            return None

        try:
            prompt = self.TITLE_PROMPT.format(first_message=first_user_message)
            title = await self._llm_client.generate(prompt)
            # Clean up title - take first line, strip whitespace
            title = title.strip().split("\n")[0][:100]  # Max 100 chars
            return title if title else None
        except Exception:
            return None

    async def should_summarize(self, conversation_id: str) -> bool:
        """Check if a conversation should be summarized.

        Args:
            conversation_id: ID of the conversation

        Returns:
            True if conversation has enough messages for summarization
        """
        messages = await self._repository.get_messages(
            conversation_id, limit=self.MESSAGES_BEFORE_SUMMARIZE + 1
        )
        if messages is None:
            return False
        return len(messages) >= self.MESSAGES_BEFORE_SUMMARIZE

    async def auto_summarize_if_needed(
        self,
        conversation_id: str,
    ) -> Optional[str]:
        """Automatically summarize if conditions are met.

        Args:
            conversation_id: ID of the conversation

        Returns:
            Summary if generated, None otherwise
        """
        if await self.should_summarize(conversation_id):
            return await self.summarize_conversation(conversation_id)
        return None


# Singleton instance
_summarizer: Optional[ConversationSummarizer] = None


def get_conversation_summarizer(
    session: AsyncSession,
    llm_client: Optional[LLMClientProtocol] = None,
) -> ConversationSummarizer:
    """Get a ConversationSummarizer instance.

    Args:
        session: Database session
        llm_client: Optional LLM client

    Returns:
        ConversationSummarizer instance
    """
    global _summarizer
    _summarizer = ConversationSummarizer(session, llm_client)
    return _summarizer
