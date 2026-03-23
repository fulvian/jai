"""Batch processing for UnifiedIntentAnalyzer.

This module provides:
- Batch processing of multiple queries
- Async batch collection and processing
- Performance optimization through batching
"""

import asyncio
from dataclasses import dataclass

import structlog

from me4brain.engine.unified_intent_analyzer import IntentAnalysis, UnifiedIntentAnalyzer

logger = structlog.get_logger(__name__)


@dataclass
class BatchRequest:
    """Single request in a batch."""

    query: str
    context: str | None = None
    future: asyncio.Future | None = None


@dataclass
class BatchResult:
    """Result of batch processing."""

    query: str
    analysis: IntentAnalysis
    error: str | None = None


class IntentBatchProcessor:
    """Batch processor for intent analysis.

    Collects multiple queries and processes them together for better throughput.
    """

    def __init__(
        self,
        analyzer: UnifiedIntentAnalyzer,
        batch_size: int = 10,
        batch_timeout_ms: float = 100.0,
    ):
        """Initialize batch processor.

        Args:
            analyzer: UnifiedIntentAnalyzer instance
            batch_size: Maximum batch size
            batch_timeout_ms: Maximum time to wait for batch to fill
        """
        self._analyzer = analyzer
        self._batch_size = batch_size
        self._batch_timeout = batch_timeout_ms / 1000.0  # Convert to seconds
        self._queue: list[BatchRequest] = []
        self._lock = asyncio.Lock()
        self._batch_event = asyncio.Event()
        self._processor_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start batch processor background task."""
        if self._processor_task is None or self._processor_task.done():
            self._processor_task = asyncio.create_task(self._process_batches())
            logger.info("batch_processor_started")

    async def stop(self) -> None:
        """Stop batch processor."""
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
            logger.info("batch_processor_stopped")

    async def analyze(
        self,
        query: str,
        context: str | None = None,
    ) -> IntentAnalysis:
        """Analyze query using batch processing.

        Args:
            query: User query
            context: Optional context

        Returns:
            IntentAnalysis result
        """
        # Ensure processor is running
        await self.start()

        # Create request with future
        future: asyncio.Future[IntentAnalysis] = asyncio.Future()
        request = BatchRequest(query=query, context=context, future=future)

        # Add to queue
        async with self._lock:
            self._queue.append(request)

            # Signal if batch is full
            if len(self._queue) >= self._batch_size:
                self._batch_event.set()

        # Wait for result
        try:
            result = await asyncio.wait_for(future, timeout=self._batch_timeout * 2)
            return result
        except TimeoutError:
            logger.warning(
                "batch_processing_timeout",
                query_preview=query[:50],
            )
            # Fallback to direct analysis
            return await self._analyzer.analyze(query, context)

    async def _process_batches(self) -> None:
        """Background task to process batches."""
        while True:
            try:
                # Wait for batch to fill or timeout
                try:
                    await asyncio.wait_for(
                        self._batch_event.wait(),
                        timeout=self._batch_timeout,
                    )
                except TimeoutError:
                    pass

                # Get current batch
                async with self._lock:
                    if not self._queue:
                        self._batch_event.clear()
                        continue

                    batch = self._queue[: self._batch_size]
                    self._queue = self._queue[self._batch_size :]
                    self._batch_event.clear()

                # Process batch
                await self._process_batch(batch)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "batch_processing_error",
                    error=str(e),
                    error_type=type(e).__name__,
                )

    async def _process_batch(self, batch: list[BatchRequest]) -> None:
        """Process a batch of requests.

        Args:
            batch: List of batch requests
        """
        logger.debug(
            "batch_processing_start",
            batch_size=len(batch),
        )

        # Process all queries in parallel
        tasks = [self._analyzer.analyze(req.query, req.context) for req in batch]

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Distribute results to futures
            for req, result in zip(batch, results):
                if isinstance(result, Exception):
                    if req.future and not req.future.done():
                        req.future.set_exception(result)
                    logger.warning(
                        "batch_item_failed",
                        query_preview=req.query[:50],
                        error=str(result),
                    )
                else:
                    if req.future and not req.future.done():
                        req.future.set_result(result)

            logger.debug(
                "batch_processing_complete",
                batch_size=len(batch),
                successful=sum(1 for r in results if not isinstance(r, Exception)),
            )

        except Exception as e:
            logger.error(
                "batch_processing_failed",
                error=str(e),
                batch_size=len(batch),
            )
            # Set exception for all futures
            for req in batch:
                if req.future and not req.future.done():
                    req.future.set_exception(e)


# Global batch processor instance
_batch_processor: IntentBatchProcessor | None = None


def get_batch_processor(
    analyzer: UnifiedIntentAnalyzer,
    batch_size: int = 10,
    batch_timeout_ms: float = 100.0,
) -> IntentBatchProcessor:
    """Get global batch processor instance.

    Args:
        analyzer: UnifiedIntentAnalyzer instance
        batch_size: Maximum batch size
        batch_timeout_ms: Maximum time to wait for batch

    Returns:
        IntentBatchProcessor singleton
    """
    global _batch_processor
    if _batch_processor is None:
        _batch_processor = IntentBatchProcessor(analyzer, batch_size, batch_timeout_ms)
    return _batch_processor


def reset_batch_processor() -> None:
    """Reset batch processor (for testing)."""
    global _batch_processor
    _batch_processor = None
