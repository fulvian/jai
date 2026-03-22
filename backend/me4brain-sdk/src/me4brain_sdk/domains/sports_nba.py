"""Sports/NBA Domain - NBA analytics and stats."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class NBAPlayer(BaseModel):
    """NBA player information."""

    id: int
    first_name: str
    last_name: str
    position: str | None = None
    team: str | None = None
    height: str | None = None
    weight: str | None = None


class NBATeam(BaseModel):
    """NBA team information."""

    id: int
    name: str
    full_name: str
    abbreviation: str
    city: str
    conference: str | None = None
    division: str | None = None


class NBAGame(BaseModel):
    """NBA game information."""

    id: int
    date: str
    home_team: str
    home_score: int = 0
    visitor_team: str
    visitor_score: int = 0
    status: str = "scheduled"
    season: int | None = None


class NBAPlayerStats(BaseModel):
    """NBA player season stats."""

    player_id: int
    player_name: str
    team: str | None = None
    games_played: int = 0
    points_per_game: float = 0.0
    rebounds_per_game: float = 0.0
    assists_per_game: float = 0.0
    steals_per_game: float = 0.0
    blocks_per_game: float = 0.0
    field_goal_pct: float = 0.0
    three_point_pct: float = 0.0


class SportsNBADomain(BaseDomain):
    """Sports/NBA domain - NBA analytics and statistics.

    Example:
        # Search players
        players = await client.domains.sports_nba.search_players("LeBron")

        # Get player stats
        stats = await client.domains.sports_nba.player_stats(player_id=123)

        # Get today's games
        games = await client.domains.sports_nba.games_today()
    """

    @property
    def domain_name(self) -> str:
        return "sports_nba"

    async def search_players(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[NBAPlayer]:
        """Search NBA players by name.

        Args:
            query: Player name search
            max_results: Maximum results

        Returns:
            List of matching players
        """
        result = await self._execute_tool(
            "nba_search_players",
            {"query": query, "max_results": max_results},
        )
        players = result.get("result", {}).get("players", [])
        return [NBAPlayer.model_validate(p) for p in players]

    async def get_player(self, player_id: int) -> NBAPlayer:
        """Get player details by ID.

        Args:
            player_id: Player ID

        Returns:
            Player information
        """
        result = await self._execute_tool("nba_player", {"player_id": player_id})
        return NBAPlayer.model_validate(result.get("result", {}))

    async def player_stats(
        self,
        player_id: int,
        season: int | None = None,
    ) -> NBAPlayerStats:
        """Get player season statistics.

        Args:
            player_id: Player ID
            season: Season year (e.g., 2024 for 2024-25)

        Returns:
            Player season stats
        """
        params: dict[str, Any] = {"player_id": player_id}
        if season:
            params["season"] = season
        result = await self._execute_tool("nba_player_stats", params)
        return NBAPlayerStats.model_validate(result.get("result", {}))

    async def list_teams(self) -> list[NBATeam]:
        """List all NBA teams.

        Returns:
            List of NBA teams
        """
        result = await self._execute_tool("nba_teams", {})
        teams = result.get("result", {}).get("teams", [])
        return [NBATeam.model_validate(t) for t in teams]

    async def get_team(self, team_id: int) -> NBATeam:
        """Get team details by ID.

        Args:
            team_id: Team ID

        Returns:
            Team information
        """
        result = await self._execute_tool("nba_team", {"team_id": team_id})
        return NBATeam.model_validate(result.get("result", {}))

    async def games_today(self) -> list[NBAGame]:
        """Get today's NBA games.

        Returns:
            List of today's games
        """
        result = await self._execute_tool("nba_games_today", {})
        games = result.get("result", {}).get("games", [])
        return [NBAGame.model_validate(g) for g in games]

    async def games_by_date(self, date: str) -> list[NBAGame]:
        """Get NBA games by date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            List of games
        """
        result = await self._execute_tool("nba_games", {"date": date})
        games = result.get("result", {}).get("games", [])
        return [NBAGame.model_validate(g) for g in games]
