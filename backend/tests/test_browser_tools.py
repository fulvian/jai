"""Test Browser Automation Tools.

Tests for browser automation functionality including:
- Browser open/close lifecycle
- Navigation
- Permission validation (CONFIRM for browser_open/act)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from me4brain.domains.utility.tools.browser import (
    browser_close,
    browser_open,
    get_executors,
    get_tool_definitions,
)
from me4brain.engine.permission_validator import PermissionLevel, PermissionValidator


class TestBrowserToolDefinitions:
    """Test browser tool definitions are correctly configured."""

    def test_get_tool_definitions_returns_all_tools(self):
        """All 6 browser tools should be defined."""
        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]

        assert len(tools) == 6
        assert "browser_open" in tool_names
        assert "browser_act" in tool_names
        assert "browser_extract" in tool_names
        assert "browser_screenshot" in tool_names
        assert "browser_navigate" in tool_names
        assert "browser_close" in tool_names

    def test_get_executors_returns_all_functions(self):
        """All browser tools should have executor functions."""
        executors = get_executors()

        assert len(executors) == 6
        assert callable(executors["browser_open"])
        assert callable(executors["browser_act"])
        assert callable(executors["browser_extract"])

    def test_tool_definitions_have_correct_domain(self):
        """All browser tools should be in utility domain."""
        tools = get_tool_definitions()

        for tool in tools:
            assert tool.domain == "utility"
            assert tool.category == "browser"


class TestBrowserPermissions:
    """Test permission levels for browser tools."""

    def test_browser_open_requires_confirm(self):
        """browser_open should require CONFIRM permission."""
        validator = PermissionValidator()
        result = validator.validate("browser_open")

        assert result.permission_level == PermissionLevel.CONFIRM
        assert result.requires_human_approval is True

    def test_browser_act_requires_confirm(self):
        """browser_act should require CONFIRM permission."""
        validator = PermissionValidator()
        result = validator.validate("browser_act")

        assert result.permission_level == PermissionLevel.CONFIRM

    def test_browser_extract_is_safe(self):
        """browser_extract is read-only, should be SAFE."""
        validator = PermissionValidator()
        result = validator.validate("browser_extract")

        assert result.permission_level == PermissionLevel.SAFE
        assert result.requires_human_approval is False

    def test_browser_screenshot_is_safe(self):
        """browser_screenshot is read-only, should be SAFE."""
        validator = PermissionValidator()
        result = validator.validate("browser_screenshot")

        assert result.permission_level == PermissionLevel.SAFE

    def test_browser_close_is_safe(self):
        """browser_close is cleanup action, should be SAFE."""
        validator = PermissionValidator()
        result = validator.validate("browser_close")

        assert result.permission_level == PermissionLevel.SAFE


class TestBrowserOperations:
    """Test actual browser operations with mocked manager."""

    @pytest.mark.asyncio
    async def test_browser_open_without_manager(self):
        """browser_open should return error when manager not initialized."""
        with patch(
            "me4brain.domains.utility.tools.browser.get_browser_manager",
            return_value=None,
        ):
            result = await browser_open("https://example.com")

            assert "error" in result
            assert "not initialized" in result["error"]

    @pytest.mark.asyncio
    async def test_browser_close_without_session(self):
        """browser_close should return error when no session active."""
        with patch(
            "me4brain.domains.utility.tools.browser.get_browser_manager",
            return_value=None,
        ):
            result = await browser_close()

            assert "error" in result

    @pytest.mark.asyncio
    async def test_browser_open_with_mocked_manager(self):
        """browser_open should create session when manager available."""
        # Mock session
        mock_session = MagicMock()
        mock_session.id = "test-session-123"
        mock_session.current_url = "https://example.com"
        mock_session.current_title = "Example Domain"
        mock_session.status.value = "ready"

        # Mock manager
        mock_manager = AsyncMock()
        mock_manager.create_session = AsyncMock(return_value=mock_session)

        with patch(
            "me4brain.domains.utility.tools.browser.get_browser_manager",
            return_value=mock_manager,
        ):
            result = await browser_open("https://example.com", headless=True)

            assert result["session_id"] == "test-session-123"
            assert result["url"] == "https://example.com"
            assert result["status"] == "ready"


class TestBrowserToolIntegration:
    """Integration tests for browser tools with Tool Calling Engine."""

    def test_browser_tools_can_be_imported_from_utility(self):
        """Browser tools should be importable from utility tools package."""
        from me4brain.domains.utility.tools import (
            browser_act,
            browser_extract,
            browser_open,
        )

        assert callable(browser_open)
        assert callable(browser_act)
        assert callable(browser_extract)

    def test_combined_tool_definitions_include_browser(self):
        """Combined utility tools should include browser tools."""
        from me4brain.domains.utility.tools import get_tool_definitions

        tools = get_tool_definitions()
        tool_names = [t.name for t in tools]

        # Should have API tools + Browser tools
        assert "get_ip" in tool_names  # API tool
        assert "browser_open" in tool_names  # Browser tool
