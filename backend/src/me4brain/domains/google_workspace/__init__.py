"""Google Workspace Domain Package.

Implementa domain handler per Google Workspace APIs:
- Drive: File/folder management
- Gmail: Email reading and search
- Calendar: Event management
- Docs, Sheets, Slides: Document operations
- Meet, Forms, Classroom: Collaboration tools

Volatilità: SEMI_VOLATILE (dati cambiano frequentemente ma non in real-time)
"""

from me4brain.domains.google_workspace.handler import GoogleWorkspaceHandler


def get_handler() -> GoogleWorkspaceHandler:
    """Factory function for domain handler discovery.

    Called by PluginRegistry during auto-discovery.
    """
    return GoogleWorkspaceHandler()


__all__ = ["GoogleWorkspaceHandler", "get_handler"]
