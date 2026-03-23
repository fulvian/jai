"""Unit tests for Monitoring module (M8)."""

from __future__ import annotations

import pytest

from me4brain.core.monitoring.alerts import AlertManager
from me4brain.core.monitoring.health import HealthChecker
from me4brain.core.monitoring.metrics import MetricsCollector
from me4brain.core.monitoring.types import (
    Alert,
    AlertRule,
    AlertSeverity,
    ComponentHealth,
    HealthReport,
    HealthStatus,
    LLMUsage,
    MetricDefinition,
    MetricType,
    MetricValue,
)

# --- Types Tests ---


class TestMonitoringTypes:
    """Test per modelli Pydantic monitoring."""

    def test_metric_type_enum(self):
        """Test enum tipi metrica."""
        assert MetricType.COUNTER.value == "counter"
        assert MetricType.HISTOGRAM.value == "histogram"

    def test_health_status_enum(self):
        """Test enum stati salute."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"

    def test_alert_severity_enum(self):
        """Test enum severità."""
        assert AlertSeverity.CRITICAL.value == "critical"
        assert AlertSeverity.WARNING.value == "warning"

    def test_metric_definition_creation(self):
        """Test creazione definizione metrica."""
        metric = MetricDefinition(
            name="test_counter",
            metric_type=MetricType.COUNTER,
            description="Test counter",
            labels=["method", "status"],
        )
        assert metric.name == "test_counter"
        assert len(metric.labels) == 2

    def test_metric_value_creation(self):
        """Test creazione valore metrica."""
        value = MetricValue(
            name="test_metric",
            value=42.0,
            labels={"endpoint": "/test"},
        )
        assert value.value == 42.0
        assert value.labels["endpoint"] == "/test"

    def test_component_health_creation(self):
        """Test creazione salute componente."""
        health = ComponentHealth(
            name="redis",
            status=HealthStatus.HEALTHY,
            latency_ms=1.5,
        )
        assert health.name == "redis"
        assert health.status == HealthStatus.HEALTHY

    def test_health_report_from_components_all_healthy(self):
        """Test report aggregato - tutti healthy."""
        components = [
            ComponentHealth(name="redis", status=HealthStatus.HEALTHY),
            ComponentHealth(name="qdrant", status=HealthStatus.HEALTHY),
        ]
        report = HealthReport.from_components(components)
        assert report.status == HealthStatus.HEALTHY

    def test_health_report_from_components_one_unhealthy(self):
        """Test report aggregato - uno unhealthy."""
        components = [
            ComponentHealth(name="redis", status=HealthStatus.HEALTHY),
            ComponentHealth(name="qdrant", status=HealthStatus.UNHEALTHY),
        ]
        report = HealthReport.from_components(components)
        assert report.status == HealthStatus.UNHEALTHY

    def test_health_report_from_components_degraded(self):
        """Test report aggregato - degraded."""
        components = [
            ComponentHealth(name="redis", status=HealthStatus.HEALTHY),
            ComponentHealth(name="neo4j", status=HealthStatus.DEGRADED),
        ]
        report = HealthReport.from_components(components)
        assert report.status == HealthStatus.DEGRADED

    def test_alert_rule_creation(self):
        """Test creazione regola alert."""
        rule = AlertRule(
            name="high_latency",
            metric_name="latency_seconds",
            condition="gt",
            threshold=5.0,
            severity=AlertSeverity.WARNING,
        )
        assert rule.name == "high_latency"
        assert rule.condition == "gt"

    def test_alert_creation(self):
        """Test creazione alert."""
        alert = Alert(
            id="alert-123",
            rule_name="high_latency",
            severity=AlertSeverity.WARNING,
            message="Latency too high",
            value=10.0,
            threshold=5.0,
        )
        assert alert.status == "firing"
        assert alert.resolved_at is None

    def test_llm_usage_creation(self):
        """Test creazione LLM usage."""
        usage = LLMUsage(
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=500,
        )
        assert usage.total_tokens == 150

    def test_llm_usage_from_response(self):
        """Test creazione da response."""
        usage = LLMUsage.from_response(
            model="gpt-4o",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
            latency_ms=500,
        )
        assert usage.total_tokens == 150
        assert usage.cost_dollars > 0

    def test_llm_usage_cost_estimation(self):
        """Test stima costo."""
        cost = LLMUsage._estimate_cost("gpt-4o", 1000, 500)
        assert cost > 0


# --- MetricsCollector Tests ---


class TestMetricsCollector:
    """Test per MetricsCollector."""

    def test_collector_init(self):
        """Test inizializzazione."""
        collector = MetricsCollector(namespace="test")
        assert collector.namespace == "test"

    def test_record_request(self):
        """Test registrazione request."""
        collector = MetricsCollector(namespace="test_req")
        collector.record_request("GET", "/api/test", 200, 0.1)
        # No exception = success

    def test_record_llm_usage(self):
        """Test registrazione LLM usage."""
        import uuid

        collector = MetricsCollector(namespace=f"test_llm_{uuid.uuid4().hex[:6]}")
        usage = LLMUsage(
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_ms=500,
        )
        collector.record_llm_usage(usage)

    def test_record_agent_task(self):
        """Test registrazione task agente."""
        collector = MetricsCollector(namespace="test_agent")
        collector.record_agent_task("worker", "completed")

    def test_record_memory_op(self):
        """Test registrazione operazione memoria."""
        collector = MetricsCollector(namespace="test_mem")
        collector.record_memory_op("working", "read", 0.01)

    def test_record_browser_action(self):
        """Test registrazione azione browser."""
        collector = MetricsCollector(namespace="test_browser")
        collector.record_browser_action("click")

    def test_uptime(self):
        """Test uptime."""
        collector = MetricsCollector(namespace="test_uptime")
        uptime = collector.get_uptime()
        assert uptime >= 0

    def test_generate_metrics(self):
        """Test generazione output."""
        collector = MetricsCollector(namespace="test_gen")
        output = collector.generate_metrics()
        assert isinstance(output, bytes)
        assert b"test_gen_uptime_seconds" in output


# --- HealthChecker Tests ---


class TestHealthChecker:
    """Test per HealthChecker."""

    def test_checker_init(self):
        """Test inizializzazione."""
        checker = HealthChecker(timeout_seconds=2.0)
        assert checker.timeout == 2.0

    def test_register_check(self):
        """Test registrazione check custom."""
        checker = HealthChecker()

        async def custom_check():
            return ComponentHealth(name="custom", status=HealthStatus.HEALTHY)

        checker.register("custom", custom_check)
        assert "custom" in checker._checks

    @pytest.mark.asyncio
    async def test_check_component_not_registered(self):
        """Test check componente non registrato."""
        checker = HealthChecker()
        result = await checker.check_component("nonexistent")
        assert result.status == HealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_check_component_timeout(self):
        """Test timeout check."""
        checker = HealthChecker(timeout_seconds=0.1)

        async def slow_check():
            import asyncio

            await asyncio.sleep(1)
            return ComponentHealth(name="slow", status=HealthStatus.HEALTHY)

        checker.register("slow", slow_check)
        result = await checker.check_component("slow")
        assert result.status == HealthStatus.UNHEALTHY
        assert "timed out" in result.message

    @pytest.mark.asyncio
    async def test_check_component_exception(self):
        """Test check con exception."""
        checker = HealthChecker()

        async def failing_check():
            raise Exception("Connection failed")

        checker.register("failing", failing_check)
        result = await checker.check_component("failing")
        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_check_all(self):
        """Test check tutti componenti."""
        checker = HealthChecker()

        # Override checks con mock
        async def mock_healthy():
            return ComponentHealth(name="mock", status=HealthStatus.HEALTHY)

        checker._checks = {"mock1": mock_healthy, "mock2": mock_healthy}

        report = await checker.check_all()
        assert report.status == HealthStatus.HEALTHY
        assert len(report.components) == 2


# --- AlertManager Tests ---


class TestAlertManager:
    """Test per AlertManager."""

    def test_manager_init(self):
        """Test inizializzazione."""
        manager = AlertManager()
        assert len(manager._rules) > 0  # Default rules

    def test_add_rule(self):
        """Test aggiunta regola."""
        manager = AlertManager()
        rule = AlertRule(
            name="test_rule",
            metric_name="test_metric",
            condition="gt",
            threshold=100,
        )
        manager.add_rule(rule)
        assert "test_rule" in manager._rules

    def test_remove_rule(self):
        """Test rimozione regola."""
        manager = AlertManager()
        rule = AlertRule(
            name="to_remove",
            metric_name="test",
            condition="gt",
            threshold=50,
        )
        manager.add_rule(rule)
        assert manager.remove_rule("to_remove") is True
        assert "to_remove" not in manager._rules

    def test_get_rules(self):
        """Test lista regole."""
        manager = AlertManager()
        rules = manager.get_rules()
        assert len(rules) > 0

    def test_evaluate_no_alert(self):
        """Test valutazione senza alert."""
        manager = AlertManager()
        manager._rules.clear()
        manager.add_rule(
            AlertRule(
                name="test",
                metric_name="test_metric",
                condition="gt",
                threshold=100,
            )
        )

        result = manager.evaluate("test_metric", 50)  # Under threshold
        assert result is None

    def test_evaluate_trigger_alert(self):
        """Test valutazione con trigger."""
        manager = AlertManager()
        manager._rules.clear()
        manager._notifiers.clear()  # No notifications
        manager.add_rule(
            AlertRule(
                name="high_test",
                metric_name="test_metric",
                condition="gt",
                threshold=100,
                severity=AlertSeverity.WARNING,
            )
        )

        result = manager.evaluate("test_metric", 150)  # Over threshold
        assert result is not None
        assert result.rule_name == "high_test"
        assert result.status == "firing"

    def test_evaluate_resolve_alert(self):
        """Test risoluzione alert."""
        manager = AlertManager()
        manager._rules.clear()
        manager._notifiers.clear()
        manager.add_rule(
            AlertRule(
                name="test_resolve",
                metric_name="test_metric",
                condition="gt",
                threshold=100,
            )
        )

        # Trigger
        manager.evaluate("test_metric", 150)
        assert "test_resolve" in manager._active_alerts

        # Resolve
        manager.evaluate("test_metric", 50)
        assert "test_resolve" not in manager._active_alerts
        assert len(manager._resolved_alerts) == 1

    def test_check_condition_gt(self):
        """Test condizione gt."""
        manager = AlertManager()
        assert manager._check_condition("gt", 10, 5) is True
        assert manager._check_condition("gt", 5, 10) is False

    def test_check_condition_lt(self):
        """Test condizione lt."""
        manager = AlertManager()
        assert manager._check_condition("lt", 5, 10) is True
        assert manager._check_condition("lt", 10, 5) is False

    def test_check_condition_eq(self):
        """Test condizione eq."""
        manager = AlertManager()
        assert manager._check_condition("eq", 10, 10) is True
        assert manager._check_condition("eq", 10, 5) is False

    def test_get_active_alerts(self):
        """Test lista alerts attivi."""
        manager = AlertManager()
        manager._rules.clear()
        manager._notifiers.clear()
        manager.add_rule(
            AlertRule(
                name="active_test",
                metric_name="metric",
                condition="gt",
                threshold=0,
            )
        )
        manager.evaluate("metric", 100)

        active = manager.get_active_alerts()
        assert len(active) == 1

    def test_clear_resolved(self):
        """Test pulizia resolved."""
        manager = AlertManager()
        manager._resolved_alerts = [
            Alert(
                id="1",
                rule_name="r1",
                severity=AlertSeverity.INFO,
                message="",
                value=0,
                threshold=0,
            ),
        ]
        count = manager.clear_resolved()
        assert count == 1
        assert len(manager._resolved_alerts) == 0
