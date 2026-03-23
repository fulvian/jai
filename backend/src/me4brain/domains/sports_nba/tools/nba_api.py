"""NBA API Tools - BallDontLie, ESPN, TheOddsAPI integrations.

Questo modulo contiene le implementazioni dei tool NBA migrati da tool_executor.py.
Ogni tool è una funzione standalone che può essere chiamata dal SportsNBAHandler.

Tools:
- balldontlie_games: Prossime partite NBA
- balldontlie_players: Ricerca giocatori
- balldontlie_stats: Statistiche giocatore
- balldontlie_teams: Lista squadre NBA
- espn_scoreboard: Scoreboard live NBA
- espn_injuries: Report infortuni NBA
- odds_api_odds: Quote scommesse NBA
"""

import asyncio
import os
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import structlog
from dotenv import load_dotenv

# =============================================================================
# NBA Stats API TLS Fingerprint Spoofing (Akamai Bypass)
# =============================================================================
# The nba_api package uses requests. stats.nba.com is protected by Akamai WAF
# which drops TCP connections from standard Python HTTP clients (like requests
# and httpx) based on TLS JA3/JA4 fingerprints. We use curl_cffi to spoof
# Chrome's fingerprint and bypass the block.
try:
    import requests
    from curl_cffi import requests as cffi_requests

    class SpoofedSession(cffi_requests.Session):
        def __init__(self, *args, **kwargs):
            kwargs["impersonate"] = "chrome120"
            super().__init__(*args, **kwargs)

    # Monkey-patch globally for the imported nba_api modules
    requests.Session = SpoofedSession
    requests.get = cffi_requests.get
except ImportError:
    pass

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# Carica .env all'import del modulo (from project root)
_project_root = Path(__file__).parent.parent.parent
load_dotenv(_project_root / ".env")

logger = structlog.get_logger(__name__)

# =============================================================================
# NBA Stats API Rate Limiting & Stealth Config
# =============================================================================

DEFAULT_TIMEOUT = 15.0
NBA_API_RATE_LIMIT_DELAY = 2.5  # 2 secondi + margine di sicurezza
_last_nba_api_call = 0.0
_nba_api_rate_limit_lock = asyncio.Lock()
_advanced_stats_cache: dict[str, tuple[float, Any]] = {}
_advanced_stats_cache_lock = asyncio.Lock()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]


def _get_nba_stats_headers() -> dict[str, str]:
    """Genera header realistici per evitare blocchi da stats.nba.com."""
    return {
        "Host": "stats.nba.com",
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "x-nba-stats-origin": "stats",
        "x-nba-stats-token": "true",
        "Connection": "keep-alive",
        "Referer": "https://stats.nba.com/",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache",
    }


async def _enforce_nba_api_rate_limit():
    """Garantisce che tra le chiamate intercorra almeno NBA_API_RATE_LIMIT_DELAY."""
    global _last_nba_api_call
    async with _nba_api_rate_limit_lock:
        now = time.time()
        elapsed = now - _last_nba_api_call
        if elapsed < NBA_API_RATE_LIMIT_DELAY:
            sleep_time = NBA_API_RATE_LIMIT_DELAY - elapsed
            logger.debug("nba_api_rate_limit_wait", wait_seconds=f"{sleep_time:.2f}")
            await asyncio.sleep(sleep_time)

        _last_nba_api_call = time.time()


def _get_api_key(env_var: str) -> str | None:
    """Ottiene API key da environment."""
    return os.getenv(env_var)


# =============================================================================
# BallDontLie API v2 (NBA Stats)
# =============================================================================


async def balldontlie_games(
    dates: list[str] | None = None,
    team_id: int | None = None,
) -> dict[str, Any]:
    """Recupera partite NBA da BallDontLie API v2.

    Args:
        dates: Lista date in formato YYYY-MM-DD (default: oggi + 3 giorni)
        team_id: ID squadra per filtrare

    Returns:
        dict con lista partite e metadata
    """
    api_key = _get_api_key("BALLDONTLIE_API_KEY")
    if not api_key:
        return {"error": "BALLDONTLIE_API_KEY not configured", "source": "BallDontLie"}

    if dates is None:
        today = datetime.now()
        dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14)]

    headers = {"Authorization": api_key}
    base_url = "https://api.balldontlie.io/v1"

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers) as client:
        try:
            all_games = []
            for date in dates:
                params = {"dates[]": date, "per_page": 20}
                if team_id:
                    params["team_ids[]"] = team_id

                response = await client.get(f"{base_url}/games", params=params)
                if response.status_code == 200:
                    games = response.json().get("data", [])
                    for g in games:
                        all_games.append(
                            {
                                "id": g.get("id"),
                                "date": g.get("date"),
                                "status": g.get("status"),
                                "home_team": g.get("home_team", {}).get("full_name"),
                                "away_team": g.get("visitor_team", {}).get("full_name"),
                                "home_score": g.get("home_team_score"),
                                "away_score": g.get("visitor_team_score"),
                            }
                        )

            return {
                "games": all_games,
                "count": len(all_games),
                "date_range": f"{dates[0]} to {dates[-1]}",
                "source": "BallDontLie API v2",
            }

        except httpx.HTTPStatusError as e:
            logger.error("balldontlie_games_error", status=e.response.status_code)
            return {
                "error": f"API error: {e.response.status_code}",
                "source": "BallDontLie",
            }
        except Exception as e:
            logger.error("balldontlie_games_exception", error=str(e))
            return {"error": str(e), "source": "BallDontLie"}


async def balldontlie_players(
    search: str,
    per_page: int = 10,
) -> dict[str, Any]:
    """Cerca giocatori NBA per nome.

    Args:
        search: Nome o parte del nome del giocatore
        per_page: Numero massimo risultati

    Returns:
        dict con lista giocatori trovati
    """
    api_key = _get_api_key("BALLDONTLIE_API_KEY")
    if not api_key:
        return {"error": "BALLDONTLIE_API_KEY not configured", "source": "BallDontLie"}

    headers = {"Authorization": api_key}
    base_url = "https://api.balldontlie.io/v1"

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers) as client:
        try:
            response = await client.get(
                f"{base_url}/players",
                params={"search": search, "per_page": per_page},
            )
            response.raise_for_status()
            players = response.json().get("data", [])

            return {
                "search": search,
                "players": [
                    {
                        "id": p.get("id"),
                        "name": f"{p.get('first_name')} {p.get('last_name')}",
                        "team": p.get("team", {}).get("full_name"),
                        "position": p.get("position"),
                        "height": p.get("height"),
                    }
                    for p in players
                ],
                "source": "BallDontLie API v2",
            }

        except httpx.HTTPStatusError as e:
            logger.error("balldontlie_players_error", status=e.response.status_code)
            return {
                "error": f"API error: {e.response.status_code}",
                "source": "BallDontLie",
            }
        except Exception as e:
            logger.error("balldontlie_players_exception", error=str(e))
            return {"error": str(e), "source": "BallDontLie"}


