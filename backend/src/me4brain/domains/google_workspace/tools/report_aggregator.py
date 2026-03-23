"""Workspace Report Aggregator Tool.

Multi-source aggregation tool that queries Drive, Gmail, Calendar, Meet
in parallel and generates a structured report.

Ispirato al pattern CrewAI con agent specializzati per ogni fonte.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def workspace_report_aggregator(
    project_keyword: str,
    date_from: str | None = None,
    date_to: str | None = None,
    include_drive: bool = True,
    include_gmail: bool = True,
    include_calendar: bool = True,
    include_meet: bool = True,
) -> dict[str, Any]:
    """Genera un report aggregato multi-source per un progetto.

    Esegue ricerche parallele su Drive, Gmail, Calendar, Meet e aggrega
    i risultati in un report strutturato.

    Args:
        project_keyword: Keyword progetto da cercare (es. "ANCI", "UDP Sicilia")
        date_from: Data inizio ricerca (YYYY-MM-DD), default 6 mesi fa
        date_to: Data fine ricerca (YYYY-MM-DD), default oggi
        include_drive: Includi ricerca Drive
        include_gmail: Includi ricerca Gmail
        include_calendar: Includi ricerca Calendar
        include_meet: Includi ricerca Meet

    Returns:
        dict con report strutturato per sezione
    """
    from me4brain.domains.google_workspace.tools import google_api

    # Default date range: 6 mesi
    now = datetime.now(UTC)
    if not date_to:
        date_to = now.strftime("%Y-%m-%d")
    if not date_from:
        date_from = (now - timedelta(days=180)).strftime("%Y-%m-%d")

    logger.info(
        "workspace_report_started",
        project=project_keyword,
        date_from=date_from,
        date_to=date_to,
    )

    # Prepara task paralleli
    tasks = {}

    # Drive: ricerca file con keyword
    if include_drive:
        drive_query = (
            f"(name contains '{project_keyword}' OR fullText contains '{project_keyword}')"
        )
        tasks["drive"] = google_api.drive_search(query=drive_query, max_results=100)

    # Gmail: ricerca email con keyword
    if include_gmail:
        gmail_query = f"(subject:{project_keyword} OR from:{project_keyword} OR to:{project_keyword}) after:{date_from.replace('-', '/')}"
        tasks["gmail"] = google_api.gmail_search(query=gmail_query, max_results=100)

    # Calendar: eventi nel range
    if include_calendar:
        time_min = f"{date_from}T00:00:00Z"
        time_max = f"{date_to}T23:59:59Z"
        tasks["calendar"] = google_api.calendar_list_events(
            query=project_keyword,
            time_min=time_min,
            time_max=time_max,
            max_results=100,
        )

    # Meet: conferenze recenti
    if include_meet:
        tasks["meet"] = google_api.meet_list_conferences(max_results=100)

    # Esegui in parallelo
    results = {}
    if tasks:
        task_names = list(tasks.keys())
        task_coroutines = list(tasks.values())

        gathered = await asyncio.gather(*task_coroutines, return_exceptions=True)

        for name, result in zip(task_names, gathered, strict=False):
            if isinstance(result, Exception):
                logger.warning(f"{name}_aggregation_failed", error=str(result))
                results[name] = {"error": str(result), "items": []}
            elif isinstance(result, dict) and result.get("error"):
                results[name] = {"error": result["error"], "items": []}
            else:
                results[name] = result

    # Aggrega in report strutturato
    report = {
        "project": project_keyword,
        "date_range": {"from": date_from, "to": date_to},
        "generated_at": now.isoformat(),
        "sections": {},
        "summary": {},
    }

    # Drive section
    if "drive" in results:
        drive_data = results["drive"]
        files = drive_data.get("files", [])
        report["sections"]["documents"] = {
            "count": len(files),
            "items": files[:50],  # Limit per output
        }
        report["summary"]["documents_count"] = len(files)

    # Gmail section
    if "gmail" in results:
        gmail_data = results["gmail"]
        emails = gmail_data.get("emails", [])
        report["sections"]["emails"] = {
            "count": len(emails),
            "items": emails[:50],
        }
        report["summary"]["emails_count"] = len(emails)

    # Calendar section
    if "calendar" in results:
        calendar_data = results["calendar"]
        events = calendar_data.get("events", [])
        report["sections"]["events"] = {
            "count": len(events),
            "items": events[:50],
        }
        report["summary"]["events_count"] = len(events)

    # Meet section - filtra per data e keyword
    if "meet" in results:
        meet_data = results["meet"]
        conferences = meet_data.get("conferences", [])

        # Filtra conferenze per periodo e keyword
        filtered_conferences = []
        for conf in conferences:
            conf.get("date", "")
            conf_title = conf.get("title", "").lower()

            # Filtro per keyword nel titolo
            if project_keyword.lower() in conf_title or not project_keyword:
                filtered_conferences.append(conf)

        report["sections"]["calls"] = {
            "count": len(filtered_conferences),
            "items": filtered_conferences[:50],
        }
        report["summary"]["calls_count"] = len(filtered_conferences)

    # Calcola totali
    total_items = sum(
        [
            report["summary"].get("documents_count", 0),
            report["summary"].get("emails_count", 0),
            report["summary"].get("events_count", 0),
            report["summary"].get("calls_count", 0),
        ]
    )
    report["summary"]["total_items"] = total_items

    logger.info(
        "workspace_report_completed",
        project=project_keyword,
        total_items=total_items,
    )

    return report


# Tool definition per registrazione
TOOL_DEFINITION = {
    "name": "google_workspace_report",
    "description": """Genera un report aggregato multi-source per un progetto.

Esegue ricerche parallele su Google Drive, Gmail, Calendar e Meet,
aggregando i risultati in un report strutturato con sezioni:
- documents: File e documenti su Drive
- emails: Email relative al progetto
- events: Eventi calendario
- calls: Conferenze Meet

Ideale per generare report di attività su progetti specifici.""",
    "parameters": {
        "type": "object",
        "properties": {
            "project_keyword": {
                "type": "string",
                "description": "Keyword del progetto da cercare (es. 'ANCI', 'UDP Sicilia', 'Progetto X')",
            },
            "date_from": {
                "type": "string",
                "description": "Data inizio ricerca formato YYYY-MM-DD (default: 6 mesi fa)",
            },
            "date_to": {
                "type": "string",
                "description": "Data fine ricerca formato YYYY-MM-DD (default: oggi)",
            },
            "include_drive": {
                "type": "boolean",
                "description": "Includi ricerca Google Drive (default: true)",
                "default": True,
            },
            "include_gmail": {
                "type": "boolean",
                "description": "Includi ricerca Gmail (default: true)",
                "default": True,
            },
            "include_calendar": {
                "type": "boolean",
                "description": "Includi ricerca Calendar (default: true)",
                "default": True,
            },
            "include_meet": {
                "type": "boolean",
                "description": "Includi ricerca Meet (default: true)",
                "default": True,
            },
        },
        "required": ["project_keyword"],
    },
}
