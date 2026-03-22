#!/usr/bin/env python3
"""Bulk update tool domains from google_workspace to intent-based domains."""

import re

# Mapping tool_name -> nuovo dominio
DOMAIN_MAPPING = {
    # search
    "google_drive_search": "search",
    "google_gmail_search": "search",
    # file_management
    "google_drive_list_files": "file_management",
    "google_drive_get_file": "file_management",
    "google_drive_get_content": "file_management",
    "google_drive_export": "file_management",
    "google_drive_create_folder": "file_management",
    "google_drive_copy": "file_management",
    # communication
    "google_gmail_get_message": "communication",
    "google_gmail_send": "communication",
    "google_gmail_reply": "communication",
    "google_gmail_forward": "communication",
    "google_gmail_get_attachments": "communication",
    "google_gmail_get_attachment_content": "communication",
    "google_classroom_list_courses": "communication",
    "google_classroom_get_coursework": "communication",
    # scheduling
    "google_calendar_upcoming": "scheduling",
    "google_calendar_list_events": "scheduling",
    "google_calendar_create_event": "scheduling",
    "google_calendar_get_event": "scheduling",
    "google_calendar_update_event": "scheduling",
    "google_calendar_delete_event": "scheduling",
    "google_meet_create": "scheduling",
    "google_meet_list_conferences": "scheduling",
    # content_creation
    "google_docs_get": "content_creation",
    "google_docs_create": "content_creation",
    "google_docs_insert_text": "content_creation",
    "google_docs_append_text": "content_creation",
    "google_docs_replace_text": "content_creation",
    "google_slides_get": "content_creation",
    "google_slides_create": "content_creation",
    "google_slides_get_text": "content_creation",
    "google_slides_add_slide": "content_creation",
    "google_meet_get_transcript": "content_creation",
    "google_forms_get": "content_creation",
    # data_analysis
    "google_sheets_get_values": "data_analysis",
    "google_sheets_get_metadata": "data_analysis",
    "google_sheets_create": "data_analysis",
    "google_sheets_update_values": "data_analysis",
    "google_sheets_append_row": "data_analysis",
    "google_sheets_add_sheet": "data_analysis",
    "google_forms_get_responses": "data_analysis",
}


def update_domains(filepath: str):
    with open(filepath, "r") as f:
        content = f.read()

    # Find each ToolDefinition block and update domain
    for tool_name, new_domain in DOMAIN_MAPPING.items():
        # Pattern: name="tool_name"... domain="google_workspace"
        pattern = rf'(name="{tool_name}".*?domain=)"google_workspace"'
        replacement = rf'\1"{new_domain}"'
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    with open(filepath, "w") as f:
        f.write(content)

    print(f"Updated {len(DOMAIN_MAPPING)} tools")


if __name__ == "__main__":
    update_domains("src/me4brain/domains/google_workspace/tools/google_api.py")
