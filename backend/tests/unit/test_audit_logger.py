"""
Unit tests for Audit Logger module.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from me4brain.audit.audit_logger import AuditLogger, get_audit_logger
from me4brain.models.audit import AuditAction, AuditLogEntry, AuditStatus


class TestAuditLogEntry:
    """Test AuditLogEntry model."""

    def test_creation(self):
        """Test creating an audit log entry."""
        entry = AuditLogEntry(
            id="audit_123",
            action=AuditAction.USER_LOGIN,
            user_id="user_1",
        )
        assert entry.id == "audit_123"
        assert entry.action == AuditAction.USER_LOGIN
        assert entry.status == AuditStatus.SUCCESS

    def test_to_dict(self):
        """Test converting to dictionary."""
        entry = AuditLogEntry(
            id="audit_123",
            action=AuditAction.CONVERSATION_CREATED,
            user_id="user_1",
            resource_type="conversation",
            resource_id="conv_123",
        )
        result = entry.to_dict()
        assert result["id"] == "audit_123"
        assert result["action"] == "conversation.created"
        assert result["resource_type"] == "conversation"

    def test_from_dict(self):
        """Test creating from dictionary."""
        data = {
            "id": "audit_123",
            "action": "user.login",
            "status": "success",
            "user_id": "user_1",
            "timestamp": "2024-01-01T00:00:00",
        }
        entry = AuditLogEntry.from_dict(data)
        assert entry.id == "audit_123"
        assert entry.action == AuditAction.USER_LOGIN
        assert entry.status == AuditStatus.SUCCESS

    def test_from_dict_with_defaults(self):
        """Test from_dict handles missing optional fields."""
        data = {
            "id": "audit_123",
            "action": "user.login",
        }
        entry = AuditLogEntry.from_dict(data)
        assert entry.id == "audit_123"
        assert entry.status == AuditStatus.SUCCESS  # default

    def test_from_dict_missing_required(self):
        """Test from_dict raises on missing required fields."""
        data = {"id": "audit_123"}  # missing action
        with pytest.raises(ValueError, match="action is required"):
            AuditLogEntry.from_dict(data)


class TestAuditLogger:
    """Test AuditLogger class."""

    @pytest.fixture
    def logger(self):
        """Create a fresh audit logger."""
        return AuditLogger()

    def test_log_creates_entry(self, logger):
        """Test logging creates an audit entry."""
        entry = logger.log(
            action=AuditAction.USER_LOGIN,
            user_id="user_1",
        )
        assert entry.id is not None
        assert entry.action == AuditAction.USER_LOGIN
        assert entry.user_id == "user_1"
        assert entry.status == AuditStatus.SUCCESS

    def test_log_with_all_fields(self, logger):
        """Test logging with all fields."""
        entry = logger.log(
            action=AuditAction.API_KEY_CREATED,
            user_id="user_1",
            status=AuditStatus.SUCCESS,
            resource_type="api_key",
            resource_id="key_123",
            details={"name": "Test Key"},
            ip_address="192.168.1.1",
            user_agent="TestClient/1.0",
            request_id="req_123",
            session_id="session_456",
        )
        assert entry.resource_type == "api_key"
        assert entry.resource_id == "key_123"
        assert entry.ip_address == "192.168.1.1"
        assert entry.details == {"name": "Test Key"}

    def test_get_logs_no_filters(self, logger):
        """Test getting logs without filters."""
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_1")
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_2")
        logs = logger.get_logs()
        assert len(logs) == 2

    def test_get_logs_by_user(self, logger):
        """Test filtering logs by user."""
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_1")
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_2")
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_1")
        logs = logger.get_logs(user_id="user_1")
        assert len(logs) == 2

    def test_get_logs_by_action(self, logger):
        """Test filtering logs by action."""
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_1")
        logger.log(action=AuditAction.USER_LOGOUT, user_id="user_1")
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_2")
        logs = logger.get_logs(action=AuditAction.USER_LOGIN)
        assert len(logs) == 2

    def test_get_logs_by_resource(self, logger):
        """Test filtering logs by resource."""
        logger.log(
            action=AuditAction.CONVERSATION_ACCESSED,
            user_id="user_1",
            resource_type="conversation",
            resource_id="conv_1",
        )
        logger.log(
            action=AuditAction.CONVERSATION_ACCESSED,
            user_id="user_1",
            resource_type="conversation",
            resource_id="conv_2",
        )
        logs = logger.get_logs(resource_type="conversation", resource_id="conv_1")
        assert len(logs) == 1

    def test_get_logs_by_date_range(self, logger):
        """Test filtering logs by date range."""
        old_entry = AuditLogEntry(
            id="old",
            action=AuditAction.USER_LOGIN,
            timestamp=datetime.utcnow() - timedelta(days=2),
        )
        logger._logs.append(old_entry)

        recent_entry = logger.log(action=AuditAction.USER_LOGIN, user_id="user_1")

        start_date = datetime.utcnow() - timedelta(days=1)
        logs = logger.get_logs(start_date=start_date)
        assert len(logs) == 1
        assert logs[0].id == recent_entry.id

    def test_get_logs_respects_limit(self, logger):
        """Test getting logs respects limit."""
        for i in range(10):
            logger.log(action=AuditAction.USER_LOGIN, user_id=f"user_{i}")
        logs = logger.get_logs(limit=5)
        assert len(logs) == 5

    def test_get_user_logs(self, logger):
        """Test get_user_logs convenience method."""
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_1")
        logger.log(action=AuditAction.USER_LOGOUT, user_id="user_1")
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_2")
        logs = logger.get_user_logs("user_1")
        assert len(logs) == 2

    def test_get_resource_logs(self, logger):
        """Test get_resource_logs convenience method."""
        logger.log(
            action=AuditAction.CONVERSATION_ACCESSED,
            user_id="user_1",
            resource_type="conversation",
            resource_id="conv_123",
        )
        logs = logger.get_resource_logs("conversation", "conv_123")
        assert len(logs) == 1

    def test_export_logs(self, logger):
        """Test exporting logs as JSON."""
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_1")
        exported = logger.export_logs()
        assert '"action": "user.login"' in exported
        assert '"user_id": "user_1"' in exported

    def test_export_logs_with_user_filter(self, logger):
        """Test exporting logs with user filter."""
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_1")
        logger.log(action=AuditAction.USER_LOGIN, user_id="user_2")
        exported = logger.export_logs(user_id="user_1")
        assert "user_1" in exported
        assert "user_2" not in exported


class TestAuditLoggerConvenienceMethods:
    """Test audit logger convenience methods."""

    @pytest.fixture
    def logger(self):
        """Create a fresh audit logger."""
        return AuditLogger()

    def test_log_login_success(self, logger):
        """Test log_login with success."""
        entry = logger.log_login(user_id="user_1", ip_address="192.168.1.1")
        assert entry.action == AuditAction.USER_LOGIN
        assert entry.status == AuditStatus.SUCCESS

    def test_log_login_failure(self, logger):
        """Test log_login with failure."""
        entry = logger.log_login(
            user_id="user_1",
            success=False,
            error_message="Invalid password",
        )
        assert entry.action == AuditAction.USER_LOGIN_FAILED
        assert entry.status == AuditStatus.FAILURE
        assert entry.error_message == "Invalid password"

    def test_log_api_key_created(self, logger):
        """Test log_api_key_created."""
        entry = logger.log_api_key_created(
            user_id="user_1",
            key_id="key_123",
            ip_address="192.168.1.1",
        )
        assert entry.action == AuditAction.API_KEY_CREATED
        assert entry.resource_type == "api_key"
        assert entry.resource_id == "key_123"

    def test_log_api_key_revoked(self, logger):
        """Test log_api_key_revoked."""
        entry = logger.log_api_key_revoked(
            user_id="user_1",
            key_id="key_123",
        )
        assert entry.action == AuditAction.API_KEY_REVOKED

    def test_log_conversation_accessed(self, logger):
        """Test log_conversation_accessed."""
        entry = logger.log_conversation_accessed(
            user_id="user_1",
            conversation_id="conv_123",
        )
        assert entry.action == AuditAction.CONVERSATION_ACCESSED
        assert entry.resource_type == "conversation"
        assert entry.resource_id == "conv_123"

    def test_log_data_export(self, logger):
        """Test log_data_export."""
        entry = logger.log_data_export(
            user_id="user_1",
            exported_data_types=["conversations", "api_keys"],
        )
        assert entry.action == AuditAction.DATA_EXPORTED
        assert "conversations" in entry.details["exported_data_types"]

    def test_log_data_deletion(self, logger):
        """Test log_data_deletion."""
        entry = logger.log_data_deletion(
            user_id="user_1",
            deleted_data_types=["conversations"],
        )
        assert entry.action == AuditAction.DATA_DELETED


class TestAuditLoggerRetention:
    """Test audit logger retention limits."""

    def test_prunes_old_logs(self):
        """Test that old logs are pruned when exceeding max."""
        logger = AuditLogger()
        logger._max_logs = 5

        # Add more than max
        for i in range(10):
            logger.log(action=AuditAction.USER_LOGIN, user_id=f"user_{i}")

        assert len(logger._logs) == 5


class TestModuleFunctions:
    """Test module-level functions."""

    def test_get_audit_logger_singleton(self):
        """Test get_audit_logger returns same instance."""
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()
        assert logger1 is logger2
