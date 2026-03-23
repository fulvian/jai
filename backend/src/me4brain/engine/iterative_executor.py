"""Iterative Executor - ReAct pattern implementation.

Executes tool calls step-by-step instead of all at once.
Each step selects a small subset of tools (max 10) relevant to that step.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from me4brain.engine.executor import ParallelExecutor
from me4brain.engine.hybrid_router.types import RetrievedTool, SubQuery
from me4brain.engine.prompts.registry import PromptHintsRegistry
from me4brain.engine.types import ToolResult, ToolTask
from me4brain.llm.provider_factory import resolve_model_client
from me4brain.utils.json_utils import robust_json_parse

if TYPE_CHECKING:
    from me4brain.engine.hybrid_router.llama_tool_retriever import LlamaIndexToolRetriever
    from me4brain.llm import NanoGPTClient

logger = structlog.get_logger(__name__)


@dataclass
class StepResult:
    """Result from executing a single step."""

    step_id: int
    sub_query: str
    domain: str
    tools_selected: list[str]
    tool_results: list[ToolResult]
    execution_time_ms: float


@dataclass
class ExecutionContext:
    """Accumulates results across all steps."""

    original_query: str
    step_results: list[StepResult] = field(default_factory=list)

    def add_step(self, result: StepResult) -> None:
        """Add a step result to context."""
        self.step_results.append(result)

    def get_context_summary(self) -> str:
        """Get enriched summary of completed steps for inter-step chaining.

        Includes both a human-readable summary AND structured key data
        (file IDs, email IDs, event IDs, folder IDs) that the next step
        can use to parameterize tool calls.
        """
        if not self.step_results:
            return ""

        parts = ["### Risultati dei passaggi precedenti:\n"]
        key_ids: list[str] = []  # Collect structured IDs for chaining

        for sr in self.step_results:
            parts.append(f"**Step {sr.step_id}** ({sr.domain}): {sr.sub_query[:150]}")
            if sr.tool_results:
                for tr in sr.tool_results:
                    if tr.success:
                        result_str = str(tr.data)
                        # More generous truncation to preserve structured data
                        result_preview = result_str[:2000]
                        parts.append(f"  - {tr.tool_name}: {result_preview}")
                        # Extract key IDs from structured results for chaining
                        extracted = self._extract_key_ids(tr.data, tr.tool_name)
                        key_ids.extend(extracted)
                    else:
                        parts.append(f"  - {tr.tool_name}: ERROR - {tr.error}")
            parts.append("")

        # Append structured IDs section for easy chaining
        if key_ids:
            parts.append("### Dati chiave disponibili per i prossimi passaggi:")
            for kid in key_ids[:30]:  # Cap to avoid context overflow
                parts.append(f"  - {kid}")
            parts.append("")

        return "\n".join(parts)

    # Mapping from tool-domain to the parameter name expected by the detail tool
    _ID_PARAM_MAP: ClassVar[dict[str, str]] = {
        "google_drive_search": "file_id",
        "google_drive_list_files": "file_id",
        "google_gmail_search": "message_id",
        "google_gmail_list": "message_id",
        "google_calendar_list_events": "event_id",
        "google_calendar_search_events": "event_id",
    }

    @staticmethod
    def _extract_key_ids(data: any, tool_name: str) -> list[str]:
        """Extract actionable IDs from tool results for inter-step chaining.

        Returns structured, unambiguous ID references that the LLM can
        directly copy into tool call parameters.

        Format: 'param_name="ID_VALUE" (display_name)'
        Example: 'file_id="1m4BUTb38DR..." (Report_Finale_...)'
        """
        ids: list[str] = []
        if not data:
            return ids

        # Determine the correct parameter name for the detail tool
        param_name = ExecutionContext._ID_PARAM_MAP.get(tool_name, "id")

        def _scan(obj: any, depth: int = 0) -> None:
            if depth > 4:  # Prevent deep recursion
                return
            if isinstance(obj, dict):
                # Look for common ID fields
                for key in (
                    "id",
                    "file_id",
                    "message_id",
                    "event_id",
                    "folder_id",
                    "doc_id",
                    "threadId",
                ):
                    if key in obj:
                        id_value = str(obj[key])
                        name = obj.get("name", obj.get("title", obj.get("subject", "")))
                        # Use the correct parameter name for the detail tool
                        effective_param = param_name if key == "id" else key
                        label = f'{effective_param}="{id_value}"'
                        if name:
                            label += f" (name: {name})"
                        ids.append(label)
                for v in obj.values():
                    _scan(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj[:20]:  # Cap list scanning
                    _scan(item, depth + 1)

        _scan(data)
        return ids

    def get_all_tool_results(self) -> list[ToolResult]:
        """Get all tool results from all steps."""
        results = []
        for sr in self.step_results:
            results.extend(sr.tool_results)
        return results

    def get_all_tasks(self) -> list[ToolTask]:
        """Get all tool tasks that were executed."""
        tasks = []
        for sr in self.step_results:
            for tr in sr.tool_results:
                # Reconstruct task from result - ToolResult doesn't have arguments,
                # so we just record the tool name for tracking purposes
                tasks.append(
                    ToolTask(
                        tool_name=tr.tool_name,
                        arguments={},  # ToolResult doesn't store original arguments
                    )
                )
        return tasks


class IterativeExecutor:
    """Executes sub-queries iteratively using ReAct pattern.

    Instead of sending 75 tools at once, this executor:
    1. Takes each sub-query from the planner
    2. Retrieves only 5-10 relevant tools for that sub-query
    3. Calls LLM to select and parameterize tools
    4. Executes selected tools
    5. Adds results to context
    6. Moves to next sub-query

    This keeps each LLM call under ~10 tools, avoiding provider limits.
    """

    MAX_TOOLS_PER_STEP = 10  # Hard limit per step
    MAX_OBSERVE_ITERATIONS = 3  # Max ReAct observe-retry loops per step
    STEP_TIMEOUT_SECONDS = 900  # 15 min per step (ReAct + multi-tool + DEEPER)

    def __init__(
        self,
        llm_client: NanoGPTClient,
        retriever: LlamaIndexToolRetriever,
        executor: ParallelExecutor,
        model: str = "qwen3.5:4b",
        tool_calling_llm: Optional[LLMProvider] = None,
        tool_calling_model: Optional[str] = None,
        context_window: int = 32768,
    ):
        self._llm = llm_client
        self._retriever = retriever
        self._executor = executor
        self._model = model
        self._context_window = context_window
        self._tc_llm = tool_calling_llm or llm_client
        self._tc_model = tool_calling_model or model
        self._registry = PromptHintsRegistry()
        self._total_tokens_used = 0
        self._hints_cache: dict[str, dict[str, Any]] = {}
        from me4brain.engine.context_compressor import (
            AdaptiveContextCompressor,
            ContextWindowTracker,
        )

        self._compressor = AdaptiveContextCompressor(
            context_window=context_window,
            llm_provider=llm_client,
        )
        self._context_tracker = ContextWindowTracker(model_context_window=context_window)

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def _compress_tool_result(self, result: ToolResult, sub_query: str) -> ToolResult:
        """Compress tool result using trajectory reduction (SOTA 2026).

        Rules:
        - Results <500 chars: no compression
        - 500-2000 chars: extract key fields only
        - >2000 chars: quick summary (no LLM for speed)
        """
        data_str = str(result.data) if result.data else ""
        if len(data_str) < 500:
            return result

        compressed_data = result.data
        if len(data_str) < 2000:
            compressed_data = self._extract_essential_fields(result.data)
        else:
            compressed_data = {
                "_summary": self._quick_summarize_data(result.data, result.tool_name),
                "_key_ids": self._extract_all_ids(result.data),
                "_original_size": len(data_str),
            }

        return ToolResult(
            tool_name=result.tool_name,
            success=result.success,
            data=compressed_data,
            error=result.error,
            latency_ms=result.latency_ms,
        )

    def _extract_essential_fields(self, data: Any) -> dict[str, Any]:
        """Extract essential fields from structured data."""
        if not isinstance(data, dict):
            return data

        essential = {}
        key_fields = [
            "id",
            "name",
            "title",
            "subject",
            "from",
            "to",
            "date",
            "time",
            "status",
            "count",
            "total",
            "error",
            "message",
            "temperature",
            "description",
            "price",
            "currency",
        ]
        for key in key_fields:
            if key in data:
                essential[key] = data[key]

        list_keys = ["results", "events", "files", "messages", "emails", "items"]
        for key in list_keys:
            if key in data and isinstance(data[key], list):
                essential[key] = data[key][:5]
                essential[f"{key}_count"] = len(data[key])

        return essential if essential else data

    def _quick_summarize_data(self, data: Any, tool_name: str) -> str:
        """Quick summarization without LLM."""
        data_str = str(data)
        ids = self._extract_all_ids(data)
        summary_parts = [f"[{tool_name}]"]

        if ids:
            summary_parts.append(f"IDs: {', '.join(ids[:5])}")

        counts = re.findall(r"\b(\d+)\s+(file|email|event|item|result|message)s?\b", data_str)
        if counts:
            for count, item_type in counts[:3]:
                summary_parts.append(f"{count} {item_type}")

        first_sentence = data_str[:200].split(".")[0]
        if first_sentence:
            summary_parts.append(first_sentence[:100])

        return " | ".join(summary_parts)

    def _extract_all_ids(self, data: Any) -> list[str]:
        """Extract all IDs from data."""
        ids = []
        id_patterns = [
            r'"id":\s*"([^"]+)"',
            r'"file_id":\s*"([^"]+)"',
            r'"message_id":\s*"([^"]+)"',
            r'"event_id":\s*"([^"]+)"',
        ]
        data_str = str(data)
        for pattern in id_patterns:
            matches = re.findall(pattern, data_str)
            ids.extend(matches)
        return list(dict.fromkeys(ids))[:10]

    def _try_extract_valid_json(self, raw_text: str) -> dict | None:
        """Extract and parse JSON with robust repair strategies.

        Uses json_utils.robust_json_parse for multi-strategy parsing,
        then normalizes quoted keys for agentic tool calls.
        """
        if not raw_text or len(raw_text.strip()) < 2:
            return None

        parsed = robust_json_parse(raw_text, expect_object=True)

        if parsed is None:
            return None

        normalized = self._normalize_quoted_keys(parsed)
        return normalized if normalized else None

    def _normalize_quoted_keys(self, obj: Any) -> Any:
        """Recursively normalize literally quoted keys like {\"query\": \"value\"}."""
        if isinstance(obj, dict):
            normalized = {}
            for key, value in obj.items():
                clean_key = str(key)
                # Iteratively strip quotes/backslashes
                while True:
                    prev = clean_key
                    clean_key = clean_key.strip("\"'\\")
                    if clean_key == prev:
                        break

                normalized[clean_key] = self._normalize_quoted_keys(value)
            return normalized
        elif isinstance(obj, list):
            return [self._normalize_quoted_keys(item) for item in obj]
        elif isinstance(obj, str):
            # Strip outer quotes from string values if they exist
            if (obj.startswith('"') and obj.endswith('"')) or (
                obj.startswith("'") and obj.endswith("'")
            ):
                return obj[1:-1]
            return obj
        return obj

    async def execute_plan(
        self,
        sub_queries: list[SubQuery],
        original_query: str,
        context_str: str | None = None,
    ) -> ExecutionContext:
        """Execute all sub-queries iteratively.

        Args:
            sub_queries: List of sub-queries from the planner
            original_query: The original user query
            context_str: Optional additional context

        Returns:
            ExecutionContext with all step results
        """
        import time

        exec_context = ExecutionContext(original_query=original_query)

        logger.info(
            "iterative_execution_started",
            total_steps=len(sub_queries),
            original_query_preview=original_query[:50],
        )

        for i, sq in enumerate(sub_queries):
            step_start = time.time()

            try:
                step_result = await self._execute_step(
                    step_id=i + 1,
                    sub_query=sq,
                    exec_context=exec_context,
                    context_str=context_str,
                )

                exec_context.add_step(step_result)

                logger.info(
                    "iterative_step_completed",
                    step_id=i + 1,
                    sub_query_preview=sq.text[:50],
                    tools_executed=len(step_result.tool_results),
                    execution_time_ms=step_result.execution_time_ms,
                )

            except Exception as e:
                logger.error(
                    "iterative_step_failed",
                    step_id=i + 1,
                    error=str(e),
                )
                # Create empty step result to continue
                exec_context.add_step(
                    StepResult(
                        step_id=i + 1,
                        sub_query=sq.text,
                        domain=sq.domain,
                        tools_selected=[],
                        tool_results=[],
                        execution_time_ms=(time.time() - step_start) * 1000,
                    )
                )

        logger.info(
            "iterative_execution_completed",
            total_steps=len(sub_queries),
            total_tools_executed=len(exec_context.get_all_tool_results()),
            total_tokens_estimated=self._total_tokens_used,
            cache_hits=getattr(self, "_cache_hits", 0),
        )

        return exec_context

    # =========================================================================
    # Streaming version
    # =========================================================================

    # User-friendly messages per domain
    _DOMAIN_MESSAGES: dict[str, tuple[str, str]] = {
        # domain → (active_message, icon)
        "google_workspace": ("Esploro il tuo spazio di lavoro", "🏢"),
        "finance_crypto": ("Analizzo mercati e asset", "📈"),
        "productivity": ("Organizzo le tue attività", "⏱️"),
        "geo_weather": ("Controllo meteo e geodata", "🌤️"),
        "web_search": ("Cerco informazioni sul web", "🌐"),
        "travel": ("Organizzo il tuo viaggio", "✈️"),
        "food": ("Cerco cibo e ristoranti", "🍽️"),
        "entertainment": ("Cerco intrattenimento", "🎭"),
        "sports_booking": ("Cerco disponibilità campi", "🎾"),
        "sports_nba": ("Analizzo statistiche NBA", "🏀"),
        "shopping": ("Cerco prodotti e prezzi", "🛒"),
        "tech_coding": ("Analizzo logica e codice", "💻"),
        "medical": ("Cerco informazioni mediche", "🏥"),
        "science_research": ("Consulto basi scientifiche", "🔬"),
        "knowledge_media": ("Esploro notizie e media", "📰"),
        "jobs": ("Cerco opportunità di lavoro", "💼"),
        "utility": ("Eseguo utility di sistema", "⚙️"),
    }

    # Tool name → result description for common tools
    _TOOL_RESULT_MESSAGES: dict[str, str] = {
        "google_gmail_search": "{count} email trovate",
        "google_gmail_read": "Email letta",
        "google_calendar_list_events": "{count} eventi trovati",
        "google_calendar_create_event": "Evento creato",
        "google_drive_list_files": "{count} file trovati",
        "google_drive_copy": "File copiato",
        "google_docs_create": "Documento creato",
        "google_sheets_create": "Foglio creato",
        "google_slides_create": "Presentazione creata",
        "google_meet_list_conferences": "{count} riunioni trovate",
        "coingecko_price": "Prezzi ottenuti",
        "openmeteo_weather": "Meteo ottenuto",
    }

    # Intent-to-Tool explicit mapping to bypass retriever inaccuracy
    _INTENT_TOOL_MAP: dict[str, list[str]] = {
        "drive_search": ["google_drive_search"],
        "file_search": ["google_drive_search"],
        "file_read": ["google_drive_get_content"],
        "gmail_search": ["google_gmail_search"],
        "email_search": ["google_gmail_search"],
        "calendar_search": ["google_calendar_list_events"],
        "meet_search": ["google_meet_list_conferences"],
        "content_creation": ["google_docs_create", "google_sheets_create"],
        "workspace_report": ["google_workspace_report"],
        # Weather/Geo domain
        "weather_query": ["openmeteo_weather"],
        "geo_weather": ["openmeteo_weather"],
        "meteo": ["openmeteo_weather"],
        # Finance domain
        "crypto_price": ["coingecko_price"],
        "finance_query": ["coingecko_price"],
        # Web search
        "web_search": ["duckduckgo_search"],
        "search_query": ["duckduckgo_search"],
    }

    def _get_step_message(self, domain: str) -> tuple[str, str]:
        """Get user-friendly message and icon for a domain."""
        return self._DOMAIN_MESSAGES.get(domain, ("Sto elaborando la richiesta", "🔄"))

    # Tool name prefix → evocative icon
    _TOOL_ICON_MAP: ClassVar[list[tuple[str, str]]] = [
        ("google_gmail", "📧"),
        ("google_drive", "📁"),
        ("google_calendar", "📅"),
        ("google_docs", "📝"),
        ("google_sheets", "📊"),
        ("google_slides", "📊"),
        ("google_meet", "🎥"),
        ("duckduckgo", "🌐"),
        ("openmeteo", "🌤️"),
        ("coingecko", "💰"),
        ("playtomic", "🎾"),
        ("skyscanner", "✈️"),
        ("thefork", "🍽️"),
    ]

    def _get_tool_icon(self, tool_name: str) -> str:
        """Get evocative icon for a tool based on its name."""
        for prefix, icon in self._TOOL_ICON_MAP:
            if tool_name.startswith(prefix):
                return icon
        return "✅"  # Fallback for unknown tools

    def _get_tool_result_summary(self, tool_result: ToolResult) -> str | None:
        """Generate user-friendly result summary from tool result.

        Returns None for zero-count results (to be filtered out by caller).
        """
        if not tool_result.success:
            # Include tool name and error hint for diagnostics
            tool_short = tool_result.tool_name.replace("google_", "")
            error_hint = ""
            if tool_result.error:
                error_hint = f": {tool_result.error[:60]}"
            return f"{tool_short} fallito{error_hint}"

        template = self._TOOL_RESULT_MESSAGES.get(tool_result.tool_name)
        if template and tool_result.data:
            # Try to count items in result
            count = 0
            if isinstance(tool_result.data, dict):
                for key in (
                    "results",
                    "events",
                    "files",
                    "messages",
                    "emails",
                    "items",
                    "conferences",
                    "documents",
                ):
                    if key in tool_result.data:
                        val = tool_result.data[key]
                        count = len(val) if isinstance(val, list) else 0
                        break
                # Fallback: check 'count' key directly
                if count == 0 and "count" in tool_result.data:
                    count = tool_result.data["count"]
            elif isinstance(tool_result.data, list):
                count = len(tool_result.data)

            # Skip zero-count results (e.g. "0 file trovati" is not useful)
            if count == 0:
                return None

            return template.format(count=count)

        # Provide tool-specific descriptive message instead of generic "Completato"
        tool_name = tool_result.tool_name
        _TOOL_DESCRIPTIONS: dict[str, str] = {
            "google_gmail_read": "Email letta",
            "google_drive_copy": "File copiato",
            "google_drive_get_content": "Contenuto analizzato",
            "google_docs_create": "Documento creato",
            "google_docs_write": "Documento aggiornato",
            "google_sheets_create": "Foglio creato",
            "google_slides_create": "Presentazione creata",
            "duckduckgo_search": "Ricerca completata",
            "coingecko_price": "Prezzi ottenuti",
            "openmeteo_weather": "Meteo ottenuto",
        }
        return _TOOL_DESCRIPTIONS.get(tool_name, "Completato")

    async def execute_plan_stream(
        self,
        sub_queries: list[SubQuery],
        original_query: str,
        context_str: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute all sub-queries iteratively, yielding SSE progress events.

        Yields dicts with:
            type: 'step_start' | 'tool_executing' | 'tool_complete' |
                  'step_complete' | 'error'
            + type-specific fields (step, total, message, icon, etc.)

        Returns the ExecutionContext via a final 'execution_done' event.
        """
        import time

        from me4brain.engine.session_context import get_current_session_id

        # FIX Issue #6: Log session_id to verify propagation through async tasks
        current_session_id = get_current_session_id()
        logger.info(
            "execute_plan_stream_start",
            session_id=current_session_id,
            sub_queries_count=len(sub_queries),
            original_query_preview=original_query[:50],
        )

        exec_context = ExecutionContext(original_query=original_query)
        total_steps = len(sub_queries)

        for i, sq in enumerate(sub_queries):
            step_start = time.time()
            step_num = i + 1
            msg, icon = self._get_step_message(sq.domain)

            # Yield step_start with actual sub-query context
            # Truncate sub-query for user display
            sub_query_short = sq.text[:80].rstrip()
            if len(sq.text) > 80:
                sub_query_short += "..."
            yield {
                "type": "step_start",
                "step": step_num,
                "total": total_steps,
                "message": f"{msg}: {sub_query_short}",
                "icon": icon,
                "domain": sq.domain,
            }

            try:
                step_result = None
                async with asyncio.timeout(
                    self.STEP_TIMEOUT_SECONDS
                ):  # 15 min max per step (complex queries with DEEPER + multi-LLM + ReAct)
                    async for event in self._execute_step_stream(
                        step_id=step_num,
                        sub_query=sq,
                        exec_context=exec_context,
                        context_str=context_str,
                        original_query=original_query,
                        step_num=step_num,
                        total_steps=total_steps,
                    ):
                        if event.get("type") == "_step_result":
                            step_result = event["result"]
                        else:
                            # Forward SSE events (step_thinking, etc.)
                            yield event

                if step_result is None:
                    step_result = StepResult(
                        step_id=step_num,
                        sub_query=sq.text,
                        domain=sq.domain,
                        tools_selected=[],
                        tool_results=[],
                        execution_time_ms=0,
                    )

                exec_context.add_step(step_result)

                # Generate result summary — deduplicate and filter
                result_parts: list[str] = []
                seen: set[str] = set()
                for tr in step_result.tool_results:
                    summary = self._get_tool_result_summary(tr)
                    # Skip None (zero-count) and deduplicate identical messages
                    if summary is not None and summary not in seen:
                        result_parts.append(summary)
                        seen.add(summary)

                # Build a communicative summary with step numbering
                result_summary = ", ".join(result_parts) if result_parts else "Completato"
                step_label = f"[{step_num}/{total_steps}] {result_summary}"

                # Determine icon based on tool success/failure
                if len(step_result.tool_results) == 0:
                    # No tools were executed — something went wrong
                    step_icon = "⚠️"
                    if not result_parts:
                        result_summary = "Nessun risultato"
                elif all(not tr.success for tr in step_result.tool_results):
                    step_icon = "❌"
                elif any(not tr.success for tr in step_result.tool_results):
                    step_icon = "⚠️"
                else:
                    # Success — pick evocative icon from primary tool
                    step_icon = self._get_tool_icon(step_result.tool_results[0].tool_name)

                # Yield step_complete
                yield {
                    "type": "step_complete",
                    "step": step_num,
                    "total": total_steps,
                    "message": step_label,
                    "icon": step_icon,
                    "tools_count": len(step_result.tool_results),
                    "execution_time_ms": step_result.execution_time_ms,
                }

            except TimeoutError:
                logger.error(
                    "iterative_step_timeout",
                    step_id=step_num,
                    timeout_seconds=600,
                    sub_query_preview=sq.text[:80],
                )
                exec_context.add_step(
                    StepResult(
                        step_id=step_num,
                        sub_query=sq.text,
                        domain=sq.domain,
                        tools_selected=[],
                        tool_results=[],
                        execution_time_ms=600_000,
                    )
                )
                yield {
                    "type": "step_error",
                    "step": step_num,
                    "total": total_steps,
                    "message": f"[{step_num}/{total_steps}] Tempo scaduto (600s)",
                    "icon": "❌",
                }

            except Exception as e:
                import traceback

                # Temporary debug: dump traceback to file for diagnosis
                tb_str = traceback.format_exc()

                logger.error(
                    "iterative_step_failed",
                    step_id=step_num,
                    error=str(e),
                    error_type=type(e).__name__,
                    traceback=tb_str,
                )
                exec_context.add_step(
                    StepResult(
                        step_id=step_num,
                        sub_query=sq.text,
                        domain=sq.domain,
                        tools_selected=[],
                        tool_results=[],
                        execution_time_ms=(time.time() - step_start) * 1000,
                    )
                )
                yield {
                    "type": "step_error",
                    "step": step_num,
                    "total": total_steps,
                    "message": "Non sono riuscito a completare questo passaggio",
                    "icon": "⚠️",
                }

        # Final event with the execution context
        yield {
            "type": "execution_done",
            "exec_context": exec_context,
        }

    # =========================================================================
    # Streaming ReAct step execution
    # =========================================================================

    async def _execute_step_stream(
        self,
        step_id: int,
        sub_query: SubQuery,
        exec_context: ExecutionContext,
        context_str: str | None,
        original_query: str = "",
        step_num: int = 0,
        total_steps: int = 0,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Execute a step with ReAct loop, yielding SSE events for the frontend.

        Yields:
            - step_thinking: User-friendly messages about reasoning
            - _step_result: Internal event containing the final StepResult
        """
        import time

        step_start = time.time()

        # Get tools for this step
        tools = await self._get_tools_for_step(sub_query)

        logger.info(
            "step_tools_retrieved",
            step_id=step_id,
            sub_query=sub_query.text[:100],
            tools_count=len(tools),
            tools_names=[t.name for t in tools] if tools else [],
        )

        if not tools:
            logger.warning(
                "no_tools_for_step",
                step_id=step_id,
                sub_query_preview=sub_query.text[:50],
            )
            yield {
                "type": "_step_result",
                "result": StepResult(
                    step_id=step_id,
                    sub_query=sub_query.text,
                    domain=sub_query.domain,
                    tools_selected=[],
                    tool_results=[],
                    execution_time_ms=(time.time() - step_start) * 1000,
                ),
            }
            return

        logger.debug(
            "step_tools_retrieved",
            step_id=step_id,
            tools_count=len(tools),
            tools=[t.name for t in tools],
        )

        # ReAct observation loop
        all_tool_results: list[ToolResult] = []
        all_tools_selected: list[str] = []
        current_sub_query = sub_query
        iteration_context = ""

        for iteration in range(self.MAX_OBSERVE_ITERATIONS):
            logger.info(
                "react_iteration_start",
                step_id=step_id,
                iteration=iteration + 1,
                max_iterations=self.MAX_OBSERVE_ITERATIONS,
            )

            # Build extra context
            extra_context_combined = ""
            if context_str:
                extra_context_combined += context_str
            if iteration_context:
                extra_context_combined += (
                    f"\n\n### Observation from previous iteration:\n{iteration_context}"
                )

            # Select tools via LLM
            tool_tasks = await self._select_tools_for_step(
                step_id=step_id,
                sub_query=current_sub_query,
                tools=tools,
                previous_context=exec_context.get_context_summary(),
                extra_context=extra_context_combined or None,
                original_query=original_query,
            )

            if not tool_tasks:
                if iteration == 0:
                    logger.warning(
                        "no_tools_selected_for_step",
                        step_id=step_id,
                        sub_query_preview=current_sub_query.text[:50],
                    )
                break

            # Log and execute tools
            tool_names_str = ", ".join(t.tool_name.replace("google_", "") for t in tool_tasks)
            for task in tool_tasks:
                logger.info(
                    "tool_call_executing",
                    step_id=step_id,
                    tool_name=task.tool_name,
                    arguments_preview=str(task.arguments)[:200],
                    iteration=iteration + 1,
                )

            # Emit tool execution event with real tool names
            yield {
                "type": "step_thinking",
                "step": step_num,
                "total": total_steps,
                "message": f"Esecuzione: {tool_names_str}",
                "icon": "⚙️",
            }

            tool_results = await self._executor.execute(tool_tasks)

            for result in tool_results:
                logger.info(
                    "tool_call_completed",
                    step_id=step_id,
                    tool_name=result.tool_name,
                    success=result.success,
                    error=result.error,
                    result_preview=str(result.data)[:300] if result.data else "(no data)",
                    latency_ms=result.latency_ms,
                    iteration=iteration + 1,
                )

            all_tool_results.extend(tool_results)
            all_tools_selected.extend([t.tool_name for t in tool_tasks])

            # OBSERVE phase — only if not the last iteration
            if iteration < self.MAX_OBSERVE_ITERATIONS - 1:
                # Emit thinking event for the user
                yield {
                    "type": "step_thinking",
                    "step": step_num,
                    "total": total_steps,
                    "message": "Sto analizzando i risultati...",
                    "icon": "🧠",
                }

                observation = await self._observe_results(
                    step_id=step_id,
                    sub_query=current_sub_query,
                    tool_results=tool_results,
                    tools_available=tools,
                    iteration=iteration + 1,
                )

                if observation["decision"] == "SUFFICIENT":
                    logger.info(
                        "react_observation_sufficient",
                        step_id=step_id,
                        iteration=iteration + 1,
                        reason=observation.get("reason", ""),
                    )
                    break

                elif observation["decision"] == "RETRY":
                    retry_hint = observation.get("retry_hint", "")
                    logger.info(
                        "react_observation_retry",
                        step_id=step_id,
                        iteration=iteration + 1,
                        reason=observation.get("reason", ""),
                        retry_hint=retry_hint,
                    )
                    # Emit user-friendly retry event
                    yield {
                        "type": "step_thinking",
                        "step": step_num,
                        "total": total_steps,
                        "message": "La ricerca non ha dato risultati, riprovo con termini più semplici...",
                        "icon": "🔄",
                    }
                    current_sub_query = SubQuery(
                        text=f"{retry_hint} ({current_sub_query.text[:50]})",
                        domain=sub_query.domain,
                        intent=sub_query.intent,
                    )
                    iteration_context = (
                        f"Previous search returned 0 results. "
                        f"RETRY with simpler query: {retry_hint}. "
                        f"Use SHORT keywords only (1-2 words)."
                    )

                elif observation["decision"] == "DEEPER":
                    tool_hints = observation.get("tool_hints", [])
                    logger.info(
                        "react_observation_deeper",
                        step_id=step_id,
                        iteration=iteration + 1,
                        reason=observation.get("reason", ""),
                        tool_hints=tool_hints,
                    )
                    # Emit user-friendly deeper event
                    yield {
                        "type": "step_thinking",
                        "step": step_num,
                        "total": total_steps,
                        "message": "Ho trovato risultati, approfondisco il contenuto...",
                        "icon": "🔎",
                    }
                    ids_found = []
                    for tr in tool_results:
                        ids_found.extend(ExecutionContext._extract_key_ids(tr.data, tr.tool_name))
                    # Format as numbered list for unambiguous LLM consumption
                    ids_list = "\n".join(
                        f"{i + 1}. {id_ref}" for i, id_ref in enumerate(ids_found[:10])
                    )
                    iteration_context = (
                        f"Previous tools found data. Now drill deeper.\n"
                        f"Suggested tools: {', '.join(tool_hints)}\n\n"
                        f"FOUND ITEMS (copy the exact ID values into tool parameters):\n"
                        f"{ids_list}\n\n"
                        f"IMPORTANT: Use ONLY the exact ID values shown in quotes above. "
                        f"Do NOT modify or guess IDs."
                    )

                else:
                    break

        # Yield the final result as internal event
        yield {
            "type": "_step_result",
            "result": StepResult(
                step_id=step_id,
                sub_query=sub_query.text,
                domain=sub_query.domain,
                tools_selected=all_tools_selected,
                tool_results=all_tool_results,
                execution_time_ms=(time.time() - step_start) * 1000,
            ),
        }

    # Observation prompt for ReAct loop
    _OBSERVE_SYSTEM_PROMPT = """You are an observation agent in a ReAct loop.
You have just executed tool(s) for this sub-query. Analyze the results and decide what to do next.

RULES:
1. If the results contain useful data that answers the sub-query → reply SUFFICIENT
2. If the results are EMPTY or returned 0 items and you can try a SIMPLER/BROADER query → reply RETRY with new parameters
3. If the results contain IDs (file_id, message_id, event_id) that should be explored deeper → reply DEEPER with tool calls

CRITICAL:
- For RETRY: simplify the search query drastically. Use 1-2 keywords MAX.
- For DEEPER: use IDs from the results to call detail/content tools.
- NEVER retry more than once with the same strategy.
- NEVER hallucinate data. Only reference IDs/data from actual results.

Reply with EXACTLY ONE of these JSON formats:
{"decision": "SUFFICIENT", "reason": "brief explanation"}
{"decision": "RETRY", "reason": "brief explanation", "retry_hint": "simpler search terms to use"}
{"decision": "DEEPER", "reason": "brief explanation", "tool_hints": ["tool_name1", "tool_name2"]}
"""

    async def _execute_step(
        self,
        step_id: int,
        sub_query: SubQuery,
        exec_context: ExecutionContext,
        context_str: str | None,
    ) -> StepResult:
        """Execute a single step with ReAct observation loop.

        ReAct Pattern:
        1. Retrieve top 10 tools for this sub-query
        2. LOOP (max MAX_OBSERVE_ITERATIONS):
           a. Call LLM to select and parameterize tools
           b. Execute selected tools
           c. OBSERVE: LLM analyzes results
              - SUFFICIENT → return results
              - RETRY → re-run with simpler query
              - DEEPER → drill into results with new tool calls
        """
        import time

        step_start = time.time()

        # Step 1: Get tools specific to this sub-query (max 10)
        tools = await self._get_tools_for_step(sub_query)

        if not tools:
            logger.warning(
                "no_tools_for_step",
                step_id=step_id,
                sub_query_preview=sub_query.text[:50],
            )
            return StepResult(
                step_id=step_id,
                sub_query=sub_query.text,
                domain=sub_query.domain,
                tools_selected=[],
                tool_results=[],
                execution_time_ms=(time.time() - step_start) * 1000,
            )

        logger.debug(
            "step_tools_retrieved",
            step_id=step_id,
            tools_count=len(tools),
            tools=[t.name for t in tools],
        )

        # ReAct observation loop
        all_tool_results: list[ToolResult] = []
        all_tools_selected: list[str] = []
        current_sub_query = sub_query
        iteration_context = ""  # Accumulates observation context for retries

        for iteration in range(self.MAX_OBSERVE_ITERATIONS):
            logger.info(
                "react_iteration_start",
                step_id=step_id,
                iteration=iteration + 1,
                max_iterations=self.MAX_OBSERVE_ITERATIONS,
            )

            # Step 2a: Call LLM to select tools
            extra_context_combined = ""
            if context_str:
                extra_context_combined += context_str
            if iteration_context:
                extra_context_combined += (
                    f"\n\n### Observation from previous iteration:\n{iteration_context}"
                )

            tool_tasks = await self._select_tools_for_step(
                step_id=step_id,
                sub_query=current_sub_query,
                tools=tools,
                previous_context=exec_context.get_context_summary(),
                extra_context=extra_context_combined or None,
            )

            if not tool_tasks:
                # ✅ SOTA 2026: Nuclear Fallback
                # If the LLM is "lazy" and doesn't select any tools, but we HAVE retrieved tools,
                # force a call with the most appropriate search tool using the sub-query text.
                logger.info(
                    "nuclear_fallback_check",
                    step_id=step_id,
                    iteration=iteration,
                    has_tools=bool(tools),
                    tools_count=len(tools) if tools else 0,
                    tools_names=[t.name for t in tools] if tools else [],
                    sub_query_domain=sub_query.domain,
                    sub_query_intent=sub_query.intent,
                )
                if iteration == 0 and tools:
                    fallback_tool = None
                    # Priority 1: Match tool from _INTENT_TOOL_MAP
                    forced_tool_names = self._INTENT_TOOL_MAP.get(sub_query.intent, [])
                    if forced_tool_names:
                        for t in tools:
                            if t.name in forced_tool_names:
                                fallback_tool = t
                                break

                    # Priority 2: Domain-specific tool patterns
                    if not fallback_tool:
                        # Weather tools
                        if sub_query.domain == "geo_weather" or "weather" in sub_query.domain:
                            for t in tools:
                                if "meteo" in t.name or "weather" in t.name:
                                    fallback_tool = t
                                    break
                        # Finance tools
                        elif sub_query.domain == "finance_crypto" or "finance" in sub_query.domain:
                            for t in tools:
                                if "coin" in t.name or "price" in t.name or "crypto" in t.name:
                                    fallback_tool = t
                                    break
                        # Search/list tools for other domains
                        if not fallback_tool:
                            for t in tools:
                                if "search" in t.name or "list" in t.name:
                                    fallback_tool = t
                                    break
                        # Last resort: take the first tool
                        if not fallback_tool and tools:
                            fallback_tool = tools[0]

                    if fallback_tool:
                        logger.warning(
                            "executor_nuclear_fallback_active",
                            step_id=step_id,
                            tool_name=fallback_tool.name,
                            sub_query=sub_query.text,
                            domain=sub_query.domain,
                        )
                        # Build arguments dynamically based on tool parameter schema
                        fallback_args = self._build_fallback_arguments(
                            tool_name=fallback_tool.name,
                            tool_schema=fallback_tool.schema,
                            query_text=current_sub_query.text,
                            domain=sub_query.domain,
                        )
                        logger.info(
                            "executor_nuclear_fallback_args",
                            step_id=step_id,
                            tool_name=fallback_tool.name,
                            fallback_args=fallback_args,
                        )
                        tool_tasks = [
                            ToolTask(
                                tool_name=fallback_tool.name,
                                arguments=fallback_args,
                            )
                        ]

                if not tool_tasks:
                    if iteration == 0:
                        logger.warning(
                            "no_tools_selected_for_step",
                            step_id=step_id,
                            sub_query_preview=current_sub_query.text[:50],
                        )
                    break  # No tools to call, exit loop

            # Log tool calls
            for task in tool_tasks:
                args_preview = str(task.arguments)[:200]
                logger.info(
                    "tool_call_executing",
                    step_id=step_id,
                    tool_name=task.tool_name,
                    arguments_preview=args_preview,
                    iteration=iteration + 1,
                )

            # Step 2b: Execute the selected tools
            tool_results = await self._executor.execute(tool_tasks)

            # Log results
            for result in tool_results:
                result_preview = str(result.data)[:300] if result.data else "(no data)"
                logger.info(
                    "tool_call_completed",
                    step_id=step_id,
                    tool_name=result.tool_name,
                    success=result.success,
                    error=result.error,
                    result_preview=result_preview,
                    latency_ms=result.latency_ms,
                    iteration=iteration + 1,
                )

            all_tool_results.extend(tool_results)
            all_tools_selected.extend([t.tool_name for t in tool_tasks])

            # Step 2c: OBSERVE — only if not the last iteration
            if iteration < self.MAX_OBSERVE_ITERATIONS - 1:
                observation = await self._observe_results(
                    step_id=step_id,
                    sub_query=current_sub_query,
                    tool_results=tool_results,
                    tools_available=tools,
                    iteration=iteration + 1,
                )

                if observation["decision"] == "SUFFICIENT":
                    logger.info(
                        "react_observation_sufficient",
                        step_id=step_id,
                        iteration=iteration + 1,
                        reason=observation.get("reason", ""),
                    )
                    break  # Results are good enough

                elif observation["decision"] == "RETRY":
                    retry_hint = observation.get("retry_hint", "")
                    logger.info(
                        "react_observation_retry",
                        step_id=step_id,
                        iteration=iteration + 1,
                        reason=observation.get("reason", ""),
                        retry_hint=retry_hint,
                    )
                    # Create modified sub-query with simpler terms
                    current_sub_query = SubQuery(
                        text=f"{retry_hint} ({current_sub_query.text[:50]})",
                        domain=sub_query.domain,
                        intent=sub_query.intent,
                    )
                    iteration_context = (
                        f"Previous search returned 0 results. "
                        f"RETRY with simpler query: {retry_hint}. "
                        f"Use SHORT keywords only (1-2 words)."
                    )

                elif observation["decision"] == "DEEPER":
                    tool_hints = observation.get("tool_hints", [])
                    logger.info(
                        "react_observation_deeper",
                        step_id=step_id,
                        iteration=iteration + 1,
                        reason=observation.get("reason", ""),
                        tool_hints=tool_hints,
                    )
                    # Build context with IDs from results for next iteration
                    ids_found = []
                    for tr in tool_results:
                        ids_found.extend(ExecutionContext._extract_key_ids(tr.data, tr.tool_name))
                    iteration_context = (
                        f"Previous tools found data. Now drill deeper.\n"
                        f"Available IDs: {'; '.join(ids_found[:10])}\n"
                        f"Suggested tools: {', '.join(tool_hints)}\n"
                        f"Use the IDs above to call detail/content tools."
                    )

                else:
                    logger.warning(
                        "react_observation_unknown",
                        step_id=step_id,
                        decision=observation.get("decision"),
                    )
                    break

        return StepResult(
            step_id=step_id,
            sub_query=sub_query.text,
            domain=sub_query.domain,
            tools_selected=all_tools_selected,
            tool_results=all_tool_results,
            execution_time_ms=(time.time() - step_start) * 1000,
        )

    async def _observe_results(
        self,
        step_id: int,
        sub_query: SubQuery,
        tool_results: list[ToolResult],
        tools_available: list[RetrievedTool],
        iteration: int,
    ) -> dict[str, Any]:
        """ReAct OBSERVE phase: analyze tool results and decide next action.

        Returns dict with 'decision' key: SUFFICIENT, RETRY, or DEEPER.
        Uses Mistral Large 3 for fast, focused observation.
        """
        # Format tool results for observation
        results_summary_parts: list[str] = []
        has_empty_results = False
        has_ids = False

        for tr in tool_results:
            if not tr.success:
                results_summary_parts.append(f"- {tr.tool_name}: ERROR ({tr.error})")
                continue

            if isinstance(tr.data, dict):
                # Check for empty results
                for key in (
                    "results",
                    "events",
                    "files",
                    "messages",
                    "emails",
                    "items",
                    "conferences",
                    "documents",
                ):
                    if key in tr.data:
                        count = len(tr.data[key]) if isinstance(tr.data[key], list) else 0
                        if count == 0:
                            has_empty_results = True
                        results_summary_parts.append(f"- {tr.tool_name}: {count} {key} found")
                        break
                else:
                    results_summary_parts.append(f"- {tr.tool_name}: returned data")

                # Check for IDs
                for id_key in ("id", "file_id", "message_id", "event_id"):
                    if id_key in tr.data:
                        has_ids = True
                        break
                # Also check nested lists
                for key in ("results", "events", "files", "messages", "emails"):
                    val = tr.data.get(key, [])
                    if isinstance(val, list) and len(val) > 0:
                        if isinstance(val[0], dict) and any(
                            k in val[0] for k in ("id", "file_id", "message_id")
                        ):
                            has_ids = True
                        break
            else:
                results_summary_parts.append(f"- {tr.tool_name}: returned data")

        results_summary = "\n".join(results_summary_parts)

        # Fast-path: if results are clearly sufficient
        # Search results (files, emails, events) naturally contain IDs in list items.
        # These are NOT candidates for DEEPER - they are already complete search results.
        # DEEPER is only useful when a tool returns a single entity ID that needs expansion.
        has_list_results = any(
            isinstance(tr.data, dict)
            and any(
                isinstance(tr.data.get(k, []), list) and len(tr.data.get(k, [])) > 0
                for k in (
                    "results",
                    "events",
                    "files",
                    "messages",
                    "emails",
                    "items",
                    "conferences",
                    "documents",
                )
            )
            for tr in tool_results
            if tr.success
        )

        if not has_empty_results and has_list_results:
            return {"decision": "SUFFICIENT", "reason": "Search returned list results"}

        if not has_empty_results and not has_ids:
            return {"decision": "SUFFICIENT", "reason": "Data found, no IDs to explore"}

        # If all results are empty, suggest RETRY
        if (
            has_empty_results
            and not has_ids
            and all(
                not tr.success
                or (
                    isinstance(tr.data, dict)
                    and any(
                        len(tr.data.get(k, [])) == 0
                        for k in (
                            "results",
                            "events",
                            "files",
                            "messages",
                            "emails",
                            "items",
                            "conferences",
                            "documents",
                        )
                        if k in tr.data
                    )
                )
                for tr in tool_results
            )
        ):
            return {
                "decision": "RETRY",
                "reason": "All results empty, need simpler query",
                "retry_hint": sub_query.text.split()[-2:]
                if len(sub_query.text.split()) > 2
                else sub_query.text,
            }

        # Full LLM observation for ambiguous cases
        available_tool_names = [t.name for t in tools_available]
        user_msg = (
            f"Sub-query: {sub_query.text}\n"
            f"Iteration: {iteration}/{self.MAX_OBSERVE_ITERATIONS}\n"
            f"Tools available: {', '.join(available_tool_names)}\n\n"
            f"Results:\n{results_summary}\n\n"
            f"Result data preview:\n{str([tr.data for tr in tool_results if tr.success])[:1500]}"
        )

        try:
            from me4brain.llm.models import LLMRequest

            client, actual_model = resolve_model_client(self._model)
            observe_request = LLMRequest(
                messages=[
                    {"role": "system", "content": self._OBSERVE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                model=actual_model,
                temperature=0.1,
                max_tokens=200,
            )

            response = await client.generate_response(observe_request)

            content = response.content.strip()
            # Parse JSON from response
            observation = self._try_extract_valid_json(content)
            if observation and "decision" in observation:
                logger.debug(
                    "react_observation_parsed",
                    step_id=step_id,
                    decision=observation["decision"],
                    reason=observation.get("reason", ""),
                )
                return observation

        except Exception as e:
            logger.warning(
                "react_observation_failed",
                step_id=step_id,
                error=str(e),
            )

        # Fallback: if observation fails, consider results sufficient
        return {"decision": "SUFFICIENT", "reason": "Observation fallback"}

    async def _get_tools_for_step(self, sub_query: SubQuery) -> list[RetrievedTool]:
        """Get a small, focused set of tools for this step.

        Uses the retriever but with a hard cap of MAX_TOOLS_PER_STEP.
        Guarantees specific tools for recognized Google Workspace intents.
        """
        from me4brain.engine.hybrid_router.types import DomainClassification, DomainComplexity

        # SOTA 2026: Forced Intent Mapping
        # If the decomposer identified a specific Workspace intent, force those tools
        forced_names = self._INTENT_TOOL_MAP.get(sub_query.intent, [])
        if forced_names:
            forced_tools: list[RetrievedTool] = []
            for name in forced_names:
                t = await self._retriever.get_tool_by_name(name)
                if t:
                    forced_tools.append(t)

            if forced_tools:
                logger.info(
                    "forced_intent_tools",
                    intent=sub_query.intent,
                    count=len(forced_tools),
                    tools=[t.name for t in forced_tools],
                )
                return forced_tools

        # Fallback logic for domain enrichment
        effective_domain = sub_query.domain
        query_lower = sub_query.text.lower()

        # Keyword → intent-based domain mapping (post-restructuring)
        # IMPORTANT: Order matters! Multi-word keywords FIRST, then specific single words.
        # Avoid generic words like "cerca", "file", "report" that match too broadly.
        _KEYWORD_DOMAIN_MAP: list[tuple[str, str]] = [
            # Google Workspace
            ("google drive", "google_workspace"),
            ("google docs", "google_workspace"),
            ("google sheets", "google_workspace"),
            ("google calendar", "google_workspace"),
            ("google meet", "google_workspace"),
            ("gmail", "google_workspace"),
            ("email", "google_workspace"),
            ("calendario", "google_workspace"),
            ("appuntamento", "google_workspace"),
            ("drive", "google_workspace"),
            ("documento", "google_workspace"),
            ("cartella", "google_workspace"),
            # Finance & Crypto
            ("crypto", "finance_crypto"),
            ("bitcoin", "finance_crypto"),
            ("stocks", "finance_crypto"),
            ("borsa", "finance_crypto"),
            ("prezzo", "finance_crypto"),
            ("costa", "finance_crypto"),
            ("euro", "finance_crypto"),
            ("dollaro", "finance_crypto"),
            # Weather (Geo)
            ("meteo", "geo_weather"),
            ("tempo fa", "geo_weather"),
            ("temperatura", "geo_weather"),
            ("gradi", "geo_weather"),
            ("previsioni", "geo_weather"),
            ("piove", "geo_weather"),
            # Productivity
            ("promemoria", "productivity"),
            ("task", "productivity"),
            ("todo", "productivity"),
            ("note", "productivity"),
            # Sport NBA
            ("nba", "sports_nba"),
            ("lakers", "sports_nba"),
            ("celtics", "sports_nba"),
            # Science
            ("paper", "science_research"),
            ("arxiv", "science_research"),
            ("scientifico", "science_research"),
            # General Web
            ("search", "web_search"),
            ("cerca", "web_search"),
            ("trova", "web_search"),
            ("notizie", "web_search"),
        ]

        for keyword, target_domain in _KEYWORD_DOMAIN_MAP:
            if keyword in query_lower and effective_domain != target_domain:
                logger.debug(
                    "domain_enriched",
                    original_domain=effective_domain,
                    new_domain=target_domain,
                    reason=f"keyword_{keyword}_detected",
                )
                effective_domain = target_domain
                break  # First match wins

        # Create a mini-classification for just this sub-query's domain
        domain_complexity = DomainComplexity(name=effective_domain, complexity="medium")
        classification = DomainClassification(
            domains=[domain_complexity],
            confidence=0.95,
        )

        # Retrieve tools - the retriever will respect our limits
        # We pass a custom config override via direct query
        retrieval = await self._retriever.retrieve(
            query=sub_query.text,
            classification=classification,
        )

        # Hard cap to MAX_TOOLS_PER_STEP
        tools = retrieval.tools[: self.MAX_TOOLS_PER_STEP]

        # FIX B3: Fallback to global top-k if no tools found
        if not tools and hasattr(self._retriever, "retrieve_global_topk"):
            logger.warning(
                "step_fallback_global_topk",
                step_query=sub_query.text[:50],
                domain=sub_query.domain,
            )
            fallback_retrieval = await self._retriever.retrieve_global_topk(
                sub_query.text, k=self.MAX_TOOLS_PER_STEP
            )
            tools = fallback_retrieval.tools[: self.MAX_TOOLS_PER_STEP]
            logger.info(
                "step_fallback_success",
                tools_found=len(tools),
                tool_names=[t.name for t in tools],
            )

        return tools

    def _build_fallback_arguments(
        self,
        tool_name: str,
        tool_schema: dict,
        query_text: str,
        domain: str,
    ) -> dict[str, Any]:
        """Build appropriate arguments for fallback tool execution based on schema and domain.

        This ensures that when the LLM fails to select tools, we can still execute them
        by extracting relevant parameters from the query text directly.

        Args:
            tool_name: Name of the tool to execute
            tool_schema: The tool's OpenAI function schema
            query_text: The original query text to extract parameters from
            domain: The domain of the query

        Returns:
            Dictionary of arguments suitable for the tool
        """
        import re

        # Get parameter schema from the tool definition
        parameters = tool_schema.get("parameters", {})
        properties = parameters.get("properties", {})

        # Default: try extracting city names if tool expects 'city' parameter (geo_weather pattern)
        if "city" in properties:
            # Use existing city extraction logic from GeoWeatherHandler as a reference
            query_lower = query_text.lower()

            # Common Italian weather-related patterns
            weather_patterns = [
                "tempo fa a",
                "meteo a",
                "previsioni meteo a",
                "che tempo fa a",
                "com'è il tempo a",
                "qual è la temperatura a",
            ]

            city = None
            for pattern in weather_patterns:
                if pattern in query_lower:
                    # Extract city name after the pattern
                    idx = query_lower.find(pattern) + len(pattern)
                    after_pattern = query_text[idx:].strip()
                    # Take up to first punctuation or end
                    city = after_pattern.split("?")[0].split(".")[0].split(",")[0].strip()
                    if city:
                        break

            # If pattern matching failed, try direct Italian city recognition
            if not city:
                # List of major Italian cities (could be expanded)
                italian_cities = [
                    "roma",
                    "milano",
                    "torino",
                    "napoli",
                    "firenze",
                    "bologna",
                    "genova",
                    "venezia",
                    "palermo",
                    "catania",
                    "bari",
                    "verona",
                    "padova",
                    "trieste",
                    "modena",
                    "parma",
                    "cagliari",
                    "messina",
                    "catanzaro",
                    "caltanissetta",
                    "agrigento",
                    "trapani",
                    "siracusa",
                    "ragusa",
                    "enna",
                    "pordenone",
                    "udine",
                    "gorizia",
                    "la spezia",
                    "livorno",
                    "lucca",
                    "pisa",
                    "siena",
                    "arezzo",
                    "perugia",
                    "ancona",
                    "pesaro",
                    "rimini",
                    "ferrara",
                    "forlì",
                    " Ravenna",
                    "macerata",
                    "camerino",
                    "campobasso",
                    "pescara",
                    "chieti",
                    "l'aquila",
                    "terni",
                    "viterbo",
                    "rieti",
                    "latina",
                    "frosinone",
                    "caserta",
                    "salerno",
                    "avellino",
                    "benevento",
                    "isernia",
                    "brindisi",
                    "lecce",
                    "taranto",
                    "potenza",
                    "matera",
                    "cosenza",
                    "reggio calabria",
                    "crotone",
                    "vibo valentia",
                ]
                for city_name in italian_cities:
                    if city_name in query_lower:
                        city = city_name.title()
                        break

                # Fallback: use any capitalized word longer than 2 chars
                if not city:
                    words = re.findall(r"\b[A-Z][a-z]{2,}\b", query_text)
                    if words:
                        city = words[0]

            if city:
                return {"city": city}
            else:
                # Last resort: use first 50 chars of query as city (may fail, but better than nothing)
                return {"city": query_text[:50]}

        # For search tools (NBA, Web search, etc.), use 'query' parameter
        if "query" in properties:
            return {"query": query_text}

        # For tools with 'search' parameter (nba_player_search, etc.)
        if "search" in properties:
            return {"search": query_text}

        # For tools with different parameter names like 'days', 'min_magnitude', etc.
        # Extract based on common patterns or use defaults
        for param_name, param_schema in properties.items():
            param_type = param_schema.get("type", "string")
            if param_type == "integer":
                # Look for numbers in query
                numbers = re.findall(r"\b(\d+)\b", query_text)
                if numbers:
                    return {param_name: int(numbers[0])}
            elif param_type == "number":
                numbers = re.findall(r"\b(\d+(?:\.\d+)?)\b", query_text)
                if numbers:
                    return {param_name: float(numbers[0])}

        # Fallback: build minimal arguments for required parameters only
        required = parameters.get("required", [])
        fallback_args = {}
        for param in required:
            if param in properties:
                param_type = properties[param].get("type", "string")
                if param_type == "string":
                    fallback_args[param] = query_text[:50]
                elif param_type in ("integer", "number"):
                    fallback_args[param] = 1  # Safe default
                elif param_type == "boolean":
                    fallback_args[param] = False

        # Validate built arguments against schema before returning
        validated_args = self._validate_fallback_args(fallback_args, properties, required)
        if validated_args:
            return validated_args

        # If validation fails, return empty dict - nuclear fallback should not proceed
        # with invalid arguments. The ReAct loop will handle the failure gracefully.
        logger.warning(
            "nuclear_fallback_validation_failed",
            tool_name=tool_name,
            built_args=fallback_args,
            required=required,
        )
        return {}

    def _validate_fallback_args(
        self,
        args: dict[str, Any],
        properties: dict[str, Any],
        required: list[str],
    ) -> dict[str, Any] | None:
        """Validate fallback arguments against tool schema.

        Returns validated args dict if valid, None if validation fails.
        """

        validated = {}

        for param_name, param_schema in properties.items():
            is_required = param_name in required
            value = args.get(param_name)
            param_type = param_schema.get("type", "string")

            if value is None:
                if is_required:
                    return None
                continue

            if param_type == "string":
                if not isinstance(value, str):
                    value = str(value)
                value = value.strip()
                if not value and is_required:
                    return None
                validated[param_name] = value

            elif param_type == "integer":
                try:
                    validated[param_name] = int(value)
                except (ValueError, TypeError):
                    if is_required:
                        return None

            elif param_type == "number":
                try:
                    validated[param_name] = float(value)
                except (ValueError, TypeError):
                    if is_required:
                        return None

            elif param_type == "boolean":
                if isinstance(value, bool):
                    validated[param_name] = value
                elif isinstance(value, str):
                    validated[param_name] = value.lower() in ("true", "1", "yes")
                else:
                    validated[param_name] = bool(value)

            elif param_type == "array":
                if isinstance(value, list):
                    validated[param_name] = value
                elif isinstance(value, str):
                    validated[param_name] = [value]
                elif is_required:
                    return None

            elif param_type == "object":
                if isinstance(value, dict):
                    validated[param_name] = value
                elif is_required:
                    return None

            else:
                validated[param_name] = value

        for req in required:
            if req not in validated or validated[req] is None:
                return None

        return validated

    async def _select_tools_for_step(
        self,
        step_id: int,
        sub_query: SubQuery,
        tools: list[RetrievedTool],
        previous_context: str,
        extra_context: str | None,
        original_query: str = "",
    ) -> list[ToolTask]:
        """Call LLM to select and parameterize tools for this step.

        This call has MAX 10 tools, so it should never hit provider limits.
        """
        from datetime import datetime

        # Build tool schemas for OpenAI format
        tool_schemas = [t.schema for t in tools]

        # ✅ SOTA 2026: GraphRAG Prompt Retrieval (Layer 1) with timeout protection
        import asyncio

        try:
            graph_data = await asyncio.wait_for(
                self._get_graph_prompt_hints(
                    domain=sub_query.domain,
                    tool_names=[t.name for t in tools],
                    query=sub_query.text,
                ),
                timeout=120.0,  # 120 second timeout (development)
            )
        except TimeoutError:
            logger.warning(
                "graph_prompt_hints_retrieval_timeout",
                domain=sub_query.domain,
                tool_count=len(tools),
                timeout_seconds=120.0,
            )
            graph_data = {"hints": "", "constraints": {}}
        except Exception as e:
            logger.warning(
                "graph_prompt_hints_retrieval_error",
                domain=sub_query.domain,
                error=str(e),
                error_type=type(e).__name__,
            )
            graph_data = {"hints": "", "constraints": {}}

        graph_hints = graph_data.get("hints", "")
        tool_constraints = graph_data.get("constraints", {})

        # ✅ SOTA 2026: Multi-Attempt Feedback Loop (Guardrails) optimized
        max_logic_attempts = 2  # Reduced from 3 to save tokens/latency
        feedback_context = ""

        # ✅ SOTA 2026: Token Budgeting for this specific step
        allocated_tokens = 4000  # Hard ceiling per selection step
        used_step_tokens = 0

        for attempt in range(max_logic_attempts):
            # Build prompt with domain-specific hints and graph templates
            system_prompt = await self._build_step_prompt(
                step_id=step_id,
                total_tools=len(tools),
                current_datetime=datetime.now().strftime("%Y-%m-%d %H:%M"),
                graph_hints=graph_hints,
                original_query=original_query,
            )

            # Build user message with context and potential feedback from previous attempt
            user_message_parts = [f"**Step {step_id}**: {sub_query.text}"]
            if previous_context:
                user_message_parts.append("\n" + previous_context)
            if extra_context:
                user_message_parts.append(f"\n**Contesto addizionale**: {extra_context}")

            # Inserimento feedback se presente (ReAct Loop)
            if feedback_context:
                user_message_parts.append(
                    f"\n⚠️ **ERRORE VALIDAZIONE PRECEDENTE**:\n{feedback_context}\nPer favore, correggi la chiamata e riprova."
                )

            user_message = "\n".join(user_message_parts)

            # Convert dict schemas to Pydantic Tool models
            # tool_schemas is list[dict] with format: {"type": "function", "function": {...}}
            import asyncio as _asyncio

            from me4brain.llm.models import LLMRequest, Tool, ToolFunction

            tool_models: list[Tool] = []
            for schema_dict in tool_schemas:
                if isinstance(schema_dict, dict) and "function" in schema_dict:
                    func_dict = schema_dict["function"]
                    tool_func = ToolFunction(
                        name=func_dict.get("name", ""),
                        description=func_dict.get("description"),
                        parameters=func_dict.get("parameters", {}),
                    )
                    tool_models.append(Tool(type="function", function=tool_func))
                elif isinstance(schema_dict, Tool):
                    # Already a Tool model, use as-is
                    tool_models.append(schema_dict)

            tc_client, actual_tc_model = resolve_model_client(self._tc_model)
            request = LLMRequest(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                model=actual_tc_model,  # Use resolved tool-calling model
                tools=tool_models,  # Now properly typed as list[Tool]
                tool_choice="auto",
                temperature=0.1,
            )

            # ✅ SOTA 2026: Budget Tracking & Short-Circuit
            current_prompt_tokens = self._estimate_tokens(system_prompt + user_message)
            if used_step_tokens + current_prompt_tokens > allocated_tokens:
                logger.warning(
                    "token_budget_exhausted",
                    step_id=step_id,
                    used=used_step_tokens,
                    needed=current_prompt_tokens,
                    limit=allocated_tokens,
                )
                return []  # Short-circuit output

            # Call LLM with retry
            response = None
            max_llm_retries = 2
            tool_selection_timeout = 120.0  # seconds - increased for Ollama tool-calling latency
            for llm_attempt in range(max_llm_retries + 1):
                try:
                    # ✅ SOTA 2026: Delegate to tool-calling specialized provider
                    # ✅ SOTA 2026: Add timeout protection to prevent indefinite hangs
                    try:
                        response = await asyncio.wait_for(
                            tc_client.generate_response(request), timeout=tool_selection_timeout
                        )
                    except TimeoutError:
                        logger.warning(
                            "step_tool_selection_timeout",
                            step_id=step_id,
                            timeout_seconds=tool_selection_timeout,
                            attempt=llm_attempt + 1,
                        )
                        # Graceful fallback: Use first N tools from retrieved list without LLM selection
                        # This preserves functionality while preventing indefinite hangs
                        max_fallback_tools = min(5, len(tools))  # Use top 5 tools by relevance
                        fallback_tasks = []
                        for tool in tools[:max_fallback_tools]:
                            fallback_tasks.append(
                                ToolTask(
                                    tool_name=tool.name,
                                    input_data={"query": user_message},
                                    metadata={"fallback": True, "reason": "tool_selection_timeout"},
                                )
                            )

                        # Estimate tokens for fallback
                        used_step_tokens += current_prompt_tokens
                        self._total_tokens_used += current_prompt_tokens
                        return fallback_tasks  # Return fallback tools immediately

                    # Update billing/tracking
                    t_count = 0
                    if response and hasattr(response, "usage") and response.usage:
                        t_count = getattr(response.usage, "total_tokens", 0)
                    else:
                        # Fallback estimation
                        t_count = (
                            self._estimate_tokens(response.content if response else "")
                            + current_prompt_tokens
                        )

                    used_step_tokens += t_count
                    self._total_tokens_used += t_count
                    break
                except Exception as e:
                    logger.warning(
                        "step_tool_selection_llm_error",
                        step_id=step_id,
                        error=str(e),
                        error_type=type(e).__name__,
                        attempt=llm_attempt + 1,
                        max_attempts=max_llm_retries + 1,
                    )
                    if llm_attempt < max_llm_retries:
                        backoff = 2 ** (llm_attempt + 1)  # 2s, 4s
                        await _asyncio.sleep(backoff)
                    else:
                        logger.error(
                            "step_tool_selection_llm_exhausted",
                            step_id=step_id,
                            error=str(e),
                        )
                        return []  # All retries exhausted — return empty

            # Parse and Validate (Layer 3)
            tool_tasks = []
            skipped_hallucination = 0
            try:
                available_tool_names = {t.name for t in tools}  # Strictly track active tools

                # Check for tool_calls first (Native Layer)
                raw_tool_calls = response.tool_calls

                # ✅ DEBUG: Log what the LLM returned
                logger.info(
                    "step_tool_selection_response",
                    step_id=step_id,
                    has_tool_calls=bool(raw_tool_calls),
                    tool_calls_count=len(raw_tool_calls) if raw_tool_calls else 0,
                    has_content=bool(response and response.content),
                    content_preview=response.content[:200]
                    if response and response.content
                    else None,
                    available_tools=list(available_tool_names),
                )

                if not raw_tool_calls and response and response.content:
                    content_json = self._try_extract_valid_json(response.content)
                    if content_json:
                        potential_calls = []
                        if isinstance(content_json, dict):
                            # Format 1: {"tool": "name", "parameters": {...}}
                            if "tool" in content_json and "parameters" in content_json:
                                potential_calls.append(
                                    {
                                        "function": {
                                            "name": content_json["tool"],
                                            "arguments": content_json["parameters"],
                                        }
                                    }
                                )
                            # Format 2: {"name": "name", "arguments": {...}}
                            elif "name" in content_json and "arguments" in content_json:
                                potential_calls.append({"function": content_json})

                        # Format 3: [{"name": "...", "arguments": {...}}]
                        elif isinstance(content_json, list):
                            for item in content_json:
                                if isinstance(item, dict) and "name" in item:
                                    # Ensure we have arguments or parameters
                                    args = item.get("arguments") or item.get("parameters") or {}
                                    potential_calls.append(
                                        {"function": {"name": item["name"], "arguments": args}}
                                    )

                        if potential_calls:
                            from me4brain.llm.models import ToolCall, ToolCallFunction

                            # Wrap in native ToolCall models to match LLMResponse architecture
                            raw_tool_calls = []
                            for c in potential_calls:
                                # Ensure arguments is a JSON string as expected by ToolCallFunction
                                args_str = (
                                    json.dumps(c["function"]["arguments"])
                                    if isinstance(c["function"]["arguments"], (dict, list))
                                    else str(c["function"]["arguments"])
                                )
                                raw_tool_calls.append(
                                    ToolCall(
                                        function=ToolCallFunction(
                                            name=c["function"]["name"], arguments=args_str
                                        )
                                    )
                                )

                            logger.info(
                                "step_tool_content_fallback_triggered",
                                step_id=step_id,
                                calls_found=len(raw_tool_calls),
                            )

                if raw_tool_calls:
                    for tc in raw_tool_calls:
                        tool_name = tc.function.name

                        # ✅ SOTA 2026: Hard Validation (Layer 2)
                        # Prevents hallucinating tools outside the current active retrieved set
                        if not tool_name or tool_name not in available_tool_names:
                            skipped_hallucination += 1
                            logger.error(
                                "step_tool_hallucination_blocked",
                                step_id=step_id,
                                tool_called=tool_name or "empty",
                                available=list(available_tool_names),
                            )
                            continue

                        args = tc.function.arguments
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = self._try_extract_valid_json(args)
                                if args is None:
                                    logger.warning(
                                        "step_tool_json_parse_failed",
                                        step_id=step_id,
                                        tool_name=tool_name,
                                    )
                                    args = {}

                        # ✅ SOTA 2026: Hard Validation (Layer 3)
                        # Apply hand-crafted constraints if available for this tool
                        if tool_name in tool_constraints:
                            const = tool_constraints[tool_name]
                            if "input_schema" in const:
                                schema = const["input_schema"]
                                val_errors = self._validate_args(args, schema)
                                if val_errors:
                                    error_msg = f"Validazione fallita per tool '{tool_name}': {', '.join(val_errors)}"
                                    logger.warning(
                                        "step_tool_validation_failed",
                                        tool=tool_name,
                                        errors=val_errors,
                                    )
                                    # Se abbiamo errori di validazione, solleviamo un'eccezione per triggerare il feedback loop
                                    raise ValueError(error_msg)

                        tool_tasks.append(ToolTask(tool_name=tool_name, arguments=args))

                # Se siamo arrivati qui senza eccezioni, abbiamo finito
                if skipped_hallucination > 0:
                    logger.warning(
                        "step_tool_hallucinations_total",
                        step_id=step_id,
                        skipped=skipped_hallucination,
                        valid=len(tool_tasks),
                    )

                logger.debug(
                    "step_tools_selected",
                    step_id=step_id,
                    tools_available=len(tools),
                    tools_selected=len(tool_tasks),
                )
                return tool_tasks

            except ValueError as e:
                feedback_context = str(e)
                logger.info(
                    "react_feedback_loop_trigger",
                    step_id=step_id,
                    error=feedback_context,
                    attempt=attempt + 1,
                )
                # Riprova il ciclo con il feedback aggiunto
                continue

        # If all attempts fail, return empty
        return []

    async def _build_step_prompt(
        self,
        step_id: int,
        total_tools: int,
        current_datetime: str,
        graph_hints: str | None = None,
        original_query: str = "",
    ) -> str:
        """Build system prompt for step execution.

        Instructs the LLM to:
        1. Call tools directly without explanation
        2. Use results from previous steps to parameterize calls
        3. Maximize data retrieval depth
        4. Use SHORT, SIMPLE search queries
        5. DO NOT quote keys and values with backslashes
        """

        hints_section = ""
        if graph_hints:
            hints_section = (
                f"\n=== STRICT TOOL GUIDELINES (Hand-Crafted GraphRAG) ===\n{graph_hints}\n"
            )

        # SOTA 2026: Entity Context Injection
        # Extract potential entities from the original query (Capitalized words or quotes)
        # This helps the LLM not "broaden" queries away from the actual target (e.g. Castelvetere)
        import re

        potential_entities = re.findall(r'"([^"]*)"', original_query)
        # Simple fallback to words that look like entities if no quotes
        if not potential_entities:
            potential_entities = [
                w for w in re.findall(r"\b[A-Z][a-z]+\b", original_query) if len(w) > 3
            ]

        entity_instruction = ""
        if potential_entities:
            entity_list = ", ".join(set(potential_entities[:5]))
            entity_instruction = (
                f"\n=== CRITICAL ENTITIES (MUST INCLUDE IN SEARCHES) ===\n{entity_list}\n"
            )

        base_prompt = f"""CALL TOOLS DIRECTLY. NO EXPLANATION.

RULES:
1. Call the most appropriate tool(s) for this step.
2. If previous steps found IDs (file_id, message_id, folder_id, event_id),
   USE THEM to drill deeper (e.g., read file_id="XYZ").
3. SEARCH QUERIES MUST BE EXTREMELY SPECIFIC. Include the relevant entities below.
   - WRONG: query="ANCI project"
   - CORRECT: query="Castelvetere ANCI project"
4. {entity_instruction}
5. Use generous max_results (20+).
6. You may call MULTIPLE tools in one step.

=== JSON RULES ===
- Output ONLY valid tool calls using the provided tools.
- DO NOT quote JSON keys or values with literal backslashes.

{hints_section}
Step {step_id}. Tools: {total_tools}. Date: {current_datetime}.
NOW EXECUTE:"""

        return base_prompt

    async def _ensure_fewshot_index_exists(self, driver) -> None:
        """Ensure the vector index exists, creating it if necessary."""
        try:
            async with driver.session() as session:
                # Check if it exists
                res = await session.run(
                    "SHOW INDEXES WHERE name = 'fewshot_embeddings' AND type = 'VECTOR'"
                )
                record = await res.single()

                if not record:
                    logger.info("creating_missing_vector_index", index="fewshot_embeddings")
                    await session.run(
                        """
                        CALL db.index.vector.createNodeIndex(
                            'fewshot_embeddings',
                            'FewShotExample',
                            'embedding',
                            1024,
                            'cosine'
                        )
                        """
                    )
        except Exception as e:
            logger.warning("vector_index_check_failed", error=str(e), error_type=type(e).__name__)

    async def _get_graph_prompt_hints(
        self, domain: str, tool_names: list[str], query: str | None = None
    ) -> dict[str, Any]:
        """Retrieve hand-crafted prompt templates from Neo4j (GraphRAG Layer 1).

        SOTA 2026: Performance optimization via session caching and
        Two-Stage Hybrid Retrieval for Few-Shot Examples (Graph + Vector).
        """
        import asyncio

        # Cache Key based on domain, sorted tool names, and query if present
        cache_key = f"{domain}:" + ",".join(sorted(tool_names))
        if query:
            cache_key += f":{hash(query)}"

        if cache_key in self._hints_cache:
            logger.debug("graph_hints_cache_hit", key=cache_key)
            self._cache_hits = getattr(self, "_cache_hits", 0) + 1
            return self._hints_cache[cache_key]

        import yaml

        from me4brain.memory.semantic import get_semantic_memory

        semantic = get_semantic_memory()
        driver = await semantic.get_driver()
        if not driver:
            return {"hints": "", "constraints": {}}

        hints_parts = []
        constraints = {}

        # Timeouts for Neo4j operations (seconds)
        neo4j_query_timeout = 10.0  # 10 seconds per query

        try:
            async with driver.session() as session:
                # 1. Domain Hints (with timeout protection)
                try:
                    domain_res = await asyncio.wait_for(
                        session.run(
                            "MATCH (d:DomainTemplate {id: $id}) RETURN d.content as content",
                            {"id": domain},
                        ),
                        timeout=neo4j_query_timeout,
                    )
                    domain_record = await asyncio.wait_for(
                        domain_res.single(), timeout=neo4j_query_timeout
                    )
                    if domain_record:
                        hints_parts.append(
                            f"DOMAIN [{domain.upper()}]:\n{domain_record['content']}"
                        )
                except TimeoutError:
                    logger.warning(
                        "graph_domain_hints_timeout",
                        domain=domain,
                        timeout_seconds=neo4j_query_timeout,
                    )
                except Exception as e:
                    logger.warning(
                        "graph_domain_hints_error",
                        domain=domain,
                        error=str(e),
                        error_type=type(e).__name__,
                    )

                # 2. Tool-Specific Constraints & Rules (with timeout protection)
                try:
                    tool_res = await asyncio.wait_for(
                        session.run(
                            """
                             MATCH (t:ToolTemplate)
                             WHERE t.id IN $tool_names
                             RETURN t.id as id, t.constraints as constraints, t.hard_rules as hard_rules,
                                    t.version as version, t.deprecated as deprecated, t.migration_hint as migration_hint
                             """,
                            {"tool_names": tool_names},
                        ),
                        timeout=neo4j_query_timeout,
                    )

                    async for record in tool_res:
                        tool_id = record["id"]
                        tool_hint = f"TOOL [{tool_id}] (v{record.get('version', '1.0')}):\n"

                        # SOTA 2026: Deprecation warning injection
                        if record.get("deprecated"):
                            tool_hint += f" !!! DEPRECATED !!!: {record.get('migration_hint', 'Utilizza una versione più recente.')}\n"

                        # Parse constraints for both prompting and validation
                        c_data = {}
                        if record["constraints"]:
                            try:
                                c_data = yaml.safe_load(record["constraints"])
                                constraints[tool_id] = c_data
                                tool_hint += f" vincoli: {record['constraints']}\n"
                            except yaml.YAMLError:
                                logger.warning("tool_constraints_parse_error", tool_id=tool_id)

                        if record["hard_rules"]:
                            tool_hint += f" regole: {record['hard_rules']}\n"

                        hints_parts.append(tool_hint)
                except TimeoutError:
                    logger.warning(
                        "graph_tool_hints_timeout",
                        tool_names_count=len(tool_names),
                        timeout_seconds=neo4j_query_timeout,
                    )
                except Exception as e:
                    logger.warning(
                        "graph_tool_hints_error",
                        tool_names_count=len(tool_names),
                        error=str(e),
                        error_type=type(e).__name__,
                    )

                # 3. Hybrid Few-Shot Retrieval (Graph-restrained Vector Search)
                if query:
                    print(f"DEBUG: Vector search for few-shots related to query: {query[:50]}")
                    # Ensure index exists first
                    try:
                        await asyncio.wait_for(
                            self._ensure_fewshot_index_exists(driver), timeout=neo4j_query_timeout
                        )
                    except TimeoutError:
                        logger.warning(
                            "graph_fewshot_index_timeout",
                            timeout_seconds=neo4j_query_timeout,
                        )
                    except Exception:
                        pass  # Index creation failure is non-critical

                    try:
                        query_embedding = await self._llm.generate_embeddings(query)
                    except NotImplementedError:
                        # Fallback to standard embedding service
                        from me4brain.embeddings.bge_m3 import get_embedding_service

                        service = get_embedding_service()
                        query_embedding = await service.embed_query_async(query)

                    try:
                        # SOTA 2026: Cypher for Vector Similarity inside valid tool candidates (with timeout)
                        few_shot_res = await asyncio.wait_for(
                            session.run(
                                """
                                 CALL db.index.vector.queryNodes('fewshot_embeddings', 3, $embedding)
                                 YIELD node as e, score
                                 MATCH (e)-[:EXAMPLE_FOR]->(t:ToolTemplate)
                                 WHERE t.id IN $tool_names
                                 RETURN e.content as content, score, t.id as tool_id
                                 LIMIT 5
                                 """,
                                {"embedding": query_embedding, "tool_names": tool_names},
                            ),
                            timeout=neo4j_query_timeout,
                        )

                        examples = []
                        async for fs_record in few_shot_res:
                            examples.append(fs_record["content"])

                        if examples:
                            hints_parts.append(
                                "\n=== FEW-SHOT EXAMPLES (CONTEXTUALLY RELEVANT) ===\n"
                            )
                            hints_parts.extend(examples)
                    except TimeoutError:
                        logger.warning(
                            "graph_fewshot_search_timeout",
                            timeout_seconds=neo4j_query_timeout,
                        )
                    except Exception as vector_err:
                        logger.warning(
                            "graph_fewshot_search_failed",
                            error=str(vector_err),
                            error_type=type(vector_err).__name__,
                            hint="Continuing without few-shot examples.",
                        )
        except Exception as session_err:
            logger.warning(
                "graph_session_error",
                error=str(session_err),
                error_type=type(session_err).__name__,
            )

        if not hints_parts:
            # Fallback to file-based registry if graph is empty for this query
            return {
                "hints": self._registry.get_combined_hints(domain, tool_names),
                "constraints": {},
            }

        result = {
            "hints": "\n\n".join(
                hints_parts
            ),  # Changed from '\n' to '\n\n' to match original logic
            "constraints": constraints,
        }

        # Save to cache
        self._hints_cache[cache_key] = result
        return result

    def _validate_args(self, args: dict, schema: dict) -> list[str]:
        """Lightweight JSON Schema validator for Layer 3."""
        errors = []
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        # Check required fields
        for field_name in required:
            if field_name not in args:
                errors.append(f"parametro mancante: '{field_name}'")

        # Check types (simple mapping)
        for field_name, value in args.items():
            if field_name not in properties:
                # We can allow extra params or be strict. For GraphRAG, we are strict.
                errors.append(f"parametro non autorizzato: '{field_name}'")
                continue

            p_conf = properties[field_name]
            p_type = p_conf.get("type")

            if p_type == "string" and not isinstance(value, str):
                errors.append(f"'{field_name}' deve essere stringa")
            elif p_type == "integer" and not isinstance(value, int):
                # JSON might parse numbers as floats
                if isinstance(value, float) and value.is_integer():
                    args[field_name] = int(value)
                else:
                    errors.append(f"'{field_name}' deve essere intero")
            elif p_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"'{field_name}' deve essere numero")
            elif p_type == "boolean" and not isinstance(value, bool):
                errors.append(f"'{field_name}' deve essere booleano")
            elif p_type == "array" and not isinstance(value, list):
                errors.append(f"'{field_name}' deve essere lista")
            elif p_type == "object" and not isinstance(value, dict):
                errors.append(f"'{field_name}' deve essere oggetto")

        if errors:
            logger.warning(
                "telemetry_validation_failed",
                tool_schema_errors=len(errors),
                errors=errors[:3],  # Log first 3 errors for analytics
            )
        else:
            logger.info("telemetry_validation_success")

        return errors
