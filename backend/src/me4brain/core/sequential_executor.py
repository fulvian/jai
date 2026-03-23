"""Sequential DAG Executor per query complesse multi-step.

Gestisce query che richiedono esecuzione sequenziale con dipendenze dati,
dove l'output di uno step diventa input del successivo.

Esempio query: "Cerca file su Drive, analizza contenuto, crea report"
Steps:
1. drive_search(query="progetto X") → files[]
2. drive_get_content(file_id=$s1.files[0].id) → content
3. docs_create(title="Report", content=$s2.content) → doc_id

Usage:
    executor = SequentialDAGExecutor(tool_executor)
    results = await executor.execute(steps, context)
"""

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ExecutionStep:
    """Singolo step di esecuzione con dipendenze."""

    id: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    # output_mapping: come mappare output per step dipendenti
    # Esempio: {"file_id": "$s1.files[0].id"}
    output_mapping: dict[str, str] = field(default_factory=dict)


@dataclass
class StepResult:
    """Risultato di uno step."""

    step_id: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    execution_time_ms: float = 0.0


class SequentialDAGExecutor:
    """Esegue step in ordine topologico rispettando dipendenze.

    Features:
    - Topological sort per ordine esecuzione
    - Risoluzione riferimenti output ($s1.files[0].id)
    - Error propagation (step falliti bloccano dipendenti)
    - Timeout per step singoli
    """

    def __init__(
        self,
        tool_executor: Any = None,
        step_timeout: float = 30.0,
    ):
        """Inizializza executor.

        Args:
            tool_executor: ToolExecutor per esecuzione effettiva
            step_timeout: Timeout per singolo step in secondi
        """
        self.tool_executor = tool_executor
        self.step_timeout = step_timeout

    async def execute(
        self,
        steps: list[ExecutionStep],
        context: dict[str, Any] | None = None,
    ) -> dict[str, StepResult]:
        """Esegue step in ordine topologico.

        Args:
            steps: Lista step da eseguire
            context: Contesto opzionale (tenant_id, user_id, etc.)

        Returns:
            Dict step_id -> StepResult
        """
        context = context or {}
        results: dict[str, StepResult] = {}
        outputs: dict[str, Any] = {}  # step_id -> output data

        # 1. Valida e ordina step
        try:
            ordered_steps = self._topological_sort(steps)
        except ValueError as e:
            logger.error("dag_cycle_detected", error=str(e))
            return {
                "error": StepResult(
                    step_id="dag_validation",
                    success=False,
                    error=f"Ciclo rilevato nel DAG: {e}",
                )
            }

        logger.info(
            "dag_execution_start",
            total_steps=len(ordered_steps),
            order=[s.id for s in ordered_steps],
        )

        # 2. Esegui in ordine
        for step in ordered_steps:
            # Check dipendenze fallite
            failed_deps = [
                dep for dep in step.depends_on if dep in results and not results[dep].success
            ]
            if failed_deps:
                results[step.id] = StepResult(
                    step_id=step.id,
                    success=False,
                    error=f"Dipendenze fallite: {failed_deps}",
                )
                logger.warning("step_skipped_failed_deps", step=step.id, failed_deps=failed_deps)
                continue

            # Risolvi argomenti con riferimenti output
            try:
                resolved_args = self._resolve_args(step.args, outputs)
            except KeyError as e:
                results[step.id] = StepResult(
                    step_id=step.id,
                    success=False,
                    error=f"Riferimento output non trovato: {e}",
                )
                continue

            # Esegui step
            result = await self._execute_step(step, resolved_args, context)
            results[step.id] = result

            if result.success:
                outputs[step.id] = result.data
                logger.info(
                    "step_completed",
                    step=step.id,
                    tool=step.tool,
                    time_ms=result.execution_time_ms,
                )
            else:
                logger.warning(
                    "step_failed",
                    step=step.id,
                    tool=step.tool,
                    error=result.error,
                )

        return results

    def _topological_sort(self, steps: list[ExecutionStep]) -> list[ExecutionStep]:
        """Ordina step in ordine topologico (Kahn's algorithm).

        Raises:
            ValueError: Se esiste un ciclo
        """
        step_map = {s.id: s for s in steps}
        in_degree = {s.id: 0 for s in steps}
        adj = {s.id: [] for s in steps}

        for step in steps:
            for dep in step.depends_on:
                if dep in step_map:
                    adj[dep].append(step.id)
                    in_degree[step.id] += 1

        # Queue con step senza dipendenze
        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            current = queue.pop(0)
            result.append(step_map[current])
            for neighbor in adj[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(steps):
            cycle_nodes = [sid for sid, deg in in_degree.items() if deg > 0]
            raise ValueError(f"Ciclo rilevato tra: {cycle_nodes}")

        return result

    def _resolve_args(
        self,
        args: dict[str, Any],
        outputs: dict[str, Any],
    ) -> dict[str, Any]:
        """Risolve riferimenti output negli argomenti.

        Formato: $step_id.path.to.value o $step_id.array[0].field

        Examples:
            $s1.files[0].id → outputs["s1"]["files"][0]["id"]
            $s2.content → outputs["s2"]["content"]
        """
        resolved = {}
        for key, value in args.items():
            if isinstance(value, str) and value.startswith("$"):
                resolved[key] = self._resolve_reference(value, outputs)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_args(value, outputs)
            else:
                resolved[key] = value
        return resolved

    def _resolve_reference(self, ref: str, outputs: dict[str, Any]) -> Any:
        """Risolve singolo riferimento $step_id.path.

        Supporta:
        - $s1.field
        - $s1.nested.field
        - $s1.array[0].field
        """
        # Pattern: $step_id.path
        match = re.match(r"\$(\w+)(.*)", ref)
        if not match:
            raise KeyError(f"Formato riferimento invalido: {ref}")

        step_id = match.group(1)
        path = match.group(2)

        if step_id not in outputs:
            raise KeyError(f"Step '{step_id}' non trovato in outputs")

        value = outputs[step_id]

        # Naviga il path
        if path:
            for part in self._parse_path(path):
                value = value[part] if isinstance(part, int) else value[part]

        return value

    def _parse_path(self, path: str) -> list[str | int]:
        """Parse path come .field o [index]."""
        parts = []
        current = ""

        i = 0
        while i < len(path):
            if path[i] == ".":
                if current:
                    parts.append(current)
                current = ""
            elif path[i] == "[":
                if current:
                    parts.append(current)
                    current = ""
                # Find closing bracket
                end = path.find("]", i)
                if end == -1:
                    raise KeyError(f"Bracket non chiuso in: {path}")
                index = int(path[i + 1 : end])
                parts.append(index)
                i = end
            else:
                current += path[i]
            i += 1

        if current:
            parts.append(current)

        return parts

    async def _execute_step(
        self,
        step: ExecutionStep,
        args: dict[str, Any],
        context: dict[str, Any],
    ) -> StepResult:
        """Esegue singolo step con timeout."""
        import time

        start = time.perf_counter()

        try:
            # Timeout per step
            result = await asyncio.wait_for(
                self._call_tool(step.tool, args, context),
                timeout=self.step_timeout,
            )

            elapsed = (time.perf_counter() - start) * 1000

            if result.get("error"):
                return StepResult(
                    step_id=step.id,
                    success=False,
                    error=str(result.get("error")),
                    execution_time_ms=elapsed,
                )

            return StepResult(
                step_id=step.id,
                success=True,
                data=result,
                execution_time_ms=elapsed,
            )

        except TimeoutError:
            elapsed = (time.perf_counter() - start) * 1000
            return StepResult(
                step_id=step.id,
                success=False,
                error=f"Timeout dopo {self.step_timeout}s",
                execution_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.exception("step_execution_error", step=step.id, tool=step.tool)
            return StepResult(
                step_id=step.id,
                success=False,
                error=str(e),
                execution_time_ms=elapsed,
            )

    async def _call_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Chiama tool via ToolExecutor o handler diretto."""
        # Import dinamico per evitare circular imports
        if self.tool_executor:
            from me4brain.retrieval.tool_executor import ExecutionRequest

            request = ExecutionRequest(
                tool_name=tool_name,
                arguments=args,
                tenant_id=context.get("tenant_id", "default"),
                user_id=context.get("user_id", "anonymous"),
            )
            return await self.tool_executor.execute(request)

        # Fallback: cerca tool nei domain handlers
        return await self._execute_via_domain_handler(tool_name, args, context)

    async def _execute_via_domain_handler(
        self,
        tool_name: str,
        args: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Esegue tool cercando il domain handler appropriato."""
        # Google Workspace tools
        if tool_name.startswith("drive_") or tool_name.startswith("docs_"):
            from me4brain.domains.google_workspace.tools import google_api

            tool_func = getattr(google_api, tool_name, None)
            if tool_func:
                return await tool_func(**args)

        # Fallback generico
        return {"error": f"Tool '{tool_name}' non trovato"}


def parse_steps_from_analysis(analysis: dict[str, Any]) -> list[ExecutionStep]:
    """Converte output analyze_query in ExecutionStep.

    Expected format:
    {
        "execution_strategy": "sequential",
        "steps": [
            {"id": "s1", "tool": "drive_search", "args": {...}},
            {"id": "s2", "tool": "drive_get_content", "depends_on": ["s1"], "args": {...}}
        ]
    }
    """
    steps_data = analysis.get("steps", [])
    if not steps_data:
        return []

    return [
        ExecutionStep(
            id=s["id"],
            tool=s["tool"],
            args=s.get("args", {}),
            depends_on=s.get("depends_on", []),
            output_mapping=s.get("output_mapping", {}),
        )
        for s in steps_data
    ]
