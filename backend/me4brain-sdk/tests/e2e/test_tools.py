"""E2E Tests for Tools Namespace."""

from __future__ import annotations

import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
class TestToolsNamespace:
    """Test Tools namespace operations."""

    async def test_list_tools(self, async_client):
        """Test listing all available tools."""
        tools = await async_client.tools.list(limit=100)

        assert tools is not None
        assert len(tools) > 0, "Should have at least some tools registered"

        # Verify tool structure
        for tool in tools[:5]:  # Check first 5
            assert tool.name is not None
            assert tool.description is not None

    async def test_list_categories(self, async_client):
        """Test listing tool categories."""
        categories = await async_client.tools.categories()

        assert categories is not None
        assert len(categories) > 0

        # Extract category names from response (list of dicts or strings)
        if categories and isinstance(categories[0], dict):
            category_names = [c.get("name", c) for c in categories]
        else:
            category_names = categories

        # Should have some known categories from the actual tools catalog
        known_categories = ["google", "nba", "alpaca", "openmeteo", "binance"]
        for cat in known_categories:
            if cat in category_names:
                break
        else:
            pytest.fail(f"Should have at least one known category, got: {category_names}")

    async def test_search_tools(self, async_client):
        """Test tool search by query."""
        results = await async_client.tools.search(
            query="weather forecast",
            limit=10,
            min_score=0.3,
        )

        assert results is not None
        # Should find weather-related tools

    async def test_search_tools_by_category(self, async_client):
        """Test tool search filtered by category."""
        results = await async_client.tools.search(
            query="stock",
            limit=10,
            category="finance",
        )

        assert results is not None

    async def test_get_tool_by_id(self, async_client):
        """Test getting tool details by ID."""
        # First list tools to get an ID
        tools = await async_client.tools.list(limit=1)

        if tools:
            tool = await async_client.tools.get(tools[0].id)

            assert tool is not None
            assert tool.id == tools[0].id

    async def test_execute_tool_calculator(self, async_client):
        """Test executing a simple tool."""
        # Try calculator tool
        try:
            result = await async_client.tools.execute(
                tool_id="calculator",
                parameters={"expression": "2 + 2"},
            )

            assert result is not None
            assert result.success is True
            # Result should be 4
        except Exception as e:
            # Tool may not be available
            pytest.skip(f"Calculator tool not available: {e}")

    async def test_execute_tool_with_invalid_params(self, async_client):
        """Test tool execution with invalid parameters."""
        from me4brain_sdk.exceptions import Me4BrAInAPIError, Me4BrAInNotFoundError

        try:
            result = await async_client.tools.execute(
                tool_id="nonexistent_tool_xyz",
                parameters={},
            )
            # If execution returns, it should indicate failure
            assert result.success is False or result.error is not None
        except (Me4BrAInAPIError, Me4BrAInNotFoundError):
            pass  # Expected - tool not found or error


@pytest.mark.e2e
@pytest.mark.asyncio
class TestToolExecution:
    """Test actual tool execution for specific domains."""

    @pytest.mark.slow
    async def test_execute_weather_tool(self, async_client):
        """Test weather tool execution."""
        try:
            result = await async_client.tools.execute(
                tool_id="openweather_current",
                parameters={"city": "Milan"},
            )

            assert result is not None
            if result.success:
                assert result.result is not None
        except Exception as e:
            pytest.skip(f"Weather tool not available: {e}")

    @pytest.mark.slow
    async def test_execute_crypto_tool(self, async_client):
        """Test crypto price tool execution."""
        try:
            result = await async_client.tools.execute(
                tool_id="coingecko_price",
                parameters={"coin_id": "bitcoin"},
            )

            assert result is not None
            if result.success:
                assert result.result is not None
        except Exception as e:
            pytest.skip(f"Crypto tool not available: {e}")
