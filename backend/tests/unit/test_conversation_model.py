# Phase 7: Conversation Model Tests
# Tests for conversation Pydantic models

from datetime import datetime

from me4brain.models.conversation import (
    Conversation,
    ConversationCreate,
    ConversationSummary,
    ConversationUpdate,
    Message,
    MessageRole,
)


class TestMessageRole:
    """Test MessageRole enum."""

    def test_user_role_value(self):
        """Test user role value."""
        assert MessageRole.USER.value == "user"

    def test_assistant_role_value(self):
        """Test assistant role value."""
        assert MessageRole.ASSISTANT.value == "assistant"

    def test_system_role_value(self):
        """Test system role value."""
        assert MessageRole.SYSTEM.value == "system"


class TestMessage:
    """Test Message model."""

    def test_message_creation(self):
        """Test creating a message."""
        msg = Message(
            id="msg_123",
            role=MessageRole.USER,
            content="Hello, world!",
        )
        assert msg.id == "msg_123"
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, world!"
        assert msg.timestamp is not None

    def test_message_with_metadata(self):
        """Test message with metadata."""
        msg = Message(
            id="msg_456",
            role=MessageRole.ASSISTANT,
            content="Response content",
            metadata={"model": "llama3", "tokens": "45"},
        )
        assert msg.metadata == {"model": "llama3", "tokens": "45"}

    def test_message_timestamp_default(self):
        """Test timestamp defaults to now."""
        before = datetime.utcnow()
        msg = Message(id="msg_789", role=MessageRole.USER, content="Test")
        after = datetime.utcnow()
        assert before <= msg.timestamp <= after


class TestConversation:
    """Test Conversation model."""

    def test_conversation_creation(self):
        """Test creating a conversation."""
        conv = Conversation(
            id="conv_123",
            user_id="user_abc",
            title="Test Conversation",
        )
        assert conv.id == "conv_123"
        assert conv.user_id == "user_abc"
        assert conv.title == "Test Conversation"
        assert conv.messages == []
        assert conv.archived is False

    def test_conversation_with_messages(self):
        """Test conversation with messages."""
        msg1 = Message(id="msg_1", role=MessageRole.USER, content="First")
        msg2 = Message(id="msg_2", role=MessageRole.ASSISTANT, content="Second")
        conv = Conversation(
            id="conv_456",
            user_id="user_abc",
            title="With Messages",
            messages=[msg1, msg2],
        )
        assert len(conv.messages) == 2

    def test_conversation_default_title(self):
        """Test default conversation title."""
        conv = Conversation(id="conv_789", user_id="user_abc")
        assert conv.title == "New Conversation"


class TestConversationSummary:
    """Test ConversationSummary model."""

    def test_summary_creation(self):
        """Test creating a conversation summary."""
        summary = ConversationSummary(
            id="conv_123",
            title="Test Summary",
            updated_at=datetime.utcnow(),
            message_count=10,
        )
        assert summary.id == "conv_123"
        assert summary.message_count == 10
        assert summary.archived is False


class TestConversationCreate:
    """Test ConversationCreate model."""

    def test_create_with_title(self):
        """Test creating with title."""
        create = ConversationCreate(title="My Conversation")
        assert create.title == "My Conversation"
        assert create.metadata is None

    def test_create_with_metadata(self):
        """Test creating with metadata."""
        create = ConversationCreate(
            title="With Meta",
            metadata={"source": "api"},
        )
        assert create.metadata == {"source": "api"}

    def test_create_default_title(self):
        """Test default title."""
        create = ConversationCreate()
        assert create.title == "New Conversation"


class TestConversationUpdate:
    """Test ConversationUpdate model."""

    def test_update_title(self):
        """Test updating title."""
        update = ConversationUpdate(title="New Title")
        assert update.title == "New Title"
        assert update.archived is None

    def test_update_archived(self):
        """Test updating archived status."""
        update = ConversationUpdate(archived=True)
        assert update.archived is True
        assert update.title is None

    def test_update_both(self):
        """Test updating both fields."""
        update = ConversationUpdate(title="T", archived=False)
        assert update.title == "T"
        assert update.archived is False
