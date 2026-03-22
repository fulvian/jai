"""Unit tests for queue manager module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json


class TestQueuedTask:
    """Tests for QueuedTask dataclass."""

    def test_to_json(self):
        """Test QueuedTask serialization to JSON."""
        from me4brain.queue.queue_manager import QueuedTask
        from me4brain.queue.tasks import TaskPriority, TaskStatus

        task = QueuedTask(
            task_id="task_123",
            name="test_task",
            args=("arg1",),
            kwargs={"key": "value"},
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
            retry_count=0,
            max_retries=3,
            enqueued_at=1000.0,
            started_at=None,
            completed_at=None,
            result=None,
            error=None,
        )

        json_str = task.to_json()
        data = json.loads(json_str)

        assert data["task_id"] == "task_123"
        assert data["name"] == "test_task"
        assert data["priority"] == "high"
        assert data["status"] == "pending"

    def test_from_json(self):
        """Test QueuedTask deserialization from JSON."""
        from me4brain.queue.queue_manager import QueuedTask

        json_str = json.dumps(
            {
                "task_id": "task_456",
                "name": "another_task",
                "args": (),
                "kwargs": {},
                "priority": "low",
                "status": "completed",
                "retry_count": 1,
                "max_retries": 3,
                "enqueued_at": 2000.0,
            }
        )

        task = QueuedTask.from_json(json_str)

        assert task.task_id == "task_456"
        assert task.name == "another_task"
        assert task.priority.value == "low"
        assert task.status.value == "completed"


class TestQueueManager:
    """Tests for QueueManager class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.rpush = AsyncMock(return_value=1)
        mock.lpop = AsyncMock(return_value=None)
        mock.llen = AsyncMock(return_value=0)
        mock.get = AsyncMock(return_value=None)
        mock.setex = AsyncMock(return_value=True)
        return mock

    @pytest.mark.asyncio
    async def test_enqueue(self, mock_redis):
        """Test enqueueing a task."""
        from me4brain.queue.queue_manager import QueueManager
        from me4brain.queue.tasks import TaskPriority

        with patch("redis.asyncio") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis

            manager = QueueManager()
            manager._redis = mock_redis

            task_id = await manager.enqueue("test_task", arg1="value1", priority=TaskPriority.HIGH)

            assert task_id is not None
            assert task_id.startswith("task_")
            mock_redis.rpush.assert_called()

    @pytest.mark.asyncio
    async def test_enqueue_classify(self, mock_redis):
        """Test enqueueing a classification task."""
        from me4brain.queue.queue_manager import QueueManager
        from me4brain.queue.tasks import TASK_CLASSIFY_DOMAIN

        with patch("redis.asyncio") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis

            manager = QueueManager()
            manager._redis = mock_redis

            task_id = await manager.enqueue_classify(query="test query", conversation_id="conv_123")

            assert task_id is not None
            mock_redis.rpush.assert_called()

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, mock_redis):
        """Test getting status of non-existent task."""
        from me4brain.queue.queue_manager import QueueManager

        with patch("redis.asyncio") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis
            mock_redis.get.return_value = None

            manager = QueueManager()
            manager._redis = mock_redis

            result = await manager.get_task_status("nonexistent_task")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_task_status_found(self, mock_redis):
        """Test getting status of existing task."""
        from me4brain.queue.queue_manager import QueueManager

        mock_redis.get.return_value = json.dumps(
            {
                "success": True,
                "result": {"key": "value"},
                "error": None,
                "execution_time_ms": 150.5,
            }
        )

        with patch("redis.asyncio") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis

            manager = QueueManager()
            manager._redis = mock_redis

            result = await manager.get_task_status("task_123")

            assert result is not None
            assert result.success is True
            assert result.execution_time_ms == 150.5

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, mock_redis):
        """Test getting queue statistics."""
        from me4brain.queue.queue_manager import QueueManager

        mock_redis.llen.side_effect = [5, 10, 3, 1]  # high, main, low, dlq

        with patch("redis.asyncio") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis

            manager = QueueManager()
            manager._redis = mock_redis

            stats = await manager.get_queue_stats()

            assert stats["running"] is False
            assert stats["queues"]["high_priority"] == 5
            assert stats["queues"]["main"] == 10
            assert stats["queues"]["low_priority"] == 3
            assert stats["queues"]["dead_letter"] == 1
            assert stats["total_pending"] == 18

    @pytest.mark.asyncio
    async def test_start_stop_workers(self, mock_redis):
        """Test starting and stopping queue workers."""
        from me4brain.queue.queue_manager import QueueManager

        with patch("redis.asyncio") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis

            manager = QueueManager(max_workers=2)
            manager._redis = mock_redis

            # Start workers
            await manager.start()
            assert manager._running is True
            assert len(manager._workers) == 2

            # Stop workers
            await manager.stop()
            assert manager._running is False
            assert len(manager._workers) == 0

    @pytest.mark.asyncio
    async def test_pause_resume(self, mock_redis):
        """Test pausing and resuming queue processing."""
        from me4brain.queue.queue_manager import QueueManager

        with patch("redis.asyncio") as mock_redis_module:
            mock_redis_module.from_url.return_value = mock_redis

            manager = QueueManager()
            manager._redis = mock_redis

            await manager.pause()
            assert manager._paused is True

            await manager.resume()
            assert manager._paused is False


class TestQueuePriority:
    """Tests for queue priority handling."""

    def test_get_queue_name_high(self):
        """Test getting queue name for high priority."""
        from me4brain.queue.queue_manager import QueueManager
        from me4brain.queue.tasks import TaskPriority

        manager = QueueManager()
        queue_name = manager._get_queue_name(TaskPriority.HIGH)

        assert "high" in queue_name

    def test_get_queue_name_low(self):
        """Test getting queue name for low priority."""
        from me4brain.queue.queue_manager import QueueManager
        from me4brain.queue.tasks import TaskPriority

        manager = QueueManager()
        queue_name = manager._get_queue_name(TaskPriority.LOW)

        assert "low" in queue_name

    def test_get_queue_name_normal(self):
        """Test getting queue name for normal priority."""
        from me4brain.queue.queue_manager import QueueManager
        from me4brain.queue.tasks import TaskPriority

        manager = QueueManager()
        queue_name = manager._get_queue_name(TaskPriority.NORMAL)

        assert "main" in queue_name or "normal" in queue_name
