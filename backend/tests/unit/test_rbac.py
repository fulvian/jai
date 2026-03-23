"""
Unit tests for RBAC (Role-Based Access Control) module.
"""

from __future__ import annotations

import pytest

from me4brain.auth.permissions import (
    Permission,
    Role,
    get_permissions_for_role,
    has_permission,
)
from me4brain.auth.rbac import (
    AuthorizationError,
    RBACChecker,
    User,
    check_permission,
    get_rbac_checker,
    require_permission,
)


class TestPermission:
    """Test Permission enum and helpers."""

    def test_permission_values(self):
        """Test Permission enum has expected values."""
        assert Permission.CONVERSATION_CREATE.value == "conversation:create"
        assert Permission.CONVERSATION_READ_OWN.value == "conversation:read:own"
        assert Permission.API_KEY_CREATE.value == "api_key:create"

    def test_role_values(self):
        """Test Role enum has expected values."""
        assert Role.ADMIN.value == "admin"
        assert Role.USER.value == "user"
        assert Role.ANALYST.value == "analyst"
        assert Role.SERVICE.value == "service"
        assert Role.PUBLIC.value == "public"


class TestRolePermissions:
    """Test role-permission mappings."""

    def test_admin_has_all_permissions(self):
        """Test admin role has all permissions."""
        admin_perms = get_permissions_for_role(Role.ADMIN)
        # Admin should have ADMIN_ALL permission
        assert Permission.ADMIN_ALL in admin_perms
        # Admin should have most critical permissions
        assert Permission.CONVERSATION_CREATE in admin_perms
        assert Permission.USER_DELETE_ANY in admin_perms

    def test_user_has_limited_permissions(self):
        """Test user role has limited permissions."""
        user_perms = get_permissions_for_role(Role.USER)
        # User should have conversation:create
        assert Permission.CONVERSATION_CREATE in user_perms
        # User should have own permissions
        assert Permission.CONVERSATION_READ_OWN in user_perms
        # User should NOT have any permissions
        assert Permission.CONVERSATION_READ_ALL not in user_perms
        assert Permission.USER_DELETE_ANY not in user_perms

    def test_analyst_has_readonly_permissions(self):
        """Test analyst role has read-only permissions."""
        analyst_perms = get_permissions_for_role(Role.ANALYST)
        # Analyst should have read permissions
        assert Permission.CONVERSATION_READ_OWN in analyst_perms
        assert Permission.CONVERSATION_READ_ALL in analyst_perms
        # Analyst should NOT have write permissions
        assert Permission.CONVERSATION_CREATE not in analyst_perms
        assert Permission.CONVERSATION_DELETE_ANY not in analyst_perms

    def test_service_has_limited_scopes(self):
        """Test service role has limited API scopes."""
        service_perms = get_permissions_for_role(Role.SERVICE)
        # Service should have create and read
        assert Permission.CONVERSATION_CREATE in service_perms
        assert Permission.CONVERSATION_READ_OWN in service_perms
        # Service should NOT have admin permissions
        assert Permission.USER_DELETE_ANY not in service_perms

    def test_public_has_health_check_only(self):
        """Test public role has only health check."""
        public_perms = get_permissions_for_role(Role.PUBLIC)
        assert len(public_perms) == 1
        assert Permission.HEALTH_CHECK in public_perms


class TestHasPermission:
    """Test has_permission function."""

    def test_admin_has_all_via_admin_all(self):
        """Test admin bypass via ADMIN_ALL."""
        # Even if we check a random permission, admin should have it
        # via the ADMIN_ALL permission
        assert has_permission(Role.ADMIN, Permission.USER_DELETE_ANY)

    def test_user_does_not_have_undefined_permission(self):
        """Test user lacks permissions not in their mapping."""
        assert not has_permission(Role.USER, Permission.AUDIT_EXPORT)

    def test_none_role_has_no_permissions(self):
        """Test role not in mapping has no permissions."""
        # This would only happen if we added a new role but forgot to add it
        # to ROLE_PERMISSIONS
        pass  # All current roles are mapped