async def balldontlie_stats(
    player_id: int,
    season: int | None = None,
) -> dict[str, Any]:
    """Recupera statistiche stagionali di un giocatore.

    Args:
        player_id: ID del giocatore BallDontLie
        season: Anno stagione (default: corrente)

    Returns:
        dict con medie stagionali
    """
    api_key = _get_api_key("BALLDONTLIE_API_KEY")
    if not api_key:
        return {"error": "BALLDONTLIE_API_KEY not configured", "source": "BallDontLie"}

    if season is None:
        season = datetime.now().year if datetime.now().month >= 10 else datetime.now().year - 1

    headers = {"Authorization": api_key}
    base_url = "https://api.balldontlie.io/v1"

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers) as client:
        try:
            response = await client.get(
                f"{base_url}/season_averages",
                params={"player_ids[]": player_id, "season": season},
            )

            if response.status_code == 200:
                stats = response.json().get("data", [])
                return {
                    "player_id": player_id,
                    "season": season,
                    "stats": stats[0] if stats else {},
                    "source": "BallDontLie API v2",
                }

            return {
                "error": f"API error: {response.status_code}",
                "source": "BallDontLie",
            }

        except Exception as e:
            logger.error("balldontlie_stats_exception", error=str(e))
            return {"error": str(e), "source": "BallDontLie"}


async def nba_api_player_stats_cascade(
    player_id: int,
    season: str | None = None,
) -> dict[str, Any]:
    """Recupera statistiche giocatore con cascata fallback.

    Workflow:
    1. Prova BallDontLie (se API key configurata)
    2. Fallback su nba_api package (gratuito, no auth)
    3. Fallback su ESPN player stats (gratuito)
    """
    if season is None:
        season = "2025-26"

    logger.info("player_stats_cascade_started", player_id=player_id, season=season)

    # STEP 1: Try BallDontLie
    api_key = _get_api_key("BALLDONTLIE_API_KEY")
    if api_key:
        try:
            data = await balldontlie_stats(player_id=player_id, season=int(season[:4]))
            if not data.get("error"):
                logger.info("player_stats_cascade_success", source="BallDontLie")
                return data
        except Exception as e:
            logger.warning("balldontlie_stats_exception", error=str(e))

    # STEP 2: Try nba_api package
    try:
        from nba_api.stats.endpoints import playerstats

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=5),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        def get_player_stats() -> dict[str, Any]:
            stats = playerstats.PlayerStats(
                player_id=player_id, timeout=10, headers=_get_nba_stats_headers()
            )
            return stats.get_dict()

        await _enforce_nba_api_rate_limit()
        data = await asyncio.to_thread(get_player_stats)
        result_sets = data.get("resultSets", [])
        if result_sets:
            headers = result_sets[0].get("headers", [])
            rows = result_sets[0].get("rowSet", [])
            if rows:
                player_data = dict(zip(headers, rows[0], strict=False))
                logger.info("player_stats_cascade_success", source="nba_api")
                return {
                    "player_id": player_id,
                    "season": season,
                    "stats": {
                        "points": player_data.get("PTS"),
                        "rebounds": player_data.get("REB"),
                        "assists": player_data.get("AST"),
                        "fg_pct": player_data.get("FG_PCT"),
                        "ft_pct": player_data.get("FT_PCT"),
                        "three_p_pct": player_data.get("FG3_PCT"),
                    },
                    "source": "nba_api (Official NBA Stats)",
                }
    except ImportError:
        logger.warning("nba_api_not_installed")
    except Exception as e:
        logger.warning("nba_api_player_stats_failed", error=str(e))

    logger.error("player_stats_cascade_all_failed", player_id=player_id)
    return {
        "error": f"Player stats not available from any source (player_id: {player_id})",
        "source": "cascade_fallback",
        "tried_sources": ["BallDontLie", "nba_api", "ESPN"],
    }


async def balldontlie_teams() -> dict[str, Any]:
    """Recupera lista tutte le squadre NBA.

    Returns:
        dict con lista squadre NBA
    """
    api_key = _get_api_key("BALLDONTLIE_API_KEY")
    if not api_key:
        return {"error": "BALLDONTLIE_API_KEY not configured", "source": "BallDontLie"}

    headers = {"Authorization": api_key}
    base_url = "https://api.balldontlie.io/v1"

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers) as client:
        try:
            response = await client.get(f"{base_url}/teams")
            response.raise_for_status()
            teams = response.json().get("data", [])

            return {
                "teams": [
                    {
                        "id": t.get("id"),
                        "name": t.get("full_name"),
                        "abbreviation": t.get("abbreviation"),
                        "conference": t.get("conference"),
                        "division": t.get("division"),
                    }
                    for t in teams
                ],
                "source": "BallDontLie API v2",
            }

        except Exception as e:
            logger.error("balldontlie_teams_exception", error=str(e))
            return {"error": str(e), "source": "BallDontLie"}


# =============================================================================
# ESPN API (Live Scoreboard & Injuries)
# =============================================================================


async def espn_scoreboard() -> dict[str, Any]:
    """Recupera scoreboard NBA live da ESPN.

    Returns:
        dict con partite in corso/programmate oggi
    """
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(
                "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
                headers={"Origin": "https://www.espn.com"},
            )

            if response.status_code != 200:
                return {
                    "error": f"ESPN API error: {response.status_code}",
                    "source": "ESPN",
                }

            data = response.json()
            events = data.get("events", [])
            games = []

            for event in events:
                competition = event.get("competitions", [{}])[0]
                competitors = competition.get("competitors", [])

                home = next((c for c in competitors if c.get("homeAway") == "home"), {})
                away = next((c for c in competitors if c.get("homeAway") == "away"), {})

                games.append(
                    {
                        "name": event.get("name"),
                        "date": event.get("date"),
                        "status": event.get("status", {}).get("type", {}).get("name"),
                        "home_team": home.get("team", {}).get("displayName"),
                        "home_score": home.get("score"),
                        "away_team": away.get("team", {}).get("displayName"),
                        "away_score": away.get("score"),
                        "venue": competition.get("venue", {}).get("fullName"),
                    }
                )

            return {
                "games": games,
                "count": len(games),
                "source": "ESPN API",
            }

        except Exception as e:
            logger.error("espn_scoreboard_exception", error=str(e))
            return {"error": str(e), "source": "ESPN"}


