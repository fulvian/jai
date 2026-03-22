"""Entertainment Domain - Movies, Music, Games."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class Movie(BaseModel):
    """Movie information."""

    id: int
    title: str
    overview: str | None = None
    release_date: str | None = None
    vote_average: float = 0.0
    poster_path: str | None = None
    genres: list[str] = Field(default_factory=list)


class MusicArtist(BaseModel):
    """Music artist."""

    name: str
    mbid: str | None = None
    listeners: int = 0
    playcount: int = 0
    url: str | None = None
    tags: list[str] = Field(default_factory=list)


class MusicTrack(BaseModel):
    """Music track."""

    name: str
    artist: str
    album: str | None = None
    duration: int = 0
    playcount: int = 0
    url: str | None = None


class EntertainmentDomain(BaseDomain):
    """Entertainment domain - movies, music, games.

    Example:
        # Search movies
        movies = await client.domains.entertainment.movie_search("Inception")

        # Get music artist
        artist = await client.domains.entertainment.music_artist("Radiohead")
    """

    @property
    def domain_name(self) -> str:
        return "entertainment"

    async def movie_search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[Movie]:
        """Search movies (TMDB).

        Args:
            query: Movie title search
            max_results: Maximum results

        Returns:
            List of movies
        """
        result = await self._execute_tool(
            "tmdb_movie_search",
            {"query": query, "max_results": max_results},
        )
        movies = result.get("result", {}).get("movies", [])
        return [Movie.model_validate(m) for m in movies]

    async def movie_details(self, movie_id: int) -> Movie:
        """Get movie details.

        Args:
            movie_id: TMDB movie ID

        Returns:
            Movie details
        """
        result = await self._execute_tool("tmdb_movie_details", {"movie_id": movie_id})
        return Movie.model_validate(result.get("result", {}))

    async def music_artist(self, artist_name: str) -> MusicArtist:
        """Get music artist info (Last.fm).

        Args:
            artist_name: Artist name

        Returns:
            Artist information
        """
        result = await self._execute_tool("lastfm_artist", {"artist_name": artist_name})
        return MusicArtist.model_validate(result.get("result", {}))

    async def music_top_tracks(
        self,
        artist_name: str,
        limit: int = 10,
    ) -> list[MusicTrack]:
        """Get artist's top tracks.

        Args:
            artist_name: Artist name
            limit: Maximum tracks

        Returns:
            List of top tracks
        """
        result = await self._execute_tool(
            "lastfm_top_tracks",
            {"artist_name": artist_name, "limit": limit},
        )
        tracks = result.get("result", {}).get("tracks", [])
        return [MusicTrack.model_validate(t) for t in tracks]

    async def book_search(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Search books (Open Library).

        Args:
            query: Book title or author
            max_results: Maximum results

        Returns:
            List of books
        """
        result = await self._execute_tool(
            "openlibrary_search",
            {"query": query, "max_results": max_results},
        )
        return result.get("result", {}).get("books", [])
