"""Google Workspace API Integration.

Unified wrapper for Google Workspace APIs:
- Google Drive: File/folder management
- Gmail: Email reading and sending
- Google Calendar: Event management
- Google Sheets: Spreadsheet operations (optional)

Uses OAuth 2.0 for user authorization.
Based on consultos/app/services/drive.py pattern.
"""

import io
import time
import random
from pathlib import Path
from typing import Any

import structlog
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from googleapiclient.errors import HttpError

from me4brain.config import get_settings

logger = structlog.get_logger(__name__)

# OAuth Scopes for full Workspace integration
# ALLINEATO A: scripts/google_oauth_setup.py
SCOPES = [
    # Drive
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
    # Gmail
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    # Calendar
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
    # Meet - read conference records, transcripts, recordings
    "https://www.googleapis.com/auth/meetings.space.readonly",
    "https://www.googleapis.com/auth/drive.meet.readonly",
    # Docs
    "https://www.googleapis.com/auth/documents",
    # Sheets
    "https://www.googleapis.com/auth/spreadsheets",
    # Slides
    "https://www.googleapis.com/auth/presentations",
    # Classroom
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
    # Forms
    "https://www.googleapis.com/auth/forms.body.readonly",
    "https://www.googleapis.com/auth/forms.responses.readonly",
]

# Token paths - cerca in ordine di priorità
TOKEN_PATHS = [
    Path("data/google_token.json"),  # Standard path
    Path("token.json"),  # Root fallback (oauth_setup.py output)
    Path.home() / ".me4brain" / "google_token.json",  # User home
]
CREDENTIALS_PATH = Path("data/google_credentials.json")

# Pre-emptive refresh: rinnova il token 5 minuti prima della scadenza
PREEMPTIVE_REFRESH_SECONDS = 300


def _find_token_file() -> Path | None:
    """Trova il file token esistente cercando in più locations."""
    for path in TOKEN_PATHS:
        if path.exists():
            return path
    return None


