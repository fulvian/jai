"""Monitor Models and Registry.

Definisce i modelli per i monitor proattivi e il registry per gestirli.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class MonitorType(str, Enum):
    """Tipi di monitor supportati."""

    # Finance
    PRICE_WATCH = "price_watch"  # Prezzo supera soglia
    SIGNAL_WATCH = "signal_watch"  # Indicatore tecnico (RSI, MACD, etc.)
    AUTONOMOUS = "autonomous"  # Valutazione LLM continua

    # Generic (OpenClaw-style)
    HEARTBEAT = "heartbeat"  # Reasoning periodico autonomo
    TASK_REMINDER = "task_reminder"  # Reminder generico
    INBOX_WATCH = "inbox_watch"  # Monitoraggio inbox email
    CALENDAR_WATCH = "calendar_watch"  # Eventi imminenti
    FILE_WATCH = "file_watch"  # Monitoraggio file/directory

    # System
    SCHEDULED = "scheduled"  # Cron-based
    EVENT_DRIVEN = "event_driven"  # Webhook trigger


class MonitorState(str, Enum):
    """Stati del ciclo di vita del monitor."""

    IDLE = "idle"  # Creato ma non ancora attivo
    ACTIVE = "active"  # In esecuzione, schedulato
    PAUSED = "paused"  # Temporaneamente sospeso
    TRIGGERED = "triggered"  # Condizione soddisfatta, notifica inviata
    COMPLETED = "completed"  # Obiettivo raggiunto, terminato
    ERROR = "error"  # Errore durante esecuzione


class NotifyChannel(str, Enum):
    """Canali di notifica disponibili."""

    WEB = "web"  # WebSocket push al frontend
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SLACK = "slack"


# =============================================================================
# Monitor Config per tipo
# =============================================================================


class PriceWatchConfig(BaseModel):
    """Config per PRICE_WATCH: prezzo supera soglia."""

    ticker: str
    condition: str = "below"  # "below" | "above"
    threshold: float
    currency: str = "USD"


class SignalWatchConfig(BaseModel):
    """Config per SIGNAL_WATCH: indicatore tecnico."""

    ticker: str
    indicator: str  # "rsi" | "macd" | "bollinger" | etc.
    condition: str  # "below" | "above" | "cross_up" | "cross_down"
    threshold: float | None = None  # Es. RSI < 30


class AutonomousConfig(BaseModel):
    """Config per AUTONOMOUS: valutazione LLM continua."""

    ticker: str
    goal: str = "both"  # "buy" | "sell" | "both"
    min_confidence: int = 70  # Soglia confidenza per trigger
    analysis_depth: str = "standard"  # "quick" | "standard" | "deep"


class ScheduledConfig(BaseModel):
    """Config per SCHEDULED: cron-based."""

    cron_expression: str  # "0 9 * * MON" = ogni lunedì alle 9
    task: str  # Descrizione task da eseguire
    params: dict[str, Any] = Field(default_factory=dict)


class EventDrivenConfig(BaseModel):
    """Config per EVENT_DRIVEN: webhook trigger."""

    webhook_id: str
    event_type: str  # "email_received" | "payment" | "custom"
    filters: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Generic Monitor Configs (OpenClaw-style)
# =============================================================================


class HeartbeatConfig(BaseModel):
    """Config per HEARTBEAT: reasoning periodico autonomo."""

    goal: str = "proactive_assistance"  # Obiettivo del reasoning
    context_sources: list[str] = Field(default_factory=lambda: ["calendar", "memory", "reminders"])
    min_urgency: str = "low"  # Soglia minima per notificare
    action_mode: str = "notify"  # "notify" | "confirm" | "execute"


class TaskReminderConfig(BaseModel):
    """Config per TASK_REMINDER: reminder generico."""

    task_description: str
    due_date: str | None = None  # ISO format
    repeat: str | None = None  # "daily" | "weekly" | "monthly"
    priority: str = "medium"  # "low" | "medium" | "high"


class InboxWatchConfig(BaseModel):
    """Config per INBOX_WATCH: monitoraggio email."""

    email_account: str = "default"  # Account email da monitorare
    filters: dict[str, Any] = Field(default_factory=dict)  # from, subject, etc.
    action_on_match: str = "notify"  # "notify" | "summarize" | "forward"
    importance_threshold: str = "medium"  # "low" | "medium" | "high"


class CalendarWatchConfig(BaseModel):
    """Config per CALENDAR_WATCH: eventi imminenti."""

    calendar_id: str = "primary"
    lookahead_minutes: int = 30  # Quanto prima notificare
    event_types: list[str] = Field(default_factory=lambda: ["meeting", "deadline"])
    include_travel_time: bool = True


class FileWatchConfig(BaseModel):
    """Config per FILE_WATCH: monitoraggio file/directory."""

    path: str  # Path da monitorare
    events: list[str] = Field(default_factory=lambda: ["created", "modified"])
    patterns: list[str] = Field(default_factory=lambda: ["*"])  # Glob patterns
    recursive: bool = False


# Union type per config
MonitorConfig = (
    PriceWatchConfig
    | SignalWatchConfig
    | AutonomousConfig
    | ScheduledConfig
    | EventDrivenConfig
    | HeartbeatConfig
    | TaskReminderConfig
    | InboxWatchConfig
    | CalendarWatchConfig
    | FileWatchConfig
)


# =============================================================================
# Evaluation Result
# =============================================================================


class Decision(BaseModel):
    """Decisione dell'LLM."""

    recommendation: str  # "BUY" | "SELL" | "HOLD" | "WAIT"
    confidence: int  # 0-100
    reasoning: str
    key_factors: list[str] = Field(default_factory=list)
    suggested_action: str | None = None


