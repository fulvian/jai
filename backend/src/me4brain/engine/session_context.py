"""Session Context - Request-scoped session propagation via contextvars.

FIX Issue #6: Propagates session_id through the entire pipeline without
modifying function signatures. Uses Python contextvars (async-safe) to
pass session context from API routes to engine internals.

Usage:
    # In API route:
    from me4brain.engine.session_context import session_context, get_current_session_id

    async with session_context(session_id="abc-123"):
        result = await engine.run_iterative_stream(query)

    # Deep inside engine code:
    sid = get_current_session_id()  # Returns "abc-123"
"""

from __future__ import annotations

import contextvars
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog

logger = structlog.get_logger(__name__)

# Context variable for session ID
_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_session_id", default=None
)


def get_current_session_id() -> str | None:
    """Get the current session ID from context.

    Returns:
        Session ID string, or None if not in a session context.
    """
    return _current_session_id.get()


def set_current_session_id(session_id: str | None) -> contextvars.Token[str | None]:
    """Set the current session ID in context.

    Args:
        session_id: Session ID to set

    Returns:
        Token for resetting the context variable
    """
    return _current_session_id.set(session_id)


@asynccontextmanager
async def session_context(session_id: str) -> AsyncIterator[None]:
    """Async context manager that sets and restores session ID.

    Args:
        session_id: Session ID to propagate through the call stack

    Yields:
        None. The session_id is available via get_current_session_id().
    """
    token = _current_session_id.set(session_id)
    try:
        logger.debug("session_context_entered", session_id=session_id)
        yield
    finally:
        _current_session_id.reset(token)
        logger.debug("session_context_exited", session_id=session_id)