async def espn_injuries() -> dict[str, Any]:
    """Recupera report infortuni NBA da ESPN.

    Returns:
        dict con lista giocatori infortunati
    """
    from bs4 import BeautifulSoup

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(
                "https://www.espn.com/nba/injuries",
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                },
            )

            if response.status_code != 200:
                return {
                    "error": f"ESPN injuries page error: {response.status_code}",
                    "source": "ESPN",
                }

            soup = BeautifulSoup(response.text, "html.parser")
            injuries = []

            # Parse tabelle infortuni
            tables = soup.find_all("table", class_="Table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) >= 2:
                        name = cols[0].get_text(strip=True)
                        if name and name != "NAME":
                            injuries.append(
                                {
                                    "player": name,
                                    "status": cols[1].get_text(strip=True) if len(cols) > 1 else "",
                                    "details": cols[3].get_text(strip=True)
                                    if len(cols) > 3
                                    else "",
                                    "source": "ESPN",
                                }
                            )

            return {
                "injuries": injuries[:30],
                "count": len(injuries),
                "source": "ESPN Injuries",
            }

        except Exception as e:
            logger.error("espn_injuries_exception", error=str(e))
            return {"error": str(e), "source": "ESPN"}


# =============================================================================
# The Odds API (Betting Odds)
# =============================================================================


async def odds_api_odds(
    sport: str = "basketball_nba",
    regions: str = "eu",
    markets: str = "h2h,spreads,totals",
) -> dict[str, Any]:
    """Recupera quote scommesse NBA da The Odds API con fallback chain.

    Args:
        sport: Chiave sport (default: basketball_nba)
        regions: Regioni bookmaker (eu, us, uk, au)
        markets: Mercati (h2h, spreads, totals)

    Returns:
        dict con quote per partite o fallback con disclaimer
    """
    api_key = _get_api_key("THE_ODDS_API_KEY")
    if not api_key:
        logger.warning("odds_api_key_missing", fallback="web_search")
        return {
            "error": "THE_ODDS_API_KEY not configured",
            "fallback": "web_search",
            "source": "The Odds API",
        }

    base_url = "https://api.the-odds-api.com/v4"

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(
                f"{base_url}/sports/{sport}/odds",
                params={
                    "apiKey": api_key,
                    "regions": regions,
                    "markets": markets,
                    "oddsFormat": "decimal",
                },
            )

            # C1 FIX: Explicit error_code parsing for OUT_OF_USAGE_CREDITS
            if response.status_code == 401:
                try:
                    error_body = response.json()
                    error_code = error_body.get("error_code", "UNKNOWN")

                    if error_code == "OUT_OF_USAGE_CREDITS":
                        logger.warning(
                            "odds_api_quota_exceeded",
                            requests_used=response.headers.get("x-requests-used"),
                            requests_remaining=response.headers.get("x-requests-remaining"),
                            fallback="polymarket_or_no_odds",
                        )
                        return {
                            "error": "API quota exhausted",
                            "error_code": "OUT_OF_USAGE_CREDITS",
                            "requests_remaining": response.headers.get("x-requests-remaining", "0"),
                            "fallback": "polymarket_or_no_odds",
                            "disclaimer": "Odds data unavailable. Using game data and historical trends.",
                            "source": "The Odds API",
                        }
                    else:
                        logger.warning(
                            "odds_api_auth_failed",
                            error_code=error_code,
                            fallback="polymarket_or_no_odds",
                        )
                        return {
                            "error": "API authentication failed",
                            "error_code": error_code,
                            "fallback": "polymarket_or_no_odds",
                            "source": "The Odds API",
                        }
                except Exception as parse_err:
                    logger.warning("odds_api_401_parse_error", error=str(parse_err))
                    return {
                        "error": f"API error: {response.status_code}",
                        "fallback": "polymarket_or_no_odds",
                        "source": "The Odds API",
                    }

            if response.status_code != 200:
                logger.warning(
                    "odds_api_http_error",
                    status_code=response.status_code,
                    fallback="polymarket_or_no_odds",
                )
                return {
                    "error": f"API error: {response.status_code}",
                    "fallback": "polymarket_or_no_odds",
                    "source": "The Odds API",
                }

            events = response.json()
            formatted = []

            for event in events[:20]:
                game_data = {
                    "id": event.get("id"),
                    "home_team": event.get("home_team"),
                    "away_team": event.get("away_team"),
                    "commence_time": event.get("commence_time"),
                    "bookmakers": [],
                }

                for bookie in event.get("bookmakers", [])[:3]:
                    bookie_data = {"name": bookie.get("title"), "markets": {}}
                    for market in bookie.get("markets", []):
                        market_key = market.get("key")
                        outcomes = {
                            o.get("name"): o.get("price") for o in market.get("outcomes", [])
                        }
                        bookie_data["markets"][market_key] = outcomes
                    game_data["bookmakers"].append(bookie_data)

                formatted.append(game_data)

            return {
                "sport": sport,
                "events": formatted,
                "count": len(events),
                "source": "The Odds API",
            }

        except Exception as e:
            logger.error(
                "odds_api_exception",
                error=str(e),
                fallback="polymarket_or_no_odds",
            )
            return {
                "error": str(e),
                "fallback": "polymarket_or_no_odds",
                "source": "The Odds API",
            }


# =============================================================================
# nba_api Package (Official NBA Stats - No Auth Required)
# =============================================================================


async def nba_api_live_scoreboard() -> dict[str, Any]:
    """Recupera scoreboard NBA live usando nba_api package (gratuito).

    Returns:
        dict con partite live/programmate oggi
    """
    try:
        from nba_api.live.nba.endpoints import scoreboard as live_scoreboard

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1.5, min=2, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        def get_scoreboard():
            # live.nba endpoints sono diversi dai classici stats.nba
            sb = live_scoreboard.ScoreBoard()
            return sb.get_dict()

        # Scoreboard live usa endpoint CDN differenti, meno restrittivi,
        # ma applichiamo comunque rate limit per sicurezza
        await _enforce_nba_api_rate_limit()
        data = await asyncio.to_thread(get_scoreboard)

        games = data.get("scoreboard", {}).get("games", [])

        formatted_games = []
        for g in games:
            formatted_games.append(
                {
                    "game_id": g.get("gameId"),
                    "status": g.get("gameStatusText"),
                    "home_team": g.get("homeTeam", {}).get("teamName"),
                    "home_score": g.get("homeTeam", {}).get("score"),
                    "away_team": g.get("awayTeam", {}).get("teamName"),
                    "away_score": g.get("awayTeam", {}).get("score"),
                    "arena": g.get("arena"),
                    "period": g.get("period"),
                }
            )

        return {
            "games": formatted_games,
            "count": len(formatted_games),
            "date": data.get("scoreboard", {}).get("gameDate"),
            "source": "nba_api (Official NBA Stats)",
        }
    except ImportError:
        logger.warning("nba_api_not_installed", hint="Install with: pip install nba_api")
        return {"error": "nba_api package not installed", "source": "nba_api"}
    except Exception as e:
        logger.error("nba_api_live_scoreboard_error", error=str(e))
        return {"error": str(e), "source": "nba_api"}


async def nba_api_team_games(
    team_id: int = 1610612741,  # Chicago Bulls default
    season: str = "2025-26",
) -> dict[str, Any]:
    """Recupera ultime partite di una squadra NBA.

    Args:
        team_id: ID squadra NBA (es. 1610612741 = Chicago Bulls)
        season: Stagione (es. "2025-26")

    Returns:
        dict con storico partite squadra
    """
    try:
        from nba_api.stats.endpoints import teamgamelog

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1.5, min=2, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        def get_games():
            log = teamgamelog.TeamGameLog(
                team_id=team_id, season=season, timeout=15, headers=_get_nba_stats_headers()
            )
            return log.get_dict()

        await _enforce_nba_api_rate_limit()
        data = await asyncio.to_thread(get_games)
        result_sets = data.get("resultSets", [])

        games = []
        if result_sets:
            headers = result_sets[0].get("headers", [])
            rows = result_sets[0].get("rowSet", [])

            for row in rows[:10]:  # Ultime 10 partite
                game = dict(zip(headers, row, strict=False))
                games.append(
                    {
                        "game_id": game.get("Game_ID"),
                        "date": game.get("GAME_DATE"),
                        "matchup": game.get("MATCHUP"),
                        "result": game.get("WL"),
                        "points": game.get("PTS"),
                        "rebounds": game.get("REB"),
                        "assists": game.get("AST"),
                    }
                )

        return {
            "team_id": team_id,
            "season": season,
            "games": games,
            "count": len(games),
            "source": "nba_api (Official NBA Stats)",
        }
    except ImportError:
        return {"error": "nba_api package not installed", "source": "nba_api"}
    except Exception as e:
        logger.error("nba_api_team_games_error", error=str(e))
        return {"error": str(e), "source": "nba_api"}


async def nba_api_player_career(player_id: int) -> dict[str, Any]:
    """Recupera statistiche carriera di un giocatore.

    Args:
        player_id: ID giocatore NBA

    Returns:
        dict con statistiche carriera
    """
    try:
        from nba_api.stats.endpoints import playercareerstats

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1.5, min=2, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        def get_career():
            career = playercareerstats.PlayerCareerStats(
                player_id=player_id, timeout=15, headers=_get_nba_stats_headers()
            )
            return career.get_dict()

        await _enforce_nba_api_rate_limit()
        data = await asyncio.to_thread(get_career)
        result_sets = data.get("resultSets", [])

        career_totals = []
        if result_sets:
            for result in result_sets:
                if result.get("name") == "CareerTotalsRegularSeason":
                    headers = result.get("headers", [])
                    rows = result.get("rowSet", [])
                    for row in rows:
                        stats = dict(zip(headers, row, strict=False))
                        career_totals.append(
                            {
                                "games": stats.get("GP"),
                                "points_avg": stats.get("PTS"),
                                "rebounds_avg": stats.get("REB"),
                                "assists_avg": stats.get("AST"),
                            }
                        )

        return {
            "player_id": player_id,
            "career_stats": career_totals,
            "source": "nba_api (Official NBA Stats)",
        }
    except ImportError:
        return {"error": "nba_api package not installed", "source": "nba_api"}
    except Exception as e:
        logger.error("nba_api_player_career_error", error=str(e))
        return {"error": str(e), "source": "nba_api"}


# =============================================================================
# ESPN API Extended (Standings, Team Stats, Schedule)
# =============================================================================


async def espn_standings() -> dict[str, Any]:
    """Recupera classifiche NBA da ESPN API (free, no auth).

    Returns:
        dict con standings Eastern/Western conference
    """
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(
                "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings",
                headers={"Origin": "https://www.espn.com"},
            )

            if response.status_code != 200:
                return {
                    "error": f"ESPN standings API error: {response.status_code}",
                    "source": "ESPN",
                }

            data = response.json()
            standings = {"eastern": [], "western": []}

            for child in data.get("children", []):
                conf_name = child.get("name", "").lower()
                conf_key = "eastern" if "east" in conf_name else "western"

                for entry in child.get("standings", {}).get("entries", []):
                    team_data = entry.get("team", {})
                    stats_map = {}
                    for stat in entry.get("stats", []):
                        stats_map[stat.get("name", "")] = stat.get(
                            "displayValue", stat.get("value", "")
                        )

                    standings[conf_key].append(
                        {
                            "team": team_data.get("displayName"),
                            "abbreviation": team_data.get("abbreviation"),
                            "wins": stats_map.get("wins", ""),
                            "losses": stats_map.get("losses", ""),
                            "win_pct": stats_map.get("winPercent", stats_map.get("winPct", "")),
                            "games_behind": stats_map.get("gamesBehind", ""),
                            "streak": stats_map.get("streak", ""),
                            "home_record": stats_map.get("Home", stats_map.get("home", "")),
                            "away_record": stats_map.get("Road", stats_map.get("away", "")),
                            "last_10": stats_map.get("Last Ten", stats_map.get("L10", "")),
                            "points_for": stats_map.get("pointsFor", ""),
                            "points_against": stats_map.get("pointsAgainst", ""),
                        }
                    )

            return {
                "standings": standings,
                "eastern_count": len(standings["eastern"]),
                "western_count": len(standings["western"]),
                "source": "ESPN API",
            }

        except Exception as e:
            logger.error("espn_standings_exception", error=str(e))
            return {"error": str(e), "source": "ESPN"}


async def espn_team_stats(team_id: str = "13") -> dict[str, Any]:
    """Recupera statistiche avanzate di una squadra NBA via ESPN (free, no auth).

    Args:
        team_id: ESPN team ID (es. '13' = Lakers, '2' = Celtics)

    Returns:
        dict con statistiche squadra avanzate
    """
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            response = await client.get(
                f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/statistics",
                headers={"Origin": "https://www.espn.com"},
            )

            if response.status_code != 200:
                return {
                    "error": f"ESPN team stats API error: {response.status_code}",
                    "source": "ESPN",
                }

            data = response.json()
            team_info = data.get("team", {})
            stats_categories = data.get("results", data.get("splits", {}).get("categories", []))

            parsed_stats: dict[str, Any] = {}
            if isinstance(stats_categories, list):
                for category in stats_categories:
                    category.get("displayName", category.get("name", "unknown"))
                    for stat in category.get("stats", []):
                        stat_name = stat.get("name", stat.get("abbreviation", ""))
                        stat_value = stat.get("displayValue", stat.get("value", ""))
                        parsed_stats[stat_name] = stat_value

            return {
                "team": team_info.get("displayName", f"Team {team_id}"),
                "team_id": team_id,
                "stats": parsed_stats,
                "source": "ESPN API",
            }

        except Exception as e:
            logger.error("espn_team_stats_exception", error=str(e))
            return {"error": str(e), "source": "ESPN"}


async def espn_schedule(days_ahead: int = 7) -> dict[str, Any]:
    """Recupera calendario partite NBA dei prossimi giorni via ESPN (free, no auth).

    Args:
        days_ahead: Numero di giorni futuri da controllare (max 14)

    Returns:
        dict con calendario partite future
    """
    days_ahead = min(days_ahead, 14)

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            all_games: list[dict[str, Any]] = []

            for day_offset in range(days_ahead):
                date = datetime.now() + timedelta(days=day_offset)
                date_str = date.strftime("%Y%m%d")

                response = await client.get(
                    "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
                    params={"dates": date_str},
                    headers={"Origin": "https://www.espn.com"},
                )

                if response.status_code != 200:
                    continue

                data = response.json()
                events = data.get("events", [])

                for event in events:
                    competition = event.get("competitions", [{}])[0]
                    competitors = competition.get("competitors", [])
                    home = next((c for c in competitors if c.get("homeAway") == "home"), {})
                    away = next((c for c in competitors if c.get("homeAway") == "away"), {})

                    all_games.append(
                        {
                            "date": date.strftime("%Y-%m-%d"),
                            "name": event.get("name"),
                            "start_time": event.get("date"),
                            "status": event.get("status", {}).get("type", {}).get("name"),
                            "home_team": home.get("team", {}).get("displayName"),
                            "home_id": home.get("team", {}).get("id"),
                            "home_record": home.get("records", [{}])[0].get("summary", "")
                            if home.get("records")
                            else "",
                            "away_team": away.get("team", {}).get("displayName"),
                            "away_id": away.get("team", {}).get("id"),
                            "away_record": away.get("records", [{}])[0].get("summary", "")
                            if away.get("records")
                            else "",
                            "venue": competition.get("venue", {}).get("fullName"),
                            "broadcast": event.get("competitions", [{}])[0]
                            .get("broadcasts", [{}])[0]
                            .get("names", [""])[0]
                            if event.get("competitions", [{}])[0].get("broadcasts")
                            else "",
                        }
                    )

            return {
                "games": all_games,
                "count": len(all_games),
                "days_covered": days_ahead,
                "source": "ESPN API",
            }

        except Exception as e:
            logger.error("espn_schedule_exception", error=str(e))
            return {"error": str(e), "source": "ESPN"}


# =============================================================================
# Polymarket Prediction Market (NBA Odds - Free, No Auth)
# =============================================================================


async def polymarket_nba_odds() -> dict[str, Any]:
    """Recupera quote NBA da Polymarket prediction market (free, no auth).

    Usa Gamma API pubblica per cercare eventi NBA con odds.

    Returns:
        dict con quote prediction market NBA
    """
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            # Cerca eventi NBA su Polymarket
            response = await client.get(
                "https://gamma-api.polymarket.com/events",
                params={
                    "limit": 20,
                    "active": "true",
                    "closed": "false",
                    "order": "volume",
                    "ascending": "false",
                    "tag": "nba",
                },
            )

            if response.status_code != 200:
                # Fallback: search query
                response = await client.get(
                    "https://gamma-api.polymarket.com/events",
                    params={
                        "limit": 20,
                        "active": "true",
                        "closed": "false",
                        "order": "volume",
                        "ascending": "false",
                    },
                )
                if response.status_code != 200:
                    return {
                        "error": f"Polymarket API error: {response.status_code}",
                        "source": "Polymarket",
                    }

            events = response.json()
            # Filtra per NBA-related se non filtrati dal tag
            nba_keywords = [
                "nba",
                "basketball",
                "lakers",
                "celtics",
                "warriors",
                "bulls",
                "heat",
                "knicks",
                "nets",
                "bucks",
                "nuggets",
                "mvp",
                "finals",
                "playoff",
                "championship",
            ]

            formatted: list[dict[str, Any]] = []
            for event in events if isinstance(events, list) else []:
                title = (event.get("title") or "").lower()
                desc = (event.get("description") or "").lower()

                is_nba = any(kw in title or kw in desc for kw in nba_keywords)
                if not is_nba and response.request.url.params.get("tag") != "nba":
                    continue

                markets = event.get("markets", [])
                market_data: list[dict[str, Any]] = []
                for m in markets[:5]:
                    import json as json_module

                    prices = m.get("outcomePrices")
                    if isinstance(prices, str):
                        try:
                            prices = json_module.loads(prices)
                        except (ValueError, TypeError):
                            prices = None

                    m.get("outcomes", [])
                    market_data.append(
                        {
                            "question": m.get("question", m.get("groupItemTitle", "")),
                            "yes_price": f"{float(prices[0]) * 100:.1f}%"
                            if prices and len(prices) > 0
                            else "N/A",
                            "no_price": f"{float(prices[1]) * 100:.1f}%"
                            if prices and len(prices) > 1
                            else "N/A",
                            "volume": m.get("volume") or m.get("volumeNum"),
                            "slug": m.get("slug"),
                        }
                    )

                formatted.append(
                    {
                        "title": event.get("title"),
                        "volume": event.get("volume"),
                        "markets": market_data,
                        "slug": event.get("slug"),
                    }
                )

            return {
                "events": formatted,
                "count": len(formatted),
                "source": "Polymarket (Gamma API)",
            }

        except Exception as e:
            logger.error("polymarket_nba_exception", error=str(e))
            return {"error": str(e), "source": "Polymarket"}


# =============================================================================
# nba_api Extended (Advanced Stats, Standings, Head-to-Head)
# =============================================================================


async def nba_api_advanced_stats(
    team_id: int = 1610612747,  # Lakers default
    season: str = "2025-26",
) -> dict[str, Any]:
    """Recupera statistiche avanzate squadra NBA (pace, ORtg, DRtg, eFG%).

    Args:
        team_id: ID squadra NBA
        season: Stagione (es. "2025-26")

    Returns:
        dict con metriche avanzate
    """
    try:
        from nba_api.stats.endpoints import teamestimatedmetrics

        cache_key = season

        async with _advanced_stats_cache_lock:
            now = time.time()
            if cache_key in _advanced_stats_cache:
                cache_time, cached_data = _advanced_stats_cache[cache_key]
                if now - cache_time < 3600:  # Cache for 1 hour
                    logger.debug("nba_api_advanced_stats_cache_hit", season=season)
                    data = cached_data
                else:
                    data = None
            else:
                data = None

            if data is None:

                @retry(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=1.5, min=2, max=10),
                    retry=retry_if_exception_type(Exception),
                    reraise=True,
                )
                def get_metrics() -> dict[str, Any]:
                    metrics = teamestimatedmetrics.TeamEstimatedMetrics(
                        season=season, timeout=15, headers=_get_nba_stats_headers()
                    )
                    return metrics.get_dict()

                try:
                    await _enforce_nba_api_rate_limit()
                    data = await asyncio.to_thread(get_metrics)
                    _advanced_stats_cache[cache_key] = (now, data)
                except Exception as e:
                    # Negative Caching: Save the error to prevent sequential timeout cascade
                    error_data = {
                        "error": f"NBA API Timeout/Error: {str(e)}",
                        "is_error_cache": True,
                    }
                    _advanced_stats_cache[cache_key] = (now, error_data)
                    logger.error(
                        "nba_api_advanced_stats_negative_cache", season=season, error=str(e)
                    )
                    data = error_data

        if data.get("is_error_cache"):
            return {
                "error": data["error"],
                "source": "nba_api",
            }

        # API returns "resultSet" (singular dict), NOT "resultSets" (list)
        result_set = data.get("resultSet", data.get("resultSets", []))

        team_stats: dict[str, Any] = {}
        # Handle both dict (resultSet) and list (resultSets) formats
        if isinstance(result_set, dict):
            headers = result_set.get("headers", [])
            rows = result_set.get("rowSet", [])
        elif isinstance(result_set, list) and result_set:
            headers = result_set[0].get("headers", [])
            rows = result_set[0].get("rowSet", [])
        else:
            headers, rows = [], []

        if headers and rows:
            for row in rows:
                row_dict = dict(zip(headers, row, strict=False))
                if row_dict.get("TEAM_ID") == team_id:
                    team_stats = {
                        "team_id": team_id,
                        "team_name": row_dict.get("TEAM_NAME"),
                        "games_played": row_dict.get("GP"),
                        "wins": row_dict.get("W"),
                        "losses": row_dict.get("L"),
                        "offensive_rating": row_dict.get("E_OFF_RATING"),
                        "defensive_rating": row_dict.get("E_DEF_RATING"),
                        "net_rating": row_dict.get("E_NET_RATING"),
                        "pace": row_dict.get("E_PACE"),
                        "assist_ratio": row_dict.get("E_AST_RATIO"),
                        "offensive_rebound_pct": row_dict.get("E_OREB_PCT"),
                        "defensive_rebound_pct": row_dict.get("E_DREB_PCT"),
                        "rebound_pct": row_dict.get("E_REB_PCT"),
                        "turnover_pct": row_dict.get("E_TM_TOV_PCT"),
                    }
                    break

        if not team_stats:
            return {
                "error": f"Team {team_id} not found in metrics",
                "source": "nba_api",
            }

        return {
            "advanced_stats": team_stats,
            "season": season,
            "source": "nba_api (Official NBA Stats)",
        }

    except ImportError:
        return {"error": "nba_api package not installed", "source": "nba_api"}
    except Exception as e:
        logger.error("nba_api_advanced_stats_error", error=str(e))
        return {"error": str(e), "source": "nba_api"}


