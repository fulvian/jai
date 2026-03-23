"""Alert Manager - Gestione regole e notifiche alert."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

import structlog

from me4brain.core.monitoring.types import Alert, AlertRule, AlertSeverity

logger = structlog.get_logger(__name__)


class AlertManager:
    """
    Manager per regole di alerting.

    Responsabilità:
    - Definizione regole (threshold-based)
    - Valutazione periodica
    - Notifiche (webhook, log)
    - Tracking stato alerts
    """

    def __init__(self):
        """Inizializza manager."""
        self._rules: dict[str, AlertRule] = {}
        self._active_alerts: dict[str, Alert] = {}
        self._resolved_alerts: list[Alert] = []
        self._notifiers: list[Callable[[Alert], None]] = []
        self._max_resolved = 100

        self._register_default_rules()

    def _register_default_rules(self) -> None:
        """Registra regole di default."""
        default_rules = [
            AlertRule(
                name="high_llm_latency",
                metric_name="me4brain_llm_latency_seconds",
                condition="gt",
                threshold=10.0,
                severity=AlertSeverity.WARNING,
                annotations={"description": "LLM latency > 10s"},
            ),
            AlertRule(
                name="high_error_rate",
                metric_name="me4brain_requests_total",
                condition="gt",
                threshold=0.1,  # 10% error rate
                severity=AlertSeverity.CRITICAL,
                annotations={"description": "Error rate > 10%"},
            ),
            AlertRule(
                name="low_memory",
                metric_name="me4brain_memory_usage_mb",
                condition="gt",
                threshold=1024,  # 1GB
                severity=AlertSeverity.WARNING,
                annotations={"description": "Memory usage > 1GB"},
            ),
        ]

        for rule in default_rules:
            self.add_rule(rule)

    def add_rule(self, rule: AlertRule) -> None:
        """
        Aggiunge regola.

        Args:
            rule: Regola da aggiungere
        """
        self._rules[rule.name] = rule
        logger.debug("alert_rule_added", rule=rule.name)

    def remove_rule(self, name: str) -> bool:
        """Rimuove regola."""
        if name in self._rules:
            del self._rules[name]
            return True
        return False

    def get_rules(self) -> list[AlertRule]:
        """Ottiene tutte le regole."""
        return list(self._rules.values())

    def add_notifier(self, notifier: Callable[[Alert], None]) -> None:
        """
        Aggiunge notifier.

        Args:
            notifier: Funzione chiamata su alert
        """
        self._notifiers.append(notifier)

    def evaluate(self, metric_name: str, value: float, labels: dict | None = None) -> Alert | None:
        """
        Valuta metriche contro regole.

        Args:
            metric_name: Nome metrica
            value: Valore corrente
            labels: Label opzionali

        Returns:
            Alert se threshold superata, None altrimenti
        """
        labels = labels or {}

        for rule in self._rules.values():
            if rule.metric_name != metric_name:
                continue

            if not self._check_condition(rule.condition, value, rule.threshold):
                # Se era firing, risolvi
                if rule.name in self._active_alerts:
                    self._resolve_alert(rule.name)
                continue

            # Threshold superata
            if rule.name in self._active_alerts:
                # Già firing
                continue

            # Nuovo alert
            alert = Alert(
                id=str(uuid.uuid4())[:12],
                rule_name=rule.name,
                severity=rule.severity,
                message=rule.annotations.get("description", f"{rule.name} triggered"),
                value=value,
                threshold=rule.threshold,
                labels={**labels, **rule.labels},
            )

            self._active_alerts[rule.name] = alert
            self._notify(alert)

            logger.warning(
                "alert_triggered",
                rule=rule.name,
                value=value,
                threshold=rule.threshold,
            )

            return alert

        return None

    def _check_condition(self, condition: str, value: float, threshold: float) -> bool:
        """Verifica condizione."""
        checks = {
            "gt": value > threshold,
            "lt": value < threshold,
            "eq": value == threshold,
            "gte": value >= threshold,
            "lte": value <= threshold,
        }
        return checks.get(condition, False)

    def _resolve_alert(self, rule_name: str) -> None:
        """Risolve alert."""
        alert = self._active_alerts.pop(rule_name, None)
        if alert:
            alert.status = "resolved"
            alert.resolved_at = datetime.now()

            self._resolved_alerts.append(alert)
            if len(self._resolved_alerts) > self._max_resolved:
                self._resolved_alerts.pop(0)

            logger.info("alert_resolved", rule=rule_name)

    def _notify(self, alert: Alert) -> None:
        """Notifica alert a tutti i notifiers."""
        for notifier in self._notifiers:
            try:
                notifier(alert)
            except Exception as e:
                logger.error("notifier_error", error=str(e))

    def get_active_alerts(self) -> list[Alert]:
        """Ottiene alerts attivi."""
        return list(self._active_alerts.values())

    def get_resolved_alerts(self, since: datetime | None = None) -> list[Alert]:
        """Ottiene alerts risolti recentemente."""
        if since:
            return [a for a in self._resolved_alerts if a.resolved_at and a.resolved_at > since]
        return self._resolved_alerts[-10:]  # Ultimi 10

    def clear_resolved(self) -> int:
        """Pulisce alerts risolti."""
        count = len(self._resolved_alerts)
        self._resolved_alerts.clear()
        return count


# --- Notifiers ---


def log_notifier(alert: Alert) -> None:
    """Notifier che logga alert."""
    logger.warning(
        "alert_notification",
        alert_id=alert.id,
        rule=alert.rule_name,
        severity=alert.severity.value,
        message=alert.message,
    )


async def webhook_notifier(alert: Alert, webhook_url: str) -> None:
    """
    Notifier webhook.

    Args:
        alert: Alert da notificare
        webhook_url: URL webhook
    """
    import aiohttp

    payload = {
        "alert_id": alert.id,
        "rule": alert.rule_name,
        "severity": alert.severity.value,
        "message": alert.message,
        "value": alert.value,
        "threshold": alert.threshold,
        "started_at": alert.started_at.isoformat(),
        "labels": alert.labels,
    }

    try:
        async with aiohttp.ClientSession() as session:
            await session.post(webhook_url, json=payload)
    except Exception as e:
        logger.error("webhook_notification_failed", error=str(e))


# Singleton
_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    """Ottiene manager globale."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
        _alert_manager.add_notifier(log_notifier)
    return _alert_manager
