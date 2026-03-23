"""Unit tests for Domain Handlers."""

from unittest.mock import patch

import pytest

from me4brain.core.interfaces import (
    DomainCapability,
    DomainVolatility,
)
from me4brain.domains.utility.handler import UtilityHandler


class TestUtilityHandler:
    """Test UtilityHandler domain handler."""

    @pytest.fixture
    def handler(self):
        """Create handler instance."""
        return UtilityHandler()

    def test_domain_name(self, handler):
        """Test domain name property."""
        assert handler.domain_name == "utility"

    def test_volatility(self, handler):
        """Test volatility property."""
        assert handler.volatility == DomainVolatility.REAL_TIME

    def test_default_ttl_hours(self, handler):
        """Test default TTL."""
        assert handler.default_ttl_hours == 1

    def test_capabilities(self, handler):
        """Test capabilities list."""
        caps = handler.capabilities
        assert len(caps) >= 1
        assert isinstance(caps[0], DomainCapability)
        assert caps[0].name == "network_info"

    @pytest.mark.asyncio
    async def test_initialize(self, handler):
        """Test initialize method."""
        await handler.initialize()
        # Should not raise

    @pytest.mark.asyncio
    async def test_can_handle_matching_query(self, handler):
        """Test can_handle with matching keywords."""
        score = await handler.can_handle("qual è il mio ip?", {})
        assert score > 0

    @pytest.mark.asyncio
    async def test_can_handle_non_matching_query(self, handler):
        """Test can_handle with non-matching query."""
        score = await handler.can_handle("che tempo fa oggi?", {})
        assert score == 0

    @pytest.mark.asyncio
    async def test_can_handle_multiple_keywords(self, handler):
        """Test can_handle with multiple keywords."""
        score = await handler.can_handle("test ip headers", {})
        assert score > 0.3  # Multiple matches

    @pytest.mark.asyncio
    async def test_execute_success(self, handler):
        """Test execute with mocked API."""
        with patch("me4brain.domains.utility.tools.utility_api.get_ip") as mock_get_ip:
            mock_get_ip.return_value = {"origin": "1.2.3.4"}

            results = await handler.execute("qual è il mio ip", {}, {})

            assert len(results) == 1
            assert results[0].success is True
            assert results[0].domain == "utility"
            assert results[0].data == {"origin": "1.2.3.4"}

    @pytest.mark.asyncio
    async def test_execute_failure(self, handler):
        """Test execute handles errors."""
        with patch("me4brain.domains.utility.tools.utility_api.get_ip") as mock_get_ip:
            mock_get_ip.side_effect = Exception("Network error")

            results = await handler.execute("qual è il mio ip", {}, {})

            assert len(results) == 1
            assert results[0].success is False
            assert "Network error" in results[0].error

    def test_handles_service(self, handler):
        """Test handles_service method."""
        assert handler.handles_service("HttpbinService") is True
        assert handler.handles_service("OtherService") is False

    @pytest.mark.asyncio
    async def test_execute_tool(self, handler):
        """Test execute_tool method."""
        with patch("me4brain.domains.utility.tools.utility_api.execute_tool") as mock_exec:
            mock_exec.return_value = {"result": "ok"}

            result = await handler.execute_tool("get_ip", {})

            assert result == {"result": "ok"}
            mock_exec.assert_called_once_with("get_ip", {})


class TestUtilityKeywords:
    """Test utility handler keyword matching."""

    @pytest.fixture
    def handler(self):
        return UtilityHandler()

    @pytest.mark.asyncio
    async def test_ip_keyword(self, handler):
        score = await handler.can_handle("check ip address", {})
        assert score > 0

    @pytest.mark.asyncio
    async def test_test_keyword(self, handler):
        score = await handler.can_handle("run a test", {})
        assert score > 0

    @pytest.mark.asyncio
    async def test_uuid_keyword(self, handler):
        score = await handler.can_handle("generate uuid", {})
        assert score > 0

    @pytest.mark.asyncio
    async def test_random_keyword(self, handler):
        score = await handler.can_handle("random number", {})
        assert score > 0
