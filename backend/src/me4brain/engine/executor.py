"""Parallel Executor - Execute tools concurrently with error handling.

The executor is responsible for:
1. Running multiple tools in parallel using asyncio.gather
2. Managing timeouts per-tool
3. Isolating failures (one tool failure doesn't affect others)
4. Optional retry logic
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import structlog

from me4brain.engine.catalog import ToolCatalog
from me4brain.engine.types import ToolResult, ToolTask

logger = structlog.get_logger(__name__)

# =============================================================================
# Dependency Detection Configuration
# =============================================================================
# Tools that CONSUME content from other tools (need results to populate params)
# Format: tool_name -> parameter that needs content
CONTENT_CONSUMER_TOOLS: dict[str, str] = {
    "google_docs_create": "content",
    "google_docs_insert_text": "text",
    "google_sheets_update_values": "values",
    "google_gmail_send": "body",
    "google_gmail_reply": "body",
}

# Tools that PRODUCE content (search, retrieval, analysis tools)
# These should execute BEFORE consumer tools
CONTENT_PRODUCER_PATTERNS: frozenset[str] = frozenset(
    {
        "-search",  # All marketplace search skills
        "_search",  # google_drive_search, google_gmail_search, etc.
        "_list",  # google_calendar_list, google_drive_list_files
        "_get",  # google_drive_get_content, google_docs_get
        "aggregator",
        "tavily_",
        "duckduckgo_",
        "smart_search",
        "coingecko_",
        "fmp_",
        "technical_",
        "aviationstack_",
        "amadeus_",
    }
)


class ParallelExecutor:
    """Executes tools in parallel with robust error handling.

    Features:
    - asyncio.gather for true parallelism
    - Per-tool timeout (default 10s)
    - Retry on failure (configurable)
    - Dual-semaphore concurrency limiting (per-session + global)
    - Error isolation (one failure doesn't block others)
    - Permission validation with HITL support

    Example:
        executor = ParallelExecutor(catalog)
        results = await executor.execute([
            ToolTask(tool_name="coingecko_price", arguments={"ids": "bitcoin"}),
            ToolTask(tool_name="openmeteo_weather", arguments={"city": "Roma"}),
        ])
        # Both run in parallel, results returned in same order
    """

    def __init__(
        self,
        catalog: ToolCatalog,
        timeout_seconds: float = 120.0,
        max_retries: int = 1,
        max_concurrent: int = 5,
        max_global_concurrent: int = 20,
        hitl_callback: Callable[[str, str, dict], Any] | None = None,
    ) -> None:
        """Initialize executor.

        Args:
            catalog: Tool catalog with executors
            timeout_seconds: Maximum time per tool execution
            max_retries: Number of retries on failure (0 = no retry)
            max_concurrent: Maximum concurrent tool executions per session
            max_global_concurrent: Maximum concurrent tool executions globally
            hitl_callback: Async callback for HITL approval (tool_name, message, args) -> bool
        """
        self._catalog = catalog
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._hitl_callback = hitl_callback

        # FIX Issue #2: Dual-semaphore pattern for session isolation
        self._max_per_session = max_concurrent
        self._global_semaphore = asyncio.Semaphore(max_global_concurrent)
        self._session_semaphores: dict[str, asyncio.Semaphore] = {}
        self._session_last_used: dict[str, float] = {}  # For cleanup

        # Lazy load permission validator
        self._permission_validator = None

    def _get_permission_validator(self):
        """Lazy load permission validator."""
        if self._permission_validator is None:
            from me4brain.engine.permission_validator import get_permission_validator

            self._permission_validator = get_permission_validator()
        return self._permission_validator

    def _get_session_semaphore(self, session_id: str | None = None) -> asyncio.Semaphore:
        """Get or create a per-session semaphore.

        FIX Issue #2: Each session gets its own Semaphore so long-running
        sessions don't starve other sessions.

        Args:
            session_id: Session identifier. Falls back to contextvars if None.

        Returns:
            Session-scoped asyncio.Semaphore
        """
        if session_id is None:
            from me4brain.engine.session_context import get_current_session_id

            session_id = get_current_session_id() or "_global_"

        if session_id not in self._session_semaphores:
            self._session_semaphores[session_id] = asyncio.Semaphore(self._max_per_session)
            logger.debug(
                "session_semaphore_created", session_id=session_id, limit=self._max_per_session
            )

        self._session_last_used[session_id] = time.monotonic()

        # Periodic cleanup of stale semaphores (> 5 min idle)
        self._cleanup_stale_semaphores()

        return self._session_semaphores[session_id]

    def _cleanup_stale_semaphores(self) -> None:
        """Remove semaphores for sessions idle > 5 minutes."""
        now = time.monotonic()
        stale_threshold = 300  # 5 minutes
        stale_keys = [
            sid
            for sid, last_used in self._session_last_used.items()
            if now - last_used > stale_threshold
        ]
        for sid in stale_keys:
            del self._session_semaphores[sid]
            del self._session_last_used[sid]
            logger.debug("session_semaphore_cleaned", session_id=sid)

    def _deduplicate_tasks(self, tasks: list[ToolTask]) -> list[ToolTask]:
        """Rimuovi tasks duplicati basandosi su tool_name + arguments (chiavi ordinate).

        Returns:
            Lista unica di tasks, preservando l'ordine originale (prima occorrenza vince)
        """
        seen: set[tuple[str, frozenset[tuple[str, Any]]]] = set()
        unique: list[ToolTask] = []

        for task in tasks:
            # Creiamo una chiave stabile: tool name + frozenset degli argomenti ordinati
            args_items = tuple(sorted(task.arguments.items()))
            key = (task.tool_name, args_items)

            if key not in seen:
                seen.add(key)
                unique.append(task)
            else:
                logger.debug(
                    "duplicate_task_skipped",
                    tool_name=task.tool_name,
                    arguments=task.arguments,
                )
                logger.debug(
                    "duplicate_task_skipped",
                    tool_name=task.tool_name,
                    arguments=task.arguments,
                )

        if len(unique) < len(tasks):
            logger.info(
                "tasks_deduplicated",
                original_count=len(tasks),
                unique_count=len(unique),
                duplicates_removed=len(tasks) - len(unique),
            )

        return unique

    async def execute(
        self,
        tasks: list[ToolTask],
        session_id: str | None = None,
    ) -> list[ToolResult]:
        """Execute tasks with dependency detection.

        For queries like "search X and save to Google Docs", this method:
        1. Detects content dependencies (consumer tools with empty content params)
        2. Executes producer tools first (search, retrieval)
        3. Injects producer results into consumer tools
        4. Executes consumer tools with populated content

        Args:
            tasks: List of ToolTask objects to execute
            session_id: Optional session ID for per-session concurrency limiting

        Returns:
            List of ToolResult objects in the same order as tasks.
            Each result contains success/failure status and data/error.
        """
        if not tasks:
            return []

        original_task_count = len(tasks)
        tasks = self._deduplicate_tasks(tasks)
        if not tasks:
            logger.info("executor_no_tasks_after_deduplication")
            return []

        logger.info(
            "executor_starting",
            task_count=len(tasks),
            tool_names=[t.tool_name for t in tasks],
            tasks_deduplicated=original_task_count > len(tasks),
            original_count=original_task_count,
        )

        start_time = time.monotonic()
        session_sem = self._get_session_semaphore(session_id)

        producers, consumers, independent = self._split_by_dependency(tasks)

        if consumers and producers:
            logger.info(
                "executor_dependency_mode",
                producers_count=len(producers),
                consumers_count=len(consumers),
                independent_count=len(independent),
            )

            producer_results_raw = await asyncio.gather(
                *[self._execute_single(task, session_sem) for task in producers],
                return_exceptions=True,
            )
            producer_results = self._convert_exceptions_to_results(producers, producer_results_raw)

            aggregated_content = self._aggregate_producer_results(producers, producer_results)

            if aggregated_content:
                enriched_consumers = self._inject_content_to_consumers(
                    consumers, aggregated_content
                )
            else:
                enriched_consumers = consumers

            consumer_results_raw = await asyncio.gather(
                *[self._execute_single(task, session_sem) for task in enriched_consumers],
                return_exceptions=True,
            )
            consumer_results = self._convert_exceptions_to_results(consumers, consumer_results_raw)

            independent_results_raw = await asyncio.gather(
                *[self._execute_single(task, session_sem) for task in independent],
                return_exceptions=True,
            )
            independent_results = self._convert_exceptions_to_results(
                independent, independent_results_raw
            )

            results = producer_results + consumer_results + independent_results

        else:
            raw_results = await asyncio.gather(
                *[self._execute_single(task, session_sem) for task in tasks],
                return_exceptions=True,
            )
            results = self._convert_exceptions_to_results(tasks, raw_results)

        total_time = (time.monotonic() - start_time) * 1000
        success_count = sum(1 for r in results if r.success)
        logger.info(
            "executor_complete",
            total_tasks=len(tasks),
            successful=success_count,
            failed=len(tasks) - success_count,
            total_latency_ms=round(total_time, 2),
        )

        return results

    def _convert_exceptions_to_results(
        self,
        tasks: list[ToolTask],
        raw_results: list[ToolResult | BaseException],
    ) -> list[ToolResult]:
        """Convert raw results from gather, handling exceptions."""
        results: list[ToolResult] = []
        for i, r in enumerate(raw_results):
            task = tasks[i] if i < len(tasks) else None
            if isinstance(r, Exception):
                logger.error(
                    "executor_task_unhandled_exception",
                    tool_name=task.tool_name if task else "unknown",
                    error=str(r),
                    error_type=type(r).__name__,
                )
                results.append(
                    ToolResult(
                        tool_name=task.tool_name if task else "unknown",
                        success=False,
                        error=f"Unexpected error: {r}",
                        call_id=task.call_id if task else None,
                    )
                )
            else:
                results.append(r)
        return results

    def _split_by_dependency(
        self, tasks: list[ToolTask]
    ) -> tuple[list[ToolTask], list[ToolTask], list[ToolTask]]:
        """Split tasks into producers, consumers, and independent.

        Returns:
            Tuple of (producers, consumers, independent) task lists
        """
        producers: list[ToolTask] = []
        consumers: list[ToolTask] = []
        independent: list[ToolTask] = []

        for task in tasks:
            tool_name = task.tool_name

            # Check if this is a consumer with empty content
            if tool_name in CONTENT_CONSUMER_TOOLS:
                content_param = CONTENT_CONSUMER_TOOLS[tool_name]
                content_value = task.arguments.get(content_param, "")

                # Consumer with empty/missing content -> needs dependency injection
                if not content_value or content_value == "":
                    consumers.append(task)
                    continue

            # Check if this is a producer
            is_producer = any(pattern in tool_name for pattern in CONTENT_PRODUCER_PATTERNS)
            if is_producer:
                producers.append(task)
            else:
                independent.append(task)

        if consumers:
            logger.info(
                "dependency_detected",
                producers=[t.tool_name for t in producers],
                consumers=[t.tool_name for t in consumers],
                independent=[t.tool_name for t in independent],
            )

        return producers, consumers, independent

    def _aggregate_producer_results(
        self,
        producers: list[ToolTask],
        results: list[ToolResult | None],
    ) -> str:
        """Aggregate successful producer results into content string."""
        import json

        content_parts: list[str] = []

        for task, result in zip(producers, results, strict=False):
            if result and result.success and result.data:
                # Format result based on type
                if isinstance(result.data, str):
                    content_parts.append(f"## {task.tool_name}\n{result.data}")
                elif isinstance(result.data, dict):
                    # Pretty format dict data
                    formatted = json.dumps(result.data, indent=2, ensure_ascii=False)
                    content_parts.append(f"## {task.tool_name}\n```json\n{formatted}\n```")
                elif isinstance(result.data, list):
                    # Format list items
                    items = "\n".join(f"- {item}" for item in result.data[:20])
                    content_parts.append(f"## {task.tool_name}\n{items}")

        return "\n\n".join(content_parts) if content_parts else ""

    def _inject_content_to_consumers(
        self,
        consumers: list[ToolTask],
        content: str,
    ) -> list[ToolTask]:
        """Create new ToolTask objects with content injected."""
        if not content:
            return consumers  # No content to inject

        enriched: list[ToolTask] = []

        for task in consumers:
            content_param = CONTENT_CONSUMER_TOOLS.get(task.tool_name)
            if content_param:
                # Create new arguments dict with content
                new_args = dict(task.arguments)
                new_args[content_param] = content

                enriched.append(
                    ToolTask(
                        tool_name=task.tool_name,
                        arguments=new_args,
                        call_id=task.call_id,
                    )
                )

                logger.debug(
                    "content_injected",
                    tool=task.tool_name,
                    param=content_param,
                    content_length=len(content),
                )
            else:
                enriched.append(task)

        return enriched

    async def execute_single(
        self,
        task: ToolTask,
    ) -> ToolResult:
        """Execute a single task (public interface).

        Args:
            task: Single ToolTask to execute

        Returns:
            ToolResult with execution outcome
        """
        return await self._execute_single(task)

    async def _execute_single(
        self,
        task: ToolTask,
        session_semaphore: asyncio.Semaphore | None = None,
    ) -> ToolResult:
        """Execute a single tool with timeout and retry.

        Args:
            task: ToolTask to execute
            session_semaphore: Per-session semaphore for concurrency limiting

        Returns:
            ToolResult with success/failure
        """
        # FIX Issue #2: Dual-semaphore — acquire both session + global
        sem = session_semaphore or self._get_session_semaphore()
        async with sem, self._global_semaphore:
            # Step 0: Permission validation (isolated — crash here must not
            # escape _execute_single and cascade through asyncio.gather)
            try:
                perm_validator = self._get_permission_validator()
                perm_result = perm_validator.validate(task.tool_name, task.arguments)
            except Exception as e:
                logger.error(
                    "perm_validation_error",
                    tool_name=task.tool_name,
                    error=str(e),
                )
                # Fallthrough: prefer execution over blocking on validator bug
                from me4brain.engine.permission_validator import (
                    PermissionLevel,
                    PermissionResult,
                )

                perm_result = PermissionResult(permission_level=PermissionLevel.ALLOW)

            from me4brain.engine.permission_validator import PermissionLevel

            # DENY - Block immediately
            if perm_result.permission_level == PermissionLevel.DENY:
                logger.warning(
                    "executor_tool_denied",
                    tool_name=task.tool_name,
                    reason=perm_result.reason,
                )
                return ToolResult(
                    tool_name=task.tool_name,
                    success=False,
                    error=f"⛔ Azione bloccata: {perm_result.reason}",
                    call_id=task.call_id,
                )

            # CONFIRM - Require HITL approval
            if perm_result.permission_level == PermissionLevel.CONFIRM:
                if self._hitl_callback:
                    try:
                        approved = await self._hitl_callback(
                            task.tool_name,
                            perm_result.approval_message,
                            task.arguments,
                        )
                        if not approved:
                            logger.info(
                                "executor_tool_rejected_by_user",
                                tool_name=task.tool_name,
                            )
                            return ToolResult(
                                tool_name=task.tool_name,
                                success=False,
                                error="❌ Azione rifiutata dall'utente",
                                call_id=task.call_id,
                            )
                    except Exception as e:
                        logger.error("executor_hitl_error", error=str(e))
                        return ToolResult(
                            tool_name=task.tool_name,
                            success=False,
                            error=f"Errore approvazione: {e}",
                            call_id=task.call_id,
                        )
                else:
                    # No HITL callback - block by default
                    logger.warning(
                        "executor_no_hitl_callback",
                        tool_name=task.tool_name,
                        message=perm_result.approval_message,
                    )
                    return ToolResult(
                        tool_name=task.tool_name,
                        success=False,
                        error=f"⚠️ Richiede approvazione: {perm_result.approval_message}",
                        call_id=task.call_id,
                    )

            # NOTIFY - Log but proceed
            if perm_result.permission_level == PermissionLevel.NOTIFY:
                logger.info(
                    "executor_tool_notify",
                    tool_name=task.tool_name,
                    message=perm_result.approval_message,
                )

            # Get executor from catalog
            executor = self._catalog.get_executor(task.tool_name)

            if not executor:
                logger.warning(
                    "executor_tool_not_found",
                    tool_name=task.tool_name,
                )
                return ToolResult(
                    tool_name=task.tool_name,
                    success=False,
                    error=f"Tool not found: {task.tool_name}",
                    call_id=task.call_id,
                )

            # Execute with retry
            last_error = None
            attempts = self._max_retries + 1  # +1 for initial attempt

            for attempt in range(attempts):
                try:
                    start_time = time.monotonic()

                    # Execute with timeout
                    result = await asyncio.wait_for(
                        self._call_executor(executor, task.arguments),
                        timeout=self._timeout,
                    )

                    latency = (time.monotonic() - start_time) * 1000

                    # Validate result
                    if result is None:
                        result = {}
                    elif not isinstance(result, dict):
                        result = {"result": result}

                    logger.debug(
                        "executor_tool_success",
                        tool_name=task.tool_name,
                        latency_ms=round(latency, 2),
                        attempt=attempt + 1,
                    )

                    return ToolResult(
                        tool_name=task.tool_name,
                        success=True,
                        data=result,
                        latency_ms=latency,
                        call_id=task.call_id,
                    )

                except TimeoutError:
                    last_error = f"Timeout after {self._timeout}s"
                    logger.warning(
                        "executor_tool_timeout",
                        tool_name=task.tool_name,
                        timeout=self._timeout,
                        attempt=attempt + 1,
                    )

                except Exception as e:
                    last_error = str(e)
                    logger.warning(
                        "executor_tool_error",
                        tool_name=task.tool_name,
                        error=str(e),
                        attempt=attempt + 1,
                        will_retry=attempt < attempts - 1,
                    )

                # Backoff before retry
                if attempt < attempts - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))

            # All attempts failed
            return ToolResult(
                tool_name=task.tool_name,
                success=False,
                error=last_error or "Unknown error",
                call_id=task.call_id,
            )

    async def _call_executor(
        self,
        executor: Callable[..., Any],
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Call the executor with arguments.

        Handles both sync and async executors.
        Filters out LLM-hallucinated parameters not in function signature.

        Args:
            executor: The executable function
            arguments: Arguments to pass

        Returns:
            Executor result as dict
        """
        import inspect

        # Filter arguments to only those the function accepts
        # LLMs often hallucinate extra parameters (e.g. 'max', 'team_id')
        try:
            sig = inspect.signature(executor)
            valid_params = set(sig.parameters.keys())
            # Check for **kwargs — if present, pass everything through
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            )
            if not has_var_keyword:
                filtered_args = {k: v for k, v in arguments.items() if k in valid_params}
                if len(filtered_args) < len(arguments):
                    ignored = set(arguments.keys()) - valid_params
                    logger.warning(
                        "executor_filtered_hallucinated_params",
                        executor=getattr(executor, "__name__", str(executor)),
                        ignored=sorted(ignored),
                        valid=sorted(valid_params),
                        hint="LLM generated parameters not in function signature",
                    )
            else:
                filtered_args = arguments
        except (ValueError, TypeError):
            # If signature inspection fails, pass through as-is
            filtered_args = arguments

        # Call executor with filtered arguments
        if asyncio.iscoroutinefunction(executor):
            result = await executor(**filtered_args)
        else:
            # Sync executor - run in thread pool
            loop = asyncio.get_event_loop()
            _args = filtered_args  # Capture for lambda
            result = await loop.run_in_executor(
                None,
                lambda: executor(**_args),
            )

        return result

    async def execute_direct(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Execute a tool directly by name.

        Convenience method for direct tool execution.

        Args:
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            ToolResult
        """
        task = ToolTask(tool_name=tool_name, arguments=arguments)
        return await self._execute_single(task)
