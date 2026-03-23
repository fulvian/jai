"""Metrics Collector - Prometheus metrics per Me4BrAIn."""

from __future__ import annotations

import time
from contextlib import contextmanager

import structlog
from prometheus_client import (
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from me4brain.core.monitoring.types import LLMUsage

logger = structlog.get_logger(__name__)


class MetricsCollector:
    """
    Collector Prometheus per Me4BrAIn.

    Metriche predefinite:
    - Requests: total, duration, errors
    - LLM: tokens, latency, cost
    - Agents: tasks, handoffs
    - Memory: operations per layer
    - Browser: sessions, actions
    """

    def __init__(self, namespace: str = "me4brain"):
        """
        Inizializza collector.

        Args:
            namespace: Prefisso metriche
        """
        self.namespace = namespace
        self._start_time = time.time()
        self._init_metrics()

    def _init_metrics(self) -> None:
        """Inizializza tutte le metriche."""

        # --- Request Metrics ---
        self.requests_total = Counter(
            f"{self.namespace}_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
        )

        self.request_duration = Histogram(
            f"{self.namespace}_request_duration_seconds",
            "Request duration in seconds",
            ["method", "endpoint"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )

        self.requests_in_progress = Gauge(
            f"{self.namespace}_requests_in_progress",
            "Requests currently being processed",
            ["method"],
        )

        # --- LLM Metrics ---
        self.llm_requests_total = Counter(
            f"{self.namespace}_llm_requests_total",
            "Total LLM API requests",
            ["model", "status"],
        )

        self.llm_tokens_total = Counter(
            f"{self.namespace}_llm_tokens_total",
            "Total tokens used",
            ["model", "token_type"],  # prompt, completion
        )

        self.llm_latency = Histogram(
            f"{self.namespace}_llm_latency_seconds",
            "LLM request latency",
            ["model"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
        )

        self.llm_cost_dollars = Counter(
            f"{self.namespace}_llm_cost_dollars_total",
            "Estimated LLM cost in USD",
            ["model"],
        )

        # --- Agent Metrics ---
        self.agent_tasks_total = Counter(
            f"{self.namespace}_agent_tasks_total",
            "Total agent tasks",
            ["agent_type", "status"],  # completed, failed, timeout
        )

        self.agent_handoffs_total = Counter(
            f"{self.namespace}_agent_handoffs_total",
            "Total agent handoffs",
            ["from_agent", "to_agent"],
        )

        self.agents_active = Gauge(
            f"{self.namespace}_agents_active",
            "Currently active agents",
            ["status"],
        )

        # --- Memory Metrics ---
        self.memory_operations_total = Counter(
            f"{self.namespace}_memory_operations_total",
            "Total memory operations",
            ["layer", "operation"],  # working/episodic/semantic, read/write/delete
        )

        self.memory_latency = Histogram(
            f"{self.namespace}_memory_latency_seconds",
            "Memory operation latency",
            ["layer"],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
        )

        # --- Browser Metrics ---
        self.browser_sessions_total = Counter(
            f"{self.namespace}_browser_sessions_total",
            "Total browser sessions created",
        )

        self.browser_sessions_active = Gauge(
            f"{self.namespace}_browser_sessions_active",
            "Currently active browser sessions",
        )

        self.browser_actions_total = Counter(
            f"{self.namespace}_browser_actions_total",
            "Total browser actions",
            ["action_type"],
        )

        # --- Webhook Metrics ---
        self.webhook_deliveries_total = Counter(
            f"{self.namespace}_webhook_deliveries_total",
            "Total webhook deliveries",
            ["status"],  # success, failed, retried
        )

        # --- System Metrics ---
        self.uptime_seconds = Gauge(
            f"{self.namespace}_uptime_seconds",
            "Process uptime in seconds",
        )

        logger.info("metrics_collector_initialized", namespace=self.namespace)

    # --- Request Methods ---

    @contextmanager
    def track_request(self, method: str, endpoint: str):
        """Context manager per tracking request."""
        self.requests_in_progress.labels(method=method).inc()
        start = time.time()

        try:
            yield
            status = "200"
        except Exception:
            status = "500"
            raise
        finally:
            duration = time.time() - start
            self.requests_in_progress.labels(method=method).dec()
            self.request_duration.labels(method=method, endpoint=endpoint).observe(duration)
            self.requests_total.labels(method=method, endpoint=endpoint, status_code=status).inc()

    def record_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
    ) -> None:
        """Registra request completata."""
        self.requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code),
        ).inc()
        self.request_duration.labels(method=method, endpoint=endpoint).observe(duration)

    # --- LLM Methods ---

    def record_llm_usage(self, usage: LLMUsage) -> None:
        """Registra usage LLM."""
        model = usage.model

        self.llm_requests_total.labels(model=model, status="success").inc()
        self.llm_tokens_total.labels(model=model, token_type="prompt").inc(usage.prompt_tokens)
        self.llm_tokens_total.labels(model=model, token_type="completion").inc(
            usage.completion_tokens
        )
        self.llm_latency.labels(model=model).observe(usage.latency_ms / 1000)
        self.llm_cost_dollars.labels(model=model).inc(usage.cost_dollars)

    def record_llm_error(self, model: str) -> None:
        """Registra errore LLM."""
        self.llm_requests_total.labels(model=model, status="error").inc()

    @contextmanager
    def track_llm_request(self, model: str):
        """Context manager per LLM request."""
        start = time.time()
        try:
            yield
        finally:
            latency = time.time() - start
            self.llm_latency.labels(model=model).observe(latency)

    # --- Agent Methods ---

    def record_agent_task(self, agent_type: str, status: str) -> None:
        """Registra task agente."""
        self.agent_tasks_total.labels(agent_type=agent_type, status=status).inc()

    def record_agent_handoff(self, from_agent: str, to_agent: str) -> None:
        """Registra handoff tra agenti."""
        self.agent_handoffs_total.labels(from_agent=from_agent, to_agent=to_agent).inc()

    def set_active_agents(self, status: str, count: int) -> None:
        """Imposta conteggio agenti attivi."""
        self.agents_active.labels(status=status).set(count)

    # --- Memory Methods ---

    def record_memory_op(self, layer: str, operation: str, duration: float = 0) -> None:
        """Registra operazione memoria."""
        self.memory_operations_total.labels(layer=layer, operation=operation).inc()
        if duration > 0:
            self.memory_latency.labels(layer=layer).observe(duration)

    # --- Browser Methods ---

    def record_browser_session(self) -> None:
        """Registra nuova sessione browser."""
        self.browser_sessions_total.inc()

    def set_active_browser_sessions(self, count: int) -> None:
        """Imposta sessioni browser attive."""
        self.browser_sessions_active.set(count)

    def record_browser_action(self, action_type: str) -> None:
        """Registra azione browser."""
        self.browser_actions_total.labels(action_type=action_type).inc()

    # --- Webhook Methods ---

    def record_webhook_delivery(self, status: str) -> None:
        """Registra delivery webhook."""
        self.webhook_deliveries_total.labels(status=status).inc()

    # --- System Methods ---

    def update_uptime(self) -> None:
        """Aggiorna uptime."""
        self.uptime_seconds.set(time.time() - self._start_time)

    def get_uptime(self) -> float:
        """Ottiene uptime in secondi."""
        return time.time() - self._start_time

    def generate_metrics(self) -> bytes:
        """Genera output Prometheus."""
        self.update_uptime()
        return generate_latest(REGISTRY)


# Singleton
_metrics_collector: MetricsCollector | None = None


def get_metrics() -> MetricsCollector:
    """Ottiene collector globale."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def initialize_metrics(namespace: str = "me4brain") -> MetricsCollector:
    """Inizializza metrics collector."""
    global _metrics_collector
    _metrics_collector = MetricsCollector(namespace=namespace)
    return _metrics_collector
