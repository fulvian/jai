"""
Auth module - Authentication and authorization for JAI.

Provides:
- RBAC (Role-Based Access Control)
- Permission definitions and checking
- API key management
"""

from me4brain.auth.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    get_permissions_for_role,
    has_permission,
)
from me4brain.auth.permissions import (
    require_permission as require_permission_decorator,
)
from me4brain.auth.rbac import (
    AuthorizationError,
    RBACChecker,
    ServiceAccount,
    User,
    check_permission,
    get_rbac_checker,
    require_permission,
)

__all__ = [
    # Permissions
    "Permission",
    "Role",
    "ROLE_PERMISSIONS",
    "get_permissions_for_role",
    "has_permission",
    "require_permission_decorator",
    # RBAC
    "AuthorizationError",
    "RBACChecker",
    "ServiceAccount",
    "User",
    "check_permission",
    "get_rbac_checker",
    "require_permission",
]