class EvaluationResult(BaseModel):
    """Risultato di una valutazione."""

    monitor_id: str
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
    trigger: bool = False
    decision: Decision | None = None
    data_snapshot: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


# =============================================================================
# Main Monitor Model
# =============================================================================


class Monitor(BaseModel):
    """Monitor proattivo."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    type: MonitorType
    name: str
    description: str | None = None

    # Config specifica per tipo
    config: dict[str, Any]  # Parsed come *Config in base al type

    # Scheduling
    interval_minutes: int = 15  # Frequenza check (default 15 min)
    max_checks: int | None = None  # Limite check (None = infinito)

    # Notifiche
    notify_channels: list[NotifyChannel] = Field(default_factory=lambda: [NotifyChannel.WEB])

    # Stato
    state: MonitorState = MonitorState.IDLE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_check: datetime | None = None
    next_check: datetime | None = None
    checks_count: int = 0
    triggers_count: int = 0

    # History (ultimi N risultati)
    history: list[EvaluationResult] = Field(default_factory=list)
    max_history: int = 50

    def add_evaluation(self, result: EvaluationResult) -> None:
        """Aggiunge risultato alla history."""
        self.history.insert(0, result)
        if len(self.history) > self.max_history:
            self.history = self.history[: self.max_history]
        self.checks_count += 1
        self.last_check = result.evaluated_at
        if result.trigger:
            self.triggers_count += 1


# =============================================================================
# Request/Response Models per API
# =============================================================================


class CreateMonitorRequest(BaseModel):
    """Request per creare un monitor."""

    type: MonitorType
    name: str
    description: str | None = None
    config: dict[str, Any]
    interval_minutes: int = 15
    notify_channels: list[NotifyChannel] = Field(default_factory=lambda: [NotifyChannel.WEB])


class MonitorListResponse(BaseModel):
    """Response lista monitor."""

    monitors: list[Monitor]
    total: int
    active_count: int
    paused_count: int


class MonitorStatsResponse(BaseModel):
    """Statistiche monitor."""

    total_monitors: int
    active_monitors: int
    total_checks: int
    total_triggers: int
    by_type: dict[str, int]
