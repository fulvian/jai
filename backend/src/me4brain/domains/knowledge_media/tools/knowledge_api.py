"""Knowledge & Media API Tools."""

from typing import Any
import httpx
import structlog

logger = structlog.get_logger(__name__)
TIMEOUT = 10.0


async def wikipedia_summary(topic: str) -> dict[str, Any]:
    """Ottieni summary Wikipedia."""
    try:
        from urllib.parse import quote

        # URL encode the topic properly
        encoded_topic = quote(topic.replace(" ", "_"), safe="")

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded_topic}",
                headers={
                    "User-Agent": "Me4BrAIn/2.0 (AI Research Platform; contact@me4brain.ai)",
                    "Accept": "application/json",
                },
            )
            if resp.status_code == 404:
                return {"error": f"Page not found: {topic}", "source": "Wikipedia"}
            resp.raise_for_status()
            data = resp.json()
            return {
                "title": data.get("title"),
                "extract": data.get("extract"),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
                "source": "Wikipedia",
            }
    except Exception as e:
        logger.error("wikipedia_summary_error", error=str(e), topic=topic)
        return {"error": str(e), "source": "Wikipedia"}


async def hackernews_top(count: int = 10) -> dict[str, Any]:
    """Ottieni top stories Hacker News."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            ids_resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            ids = ids_resp.json()[:count]

            stories = []
            for story_id in ids[:count]:
                story_resp = await client.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                )
                story = story_resp.json()
                stories.append(
                    {
                        "title": story.get("title"),
                        "url": story.get("url"),
                        "score": story.get("score"),
                        "by": story.get("by"),
                    }
                )

            return {"stories": stories, "count": len(stories), "source": "Hacker News"}
    except Exception as e:
        return {"error": str(e)}


async def openlibrary_search(query: str, limit: int = 5) -> dict[str, Any]:
    """Cerca libri su Open Library."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://openlibrary.org/search.json",
                params={"q": query, "limit": limit},
            )
            data = resp.json()
            books = []
            for doc in data.get("docs", [])[:limit]:
                books.append(
                    {
                        "title": doc.get("title"),
                        "author": doc.get("author_name", ["Unknown"])[0]
                        if doc.get("author_name")
                        else "Unknown",
                        "year": doc.get("first_publish_year"),
                        "key": doc.get("key"),
                    }
                )
            return {"books": books, "count": len(books), "source": "Open Library"}
    except Exception as e:
        return {"error": str(e)}


AVAILABLE_TOOLS = {
    "wikipedia_summary": wikipedia_summary,
    "hackernews_top": hackernews_top,
    "openlibrary_search": openlibrary_search,
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool knowledge per nome, filtrando parametri non accettati."""
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {"error": f"Unknown knowledge tool: {tool_name}"}

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
# Engine Integration - Tool Definitions for auto-discovery
# =============================================================================


def get_tool_definitions() -> list:
    """Get tool definitions for ToolCallingEngine auto-discovery."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        ToolDefinition(
            name="wikipedia_summary",
            description="Get a Wikipedia summary for any topic. Returns a concise extract, title, and URL. Use when user asks 'what is X', 'tell me about Y', 'Wikipedia article on Z'.",
            parameters={
                "topic": ToolParameter(
                    type="string",
                    description="Topic to search (e.g., 'Bitcoin', 'Albert Einstein', 'Climate Change')",
                    required=True,
                ),
            },
            domain="search",
            category="encyclopedia",
        ),
        ToolDefinition(
            name="hackernews_top",
            description="Get top stories from Hacker News tech community. Returns trending tech articles, discussions, and links. Use when user asks 'tech news today', 'trending on HN', 'Hacker News top'.",
            parameters={
                "count": ToolParameter(
                    type="integer",
                    description="Number of stories to fetch (1-30, default 10)",
                    required=False,
                    default="10",
                ),
            },
            domain="search",
            category="news",
        ),
        ToolDefinition(
            name="openlibrary_search",
            description="Search for books on Open Library catalog. Find titles, authors, publication years. Use when user asks 'find book about X', 'books by author Y', 'search library for Z'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Book search query (title, author, or keyword)",
                    required=True,
                ),
                "limit": ToolParameter(
                    type="integer",
                    description="Maximum number of results",
                    required=False,
                    default="5",
                ),
            },
            domain="search",
            category="books",
        ),
    ]


def get_executors() -> dict:
    """Get executor functions for ToolCallingEngine."""
    return {
        "wikipedia_summary": wikipedia_summary,
        "hackernews_top": hackernews_top,
        "openlibrary_search": openlibrary_search,
    }
