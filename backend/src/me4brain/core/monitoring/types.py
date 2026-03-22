"""Monitoring Types - Modelli Pydantic per observability."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class MetricType(str, Enum):
    """Tipi di metriche Prometheus."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class HealthStatus(str, Enum):
    """Stati di salute componenti."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AlertSeverity(str, Enum):
    """Livelli severità alert."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# --- Metrics ---


class MetricDefinition(BaseModel):
    """Definizione metrica."""

    name: str
    metric_type: MetricType
    description: str
    labels: list[str] = Field(default_factory=list)
    buckets: Optional[list[float]] = None  # Per histogram


class MetricValue(BaseModel):
    """Valore metrica osservato."""

    name: str
    value: float
    labels: dict[str, str] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


# --- Health ---


class ComponentHealth(BaseModel):
    """Stato salute singolo componente."""

    name: str
    status: HealthStatus
    latency_ms: Optional[float] = None
    message: Optional[str] = None
    last_check: datetime = Field(default_factory=datetime.now)


class HealthReport(BaseModel):
    """Report salute aggregato."""

    status: HealthStatus
    components: list[ComponentHealth] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_components(cls, components: list[ComponentHealth]) -> "HealthReport":
        """Calcola status aggregato."""
        if not components:
            return cls(status=HealthStatus.UNKNOWN)

        statuses = [c.status for c in components]

        if HealthStatus.UNHEALTHY in statuses:
            agg_status = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            agg_status = HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            agg_status = HealthStatus.HEALTHY
        else:
            agg_status = HealthStatus.UNKNOWN

        return cls(status=agg_status, components=components)


# --- Alerts ---


class AlertRule(BaseModel):
    """Regola di alerting."""

    name: str
    metric_name: str
    condition: Literal["gt", "lt", "eq", "gte", "lte"]
    threshold: float
    duration_seconds: int = 60  # Tempo prima di triggerare
    severity: AlertSeverity = AlertSeverity.WARNING
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class Alert(BaseModel):
    """Istanza di alert triggered."""

    id: str
    rule_name: str
    severity: AlertSeverity
    status: Literal["firing", "resolved"] = "firing"
    message: str
    value: float
    threshold: float

    # Timing
    started_at: datetime = Field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None

    # Context
    labels: dict[str, str] = Field(default_factory=dict)


# --- Dashboard ---


class PanelConfig(BaseModel):
    """Configurazione pannello dashboard."""

    title: str
    metric_query: str  # PromQL
    panel_type: Literal["graph", "stat", "gauge", "table"] = "graph"
    width: int = 12
    height: int = 8


class DashboardConfig(BaseModel):
    """Configurazione dashboard."""

    name: str
    refresh_seconds: int = 30
    panels: list[PanelConfig] = Field(default_factory=list)


# --- LLM Metrics ---


class LLMUsage(BaseModel):
    """Usage LLM per tracking."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    cost_dollars: float = 0.0

    @classmethod
    def from_response(
        cls,
        model: str,
        usage: dict,
        latency_ms: float,
    ) -> "LLMUsage":
        """Crea da response LLM."""
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)

        # Cost estimation (approximate)
        cost = cls._estimate_cost(model, prompt, completion)

        return cls(
            model=model,
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
            latency_ms=latency_ms,
            cost_dollars=cost,
        )

    @staticmethod
    def _estimate_cost(model: str, prompt: int, completion: int) -> float:
        """Stima costo ($/1M tokens)."""
        rates = {
            "gpt-4o": (2.50, 10.0),
            "gpt-4o-mini": (0.15, 0.60),
            "claude-3-5-sonnet": (3.0, 15.0),
            "claude-3-haiku": (0.25, 1.25),
            "mistral-large": (2.0, 6.0),
        }

        input_rate, output_rate = rates.get(model, (1.0, 3.0))
        cost = (prompt * input_rate + completion * output_rate) / 1_000_000

        return round(cost, 6)


# --- API Models ---


class StatsResponse(BaseModel):
    """Response statistiche interne."""

    uptime_seconds: float
    requests_total: int
    requests_per_minute: float
    llm_tokens_total: int
    llm_cost_total: float
    active_sessions: int
    memory_usage_mb: float


class AlertsResponse(BaseModel):
    """Response alerts attivi."""

    total: int
    firing: list[Alert] = Field(default_factory=list)
    resolved_recent: list[Alert] = Field(default_factory=list)
