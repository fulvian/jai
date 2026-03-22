"""
Permissions module - Defines all system permissions for RBAC.

This module defines the permission constants used throughout JAI to control
access to various resources and operations.
"""

from __future__ import annotations

from enum import Enum


class Permission(str, Enum):
    """System permissions for RBAC.

    Permissions follow the pattern: resource:action:scope
    - resource: The resource being accessed (conversation, query, user, etc.)
    - action: The action being performed (create, read, update, delete)
    - scope: The scope of the access (own, all, any)
    """

    # Conversation permissions
    CONVERSATION_CREATE = "conversation:create"
    CONVERSATION_READ_OWN = "conversation:read:own"
    CONVERSATION_READ_ALL = "conversation:read:all"
    CONVERSATION_UPDATE_OWN = "conversation:update:own"
    CONVERSATION_UPDATE_ANY = "conversation:update:any"
    CONVERSATION_DELETE_OWN = "conversation:delete:own"
    CONVERSATION_DELETE_ANY = "conversation:delete:any"

    # Query permissions
    QUERY_SUBMIT = "query:submit"

    # User management permissions
    USER_CREATE = "user:create"
    USER_READ_OWN = "user:read:own"
    USER_READ_ALL = "user:read:all"
    USER_UPDATE_OWN = "user:update:own"
    USER_UPDATE_ANY = "user:update:any"
    USER_DELETE_OWN = "user:delete:own"
    USER_DELETE_ANY = "user:delete:any"

    # API key permissions
    API_KEY_CREATE = "api_key:create"
    API_KEY_READ_OWN = "api_key:read:own"
    API_KEY_READ_ALL = "api_key:read:all"
    API_KEY_REVOKE_OWN = "api_key:revoke:own"
    API_KEY_REVOKE_ANY = "api_key:revoke:any"

    # Metrics and monitoring
    METRICS_VIEW = "metrics:view"
    METRICS_VIEW_ALL = "metrics:view:all"

    # System configuration
    CONFIG_MANAGE = "config:manage"
    CONFIG_VIEW = "config:view"

    # Audit logs
    AUDIT_VIEW = "audit:view"
    AUDIT_EXPORT = "audit:export"

    # Domain management
    DOMAIN_CREATE = "domain:create"
    DOMAIN_READ = "domain:read"
    DOMAIN_UPDATE = "domain:update"
    DOMAIN_DELETE = "domain:delete"

    # Tool management
    TOOL_CREATE = "tool:create"
    TOOL_READ = "tool:read"
    TOOL_UPDATE = "tool:update"
    TOOL_DELETE = "tool:delete"

    # Health check (public)
    HEALTH_CHECK = "health:check"

    # Admin-only permissions
    ADMIN_ALL = "admin:all"


class Role(str, Enum):
    """System roles for RBAC.

    Roles are collections of permissions that can be assigned to users.
    """

    # Admin role - full system access
    ADMIN = "admin"

    # User role - standard user access to own resources
    USER = "user"

    # Analyst role - read-only access to metrics and logs
    ANALYST = "analyst"

    # Service role - API-to-API communication with limited scopes
    SERVICE = "service"

    # Public role - unauthenticated access to public endpoints
    PUBLIC = "public"


# Role to permissions mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.ADMIN: {
        # Admin has all permissions
        Permission.ADMIN_ALL,
        # User permissions
        Permission.CONVERSATION_CREATE,
        Permission.CONVERSATION_READ_OWN,
        Permission.CONVERSATION_READ_ALL,
        Permission.CONVERSATION_UPDATE_OWN,
        Permission.CONVERSATION_UPDATE_ANY,
        Permission.CONVERSATION_DELETE_OWN,
        Permission.CONVERSATION_DELETE_ANY,
        Permission.QUERY_SUBMIT,
        Permission.USER_CREATE,
        Permission.USER_READ_OWN,
        Permission.USER_READ_ALL,
        Permission.USER_UPDATE_OWN,
        Permission.USER_UPDATE_ANY,
        Permission.USER_DELETE_OWN,
        Permission.USER_DELETE_ANY,
        Permission.API_KEY_CREATE,
        Permission.API_KEY_READ_OWN,
        Permission.API_KEY_READ_ALL,
        Permission.API_KEY_REVOKE_OWN,
        Permission.API_KEY_REVOKE_ANY,
        Permission.METRICS_VIEW,
        Permission.METRICS_VIEW_ALL,
        Permission.CONFIG_MANAGE,
        Permission.CONFIG_VIEW,
        Permission.AUDIT_VIEW,
        Permission.AUDIT_EXPORT,
        Permission.DOMAIN_CREATE,
        Permission.DOMAIN_READ,
        Permission.DOMAIN_UPDATE,
        Permission.DOMAIN_DELETE,
        Permission.TOOL_CREATE,
        Permission.TOOL_READ,
        Permission.TOOL_UPDATE,
        Permission.TOOL_DELETE,
        Permission.HEALTH_CHECK,
    },
    Role.USER: {
        # User can create conversations and manage their own
        Permission.CONVERSATION_CREATE,
        Permission.CONVERSATION_READ_OWN,
        Permission.CONVERSATION_UPDATE_OWN,
        Permission.CONVERSATION_DELETE_OWN,
        # User can submit queries
        Permission.QUERY_SUBMIT,
        # User can manage their own API keys
        Permission.API_KEY_CREATE,
        Permission.API_KEY_READ_OWN,
        Permission.API_KEY_REVOKE_OWN,
        # User can view their own user data
        Permission.USER_READ_OWN,
        Permission.USER_UPDATE_OWN,
        # User can view basic metrics
        Permission.METRICS_VIEW,
        Permission.HEALTH_CHECK,
    },
    Role.ANALYST: {
        # Analyst has read-only access
        Permission.CONVERSATION_READ_OWN,
        Permission.CONVERSATION_READ_ALL,
        Permission.USER_READ_OWN,
        Permission.USER_READ_ALL,
        Permission.METRICS_VIEW,
        Permission.METRICS_VIEW_ALL,
        Permission.AUDIT_VIEW,
        Permission.AUDIT_EXPORT,
        Permission.CONFIG_VIEW,
        Permission.DOMAIN_READ,
        Permission.TOOL_READ,
        Permission.HEALTH_CHECK,
    },
    Role.SERVICE: {
        # Service account - limited scopes for API-to-API
        Permission.CONVERSATION_CREATE,
        Permission.CONVERSATION_READ_OWN,
        Permission.QUERY_SUBMIT,
        Permission.API_KEY_CREATE,
        Permission.API_KEY_READ_OWN,
        Permission.HEALTH_CHECK,
    },
    Role.PUBLIC: {
        # Public access - only health check
        Permission.HEALTH_CHECK,
    },
}


def get_permissions_for_role(role: Role) -> set[Permission]:
    """Get all permissions for a given role.

    Args:
        role: The role to get permissions for

    Returns:
        Set of permissions granted to the role
    """
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(role: Role, permission: Permission) -> bool:
    """Check if a role has a specific permission.

    Args:
        role: The role to check
        permission: The permission to verify

    Returns:
        True if the role has the permission, False otherwise
    """
    if Permission.ADMIN_ALL in ROLE_PERMISSIONS.get(role, set()):
        # Admin has all permissions
        return True
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_permission(permission: Permission):
    """Decorator to require a specific permission.

    Usage:
        @require_permission(Permission.CONVERSATION_CREATE)
        async def create_conversation(user: User, ...):
            ...

    Args:
        permission: The permission required to execute the function
    """

    def decorator(func):
        func._required_permission = permission
        return func

    return decorator
