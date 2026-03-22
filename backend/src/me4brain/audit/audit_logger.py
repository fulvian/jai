"""
Audit logging module for JAI.

Provides comprehensive audit logging for security and compliance.
Logs all sensitive operations with full context.
"""

from __future__ import annotations

import json
import structlog
import uuid
from datetime import datetime
from typing import Any, Optional

from me4brain.models.audit import AuditAction, AuditLogEntry, AuditStatus

logger = structlog.get_logger(__name__)


class AuditLogger:
    """Audit logger for security and compliance.

    Provides methods to log all sensitive operations.
    """

    def __init__(self):
        # In-memory storage for demonstration
        # In production, this would use a database
        self._logs: list[AuditLogEntry] = []
        self._logs_by_user: dict[str, list[str]] = {}  # user_id -> [log_ids]
        self._logs_by_resource: dict[str, list[str]] = {}  # resource_type:id -> [log_ids]
        self._max_logs = 100000  # Retention limit

    def log(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        status: AuditStatus = AuditStatus.SUCCESS,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> AuditLogEntry:
        """Log an audit event.

        Args:
            action: The action being logged
            user_id: ID of the user performing the action
            status: Status of the action
            resource_type: Type of resource being acted upon
            resource_id: ID of the resource
            details: Additional details
            ip_address: Client IP address
            user_agent: Client user agent
            request_id: Request correlation ID
            session_id: Session ID
            error_message: Error message if action failed

        Returns:
            The created audit log entry
        """
        entry = AuditLogEntry(
            id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            user_id=user_id,
            action=action,
            status=status,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            session_id=session_id,
            error_message=error_message,
        )

        # Store
        self._logs.append(entry)
        if len(self._logs) > self._max_logs:
            # Prune old logs
            self._logs = self._logs[-self._max_logs :]

        # Index by user
        if user_id:
            if user_id not in self._logs_by_user:
                self._logs_by_user[user_id] = []
            self._logs_by_user[user_id].append(entry.id)

        # Index by resource
        if resource_type and resource_id:
            key = f"{resource_type}:{resource_id}"
            if key not in self._logs_by_resource:
                self._logs_by_resource[key] = []
            self._logs_by_resource[key].append(entry.id)

        # Log to structlog as well
        log_data = {
            "audit_id": entry.id,
            "action": entry.action.value,
            "user_id": user_id,
            "status": entry.status.value,
            "resource_type": resource_type,
            "resource_id": resource_id,
        }
        if error_message:
            logger.warning("audit_event", **log_data, error=error_message)
        else:
            logger.info("audit_event", **log_data)

        return entry

    def get_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        """Query audit logs.

        Args:
            user_id: Filter by user ID
            action: Filter by action type
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of results

        Returns:
            List of matching audit log entries
        """
        results = self._logs

        # Apply filters
        if user_id:
            results = [r for r in results if r.user_id == user_id]

        if action:
            results = [r for r in results if r.action == action]

        if resource_type and resource_id:
            key = f"{resource_type}:{resource_id}"
            log_ids = set(self._logs_by_resource.get(key, []))
            results = [r for r in results if r.id in log_ids]

        if start_date:
            results = [r for r in results if r.timestamp >= start_date]

        if end_date:
            results = [r for r in results if r.timestamp <= end_date]

        # Sort by timestamp descending
        results.sort(key=lambda x: x.timestamp, reverse=True)

        return results[:limit]

    def get_user_logs(self, user_id: str, limit: int = 100) -> list[AuditLogEntry]:
        """Get all logs for a specific user.

        Args:
            user_id: The user ID
            limit: Maximum number of results

        Returns:
            List of audit log entries for the user
        """
        return self.get_logs(user_id=user_id, limit=limit)

    def get_resource_logs(
        self, resource_type: str, resource_id: str, limit: int = 100
    ) -> list[AuditLogEntry]:
        """Get all logs for a specific resource.

        Args:
            resource_type: The resource type
            resource_id: The resource ID
            limit: Maximum number of results

        Returns:
            List of audit log entries for the resource
        """
        return self.get_logs(resource_type=resource_type, resource_id=resource_id, limit=limit)

    def export_logs(
        self,
        user_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> str:
        """Export audit logs as JSON.

        Args:
            user_id: Filter by user ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            JSON string of audit logs
        """
        logs = self.get_logs(user_id=user_id, start_date=start_date, end_date=end_date, limit=10000)
        return json.dumps([log.to_dict() for log in logs], indent=2)

    # Convenience methods for common audit events

    def log_login(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> AuditLogEntry:
        """Log a login attempt.

        Args:
            user_id: The user ID
            ip_address: Client IP
            user_agent: Client user agent
            success: Whether login succeeded
            error_message: Error if failed

        Returns:
            The audit log entry
        """
        return self.log(
            action=AuditAction.USER_LOGIN if success else AuditAction.USER_LOGIN_FAILED,
            user_id=user_id,
            status=AuditStatus.SUCCESS if success else AuditStatus.FAILURE,
            ip_address=ip_address,
            user_agent=user_agent,
            error_message=error_message,
        )

    def log_api_key_created(
        self,
        user_id: str,
        key_id: str,
        ip_address: Optional[str] = None,
    ) -> AuditLogEntry:
        """Log API key creation.

        Args:
            user_id: The user ID
            key_id: The created key ID
            ip_address: Client IP

        Returns:
            The audit log entry
        """
        return self.log(
            action=AuditAction.API_KEY_CREATED,
            user_id=user_id,
            status=AuditStatus.SUCCESS,
            resource_type="api_key",
            resource_id=key_id,
            ip_address=ip_address,
        )

    def log_api_key_revoked(
        self,
        user_id: str,
        key_id: str,
        ip_address: Optional[str] = None,
    ) -> AuditLogEntry:
        """Log API key revocation.

        Args:
            user_id: The user ID
            key_id: The revoked key ID
            ip_address: Client IP

        Returns:
            The audit log entry
        """
        return self.log(
            action=AuditAction.API_KEY_REVOKED,
            user_id=user_id,
            status=AuditStatus.SUCCESS,
            resource_type="api_key",
            resource_id=key_id,
            ip_address=ip_address,
        )

    def log_conversation_accessed(
        self,
        user_id: str,
        conversation_id: str,
        ip_address: Optional[str] = None,
    ) -> AuditLogEntry:
        """Log conversation access.

        Args:
            user_id: The user ID
            conversation_id: The conversation ID
            ip_address: Client IP

        Returns:
            The audit log entry
        """
        return self.log(
            action=AuditAction.CONVERSATION_ACCESSED,
            user_id=user_id,
            status=AuditStatus.SUCCESS,
            resource_type="conversation",
            resource_id=conversation_id,
            ip_address=ip_address,
        )

    def log_data_export(
        self,
        user_id: str,
        exported_data_types: list[str],
        ip_address: Optional[str] = None,
    ) -> AuditLogEntry:
        """Log data export (GDPR).

        Args:
            user_id: The user ID
            exported_data_types: Types of data exported
            ip_address: Client IP

        Returns:
            The audit log entry
        """
        return self.log(
            action=AuditAction.DATA_EXPORTED,
            user_id=user_id,
            status=AuditStatus.SUCCESS,
            details={"exported_data_types": exported_data_types},
            ip_address=ip_address,
        )

    def log_data_deletion(
        self,
        user_id: str,
        deleted_data_types: list[str],
        ip_address: Optional[str] = None,
    ) -> AuditLogEntry:
        """Log data deletion (GDPR).

        Args:
            user_id: The user ID
            deleted_data_types: Types of data deleted
            ip_address: Client IP

        Returns:
            The audit log entry
        """
        return self.log(
            action=AuditAction.DATA_DELETED,
            user_id=user_id,
            status=AuditStatus.SUCCESS,
            details={"deleted_data_types": deleted_data_types},
            ip_address=ip_address,
        )


# Singleton instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance.

    Returns:
        The global audit logger
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
