"""Adaptive Context Compressor - SOTA 2026.

Compressione autonoma del contesto inter-step basata su:
- Anchored Iterative Summarization (Zylos Research, Feb 2026)
- Trajectory Reduction (Zylos Research, Mar 2026)
- Autonomous Context Compression (LangChain Deep Agents SDK, Mar 2026)

Strategia a 3 livelli:
1. LIGHT (context < 40% window): solo dedup + truncation
2. MEDIUM (context 40-70% window): summarize risultati vecchi, mantieni ancore
3. AGGRESSIVE (context > 70% window): summarize tutto tranne ancore + ultima query
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

import structlog

if TYPE_CHECKING:
    from me4brain.engine.iterative_executor import ExecutionContext
    from me4brain.llm.base import LLMProvider

logger = structlog.get_logger(__name__)


class CompressionLevel(str, Enum):
    LIGHT = "LIGHT"
    MEDIUM = "MEDIUM"
    AGGRESSIVE = "AGGRESSIVE"


@dataclass
class AnchorData:
    """Dati che devono essere preservati durante la compressione."""

    critical_ids: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    last_user_query: str = ""
    system_prompt_hash: str = ""


@dataclass
class CompressionResult:
    """Risultato della compressione del contesto."""

    compressed_context: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    level: CompressionLevel
    anchors_preserved: int
    summary_generated: bool


class AdaptiveContextCompressor:
    """Compressione autonoma del contesto inter-step.

    SOTA 2026: Compressione intelligente che preserva "ancore" critiche
    mentre riduce la narrativa (risultati tool, reasoning intermedio).

    Target: 85% compaction rate mantenendo output quality.
    """

    LIGHT_THRESHOLD = 0.40
    MEDIUM_THRESHOLD = 0.70
    OUTPUT_RESERVE_RATIO = 0.15
    SAFETY_MARGIN_RATIO = 0.05

    def __init__(
        self,
        context_window: int = 32768,
        output_reserve: int = 4096,
        llm_provider: Optional[LLMProvider] = None,
        fast_model: str = "qwen3.5-4b-mlx",
    ):
        self.context_window = context_window
        self.output_reserve = output_reserve
        self.effective_budget = int(
            context_window * (1 - self.OUTPUT_RESERVE_RATIO - self.SAFETY_MARGIN_RATIO)
        )
        self._anchors: AnchorData = AnchorData()
        self._compressed_history: str = ""
        self._llm = llm_provider
        self._fast_model = fast_model
        self._compression_count = 0
        self._total_tokens_saved = 0

    def estimate_tokens(self, text: str) -> int:
        """Stima veloce: ~4 chars per token per modelli piccoli."""
        return max(1, len(text) // 4)

    def get_compression_level(self, current_context: str) -> CompressionLevel:
        """Determina livello di compressione necessario."""
        usage = self.estimate_tokens(current_context) / self.effective_budget
        if usage < self.LIGHT_THRESHOLD:
            return CompressionLevel.LIGHT
        elif usage < self.MEDIUM_THRESHOLD:
            return CompressionLevel.MEDIUM
        else:
            return CompressionLevel.AGGRESSIVE

    def extract_anchors(
        self, context: str, exec_context: Optional[ExecutionContext] = None
    ) -> AnchorData:
        """Estrae ancore dal contesto (dati critici da preservare).

        Ancore identificate:
        - ID estratti (file_id, message_id, event_id, folder_id)
        - Decisioni chiave (SUFFICIENT, RETRY, DEEPER)
        - Constraints utente
        - Ultima query utente
        """
        anchors = AnchorData()

        id_patterns = [
            r'file_id=["\']([^"\']+)["\']',
            r'message_id=["\']([^"\']+)["\']',
            r'event_id=["\']([^"\']+)["\']',
            r'folder_id=["\']([^"\']+)["\']',
            r'doc_id=["\']([^"\']+)["\']',
            r'threadId=["\']([^"\']+)["\']',
            r'"id":\s*"([^"]+)"',
        ]

        for pattern in id_patterns:
            matches = re.findall(pattern, context)
            anchors.critical_ids.extend(matches)

        anchors.critical_ids = list(dict.fromkeys(anchors.critical_ids))[:50]

        decision_patterns = [
            r"(SUFFICIENT|RETRY|DEEPER):\s*([^\n]+)",
        ]
        for pattern in decision_patterns:
            matches = re.findall(pattern, context)
            for match in matches:
                anchors.decisions.append(f"{match[0]}: {match[1][:100]}")

        if exec_context and hasattr(exec_context, "original_query"):
            anchors.last_user_query = exec_context.original_query[:500]

        return anchors

    def _deduplicate_content(self, context: str) -> str:
        """Rimuove contenuto duplicato dal contesto."""
        lines = context.split("\n")
        seen = set()
        unique_lines = []

        for line in lines:
            normalized = line.strip().lower()
            if len(normalized) > 20:
                if normalized not in seen:
                    seen.add(normalized)
                    unique_lines.append(line)
            else:
                unique_lines.append(line)

        return "\n".join(unique_lines)

    def _truncate_results(self, context: str, max_chars_per_result: int = 500) -> str:
        """Tronca risultati tool lunghi mantenendo struttura."""
        result_pattern = r"(- \w+: )(.{500,}?)(?=\n- |\n\n|$)"

        def truncate_match(match):
            prefix = match.group(1)
            content = match.group(2)
            if len(content) > max_chars_per_result:
                return f"{prefix}{content[:max_chars_per_result]}... [truncated]"
            return match.group(0)

        return re.sub(result_pattern, truncate_match, context, flags=re.DOTALL)

    async def _llm_summarize(
        self, content: str, max_words: int = 150, focus: str = "results"
    ) -> str:
        """Usa LLM per generare summary del contenuto."""
        if not self._llm:
            return self._heuristic_summarize(content, max_words)

        from me4brain.llm.models import LLMRequest, Message

        prompt = f"""Summarize the following {focus} concisely (max {max_words} words).
