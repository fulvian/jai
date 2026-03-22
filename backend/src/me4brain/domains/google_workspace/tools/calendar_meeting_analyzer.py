"""Calendar Meeting Analyzer Tool.

Analizza eventi calendario per trovare tutti i meeting (Google Meet, Zoom, Teams, etc.)
in un range temporale, non solo quelli registrati da Google Meet.
"""

import re
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def calendar_analyze_meetings(
    start_date: str,
    end_date: str,
    include_all_platforms: bool = True,
    min_duration_minutes: int = 5,
) -> dict[str, Any]:
    """Analizza eventi calendario per trovare tutti i meeting in un range temporale.

    Args:
        start_date: Data inizio (formato ISO: YYYY-MM-DD)
        end_date: Data fine (formato ISO: YYYY-MM-DD)
        include_all_platforms: Include meeting non-Google Meet (Zoom, Teams, etc.)
        min_duration_minutes: Durata minima meeting da includere

    Returns:
        Dict con analisi meeting completa
    """
    from me4brain.integrations.google_workspace import get_google_workspace_service

    service = get_google_workspace_service()
    if not service:
        return {"error": "Google Workspace not configured", "source": "Google Calendar"}

    try:
        # Ottieni tutti gli eventi nel range
        time_min = f"{start_date}T00:00:00Z"
        time_max = f"{end_date}T23:59:59Z"

        events = await service.calendar_list_events(
            time_min=time_min,
            time_max=time_max,
            max_results=100,
        )

        meetings = []
        platform_stats = {
            "google_meet": 0,
            "zoom": 0,
            "teams": 0,
            "other": 0,
            "unknown": 0,
        }

        for event in events:
            # Skip eventi all-day (non hanno dateTime)
            if "dateTime" not in event.get("start", {}):
                continue

            # Calcola durata
            start_dt = datetime.fromisoformat(event["start"]["dateTime"].replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(event["end"]["dateTime"].replace("Z", "+00:00"))
            duration_minutes = (end_dt - start_dt).total_seconds() / 60

            if duration_minutes < min_duration_minutes:
                continue

            # Detect piattaforma meeting
            platform = _detect_meeting_platform(event)
            platform_stats[platform] += 1

            # Estrai partecipanti
            attendees = [
                {
                    "email": a.get("email"),
                    "name": a.get("displayName", a.get("email")),
                    "response": a.get("responseStatus"),
                }
                for a in event.get("attendees", [])
            ]

            meetings.append(
                {
                    "id": event.get("id"),
                    "summary": event.get("summary", "No Title"),
                    "start": start_dt.isoformat(),
                    "end": end_dt.isoformat(),
                    "duration_minutes": int(duration_minutes),
                    "platform": platform,
                    "attendees": attendees,
                    "attendee_count": len(attendees),
                    "location": event.get("location"),
                    "meeting_link": _extract_meeting_link(event),
                    "description": event.get("description", "")[:200],  # Primi 200 char
                }
            )

        # Ordina per durata (più lunghi prima)
        meetings.sort(key=lambda x: x["duration_minutes"], reverse=True)

        return {
            "date_range": {"start": start_date, "end": end_date},
            "total_meetings": len(meetings),
            "platform_breakdown": platform_stats,
            "meetings": meetings,
            "top_3_longest": meetings[:3] if len(meetings) >= 3 else meetings,
            "source": "Google Calendar",
        }

    except Exception as e:
        logger.error("calendar_analyze_meetings_error", error=str(e))
        return {"error": str(e), "source": "Google Calendar"}


def _detect_meeting_platform(event: dict[str, Any]) -> str:
    """Rileva piattaforma meeting dall'evento calendario."""
    description = event.get("description", "").lower()
    location = event.get("location", "").lower()
    conference_data = event.get("conferenceData", {})

    # Check conferenceData (Google Meet nativo)
    if conference_data:
        entry_points = conference_data.get("entryPoints", [])
        for entry in entry_points:
            if entry.get("entryPointType") == "video":
                uri = entry.get("uri", "").lower()
                if "meet.google.com" in uri:
                    return "google_meet"

    # Check description e location per link meeting
    combined_text = f"{description} {location}"

    # Google Meet
    if "meet.google.com" in combined_text:
        return "google_meet"

    # Zoom
    if "zoom.us" in combined_text or "zoom.com" in combined_text:
        return "zoom"

    # Microsoft Teams
    if "teams.microsoft.com" in combined_text or "teams.live.com" in combined_text:
        return "teams"

    # Altri servizi comuni
    meeting_patterns = [
        (r"webex\.com", "other"),
        (r"gotomeeting\.com", "other"),
        (r"bluejeans\.com", "other"),
        (r"whereby\.com", "other"),
    ]

    for pattern, platform in meeting_patterns:
        if re.search(pattern, combined_text):
            return platform

    # Se ha partecipanti ma nessun link riconosciuto
    if event.get("attendees") and len(event.get("attendees", [])) > 1:
        return "unknown"

    return "unknown"


def _extract_meeting_link(event: dict[str, Any]) -> str | None:
    """Estrae link meeting dall'evento."""
    # Check conferenceData (Google Meet nativo)
    conference_data = event.get("conferenceData", {})
    if conference_data:
        entry_points = conference_data.get("entryPoints", [])
        for entry in entry_points:
            if entry.get("entryPointType") == "video":
                return entry.get("uri")

    # Check description e location
    description = event.get("description", "")
    location = event.get("location", "")
    combined_text = f"{description} {location}"

    # Pattern URL generico
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, combined_text)

    # Filtra per domini meeting noti
    meeting_domains = [
        "meet.google.com",
        "zoom.us",
        "zoom.com",
        "teams.microsoft.com",
        "teams.live.com",
        "webex.com",
        "gotomeeting.com",
        "bluejeans.com",
        "whereby.com",
    ]

    for url in urls:
        if any(domain in url.lower() for domain in meeting_domains):
            return url

    return None


# =============================================================================
# Tool Definitions & Executors
# =============================================================================

from me4brain.engine.types import ToolDefinition, ToolParameter

def get_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="calendar_analyze_meetings",
            description="Analyzes calendar events to find and list all meetings from various platforms (Google Meet, Zoom, Teams, Webex, etc.) in a given time range. Essential for meeting reports and productivity analysis.",
            parameters={
                "start_date": ToolParameter(
                    type="string",
                    description="Start date (ISO format: YYYY-MM-DD)",
                    required=True,
                ),
                "end_date": ToolParameter(
                    type="string",
                    description="End date (ISO format: YYYY-MM-DD)",
                    required=True,
                ),
                "include_all_platforms": ToolParameter(
                    type="boolean",
                    description="If True, includes non-Google Meet platforms (default: True)",
                    required=False,
                ),
                "min_duration_minutes": ToolParameter(
                    type="integer",
                    description="Minimum duration in minutes to include (default: 5)",
                    required=False,
                ),
            },
            domain="scheduling",
            category="calendar",
        )
    ]

def get_executors() -> dict:
    return {"calendar_analyze_meetings": calendar_analyze_meetings}
