"""Execution Monitor - Hook nel Tool Calling Engine per tracciare esecuzioni."""

import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Optional

import structlog

from me4brain.core.skills.types import ExecutionTrace, ToolCall

logger = structlog.get_logger(__name__)


class ExecutionMonitor:
    """
    Monitora esecuzioni tool per auto-learning.

    Si aggancia al Tool Calling Engine per tracciare le catene di tool call
    e inviare le tracce al Crystallizer per potenziale cristallizzazione.
    """

    def __init__(
        self,
        on_trace_complete: Optional[Callable[[ExecutionTrace], None]] = None,
        min_tools_for_crystallization: int = 2,
    ):
        """
        Inizializza il monitor.

        Args:
            on_trace_complete: Callback chiamata quando una trace è completa
            min_tools_for_crystallization: Numero minimo di tool per considerare
                                           la cristallizzazione (default: 2)
        """
        self.on_trace_complete = on_trace_complete
        self.min_tools = min_tools_for_crystallization

        # Tracce attive per sessione
        self._traces: dict[str, ExecutionTrace] = {}
        self._start_times: dict[str, float] = {}

    def start_trace(self, session_id: str, input_query: str) -> None:
        """
        Inizia una nuova trace per la sessione.

        Args:
            session_id: ID della sessione
            input_query: Query utente originale
        """
        self._traces[session_id] = ExecutionTrace(
            session_id=session_id,
            input_query=input_query,
            tool_chain=[],
            created_at=datetime.now(),
        )
        self._start_times[session_id] = time.perf_counter()

        logger.debug("execution_trace_started", session_id=session_id)

    async def on_tool_start(self, session_id: str, tool_name: str, args: dict[str, Any]) -> None:
        """Hook called at the start of a tool execution for a specific session."""
        if session_id not in self._traces:
            logger.warning("on_tool_start_without_trace", session_id=session_id)
            return

        trace = self._traces[session_id]
        tool_call = ToolCall(
            name=tool_name,
            args=args,
            result=None,
            success=True,
            duration_ms=0.0,
        )
        tool_call._start_time = time.perf_counter()  # type: ignore
        trace.tool_chain.append(tool_call)

    async def on_tool_end(
        self,
        session_id: str,
        tool_name: str,
        result: Any,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Hook called at the end of a tool execution for a specific session."""
        if session_id not in self._traces:
            return

        trace = self._traces[session_id]
        for tool_call in reversed(trace.tool_chain):
            if tool_call.name == tool_name and tool_call.result is None:
                end_time = time.perf_counter()
                start_time = getattr(tool_call, "_start_time", end_time)
                tool_call.result = result
                tool_call.success = success
                tool_call.error = error
                tool_call.duration_ms = (end_time - start_time) * 1000
                break

    def finalize_trace(
        self, session_id: str, final_output: Optional[str] = None, overall_success: bool = True
    ) -> Optional[ExecutionTrace]:
        """
        Completa trace e invia a crystallizer.

        Args:
            session_id: ID della sessione da finalizzare
            final_output: Output finale della pipeline
            overall_success: Se l'intera esecuzione è stata un successo

        Returns:
            ExecutionTrace completata, o None se non c'era trace attiva
        """
        if session_id not in self._traces:
            return None

        trace = self._traces.pop(session_id)
        start_time = self._start_times.pop(session_id, None)

        # Calcola durata totale
        if start_time:
            trace.total_duration_ms = (time.perf_counter() - start_time) * 1000

        trace.final_output = final_output
        trace.success = overall_success and all(t.success for t in trace.tool_chain)

        logger.info(
            "execution_trace_finalized",
            session_id=trace.session_id,
            tool_count=len(trace.tool_chain),
            success=trace.success,
            duration_ms=trace.total_duration_ms,
        )

        # Invia a crystallizer se la trace è abbastanza interessante
        if self.on_trace_complete and len(trace.tool_chain) >= self.min_tools and trace.success:
            try:
                self.on_trace_complete(trace)
            except Exception as e:
                logger.error("crystallizer_callback_error", error=str(e), session_id=session_id)

        return trace

    def abort_trace(self, session_id: str, reason: str = "aborted") -> None:
        """Abort trace for a specific session."""
        if session_id in self._traces:
            self._traces.pop(session_id)
            self._start_times.pop(session_id, None)
            logger.info("execution_trace_aborted", session_id=session_id, reason=reason)

    def get_trace(self, session_id: str) -> Optional[ExecutionTrace]:
        """Get the current trace for a session."""
        return self._traces.get(session_id)

    @property
    def active_sessions_count(self) -> int:
        """Count of currently active execution traces."""
        return len(self._traces)
