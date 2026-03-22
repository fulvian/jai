"""Monitoring and observability for UnifiedIntentAnalyzer.

Provides metrics collection, structured logging, and observability hooks
for intent analysis operations.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class IntentMetrics:
    """Metrics for intent analysis operations."""

    total_queries: int = 0
    conversational_queries: int = 0
    tool_required_queries: int = 0
    failed_queries: int = 0
    
    # Latency metrics (milliseconds)
    total_latency_ms: float = 0.0
    min_latency_ms: float = float("inf")
    max_latency_ms: float = 0.0
    
    # Accuracy metrics
    correct_classifications: int = 0
    incorrect_classifications: int = 0
    
    # Confidence metrics
    total_confidence: float = 0.0
    low_confidence_queries: int = 0  # confidence < 0.7
    
    # Domain metrics
    domain_distribution: dict[str, int] = field(default_factory=dict)
    
    # Complexity metrics
    complexity_distribution: dict[str, int] = field(default_factory=dict)
    
    # Cache metrics
    cache_hits: int = 0
    cache_misses: int = 0
    
    # Error metrics
    llm_api_failures: int = 0
    json_parse_failures: int = 0
    invalid_domain_filters: int = 0

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        if self.total_queries == 0:
            return 0.0
        return self.total_latency_ms / self.total_queries

    @property
    def avg_confidence(self) -> float:
        """Calculate average confidence."""
        if self.total_queries == 0:
            return 0.0
        return self.total_confidence / self.total_queries

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total_cache_ops = self.cache_hits + self.cache_misses
        if total_cache_ops == 0:
            return 0.0
        return self.cache_hits / total_cache_ops

    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        if self.total_queries == 0:
            return 0.0
        return self.failed_queries / self.total_queries

    @property
    def accuracy(self) -> float:
        """Calculate accuracy (if labeled data available)."""
        total_labeled = self.correct_classifications + self.incorrect_classifications
        if total_labeled == 0:
            return 0.0
        return self.correct_classifications / total_labeled

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_queries": self.total_queries,
            "conversational_queries": self.conversational_queries,
            "tool_required_queries": self.tool_required_queries,
            "failed_queries": self.failed_queries,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "min_latency_ms": round(self.min_latency_ms, 2),
            "max_latency_ms": round(self.max_latency_ms, 2),
            "avg_confidence": round(self.avg_confidence, 3),
            "low_confidence_queries": self.low_confidence_queries,
            "cache_hit_rate": round(self.cache_hit_rate, 3),
            "error_rate": round(self.error_rate, 3),
            "accuracy": round(self.accuracy, 3),
            "domain_distribution": self.domain_distribution,
            "complexity_distribution": self.complexity_distribution,
            "llm_api_failures": self.llm_api_failures,
            "json_parse_failures": self.json_parse_failures,
            "invalid_domain_filters": self.invalid_domain_filters,
        }


class IntentMonitor:
    """Monitor for intent analysis operations."""

    def __init__(self):
        """Initialize the monitor."""
        self.metrics = IntentMetrics()
        self._start_time: dict[str, float] = {}

    def start_operation(self, operation_id: str) -> None:
        """Start timing an operation."""
        self._start_time[operation_id] = time.monotonic()

    def end_operation(
        self,
        operation_id: str,
        success: bool = True,
        **kwargs: Any,
    ) -> float:
        """End timing an operation and record metrics.

        Args:
            operation_id: Unique operation identifier
            success: Whether operation succeeded
            **kwargs: Additional metrics to record

        Returns:
            Latency in milliseconds
        """
        if operation_id not in self._start_time:
            return 0.0

        latency_ms = (time.monotonic() - self._start_time[operation_id]) * 1000
        del self._start_time[operation_id]

        # Update latency metrics
        self.metrics.total_latency_ms += latency_ms
        self.metrics.min_latency_ms = min(self.metrics.min_latency_ms, latency_ms)
        self.metrics.max_latency_ms = max(self.metrics.max_latency_ms, latency_ms)

        if not success:
            self.metrics.failed_queries += 1

        return latency_ms

    def record_analysis(
        self,
        intent: str,
        domains: list[str],
        complexity: str,
        confidence: float,
        latency_ms: float,
        cache_hit: bool = False,
    ) -> None:
        """Record an intent analysis operation.

        Args:
            intent: Intent type (conversational or tool_required)
            domains: List of identified domains
            complexity: Query complexity (simple, moderate, complex)
            confidence: Confidence score (0.0-1.0)
            latency_ms: Operation latency in milliseconds
            cache_hit: Whether result came from cache
        """
        self.metrics.total_queries += 1

        # Update intent distribution
        if intent == "conversational":
            self.metrics.conversational_queries += 1
        else:
            self.metrics.tool_required_queries += 1

        # Update latency metrics
        self.metrics.total_latency_ms += latency_ms
        self.metrics.min_latency_ms = min(self.metrics.min_latency_ms, latency_ms)
        self.metrics.max_latency_ms = max(self.metrics.max_latency_ms, latency_ms)

        # Update confidence metrics
        self.metrics.total_confidence += confidence
        if confidence < 0.7:
            self.metrics.low_confidence_queries += 1

        # Update domain distribution
        for domain in domains:
            self.metrics.domain_distribution[domain] = (
                self.metrics.domain_distribution.get(domain, 0) + 1
            )

        # Update complexity distribution
        self.metrics.complexity_distribution[complexity] = (
            self.metrics.complexity_distribution.get(complexity, 0) + 1
        )

        # Update cache metrics
        if cache_hit:
            self.metrics.cache_hits += 1
        else:
            self.metrics.cache_misses += 1

        # SOTA 2026: Log individual analysis for observability
        logger.info(
            "intent_analysis_result",
            intent=intent,
            domains=domains,
            complexity=complexity,
            confidence=confidence,
            latency_ms=round(latency_ms, 2),
            cache_hit=cache_hit,
        )

    def record_error(self, error_type: str) -> None:
        """Record an error.

        Args:
            error_type: Type of error (llm_api_failure, json_parse_failure, etc.)
        """
        self.metrics.failed_queries += 1

        if error_type == "llm_api_failure":
            self.metrics.llm_api_failures += 1
        elif error_type == "json_parse_failure":
            self.metrics.json_parse_failures += 1
        elif error_type == "invalid_domain_filter":
            self.metrics.invalid_domain_filters += 1

    def record_classification_feedback(
        self,
        predicted_intent: str,
        actual_intent: str,
    ) -> None:
        """Record classification feedback for accuracy tracking.

        Args:
            predicted_intent: Predicted intent
            actual_intent: Actual intent (from user feedback)
        """
        if predicted_intent == actual_intent:
            self.metrics.correct_classifications += 1
        else:
            self.metrics.incorrect_classifications += 1

    def get_metrics(self) -> IntentMetrics:
        """Get current metrics."""
        return self.metrics

    def reset_metrics(self) -> None:
        """Reset all metrics."""
        self.metrics = IntentMetrics()

    def log_metrics(self) -> None:
        """Log current metrics."""
        logger.info(
            "intent_metrics_snapshot",
            **self.metrics.to_dict(),
        )

    def check_alerts(self) -> list[dict[str, Any]]:
        """Check for alert conditions.

        Returns:
            List of alert dictionaries with alert_type and message
        """
        alerts = []

        # High error rate alert
        if self.metrics.error_rate > 0.05:
            alerts.append({
                "alert_type": "high_error_rate",
                "message": f"Error rate is {self.metrics.error_rate:.1%}",
                "severity": "warning",
            })

        # High latency alert
        if self.metrics.avg_latency_ms > 300:
            alerts.append({
                "alert_type": "high_latency",
                "message": f"Average latency is {self.metrics.avg_latency_ms:.0f}ms",
                "severity": "warning",
            })

        # Low confidence alert
        low_confidence_rate = (
            self.metrics.low_confidence_queries / self.metrics.total_queries
            if self.metrics.total_queries > 0
            else 0
        )
        if low_confidence_rate > 0.1:
            alerts.append({
                "alert_type": "low_confidence",
                "message": f"Low confidence rate is {low_confidence_rate:.1%}",
                "severity": "info",
            })

        # LLM API failures alert
        if self.metrics.llm_api_failures > 10:
            alerts.append({
                "alert_type": "llm_api_failures",
                "message": f"LLM API failures: {self.metrics.llm_api_failures}",
                "severity": "critical",
            })

        return alerts


# Global monitor instance
_monitor: IntentMonitor | None = None


def get_intent_monitor() -> IntentMonitor:
    """Get or create the global intent monitor."""
    global _monitor
    if _monitor is None:
        _monitor = IntentMonitor()
    return _monitor


def reset_intent_monitor() -> None:
    """Reset the global intent monitor."""
    global _monitor
    _monitor = None
