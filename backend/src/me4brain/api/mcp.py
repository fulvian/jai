"""Me4BrAIn MCP Server - Model Context Protocol implementation.

Standardized interface for LM Studio and other MCP hosts.
Provides:
1. Dynamic tools from ToolCatalog
2. Memory resources (Semantic/Episodic)
3. Learning prompts (Muscle Memory)
"""

import structlog
from fastmcp import FastMCP

from me4brain.api.routes.engine import get_engine
from me4brain.memory import get_episodic_memory
from me4brain.memory.semantic import get_semantic_memory

logger = structlog.get_logger(__name__)

# Initialize FastMCP
mcp = FastMCP(
    "Me4BrAIn",
)


@mcp.tool()
async def query_engine(query: str, session_id: str | None = None) -> str:
    """
    Execute a natural language query using Me4BrAIn's agentic engine.
    This uses multi-step reasoning and iterative tool execution internally.
    """
    import asyncio

    engine = await get_engine()

    try:
        # 55s timeout to stay under LM Studio's 60s hard limit.
        # This allows us to return a friendly 'still working' message instead of a silent failure.
        response = await asyncio.wait_for(engine.run(query), timeout=55.0)
        return response.answer
    except TimeoutError:
        return (
            "⚠️ L'analisi è molto complessa e sta richiedendo più dei 60 secondi "
            "concessi da LM Studio. Il backend Me4BrAIn sta continuando l'elaborazione "
            "in background. Per favore, riprova tra un minuto chiedendo: 'A che punto è l'analisi precedente?'"
        )


# We will call this from the main app's lifespan to ensure the engine is ready
# Curated "Hero" tools to expose individually without bloating context
# These are the tools that will appear as individual tools in LM Studio.
# All other 200+ tools are accessible via 'query_engine'.


@mcp.tool()
async def nba_betting_analyzer(
    home_team: str | None = None, away_team: str | None = None, analyze_all_today: bool = False
) -> str:
    """
    Professional NBA betting analysis. Predicts winners, spreads, and totals.
    Set analyze_all_today=True to see the full daily slate predictions.
    """
    engine = await get_engine()
    args = {"analyze_all_today": analyze_all_today}
    if home_team:
        args["home_team"] = home_team
    if away_team:
        args["away_team"] = away_team

    result = await engine.execute_tool("nba_betting_analyzer", args)
    return (
        str(result.data)
        if hasattr(result, "success") and result.success
        else f"Error: {getattr(result, 'error', 'Unknown')}"
    )


@mcp.tool()
async def stock_key_metrics(symbol: str) -> str:
    """Get key financial metrics, ratios, and price targets for a stock symbol (e.g. AAPL)."""
    engine = await get_engine()
    result = await engine.execute_tool("stock_key_metrics", {"symbol": symbol})
    return (
        str(result.data)
        if hasattr(result, "success") and result.success
        else f"Error: {getattr(result, 'error', 'Unknown')}"
    )


@mcp.tool()
async def smart_search(query: str) -> str:
    """Universal web search that intelligently routes between Google, Brave, and Tavily."""
    engine = await get_engine()
    result = await engine.execute_tool("smart_search", {"query": query})
    return (
        str(result.data)
        if hasattr(result, "success") and result.success
        else f"Error: {getattr(result, 'error', 'Unknown')}"
    )


@mcp.tool()
async def calendar_analyze_meetings(days_ahead: int = 7) -> str:
    """Analyze upcoming calendar meetings across Google, Outlook, and Zoom. Detects conflicts and provides summaries."""
    engine = await get_engine()
    result = await engine.execute_tool("calendar_analyze_meetings", {"days_ahead": days_ahead})
    return (
        str(result.data)
        if hasattr(result, "success") and result.success
        else f"Error: {getattr(result, 'error', 'Unknown')}"
    )


@mcp.tool()
async def gmail_search(query: str, max_results: int = 20) -> str:
    """Search Gmail messages using keywords or advanced filters (e.g. 'from:boss after:2024/01/01')."""
    engine = await get_engine()
    result = await engine.execute_tool("gmail_search", {"query": query, "max_results": max_results})
    return (
        str(result.data)
        if hasattr(result, "success") and result.success
        else f"Error: {getattr(result, 'error', 'Unknown')}"
    )


@mcp.tool()
async def espn_scoreboard() -> str:
    """Get real-time NBA scores, game status, and today's schedule."""
    engine = await get_engine()
    result = await engine.execute_tool("espn_scoreboard", {})
    return (
        str(result.data)
        if hasattr(result, "success") and result.success
        else f"Error: {getattr(result, 'error', 'Unknown')}"
    )


async def register_dynamic_tools():
    """
    Meant for future dynamic registration. Currently using explicit hero tools
    above to ensure valid JSON schemas for local LLMs (Qwen/Llama).
    """
    logger.info("mcp_hero_tools_ready")


@mcp.resource("schema://semantic/{entity}")
async def get_semantic_facts(entity: str) -> str:
    """
    Retrieve facts and relationships for a specific entity from the Knowledge Graph.
    """
    get_semantic_memory()
    # Mock/Simple implementation for now - should query Neo4j
    # In a real scenario, we'd use semantic.get_entity(entity)
    return f"Semantic data for {entity} would be retrieved from Neo4j here."


@mcp.resource("schema://memory/episodes/{query}")
async def search_episodic_memory(query: str) -> str:
    """
    Search past experiences and interactions related to the query.
    """
    episodic = get_episodic_memory()
    # Search Qdrant for similar episodes
    results = await episodic.search(query=query, limit=3)

    if not results:
        return "No relevant episodes found."

    formatted = []
    for r in results:
        formatted.append(f"--- Episode ---\n{r.content}\nScore: {r.score}")

    return "\n\n".join(formatted)


@mcp.prompt("analyze_market")
def analyze_market_prompt(asset: str) -> str:
    """
    A template for performing a deep market analysis using Me4BrAIn skills.
    """
    return f"Analyze the market for {asset}. Use coingecko_price for current data and search_news for recent events. Then synthesize a recommendation."
