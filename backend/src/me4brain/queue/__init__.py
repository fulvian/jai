"""
Queue package - Async task queue for background processing.
"""

from me4brain.queue.tasks import (
    TASK_CLASSIFY_DOMAIN,
    TASK_SUMMARIZE_CONVERSATION,
    TASK_WARM_CACHE,
    TaskDefinition,
    TaskPriority,
    TaskResult,
    TaskStatus,
    get_all_tasks,
    get_task,
    register_task,
    task,
)
from me4brain.queue.queue_manager import (
    QueueManager,
    get_queue_manager,
)

__all__ = [
    "get_queue_manager",
    "get_task",
    "get_all_tasks",
    "register_task",
    "QueueManager",
    "TaskDefinition",
    "TaskPriority",
    "TaskResult",
    "TaskStatus",
    "TASK_CLASSIFY_DOMAIN",
    "TASK_SUMMARIZE_CONVERSATION",
    "TASK_WARM_CACHE",
    "task",
]
