"""Feature flag management for gradual rollout of UnifiedIntentAnalyzer.

This module provides traffic splitting and feature flag management for
deploying UnifiedIntentAnalyzer with gradual rollout:
- 0% traffic (disabled)
- 10% traffic (canary)
- 50% traffic (beta)
- 100% traffic (production)
"""

import hashlib
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


class RolloutPhase(str, Enum):
    """Rollout phases for UnifiedIntentAnalyzer."""

    DISABLED = "disabled"  # 0% traffic
    CANARY = "canary"  # 10% traffic
    BETA = "beta"  # 50% traffic
    PRODUCTION = "production"  # 100% traffic


@dataclass
class RolloutMetrics:
    """Metrics for a rollout phase."""

    phase: RolloutPhase
    traffic_percentage: int
    queries_processed: int
    successful_queries: int
    failed_queries: int
    avg_latency_ms: float
    error_rate: float
    accuracy: float
    cache_hit_rate: float

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "phase": self.phase.value,
            "traffic_percentage": self.traffic_percentage,
            "queries_processed": self.queries_processed,
            "successful_queries": self.successful_queries,
            "failed_queries": self.failed_queries,
            "avg_latency_ms": self.avg_latency_ms,
            "error_rate": self.error_rate,
            "accuracy": self.accuracy,
            "cache_hit_rate": self.cache_hit_rate,
        }


