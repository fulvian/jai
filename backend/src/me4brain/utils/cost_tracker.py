"""Cost Monitoring Module.

Traccia utilizzo token LLM e costi API per billing e analytics.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TokenUsage:
    """Usage di token per una singola chiamata."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = "unknown"
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CostRecord:
    """Record di costo per una operazione."""

    operation: str
    tenant_id: str
    user_id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


# Token pricing per model (USD per 1K tokens) - aggiornare periodicamente
MODEL_PRICING = {
    # OpenAI
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    # Anthropic
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-opus": {"input": 0.015, "output": 0.075},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    # Google
    "gemini-2.0-flash": {"input": 0.0001, "output": 0.0004},
    "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
    # Default
    "default": {"input": 0.001, "output": 0.002},
}


class CostTracker:
    """Tracker centralizzato per costi."""

    _instance: "CostTracker | None" = None
    _records: list[CostRecord]
    _aggregates: dict[str, dict[str, float]]

    def __new__(cls) -> "CostTracker":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._records = []
            cls._instance._aggregates = {}
        return cls._instance

    def record_llm_usage(
        self,
        tenant_id: str,
        user_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        operation: str = "query",
        metadata: dict[str, Any] | None = None,
    ) -> CostRecord:
        """Registra utilizzo LLM."""
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = self._calculate_cost(model, prompt_tokens, completion_tokens)

        record = CostRecord(
            operation=operation,
            tenant_id=tenant_id,
            user_id=user_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            metadata=metadata or {},
        )

        self._records.append(record)
        self._update_aggregates(record)

        logger.info(
            "llm_usage_recorded",
            tenant_id=tenant_id,
            model=model,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
        )

        return record

    def _calculate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Calcola costo in USD."""
        # Trova pricing per model
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            # Prova match parziale
            for key in MODEL_PRICING:
                if key in model.lower():
                    pricing = MODEL_PRICING[key]
                    break
            else:
                pricing = MODEL_PRICING["default"]

        input_cost = (prompt_tokens / 1000) * pricing["input"]
        output_cost = (completion_tokens / 1000) * pricing["output"]

        return round(input_cost + output_cost, 6)

    def _update_aggregates(self, record: CostRecord) -> None:
        """Aggiorna aggregati per tenant."""
        key = f"{record.tenant_id}:{record.timestamp.strftime('%Y-%m-%d')}"

        if key not in self._aggregates:
            self._aggregates[key] = {
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "call_count": 0,
            }

        self._aggregates[key]["total_tokens"] += record.total_tokens
        self._aggregates[key]["total_cost_usd"] += record.cost_usd
        self._aggregates[key]["call_count"] += 1

    def get_tenant_usage(
        self,
        tenant_id: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """Ottiene usage per un tenant."""
        filtered = [
            r
            for r in self._records
            if r.tenant_id == tenant_id
            and (start_date is None or r.timestamp >= start_date)
            and (end_date is None or r.timestamp <= end_date)
        ]

        if not filtered:
            return {
                "tenant_id": tenant_id,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "call_count": 0,
                "by_model": {},
            }

        by_model: dict[str, dict[str, Any]] = {}
        for r in filtered:
            if r.model not in by_model:
                by_model[r.model] = {"tokens": 0, "cost_usd": 0.0, "calls": 0}
            by_model[r.model]["tokens"] += r.total_tokens
            by_model[r.model]["cost_usd"] += r.cost_usd
            by_model[r.model]["calls"] += 1

        return {
            "tenant_id": tenant_id,
            "total_tokens": sum(r.total_tokens for r in filtered),
            "total_cost_usd": sum(r.cost_usd for r in filtered),
            "call_count": len(filtered),
            "by_model": by_model,
        }

    def get_daily_summary(self, date: datetime | None = None) -> dict[str, Any]:
        """Ottiene summary giornaliero."""
        target_date = (date or datetime.now(UTC)).strftime("%Y-%m-%d")

        daily_records = [
            r for r in self._records if r.timestamp.strftime("%Y-%m-%d") == target_date
        ]

        by_tenant: dict[str, dict[str, Any]] = {}
        for r in daily_records:
            if r.tenant_id not in by_tenant:
                by_tenant[r.tenant_id] = {"tokens": 0, "cost_usd": 0.0, "calls": 0}
            by_tenant[r.tenant_id]["tokens"] += r.total_tokens
            by_tenant[r.tenant_id]["cost_usd"] += r.cost_usd
            by_tenant[r.tenant_id]["calls"] += 1

        return {
            "date": target_date,
            "total_tokens": sum(r.total_tokens for r in daily_records),
            "total_cost_usd": sum(r.cost_usd for r in daily_records),
            "total_calls": len(daily_records),
            "by_tenant": by_tenant,
        }

    def export_records(
        self,
        tenant_id: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Esporta records per billing/analytics."""
        filtered = self._records
        if tenant_id:
            filtered = [r for r in filtered if r.tenant_id == tenant_id]

        return [
            {
                "operation": r.operation,
                "tenant_id": r.tenant_id,
                "user_id": r.user_id,
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in filtered[-limit:]
        ]


# Singleton instance
cost_tracker = CostTracker()


def track_llm_cost(
    tenant_id: str,
    user_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: float,
    operation: str = "query",
) -> CostRecord:
    """Helper function per tracking costi."""
    return cost_tracker.record_llm_usage(
        tenant_id=tenant_id,
        user_id=user_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        operation=operation,
    )
