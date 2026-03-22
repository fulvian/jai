"""Google Workspace Tools Package.

Esporta tool Google Workspace per uso da GoogleWorkspaceHandler.
"""

from me4brain.domains.google_workspace.tools.google_api import (
    AVAILABLE_TOOLS as GOOGLE_API_TOOLS,
    calendar_list_events,
    calendar_upcoming,
    drive_get_file,
    drive_list_files,
    drive_search,
    execute_tool as google_api_execute,
    get_executors as get_google_api_executors,
    get_tool_definitions as get_google_api_definitions,
    gmail_get_message,
    gmail_search,
)
from me4brain.domains.google_workspace.tools.report_aggregator import (
    workspace_report_aggregator,
    TOOL_DEFINITION as REPORT_TOOL_DEFINITION,
)
from me4brain.domains.google_workspace.tools.calendar_meeting_analyzer import (
    calendar_analyze_meetings,
    get_executors as get_calendar_executors,
    get_tool_definitions as get_calendar_definitions,
)
# Merge definitions and executors
def get_tool_definitions():
    defs = get_google_api_definitions() + get_calendar_definitions()
    defs.append(REPORT_TOOL_DEFINITION)
    return defs

def get_executors():
    execs = get_google_api_executors().copy()
    execs.update(get_calendar_executors())
    execs["workspace_report_aggregator"] = workspace_report_aggregator
    return execs

def execute_tool(tool_name: str, args: dict):
    execs = get_executors()
    if tool_name in execs:
        return execs[tool_name](**args)
    return {"error": f"Tool {tool_name} not found in Google Workspace domain"}

AVAILABLE_TOOLS = get_executors()

__all__ = [
    "AVAILABLE_TOOLS",
    "execute_tool",
    "get_tool_definitions",
    "get_executors",
    # Drive
    "drive_search",
    "drive_list_files",
    "drive_get_file",
    # Gmail
    "gmail_search",
    "gmail_get_message",
    # Calendar
    "calendar_upcoming",
    "calendar_list_events",
    "calendar_analyze_meetings",
    # Report Aggregator
    "workspace_report_aggregator",
    "REPORT_TOOL_DEFINITION",
]
