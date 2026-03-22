"""Markdown to Google Docs converter.

Converts Markdown text to Google Docs API batchUpdate requests
with proper formatting (headings, bold, italic, links, lists).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TextSegment:
    """A segment of text with associated formatting."""

    text: str
    bold: bool = False
    italic: bool = False
    link: str | None = None
    heading_level: int = 0  # 0 = normal, 1-6 = heading levels


@dataclass
class MarkdownConverter:
    """Converts Markdown to Google Docs API requests."""

    content: str
    requests: list[dict[str, Any]] = field(default_factory=list)
    current_index: int = 1  # Google Docs indexes start at 1

    def convert(self) -> list[dict[str, Any]]:
        """Convert Markdown content to Google Docs batchUpdate requests.

        Returns:
            List of batchUpdate request objects
        """
        if not self.content:
            return []

        # Split into lines and process
        lines = self.content.split("\n")

        for line in lines:
            self._process_line(line)

        return self.requests

    def _process_line(self, line: str) -> None:
        """Process a single line of Markdown."""
        stripped = line.strip()

        # Skip empty lines but add newline
        if not stripped:
            self._insert_text("\n")
            return

        # Check for headings
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2)
            self._insert_heading(text, level)
            return

        # Check for horizontal rule
        if re.match(r"^[-*_]{3,}$", stripped):
            self._insert_text("─" * 50 + "\n")
            return

        # Check for list items
        list_match = re.match(r"^[-*•]\s+(.+)$", stripped)
        if list_match:
            self._insert_bullet(list_match.group(1))
            return

        # Check for numbered list
        num_match = re.match(r"^(\d+)\.\s+(.+)$", stripped)
        if num_match:
            self._insert_numbered(num_match.group(1), num_match.group(2))
            return

        # Regular paragraph - process inline formatting
        self._insert_formatted_text(stripped + "\n")

    def _insert_text(self, text: str) -> None:
        """Insert plain text."""
        if not text:
            return

        self.requests.append(
            {
                "insertText": {
                    "location": {"index": self.current_index},
                    "text": text,
                }
            }
        )
        self.current_index += len(text)

    def _insert_heading(self, text: str, level: int) -> None:
        """Insert a heading with proper formatting."""
        # Insert the text
        heading_text = text + "\n"
        start_index = self.current_index

        self._insert_text(heading_text)

        # Apply heading style
        heading_style_map = {
            1: "HEADING_1",
            2: "HEADING_2",
            3: "HEADING_3",
            4: "HEADING_4",
            5: "HEADING_5",
            6: "HEADING_6",
        }

        self.requests.append(
            {
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": start_index,
                        "endIndex": self.current_index,
                    },
                    "paragraphStyle": {
                        "namedStyleType": heading_style_map.get(level, "HEADING_2"),
                    },
                    "fields": "namedStyleType",
                }
            }
        )

    def _insert_bullet(self, text: str) -> None:
        """Insert a bullet list item."""
        bullet_text = "• " + text + "\n"
        self._insert_formatted_text(bullet_text)

    def _insert_numbered(self, number: str, text: str) -> None:
        """Insert a numbered list item."""
        numbered_text = f"{number}. " + text + "\n"
        self._insert_formatted_text(numbered_text)

    def _insert_formatted_text(self, text: str) -> None:
        """Insert text with inline formatting (bold, italic, links)."""
        # Parse inline formatting and insert segments
        segments = self._parse_inline_formatting(text)

        for segment in segments:
            start_index = self.current_index
            self._insert_text(segment.text)
            end_index = self.current_index

            # Apply bold
            if segment.bold:
                self.requests.append(
                    {
                        "updateTextStyle": {
                            "range": {
                                "startIndex": start_index,
                                "endIndex": end_index,
                            },
                            "textStyle": {"bold": True},
                            "fields": "bold",
                        }
                    }
                )

            # Apply italic
            if segment.italic:
                self.requests.append(
                    {
                        "updateTextStyle": {
                            "range": {
                                "startIndex": start_index,
                                "endIndex": end_index,
                            },
                            "textStyle": {"italic": True},
                            "fields": "italic",
                        }
                    }
                )

            # Apply link
            if segment.link:
                self.requests.append(
                    {
                        "updateTextStyle": {
                            "range": {
                                "startIndex": start_index,
                                "endIndex": end_index,
                            },
                            "textStyle": {
                                "link": {"url": segment.link},
                                "foregroundColor": {
                                    "color": {"rgbColor": {"blue": 0.8, "green": 0.2, "red": 0.0}}
                                },
                                "underline": True,
                            },
                            "fields": "link,foregroundColor,underline",
                        }
                    }
                )

    def _parse_inline_formatting(self, text: str) -> list[TextSegment]:
        """Parse inline Markdown formatting into segments.

        Handles: **bold**, *italic*, [link](url)
        """
        segments: list[TextSegment] = []
        current_pos = 0

        # Pattern for bold, italic, and links
        # Order matters: check bold first (**), then italic (*)
        pattern = re.compile(
            r"(\*\*(.+?)\*\*)"  # Bold
            r"|(\*([^*]+)\*)"  # Italic
            r"|(\[([^\]]+)\]\(([^)]+)\))"  # Link [text](url)
        )

        for match in pattern.finditer(text):
            # Add any text before this match as plain
            if match.start() > current_pos:
                segments.append(TextSegment(text=text[current_pos : match.start()]))

            if match.group(2):  # Bold
                segments.append(TextSegment(text=match.group(2), bold=True))
            elif match.group(4):  # Italic
                segments.append(TextSegment(text=match.group(4), italic=True))
            elif match.group(6) and match.group(7):  # Link
                segments.append(TextSegment(text=match.group(6), link=match.group(7)))

            current_pos = match.end()

        # Add remaining text
        if current_pos < len(text):
            segments.append(TextSegment(text=text[current_pos:]))

        return segments if segments else [TextSegment(text=text)]


def markdown_to_docs_requests(markdown_content: str) -> list[dict[str, Any]]:
    """Convert Markdown content to Google Docs batchUpdate requests.

    Args:
        markdown_content: Markdown formatted text

    Returns:
        List of batchUpdate request objects
    """
    converter = MarkdownConverter(content=markdown_content)
    return converter.convert()