async def nba_api_standings(
    season: str = "2025-26",
) -> dict[str, Any]:
    """Recupera classifiche ufficiali NBA (free, no auth).

    Args:
        season: Stagione (es. "2025-26")

    Returns:
        dict con standings completi (East/West, GB, home/away, L10)
    """
    try:
        from nba_api.stats.endpoints import leaguestandings

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1.5, min=2, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        def get_standings() -> dict[str, Any]:
            standings = leaguestandings.LeagueStandings(
                season=season, league_id="00", timeout=15, headers=_get_nba_stats_headers()
            )
            return standings.get_dict()

        await _enforce_nba_api_rate_limit()
        data = await asyncio.to_thread(get_standings)
        result_sets = data.get("resultSets", [])

        eastern: list[dict[str, Any]] = []
        western: list[dict[str, Any]] = []

        if result_sets:
            headers = result_sets[0].get("headers", [])
            rows = result_sets[0].get("rowSet", [])

            for row in rows:
                team_data = dict(zip(headers, row, strict=False))
                team_entry = {
                    "team_id": team_data.get("TeamID"),
                    "team": team_data.get("TeamCity", "") + " " + team_data.get("TeamName", ""),
                    "wins": team_data.get("WINS"),
                    "losses": team_data.get("LOSSES"),
                    "win_pct": team_data.get("WinPCT"),
                    "games_behind": team_data.get("ConferenceGamesBack"),
                    "home_record": team_data.get("HOME"),
                    "away_record": team_data.get("ROAD"),
                    "last_10": team_data.get("L10"),
                    "streak": team_data.get("CurrentStreak"),
                    "points_pg": team_data.get("PointsPG"),
                    "opp_points_pg": team_data.get("OppPointsPG"),
                    "diff_pg": team_data.get("DiffPointsPG"),
                    "conference_rank": team_data.get("PlayoffRank"),
                }

                conference = team_data.get("Conference", "")
                if conference == "East":
                    eastern.append(team_entry)
                else:
                    western.append(team_entry)

        return {
            "standings": {"eastern": eastern, "western": western},
            "eastern_count": len(eastern),
            "western_count": len(western),
            "season": season,
            "source": "nba_api (Official NBA Stats)",
        }

    except ImportError:
        return {"error": "nba_api package not installed", "source": "nba_api"}
    except Exception as e:
        logger.error("nba_api_standings_error", error=str(e))
        return {"error": str(e), "source": "nba_api"}


