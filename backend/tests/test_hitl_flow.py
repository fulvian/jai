"""Test E2E per flusso HITL (Human-in-the-Loop)."""

import asyncio
import pytest
from me4brain.engine.executor import ParallelExecutor
from me4brain.engine.catalog import ToolCatalog
from me4brain.engine.types import ToolTask
from me4brain.engine.permission_validator import PermissionLevel


class MockCatalog:
    """Mock catalog for testing."""

    def get_executor(self, tool_name: str):
        async def mock_executor(**kwargs):
            return {"status": "executed", "tool": tool_name, "args": kwargs}

        return mock_executor


@pytest.mark.asyncio
async def test_safe_tool_executes_without_approval():
    """Tool SAFE viene eseguito senza approvazione."""
    catalog = MockCatalog()
    executor = ParallelExecutor(catalog)

    task = ToolTask(
        tool_name="calculator",  # SAFE tool
        arguments={"expression": "2+2"},
    )

    result = await executor.execute_single(task)
    assert result.success is True
    assert result.data["status"] == "executed"


@pytest.mark.asyncio
async def test_deny_tool_blocked():
    """Tool DENY viene bloccato immediatamente."""
    catalog = MockCatalog()
    executor = ParallelExecutor(catalog)

    task = ToolTask(
        tool_name="execute_sudo",  # DENY tool
        arguments={"command": "rm -rf /"},
    )

    result = await executor.execute_single(task)
    assert result.success is False
    assert "bloccata" in result.error.lower() or "blocked" in result.error.lower()


@pytest.mark.asyncio
async def test_confirm_tool_blocked_without_callback():
    """Tool CONFIRM bloccato se non c'è HITL callback."""
    catalog = MockCatalog()
    executor = ParallelExecutor(catalog, hitl_callback=None)

    task = ToolTask(
        tool_name="gmail_send",  # CONFIRM tool
        arguments={"to": "test@example.com", "body": "Test"},
    )

    result = await executor.execute_single(task)
    assert result.success is False
    assert "approvazione" in result.error.lower()


@pytest.mark.asyncio
async def test_confirm_tool_approved_with_callback():
    """Tool CONFIRM viene eseguito se approvato via callback."""
    catalog = MockCatalog()

    async def approve_callback(tool_name, message, args):
        return True  # Approva

    executor = ParallelExecutor(catalog, hitl_callback=approve_callback)

    task = ToolTask(
        tool_name="gmail_send",  # CONFIRM tool
        arguments={"to": "test@example.com", "body": "Test"},
    )

    result = await executor.execute_single(task)
    assert result.success is True


@pytest.mark.asyncio
async def test_confirm_tool_rejected_with_callback():
    """Tool CONFIRM bloccato se rifiutato via callback."""
    catalog = MockCatalog()

    async def reject_callback(tool_name, message, args):
        return False  # Rifiuta

    executor = ParallelExecutor(catalog, hitl_callback=reject_callback)

    task = ToolTask(
        tool_name="gmail_send",  # CONFIRM tool
        arguments={"to": "test@example.com", "body": "Test"},
    )

    result = await executor.execute_single(task)
    assert result.success is False
    assert "rifiutata" in result.error.lower()


@pytest.mark.asyncio
async def test_notify_tool_logs_and_executes():
    """Tool NOTIFY logga e viene eseguito."""
    catalog = MockCatalog()
    executor = ParallelExecutor(catalog)

    task = ToolTask(
        tool_name="memory_store",  # NOTIFY tool
        arguments={"content": "test"},
    )

    result = await executor.execute_single(task)
    assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