class FeatureFlagManager:
    """Manages feature flags and traffic splitting for gradual rollout."""

    def __init__(self):
        """Initialize feature flag manager."""
        self._phase = self._get_initial_phase()
        self._traffic_percentage = self._get_traffic_percentage()
        self._metrics: dict[RolloutPhase, RolloutMetrics] = {}

    def _get_initial_phase(self) -> RolloutPhase:
        """Get initial rollout phase from environment."""
        phase_str = os.getenv("UNIFIED_INTENT_ROLLOUT_PHASE", "disabled").lower()
        try:
            return RolloutPhase(phase_str)
        except ValueError:
            logger.warning(
                "invalid_rollout_phase",
                phase=phase_str,
                default="disabled",
            )
            return RolloutPhase.DISABLED

    def _get_traffic_percentage(self) -> int:
        """Get traffic percentage from environment."""
        try:
            percentage = int(os.getenv("UNIFIED_INTENT_TRAFFIC_PERCENTAGE", "0"))
            return max(0, min(100, percentage))  # Clamp to 0-100
        except ValueError:
            logger.warning(
                "invalid_traffic_percentage",
                default=0,
            )
            return 0

    def set_phase(self, phase: RolloutPhase) -> None:
        """Set rollout phase.

        Args:
            phase: New rollout phase
        """
        old_phase = self._phase
        self._phase = phase
        self._traffic_percentage = self._get_traffic_percentage_for_phase(phase)

        logger.info(
            "rollout_phase_changed",
            old_phase=old_phase.value,
            new_phase=phase.value,
            traffic_percentage=self._traffic_percentage,
        )

    def set_traffic_percentage(self, percentage: int) -> None:
        """Set traffic percentage.

        Args:
            percentage: Traffic percentage (0-100)
        """
        percentage = max(0, min(100, percentage))
        old_percentage = self._traffic_percentage
        self._traffic_percentage = percentage

        logger.info(
            "traffic_percentage_changed",
            old_percentage=old_percentage,
            new_percentage=percentage,
        )

    def should_use_unified_analyzer(self, user_id: Optional[str] = None) -> bool:
        """Determine if unified analyzer should be used for this request.

        Uses consistent hashing to ensure same user always gets same treatment.

        Args:
            user_id: Optional user ID for consistent hashing

        Returns:
            True if unified analyzer should be used, False otherwise
        """
        if self._phase == RolloutPhase.DISABLED:
            return False

        if self._phase == RolloutPhase.PRODUCTION:
            return True

        # For canary and beta, use traffic percentage with consistent hashing
        if user_id:
            # Hash user ID to get consistent bucket
            hash_value = int(
                hashlib.md5(user_id.encode()).hexdigest(), 16
            ) % 100
            return hash_value < self._traffic_percentage
        else:
            # No user ID, use random bucket
            import random

            return random.randint(0, 99) < self._traffic_percentage

    def get_phase(self) -> RolloutPhase:
        """Get current rollout phase.

        Returns:
            Current rollout phase
        """
        return self._phase

    def get_traffic_percentage(self) -> int:
        """Get current traffic percentage.

        Returns:
            Traffic percentage (0-100)
        """
        return self._traffic_percentage

    def record_metrics(
        self,
        phase: RolloutPhase,
        queries_processed: int,
        successful_queries: int,
        failed_queries: int,
        avg_latency_ms: float,
        accuracy: float,
        cache_hit_rate: float,
    ) -> None:
        """Record metrics for a rollout phase.

        Args:
            phase: Rollout phase
            queries_processed: Total queries processed
            successful_queries: Successful queries
            failed_queries: Failed queries
            avg_latency_ms: Average latency in milliseconds
            accuracy: Classification accuracy (0.0-1.0)
            cache_hit_rate: Cache hit rate (0.0-1.0)
        """
        error_rate = (
            failed_queries / queries_processed if queries_processed > 0 else 0.0
        )

        metrics = RolloutMetrics(
            phase=phase,
            traffic_percentage=self._get_traffic_percentage_for_phase(phase),
            queries_processed=queries_processed,
            successful_queries=successful_queries,
            failed_queries=failed_queries,
            avg_latency_ms=avg_latency_ms,
            error_rate=error_rate,
            accuracy=accuracy,
            cache_hit_rate=cache_hit_rate,
        )

        self._metrics[phase] = metrics

        logger.info(
            "rollout_metrics_recorded",
            phase=phase.value,
            metrics=metrics.to_dict(),
        )

    def get_metrics(self, phase: Optional[RolloutPhase] = None) -> Optional[RolloutMetrics]:
        """Get metrics for a rollout phase.

        Args:
            phase: Rollout phase (None for current phase)

        Returns:
            RolloutMetrics or None if not available
        """
        if phase is None:
            phase = self._phase

        return self._metrics.get(phase)

    def get_all_metrics(self) -> dict[RolloutPhase, RolloutMetrics]:
        """Get metrics for all phases.

        Returns:
            Dictionary of phase -> metrics
        """
        return self._metrics.copy()

    def compare_phases(
        self,
        phase1: RolloutPhase,
        phase2: RolloutPhase,
    ) -> dict[str, float]:
        """Compare metrics between two phases.

        Args:
            phase1: First phase
            phase2: Second phase

        Returns:
            Dictionary of metric differences
        """
        metrics1 = self._metrics.get(phase1)
        metrics2 = self._metrics.get(phase2)

        if not metrics1 or not metrics2:
            return {}

        return {
            "latency_diff_ms": metrics2.avg_latency_ms - metrics1.avg_latency_ms,
            "accuracy_diff": metrics2.accuracy - metrics1.accuracy,
            "error_rate_diff": metrics2.error_rate - metrics1.error_rate,
            "cache_hit_rate_diff": metrics2.cache_hit_rate - metrics1.cache_hit_rate,
        }

    @staticmethod
    def _get_traffic_percentage_for_phase(phase: RolloutPhase) -> int:
        """Get traffic percentage for a phase.

        Args:
            phase: Rollout phase

        Returns:
            Traffic percentage
        """
        return {
            RolloutPhase.DISABLED: 0,
            RolloutPhase.CANARY: 10,
            RolloutPhase.BETA: 50,
            RolloutPhase.PRODUCTION: 100,
        }[phase]


# Global feature flag manager instance
_feature_flag_manager: Optional[FeatureFlagManager] = None


def get_feature_flag_manager() -> FeatureFlagManager:
    """Get global feature flag manager instance.

    Returns:
        FeatureFlagManager singleton
    """
    global _feature_flag_manager
    if _feature_flag_manager is None:
        _feature_flag_manager = FeatureFlagManager()
    return _feature_flag_manager


def reset_feature_flag_manager() -> None:
    """Reset feature flag manager (for testing)."""
    global _feature_flag_manager
    _feature_flag_manager = None
