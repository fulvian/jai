"""Natural Language to Monitor Parser.

Converte query in linguaggio naturale in configurazioni Monitor.

Esempi supportati:
- "avvisami quando BTC scende sotto 70k"
- "ogni mattina alle 9 verifica il calendario"
- "ogni ora controlla le email importanti"
- "crea un agente autonomo che monitora AAPL"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Trigger Phrases (Pattern Matching)
# =============================================================================

PROACTIVE_TRIGGERS = [
    # Creazione agente
    r"crea\s+(un\s+)?agente",
    r"crea\s+(un\s+)?sistema\s+automatic",
    r"crea\s+(un\s+)?monitor",
    r"imposta\s+(un\s+)?monitoraggio",
    r"attiva\s+(un\s+)?controllo",
    # Scheduling
    r"ogni\s+(mattina|sera|giorno|ora|minuto)",
    r"alle\s+\d{1,2}(:\d{2})?",
    r"periodicamente",
    r"quotidianamente",
    r"settimanalmente",
    # Alert/Notifiche
    r"avvisami\s+(quando|se)",
    r"notificami\s+(quando|se)",
    r"allertami\s+(quando|se)",
    r"fammi\s+sapere\s+(quando|se)",
    # Reminder
    r"ricordami\s+(di|che)",
    r"reminder",
    # Monitoring
    r"monitorami",
    r"tieni\s+d'occhio",
    r"controlla\s+(periodicamente|ogni)",
    r"verifica\s+(periodicamente|ogni)",
    r"traccia",
    r"segui",
]

PROACTIVE_PATTERN = re.compile(
    "|".join(f"({p})" for p in PROACTIVE_TRIGGERS),
    re.IGNORECASE,
)


# =============================================================================
# Schedule Patterns
# =============================================================================

SCHEDULE_PATTERNS = {
    # Time-based
    r"ogni\s+ora": "0 * * * *",
    r"ogni\s+(\d+)\s+ore": lambda m: f"0 */{m.group(1)} * * *",
    r"ogni\s+(\d+)\s+minuti": lambda m: f"*/{m.group(1)} * * * *",
    r"ogni\s+mattina": "0 8 * * *",
    r"ogni\s+sera": "0 20 * * *",
    r"ogni\s+giorno\s+alle\s+(\d{1,2})(?::(\d{2}))?": lambda m: f"{m.group(2) or '0'} {m.group(1)} * * *",
    r"alle\s+(\d{1,2})(?::(\d{2}))?": lambda m: f"{m.group(2) or '0'} {m.group(1)} * * *",
    r"quotidianamente": "0 9 * * *",
    r"settimanalmente": "0 9 * * 1",
    # Interval-based (in secondi per APScheduler)
    r"ogni\s+5\s+minuti": "*/5 * * * *",
    r"ogni\s+10\s+minuti": "*/10 * * * *",
    r"ogni\s+15\s+minuti": "*/15 * * * *",
    r"ogni\s+30\s+minuti": "*/30 * * * *",
}


# =============================================================================
# Monitor Type Detection
# =============================================================================


class DetectedMonitorType(str, Enum):
    """Tipi di monitor rilevabili da NL."""

    PRICE_WATCH = "price_watch"
    SIGNAL_WATCH = "signal_watch"
    AUTONOMOUS = "autonomous"
    HEARTBEAT = "heartbeat"
    TASK_REMINDER = "task_reminder"
    INBOX_WATCH = "inbox_watch"
    CALENDAR_WATCH = "calendar_watch"
    FILE_WATCH = "file_watch"
    SCHEDULED = "scheduled"
    GENERIC = "generic"


MONITOR_TYPE_PATTERNS = {
    DetectedMonitorType.PRICE_WATCH: [
        r"(prezzo|price|valore)\s+(di\s+)?(\w+)",
        r"(btc|bitcoin|eth|ethereum|aapl|tsla|stock|azione|crypto)",
        r"(scende|sale|supera|raggiunge)\s+(sotto|sopra)?\s*\d+",
    ],
    DetectedMonitorType.SIGNAL_WATCH: [
        r"(rsi|macd|bollinger|sma|ema|indicatore)",
        r"segnale\s+(di\s+)?(acquisto|vendita|buy|sell)",
    ],
    DetectedMonitorType.INBOX_WATCH: [
        r"(email|mail|posta|inbox|messaggio)",
        r"(gmail|outlook|mail)",
    ],
    DetectedMonitorType.CALENDAR_WATCH: [
        r"(calendario|calendar|eventi|appuntamenti|meeting)",
        r"(riunione|call|evento)",
    ],
    DetectedMonitorType.TASK_REMINDER: [
        r"ricordami\s+di",
        r"reminder",
        r"promemoria",
    ],
    DetectedMonitorType.HEARTBEAT: [
        r"agente\s+autonomo",
        r"sistema\s+automatic",
        r"proattivo",
        r"assistente\s+personale",
    ],
    DetectedMonitorType.FILE_WATCH: [
        r"(file|cartella|directory|documento)",
        r"(modifica|cambiamento|upload)",
    ],
}


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ParsedMonitor:
    """Risultato parsing NL → Monitor config."""

    type: DetectedMonitorType
    name: str
    description: str
    schedule: str | None  # Cron expression
    interval_seconds: int | None  # For interval-based
    config: dict[str, Any] = field(default_factory=dict)
    notify_channels: list[str] = field(default_factory=lambda: ["web"])
    confidence: float = 0.0
    raw_query: str = ""


@dataclass
class IntentResult:
    """Risultato intent detection."""

    is_proactive: bool
    confidence: float
    trigger_phrase: str | None = None
    query: str = ""


# =============================================================================
# NL Parser Class
# =============================================================================


class NLMonitorParser:
    """Parser per convertire linguaggio naturale in Monitor config.

    Usa pattern matching locale + opzionalmente LLM per parsing avanzato.
    """

    def __init__(self, llm_client: Any = None):
        """Inizializza parser.

        Args:
            llm_client: Client LLM opzionale per parsing avanzato
        """
        self._llm_client = llm_client

    def detect_proactive_intent(self, query: str) -> IntentResult:
        """Rileva se la query ha intent proattivo.

        Args:
            query: Query utente

        Returns:
            IntentResult con flag e confidence
        """
        query_lower = query.lower().strip()

        match = PROACTIVE_PATTERN.search(query_lower)
        if match:
            trigger = match.group(0)
            # Calcola confidence basata su quanto è esplicito il trigger
            confidence = 0.9 if len(trigger) > 10 else 0.7

            logger.info(
                "proactive_intent_detected",
                trigger=trigger,
                confidence=confidence,
            )

            return IntentResult(
                is_proactive=True,
                confidence=confidence,
                trigger_phrase=trigger,
                query=query,
            )

        return IntentResult(
            is_proactive=False,
            confidence=0.0,
            query=query,
        )

    def _detect_monitor_type(self, query: str) -> tuple[DetectedMonitorType, float]:
        """Rileva tipo di monitor dalla query.

        Returns:
            Tupla (tipo, confidence)
        """
        query_lower = query.lower()
        scores: dict[DetectedMonitorType, int] = {}

        for mon_type, patterns in MONITOR_TYPE_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    score += 1
            if score > 0:
                scores[mon_type] = score

        if not scores:
            return DetectedMonitorType.SCHEDULED, 0.5

        best_type = max(scores, key=scores.get)  # type: ignore
        max_score = scores[best_type]
        confidence = min(0.9, 0.5 + (max_score * 0.15))

        return best_type, confidence

    def _extract_schedule(self, query: str) -> tuple[str | None, int | None]:
        """Estrae schedule dalla query.

        Returns:
            Tupla (cron_expression, interval_seconds)
        """
        query_lower = query.lower()

        for pattern, result in SCHEDULE_PATTERNS.items():
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                if callable(result):
                    cron = result(match)
                else:
                    cron = result
                return cron, None

        # Default: ogni 5 minuti per price watch, ogni ora per altri
        return "*/5 * * * *", None

    def _extract_price_config(self, query: str) -> dict[str, Any]:
        """Estrae configurazione per PRICE_WATCH."""
        config: dict[str, Any] = {}
        query_lower = query.lower()

        # Ticker
        ticker_patterns = [
            (r"\b(btc|bitcoin)\b", "BTC"),
            (r"\b(eth|ethereum)\b", "ETH"),
            (r"\b(sol|solana)\b", "SOL"),
            (r"\b(aapl|apple)\b", "AAPL"),
            (r"\b(tsla|tesla)\b", "TSLA"),
            (r"\b(msft|microsoft)\b", "MSFT"),
            (r"\b(googl|google|alphabet)\b", "GOOGL"),
            (r"\b(amzn|amazon)\b", "AMZN"),
        ]

        for pattern, ticker in ticker_patterns:
            if re.search(pattern, query_lower):
                config["ticker"] = ticker
                break

        if "ticker" not in config:
            # Cerca ticker generico (3-5 lettere maiuscole)
            match = re.search(r"\b([A-Z]{3,5})\b", query)
            if match:
                config["ticker"] = match.group(1)

        # Threshold e condizione
        threshold_match = re.search(
            r"(scende|cala|sotto|below|under)\s*(?:a|di|i)?\s*(\d+(?:[.,]\d+)?(?:k|K)?)",
            query_lower,
        )
        if threshold_match:
            config["condition"] = "below"
            value = threshold_match.group(2).replace(",", ".").lower()
            if "k" in value:
                config["threshold"] = float(value.replace("k", "")) * 1000
            else:
                config["threshold"] = float(value)
        else:
            threshold_match = re.search(
                r"(sale|supera|sopra|above|over)\s*(?:a|di|i)?\s*(\d+(?:[.,]\d+)?(?:k|K)?)",
                query_lower,
            )
            if threshold_match:
                config["condition"] = "above"
                value = threshold_match.group(2).replace(",", ".").lower()
                if "k" in value:
                    config["threshold"] = float(value.replace("k", "")) * 1000
                else:
                    config["threshold"] = float(value)

        config.setdefault("currency", "USD")

        return config

    def _extract_calendar_config(self, query: str) -> dict[str, Any]:
        """Estrae config per CALENDAR_WATCH."""
        return {
            "calendar_id": "primary",
            "lookahead_minutes": 30,
            "event_types": ["meeting", "deadline"],
            "include_travel_time": True,
        }

    def _extract_inbox_config(self, query: str) -> dict[str, Any]:
        """Estrae config per INBOX_WATCH."""
        query_lower = query.lower()

        importance = "medium"
        if any(w in query_lower for w in ["importante", "urgente", "critical"]):
            importance = "high"

        return {
            "email_account": "default",
            "filters": {},
            "action_on_match": "notify",
            "importance_threshold": importance,
        }

    def _extract_reminder_config(self, query: str) -> dict[str, Any]:
        """Estrae config per TASK_REMINDER."""
        # Rimuovi trigger phrase per ottenere descrizione
        desc = re.sub(r"ricordami\s+di\s+", "", query, flags=re.IGNORECASE)
        desc = re.sub(r"reminder\s*:?\s*", "", desc, flags=re.IGNORECASE)

        return {
            "task_description": desc.strip(),
            "priority": "medium",
        }

    def _extract_heartbeat_config(self, query: str) -> dict[str, Any]:
        """Estrae config per HEARTBEAT (agente autonomo)."""
        return {
            "goal": "proactive_assistance",
            "context_sources": ["calendar", "memory", "reminders"],
            "min_urgency": "low",
            "action_mode": "notify",
        }

    def _generate_name(self, monitor_type: DetectedMonitorType, config: dict) -> str:
        """Genera nome leggibile per il monitor."""
        if monitor_type == DetectedMonitorType.PRICE_WATCH:
            ticker = config.get("ticker", "Asset")
            condition = config.get("condition", "watch")
            return f"Price Alert: {ticker} {condition}"
        elif monitor_type == DetectedMonitorType.CALENDAR_WATCH:
            return "Calendar Monitor"
        elif monitor_type == DetectedMonitorType.INBOX_WATCH:
            return "Email Monitor"
        elif monitor_type == DetectedMonitorType.TASK_REMINDER:
            desc = config.get("task_description", "Task")[:30]
            return f"Reminder: {desc}"
        elif monitor_type == DetectedMonitorType.HEARTBEAT:
            return "Autonomous Agent"
        else:
            return f"Monitor: {monitor_type.value}"

    def parse(self, query: str) -> ParsedMonitor | None:
        """Parse completo query → Monitor config.

        Args:
            query: Query utente in linguaggio naturale

        Returns:
            ParsedMonitor se parsing riuscito, None altrimenti
        """
        # 1. Check intent
        intent = self.detect_proactive_intent(query)
        if not intent.is_proactive:
            return None

        # 2. Detect tipo
        monitor_type, type_confidence = self._detect_monitor_type(query)

        # 3. Extract schedule
        cron, interval = self._extract_schedule(query)

        # 4. Extract config basato su tipo
        if monitor_type == DetectedMonitorType.PRICE_WATCH:
            config = self._extract_price_config(query)
        elif monitor_type == DetectedMonitorType.CALENDAR_WATCH:
            config = self._extract_calendar_config(query)
        elif monitor_type == DetectedMonitorType.INBOX_WATCH:
            config = self._extract_inbox_config(query)
        elif monitor_type == DetectedMonitorType.TASK_REMINDER:
            config = self._extract_reminder_config(query)
        elif monitor_type == DetectedMonitorType.HEARTBEAT:
            config = self._extract_heartbeat_config(query)
        else:
            config = {"raw_query": query}

        # 5. Generate name
        name = self._generate_name(monitor_type, config)

        # 6. Calcola confidence complessiva
        overall_confidence = (intent.confidence + type_confidence) / 2

        parsed = ParsedMonitor(
            type=monitor_type,
            name=name,
            description=query,
            schedule=cron,
            interval_seconds=interval,
            config=config,
            notify_channels=["web"],
            confidence=overall_confidence,
            raw_query=query,
        )

        logger.info(
            "monitor_parsed",
            type=monitor_type.value,
            name=name,
            confidence=overall_confidence,
            schedule=cron,
        )

        return parsed

    async def parse_with_llm(self, query: str) -> ParsedMonitor | None:
        """Parse avanzato usando LLM per disambiguazione.

        Fallback a parse() locale se LLM non disponibile.
        """
        # Per ora usa parsing locale
        # TODO: Integrare chiamata LLM per casi complessi
        return self.parse(query)


# =============================================================================
# Utility Functions
# =============================================================================


def is_proactive_query(query: str) -> bool:
    """Quick check se query ha intent proattivo."""
    return bool(PROACTIVE_PATTERN.search(query.lower()))


def get_parser() -> NLMonitorParser:
    """Factory per ottenere parser singleton."""
    return NLMonitorParser()
