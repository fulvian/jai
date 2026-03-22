"""Sports NBA Domain Package.

Gestisce query relative a NBA: partite, giocatori, statistiche, quote.

Tool inclusi (13):
- nba_upcoming_games
- nba_live_scoreboard
- nba_player_search
- nba_player_career_stats
- nba_player_season_stats
- nba_standings
- nba_teams
- nba_team_roster
- nba_box_scores
- nba_injury_report
- espn_nba_injuries
- nba_betting_odds
- nba_stat_leaders
"""

from me4brain.domains.sports_nba.handler import SportsNBAHandler

_handler: SportsNBAHandler | None = None


def get_handler() -> SportsNBAHandler:
    """Factory function per auto-discovery da PluginRegistry."""
    global _handler
    if _handler is None:
        _handler = SportsNBAHandler()
    return _handler


__all__ = ["get_handler", "SportsNBAHandler"]
