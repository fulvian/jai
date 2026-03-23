"""LLM Batch Scheduler - SOTA 2026.

Raggruppa chiamate LLM indipendenti in batch per efficienza.

Invece di:
  call1 → wait → call2 → wait → call3 → wait

Fa:
  [call1, call2, call3] → wait_all (concorrenti su provider diversi)
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from me4brain.llm.base import LLMProvider
    from me4brain.llm.models import LLMChunk, LLMRequest, LLMResponse

logger = structlog.get_logger(__name__)


@dataclass
class BatchStats:
    """Statistiche del batch scheduler."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_latency_ms: float = 0.0


class LLMBatchScheduler:
    """Raggruppa chiamate LLM indipendenti in batch per efficienza.

    SOTA 2026: Esegue richieste indipendenti in parallelo invece che sequenzialmente.
    """

    def __init__(
        self,
        provider: LLMProvider | None = None,
        max_concurrent: int = 5,
    ):
        self._provider = provider
        self._max_concurrent = max_concurrent
        self._stats = BatchStats()
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def batch_generate(
        self,
        requests: list[LLMRequest],
    ) -> list[LLMResponse | Exception]:
        """Esegui richieste indipendenti in parallelo.

        Args:
            requests: Lista di richieste LLM indipendenti

        Returns:
            Lista di risposte o eccezioni (ordine preservato)
        """
        if not requests:
            return []

        self._stats.total_requests += len(requests)

        async def _execute_with_semaphore(
            request: LLMRequest, idx: int
        ) -> tuple[int, LLMResponse | Exception]:
            async with self._semaphore:
                start_time = time.time()
                try:
                    if self._provider is None:
                        raise ValueError("No LLM provider configured")
                    response = await self._provider.generate_response(request)
                    latency = (time.time() - start_time) * 1000
                    self._stats.successful_requests += 1
                    self._stats.total_latency_ms += latency
                    return idx, response
                except Exception as e:
                    self._stats.failed_requests += 1
                    logger.warning(
                        "batch_request_failed",
                        index=idx,
                        error=str(e),
                    )
                    return idx, e

        tasks = [_execute_with_semaphore(request, idx) for idx, request in enumerate(requests)]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        ordered_results: list[LLMResponse | Exception] = [None] * len(requests)
        for result in results:
            if isinstance(result, Exception):
                logger.error("batch_task_exception", error=str(result))
                continue
            idx, response = result
            ordered_results[idx] = response

        return ordered_results

    async def batch_generate_streaming(
        self,
        requests: list[LLMRequest],
    ) -> list[AsyncGenerator[LLMChunk, None] | Exception]:
        """Esegui richieste streaming in parallelo.

        Returns:
            Lista di generatori async o eccezioni
        """
        if not requests:
            return []

        self._stats.total_requests += len(requests)

        results: list[AsyncGenerator[LLMChunk, None] | Exception] = []

        for request in requests:
            try:
                if self._provider is None:
                    raise ValueError("No LLM provider configured")
                stream = self._provider.stream_response(request)
                results.append(stream)
                self._stats.successful_requests += 1
            except Exception as e:
                self._stats.failed_requests += 1
                results.append(e)

        return results

    def get_stats(self) -> BatchStats:
        """Statistiche del batch scheduler."""
        return BatchStats(
            total_requests=self._stats.total_requests,
            successful_requests=self._stats.successful_requests,
            failed_requests=self._stats.failed_requests,
            total_latency_ms=self._stats.total_latency_ms,
        )


_batch_scheduler: LLMBatchScheduler | None = None


def get_batch_scheduler() -> LLMBatchScheduler:
    """Ottiene il singleton del batch scheduler."""
    global _batch_scheduler
    if _batch_scheduler is None:
        _batch_scheduler = LLMBatchScheduler()
    return _batch_scheduler
