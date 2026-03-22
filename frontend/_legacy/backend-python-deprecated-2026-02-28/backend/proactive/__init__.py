"""Proactive Agent System.

Modulo per monitoraggio autonomo e esecuzione schedulata.
"""

from backend.proactive.monitors import (
    Monitor,
    MonitorConfig,
    MonitorState,
    MonitorType,
    EvaluationResult,
)
from backend.proactive.scheduler import ProactiveScheduler
from backend.proactive.evaluator import MonitorEvaluator
from backend.proactive.notifications import NotificationDispatcher

__all__ = [
    "Monitor",
    "MonitorConfig",
    "MonitorState",
    "MonitorType",
    "EvaluationResult",
    "ProactiveScheduler",
    "MonitorEvaluator",
    "NotificationDispatcher",
]
