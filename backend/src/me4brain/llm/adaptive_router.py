"""Adaptive Model Router - SOTA 2026.

Routing intelligente dei modelli basato su:
- Complessità della query
- Risorse hardware disponibili
- Caratteristiche del modello (context window, speed, capabilities)
- Costo/efficienza

Seleziona automaticamente:
- Modello locale per query semplici (< 5 tool call)
- Cloud per query complesse (> 10 tool call) o sotto pressione memoria
- Mix per query medie (locale per routing, cloud per synthesis)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

import structlog

from me4brain.llm.model_profiles import (
    ModelProfile,
    ModelProvider,
    get_best_model_for_task,
    get_model_profile,
    get_context_window_for_model,
)
from me4brain.core.monitoring.resource_monitor import (
    HardwareResourceMonitor,
    get_resource_monitor,
)

if TYPE_CHECKING:
    from me4brain.llm.base import LLMProvider

logger = structlog.get_logger(__name__)


class QueryComplexity(str, Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class ComponentType(str, Enum):
    ROUTING = "routing"
    TOOL_SELECTION = "tool_selection"
    OBSERVATION = "observation"
    SYNTHESIS = "synthesis"
    INTENT_ANALYSIS = "intent_analysis"
    CONTEXT_REWRITE = "context_rewrite"


@dataclass
class RoutingDecision:
    """Decisione di routing per una richiesta."""

    provider: ModelProvider
    model_id: str
    reason: str
    estimated_tokens: int
    fallback_model: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingStats:
    """Statistiche di routing della sessione."""

    total_requests: int = 0
    local_requests: int = 0
    cloud_requests: int = 0
    fallbacks_triggered: int = 0
    tokens_saved_by_local: int = 0
    estimated_cost_saved_usd: float = 0.0


class AdaptiveModelRouter:
    """Routing intelligente dei modelli basato su risorse e complessità.

    SOTA 2026: Seleziona automaticamente il modello ottimale basandosi su:
    - Complessità query (numero tool, lunghezza, dominio)
    - Stato risorse hardware (RAM, swap, VRAM)
    - Profilo modello (speed, context window, capabilities)
    - Costo stimato
    """

    SIMPLE_TOOL_THRESHOLD = 5
    COMPLEX_TOOL_THRESHOLD = 10
    SIMPLE_TOKEN_THRESHOLD = 2000
    COMPLEX_TOKEN_THRESHOLD = 8000

    def __init__(
        self,
        resource_monitor: Optional[HardwareResourceMonitor] = None,
        local_provider: Optional[LLMProvider] = None,
        cloud_provider: Optional[LLMProvider] = None,
        local_model: str = "qwen3.5-4b-mlx",
        cloud_model: str = "mistralai/mistral-large-3-675b-instruct-2512",
        prefer_local: bool = True,
    ):
        self._monitor = resource_monitor or get_resource_monitor()
        self._local_provider = local_provider
        self._cloud_provider = cloud_provider
        self._local_model = local_model
        self._cloud_model = cloud_model
        self._prefer_local = prefer_local
        self._stats = RoutingStats()
        self._cooldown_until: float = 0
        self._consecutive_local_failures: int = 0

    def estimate_query_complexity(
        self,
        query: str,
        tools_count: int = 0,
        sub_queries_count: int = 0,
        domains: Optional[list[str]] = None,
    ) -> QueryComplexity:
        """Stima la complessità di una query.

        Fattori considerati:
        - Numero di tool richiesti
        - Numero di sub-query
        - Lunghezza della query
        - Numero di domini coinvolti
        """
        query_tokens = len(query) // 4

        complexity_score = 0

        if tools_count > self.COMPLEX_TOOL_THRESHOLD:
            complexity_score += 3
        elif tools_count > self.SIMPLE_TOOL_THRESHOLD:
            complexity_score += 1

        if sub_queries_count > 5:
            complexity_score += 2
        elif sub_queries_count > 2:
            complexity_score += 1

        if query_tokens > self.COMPLEX_TOKEN_THRESHOLD:
            complexity_score += 2
        elif query_tokens > self.SIMPLE_TOKEN_THRESHOLD:
            complexity_score += 1

        if domains and len(domains) > 2:
            complexity_score += 1

        if complexity_score >= 4:
            return QueryComplexity.COMPLEX
        elif complexity_score >= 2:
            return QueryComplexity.MODERATE
        else:
            return QueryComplexity.SIMPLE

    async def select_provider(
        self,
        query: str,
        component: ComponentType,
        tools_count: int = 0,
        sub_queries_count: int = 0,
        estimated_tokens: int = 0,
    ) -> RoutingDecision:
        """Seleziona provider e modello ottimale.

        Args:
            query: Query dell'utente
            component: Componente che farà la chiamata (routing, synthesis, etc.)
            tools_count: Numero di tool coinvolti
            sub_queries_count: Numero di sub-query
            estimated_tokens: Token stimati per la richiesta

        Returns:
            RoutingDecision con provider, modello e motivazione
        """
        stats = await self._monitor.get_system_stats()
        complexity = self.estimate_query_complexity(query, tools_count, sub_queries_count)

        if self._should_skip_local(stats):
            return self._make_cloud_decision(
                component, estimated_tokens, reason="Resource pressure detected"
            )

        if not self._prefer_local:
            return self._make_cloud_decision(
                component, estimated_tokens, reason="Local preference disabled"
            )

        if complexity == QueryComplexity.SIMPLE:
            return self._make_local_decision(
                component, estimated_tokens, reason="Simple query, local model sufficient"
            )

        if complexity == QueryComplexity.COMPLEX:
            if component in (ComponentType.SYNTHESIS, ComponentType.OBSERVATION):
                return self._make_cloud_decision(
                    component, estimated_tokens, reason="Complex query, cloud for heavy component"
                )
            else:
                return self._make_local_decision(
                    component,
                    estimated_tokens,
                    reason="Complex query, local for lightweight component",
                    fallback_model=self._cloud_model,
                )

        if component == ComponentType.SYNTHESIS:
            return self._make_local_decision(
                component,
                estimated_tokens,
                reason="Moderate query, local synthesis",
                fallback_model=self._cloud_model,
            )

        return self._make_local_decision(
            component, estimated_tokens, reason="Moderate query, local model"
        )

    def _should_skip_local(self, stats: Any) -> bool:
        """Verifica se il locale dovrebbe essere saltato."""
        if self._monitor.should_use_cloud_fallback(stats):
            return True

        if time.time() < self._cooldown_until:
            return True

        if self._consecutive_local_failures >= 3:
            return True

        local_profile = get_model_profile(self._local_model)
        if local_profile and local_profile.vram_required_gb:
            available_gb = stats.ram_available_gb
            if available_gb < local_profile.vram_required_gb * 1.5:
                return True

        return False

    def _make_local_decision(
        self,
        component: ComponentType,
        estimated_tokens: int,
        reason: str,
        fallback_model: Optional[str] = None,
    ) -> RoutingDecision:
        """Crea decisione per modello locale."""
        self._stats.total_requests += 1
        self._stats.local_requests += 1

        if estimated_tokens > 0:
            cloud_cost = self._estimate_cloud_cost(estimated_tokens)
            self._stats.estimated_cost_saved_usd += cloud_cost
            self._stats.tokens_saved_by_local += estimated_tokens

        return RoutingDecision(
            provider=ModelProvider.LOCAL_MLX,
            model_id=self._local_model,
            reason=reason,
            estimated_tokens=estimated_tokens,
            fallback_model=fallback_model or self._cloud_model,
            metadata={"component": component.value},
        )

    def _make_cloud_decision(
        self,
        component: ComponentType,
        estimated_tokens: int,
        reason: str,
    ) -> RoutingDecision:
        """Crea decisione per modello cloud."""
        self._stats.total_requests += 1
        self._stats.cloud_requests += 1

        return RoutingDecision(
            provider=ModelProvider.CLOUD_NANOGPT,
            model_id=self._cloud_model,
            reason=reason,
            estimated_tokens=estimated_tokens,
            metadata={"component": component.value},
        )

    def _estimate_cloud_cost(self, tokens: int) -> float:
        """Stima costo cloud per un numero di token."""
        cloud_profile = get_model_profile(self._cloud_model)
        if cloud_profile:
            return (tokens / 1000) * cloud_profile.cost_per_1k_tokens
        return 0.0

    def record_local_failure(self) -> None:
        """Registra un fallimento del modello locale."""
        self._consecutive_local_failures += 1
        self._stats.fallbacks_triggered += 1

        if self._consecutive_local_failures >= 3:
            self._cooldown_until = time.time() + 60
            logger.warning(
                "local_model_cooldown",
                failures=self._consecutive_local_failures,
                cooldown_seconds=60,
            )

    def record_local_success(self) -> None:
        """Registra un successo del modello locale."""
        self._consecutive_local_failures = 0
        self._cooldown_until = 0

    def get_stats(self) -> RoutingStats:
        """Statistiche di routing della sessione."""
        return self._stats

    def get_context_budget(
        self,
        model_id: str,
        component: ComponentType,
        step: int = 1,
        total_steps: int = 1,
    ) -> int:
        """Calcola il budget di contesto per una chiamata.

        SOTA 2026: Token Budget Dinamico (Context Engineering, Comet 2026)
        Budget calcolato come: context_window × 0.85 - system_prompt_tokens - output_reserve
        """
        context_window = get_context_window_for_model(model_id)

        usable_ratio = 0.85
        output_reserve = 4096
        system_prompt_reserve = 2000

        usable_budget = int(context_window * usable_ratio)
        available = usable_budget - output_reserve - system_prompt_reserve

        if total_steps > 1:
            step_position = step / total_steps
            if step_position < 0.2:
                weight = 1.3
            elif step_position > 0.8:
                weight = 1.2
            else:
                weight = 1.0

            base_per_step = available / total_steps
            return int(base_per_step * weight)

        return available

    def reset_stats(self) -> None:
        """Reset statistiche per nuova sessione."""
        self._stats = RoutingStats()
        self._consecutive_local_failures = 0
        self._cooldown_until = 0


_adaptive_router: Optional[AdaptiveModelRouter] = None


def get_adaptive_router(
    local_model: str = "qwen3.5-4b-mlx",
    cloud_model: str = "mistralai/mistral-large-3-675b-instruct-2512",
) -> AdaptiveModelRouter:
    """Ottiene il singleton dell'adaptive router."""
    global _adaptive_router
    if _adaptive_router is None:
        _adaptive_router = AdaptiveModelRouter(
            local_model=local_model,
            cloud_model=cloud_model,
        )
    return _adaptive_router
