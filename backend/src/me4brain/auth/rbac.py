"""
RBAC (Role-Based Access Control) module for JAI.

Provides comprehensive role-based access control including:
- User authentication and authorization
- Role assignment and permission checking
- Permission decorators for route protection
- Integration with FastAPI
"""

from __future__ import annotations

import structlog
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from me4brain.auth.permissions import Permission, Role, has_permission, get_permissions_for_role

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)


@dataclass
class User:
    """User model for authentication and authorization.

    Represents a user in the system with associated roles and metadata.
    """

    id: str
    username: str
    email: str
    roles: list[Role] = field(default_factory=list)
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission through any of their roles.

        Args:
            permission: The permission to check

        Returns:
            True if user has the permission via any role
        """
        if not self.is_active:
            return False
        for role in self.roles:
            if has_permission(role, permission):
                return True
        return False

    def has_any_permission(self, permissions: list[Permission]) -> bool:
        """Check if user has any of the specified permissions.

        Args:
            permissions: List of permissions to check

        Returns:
            True if user has at least one permission
        """
        return any(self.has_permission(p) for p in permissions)

    def has_all_permissions(self, permissions: list[Permission]) -> bool:
        """Check if user has all of the specified permissions.

        Args:
            permissions: List of permissions to check

        Returns:
            True if user has all permissions
        """
        return all(self.has_permission(p) for p in permissions)

    def get_permissions(self) -> set[Permission]:
        """Get all permissions for this user through their roles.

        Returns:
            Set of all permissions the user has
        """
        perms = set()
        for role in self.roles:
            perms.update(get_permissions_for_role(role))
        return perms

    def is_admin(self) -> bool:
        """Check if user has admin role.

        Returns:
            True if user has admin role
        """
        return Role.ADMIN in self.roles

    def is_service_account(self) -> bool:
        """Check if user is a service account.

        Returns:
            True if user has service role
        """
        return Role.SERVICE in self.roles

    def to_dict(self) -> dict[str, Any]:
        """Convert user to dictionary (excluding sensitive data).

        Returns:
            User data as dictionary
        """
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "roles": [r.value for r in self.roles],
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }


@dataclass
class ServiceAccount(User):
    """Service account for API-to-API communication.

    Service accounts have limited permissions and are used for
    machine-to-machine authentication.
    """

    service_name: str = ""
    scopes: list[str] = field(default_factory=list)


class AuthorizationError(Exception):
    """Exception raised when authorization fails."""

    def __init__(self, message: str, required_permission: Optional[Permission] = None):
        super().__init__(message)
        self.required_permission = required_permission


class RBACChecker:
    """RBAC authorization checker.

    Provides methods to check and enforce permissions.
    """

    def __init__(self):
        self._cache: dict[str, set[Permission]] = {}

    def check_permission(
        self,
        user: Optional[User],
        permission: Permission,
        resource_owner_id: Optional[str] = None,
    ) -> bool:
        """Check if user has permission for an action.

        Args:
            user: The user to check
            permission: The permission required
            resource_owner_id: ID of the resource owner (for own/* permissions)

        Returns:
            True if authorized, False otherwise
        """
        if user is None:
            # Anonymous user check
            return permission == Permission.HEALTH_CHECK

        # Admin bypass
        if user.is_admin():
            return True

        # Check base permission
        if not user.has_permission(permission):
            logger.warning(
                "permission_denied",
                user_id=user.id,
                permission=permission.value,
            )
            return False

        # Handle own/* permissions
        if permission.value.endswith(":own") and resource_owner_id:
            if user.id != resource_owner_id and not user.is_admin():
                logger.warning(
                    "resource_access_denied",
                    user_id=user.id,
                    resource_owner=resource_owner_id,
                    permission=permission.value,
                )
                return False

        return True

    def require_permission(
        self,
        user: Optional[User],
        permission: Permission,
        resource_owner_id: Optional[str] = None,
    ) -> None:
        """Require a permission or raise AuthorizationError.

        Args:
            user: The user to check
            permission: The permission required
            resource_owner_id: ID of the resource owner

        Raises:
            AuthorizationError: If user doesn't have permission
        """
        if not self.check_permission(user, permission, resource_owner_id):
            raise AuthorizationError(
                f"Permission denied: {permission.value}",
                required_permission=permission,
            )

    def filter_by_permission(
        self,
        user: User,
        items: list[dict[str, Any]],
        permission: Permission,
        owner_field: str = "user_id",
    ) -> list[dict[str, Any]]:
        """Filter a list of items based on user's permission.

        For admin users, returns all items.
        For regular users with *_all permission, returns all items.
        For regular users with *_own permission, returns only their items.

        Args:
            user: The user performing the action
            items: List of resource dictionaries
            permission: The permission to check
            owner_field: The field name containing the owner ID

        Returns:
            Filtered list of items
        """
        # Admin sees all
        if user.is_admin() or Permission.CONVERSATION_READ_ALL in user.get_permissions():
            return items

        # Filter to own items
        return [item for item in items if item.get(owner_field) == user.id]


# Global RBAC checker instance
_rbac_checker: Optional[RBACChecker] = None


def get_rbac_checker() -> RBACChecker:
    """Get the global RBAC checker instance.

    Returns:
        The global RBAC checker
    """
    global _rbac_checker
    if _rbac_checker is None:
        _rbac_checker = RBACChecker()
    return _rbac_checker


def check_permission(
    user: Optional[User],
    permission: Permission,
    resource_owner_id: Optional[str] = None,
) -> bool:
    """Convenience function to check permission.

    Args:
        user: The user to check
        permission: The permission required
        resource_owner_id: ID of the resource owner

    Returns:
        True if authorized
    """
    return get_rbac_checker().check_permission(user, permission, resource_owner_id)


def require_permission(
    user: Optional[User],
    permission: Permission,
    resource_owner_id: Optional[str] = None,
) -> None:
    """Convenience function to require permission.

    Args:
        user: The user to check
        permission: The permission required
        resource_owner_id: ID of the resource owner

    Raises:
        AuthorizationError: If user doesn't have permission
    """
    get_rbac_checker().require_permission(user, permission, resource_owner_id)