Preserve ALL IDs, names, and key numbers. Focus on actionable results.

Content to summarize:
{content[:4000]}

Summary:"""

        try:
            request = LLMRequest(
                messages=[Message(role="user", content=prompt)],
                model=self._fast_model,
                temperature=0.1,
                max_tokens=max_words * 2,
            )
            response = await self._llm.generate_response(request)
            return response.content.strip() if response.content else ""
        except Exception as e:
            logger.warning("llm_summarize_failed", error=str(e))
            return self._heuristic_summarize(content, max_words)

    def _heuristic_summarize(self, content: str, max_words: int = 150) -> str:
        """Summarizzazione euristica senza LLM."""
        id_pattern = r'(file_id|message_id|event_id|folder_id|doc_id|id)=["\']?([^"\'\s,]+)["\']?'
        ids = re.findall(id_pattern, content)

        number_pattern = r"\b(\d+(?:\.\d+)?)\s*(file|email|event|document|result|item)s?\b"
        numbers = re.findall(number_pattern, content)

        summary_parts = []

        if ids:
            id_summary = "IDs found: " + ", ".join([f"{k}={v}" for k, v in ids[:10]])
            summary_parts.append(id_summary)

        if numbers:
            count_summary = ", ".join([f"{n} {t}" for n, t in numbers[:5]])
            summary_parts.append(count_summary)

        first_sentences = re.split(r"[.!?]", content)
        if first_sentences:
            summary_parts.append(first_sentences[0][:200])

        summary = ". ".join(summary_parts)
        words = summary.split()
        if len(words) > max_words:
            summary = " ".join(words[:max_words]) + "..."

        return summary

    def _build_compressed_context(
        self,
        original_context: str,
        anchors: AnchorData,
        level: CompressionLevel,
    ) -> str:
        """Costruisce il contesto compresso preservando le ancore."""
        parts = []

        if anchors.last_user_query:
            parts.append(f"### Query originale:\n{anchors.last_user_query}\n")

        if anchors.critical_ids:
            parts.append("### ID disponibili:")
            for id_ref in anchors.critical_ids[:30]:
                parts.append(f"  - {id_ref}")
            parts.append("")

        if anchors.decisions:
            parts.append("### Decisioni precedenti:")
            for decision in anchors.decisions[-5:]:
                parts.append(f"  - {decision}")
            parts.append("")

        if level == CompressionLevel.LIGHT:
            compressed = self._deduplicate_content(original_context)
            compressed = self._truncate_results(compressed, 1000)
            parts.append(compressed)
        elif level == CompressionLevel.MEDIUM:
            compressed = self._deduplicate_content(original_context)
            compressed = self._truncate_results(compressed, 500)
            parts.append("### Risultati (compresso):")
            parts.append(compressed)
        else:
            if self._compressed_history:
                parts.append("### Storico compresso:")
                parts.append(self._compressed_history[:2000])
                parts.append("")

            summary = self._heuristic_summarize(original_context, 100)
            parts.append("### Summary risultati:")
            parts.append(summary)

        return "\n".join(parts)

    async def compress(
        self,
        exec_context: ExecutionContext,
        current_step: int,
        total_steps: int,
    ) -> CompressionResult:
        """Comprimi il contesto preservando le ancore.

        Args:
            exec_context: Contesto di esecuzione con tutti gli step results
            current_step: Step corrente (1-indexed)
            total_steps: Totale step previsti

        Returns:
            CompressionResult con il contesto compresso e metriche
        """
        start_time = time.time()

        raw_context = exec_context.get_context_summary()
        original_tokens = self.estimate_tokens(raw_context)

        level = self.get_compression_level(raw_context)

        if level == CompressionLevel.LIGHT and original_tokens < self.effective_budget * 0.3:
            return CompressionResult(
                compressed_context=raw_context,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                compression_ratio=1.0,
                level=level,
                anchors_preserved=0,
                summary_generated=False,
            )

        self._anchors = self.extract_anchors(raw_context, exec_context)

        compressed = self._build_compressed_context(raw_context, self._anchors, level)
        compressed_tokens = self.estimate_tokens(compressed)

        compression_ratio = compressed_tokens / original_tokens if original_tokens > 0 else 1.0

        self._compression_count += 1
        self._total_tokens_saved += original_tokens - compressed_tokens

        logger.info(
            "context_compressed",
            level=level.value,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=round(compression_ratio, 2),
            anchors_count=len(self._anchors.critical_ids),
            step=f"{current_step}/{total_steps}",
            elapsed_ms=round((time.time() - start_time) * 1000, 2),
        )

        return CompressionResult(
            compressed_context=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=compression_ratio,
            level=level,
            anchors_preserved=len(self._anchors.critical_ids),
            summary_generated=level != CompressionLevel.LIGHT,
        )

    def get_stats(self) -> dict[str, Any]:
        """Statistiche di compressione della sessione."""
        return {
            "compression_count": self._compression_count,
            "total_tokens_saved": self._total_tokens_saved,
            "context_window": self.context_window,
            "effective_budget": self.effective_budget,
            "anchors_cached": len(self._anchors.critical_ids),
        }


class ContextWindowTracker:
    """Traccia l'utilizzo del context window in tempo reale.

    SOTA 2026: Tracking esplicito del context window usage per evitare overflow.
    """

    def __init__(self, model_context_window: int = 32768):
        self.max_tokens = model_context_window
        self.used_tokens = 0
        self.peak_tokens = 0
        self._history: list[dict[str, Any]] = []
        self._component_tokens: dict[str, int] = {}

    def record(self, component: str, tokens: int) -> None:
        """Registra utilizzo token per un componente."""
        self.used_tokens = tokens
        self.peak_tokens = max(self.peak_tokens, tokens)
        self._history.append(
            {
                "component": component,
                "tokens": tokens,
                "timestamp": time.time(),
            }
        )
        self._component_tokens[component] = tokens

    def add_tokens(self, component: str, additional_tokens: int) -> None:
        """Aggiunge token al tracking esistente."""
        self.used_tokens += additional_tokens
        self.peak_tokens = max(self.peak_tokens, self.used_tokens)
        self._component_tokens[component] = (
            self._component_tokens.get(component, 0) + additional_tokens
        )

    @property
    def usage_pct(self) -> float:
        """Percentuale di utilizzo del context window."""
        return self.used_tokens / self.max_tokens if self.max_tokens > 0 else 0

    @property
    def remaining(self) -> int:
        """Token rimanenti nel context window."""
        return max(0, self.max_tokens - self.used_tokens)

    def can_fit(self, additional_tokens: int, safety_margin: float = 0.15) -> bool:
        """Verifica se ci sono abbastanza token disponibili."""
        threshold = self.max_tokens * (1 - safety_margin)
        return (self.used_tokens + additional_tokens) < threshold

    def get_budget_for_step(self, step: int, total_steps: int) -> int:
        """Calcola budget token per uno step specifico.

        Distribuisce il budget in modo che gli step critici
        (primi e ultimi) ricevano più budget.
        """
        usable_budget = int(self.max_tokens * 0.80)

        if total_steps <= 1:
            return usable_budget

        step_position = step / total_steps

        if step_position < 0.2:
            weight = 1.3
        elif step_position > 0.8:
            weight = 1.2
        else:
            weight = 1.0

        base_per_step = usable_budget / total_steps
        return int(base_per_step * weight)

    def get_status(self) -> dict[str, Any]:
        """Stato attuale del context window tracker."""
        return {
            "max_tokens": self.max_tokens,
            "used_tokens": self.used_tokens,
            "peak_tokens": self.peak_tokens,
            "remaining_tokens": self.remaining,
            "usage_pct": round(self.usage_pct * 100, 1),
            "component_breakdown": dict(self._component_tokens),
            "history_count": len(self._history),
        }

    def reset(self) -> None:
        """Reset per nuova query."""
        self.used_tokens = 0
        self._history = []
        self._component_tokens = {}


_context_tracker: Optional[ContextWindowTracker] = None


def get_context_tracker(model_context_window: int = 32768) -> ContextWindowTracker:
    """Ottiene il singleton del context tracker."""
    global _context_tracker
    if _context_tracker is None or _context_tracker.max_tokens != model_context_window:
        _context_tracker = ContextWindowTracker(model_context_window)
    return _context_tracker
