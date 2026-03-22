"""Tech/Coding API Tools - GitHub, NPM, PyPI, StackOverflow, Piston.

- GitHub: 5000 req/h (auth) - Repos, Issues, PRs, Code search
- NPM: Illimitato - Package info JavaScript
- PyPI: Illimitato - Package info Python
- StackOverflow: 300 req/min - Q&A search
- Piston: Illimitato - Code execution (50+ linguaggi)
"""

from typing import Any
import os
import httpx
import structlog

logger = structlog.get_logger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
STACKOVERFLOW_KEY = os.getenv("STACKOVERFLOW_KEY")
TIMEOUT = 20.0


# =============================================================================
# GitHub API (5000 req/h with token)
# =============================================================================


async def github_repo(owner: str, repo: str) -> dict[str, Any]:
    """Info repository GitHub.

    Args:
        owner: Username/org proprietario
        repo: Nome repository

    Returns:
        dict con info repo
    """
    try:
        headers = {"Accept": "application/vnd.github+json"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers=headers,
            )
            resp.raise_for_status()
            r = resp.json()

            return {
                "full_name": r.get("full_name"),
                "description": r.get("description"),
                "language": r.get("language"),
                "stars": r.get("stargazers_count"),
                "forks": r.get("forks_count"),
                "open_issues": r.get("open_issues_count"),
                "topics": r.get("topics", []),
                "license": r.get("license", {}).get("name"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
                "url": r.get("html_url"),
                "source": "GitHub",
            }

    except Exception as e:
        logger.error("github_repo_error", error=str(e))
        return {"error": str(e), "source": "GitHub"}


async def github_search_repos(
    query: str,
    sort: str = "stars",
    limit: int = 10,
) -> dict[str, Any]:
    """Cerca repository su GitHub.

    Args:
        query: Query di ricerca (es. "machine learning language:python")
        sort: Ordinamento (stars, forks, updated)
        limit: Numero risultati

    Returns:
        dict con repos trovati
    """
    try:
        headers = {"Accept": "application/vnd.github+json"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://api.github.com/search/repositories",
                params={"q": query, "sort": sort, "per_page": limit},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            repos = []
            for r in data.get("items", []):
                repos.append(
                    {
                        "full_name": r.get("full_name"),
                        "description": r.get("description", "")[:200],
                        "language": r.get("language"),
                        "stars": r.get("stargazers_count"),
                        "url": r.get("html_url"),
                    }
                )

            return {
                "query": query,
                "results": repos,
                "total_count": data.get("total_count", 0),
                "source": "GitHub",
            }

    except Exception as e:
        logger.error("github_search_repos_error", error=str(e))
        return {"error": str(e), "source": "GitHub"}


async def github_issues(
    owner: str,
    repo: str,
    state: str = "open",
    limit: int = 10,
) -> dict[str, Any]:
    """Lista issues di un repository.

    Args:
        owner: Username/org
        repo: Nome repository
        state: open, closed, all
        limit: Numero risultati

    Returns:
        dict con issues
    """
    try:
        headers = {"Accept": "application/vnd.github+json"}
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/issues",
                params={"state": state, "per_page": limit},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

            issues = []
            for i in data:
                issues.append(
                    {
                        "number": i.get("number"),
                        "title": i.get("title"),
                        "state": i.get("state"),
                        "user": i.get("user", {}).get("login"),
                        "labels": [l.get("name") for l in i.get("labels", [])],
                        "comments": i.get("comments"),
                        "created_at": i.get("created_at"),
                        "url": i.get("html_url"),
                    }
                )

            return {
                "repo": f"{owner}/{repo}",
                "state": state,
                "issues": issues,
                "count": len(issues),
                "source": "GitHub",
            }

    except Exception as e:
        logger.error("github_issues_error", error=str(e))
        return {"error": str(e), "source": "GitHub"}


async def github_search_code(
    query: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Cerca codice su GitHub.

    Args:
        query: Query (es. "addClass repo:jquery/jquery")
        limit: Numero risultati

    Returns:
        dict con risultati codice
    """
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN richiesto per code search", "source": "GitHub"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://api.github.com/search/code",
                params={"q": query, "per_page": limit},
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                },
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for r in data.get("items", []):
                results.append(
                    {
                        "name": r.get("name"),
                        "path": r.get("path"),
                        "repo": r.get("repository", {}).get("full_name"),
                        "url": r.get("html_url"),
                    }
                )

            return {
                "query": query,
                "results": results,
                "total_count": data.get("total_count", 0),
                "source": "GitHub",
            }

    except Exception as e:
        logger.error("github_search_code_error", error=str(e))
        return {"error": str(e), "source": "GitHub"}


# =============================================================================
# NPM Registry (Illimitato)
# =============================================================================


async def npm_package(name: str) -> dict[str, Any]:
    """Info package NPM.

    Args:
        name: Nome package (es. "react", "@types/node")

    Returns:
        dict con info package
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(f"https://registry.npmjs.org/{name}")
            resp.raise_for_status()
            p = resp.json()

            latest = p.get("dist-tags", {}).get("latest")
            latest_info = p.get("versions", {}).get(latest, {})

            return {
                "name": p.get("name"),
                "description": p.get("description"),
                "latest_version": latest,
                "license": latest_info.get("license"),
                "homepage": latest_info.get("homepage"),
                "repository": latest_info.get("repository", {}).get("url"),
                "dependencies": list(latest_info.get("dependencies", {}).keys())[:10],
                "keywords": p.get("keywords", [])[:10],
                "source": "NPM",
            }

    except Exception as e:
        logger.error("npm_package_error", error=str(e))
        return {"error": str(e), "source": "NPM"}


async def npm_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Cerca package NPM.

    Args:
        query: Query di ricerca
        limit: Numero risultati

    Returns:
        dict con packages trovati
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://registry.npmjs.org/-/v1/search",
                params={"text": query, "size": limit},
            )
            resp.raise_for_status()
            data = resp.json()

            packages = []
            for obj in data.get("objects", []):
                p = obj.get("package", {})
                packages.append(
                    {
                        "name": p.get("name"),
                        "version": p.get("version"),
                        "description": p.get("description", "")[:200],
                        "keywords": p.get("keywords", [])[:5],
                        "score": obj.get("score", {}).get("final"),
                    }
                )

            return {
                "query": query,
                "results": packages,
                "count": len(packages),
                "source": "NPM",
            }

    except Exception as e:
        logger.error("npm_search_error", error=str(e))
        return {"error": str(e), "source": "NPM"}


# =============================================================================
# PyPI (Illimitato)
# =============================================================================


async def pypi_package(name: str) -> dict[str, Any]:
    """Info package PyPI.

    Args:
        name: Nome package (es. "requests", "numpy")

    Returns:
        dict con info package
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(f"https://pypi.org/pypi/{name}/json")
            resp.raise_for_status()
            data = resp.json()

            info = data.get("info", {})

            return {
                "name": info.get("name"),
                "version": info.get("version"),
                "summary": info.get("summary"),
                "author": info.get("author"),
                "license": info.get("license"),
                "home_page": info.get("home_page"),
                "project_url": info.get("project_url"),
                "requires_python": info.get("requires_python"),
                "keywords": info.get("keywords"),
                "classifiers": info.get("classifiers", [])[:5],
                "source": "PyPI",
            }

    except Exception as e:
        logger.error("pypi_package_error", error=str(e))
        return {"error": str(e), "source": "PyPI"}


# =============================================================================
# Stack Overflow (300 req/min)
# =============================================================================


async def stackoverflow_search(
    query: str,
    tagged: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Cerca domande su Stack Overflow.

    Args:
        query: Query di ricerca
        tagged: Tag separati da ; (es. "python;django")
        limit: Numero risultati

    Returns:
        dict con domande trovate
    """
    try:
        params = {
            "order": "desc",
            "sort": "relevance",
            "intitle": query,
            "site": "stackoverflow",
            "pagesize": limit,
        }
        if tagged:
            params["tagged"] = tagged
        if STACKOVERFLOW_KEY:
            params["key"] = STACKOVERFLOW_KEY

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://api.stackexchange.com/2.3/search/advanced",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            questions = []
            for q in data.get("items", []):
                questions.append(
                    {
                        "question_id": q.get("question_id"),
                        "title": q.get("title"),
                        "score": q.get("score"),
                        "answer_count": q.get("answer_count"),
                        "is_answered": q.get("is_answered"),
                        "tags": q.get("tags", []),
                        "link": q.get("link"),
                    }
                )

            return {
                "query": query,
                "tagged": tagged,
                "results": questions,
                "count": len(questions),
                "quota_remaining": data.get("quota_remaining"),
                "source": "Stack Overflow",
            }

    except Exception as e:
        logger.error("stackoverflow_search_error", error=str(e))
        return {"error": str(e), "source": "Stack Overflow"}


# =============================================================================
# Piston - Code Execution (Illimitato)
# =============================================================================


async def piston_runtimes() -> dict[str, Any]:
    """Lista runtime disponibili per esecuzione codice."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get("https://emkc.org/api/v2/piston/runtimes")
            resp.raise_for_status()
            data = resp.json()

            runtimes = []
            for r in data:
                runtimes.append(
                    {
                        "language": r.get("language"),
                        "version": r.get("version"),
                        "aliases": r.get("aliases", []),
                    }
                )

            return {
                "runtimes": runtimes,
                "count": len(runtimes),
                "source": "Piston",
            }

    except Exception as e:
        logger.error("piston_runtimes_error", error=str(e))
        return {"error": str(e), "source": "Piston"}


async def piston_execute(
    language: str,
    code: str,
    stdin: str = "",
    version: str = "*",
) -> dict[str, Any]:
    """Esegue codice in un linguaggio specifico.

    Args:
        language: Linguaggio (python, javascript, rust, go, etc.)
        code: Codice da eseguire
        stdin: Input per il programma
        version: Versione linguaggio (* = latest)

    Returns:
        dict con output esecuzione
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://emkc.org/api/v2/piston/execute",
                json={
                    "language": language,
                    "version": version,
                    "files": [{"content": code}],
                    "stdin": stdin,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            run = data.get("run", {})

            return {
                "language": data.get("language"),
                "version": data.get("version"),
                "stdout": run.get("stdout", ""),
                "stderr": run.get("stderr", ""),
                "exit_code": run.get("code"),
                "signal": run.get("signal"),
                "source": "Piston",
            }

    except Exception as e:
        logger.error("piston_execute_error", error=str(e))
        return {"error": str(e), "source": "Piston"}


# =============================================================================
# Tool Registry
# =============================================================================

AVAILABLE_TOOLS = {
    # GitHub (5000 req/h)
    "github_repo": github_repo,
    "github_search_repos": github_search_repos,
    "github_issues": github_issues,
    "github_search_code": github_search_code,
    # NPM (unlimited)
    "npm_package": npm_package,
    "npm_search": npm_search,
    # PyPI (unlimited)
    "pypi_package": pypi_package,
    # Stack Overflow (300 req/min)
    "stackoverflow_search": stackoverflow_search,
    # Piston Code Execution (unlimited)
    "piston_runtimes": piston_runtimes,
    "piston_execute": piston_execute,
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool tech per nome, filtrando parametri non accettati."""
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {"error": f"Unknown tech tool: {tool_name}"}

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
    """Generate ToolDefinition objects for all Tech Coding tools."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        # GitHub
        ToolDefinition(
            name="github_repo",
            description="Get GitHub repository information including stars, forks, issues, topics, and license. Use when user asks 'info about repo X', 'GitHub project Y', 'how many stars does Z have'.",
            parameters={
                "owner": ToolParameter(
                    type="string",
                    description="Repository owner (username or organization)",
                    required=True,
                ),
                "repo": ToolParameter(type="string", description="Repository name", required=True),
            },
            domain="dev_tools",
            category="github",
        ),
        ToolDefinition(
            name="github_search_repos",
            description="Search GitHub repositories by keyword, language, or topic. Find open source projects and libraries. Use when user asks 'find Python machine learning repos', 'best React libraries', 'projects about X'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Search query (e.g., 'machine learning language:python')",
                    required=True,
                ),
                "language": ToolParameter(
                    type="string",
                    description="Filter by programming language (e.g., 'python', 'javascript')",
                    required=False,
                ),
                "sort": ToolParameter(
                    type="string",
                    description="Sort by: 'stars', 'forks', 'updated'",
                    required=False,
                ),
            },
            domain="dev_tools",
            category="github",
        ),
        ToolDefinition(
            name="github_issues",
            description="List issues from a GitHub repository. Find bugs, feature requests, and discussions. Use when user asks 'issues in repo X', 'bugs in Y', 'open problems in Z'.",
            parameters={
                "owner": ToolParameter(
                    type="string", description="Repository owner", required=True
                ),
                "repo": ToolParameter(type="string", description="Repository name", required=True),
                "state": ToolParameter(
                    type="string",
                    description="Issue state: 'open', 'closed', 'all'",
                    required=False,
                ),
            },
            domain="dev_tools",
            category="github",
        ),
        ToolDefinition(
            name="github_search_code",
            description="Search for code snippets across GitHub repositories. Find implementations and examples. Use when user asks 'code examples for X', 'implementations of Y', 'how to use Z function'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Code search query (e.g., 'useEffect repo:facebook/react')",
                    required=True,
                ),
                "language": ToolParameter(
                    type="string", description="Filter by language", required=False
                ),
            },
            domain="dev_tools",
            category="github",
        ),
        # NPM
        ToolDefinition(
            name="npm_package",
            description="Get NPM package information including version, dependencies, and downloads. Use when user asks 'npm package info for X', 'latest version of Y', 'dependencies of Z'.",
            parameters={
                "package": ToolParameter(
                    type="string",
                    description="NPM package name (e.g., 'react', 'lodash', '@types/node')",
                    required=True,
                ),
            },
            domain="dev_tools",
            category="npm",
        ),
        ToolDefinition(
            name="npm_search",
            description="Search NPM registry for JavaScript/Node.js packages. Find libraries and frameworks. Use when user asks 'find npm package for X', 'JavaScript libraries for Y'.",
            parameters={
                "query": ToolParameter(
                    type="string", description="Search term or keyword", required=True
                ),
                "size": ToolParameter(
                    type="integer",
                    description="Number of results to return",
                    required=False,
                ),
            },
            domain="dev_tools",
            category="npm",
        ),
        # PyPI
        ToolDefinition(
            name="pypi_package",
            description="Get Python package information from PyPI including version, author, and requirements. Use when user asks 'PyPI info for X', 'Python package Y', 'pip install details for Z'.",
            parameters={
                "package": ToolParameter(
                    type="string",
                    description="PyPI package name (e.g., 'requests', 'numpy', 'pandas')",
                    required=True,
                ),
            },
            domain="dev_tools",
            category="pypi",
        ),
        # Stack Overflow
        ToolDefinition(
            name="stackoverflow_search",
            description="Search Stack Overflow for programming questions and answers. Find solutions and best practices. Use when user asks 'how to X in Python', 'error Y solution', 'best way to do Z'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Programming question or error message",
                    required=True,
                ),
                "sort": ToolParameter(
                    type="string",
                    description="Sort by: 'relevance', 'votes', 'activity'",
                    required=False,
                ),
                "tagged": ToolParameter(
                    type="string",
                    description="Filter by tag (e.g., 'python', 'javascript')",
                    required=False,
                ),
            },
            domain="dev_tools",
            category="stackoverflow",
        ),
        # Piston Code Execution
        ToolDefinition(
            name="piston_runtimes",
            description="List all available programming languages for code execution. Supports 50+ languages. Use when user asks 'what languages can you run', 'available runtimes'.",
            parameters={},
            domain="dev_tools",
            category="execution",
        ),
        ToolDefinition(
            name="piston_execute",
            description="Execute code in any programming language (Python, JavaScript, Rust, Go, C++, etc.). Runs code safely in sandbox. Use when user asks 'run this code', 'execute Python script', 'test this function'.",
            parameters={
                "language": ToolParameter(
                    type="string",
                    description="Programming language (e.g., 'python', 'javascript', 'rust', 'go', 'cpp')",
                    required=True,
                ),
                "code": ToolParameter(
                    type="string", description="Source code to execute", required=True
                ),
                "stdin": ToolParameter(
                    type="string",
                    description="Input to provide to the program",
                    required=False,
                ),
                "version": ToolParameter(
                    type="string",
                    description="Language version ('*' for latest)",
                    required=False,
                ),
            },
            domain="dev_tools",
            category="execution",
        ),
    ]


def get_executors() -> dict:
    """Return mapping of tool names to executor functions."""
    return AVAILABLE_TOOLS
