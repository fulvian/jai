"""Google Workspace Domain Handler.

Implementazione DomainHandler per Google Workspace APIs.
Gestisce query su Drive, Gmail, Calendar, Docs, Sheets, etc.

Volatilità: SEMI_VOLATILE (dati cambiano frequentemente ma non real-time)
Tool-First: Dipende dal contesto (cerca memoria prima per file noti)
"""

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


class GoogleWorkspaceHandler(DomainHandler):
    """Domain handler per Google Workspace queries.

    Capabilities:
    - Drive: file search, list, download
    - Gmail: email search, read
    - Calendar: event list, search, upcoming
    - Docs: read documents
    - Sheets: read spreadsheets
    - Meet: create/get meetings

    Example queries:
    - "Cerca file su Drive relativi al progetto X"
    - "Mostrami le email di oggi"
    - "Cosa ho in calendario questa settimana?"
    - "Leggi il documento Y"
    """

    # Services gestiti da questo handler
    HANDLED_SERVICES = frozenset(
        {
            "GoogleWorkspaceService",
            "GoogleDriveService",
            "GoogleGmailService",
            "GoogleCalendarService",
            "GoogleDocsService",
            "GoogleSheetsService",
            "GoogleSlidesService",
            "GoogleMeetService",
            "GoogleFormsService",
            "GoogleClassroomService",
        }
    )

    # Keywords per routing rapido
    GOOGLE_KEYWORDS = frozenset(
        {
            # Generici
            "google",
            "workspace",
            # Drive
            "drive",
            "file",
            "files",
            "cartella",
            "folder",
            "documento",
            "documenti",
            "pdf",
            "spreadsheet",
            "foglio",
            # Gmail
            "gmail",
            "email",
            "mail",
            "posta",
            "inbox",
            "messaggi",
            "messaggio",
            # Calendar
            "calendar",
            "calendario",
            "evento",
            "eventi",
            "appuntamento",
            "appuntamenti",
            "meeting",
            "riunione",
            "riunioni",
            # Docs
            "docs",
            # Sheets
            "sheets",
            "excel",
            # Slides
            "slides",
            "presentazione",
            "presentazioni",
            # Meet
            "meet",
            "videochiamata",
            "videocall",
            # Forms
            "forms",
            "form",
            "modulo",
            "questionario",
            # Classroom
            "classroom",
            "corso",
            "corsi",
        }
    )

    # Pattern per routing sub-service
    DRIVE_PATTERNS = ["drive", "file", "cartella", "folder", "documento", "pdf"]
    GMAIL_PATTERNS = ["gmail", "email", "mail", "posta", "inbox", "messaggio"]
    CALENDAR_PATTERNS = ["calendar", "calendario", "evento", "appuntamento", "meeting", "riunione"]
    DOCS_PATTERNS = ["docs", "documento"]
    SHEETS_PATTERNS = ["sheets", "spreadsheet", "foglio", "excel"]
    SLIDES_PATTERNS = ["slides", "presentazione"]
    MEET_PATTERNS = ["meet", "videochiamata", "videocall"]

    @property
    def domain_name(self) -> str:
        """Nome univoco dominio."""
        return "google_workspace"

    @property
    def volatility(self) -> DomainVolatility:
        """Dati Google cambiano frequentemente ma non in real-time."""
        return DomainVolatility.SEMI_VOLATILE

    @property
    def default_ttl_hours(self) -> int:
        """TTL 4 ore per dati Google."""
        return 4

    @property
    def capabilities(self) -> list[DomainCapability]:
        """Capabilities esposte dal dominio Google Workspace."""
        return [
            DomainCapability(
                name="google_drive",
                description="Cerca e gestisci file su Google Drive",
                keywords=["drive", "file", "folder", "documento", "pdf", "cartella"],
                example_queries=[
                    "Cerca file su Drive relativi al progetto",
                    "Elenca i file nella cartella X",
                    "Trova documenti modificati oggi",
                ],
            ),
            DomainCapability(
                name="google_gmail",
                description="Cerca e leggi email in Gmail",
                keywords=["gmail", "email", "mail", "posta", "inbox"],
                example_queries=[
                    "Mostrami le email di oggi",
                    "Cerca email da Mario Rossi",
                    "Email non lette questa settimana",
                ],
            ),
            DomainCapability(
                name="google_calendar",
                description="Gestisci eventi e appuntamenti in Calendar",
                keywords=["calendar", "calendario", "evento", "meeting", "appuntamento"],
                example_queries=[
                    "Cosa ho in calendario oggi?",
                    "Eventi della prossima settimana",
                    "Prossimo meeting",
                ],
            ),
            DomainCapability(
                name="google_docs",
                description="Leggi e gestisci documenti Google Docs",
                keywords=["docs", "documento", "testo"],
                example_queries=[
                    "Leggi il documento X",
                    "Contenuto del doc Y",
                ],
            ),
            DomainCapability(
                name="google_sheets",
                description="Accedi a dati in Google Sheets",
                keywords=["sheets", "spreadsheet", "excel", "foglio"],
                example_queries=[
                    "Dati dal foglio X",
                    "Valori nello spreadsheet Y",
                ],
            ),
        ]

    async def initialize(self) -> None:
        """Setup handler Google Workspace."""
        logger.info("google_workspace_handler_initialized")

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        """Determina se la query è Google Workspace-related."""
        query_lower = query.lower()

        # Check entities da analisi LLM
        entities = analysis.get("entities", [])
        google_entities = sum(
            1 for e in entities if any(kw in str(e).lower() for kw in self.GOOGLE_KEYWORDS)
        )

        # Check keywords diretti nella query
        keyword_matches = sum(1 for kw in self.GOOGLE_KEYWORDS if kw in query_lower)

        # Score: combinazione entities + keywords
        total_matches = google_entities + keyword_matches

        if total_matches == 0:
            return 0.0
        elif total_matches == 1:
            return 0.5
        elif total_matches == 2:
            return 0.7
        elif total_matches <= 4:
            return 0.85
        else:
            return 1.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Esegue logica Google Workspace con routing a sub-service."""
        query_lower = query.lower()
        start_time = datetime.now(UTC)
        results: list[DomainExecutionResult] = []

        logger.info(
            "google_workspace_execute",
            query_preview=query[:50],
            entities=analysis.get("entities", []),
        )

        # Determina sub-service target
        target_service = self._detect_target_service(query_lower)

        try:
            if target_service == "drive":
                results = [await self._execute_drive(query, analysis)]
            elif target_service == "gmail":
                results = [await self._execute_gmail(query, analysis)]
            elif target_service == "calendar":
                results = [await self._execute_calendar(query, analysis)]
            elif target_service == "docs":
                results = [await self._execute_docs(query, analysis)]
            elif target_service == "sheets":
                results = [await self._execute_sheets(query, analysis)]
            else:
                # Default: multi-service search
                results = await self._execute_multi_service(query, analysis)
        except Exception as e:
            logger.error("google_workspace_execution_error", error=str(e))
            results = [
                DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name=f"google_{target_service or 'workspace'}",
                    error=str(e),
                )
            ]

        # Add timing
        latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
        for r in results:
            r.latency_ms = latency_ms

        return results

    def _detect_target_service(self, query: str) -> str | None:
        """Rileva quale sub-service Google è target della query."""
        for pattern in self.DRIVE_PATTERNS:
            if pattern in query:
                return "drive"
        for pattern in self.GMAIL_PATTERNS:
            if pattern in query:
                return "gmail"
        for pattern in self.CALENDAR_PATTERNS:
            if pattern in query:
                return "calendar"
        for pattern in self.DOCS_PATTERNS:
            if pattern in query:
                return "docs"
        for pattern in self.SHEETS_PATTERNS:
            if pattern in query:
                return "sheets"
        for pattern in self.SLIDES_PATTERNS:
            if pattern in query:
                return "slides"
        for pattern in self.MEET_PATTERNS:
            if pattern in query:
                return "meet"
        return None

    async def _execute_drive(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue ricerca su Google Drive."""
        from me4brain.domains.google_workspace.tools import google_api

        # Estrai search term dalla query
        search_term = self._extract_search_term(query)

        try:
            data = await google_api.drive_search(query=search_term)
            has_error = bool(data.get("error"))
            return DomainExecutionResult(
                success=not has_error,
                domain=self.domain_name,
                tool_name="google_drive_search",
                data={} if has_error else data,
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="google_drive_search",
                error=str(e),
            )

    async def _execute_gmail(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue ricerca in Gmail."""
        from me4brain.domains.google_workspace.tools import google_api

        # Estrai search term o costruisci query Gmail
        search_term = self._extract_search_term(query)

        try:
            data = await google_api.gmail_search(query=search_term)
            has_error = bool(data.get("error"))
            return DomainExecutionResult(
                success=not has_error,
                domain=self.domain_name,
                tool_name="google_gmail_search",
                data={} if has_error else data,
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="google_gmail_search",
                error=str(e),
            )

    async def _execute_calendar(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue ricerca in Calendar."""
        from me4brain.domains.google_workspace.tools import google_api

        # Determina tipo: upcoming o search
        query_lower = query.lower()
        is_upcoming = any(
            w in query_lower for w in ["prossim", "oggi", "domani", "settimana", "upcoming"]
        )

        try:
            if is_upcoming:
                data = await google_api.calendar_upcoming(days=365)  # 1 anno per report
            else:
                search_term = self._extract_search_term(query)
                data = await google_api.calendar_list_events(query=search_term)

            has_error = bool(data.get("error"))
            return DomainExecutionResult(
                success=not has_error,
                domain=self.domain_name,
                tool_name="google_calendar_upcoming" if is_upcoming else "google_calendar_search",
                data={} if has_error else data,
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="google_calendar",
                error=str(e),
            )

    async def _execute_docs(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue lettura Google Docs (via Drive search)."""
        from me4brain.domains.google_workspace.tools import google_api

        search_term = self._extract_search_term(query)

        try:
            # Cerca doc su Drive poi leggi contenuto
            data = await google_api.drive_search(
                query=search_term,
                mime_type="application/vnd.google-apps.document",
            )
            has_error = bool(data.get("error"))
            return DomainExecutionResult(
                success=not has_error,
                domain=self.domain_name,
                tool_name="google_docs_search",
                data={} if has_error else data,
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="google_docs_search",
                error=str(e),
            )

    async def _execute_sheets(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue ricerca Google Sheets (via Drive search)."""
        from me4brain.domains.google_workspace.tools import google_api

        search_term = self._extract_search_term(query)

        try:
            data = await google_api.drive_search(
                query=search_term,
                mime_type="application/vnd.google-apps.spreadsheet",
            )
            has_error = bool(data.get("error"))
            return DomainExecutionResult(
                success=not has_error,
                domain=self.domain_name,
                tool_name="google_sheets_search",
                data={} if has_error else data,
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="google_sheets_search",
                error=str(e),
            )

    async def _execute_multi_service(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Esegue ricerca su più servizi Google in parallelo."""
        import asyncio

        from me4brain.domains.google_workspace.tools import google_api

        search_term = self._extract_search_term(query)

        # Esegui Drive, Gmail, Calendar, Meet in parallelo
        drive_task = google_api.drive_search(query=search_term)
        gmail_task = google_api.gmail_search(query=search_term)
        calendar_task = google_api.calendar_upcoming(days=180)  # 6 mesi per report
        meet_task = google_api.meet_list_conferences(max_results=50)  # NUOVO

        drive_result, gmail_result, calendar_result, meet_result = await asyncio.gather(
            drive_task,
            gmail_task,
            calendar_task,
            meet_task,
            return_exceptions=True,
        )

        results = []

        # Process Drive
        if isinstance(drive_result, dict) and not drive_result.get("error"):
            results.append(
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="google_drive_search",
                    data=drive_result,
                )
            )

        # Process Gmail
        if isinstance(gmail_result, dict) and not gmail_result.get("error"):
            results.append(
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="google_gmail_search",
                    data=gmail_result,
                )
            )

        # Process Calendar
        if isinstance(calendar_result, dict) and not calendar_result.get("error"):
            results.append(
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="google_calendar_upcoming",
                    data=calendar_result,
                )
            )

        # Process Meet - NUOVO
        if isinstance(meet_result, dict) and not meet_result.get("error"):
            results.append(
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="google_meet_list_conferences",
                    data=meet_result,
                )
            )

        return (
            results
            if results
            else [
                DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name="google_workspace_multi",
                    error="No results from any Google service",
                )
            ]
        )

    def _extract_search_term(self, query: str) -> str:
        """Estrae termine di ricerca dalla query utente.

        Miglioria: mantiene nomi propri (maiuscole iniziali) e acronimi.
        """
        # Stopwords comuni - solo articoli e preposizioni
        stopwords = {
            "cerca",
            "file",
            "su",
            "drive",
            "email",
            "gmail",
            "calendario",
            "calendar",
            "documento",
            "documenti",
            "mostrami",
            "leggi",
            "trova",
            "in",
            "il",
            "la",
            "le",
            "i",
            "di",
            "da",
            "per",
            "con",
            "che",
            "cosa",
            "ho",
            "oggi",
            "domani",
            "questa",
            "settimana",
            "analizza",
            "report",
            "attività",
            "relativi",
            "relative",
            "informazioni",
        }

        words = query.split()  # Mantieni case originale
        filtered = []

        for word in words:
            word_lower = word.lower()

            # Mantieni sempre:
            # 1. Acronimi (tutto maiuscolo, es. ANCI, UDP)
            # 2. Nomi propri (iniziale maiuscola, es. Allumiere, Tolfa)
            # 3. Parole lunghe non in stopwords
            is_acronym = word.isupper() and len(word) >= 2
            is_proper_noun = word[0].isupper() and not word.isupper() and len(word) > 2
            is_significant = word_lower not in stopwords and len(word) > 2

            if is_acronym or is_proper_noun or is_significant:
                filtered.append(word)

        return " ".join(filtered) if filtered else query

    def handles_service(self, service_name: str) -> bool:
        """Verifica se questo handler gestisce il servizio."""
        return service_name in self.HANDLED_SERVICES

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Esegue tool Google specificO per nome."""
        from me4brain.domains.google_workspace.tools import google_api

        logger.info(
            "google_workspace_execute_tool",
            tool_name=tool_name,
            arguments=arguments,
        )

        return await google_api.execute_tool(tool_name, arguments)