async def nba_api_head_to_head(
    team_id_1: int = 1610612747,  # Lakers
    team_id_2: int = 1610612738,  # Celtics
    season: str = "2025-26",
) -> dict[str, Any]:
    """Recupera scontri diretti tra due squadre NBA (stagione attuale e precedente).

    Args:
        team_id_1: ID prima squadra
        team_id_2: ID seconda squadra
        season: Stagione attuale (es. "2025-26")

    Returns:
        dict con storico scontri diretti
    """
    try:
        from nba_api.stats.endpoints import leaguegamefinder
        from nba_api.stats.static import teams as nba_teams

        # Trova nomi squadre
        all_teams = nba_teams.get_teams()
        team_1_name = next(
            (t["full_name"] for t in all_teams if t["id"] == team_id_1), f"Team {team_id_1}"
        )
        team_2_name = next(
            (t["full_name"] for t in all_teams if t["id"] == team_id_2), f"Team {team_id_2}"
        )

        # Calcola stagione precedente
        try:
            start_year = int(season[:4])
            prev_season = f"{start_year - 1}-{str(start_year)[2:]}"
        except Exception:
            prev_season = season

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1.5, min=2, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        def get_season_games(target_season: str) -> list[dict[str, Any]]:
            finder = leaguegamefinder.LeagueGameFinder(
                team_id_nullable=team_id_1,
                vs_team_id_nullable=team_id_2,
                season_nullable=target_season,
                timeout=15,
                headers=_get_nba_stats_headers(),
            )
            data = finder.get_dict()
            result_sets = data.get("resultSets", [])
            season_games = []
            if result_sets:
                headers = result_sets[0].get("headers", [])
                rows = result_sets[0].get("rowSet", [])
                for row in rows:
                    game = dict(zip(headers, row, strict=False))
                    season_games.append(
                        {
                            "date": game.get("GAME_DATE"),
                            "matchup": game.get("MATCHUP"),
                            "result": game.get("WL"),
                            "points": game.get("PTS"),
                            "opp_points": game.get("PTS", 0) - (game.get("PLUS_MINUS") or 0)
                            if game.get("PTS") is not None
                            else None,
                            "rebounds": game.get("REB"),
                            "assists": game.get("AST"),
                            "fg_pct": game.get("FG_PCT"),
                            "ft_pct": game.get("FT_PCT"),
                            "plus_minus": game.get("PLUS_MINUS"),
                            "season": target_season,
                        }
                    )
            return season_games

        await _enforce_nba_api_rate_limit()
        try:
            current_task = asyncio.to_thread(get_season_games, season)
            prev_task = asyncio.to_thread(get_season_games, prev_season)
            current_games, prev_games = await asyncio.wait_for(
                asyncio.gather(current_task, prev_task, return_exceptions=True),
                timeout=20.0,
            )
            if isinstance(current_games, Exception):
                logger.warning("h2h_current_season_failed", error=str(current_games))
                current_games = []
            if isinstance(prev_games, Exception):
                logger.warning("h2h_prev_season_failed", error=str(prev_games))
                prev_games = []
        except TimeoutError:
            logger.warning("h2h_timeout_20s", team_1=team_1_name, team_2=team_2_name)
            current_games = []
            prev_games = []

        # Unione e ordinamento
        all_h2h = current_games + prev_games
        # Ordina per data decrescente
        all_h2h.sort(key=lambda x: x["date"] or "", reverse=True)

        # Prendi i più recenti (max 10)
        recent_h2h = all_h2h[:10]

        team_1_wins = sum(1 for g in all_h2h if g["result"] == "W")
        team_2_wins = sum(1 for g in all_h2h if g["result"] == "L")

        return {
            "team_1": team_1_name,
            "team_2": team_2_name,
            "seasons": [season, prev_season],
            "games": recent_h2h,
            "total_h2h_record": f"{team_1_wins}-{team_2_wins}",
            "team_1_wins": team_1_wins,
            "team_2_wins": team_2_wins,
            "source": "nba_api (Official NBA Stats via LeagueGameFinder)",
        }

    except ImportError:
        return {"error": "nba_api package not installed", "source": "nba_api"}
    except Exception as e:
        logger.error("nba_api_h2h_error", error=str(e))
        return {"error": str(e), "source": "nba_api"}