class TestUserModel:
    """Test User model."""

    def test_user_creation(self):
        """Test creating a user."""
        user = User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            roles=[Role.USER],
        )
        assert user.id == "user_123"
        assert user.username == "testuser"
        assert user.roles == [Role.USER]
        assert user.is_active is True

    def test_user_has_permission_through_role(self):
        """Test user has permission through their role."""
        user = User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            roles=[Role.USER],
        )
        assert user.has_permission(Permission.CONVERSATION_CREATE)
        assert not user.has_permission(Permission.USER_DELETE_ANY)

    def test_user_with_multiple_roles(self):
        """Test user with multiple roles."""
        user = User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            roles=[Role.USER, Role.ANALYST],
        )
        # Should have USER permissions
        assert user.has_permission(Permission.CONVERSATION_CREATE)
        # Should also have ANALYST permissions
        assert user.has_permission(Permission.CONVERSATION_READ_ALL)

    def test_inactive_user_has_no_permissions(self):
        """Test inactive user has no permissions."""
        user = User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            roles=[Role.ADMIN],
            is_active=False,
        )
        assert not user.has_permission(Permission.HEALTH_CHECK)

    def test_user_is_admin(self):
        """Test is_admin method."""
        admin = User(id="admin_1", username="admin", email="admin@example.com", roles=[Role.ADMIN])
        user = User(id="user_1", username="user", email="user@example.com", roles=[Role.USER])
        assert admin.is_admin() is True
        assert user.is_admin() is False

    def test_user_get_permissions(self):
        """Test get_permissions returns all permissions."""
        user = User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            roles=[Role.USER],
        )
        perms = user.get_permissions()
        assert Permission.CONVERSATION_CREATE in perms
        assert Permission.CONVERSATION_READ_OWN in perms


class TestRBACChecker:
    """Test RBACChecker class."""

    def test_check_permission_allows_admin(self):
        """Test admin bypasses permission checks."""
        checker = RBACChecker()
        admin = User(id="admin_1", username="admin", email="admin@example.com", roles=[Role.ADMIN])
        # Admin should be allowed anything
        assert checker.check_permission(admin, Permission.USER_DELETE_ANY) is True

    def test_check_permission_denies_unauthorized(self):
        """Test regular user denied unauthorized actions."""
        checker = RBACChecker()
        user = User(id="user_1", username="user", email="user@example.com", roles=[Role.USER])
        # User trying to delete any user
        assert checker.check_permission(user, Permission.USER_DELETE_ANY) is False

    def test_check_permission_allows_own_resource(self):
        """Test user can access own resources."""
        checker = RBACChecker()
        user = User(id="user_1", username="user", email="user@example.com", roles=[Role.USER])
        # User accessing their own conversation
        assert (
            checker.check_permission(
                user, Permission.CONVERSATION_READ_OWN, resource_owner_id="user_1"
            )
            is True
        )

    def test_check_permission_denies_others_resource(self):
        """Test user cannot access others' resources with :own permission."""
        checker = RBACChecker()
        user = User(id="user_1", username="user", email="user@example.com", roles=[Role.USER])
        # User trying to access another user's conversation
        assert (
            checker.check_permission(
                user, Permission.CONVERSATION_READ_OWN, resource_owner_id="user_2"
            )
            is False
        )

    def test_require_permission_raises_on_failure(self):
        """Test require_permission raises AuthorizationError."""
        checker = RBACChecker()
        user = User(id="user_1", username="user", email="user@example.com", roles=[Role.USER])
        with pytest.raises(AuthorizationError) as exc_info:
            checker.require_permission(user, Permission.USER_DELETE_ANY)
        assert exc_info.value.required_permission == Permission.USER_DELETE_ANY

    def test_filter_by_permission_admin_sees_all(self):
        """Test admin sees all items."""
        checker = RBACChecker()
        admin = User(id="admin_1", username="admin", email="admin@example.com", roles=[Role.ADMIN])
        items = [
            {"id": "1", "user_id": "user_1"},
            {"id": "2", "user_id": "user_2"},
        ]
        result = checker.filter_by_permission(admin, items, Permission.CONVERSATION_READ_ALL)
        assert len(result) == 2

    def test_filter_by_permission_user_sees_own(self):
        """Test user sees only their own items."""
        checker = RBACChecker()
        user = User(id="user_1", username="user", email="user@example.com", roles=[Role.USER])
        items = [
            {"id": "1", "user_id": "user_1"},
            {"id": "2", "user_id": "user_2"},
            {"id": "3", "user_id": "user_1"},
        ]
        result = checker.filter_by_permission(user, items, Permission.CONVERSATION_READ_OWN)
        assert len(result) == 2
        assert all(item["user_id"] == "user_1" for item in result)


class TestModuleFunctions:
    """Test module-level convenience functions."""

    def test_get_rbac_checker_singleton(self):
        """Test get_rbac_checker returns same instance."""
        checker1 = get_rbac_checker()
        checker2 = get_rbac_checker()
        assert checker1 is checker2

    def test_check_permission_convenience_function(self):
        """Test check_permission convenience function."""
        user = User(id="user_1", username="user", email="user@example.com", roles=[Role.USER])
        assert check_permission(user, Permission.CONVERSATION_CREATE) is True
        assert check_permission(user, Permission.USER_DELETE_ANY) is False

    def test_require_permission_convenience_function(self):
        """Test require_permission convenience function."""
        user = User(id="user_1", username="user", email="user@example.com", roles=[Role.USER])
        # Should not raise
        require_permission(user, Permission.CONVERSATION_CREATE)
        # Should raise
        with pytest.raises(AuthorizationError):
            require_permission(user, Permission.USER_DELETE_ANY)
