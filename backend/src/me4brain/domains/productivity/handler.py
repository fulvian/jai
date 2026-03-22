"""Productivity Domain Handler - Tasks, Calendar, Notes, and Communication."""

from datetime import UTC, datetime
from typing import Any
import structlog
from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
)

logger = structlog.get_logger(__name__)


class ProductivityHandler(DomainHandler):
    """Domain handler for productivity queries (Notes, Reminders, Calendar, Slack, Email)."""

    PRODUCTIVITY_KEYWORDS = frozenset(
        {
            "nota",
            "note",
            "appunto",
            "memo",
            "promemoria",
            "reminder",
            "task",
            "compito",
            "todo",
            "da fare",
            "calendario",
            "appuntamento",
            "evento",
            "calendar",
            "event",
            "email",
            "mail",
            "posta",
            "slack",
            "messaggio",
            "canale",
            "chat",
            "produttività",
            "productivity",
            "organizzazione",
            "scrivere",
            "leggere",
            "cercare",
            "search",
            "read",
            "write",
            "todoist",
            "obsidian",
        }
    )

    @property
    def domain_name(self) -> str:
        return "productivity"

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.REAL_TIME

    @property
    def default_ttl_hours(self) -> int:
        return 1

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="personal_management",
                description="Gestione di note, task e calendari personali",
                keywords=["nota", "promemoria", "calendario"],
                example_queries=[
                    "Crea una nota sulla riunione",
                    "Aggiungi un promemoria",
                    "Mostra i miei eventi di oggi",
                ],
            ),
            DomainCapability(
                name="communication",
                description="Gestione di email e messaggistica aziendale (Slack)",
                keywords=["email", "slack", "messaggio"],
                example_queries=[
                    "Invia una mail a Mario",
                    "Controlla i messaggi non letti su Slack",
                ],
            ),
        ]

    async def initialize(self) -> None:
        logger.info("productivity_handler_initialized")

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        matches = sum(1 for kw in self.PRODUCTIVITY_KEYWORDS if kw in query.lower())
        return min(0.9, matches * 0.25) if matches else 0.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        # Implementation will be handled via execute_tool calls from the engine/router
        return []

    def handles_service(self, service_name: str) -> bool:
        return False

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from me4brain.domains.productivity.tools import productivity_api

        return await productivity_api.execute_tool(tool_name, arguments)
