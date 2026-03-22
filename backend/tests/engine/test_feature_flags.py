"""Tests for feature flag management and gradual rollout."""

import os
import pytest
from unittest.mock import patch

from me4brain.engine.feature_flags import (
    FeatureFlagManager,
    RolloutPhase,
    RolloutMetrics,
    get_feature_flag_manager,
    reset_feature_flag_manager,
)


def test_local_only_flag_defaults():
    """LLM local-only flags must default to safe local values."""
    from me4brain.llm.config import get_llm_config

    config = get_llm_config()
    assert config.llm_local_only is True
    assert config.llm_allow_cloud_fallback is False


class TestRolloutPhase:
    """Test RolloutPhase enum."""

    def test_rollout_phases(self):
        """Test all rollout phases."""
        assert RolloutPhase.DISABLED.value == "disabled"
        assert RolloutPhase.CANARY.value == "canary"
        assert RolloutPhase.BETA.value == "beta"
        assert RolloutPhase.PRODUCTION.value == "production"


class TestRolloutMetrics:
    """Test RolloutMetrics dataclass."""

    def test_metrics_creation(self):
        """Test creating metrics."""
        metrics = RolloutMetrics(
            phase=RolloutPhase.CANARY,
            traffic_percentage=10,
            queries_processed=1000,
            successful_queries=990,
            failed_queries=10,
            avg_latency_ms=125.5,
            error_rate=0.01,
            accuracy=0.95,
            cache_hit_rate=0.40,
        )

        assert metrics.phase == RolloutPhase.CANARY
        assert metrics.traffic_percentage == 10
        assert metrics.queries_processed == 1000
        assert metrics.error_rate == 0.01

    def test_metrics_to_dict(self):
        """Test converting metrics to dict."""
        metrics = RolloutMetrics(
            phase=RolloutPhase.BETA,
            traffic_percentage=50,
            queries_processed=5000,
            successful_queries=4950,
            failed_queries=50,
            avg_latency_ms=130.0,
            error_rate=0.01,
            accuracy=0.96,
            cache_hit_rate=0.45,
        )

        metrics_dict = metrics.to_dict()
        assert metrics_dict["phase"] == "beta"
        assert metrics_dict["traffic_percentage"] == 50
        assert metrics_dict["queries_processed"] == 5000


