"""
Queue Manager - Redis-based async task queue.

Provides a simple message queue using Redis lists for:
- Task enqueuing
- Background task processing
- Retry logic with dead-letter queue
- Task status tracking
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import structlog

from me4brain.queue.tasks import (
    TASK_CLASSIFY_DOMAIN,
    TASK_SUMMARIZE_CONVERSATION,
    TASK_WARM_CACHE,
    TaskDefinition,
    TaskPriority,
    TaskResult,
    TaskStatus,
    get_task,
)

logger = structlog.get_logger(__name__)

# Queue names
QUEUE_MAIN = "me4brain:tasks:main"
QUEUE_HIGH_PRIORITY = "me4brain:tasks:high"
QUEUE_LOW_PRIORITY = "me4brain:tasks:low"
QUEUE_DEAD_LETTER = "me4brain:tasks:dead_letter"
QUEUE_RESULTS = "me4brain:tasks:results"

# Default settings
DEFAULT_TIMEOUT = 300  # 5 minutes
DEFAULT_MAX_RETRIES = 3


@dataclass
class QueuedTask:
    """A task in the queue."""

    task_id: str
    name: str
    args: tuple
    kwargs: dict
    priority: TaskPriority
    status: TaskStatus
    retry_count: int
    max_retries: int
    enqueued_at: float
    started_at: Optional[float]
    completed_at: Optional[float]
    result: Any
    error: Optional[str]

    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(
            {
                "task_id": self.task_id,
                "name": self.name,
                "args": self.args,
                "kwargs": self.kwargs,
                "priority": self.priority.value
                if isinstance(self.priority, TaskPriority)
                else self.priority,
                "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
                "retry_count": self.retry_count,
                "max_retries": self.max_retries,
                "enqueued_at": self.enqueued_at,
                "started_at": self.started_at,
                "completed_at": self.completed_at,
                "result": self.result,
                "error": self.error,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "QueuedTask":
        """Deserialize from JSON."""
        obj = json.loads(data)
        return cls(
            task_id=obj["task_id"],
            name=obj["name"],
            args=tuple(obj.get("args", ())),
            kwargs=obj.get("kwargs", {}),
            priority=TaskPriority(obj.get("priority", "normal")),
            status=TaskStatus(obj.get("status", "pending")),
            retry_count=obj.get("retry_count", 0),
            max_retries=obj.get("max_retries", DEFAULT_MAX_RETRIES),
            enqueued_at=obj.get("enqueued_at", time.time()),
            started_at=obj.get("started_at"),
            completed_at=obj.get("completed_at"),
            result=obj.get("result"),
            error=obj.get("error"),
        )

    @classmethod
    def from_task_definition(cls, task_def: TaskDefinition) -> "QueuedTask":
        """Create from a TaskDefinition."""
        return cls(
            task_id=task_def.task_id,
            name=task_def.name,
            args=task_def.args,
            kwargs=task_def.kwargs,
            priority=task_def.priority,
            status=TaskStatus.PENDING,
            retry_count=task_def.retry_count,
            max_retries=task_def.max_retries,
            enqueued_at=time.time(),
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
        )


class QueueManager:
    """Redis-based task queue manager.

    Provides async task queuing and processing using Redis lists
    for a simple but effective message queue.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        max_workers: int = 4,
    ):
        """Initialize queue manager.

        Args:
            redis_url: Redis connection URL
            max_workers: Maximum concurrent worker tasks
        """
        self._redis_url = redis_url
        self._max_workers = max_workers
        self._redis = None
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._paused = False

    async def _get_redis(self):
        """Get or create Redis client."""
        if self._redis is None:
            import redis.asyncio as redis

            self._redis = redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    def _get_queue_name(self, priority: TaskPriority) -> str:
        """Get queue name for priority level."""
        if priority == TaskPriority.HIGH:
            return QUEUE_HIGH_PRIORITY
        elif priority == TaskPriority.LOW:
            return QUEUE_LOW_PRIORITY
        return QUEUE_MAIN

    async def enqueue(
        self,
        task_name: str,
        *args,
        priority: TaskPriority = TaskPriority.NORMAL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        **kwargs,
    ) -> str:
        """Add a task to the queue.

        Args:
            task_name: Name of the task to enqueue
            *args: Positional arguments for the task
            priority: Task priority level
            max_retries: Maximum retry attempts
            **kwargs: Keyword arguments for the task

        Returns:
            Task ID
        """
        redis = await self._get_redis()

        task_id = f"task_{uuid.uuid4().hex[:16]}"
        task_def = TaskDefinition(
            task_id=task_id,
            name=task_name,
            args=args,
            kwargs=kwargs,
            priority=priority,
            max_retries=max_retries,
        )

        queued_task = QueuedTask.from_task_definition(task_def)
        queue_name = self._get_queue_name(priority)

        await redis.rpush(queue_name, queued_task.to_json())

        logger.info(
            "task_enqueued",
            task_id=task_id,
            task_name=task_name,
            priority=priority.value,
            queue=queue_name,
        )

        return task_id

    async def enqueue_classify(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        priority: TaskPriority = TaskPriority.HIGH,
    ) -> str:
        """Convenience method to enqueue a classification task.

        Args:
            query: User query
            conversation_id: Optional conversation ID
            priority: Task priority

        Returns:
            Task ID
        """
        return await self.enqueue(
            TASK_CLASSIFY_DOMAIN,
            query=query,
            conversation_id=conversation_id,
            priority=priority,
        )

    async def enqueue_summarize(
        self,
        conversation_id: str,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> str:
        """Convenience method to enqueue a summarization task.

        Args:
            conversation_id: Conversation to summarize
            priority: Task priority

        Returns:
            Task ID
        """
        return await self.enqueue(
            TASK_SUMMARIZE_CONVERSATION,
            conversation_id=conversation_id,
            priority=priority,
        )

    async def get_task_status(self, task_id: str) -> Optional[TaskResult]:
        """Get the status and result of a task.

        Args:
            task_id: Task ID to check

        Returns:
            TaskResult if found, None otherwise
        """
        redis = await self._get_redis()
        data = await redis.get(f"{QUEUE_RESULTS}:{task_id}")

        if data is None:
            return None

        result = json.loads(data)
        return TaskResult(
            task_id=task_id,
            success=result.get("success", False),
            result=result.get("result"),
            error=result.get("error"),
            execution_time_ms=result.get("execution_time_ms", 0),
        )

    async def _process_task(self, queued_task: QueuedTask) -> None:
        """Process a single task.

        Args:
            queued_task: Task to process
        """
        start_time = time.time()
        task_func = get_task(queued_task.name)

        if task_func is None:
            logger.error("task_not_found", task_name=queued_task.name)
            queued_task.status = TaskStatus.FAILED
            queued_task.error = f"Task {queued_task.name} not found"
            return

        try:
            queued_task.status = TaskStatus.RUNNING
            queued_task.started_at = time.time()

            logger.debug("task_started", task_id=queued_task.task_id, task_name=queued_task.name)

            # Execute the task
            if asyncio.iscoroutinefunction(task_func):
                result = await asyncio.wait_for(
                    task_func(*queued_task.args, **queued_task.kwargs),
                    timeout=DEFAULT_TIMEOUT,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, lambda: task_func(*queued_task.args, **queued_task.kwargs)
                    ),
                    timeout=DEFAULT_TIMEOUT,
                )

            # Success
            queued_task.status = TaskStatus.COMPLETED
            queued_task.result = result
            queued_task.completed_at = time.time()

            execution_time = (queued_task.completed_at - start_time) * 1000
            logger.info(
                "task_completed",
                task_id=queued_task.task_id,
                task_name=queued_task.name,
                execution_time_ms=execution_time,
            )

        except asyncio.TimeoutError:
            queued_task.status = TaskStatus.FAILED
            queued_task.error = "Task timed out"
            queued_task.completed_at = time.time()
            logger.error("task_timeout", task_id=queued_task.task_id, task_name=queued_task.name)

        except Exception as e:
            queued_task.status = TaskStatus.FAILED
            queued_task.error = str(e)
            queued_task.completed_at = time.time()
            logger.error(
                "task_failed",
                task_id=queued_task.task_id,
                task_name=queued_task.name,
                error=str(e),
            )

        # Store result
        redis = await self._get_redis()
        execution_time = (
            (queued_task.completed_at - start_time) * 1000 if queued_task.completed_at else 0
        )

        result_data = {
            "success": queued_task.status == TaskStatus.COMPLETED,
            "result": queued_task.result,
            "error": queued_task.error,
            "execution_time_ms": execution_time,
        }
        await redis.setex(
            f"{QUEUE_RESULTS}:{queued_task.task_id}",
            3600,  # Keep result for 1 hour
            json.dumps(result_data),
        )

        # Handle retry if failed
        if (
            queued_task.status == TaskStatus.FAILED
            and queued_task.retry_count < queued_task.max_retries
        ):
            queued_task.retry_count += 1
            queued_task.status = TaskStatus.RETRYING
            queued_task.started_at = None
            # Re-enqueue with delay
            queue_name = self._get_queue_name(queued_task.priority)
            await asyncio.sleep(min(5 * queued_task.retry_count, 30))  # Exponential backoff
            await redis.rpush(queue_name, queued_task.to_json())
            logger.info("task_requeued", task_id=queued_task.task_id, retry=queued_task.retry_count)

        # Move to dead letter if permanently failed
        elif queued_task.status == TaskStatus.FAILED:
            await redis.rpush(QUEUE_DEAD_LETTER, queued_task.to_json())

    async def _worker(self, worker_id: int) -> None:
        """Worker coroutine that processes tasks.

        Args:
            worker_id: Worker identifier
        """
        redis = await self._get_redis()

        while self._running:
            try:
                # Try high priority first, then normal, then low
                for queue_name in [QUEUE_HIGH_PRIORITY, QUEUE_MAIN, QUEUE_LOW_PRIORITY]:
                    data = await redis.lpop(queue_name)
                    if data is not None:
                        queued_task = QueuedTask.from_json(data)
                        await self._process_task(queued_task)
                        break
                else:
                    # No tasks available, wait
                    await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("worker_error", worker_id=worker_id, error=str(e))
                await asyncio.sleep(1)

    async def start(self) -> None:
        """Start the queue workers."""
        if self._running:
            return

        self._running = True
        self._workers = [asyncio.create_task(self._worker(i)) for i in range(self._max_workers)]
        logger.info("queue_workers_started", num_workers=self._max_workers)

    async def stop(self) -> None:
        """Stop the queue workers gracefully."""
        self._running = False

        # Wait for workers to finish
        for worker in self._workers:
            worker.cancel()

        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

        logger.info("queue_workers_stopped")

    async def get_queue_stats(self) -> dict:
        """Get queue statistics.

        Returns:
            Dict with queue sizes and worker status
        """
        redis = await self._get_redis()

        high_size = await redis.llen(QUEUE_HIGH_PRIORITY)
        main_size = await redis.llen(QUEUE_MAIN)
        low_size = await redis.llen(QUEUE_LOW_PRIORITY)
        dlq_size = await redis.llen(QUEUE_DEAD_LETTER)

        return {
            "running": self._running,
            "workers": self._max_workers,
            "queues": {
                "high_priority": high_size,
                "main": main_size,
                "low_priority": low_size,
                "dead_letter": dlq_size,
            },
            "total_pending": high_size + main_size + low_size,
        }

    async def pause(self) -> None:
        """Pause task processing."""
        self._paused = True
        logger.info("queue_paused")

    async def resume(self) -> None:
        """Resume task processing."""
        self._paused = False
        logger.info("queue_resumed")


# Singleton instance
_queue_manager: Optional[QueueManager] = None


def get_queue_manager() -> QueueManager:
    """Get singleton queue manager instance."""
    global _queue_manager
    if _queue_manager is None:
        _queue_manager = QueueManager()
    return _queue_manager
