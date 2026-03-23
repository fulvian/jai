"""Me4BrAIn Integrations Package.

External service integrations:
- Google Workspace (Drive, Gmail, Calendar)
- User APIs (FRED, PubMed, NBA, Odds)
"""

from me4brain.integrations.google_workspace import (
    GOOGLE_WORKSPACE_TOOLS,
    GoogleWorkspaceService,
    get_google_workspace_service,
)
from me4brain.integrations.google_workspace import (
    SCOPES as GOOGLE_SCOPES,
)
from me4brain.integrations.user_apis import (
    USER_API_TOOLS,
    BallDontLieService,
    FREDService,
    OddsAPIService,
    PubMedService,
    get_balldontlie_service,
    get_fred_service,
    get_odds_service,
    get_pubmed_service,
)

__all__ = [
    # Google Workspace
    "GoogleWorkspaceService",
    "get_google_workspace_service",
    "GOOGLE_WORKSPACE_TOOLS",
    "GOOGLE_SCOPES",
    # User APIs
    "FREDService",
    "get_fred_service",
    "PubMedService",
    "get_pubmed_service",
    "BallDontLieService",
    "get_balldontlie_service",
    "OddsAPIService",
    "get_odds_service",
    "USER_API_TOOLS",
]
