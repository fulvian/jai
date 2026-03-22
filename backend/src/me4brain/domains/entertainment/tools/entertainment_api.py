"""Entertainment API Tools - TMDB, Open Library, Last.fm.

Tutti i tool sono gratuiti con limiti generosi:
- TMDB: 40 req/10s (film/serie TV)
- Open Library: Illimitato (libri)
- Last.fm: Illimitato (musica)
"""

from typing import Any
import os
import httpx
import structlog

logger = structlog.get_logger(__name__)

# TMDB supports both Bearer token and API key query param
TMDB_ACCESS_TOKEN = os.getenv("TMDB_ACCESS_TOKEN")  # Bearer token (preferred)
TMDB_API_KEY = os.getenv("TMDB_API_KEY")  # API key (fallback as query param)
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")

TIMEOUT = 15.0


# =============================================================================
# TMDB - The Movie Database (Film & Serie TV)
# =============================================================================


async def tmdb_search_movie(query: str, year: int | None = None) -> dict[str, Any]:
    """Cerca film su TMDB.

    Args:
        query: Titolo del film
        year: Anno di uscita (opzionale)

    Returns:
        dict con risultati film
    """
    if not TMDB_ACCESS_TOKEN:
        return {"error": "TMDB_ACCESS_TOKEN non configurata", "source": "TMDB"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            params = {"query": query, "language": "it-IT"}
            if year:
                params["year"] = year

            resp = await client.get(
                "https://api.themoviedb.org/3/search/movie",
                params=params,
                headers={"Authorization": f"Bearer {TMDB_ACCESS_TOKEN}"},
            )
            resp.raise_for_status()
            data = resp.json()

            movies = []
            for m in data.get("results", [])[:10]:
                movies.append(
                    {
                        "id": m.get("id"),
                        "title": m.get("title"),
                        "original_title": m.get("original_title"),
                        "release_date": m.get("release_date"),
                        "overview": m.get("overview", "")[:300],
                        "vote_average": m.get("vote_average"),
                        "poster": f"https://image.tmdb.org/t/p/w500{m.get('poster_path')}"
                        if m.get("poster_path")
                        else None,
                    }
                )

            return {
                "query": query,
                "results": movies,
                "total_results": data.get("total_results", 0),
                "source": "TMDB",
            }

    except Exception as e:
        logger.error("tmdb_search_movie_error", error=str(e))
        return {"error": str(e), "source": "TMDB"}


async def tmdb_movie_details(movie_id: int) -> dict[str, Any]:
    """Dettagli completi di un film.

    Args:
        movie_id: ID TMDB del film

    Returns:
        dict con dettagli film
    """
    if not TMDB_ACCESS_TOKEN:
        return {"error": "TMDB_ACCESS_TOKEN non configurata", "source": "TMDB"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"https://api.themoviedb.org/3/movie/{movie_id}",
                params={"language": "it-IT", "append_to_response": "credits"},
                headers={"Authorization": f"Bearer {TMDB_ACCESS_TOKEN}"},
            )
            resp.raise_for_status()
            m = resp.json()

            # Estrai cast principale
            cast = []
            for c in m.get("credits", {}).get("cast", [])[:5]:
                cast.append({"name": c.get("name"), "character": c.get("character")})

            # Estrai regista
            director = None
            for c in m.get("credits", {}).get("crew", []):
                if c.get("job") == "Director":
                    director = c.get("name")
                    break

            return {
                "id": m.get("id"),
                "title": m.get("title"),
                "tagline": m.get("tagline"),
                "overview": m.get("overview"),
                "release_date": m.get("release_date"),
                "runtime": m.get("runtime"),
                "vote_average": m.get("vote_average"),
                "genres": [g.get("name") for g in m.get("genres", [])],
                "director": director,
                "cast": cast,
                "budget": m.get("budget"),
                "revenue": m.get("revenue"),
                "imdb_id": m.get("imdb_id"),
                "source": "TMDB",
            }

    except Exception as e:
        logger.error("tmdb_movie_details_error", error=str(e))
        return {"error": str(e), "source": "TMDB"}


async def tmdb_trending(media_type: str = "movie", time_window: str = "week") -> dict[str, Any]:
    """Film/Serie in tendenza.

    Args:
        media_type: "movie", "tv", o "all"
        time_window: "day" o "week"

    Returns:
        dict con trending
    """
    if not TMDB_ACCESS_TOKEN:
        return {"error": "TMDB_ACCESS_TOKEN non configurata", "source": "TMDB"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"https://api.themoviedb.org/3/trending/{media_type}/{time_window}",
                params={"language": "it-IT"},
                headers={"Authorization": f"Bearer {TMDB_ACCESS_TOKEN}"},
            )
            resp.raise_for_status()
            data = resp.json()

            items = []
            for m in data.get("results", [])[:10]:
                items.append(
                    {
                        "id": m.get("id"),
                        "title": m.get("title") or m.get("name"),
                        "media_type": m.get("media_type"),
                        "release_date": m.get("release_date") or m.get("first_air_date"),
                        "vote_average": m.get("vote_average"),
                        "overview": m.get("overview", "")[:200],
                    }
                )

            return {
                "media_type": media_type,
                "time_window": time_window,
                "results": items,
                "source": "TMDB",
            }

    except Exception as e:
        logger.error("tmdb_trending_error", error=str(e))
        return {"error": str(e), "source": "TMDB"}


# =============================================================================
# Open Library - Libri (100% Gratuito)
# =============================================================================


async def openlibrary_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Cerca libri su Open Library.

    Args:
        query: Titolo o autore
        limit: Numero massimo risultati

    Returns:
        dict con libri trovati
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://openlibrary.org/search.json",
                params={"q": query, "limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()

            books = []
            for b in data.get("docs", []):
                books.append(
                    {
                        "key": b.get("key"),
                        "title": b.get("title"),
                        "author": b.get("author_name", ["Unknown"])[0]
                        if b.get("author_name")
                        else "Unknown",
                        "first_publish_year": b.get("first_publish_year"),
                        "isbn": b.get("isbn", [None])[0] if b.get("isbn") else None,
                        "subject": b.get("subject", [])[:3],
                        "cover_id": b.get("cover_i"),
                    }
                )

            return {
                "query": query,
                "results": books,
                "total_found": data.get("numFound", 0),
                "source": "Open Library",
            }

    except Exception as e:
        logger.error("openlibrary_search_error", error=str(e))
        return {"error": str(e), "source": "Open Library"}


async def openlibrary_book(isbn: str) -> dict[str, Any]:
    """Dettagli libro per ISBN.

    Args:
        isbn: ISBN-10 o ISBN-13

    Returns:
        dict con dettagli libro
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"https://openlibrary.org/api/books",
                params={"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"},
            )
            resp.raise_for_status()
            data = resp.json()

            key = f"ISBN:{isbn}"
            if key not in data:
                return {"error": f"ISBN {isbn} non trovato", "source": "Open Library"}

            b = data[key]
            return {
                "title": b.get("title"),
                "authors": [a.get("name") for a in b.get("authors", [])],
                "publishers": [p.get("name") for p in b.get("publishers", [])],
                "publish_date": b.get("publish_date"),
                "number_of_pages": b.get("number_of_pages"),
                "subjects": [s.get("name") for s in b.get("subjects", [])[:5]],
                "cover": b.get("cover", {}).get("large"),
                "url": b.get("url"),
                "source": "Open Library",
            }

    except Exception as e:
        logger.error("openlibrary_book_error", error=str(e))
        return {"error": str(e), "source": "Open Library"}


# =============================================================================
# Last.fm - Musica (Illimitato)
# =============================================================================


async def lastfm_search_artist(artist: str) -> dict[str, Any]:
    """Cerca artista su Last.fm.

    Args:
        artist: Nome artista

    Returns:
        dict con info artista
    """
    if not LASTFM_API_KEY:
        return {"error": "LASTFM_API_KEY non configurata", "source": "Last.fm"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://ws.audioscrobbler.com/2.0/",
                params={
                    "method": "artist.search",
                    "artist": artist,
                    "api_key": LASTFM_API_KEY,
                    "format": "json",
                    "limit": 5,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            artists = []
            for a in data.get("results", {}).get("artistmatches", {}).get("artist", []):
                artists.append(
                    {
                        "name": a.get("name"),
                        "listeners": a.get("listeners"),
                        "url": a.get("url"),
                    }
                )

            return {
                "query": artist,
                "results": artists,
                "source": "Last.fm",
            }

    except Exception as e:
        logger.error("lastfm_search_artist_error", error=str(e))
        return {"error": str(e), "source": "Last.fm"}


async def lastfm_top_tracks(artist: str) -> dict[str, Any]:
    """Top tracce di un artista.

    Args:
        artist: Nome artista

    Returns:
        dict con top tracks
    """
    if not LASTFM_API_KEY:
        return {"error": "LASTFM_API_KEY non configurata", "source": "Last.fm"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://ws.audioscrobbler.com/2.0/",
                params={
                    "method": "artist.gettoptracks",
                    "artist": artist,
                    "api_key": LASTFM_API_KEY,
                    "format": "json",
                    "limit": 10,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            tracks = []
            for t in data.get("toptracks", {}).get("track", []):
                tracks.append(
                    {
                        "name": t.get("name"),
                        "playcount": t.get("playcount"),
                        "listeners": t.get("listeners"),
                        "url": t.get("url"),
                    }
                )

            return {
                "artist": artist,
                "tracks": tracks,
                "source": "Last.fm",
            }

    except Exception as e:
        logger.error("lastfm_top_tracks_error", error=str(e))
        return {"error": str(e), "source": "Last.fm"}


# =============================================================================
# Tool Registry
# =============================================================================

AVAILABLE_TOOLS = {
    # TMDB (Movies/TV)
    "tmdb_search_movie": tmdb_search_movie,
    "tmdb_movie_details": tmdb_movie_details,
    "tmdb_trending": tmdb_trending,
    # Open Library (Books)
    "openlibrary_search": openlibrary_search,
    "openlibrary_book": openlibrary_book,
    # Last.fm (Music)
    "lastfm_search_artist": lastfm_search_artist,
    "lastfm_top_tracks": lastfm_top_tracks,
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool entertainment per nome, filtrando parametri non accettati."""
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {"error": f"Unknown entertainment tool: {tool_name}"}

    tool_func = AVAILABLE_TOOLS[tool_name]
    sig = inspect.signature(tool_func)
    valid_params = set(sig.parameters.keys())
    filtered_args = {k: v for k, v in arguments.items() if k in valid_params}

    if len(filtered_args) < len(arguments):
        ignored = set(arguments.keys()) - valid_params
        logger.warning(
            "execute_tool_ignored_params",
            tool=tool_name,
            ignored=list(ignored),
            hint="LLM hallucinated parameters not in function signature",
        )

    return await tool_func(**filtered_args)


# =============================================================================
# Tool Engine Integration
# =============================================================================


def get_tool_definitions() -> list:
    """Generate ToolDefinition objects for all Entertainment tools."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        # TMDB (Movies/TV)
        ToolDefinition(
            name="tmdb_search_movie",
            description="Search for movies on TMDB (The Movie Database). Find films by title, returns posters, ratings, release dates, and overviews. Use when user asks 'find movie X', 'search for film Y', 'what movies about Z'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Movie title or search term to find",
                    required=True,
                ),
                "year": ToolParameter(
                    type="integer",
                    description="Release year to filter results (optional)",
                    required=False,
                ),
            },
            domain="entertainment",
            category="movies",
        ),
        ToolDefinition(
            name="tmdb_movie_details",
            description="Get complete movie details from TMDB including cast, director, budget, revenue, genres, runtime. Use when user asks for 'details about movie X', 'who directed Y', 'cast of Z'.",
            parameters={
                "movie_id": ToolParameter(
                    type="integer",
                    description="TMDB movie ID (from tmdb_search_movie)",
                    required=True,
                ),
            },
            domain="entertainment",
            category="movies",
        ),
        ToolDefinition(
            name="tmdb_trending",
            description="Get trending movies or TV shows right now. Returns what's popular today or this week. Use when user asks 'what movies are popular', 'trending shows', 'top films this week'.",
            parameters={
                "media_type": ToolParameter(
                    type="string",
                    description="Media type: 'movie', 'tv', or 'all'",
                    required=False,
                ),
                "time_window": ToolParameter(
                    type="string",
                    description="Time window: 'day' (today) or 'week'",
                    required=False,
                ),
            },
            domain="entertainment",
            category="movies",
        ),
        # Open Library (Books)
        ToolDefinition(
            name="openlibrary_search",
            description="Search for books on Open Library by title, author, or keyword. Find any book in the world's largest open library catalog. Use when user asks 'find book X', 'books by author Y', 'search for novel Z'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Book title, author name, or search term",
                    required=True,
                ),
                "search_type": ToolParameter(
                    type="string",
                    description="Search type: 'title', 'author', or 'isbn'",
                    required=False,
                ),
            },
            domain="entertainment",
            category="books",
        ),
        ToolDefinition(
            name="openlibrary_book",
            description="Get detailed book information by ISBN or Open Library ID. Returns authors, publishers, page count, subjects, and cover images. Use when user asks 'details about book', 'ISBN lookup', 'book information'.",
            parameters={
                "work_id": ToolParameter(
                    type="string",
                    description="Open Library work ID (e.g., 'OL45883W') or ISBN",
                    required=True,
                ),
            },
            domain="entertainment",
            category="books",
        ),
        # Last.fm (Music)
        ToolDefinition(
            name="lastfm_search_artist",
            description="Search for music artists on Last.fm. Find bands, singers, and musicians with listener stats. Use when user asks 'find artist X', 'search musician Y', 'info about band Z'.",
            parameters={
                "artist": ToolParameter(
                    type="string",
                    description="Artist or band name to search",
                    required=True,
                ),
            },
            domain="entertainment",
            category="music",
        ),
        ToolDefinition(
            name="lastfm_top_tracks",
            description="Get the most popular songs by an artist on Last.fm. Returns top tracks with play counts. Use when user asks 'top songs by X', 'best tracks from Y', 'popular songs of Z'.",
            parameters={
                "artist": ToolParameter(
                    type="string",
                    description="Artist name to get top tracks for",
                    required=True,
                ),
            },
            domain="entertainment",
            category="music",
        ),
    ]


def get_executors() -> dict:
    """Return mapping of tool names to executor functions."""
    return AVAILABLE_TOOLS
