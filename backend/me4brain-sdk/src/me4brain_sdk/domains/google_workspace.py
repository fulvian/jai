from __future__ import annotations

"""Google Workspace Domain - Calendar, Gmail, Drive, Sheets integration."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class CalendarEvent(BaseModel):
    """Google Calendar event."""

    id: str
    title: str
    start: datetime
    end: datetime
    description: str | None = None
    location: str | None = None
    attendees: list[str] = Field(default_factory=list)
    link: str | None = None


class EmailMessage(BaseModel):
    """Gmail message."""

    id: str
    thread_id: str
    from_email: str
    to_emails: list[str] = Field(default_factory=list)
    subject: str
    snippet: str
    date: datetime
    is_read: bool = True
    labels: list[str] = Field(default_factory=list)


class DriveFile(BaseModel):
    """Google Drive file."""

    id: str
    name: str
    mime_type: str
    size_bytes: int | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    web_link: str | None = None
    parents: list[str] = Field(default_factory=list)


class GoogleWorkspaceDomain(BaseDomain):
    """Google Workspace integration - Calendar, Gmail, Drive, Sheets.

    Requires Google OAuth credentials configured in Me4BrAIn.

    Example:
        # List calendar events
        events = await client.domains.google_workspace.calendar_events(
            max_results=10,
        )

        # Send email
        await client.domains.google_workspace.send_email(
            to=["user@example.com"],
            subject="Hello",
            body="World",
        )
    """

    @property
    def domain_name(self) -> str:
        return "google_workspace"

    # =========================================================================
    # Calendar
    # =========================================================================

    async def calendar_events(
        self,
        max_results: int = 10,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        calendar_id: str = "primary",
    ) -> list[CalendarEvent]:
        """List upcoming calendar events.

        Args:
            max_results: Maximum events to return
            time_min: Start time filter
            time_max: End time filter
            calendar_id: Calendar ID (default: primary)

        Returns:
            List of calendar events
        """
        params: dict[str, Any] = {
            "max_results": max_results,
            "calendar_id": calendar_id,
        }
        if time_min:
            params["time_min"] = time_min.isoformat()
        if time_max:
            params["time_max"] = time_max.isoformat()

        result = await self._execute_tool("calendar_list_events", params)
        events = result.get("result", {}).get("events", [])
        return [CalendarEvent.model_validate(e) for e in events]

    async def calendar_create_event(
        self,
        title: str,
        start: datetime,
        end: datetime,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> CalendarEvent:
        """Create a calendar event.

        Args:
            title: Event title
            start: Start time
            end: End time
            description: Event description
            location: Event location
            attendees: List of attendee emails
            calendar_id: Calendar ID

        Returns:
            Created event
        """
        result = await self._execute_tool(
            "calendar_create_event",
            {
                "title": title,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "description": description,
                "location": location,
                "attendees": attendees or [],
                "calendar_id": calendar_id,
            },
        )
        return CalendarEvent.model_validate(result.get("result", {}))

    # =========================================================================
    # Gmail
    # =========================================================================

    async def gmail_search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[EmailMessage]:
        """Search Gmail messages.

        Args:
            query: Gmail search query
            max_results: Maximum results

        Returns:
            List of messages
        """
        result = await self._execute_tool(
            "gmail_search",
            {"query": query, "max_results": max_results},
        )
        messages = result.get("result", {}).get("messages", [])
        return [EmailMessage.model_validate(m) for m in messages]

    async def gmail_send(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """Send an email.

        Args:
            to: Recipient emails
            subject: Email subject
            body: Email body
            cc: CC recipients
            bcc: BCC recipients
            is_html: Whether body is HTML

        Returns:
            Send result with message ID
        """
        result = await self._execute_tool(
            "gmail_send",
            {
                "to": to,
                "subject": subject,
                "body": body,
                "cc": cc,
                "bcc": bcc,
                "is_html": is_html,
            },
        )
        return result.get("result", {})

    async def gmail_read(self, message_id: str) -> dict[str, Any]:
        """Read email content.

        Args:
            message_id: Message ID

        Returns:
            Full email content
        """
        result = await self._execute_tool("gmail_read", {"message_id": message_id})
        return result.get("result", {})

    # =========================================================================
    # Drive
    # =========================================================================

    async def drive_search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[DriveFile]:
        """Search Drive files.

        Args:
            query: Search query
            max_results: Maximum results

        Returns:
            List of files
        """
        result = await self._execute_tool(
            "drive_search",
            {"query": query, "max_results": max_results},
        )
        files = result.get("result", {}).get("files", [])
        return [DriveFile.model_validate(f) for f in files]

    async def drive_list(
        self,
        folder_id: str = "root",
        max_results: int = 20,
    ) -> list[DriveFile]:
        """List files in a folder.

        Args:
            folder_id: Folder ID (default: root)
            max_results: Maximum results

        Returns:
            List of files
        """
        result = await self._execute_tool(
            "drive_list",
            {"folder_id": folder_id, "max_results": max_results},
        )
        files = result.get("result", {}).get("files", [])
        return [DriveFile.model_validate(f) for f in files]

    # =========================================================================
    # Sheets
    # =========================================================================

    async def sheets_read(
        self,
        spreadsheet_id: str,
        range: str = "Sheet1",
    ) -> list[list[Any]]:
        """Read data from a spreadsheet.

        Args:
            spreadsheet_id: Spreadsheet ID
            range: Range to read (e.g., "Sheet1!A1:D10")

        Returns:
            2D array of cell values
        """
        result = await self._execute_tool(
            "sheets_read",
            {"spreadsheet_id": spreadsheet_id, "range": range},
        )
        return result.get("result", {}).get("values", [])

    async def sheets_write(
        self,
        spreadsheet_id: str,
        range: str,
        values: list[list[Any]],
    ) -> dict[str, Any]:
        """Write data to a spreadsheet.

        Args:
            spreadsheet_id: Spreadsheet ID
            range: Range to write (e.g., "Sheet1!A1")
            values: 2D array of values

        Returns:
            Write result
        """
        result = await self._execute_tool(
            "sheets_write",
            {
                "spreadsheet_id": spreadsheet_id,
                "range": range,
                "values": values,
            },
        )
        return result.get("result", {})