class TestFeatureFlagManager:
    """Test FeatureFlagManager."""

    def setup_method(self):
        """Reset feature flag manager before each test."""
        reset_feature_flag_manager()

    def test_initial_phase_disabled(self):
        """Test initial phase is disabled."""
        with patch.dict(os.environ, {}, clear=True):
            manager = FeatureFlagManager()
            assert manager.get_phase() == RolloutPhase.DISABLED
            assert manager.get_traffic_percentage() == 0

    def test_set_phase(self):
        """Test setting rollout phase."""
        manager = FeatureFlagManager()

        manager.set_phase(RolloutPhase.CANARY)
        assert manager.get_phase() == RolloutPhase.CANARY
        assert manager.get_traffic_percentage() == 10

        manager.set_phase(RolloutPhase.BETA)
        assert manager.get_phase() == RolloutPhase.BETA
        assert manager.get_traffic_percentage() == 50

        manager.set_phase(RolloutPhase.PRODUCTION)
        assert manager.get_phase() == RolloutPhase.PRODUCTION
        assert manager.get_traffic_percentage() == 100

    def test_set_traffic_percentage(self):
        """Test setting traffic percentage."""
        manager = FeatureFlagManager()

        manager.set_traffic_percentage(25)
        assert manager.get_traffic_percentage() == 25

        # Test clamping to 0-100
        manager.set_traffic_percentage(-10)
        assert manager.get_traffic_percentage() == 0

        manager.set_traffic_percentage(150)
        assert manager.get_traffic_percentage() == 100

    def test_should_use_unified_analyzer_disabled(self):
        """Test that disabled phase never uses unified analyzer."""
        manager = FeatureFlagManager()
        manager.set_phase(RolloutPhase.DISABLED)

        # Should always return False
        for _ in range(100):
            assert manager.should_use_unified_analyzer() is False
            assert manager.should_use_unified_analyzer("user123") is False

    def test_should_use_unified_analyzer_production(self):
        """Test that production phase always uses unified analyzer."""
        manager = FeatureFlagManager()
        manager.set_phase(RolloutPhase.PRODUCTION)

        # Should always return True
        for _ in range(100):
            assert manager.should_use_unified_analyzer() is True
            assert manager.should_use_unified_analyzer("user123") is True

    def test_should_use_unified_analyzer_canary(self):
        """Test canary phase traffic splitting."""
        manager = FeatureFlagManager()
        manager.set_phase(RolloutPhase.CANARY)  # 10% traffic

        # With user ID, should be consistent
        user_id = "user123"
        result1 = manager.should_use_unified_analyzer(user_id)
        result2 = manager.should_use_unified_analyzer(user_id)
        assert result1 == result2  # Consistent

        # Approximately 10% should get True
        count = sum(1 for i in range(1000) if manager.should_use_unified_analyzer(f"user{i}"))
        # Allow 5-15% range
        assert 50 < count < 150

    def test_should_use_unified_analyzer_beta(self):
        """Test beta phase traffic splitting."""
        manager = FeatureFlagManager()
        manager.set_phase(RolloutPhase.BETA)  # 50% traffic

        # Approximately 50% should get True
        count = sum(1 for i in range(1000) if manager.should_use_unified_analyzer(f"user{i}"))
        # Allow 40-60% range
        assert 400 < count < 600

    def test_record_metrics(self):
        """Test recording metrics."""
        manager = FeatureFlagManager()

        manager.record_metrics(
            phase=RolloutPhase.CANARY,
            queries_processed=1000,
            successful_queries=990,
            failed_queries=10,
            avg_latency_ms=125.5,
            accuracy=0.95,
            cache_hit_rate=0.40,
        )

        metrics = manager.get_metrics(RolloutPhase.CANARY)
        assert metrics is not None
        assert metrics.queries_processed == 1000
        assert metrics.error_rate == 0.01
        assert metrics.accuracy == 0.95

    def test_get_metrics_current_phase(self):
        """Test getting metrics for current phase."""
        manager = FeatureFlagManager()
        manager.set_phase(RolloutPhase.BETA)

        manager.record_metrics(
            phase=RolloutPhase.BETA,
            queries_processed=5000,
            successful_queries=4950,
            failed_queries=50,
            avg_latency_ms=130.0,
            accuracy=0.96,
            cache_hit_rate=0.45,
        )

        # Get metrics for current phase
        metrics = manager.get_metrics()
        assert metrics is not None
        assert metrics.phase == RolloutPhase.BETA

    def test_get_all_metrics(self):
        """Test getting all metrics."""
        manager = FeatureFlagManager()

        # Record metrics for multiple phases
        for phase in [RolloutPhase.CANARY, RolloutPhase.BETA, RolloutPhase.PRODUCTION]:
            manager.record_metrics(
                phase=phase,
                queries_processed=1000,
                successful_queries=990,
                failed_queries=10,
                avg_latency_ms=125.0,
                accuracy=0.95,
                cache_hit_rate=0.40,
            )

        all_metrics = manager.get_all_metrics()
        assert len(all_metrics) == 3
        assert RolloutPhase.CANARY in all_metrics
        assert RolloutPhase.BETA in all_metrics
        assert RolloutPhase.PRODUCTION in all_metrics

    def test_compare_phases(self):
        """Test comparing metrics between phases."""
        manager = FeatureFlagManager()

        # Record metrics for two phases
        manager.record_metrics(
            phase=RolloutPhase.CANARY,
            queries_processed=1000,
            successful_queries=990,
            failed_queries=10,
            avg_latency_ms=125.0,
            accuracy=0.95,
            cache_hit_rate=0.40,
        )

        manager.record_metrics(
            phase=RolloutPhase.BETA,
            queries_processed=5000,
            successful_queries=4950,
            failed_queries=50,
            avg_latency_ms=130.0,
            accuracy=0.96,
            cache_hit_rate=0.45,
        )

        comparison = manager.compare_phases(RolloutPhase.CANARY, RolloutPhase.BETA)
        assert comparison["latency_diff_ms"] == 5.0  # 130 - 125
        assert abs(comparison["accuracy_diff"] - 0.01) < 0.0001  # 0.96 - 0.95
        assert abs(comparison["cache_hit_rate_diff"] - 0.05) < 0.0001  # 0.45 - 0.40

    def test_get_traffic_percentage_for_phase(self):
        """Test getting traffic percentage for each phase."""
        assert FeatureFlagManager._get_traffic_percentage_for_phase(RolloutPhase.DISABLED) == 0
        assert FeatureFlagManager._get_traffic_percentage_for_phase(RolloutPhase.CANARY) == 10
        assert FeatureFlagManager._get_traffic_percentage_for_phase(RolloutPhase.BETA) == 50
        assert FeatureFlagManager._get_traffic_percentage_for_phase(RolloutPhase.PRODUCTION) == 100


class TestGlobalFeatureFlagManager:
    """Test global feature flag manager singleton."""

    def setup_method(self):
        """Reset feature flag manager before each test."""
        reset_feature_flag_manager()

    def test_get_feature_flag_manager_singleton(self):
        """Test that get_feature_flag_manager returns singleton."""
        manager1 = get_feature_flag_manager()
        manager2 = get_feature_flag_manager()
        assert manager1 is manager2

    def test_reset_feature_flag_manager(self):
        """Test resetting feature flag manager."""
        manager1 = get_feature_flag_manager()
        manager1.set_phase(RolloutPhase.PRODUCTION)

        reset_feature_flag_manager()

        manager2 = get_feature_flag_manager()
        assert manager2 is not manager1
        assert manager2.get_phase() == RolloutPhase.DISABLED
