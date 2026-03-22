"""
Task definitions for the message queue.

Defines async tasks that can be offloaded to a background queue
for processing by workers.
"""

from __future__ import annotations

import asyncio
import structlog
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

logger = structlog.get_logger(__name__)


class TaskPriority(str, Enum):
    """Task priority levels."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class TaskResult:
    """Result of a task execution."""

    task_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class TaskDefinition:
    """Definition of a queued task."""

    task_id: str
    name: str
    args: tuple = ()
    kwargs: dict = None
    priority: TaskPriority = TaskPriority.NORMAL
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 300

    def __post_init__(self):
        if self.kwargs is None:
            self.kwargs = {}


def task(
    name: str = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    max_retries: int = 3,
    timeout_seconds: int = 300,
):
    """Decorator to mark a function as a queue task.

    Usage:
        @task(name="classify_async", max_retries=3)
        async def classify_task(query: str, conversation_id: str):
            # task logic
            return result
    """

    def decorator(func):
        func._is_task = True
        func._task_name = name or func.__name__
        func._task_priority = priority
        func._task_max_retries = max_retries
        func._task_timeout = timeout_seconds
        return func

    return decorator


# Pre-defined task types
TASK_CLASSIFY_DOMAIN = "classify_domain_async"
TASK_SUMMARIZE_CONVERSATION = "summarize_conversation"
TASK_WARM_CACHE = "warm_cache"
TASK_GENERATE_EMBEDDINGS = "generate_embeddings"
TASK_SEND_NOTIFICATION = "send_notification"


# Task registry
_task_registry: dict[str, callable] = {}


def register_task(name: str, func: callable) -> None:
    """Register a task function.

    Args:
        name: Task name
        func: Async function to call
    """
    _task_registry[name] = func
    logger.debug("task_registered", task_name=name)


def get_task(name: str) -> Optional[callable]:
    """Get a registered task function.

    Args:
        name: Task name

    Returns:
        Task function or None
    """
    return _task_registry.get(name)


def get_all_tasks() -> dict[str, callable]:
    """Get all registered tasks."""
    return _task_registry.copy()


# =============================================================================
# Example Task Implementations
# =============================================================================


@task(name=TASK_CLASSIFY_DOMAIN, priority=TaskPriority.HIGH, max_retries=3)
async def classify_domain_async(query: str, conversation_id: str = None) -> dict:
    """Async domain classification task.

    Args:
        query: User query
        conversation_id: Optional conversation ID for context

    Returns:
        Classification result dict
    """
    from me4brain.observability.tracing import TracingContext

    with TracingContext("task.classify_domain", query=query[:100]):
        # Import here to avoid circular dependencies
        try:
            from me4brain.engine.hybrid_router.domain_classifier import DomainClassifier
            from me4brain.config.settings import get_settings

            settings = get_settings()
            classifier = DomainClassifier()

            result = await classifier.classify(query)
            return {
                "success": True,
                "domain": result.domain_names[0] if result.domain_names else None,
                "confidence": result.confidence,
                "query": query,
            }
        except Exception as e:
            logger.error("classify_task_failed", error=str(e), query=query[:100])
            return {
                "success": False,
                "error": str(e),
                "query": query,
            }


@task(name=TASK_SUMMARIZE_CONVERSATION, priority=TaskPriority.NORMAL, max_retries=2)
async def summarize_conversation_task(conversation_id: str) -> dict:
    """Async conversation summarization task.

    Args:
        conversation_id: Conversation to summarize

    Returns:
        Summary result dict
    """
    from me4brain.observability.tracing import TracingContext

    with TracingContext("task.summarize_conversation", conversation_id=conversation_id):
        try:
            # This would use the ConversationSummarizer
            # Placeholder implementation
            return {
                "success": True,
                "conversation_id": conversation_id,
                "summary": "Summary placeholder",
            }
        except Exception as e:
            logger.error("summarize_task_failed", error=str(e))
            return {
                "success": False,
                "error": str(e),
                "conversation_id": conversation_id,
            }


@task(name=TASK_WARM_CACHE, priority=TaskPriority.LOW, max_retries=1)
async def warm_cache_task(query_patterns: list[str]) -> dict:
    """Pre-warm cache with common queries.

    Args:
        query_patterns: List of query patterns to pre-cache

    Returns:
        Warm cache result
    """
    warmed = 0
    for pattern in query_patterns:
        try:
            # Pre-generate cache entries for common queries
            warmed += 1
        except Exception as e:
            logger.warning("warm_cache_pattern_failed", pattern=pattern, error=str(e))

    return {
        "success": True,
        "warmed_count": warmed,
        "total_patterns": len(query_patterns),
    }


# Register all tasks
register_task(TASK_CLASSIFY_DOMAIN, classify_domain_async)
register_task(TASK_SUMMARIZE_CONVERSATION, summarize_conversation_task)
register_task(TASK_WARM_CACHE, warm_cache_task)
