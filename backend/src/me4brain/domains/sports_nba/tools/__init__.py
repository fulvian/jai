"""NBA Tools Package.

Esporta tool NBA per uso da SportsNBAHandler.
"""

from me4brain.domains.sports_nba.tools.nba_api import (
    AVAILABLE_TOOLS as NBA_API_TOOLS,
    balldontlie_games,
    balldontlie_players,
    balldontlie_stats,
    balldontlie_teams,
    espn_injuries,
    espn_scoreboard,
    execute_tool as nba_api_execute,
    get_executors as get_nba_api_executors,
    get_tool_definitions as get_nba_api_definitions,
    odds_api_odds,
)
from me4brain.domains.sports_nba.tools.betting_analyzer import (
    nba_betting_analyzer,
    get_executors as get_betting_executors,
    get_tool_definitions as get_betting_definitions,
)


# Merge definitions and executors
def get_tool_definitions():
    return get_nba_api_definitions() + get_betting_definitions()


def get_executors():
    execs = get_nba_api_executors().copy()
    execs.update(get_betting_executors())
    return execs


def execute_tool(tool_name: str, args: dict):
    execs = get_executors()
    if tool_name in execs:
        return execs[tool_name](**args)
    return {"error": f"Tool {tool_name} not found in Sports NBA domain"}


AVAILABLE_TOOLS = get_executors()

__all__ = [
    "AVAILABLE_TOOLS",
    "execute_tool",
    "get_tool_definitions",
    "get_executors",
    "balldontlie_games",
    "balldontlie_players",
    "balldontlie_stats",
    "balldontlie_teams",
    "espn_scoreboard",
    "espn_injuries",
    "odds_api_odds",
    "nba_betting_analyzer",
]
