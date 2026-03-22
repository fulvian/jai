"""Sports Booking Domain Handler.

Handler per ricerca e prenotazione campi sportivi tramite Playtomic.
Supporta padel, tennis e altri sport disponibili sulla piattaforma.
"""

from typing import Any

import structlog

from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
)

logger = structlog.get_logger(__name__)


class SportsBookingHandler(DomainHandler):
    """Handler per prenotazione campi sportivi via Playtomic."""

    HANDLED_SERVICES = frozenset({"PlaytomicService"})

    BOOKING_KEYWORDS = frozenset(
        {
            # Sport
            "padel",
            "tennis",
            "campo",
            "campi",
            "court",
            "courts",
            # Azioni
            "prenota",
            "prenotare",
            "prenotazione",
            "book",
            "booking",
            "disponibilità",
            "disponibile",
            "available",
            "availability",
            "slot",
            # Platform
            "playtomic",
            # Luoghi
            "club",
            "centro",
            "circolo",
        }
    )

    @property
    def domain_name(self) -> str:
        return "sports_booking"

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="club_search",
                description="Cerca club sportivi per città o nome",
                required_params=[],
                optional_params=["query", "sport"],
            ),
            DomainCapability(
                name="court_availability",
                description="Verifica disponibilità campi per data e fascia oraria",
                required_params=["tenant_id", "date"],
                optional_params=["time_from", "time_to", "sport"],
            ),
            DomainCapability(
                name="court_booking",
                description="Prenota un campo (richiede autenticazione)",
                required_params=["resource_id", "start_time", "duration"],
            ),
            DomainCapability(
                name="my_bookings",
                description="Lista prenotazioni utente",
                required_params=[],
                optional_params=["upcoming_only"],
            ),
        ]

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.REAL_TIME

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        """Determina se questo handler può gestire la query."""
        query_lower = query.lower()
        matches = sum(1 for kw in self.BOOKING_KEYWORDS if kw in query_lower)

        # Alta confidenza se menzione esplicita di playtomic
        if "playtomic" in query_lower:
            return 0.95

        # Alta confidenza se sport + azione booking
        sport_keywords = {"padel", "tennis", "campo", "campi", "court"}
        action_keywords = {"prenota", "prenotare", "disponibilità", "available", "slot", "book"}

        has_sport = any(kw in query_lower for kw in sport_keywords)
        has_action = any(kw in query_lower for kw in action_keywords)

        if has_sport and has_action:
            return 0.9

        if matches >= 2:
            return 0.8
        elif matches == 1:
            return 0.6

        return 0.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Esegue la query sul dominio sports_booking."""
        from .tools.playtomic_api import execute_tool
        import re
        from datetime import datetime, timedelta

        query_lower = query.lower()
        results: list[DomainExecutionResult] = []

        # Estrai date dalla query
        date = self._extract_date(query_lower)

        # Estrai fascia oraria
        time_from, time_to = self._extract_time_range(query_lower)

        # Estrai città/location
        location = self._extract_location(query, analysis)

        # Determina l'azione richiesta
        if any(kw in query_lower for kw in ["cerca", "search", "trova", "club", "dove"]):
            # Ricerca club
            data = await execute_tool(
                "playtomic_search_clubs",
                {"query": location or "Milano", "sport": "PADEL"},
            )
            results.append(
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="playtomic_search_clubs",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            )

        elif any(
            kw in query_lower for kw in ["disponibil", "available", "slot", "libero", "liberi"]
        ):
            # Disponibilità campi
            # Estrai tenant_id dal contesto o dalla query
            tenant_id = context.get("tenant_id") or self._extract_tenant_id(query, analysis)

            if not tenant_id:
                # Prima cerca il club, poi disponibilità
                search_data = await execute_tool(
                    "playtomic_search_clubs",
                    {"query": location or "Milano", "sport": "PADEL"},
                )
                if search_data.get("clubs"):
                    tenant_id = search_data["clubs"][0].get("tenant_id")

            if tenant_id:
                params = {
                    "tenant_id": tenant_id,
                    "date": date or datetime.now().strftime("%Y-%m-%d"),
                    "sport": "PADEL",
                }
                if time_from:
                    params["time_from"] = time_from
                if time_to:
                    params["time_to"] = time_to

                data = await execute_tool("playtomic_club_availability", params)
                results.append(
                    DomainExecutionResult(
                        success=not data.get("error"),
                        domain=self.domain_name,
                        tool_name="playtomic_club_availability",
                        data=data if not data.get("error") else {},
                        error=data.get("error"),
                    )
                )
            else:
                results.append(
                    DomainExecutionResult(
                        success=False,
                        domain=self.domain_name,
                        tool_name="playtomic_club_availability",
                        data={},
                        error="Impossibile identificare il club. Specifica il nome del club.",
                    )
                )

        elif any(kw in query_lower for kw in ["prenota", "book", "riserva"]):
            # Prenotazione
            data = await execute_tool(
                "playtomic_book_court",
                {
                    "resource_id": context.get("resource_id", ""),
                    "start_time": context.get("start_time", ""),
                    "duration": context.get("duration", 90),
                },
            )
            results.append(
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="playtomic_book_court",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            )

        elif any(kw in query_lower for kw in ["mie prenotazioni", "my booking", "le mie"]):
            # Lista prenotazioni
            data = await execute_tool("playtomic_my_bookings", {"upcoming_only": True})
            results.append(
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="playtomic_my_bookings",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            )

        else:
            # Default: ricerca club
            data = await execute_tool(
                "playtomic_search_clubs",
                {"query": location or "Milano", "sport": "PADEL"},
            )
            results.append(
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="playtomic_search_clubs",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            )

        return results

    def _extract_date(self, query: str) -> str | None:
        """Estrae data dalla query."""
        from datetime import datetime, timedelta
        import re

        today = datetime.now()

        if "oggi" in query or "today" in query:
            return today.strftime("%Y-%m-%d")
        elif "domani" in query or "tomorrow" in query:
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "dopodomani" in query:
            return (today + timedelta(days=2)).strftime("%Y-%m-%d")

        # Cerca data esplicita (es. 2026-02-07 o 07/02/2026)
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", query)
        if date_match:
            return date_match.group(1)

        date_match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", query)
        if date_match:
            day, month, year = date_match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        return None

    def _extract_time_range(self, query: str) -> tuple[str | None, str | None]:
        """Estrae fascia oraria dalla query."""
        import re

        time_from = None
        time_to = None

        # Pattern: "dalle 18 alle 21", "from 18:00 to 21:00"
        range_match = re.search(
            r"(?:dalle?|from)\s*(\d{1,2})(?::(\d{2}))?\s*(?:alle?|to)\s*(\d{1,2})(?::(\d{2}))?",
            query,
        )
        if range_match:
            h1, m1, h2, m2 = range_match.groups()
            time_from = f"{h1.zfill(2)}:{m1 or '00'}"
            time_to = f"{h2.zfill(2)}:{m2 or '00'}"
            return time_from, time_to

        # Pattern: "dopo le 18", "after 18:00"
        after_match = re.search(r"(?:dopo\s*le?|after)\s*(\d{1,2})(?::(\d{2}))?", query)
        if after_match:
            h, m = after_match.groups()
            time_from = f"{h.zfill(2)}:{m or '00'}"

        # Pattern: "prima delle 21", "before 21:00"
        before_match = re.search(r"(?:prima\s*(?:delle?)?|before)\s*(\d{1,2})(?::(\d{2}))?", query)
        if before_match:
            h, m = before_match.groups()
            time_to = f"{h.zfill(2)}:{m or '00'}"

        return time_from, time_to

    def _extract_location(self, query: str, analysis: dict[str, Any]) -> str | None:
        """Estrae città/location dalla query."""
        # Città italiane comuni
        cities = [
            "milano",
            "roma",
            "napoli",
            "torino",
            "firenze",
            "bologna",
            "genova",
            "palermo",
            "catania",
            "bari",
            "venezia",
            "verona",
            "padova",
            "brescia",
            "bergamo",
            "modena",
            "parma",
            "reggio",
        ]

        query_lower = query.lower()
        for city in cities:
            if city in query_lower:
                return city.capitalize()

        # Cerca nell'analisi
        entities = analysis.get("entities", [])
        for entity in entities:
            if entity.get("type") == "location":
                return entity.get("value")

        return None

    def _extract_tenant_id(self, query: str, analysis: dict[str, Any]) -> str | None:
        """Estrae tenant_id dal contesto o dalla query."""
        # Cerca nell'analisi se c'è un club menzionato
        entities = analysis.get("entities", [])
        for entity in entities:
            if entity.get("type") == "club_id":
                return entity.get("value")

        return None
