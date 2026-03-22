"""Entertainment Domain Handler."""

from typing import Any

import structlog

from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
)

logger = structlog.get_logger(__name__)


class EntertainmentHandler(DomainHandler):
    """Handler per Film, Libri e Musica."""

    HANDLED_SERVICES = frozenset({"TMDBService", "OpenLibraryService", "LastfmService"})

    ENTERTAINMENT_KEYWORDS = frozenset(
        {
            # Film
            "film",
            "movie",
            "cinema",
            "regista",
            "attore",
            "attrice",
            "serie",
            "tv",
            "episodio",
            "stagione",
            "trailer",
            # Libri
            "libro",
            "book",
            "autore",
            "romanzo",
            "editore",
            "isbn",
            # Musica
            "musica",
            "canzone",
            "album",
            "artista",
            "cantante",
            "band",
            "traccia",
            "playlist",
            "concerto",
        }
    )

    @property
    def domain_name(self) -> str:
        return "entertainment"

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="movies_tv",
                description="Cerca film e serie TV (TMDB)",
                required_params=["query"],
                optional_params=["year"],
            ),
            DomainCapability(
                name="books",
                description="Cerca libri e autori (Open Library)",
                required_params=["query"],
                optional_params=["isbn"],
            ),
            DomainCapability(
                name="music",
                description="Cerca artisti e tracce (Last.fm)",
                required_params=["artist"],
            ),
        ]

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.STABLE

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        """Check if this handler can process the query."""
        query_lower = query.lower()
        matches = sum(1 for kw in self.ENTERTAINMENT_KEYWORDS if kw in query_lower)
        if matches >= 2:
            return 0.9
        elif matches == 1:
            return 0.7
        return 0.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        from .tools.entertainment_api import execute_tool

        query_lower = query.lower()
        results = []

        # Detect intent
        if any(kw in query_lower for kw in ["film", "movie", "cinema", "serie", "tv"]):
            # Movie search
            data = await execute_tool("tmdb_search_movie", {"query": query})
            results.append(
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="tmdb_search_movie",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            )

        if any(kw in query_lower for kw in ["libro", "book", "autore", "romanzo"]):
            # Book search
            data = await execute_tool("openlibrary_search", {"query": query})
            results.append(
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="openlibrary_search",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            )

        if any(kw in query_lower for kw in ["musica", "artista", "cantante", "band"]):
            # Music search - extract artist name
            data = await execute_tool("lastfm_search_artist", {"artist": query})
            results.append(
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="lastfm_search_artist",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            )

        if not results:
            # Default: try movie search
            data = await execute_tool("tmdb_search_movie", {"query": query})
            results.append(
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="tmdb_search_movie",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            )

        return results