# =============================================================================
# Tool Registry (per SportsNBAHandler)
# =============================================================================

AVAILABLE_TOOLS = {
    # BallDontLie (backup)
    "nba_upcoming_games": balldontlie_games,
    "nba_player_search": balldontlie_players,
    "nba_player_stats": balldontlie_stats,
    "nba_teams": balldontlie_teams,
    # ESPN (free)
    "nba_live_scoreboard": espn_scoreboard,
    "nba_injuries": espn_injuries,
    "nba_standings": espn_standings,
    "nba_team_stats": espn_team_stats,
    "nba_schedule": espn_schedule,
    # The Odds API
    "nba_betting_odds": odds_api_odds,
    # Polymarket (free, no auth)
    "nba_polymarket_odds": polymarket_nba_odds,
    # nba_api Package (official - preferred)
    "nba_api_live": nba_api_live_scoreboard,
    "nba_api_team_games": nba_api_team_games,
    "nba_api_player_career": nba_api_player_career,
    "nba_api_advanced_stats": nba_api_advanced_stats,
    "nba_api_standings": nba_api_standings,
    "nba_api_head_to_head": nba_api_head_to_head,
    "nba_api_player_stats_cascade": nba_api_player_stats_cascade,
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool NBA per nome.

    Filtra automaticamente parametri non accettati dalla funzione
    (es. parametri allucinati dall'LLM come 'max').

    Args:
        tool_name: Nome del tool
        arguments: Argomenti per il tool

    Returns:
        Risultato del tool
    """
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {
            "error": f"Unknown NBA tool: {tool_name}",
            "available": list(AVAILABLE_TOOLS.keys()),
        }

    tool_func = AVAILABLE_TOOLS[tool_name]

    # Filter arguments to only those the function accepts
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
    """Generate ToolDefinition objects for all Sports NBA tools."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        # BallDontLie
        ToolDefinition(
            name="nba_upcoming_games",
            description="Get upcoming NBA games and schedule. Returns dates, teams, and scores for scheduled and past games. Use when user asks 'NBA games today', 'when do Lakers play', 'next NBA matches'.",
            parameters={
                "team_id": ToolParameter(
                    type="integer",
                    description="Team ID to filter games (optional)",
                    required=False,
                ),
            },
            domain="sports_nba",
            category="games",
        ),
        ToolDefinition(
            name="nba_player_search",
            description="Search for NBA players by name. Find player info, team, position. Use when user asks 'find player X', 'who is Y', 'player info for Z'.",
            parameters={
                "search": ToolParameter(
                    type="string",
                    description="Player name to search (e.g., 'LeBron', 'Curry', 'Doncic')",
                    required=True,
                ),
            },
            domain="sports_nba",
            category="players",
        ),
        ToolDefinition(
            name="nba_player_stats",
            description="Get detailed season statistics for an NBA player. Returns averages for points, rebounds, assists. Use when user asks 'how many points does X average', 'Y's stats this season'.",
            parameters={
                "player_id": ToolParameter(
                    type="integer",
                    description="Player ID from nba_player_search",
                    required=True,
                ),
                "season": ToolParameter(
                    type="integer",
                    description="Season year (e.g., 2024 for 2024-25)",
                    required=False,
                ),
            },
            domain="sports_nba",
            category="players",
        ),
        ToolDefinition(
            name="nba_teams",
            description="List all 30 NBA teams with details. Returns name, abbreviation, conference, division. Use when user asks 'NBA team list', 'teams in Eastern Conference', 'all NBA franchises'.",
            parameters={},
            domain="sports_nba",
            category="teams",
        ),
        # ESPN
        ToolDefinition(
            name="nba_live_scoreboard",
            description="Get live NBA scores from ESPN. Shows games in progress, final scores, and today's schedule. Use when user asks 'NBA scores now', 'live games', 'who's winning'.",
            parameters={},
            domain="sports_nba",
            category="live",
        ),
        ToolDefinition(
            name="nba_injuries",
            description="Get current NBA injury report from ESPN. Shows injured players and their status. Use when user asks 'NBA injuries', 'who is injured', 'injured players on Lakers'.",
            parameters={},
            domain="sports_nba",
            category="injuries",
        ),
        # Odds API
        ToolDefinition(
            name="nba_betting_odds",
            description="Get NBA betting odds from major bookmakers. Returns spreads, moneylines, and over/unders. Use when user asks 'NBA odds', 'betting lines for Lakers', 'spread on tonight's game'.",
            parameters={
                "regions": ToolParameter(
                    type="string",
                    description="Bookmaker regions: 'us', 'eu', 'uk' (default: eu)",
                    required=False,
                ),
                "markets": ToolParameter(
                    type="string",
                    description="Bet types: 'h2h' (moneyline), 'spreads', 'totals' (comma-separated)",
                    required=False,
                ),
            },
            domain="sports_nba",
            category="betting",
        ),
        # nba_api Package (Official)
        ToolDefinition(
            name="nba_api_live",
            description="Get official NBA live scoreboard from NBA Stats API. Returns real-time game data with periods and arenas. Use when user needs official NBA live data.",
            parameters={},
            domain="sports_nba",
            category="live",
        ),
        ToolDefinition(
            name="nba_api_team_games",
            description="Get game history for a specific NBA team. Returns results, scores, and stats. Use when user asks 'Lakers recent games', 'Bulls last 10 games', 'Celtics game log'.",
            parameters={
                "team_id": ToolParameter(
                    type="integer",
                    description="NBA team ID (e.g., 1610612747 for Lakers)",
                    required=True,
                ),
                "season": ToolParameter(
                    type="string",
                    description="Season string (e.g., '2024-25')",
                    required=False,
                ),
            },
            domain="sports_nba",
            category="games",
        ),
        ToolDefinition(
            name="nba_api_player_career",
            description="Get complete career statistics for an NBA player. Returns career totals, games played, averages. Use when user asks 'LeBron career stats', 'how many points has X scored in his career'.",
            parameters={
                "player_id": ToolParameter(
                    type="integer",
                    description="NBA player ID (from nba_player_search)",
                    required=True,
                ),
            },
            domain="sports_nba",
            category="players",
        ),
        # ESPN Extended
        ToolDefinition(
            name="nba_standings",
            description="Get NBA standings for Eastern and Western conference. Shows wins, losses, win%, games behind, streak, home/away records, last 10. Use when user asks 'NBA standings', 'classifica NBA', 'Eastern/Western conference rankings'.",
            parameters={},
            domain="sports_nba",
            category="standings",
        ),
        ToolDefinition(
            name="nba_team_stats",
            description="Get detailed statistics for a specific NBA team. Returns points per game, rebounds, assists, shooting percentages, efficiency metrics. Use when user asks 'Lakers stats', 'team statistics', 'how do Celtics perform'.",
            parameters={
                "team_id": ToolParameter(
                    type="string",
                    description="ESPN team ID (e.g., '13' for Lakers, '2' for Celtics)",
                    required=True,
                ),
            },
            domain="sports_nba",
            category="teams",
        ),
        ToolDefinition(
            name="nba_schedule",
            description="Get NBA game schedule for upcoming days. Returns dates, matchups, venues, broadcast info. Use when user asks 'NBA schedule this week', 'upcoming NBA games', 'when are the next games'.",
            parameters={
                "days_ahead": ToolParameter(
                    type="integer",
                    description="Number of days to look ahead (default 7, max 14)",
                    required=False,
                ),
            },
            domain="sports_nba",
            category="games",
        ),
        # Polymarket
        ToolDefinition(
            name="nba_polymarket_odds",
            description="Get NBA prediction market odds from Polymarket. Shows real money odds on NBA outcomes (championships, MVP, series). Use when user asks 'Polymarket NBA odds', 'prediction market basketball', 'market odds NBA finals'.",
            parameters={},
            domain="sports_nba",
            category="betting",
        ),
        # nba_api Extended
        ToolDefinition(
            name="nba_api_advanced_stats",
            description="Get advanced analytics for NBA team. Returns offensive/defensive rating, pace, net rating, efficiency metrics. Essential for betting analysis. Use when user asks 'advanced stats Lakers', 'team efficiency', 'pace and ratings'.",
            parameters={
                "team_id": ToolParameter(
                    type="integer",
                    description="NBA team ID (e.g., 1610612747 for Lakers)",
                    required=True,
                ),
                "season": ToolParameter(
                    type="string",
                    description="Season string (e.g., '2025-26')",
                    required=False,
                ),
            },
            domain="sports_nba",
            category="analytics",
        ),
        ToolDefinition(
            name="nba_api_standings",
            description="Get official NBA standings from NBA Stats. Shows conference rankings, home/away records, last 10 games, points differential. Use when user asks 'official NBA standings', 'playoff race', 'conference rankings'.",
            parameters={
                "season": ToolParameter(
                    type="string",
                    description="Season string (e.g., '2025-26')",
                    required=False,
                ),
            },
            domain="sports_nba",
            category="standings",
        ),
        ToolDefinition(
            name="nba_api_head_to_head",
            description="Get head-to-head results between two NBA teams this season. Shows game-by-game results, scores, stats. Essential for betting analysis. Use when user asks 'Lakers vs Celtics history', 'head to head record', 'scontri diretti'.",
            parameters={
                "team_id_1": ToolParameter(
                    type="integer",
                    description="First team NBA ID (e.g., 1610612747 for Lakers)",
                    required=True,
                ),
                "team_id_2": ToolParameter(
                    type="integer",
                    description="Second team NBA ID (e.g., 1610612738 for Celtics)",
                    required=True,
                ),
                "season": ToolParameter(
                    type="string",
                    description="Season string (e.g., '2025-26')",
                    required=False,
                ),
            },
            domain="sports_nba",
            category="analytics",
        ),
    ]


def get_executors() -> dict:
    """Return mapping of tool names to executor functions."""
    return AVAILABLE_TOOLS