class GoogleWorkspaceService:
    """Unified Google Workspace API Service.

    Implementa auto-refresh robusto con:
    - Retry con exponential backoff
    - Pre-emptive refresh prima della scadenza
    - Fallback multiple token locations
    - Salvataggio automatico dopo ogni refresh
    """

    def __init__(self, credentials: Credentials | None = None):
        """Initialize with credentials or load from file."""
        self.credentials = credentials or self._load_or_refresh_credentials()
        self._drive = None
        self._gmail = None
        self._calendar = None
        self._meet = None
        self._token_path = _find_token_file() or TOKEN_PATHS[0]

    def _load_or_refresh_credentials(self) -> Credentials | None:
        """Load existing credentials with robust refresh logic.

        Strategia:
        1. Cerca token in multiple locations
        2. Se valido, usa direttamente
        3. Se sta per scadere (< 5 min), pre-refresh
        4. Se scaduto con refresh_token, rinnova con retry
        5. Se tutto fallisce, guida l'utente al ri-setup
        """
        token_path = _find_token_file()

        if not token_path:
            logger.warning(
                "google_token_not_found",
                searched_paths=[str(p) for p in TOKEN_PATHS],
                hint="Run: uv run python scripts/google_oauth_setup.py",
            )
            return None

        logger.info("google_token_found", path=str(token_path))

        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as e:
            logger.error("google_token_parse_failed", path=str(token_path), error=str(e))
            return None

        if not creds:
            logger.error("google_credentials_empty", path=str(token_path))
            return None

        # ===== CASO 1: Token valido =====
        if creds.valid:
            # Pre-emptive refresh se sta per scadere
            if creds.expiry:
                from datetime import datetime, timedelta, timezone

                now = datetime.now(timezone.utc)
                expires_in = (creds.expiry.replace(tzinfo=timezone.utc) - now).total_seconds()

                if expires_in < PREEMPTIVE_REFRESH_SECONDS and creds.refresh_token:
                    logger.info(
                        "google_preemptive_refresh",
                        expires_in_seconds=expires_in,
                    )
                    return self._refresh_with_retry(creds, token_path)

            logger.info("google_credentials_valid")
            return creds

        # ===== CASO 2: Token scaduto con refresh_token =====
        if creds.expired and creds.refresh_token:
            logger.info("google_token_expired_refreshing")
            return self._refresh_with_retry(creds, token_path)

        # ===== CASO 3: Token scaduto senza refresh_token =====
        logger.error(
            "google_token_expired_no_refresh",
            hint="Token scaduto senza refresh_token. L'app GCP è in Testing mode?",
            action="Run: uv run python scripts/google_oauth_setup.py",
            gcp_fix="Pubblica l'app in Production mode nella Google Cloud Console",
        )
        return None

    def _refresh_with_retry(
        self,
        creds: Credentials,
        token_path: Path,
        max_retries: int = 3,
    ) -> Credentials | None:
        """Refresh credentials with exponential backoff retry.

        Args:
            creds: Credentials da rinnovare
            token_path: Path dove salvare il token aggiornato
            max_retries: Numero massimo di tentativi

        Returns:
            Credentials rinnovate o None se fallisce
        """
        for attempt in range(max_retries):
            try:
                # 1. Refresh in-memory (Google API call)
                creds.refresh(Request())

                # 2. Attempt disk save (Non-blocking resilience)
                try:
                    self._save_credentials_to_path(creds, token_path)
                except Exception as save_err:
                    logger.error(
                        "google_token_save_failed_resilience_active",
                        error=str(save_err),
                        path=str(token_path),
                        hint="Check file permissions. Continuing with in-memory token.",
                    )

                logger.info(
                    "google_token_refreshed",
                    attempt=attempt + 1,
                    new_expiry=creds.expiry.isoformat() if creds.expiry else None,
                )
                return creds

            except Exception as e:
                error_msg = str(e).lower()

                # Token revocato o invalido - richiede re-auth
                if "invalid_grant" in error_msg or "token has been revoked" in error_msg:
                    logger.error(
                        "google_token_revoked",
                        error=str(e),
                        action="Token revocato. Run: uv run python scripts/google_oauth_setup.py",
                    )
                    return None

                # Retry con backoff
                if attempt < max_retries - 1:
                    delay = (2**attempt) + random.random()
                    logger.warning(
                        "google_refresh_retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay_seconds=delay,
                        error=str(e),
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "google_refresh_failed",
                        attempts=max_retries,
                        error=str(e),
                    )

        return None

    def _save_credentials(self, creds: Credentials) -> None:
        """Save credentials to default token file."""
        self._save_credentials_to_path(creds, self._token_path)

    def _save_credentials_to_path(self, creds: Credentials, path: Path) -> None:
        """Save credentials to specified path."""
        path.parent.mkdir(exist_ok=True, parents=True)
        with open(path, "w") as f:
            f.write(creds.to_json())
        logger.info("google_credentials_saved", path=str(path))

    def _get_google_service(self, service_name: str, version: str):
        """Get a Google API service by name.

        This is a generic method to access any Google API service.
        Supports: docs, sheets, slides, forms, classroom, calendar, gmail, drive, etc.

        Args:
            service_name: Name of the service (e.g. 'docs', 'sheets', 'slides')
            version: API version (e.g. 'v1', 'v3')

        Returns:
            Google API service object
        """
        if not self.credentials:
            raise ValueError("Google credentials not configured")
        return build(service_name, version, credentials=self.credentials)

    # =========================================================================
    # DRIVE API
    # =========================================================================

    @property
    def drive(self):
        """Lazy-load Drive service."""
        if not self._drive and self.credentials:
            self._drive = build("drive", "v3", credentials=self.credentials)
        return self._drive

    async def drive_list_files(
        self,
        folder_id: str | None = None,
        query: str | None = None,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """List files in Drive, optionally filtered by folder or query."""
        q_parts = []
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        if query:
            q_parts.append(query)
        q_parts.append("trashed = false")
        full_query = " and ".join(q_parts)

        return await self._execute_with_backoff(
            self.drive.files().list(
                q=full_query,
                pageSize=max_results,
                fields="files(id, name, mimeType, webViewLink, modifiedTime, size)",
            )
        )

    async def search(
        self,
        query: str,
        max_results: int = 20,
        folder_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search files in Google Drive by content (fullText search).

        This searches in file content, not just file names.
        Uses Google Drive's fullText search capability.

        Args:
            query: Search terms to find in file content
            max_results: Maximum number of results
            folder_id: Optional folder ID to restrict search scope

        Returns:
            List of matching files with metadata
        """
        # UNIVERSAL QUERY SANITIZER - max 1800 chars per Google Drive limits
        safe_query = self._sanitize_drive_query(query)

        # Build query with optional folder restriction
        q_parts = [safe_query, "trashed = false"]
        if folder_id:
            q_parts.append(f"'{folder_id}' in parents")
        q = " and ".join(q_parts)

        logger.info(
            "drive_search",
            query=query[:100],
            drive_query=q[:200],
            folder_id=folder_id,
            original_len=len(query),
            sanitized_len=len(q),
        )

        result = await self._execute_with_backoff(
            self.drive.files().list(
                q=q,
                pageSize=max_results,
                fields="files(id, name, mimeType, webViewLink, modifiedTime, size)",
            )
        )

        files = result.get("files", [])
        logger.info("drive_search_results", query=query[:50], count=len(files), folder_id=folder_id)

        return {"files": files, "query": query, "count": len(files), "folder_id": folder_id}

    def _sanitize_drive_query(self, query: str, max_length: int = 1800) -> str:
        """Universal Google Drive query sanitizer & truncator.

        Handles:
        - SMART keyword extraction (prioritizes proper nouns/entities)
        - Length truncation (max 3-5 keywords for fullText search)
        - Special character escaping (quotes, backslashes)
        - Fallback to name-only search for very long/complex queries

        Args:
            query: Raw search query from user
            max_length: Max safe length for Drive API (default 1800, Google limit ~8192)

        Returns:
            Safe fullText query string for Drive API

        NOTE: Google Drive fullText search works best with 1-3 short keywords.
        Long phrases (>5 words) often return 0 results.
        """
        import re

        # Step 1: Extract meaningful keywords (prioritize proper nouns and entities)
        words = query.split()

        # Filter: keep words with first letter uppercase (likely names/entities)
        # or words > 4 chars that aren't common stopwords
        stopwords = {
            "vorrei",
            "devo",
            "questo",
            "questa",
            "come",
            "cosa",
            "dove",
            "quando",
            "perché",
            "quale",
            "quali",
            "tutti",
            "tutte",
            "alcune",
            "alcuni",
            "nella",
            "nella",
            "della",
            "dello",
            "degli",
            "delle",
            "from",
            "with",
            "that",
            "this",
            "have",
            "been",
            "would",
            "could",
            "should",
            "about",
            "there",
            "where",
            "which",
            "their",
            "what",
            "your",
            "will",
            "into",
            "analizza",
            "individua",
            "cerca",
            "trova",
            "leggi",
            "scrivi",
            "relazione",
            "attività",
            "consulente",
            "progetto",
            "riferimento",
        }

        keywords = []

        # Priority 0: Exact phrases (quoted strings) - SOTA 2026 Resilience
        # If the LLM quoted an entity, prioritize it exactly
        quoted_phrases = re.findall(r'"([^"]*)"', query)
        for phrase in quoted_phrases:
            if phrase and len(phrase) > 2:
                keywords.append(f'"{phrase}"')

        # Priority 1: Capitalized words (likely names, organizations, places)
        for word in words:
            # Clean word from punctuation
            clean_word = re.sub(r"^[^\w]+|[^\w]+$", "", word)
            if not clean_word:
                continue

            # Check if starts with uppercase (proper noun)
            if clean_word[0].isupper() and clean_word.lower() not in stopwords:
                if clean_word not in keywords:
                    keywords.append(clean_word)

        # Priority 2: Add long words (>5 chars) not in stopwords
        if len(keywords) < 5:
            for word in words:
                clean_word = re.sub(r"^[^\w]+|[^\w]+$", "", word)
                if (
                    clean_word
                    and len(clean_word) > 5
                    and clean_word.lower() not in stopwords
                    and clean_word not in keywords
                ):
                    keywords.append(clean_word)
                    if len(keywords) >= 5:
                        break

        # Step 2: Build query from top 7 keywords/phrases
        if keywords:
            search_terms = " ".join(keywords[:7])
        else:
            # No good keywords found, use first 3 words
            search_terms = " ".join(words[:3])

        # Step 3: Escape special characters
        safe_query = search_terms.replace("\\", "\\\\").replace("'", "\\'")

        # Step 4: Build Drive API query
        if len(safe_query) <= max_length:
            logger.info(
                "drive_search",
                query=query[:100],
                sanitized_len=len(safe_query),
                original_len=len(query),
                drive_query=f"fullText contains '{safe_query}'",
            )
            return f"fullText contains '{safe_query}' and trashed = false"

        # Step 5: Nuclear fallback - name contains first word
        first_word = keywords[0] if keywords else words[0] if words else ""
        safe_first = first_word.replace("\\", "\\\\").replace("'", "\\'")
        logger.warning(
            "drive_query_fallback_name",
            original_len=len(query),
            fallback="name contains",
        )
        return f"name contains '{safe_first}' and trashed = false"

    async def drive_get_file(self, file_id: str) -> dict[str, Any]:
        """Get file metadata."""
        return await self._execute_with_backoff(
            self.drive.files().get(
                fileId=file_id,
                fields="id, name, mimeType, webViewLink, parents, modifiedTime, size",
            )
        )

    async def drive_create_folder(self, name: str, parent_id: str | None = None) -> str:
        """Create a new folder."""
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]

        folder = await self._execute_with_backoff(
            self.drive.files().create(body=metadata, fields="id")
        )
        return folder.get("id")

    async def drive_download_file(self, file_id: str, mime_type: str) -> bytes:
        """Download file content."""
        if mime_type.startswith("application/vnd.google-apps."):
            export_mime = self._get_export_mime_type(mime_type)
            request = self.drive.files().export_media(fileId=file_id, mimeType=export_mime)
        else:
            request = self.drive.files().get_media(fileId=file_id)

        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return fh.getvalue()

    async def drive_upload_file(
        self,
        file_path: str | Path,
        name: str | None = None,
        parent_id: str | None = None,
        mime_type: str = "application/octet-stream",
    ) -> str:
        """Upload a file to Drive."""
        file_path = Path(file_path)
        metadata = {"name": name or file_path.name}
        if parent_id:
            metadata["parents"] = [parent_id]

        media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
        result = await self._execute_with_backoff(
            self.drive.files().create(body=metadata, media_body=media, fields="id, webViewLink")
        )
        return result

    # =========================================================================
    # GMAIL API
    # =========================================================================

    @property
    def gmail(self):
        """Lazy-load Gmail service."""
        if not self._gmail and self.credentials:
            self._gmail = build("gmail", "v1", credentials=self.credentials)
        return self._gmail

    async def gmail_list_messages(
        self,
        query: str | None = None,
        label_ids: list[str] | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """List Gmail messages matching query."""
        params = {
            "userId": "me",
            "maxResults": max_results,
        }
        if query:
            params["q"] = query
        if label_ids:
            params["labelIds"] = label_ids

        result = await self._execute_with_backoff(self.gmail.users().messages().list(**params))
        return result.get("messages", [])

    async def gmail_get_message(self, message_id: str, format: str = "full") -> dict[str, Any]:
        """Get a specific email message."""
        return await self._execute_with_backoff(
            self.gmail.users().messages().get(userId="me", id=message_id, format=format)
        )

    async def gmail_search(
        self,
        query: str,
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Search emails and return full message details."""
        messages = await self.gmail_list_messages(query=query, max_results=max_results)
        full_messages = []
        for msg in messages[:max_results]:
            full_msg = await self.gmail_get_message(msg["id"])
            full_messages.append(full_msg)
        return full_messages

    async def gmail_get_attachments(
        self,
        message_id: str,
    ) -> list[dict[str, Any]]:
        """Get attachments from a specific email.

        Args:
            message_id: Gmail message ID

        Returns:
            List of attachments with name, mimeType, size, and data (base64)
        """
        import base64

        message = await self.gmail_get_message(message_id)
        attachments = []

        def extract_attachments(parts: list) -> None:
            for part in parts:
                filename = part.get("filename", "")
                if filename:
                    attachment_id = part.get("body", {}).get("attachmentId")
                    if attachment_id:
                        # Fetch attachment data
                        att_data = (
                            self.gmail.users()
                            .messages()
                            .attachments()
                            .get(userId="me", messageId=message_id, id=attachment_id)
                            .execute()
                        )
                        attachments.append(
                            {
                                "attachmentId": attachment_id,  # Include ID for later retrieval
                                "filename": filename,
                                "mimeType": part.get("mimeType", ""),
                                "size": part.get("body", {}).get("size", 0),
                                "data": att_data.get("data", ""),  # base64
                            }
                        )
                # Recurse into nested parts
                if "parts" in part:
                    extract_attachments(part["parts"])

        payload = message.get("payload", {})
        if "parts" in payload:
            extract_attachments(payload["parts"])

        return attachments

    async def gmail_get_attachment_content(
        self,
        message_id: str,
        attachment_id: str,
        filename: str = "",
        mime_type: str = "",
    ) -> dict[str, Any]:
        """Download and return attachment content as bytes.

        Args:
            message_id: Gmail message ID
            attachment_id: Attachment ID from gmail_get_attachments
            filename: Original filename (for mime type inference)
            mime_type: MIME type (optional, can be inferred from filename)

        Returns:
            Dict with filename, mimeType, and raw bytes data
        """
        import base64
        import mimetypes

        # Download attachment
        att_response = (
            self.gmail.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )

        # Decode base64url to bytes
        data_b64 = att_response.get("data", "")
        raw_bytes = base64.urlsafe_b64decode(data_b64)

        # Infer mimeType from filename if not provided
        if not mime_type and filename:
            mime_type, _ = mimetypes.guess_type(filename)
            mime_type = mime_type or ""

        return {
            "filename": filename,
            "mimeType": mime_type,
            "size": len(raw_bytes),
            "data": raw_bytes,
        }

    # =========================================================================
    # MEET API
    # =========================================================================

    @property
    def meet(self):
        """Lazy-load Meet API service."""
        if not self._meet and self.credentials:
            self._meet = build("meet", "v2", credentials=self.credentials)
        return self._meet

    async def meet_list_conferences(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """List past Google Meet conferences.

        Args:
            time_min: Start of time range (ISO format)
            time_max: End of time range (ISO format)
            max_results: Maximum results to return

        Returns:
            List of conference records with participants
        """
        try:
            # Meet API - chiamata sincrona diretta
            result = self.meet.conferenceRecords().list(pageSize=max_results).execute()
            records = result.get("conferenceRecords", [])

            # Enrich with participant info
            enriched = []
            for record in records[:max_results]:
                record_name = record.get("name", "")
                # Get participants for this conference
                try:
                    participants_result = (
                        self.meet.conferenceRecords()
                        .participants()
                        .list(parent=record_name, pageSize=50)
                        .execute()
                    )
                    participants = participants_result.get("participants", [])
                except Exception:
                    participants = []

                enriched.append(
                    {
                        "id": record_name.split("/")[-1] if "/" in record_name else record_name,
                        "name": record.get("space", ""),
                        "startTime": record.get("startTime"),
                        "endTime": record.get("endTime"),
                        "participants": [
                            {
                                "displayName": p.get("signedinUser", {}).get("displayName", ""),
                                "email": p.get("signedinUser", {}).get("email", ""),
                            }
                            for p in participants
                        ],
                        "participantCount": len(participants),
                    }
                )

            return enriched
        except Exception as e:
            logger.error("meet_list_conferences_error", error=str(e))
            return []

    async def meet_get_transcript(
        self,
        conference_id: str,
    ) -> dict[str, Any]:
        """Get transcript for a Google Meet conference.

        Args:
            conference_id: Conference record ID

        Returns:
            Transcript entries with speaker and text
        """
        try:
            record_name = f"conferenceRecords/{conference_id}"

            # List transcripts for this conference - chiamata sincrona
            transcripts_result = (
                self.meet.conferenceRecords().transcripts().list(parent=record_name).execute()
            )
            transcripts = transcripts_result.get("transcripts", [])

            if not transcripts:
                return {
                    "conference_id": conference_id,
                    "entries": [],
                    "message": "No transcript available",
                }

            # Get entries from first transcript
            transcript_name = transcripts[0].get("name", "")
            entries_result = (
                self.meet.conferenceRecords()
                .transcripts()
                .entries()
                .list(parent=transcript_name, pageSize=100)
                .execute()
            )
            entries = entries_result.get("transcriptEntries", [])

            return {
                "conference_id": conference_id,
                "entries": [
                    {
                        "speaker": e.get("participant", {}).get("displayName", "Unknown"),
                        "text": e.get("text", ""),
                        "startTime": e.get("startTime"),
                    }
                    for e in entries
                ],
                "entryCount": len(entries),
            }
        except Exception as e:
            logger.error("meet_get_transcript_error", error=str(e))
            return {"conference_id": conference_id, "error": str(e)}

    # =========================================================================
    # CALENDAR API
    # =========================================================================

    @property
    def calendar(self):
        """Lazy-load Calendar service."""
        if not self._calendar and self.credentials:
            self._calendar = build("calendar", "v3", credentials=self.credentials)
        return self._calendar

    async def calendar_list_events(
        self,
        calendar_id: str = "primary",
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 100,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        """List calendar events with optional query filter.

        Args:
            calendar_id: Calendar to list events from
            time_min: Start of time range (ISO format)
            time_max: End of time range (ISO format)
            max_results: Maximum results to return
            query: Free text search on event summary/description
        """
        params = {
            "calendarId": calendar_id,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        if query:
            params["q"] = query

        result = await self._execute_with_backoff(self.calendar.events().list(**params))
        return result.get("items", [])

    async def calendar_create_event(
        self,
        summary: str,
        start: str,
        end: str,
        calendar_id: str = "primary",
        description: str | None = None,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new calendar event."""
        event = {
            "summary": summary,
            "start": {"dateTime": start, "timeZone": "Europe/Rome"},
            "end": {"dateTime": end, "timeZone": "Europe/Rome"},
        }
        if description:
            event["description"] = description
        if attendees:
            event["attendees"] = [{"email": e} for e in attendees]

        return await self._execute_with_backoff(
            self.calendar.events().insert(calendarId=calendar_id, body=event)
        )

    async def calendar_get_upcoming(
        self, days: int = 7, calendar_id: str = "primary"
    ) -> list[dict[str, Any]]:
        """Get upcoming events for the next N days."""
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days)).isoformat() + "Z"

        return await self.calendar_list_events(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
        )

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _get_export_mime_type(self, google_mime: str) -> str:
        """Map Google Docs MIME types to export formats."""
        mapping = {
            "application/vnd.google-apps.document": "application/pdf",
            "application/vnd.google-apps.spreadsheet": "text/csv",
            "application/vnd.google-apps.presentation": "application/pdf",
            "application/vnd.google-apps.drawing": "image/png",
        }
        return mapping.get(google_mime, "text/plain")

    async def _execute_with_backoff(self, request, max_retries: int = 5):
        """Execute API request with exponential backoff."""
        for attempt in range(max_retries):
            try:
                if hasattr(request, "execute"):
                    return request.execute()
                return request
            except HttpError as e:
                if e.resp.status in [403, 429, 500, 502, 503, 504]:
                    if attempt == max_retries - 1:
                        raise
                    delay = (2**attempt) + random.random()
                    logger.warning(
                        "google_api_retry",
                        status=e.resp.status,
                        attempt=attempt + 1,
                        delay=delay,
                    )
                    time.sleep(delay)
                else:
                    raise


# =========================================================================
# TOOL DEFINITIONS FOR API STORE
# =========================================================================

GOOGLE_WORKSPACE_TOOLS = [
    # Drive (3 tools)
    {
        "name": "google_drive_list_files",
        "description": "List files and folders in Google Drive. Can filter by folder ID.",
        "service": "GoogleDriveService",
        "method": "list_files",
        "parameters": {
            "folder_id": {"type": "string", "description": "Folder ID (default: root)"},
            "limit": {"type": "integer", "default": 10},
        },
    },
    {
        "name": "google_drive_get_file",
        "description": "Get file metadata from Google Drive by ID.",
        "service": "GoogleDriveService",
        "method": "get_file",
        "parameters": {
            "file_id": {"type": "string", "required": True},
        },
    },
    {
        "name": "google_drive_search",
        "description": "Search files in Google Drive by name.",
        "service": "GoogleDriveService",
        "method": "search",
        "parameters": {
            "query": {"type": "string", "required": True, "description": "Search query"},
        },
    },
    # Gmail (2 tools)
    {
        "name": "google_gmail_search",
        "description": "Search emails in Gmail by query. Returns email summaries.",
        "service": "GoogleGmailService",
        "method": "search",
        "parameters": {
            "query": {
                "type": "string",
                "required": True,
                "description": "Gmail search query (e.g., 'from:user@example.com after:2024/01/01')",
            },
            "limit": {"type": "integer", "default": 10},
        },
    },
    {
        "name": "google_gmail_get_message",
        "description": "Get a specific email message by ID.",
        "service": "GoogleGmailService",
        "method": "get_message",
        "parameters": {
            "message_id": {"type": "string", "required": True},
        },
    },
    # Calendar (2 tools)
    {
        "name": "google_calendar_upcoming",
        "description": "Get upcoming calendar events for the next N days.",
        "service": "GoogleCalendarService",
        "method": "upcoming",
        "parameters": {
            "days": {"type": "integer", "default": 7},
        },
    },
    {
        "name": "google_calendar_get_event",
        "description": "Get calendar event details by ID.",
        "service": "GoogleCalendarService",
        "method": "get_event",
        "parameters": {
            "event_id": {"type": "string", "required": True},
        },
    },
    # Docs (2 tools)
    {
        "name": "google_docs_get",
        "description": "Read content from a Google Doc by ID.",
        "service": "GoogleDocsService",
        "method": "get",
        "parameters": {
            "document_id": {"type": "string", "required": True},
        },
    },
    {
        "name": "google_docs_create",
        "description": "Create a new Google Doc with a title.",
        "service": "GoogleDocsService",
        "method": "create",
        "parameters": {
            "title": {"type": "string", "default": "Untitled Document"},
        },
    },
    # Sheets (2 tools)
    {
        "name": "google_sheets_get_values",
        "description": "Get cell values from a Google Sheet.",
        "service": "GoogleSheetsService",
        "method": "get_values",
        "parameters": {
            "spreadsheet_id": {"type": "string", "required": True},
            "range": {"type": "string", "default": "Sheet1!A1:Z100"},
        },
    },
    {
        "name": "google_sheets_get_metadata",
        "description": "Get metadata and sheet names from a Google Spreadsheet.",
        "service": "GoogleSheetsService",
        "method": "get_metadata",
        "parameters": {
            "spreadsheet_id": {"type": "string", "required": True},
        },
    },
    # Slides (2 tools)
    {
        "name": "google_slides_get",
        "description": "Get Google Slides presentation info.",
        "service": "GoogleSlidesService",
        "method": "get",
        "parameters": {
            "presentation_id": {"type": "string", "required": True},
        },
    },
    {
        "name": "google_slides_list",
        "description": "List slides with text content from a presentation.",
        "service": "GoogleSlidesService",
        "method": "list_slides",
        "parameters": {
            "presentation_id": {"type": "string", "required": True},
        },
    },
    # Meet (2 tools)
    {
        "name": "google_meet_create",
        "description": "Create a new Google Meet video conference.",
        "service": "GoogleMeetService",
        "method": "create_meeting",
        "parameters": {
            "summary": {"type": "string", "default": "Quick Meeting"},
            "duration_minutes": {"type": "integer", "default": 30},
            "start_time": {
                "type": "string",
                "description": "ISO datetime (optional, defaults to now+5min)",
            },
        },
    },
    {
        "name": "google_meet_get",
        "description": "Get Google Meet details by calendar event ID.",
        "service": "GoogleMeetService",
        "method": "get_meeting",
        "parameters": {
            "event_id": {"type": "string", "required": True},
        },
    },
]


# Singleton
_workspace_service: GoogleWorkspaceService | None = None


def get_google_workspace_service() -> GoogleWorkspaceService | None:
    """Get singleton instance of Google Workspace service."""
    global _workspace_service
    if _workspace_service is None:
        try:
            _workspace_service = GoogleWorkspaceService()
        except Exception as e:
            logger.error("google_workspace_init_failed", error=str(e))
            return None
    return _workspace_service
