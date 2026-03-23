"""NBA Betting Analysis Engine.

Motore professionale per analisi pronostici NBA.
Raccoglie dati in parallelo da multiple fonti API gratuite,
calcola probabilità, detecta value bet, e produce output strutturato.

Ispirato da:
- OpenClaw sportsbet-advisor (confidence scoring ≤95%)
- OpenClaw better-polymarket (prediction market odds)

Fonti dati (tutte free):
- ESPN API: scoreboard, standings, injuries, schedule, team stats
- nba_api: advanced stats (pace, ORtg, DRtg), standings, H2H
- The Odds API: quote bookmaker (H2H, spreads, totals)
- Polymarket: prediction market odds
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Home court advantage (in punti, media NBA storica)
HOME_COURT_ADVANTAGE = 3.0

# Soglia per value bet (differenza tra prob modello e prob implicita)
VALUE_BET_THRESHOLD = 0.05  # 5%

# Confidence massima (come sportsbet-advisor)
MAX_CONFIDENCE = 0.95

DISCLAIMER = (
    "⚠️ DISCLAIMER: Questa analisi è basata su dati statistici e modelli probabilistici. "
    "I pronostici sportivi sono per natura incerti e i risultati possono differire. "
    "Scommetti responsabilmente e solo con denaro che puoi permetterti di perdere."
)


@dataclass
class TeamForm:
    """Form recente di una squadra."""

    team_name: str = ""
    last_10_record: str = ""
    streak: str = ""
    home_record: str = ""
    away_record: str = ""
    points_pg: float = 0.0
    opp_points_pg: float = 0.0
    diff_pg: float = 0.0


@dataclass
class AdvancedMetrics:
    """Metriche avanzate squadra."""

    offensive_rating: float = 0.0
    defensive_rating: float = 0.0
    net_rating: float = 0.0
    pace: float = 0.0
    wins: int = 0
    losses: int = 0


@dataclass
class Prediction:
    """Predizione per un singolo mercato."""

    market: str = ""  # "h2h", "spread", "totals"
    pick: str = ""
    model_probability: float = 0.0
    odds_implied_probability: float = 0.0
    is_value_bet: bool = False
    edge: float = 0.0  # Differenza tra prob modello e prob implicita
    reasoning: str = ""


@dataclass
class BettingAnalysis:
    """Analisi completa per una singola partita NBA."""

    home_team: str = ""
    away_team: str = ""
    game_date: str = ""
    venue: str = ""
    home_form: TeamForm = field(default_factory=TeamForm)
    away_form: TeamForm = field(default_factory=TeamForm)
    home_advanced: AdvancedMetrics = field(default_factory=AdvancedMetrics)
    away_advanced: AdvancedMetrics = field(default_factory=AdvancedMetrics)
    h2h_record: str = ""
    h2h_games: list[dict[str, Any]] = field(default_factory=list)
    key_injuries: list[dict[str, Any]] = field(default_factory=list)
    bookmaker_odds: list[dict[str, Any]] = field(default_factory=list)
    polymarket_odds: list[dict[str, Any]] = field(default_factory=list)
    predictions: list[Prediction] = field(default_factory=list)
    confidence: float = 0.0
    data_completeness: dict[str, bool] = field(default_factory=dict)
    disclaimer: str = DISCLAIMER


class NBABettingAnalyzer:
    """Motore analisi pronostici NBA professionale.

    Workflow:
    1. Raccolta dati parallela (standings, form, H2H, injuries, odds, advanced stats)
    2. Calcolo probabilità win basato su net rating + home court + form
    3. Detection value bet (confronto modello vs odds implicite)
    4. Output strutturato con confidence scoring
    """

    async def analyze_game(
        self,
        home_team: str,
        away_team: str,
        game_date: str = "",
    ) -> BettingAnalysis:
        """Analisi completa singola partita NBA.

        Args:
            home_team: Nome squadra home (es. "Lakers", "Los Angeles Lakers")
            away_team: Nome squadra away
            game_date: Data partita (YYYY-MM-DD)

        Returns:
            BettingAnalysis con tutti i dati e predizioni
        """
        from me4brain.domains.sports_nba.tools import nba_api

        logger.info(
            "betting_analysis_started",
            home=home_team,
            away=away_team,
        )

        analysis = BettingAnalysis(
            home_team=home_team,
            away_team=away_team,
            game_date=game_date,
        )

        # ==== RACCOLTA DATI PARALLELA ====
        standings_task = nba_api.espn_standings()
        injuries_task = nba_api.espn_injuries()
        odds_task = nba_api.odds_api_odds()
        polymarket_task = nba_api.polymarket_nba_odds()

        results = await asyncio.gather(
            standings_task,
            injuries_task,
            odds_task,
            polymarket_task,
            return_exceptions=True,
        )

        standings_data, injuries_data, odds_data, polymarket_data = results

        # ==== PROCESS STANDINGS (form) ====
        if isinstance(standings_data, dict) and not standings_data.get("error"):
            analysis.data_completeness["standings"] = True
            self._extract_team_form(analysis, standings_data)
        else:
            analysis.data_completeness["standings"] = False

        # ==== PROCESS INJURIES ====
        if isinstance(injuries_data, dict) and not injuries_data.get("error"):
            analysis.data_completeness["injuries"] = True
            self._extract_key_injuries(analysis, injuries_data)
        else:
            analysis.data_completeness["injuries"] = False

        # ==== PROCESS ODDS ====
        if isinstance(odds_data, dict) and not odds_data.get("error"):
            analysis.data_completeness["odds"] = True
            self._extract_odds(analysis, odds_data)
        else:
            analysis.data_completeness["odds"] = False

        # ==== PROCESS POLYMARKET ====
        if isinstance(polymarket_data, dict) and not polymarket_data.get("error"):
            analysis.data_completeness["polymarket"] = True
            analysis.polymarket_odds = polymarket_data.get("events", [])
        else:
            analysis.data_completeness["polymarket"] = False

        # ==== ADVANCED STATS (nba_api) — secondo round ====
        try:
            adv_results = await asyncio.gather(
                self._try_get_advanced_stats(home_team),
                self._try_get_advanced_stats(away_team),
                return_exceptions=True,
            )

            if isinstance(adv_results[0], AdvancedMetrics):
                analysis.home_advanced = adv_results[0]
                analysis.data_completeness["home_advanced"] = True
            else:
                analysis.data_completeness["home_advanced"] = False

            if isinstance(adv_results[1], AdvancedMetrics):
                analysis.away_advanced = adv_results[1]
                analysis.data_completeness["away_advanced"] = True
            else:
                analysis.data_completeness["away_advanced"] = False
        except Exception:
            analysis.data_completeness["home_advanced"] = False
            analysis.data_completeness["away_advanced"] = False

        # ==== CALCOLO PREDIZIONI ====
        analysis.predictions = self._calculate_predictions(analysis)

        # ==== CONFIDENCE SCORING ====
        analysis.confidence = self._calculate_confidence(analysis)

        logger.info(
            "betting_analysis_complete",
            home=home_team,
            away=away_team,
            confidence=analysis.confidence,
            predictions_count=len(analysis.predictions),
            data_completeness=analysis.data_completeness,
        )

        return analysis

    async def analyze_daily_slate(self) -> list[BettingAnalysis]:
        """Pronostici per tutte le partite del giorno.

        Returns:
            Lista di BettingAnalysis per ogni partita
        """
        from me4brain.domains.sports_nba.tools import nba_api

        logger.info("daily_slate_analysis_started")

        # Recupera partite di oggi
        schedule_data = await nba_api.espn_schedule(days_ahead=1)
        if schedule_data.get("error") or not schedule_data.get("games"):
            # Fallback: prova live scoreboard
            scoreboard = await nba_api.nba_api_live_scoreboard()
            if scoreboard.get("error") or not scoreboard.get("games"):
                return []
            games = scoreboard.get("games", [])
        else:
            games = schedule_data.get("games", [])

        analyses: list[BettingAnalysis] = []
        for game in games:
            home = game.get("home_team", "")
            away = game.get("away_team", "")
            date = game.get("date", game.get("start_time", ""))

            if home and away:
                try:
                    analysis = await self.analyze_game(home, away, date)
                    analyses.append(analysis)
                except Exception as e:
                    logger.error(
                        "game_analysis_failed",
                        home=home,
                        away=away,
                        error=str(e),
                    )

        logger.info(
            "daily_slate_analysis_complete",
            total_games=len(games),
            analyzed=len(analyses),
        )

        return analyses

    async def _try_get_advanced_stats(self, team_name: str) -> AdvancedMetrics:
        """Tenta di recuperare stats avanzate per una squadra.

        Args:
            team_name: Nome squadra (anche parziale)

        Returns:
            AdvancedMetrics o eccezione
        """
        from me4brain.domains.sports_nba.tools import nba_api

        # Mappa nomi comuni a team_id NBA
        team_id = self._resolve_team_id(team_name)
        if not team_id:
            msg = f"Team ID not found for: {team_name}"
            raise ValueError(msg)

        data = await nba_api.nba_api_advanced_stats(team_id=team_id)
        if data.get("error"):
            raise ValueError(data["error"])

        stats = data.get("advanced_stats", {})
        return AdvancedMetrics(
            offensive_rating=float(stats.get("offensive_rating") or 0),
            defensive_rating=float(stats.get("defensive_rating") or 0),
            net_rating=float(stats.get("net_rating") or 0),
            pace=float(stats.get("pace") or 0),
            wins=int(stats.get("wins") or 0),
            losses=int(stats.get("losses") or 0),
        )

    def _extract_team_form(
        self,
        analysis: BettingAnalysis,
        standings_data: dict[str, Any],
    ) -> None:
        """Estrae form delle squadre dagli standings."""
        standings = standings_data.get("standings", {})
        all_teams = standings.get("eastern", []) + standings.get("western", [])

        for team in all_teams:
            team_name = (team.get("team") or "").lower()
            home_lower = analysis.home_team.lower()
            away_lower = analysis.away_team.lower()

            # Match fuzzy: nome completo o abbreviazione
            if any(part in team_name for part in home_lower.split()):
                analysis.home_form = TeamForm(
                    team_name=team.get("team", ""),
                    last_10_record=str(team.get("last_10", "")),
                    streak=str(team.get("streak", "")),
                    home_record=str(team.get("home_record", "")),
                    away_record=str(team.get("away_record", "")),
                    points_pg=float(team.get("points_for", 0) or 0),
                    opp_points_pg=float(team.get("points_against", 0) or 0),
                )
            elif any(part in team_name for part in away_lower.split()):
                analysis.away_form = TeamForm(
                    team_name=team.get("team", ""),
                    last_10_record=str(team.get("last_10", "")),
                    streak=str(team.get("streak", "")),
                    home_record=str(team.get("home_record", "")),
                    away_record=str(team.get("away_record", "")),
                    points_pg=float(team.get("points_for", 0) or 0),
                    opp_points_pg=float(team.get("points_against", 0) or 0),
                )

    def _extract_key_injuries(
        self,
        analysis: BettingAnalysis,
        injuries_data: dict[str, Any],
    ) -> None:
        """Filtra infortuni rilevanti per le squadre in analisi."""
        injuries = injuries_data.get("injuries", [])
        home_lower = analysis.home_team.lower()
        away_lower = analysis.away_team.lower()

        for injury in injuries:
            player = injury.get("player", "")
            status = injury.get("status", "").lower()
            # Includi solo Out e Doubtful (impatto significativo)
            if status in ("out", "doubtful", "o", "d"):
                analysis.key_injuries.append(injury)

    def _extract_odds(
        self,
        analysis: BettingAnalysis,
        odds_data: dict[str, Any],
    ) -> None:
        """Estrae quote bookmaker per la partita specifica."""
        events = odds_data.get("events", [])
        home_lower = analysis.home_team.lower()
        away_lower = analysis.away_team.lower()

        for event in events:
            event_home = (event.get("home_team") or "").lower()
            event_away = (event.get("away_team") or "").lower()

            # Match partita
            home_match = any(p in event_home for p in home_lower.split())
            away_match = any(p in event_away for p in away_lower.split())

            if home_match or away_match:
                analysis.bookmaker_odds = event.get("bookmakers", [])
                break

    def _calculate_predictions(self, analysis: BettingAnalysis) -> list[Prediction]:
        """Calcola predizioni per tutti i mercati.

        Modello probabilistico basato su:
        1. Net Rating differenziale
        2. Home court advantage
        3. Form recente (streak)
        """
        predictions: list[Prediction] = []

        # ==== H2H (Moneyline) ====
        home_prob = self._win_probability(analysis)
        away_prob = 1.0 - home_prob

        # Recupera odds implicite da bookmaker
        home_implied = 0.0
        away_implied = 0.0
        spread_line = 0.0
        total_line = 0.0

        for bookie in analysis.bookmaker_odds:
            markets = bookie.get("markets", {})

            # H2H odds
            h2h = markets.get("h2h", {})
            if h2h:
                for name, price in h2h.items():
                    try:
                        implied = 1.0 / float(price) if float(price) > 0 else 0
                    except (ValueError, ZeroDivisionError):
                        implied = 0
                    name_lower = name.lower()
                    if any(p in name_lower for p in analysis.home_team.lower().split()):
                        home_implied = implied
                    elif any(p in name_lower for p in analysis.away_team.lower().split()):
                        away_implied = implied

            # Spread
            spreads = markets.get("spreads", {})
            if spreads:
                for name, price in spreads.items():
                    if isinstance(price, dict):
                        spread_line = float(price.get("point", 0))
                    elif isinstance(price, (int, float)):
                        spread_line = float(price)

            # Totals
            totals = markets.get("totals", {})
            if totals:
                for name, price in totals.items():
                    if isinstance(price, dict):
                        total_line = float(price.get("point", 0))
                    elif isinstance(price, (int, float)):
                        total_line = float(price)

            break  # Usa primo bookmaker

        # H2H Prediction
        h2h_pick = analysis.home_team if home_prob > 0.5 else analysis.away_team
        h2h_edge = abs(home_prob - home_implied) if home_implied > 0 else 0.0

        predictions.append(
            Prediction(
                market="h2h",
                pick=h2h_pick,
                model_probability=max(home_prob, away_prob),
                odds_implied_probability=home_implied if home_prob > 0.5 else away_implied,
                is_value_bet=h2h_edge > VALUE_BET_THRESHOLD,
                edge=round(h2h_edge, 4),
                reasoning=self._generate_h2h_reasoning(analysis, home_prob),
            )
        )

        # ==== SPREAD ====
        expected_margin = self._expected_margin(analysis)
        spread_pick = analysis.home_team if expected_margin > 0 else analysis.away_team

        predictions.append(
            Prediction(
                market="spread",
                pick=f"{spread_pick} (model: {expected_margin:+.1f}pts, line: {spread_line:+.1f})",
                model_probability=home_prob,
                reasoning=f"Margine atteso modello: {expected_margin:+.1f} punti. "
                f"Home court: +{HOME_COURT_ADVANTAGE} pts. "
                f"Net rating diff: {self._net_rating_diff(analysis):.1f}.",
            )
        )

        # ==== TOTALS ====
        expected_total = self._expected_total(analysis)
        if total_line > 0:
            totals_pick = "Over" if expected_total > total_line else "Under"
            predictions.append(
                Prediction(
                    market="totals",
                    pick=f"{totals_pick} {total_line} (model: {expected_total:.1f})",
                    model_probability=0.55 if abs(expected_total - total_line) > 3 else 0.52,
                    reasoning=f"Totale atteso modello: {expected_total:.1f} punti. "
                    f"Line bookmaker: {total_line}. "
                    f"Pace combinato: ~{self._combined_pace(analysis):.1f}.",
                )
            )

        return predictions

    def _win_probability(self, analysis: BettingAnalysis) -> float:
        """Calcola probabilità vittoria home team.

        Formula: logistic(net_rating_diff + home_court + form_adj)
        """
        import math

        net_diff = self._net_rating_diff(analysis)
        home_adj = HOME_COURT_ADVANTAGE / 10  # Normalizzato

        # Form adjustment basato su streak
        form_adj = 0.0
        home_streak = analysis.home_form.streak.lower() if analysis.home_form.streak else ""
        away_streak = analysis.away_form.streak.lower() if analysis.away_form.streak else ""

        if "w" in home_streak:
            try:
                wins = int("".join(c for c in home_streak if c.isdigit()) or "0")
                form_adj += min(wins * 0.02, 0.1)
            except ValueError:
                pass
        if "w" in away_streak:
            try:
                wins = int("".join(c for c in away_streak if c.isdigit()) or "0")
                form_adj -= min(wins * 0.02, 0.1)
            except ValueError:
                pass

        # Logistic function
        z = (net_diff / 10) + home_adj + form_adj
        prob = 1.0 / (1.0 + math.exp(-z * 2.5))

        # Clamp tra 0.15 e 0.85 (nessuna certezza assoluta)
        return max(0.15, min(0.85, prob))

    def _net_rating_diff(self, analysis: BettingAnalysis) -> float:
        """Differenza net rating tra home e away."""
        return analysis.home_advanced.net_rating - analysis.away_advanced.net_rating

    def _expected_margin(self, analysis: BettingAnalysis) -> float:
        """Margine atteso in punti (positivo = home wins)."""
        net_diff = self._net_rating_diff(analysis)
        return net_diff + HOME_COURT_ADVANTAGE

    def _expected_total(self, analysis: BettingAnalysis) -> float:
        """Totale punti atteso per la partita."""
        pace = self._combined_pace(analysis)
        if pace > 0:
            # Total ≈ pace * (ORtg_h + ORtg_a) / 200
            ortg_sum = (
                analysis.home_advanced.offensive_rating + analysis.away_advanced.offensive_rating
            )
            if ortg_sum > 0:
                return pace * ortg_sum / 200
        # Fallback: media punti dalle form
        home_pts = (
            analysis.home_form.points_pg
            if isinstance(analysis.home_form.points_pg, (int, float))
            else 0
        )
        away_pts = (
            analysis.away_form.points_pg
            if isinstance(analysis.away_form.points_pg, (int, float))
            else 0
        )
        if home_pts > 0 and away_pts > 0:
            return home_pts + away_pts
        return 220.0  # Default NBA average

    def _combined_pace(self, analysis: BettingAnalysis) -> float:
        """Pace medio combinato delle due squadre."""
        h_pace = analysis.home_advanced.pace
        a_pace = analysis.away_advanced.pace
        if h_pace > 0 and a_pace > 0:
            return (h_pace + a_pace) / 2
        return 100.0  # Default NBA pace

    def _generate_h2h_reasoning(
        self,
        analysis: BettingAnalysis,
        home_prob: float,
    ) -> str:
        """Genera reasoning testuale per la predizione H2H."""
        parts: list[str] = []

        # Net rating
        net_diff = self._net_rating_diff(analysis)
        if abs(net_diff) > 0:
            better = analysis.home_team if net_diff > 0 else analysis.away_team
            parts.append(f"Net Rating: {better} avvantaggiato ({net_diff:+.1f})")

        # Home court
        parts.append(f"Home court advantage: +{HOME_COURT_ADVANTAGE} pts per {analysis.home_team}")

        # Form
        if analysis.home_form.streak:
            parts.append(f"Form {analysis.home_team}: streak {analysis.home_form.streak}")
        if analysis.away_form.streak:
            parts.append(f"Form {analysis.away_team}: streak {analysis.away_form.streak}")

        # Injuries
        if analysis.key_injuries:
            out_count = len(
                [i for i in analysis.key_injuries if i.get("status", "").lower() in ("out", "o")]
            )
            parts.append(f"Infortuni: {out_count} giocatori Out")

        parts.append(
            f"Probabilità modello: {analysis.home_team} {home_prob:.0%} - {analysis.away_team} {1 - home_prob:.0%}"
        )

        return ". ".join(parts) + "."

    def _calculate_confidence(self, analysis: BettingAnalysis) -> float:
        """Calcola confidence score basato su completezza dati.

        Score = base_confidence * data_weight
        Range: 0.30 - 0.95 (mai 100%)
        """
        # Pesi per fonte dati
        data_weights = {
            "standings": 0.15,
            "injuries": 0.10,
            "odds": 0.20,
            "home_advanced": 0.20,
            "away_advanced": 0.20,
            "polymarket": 0.05,
        }

        # Base confidence
        available_weight = sum(
            w for key, w in data_weights.items() if analysis.data_completeness.get(key, False)
        )

        base_confidence = 0.30 + (available_weight * 0.65)

        # Bonus per more data sources
        sources_count = sum(1 for v in analysis.data_completeness.values() if v)
        if sources_count >= 5:
            base_confidence += 0.05

        return min(round(base_confidence, 2), MAX_CONFIDENCE)

    @staticmethod
    def _resolve_team_id(team_name: str) -> int | None:
        """Risolvi nome squadra a NBA team ID.

        Args:
            team_name: Nome o parte del nome (es. "Lakers", "Los Angeles Lakers")

        Returns:
            NBA team ID o None
        """
        # Mappa nomi comuni -> team_id NBA
        team_map: dict[str, int] = {
            "hawks": 1610612737,
            "atlanta": 1610612737,
            "celtics": 1610612738,
            "boston": 1610612738,
            "nets": 1610612751,
            "brooklyn": 1610612751,
            "hornets": 1610612766,
            "charlotte": 1610612766,
            "bulls": 1610612741,
            "chicago": 1610612741,
            "cavaliers": 1610612739,
            "cavs": 1610612739,
            "cleveland": 1610612739,
            "mavericks": 1610612742,
            "mavs": 1610612742,
            "dallas": 1610612742,
            "nuggets": 1610612743,
            "denver": 1610612743,
            "pistons": 1610612765,
            "detroit": 1610612765,
            "warriors": 1610612744,
            "golden state": 1610612744,
            "rockets": 1610612745,
            "houston": 1610612745,
            "pacers": 1610612754,
            "indiana": 1610612754,
            "clippers": 1610612746,
            "la clippers": 1610612746,
            "lakers": 1610612747,
            "los angeles lakers": 1610612747,
            "grizzlies": 1610612763,
            "memphis": 1610612763,
            "heat": 1610612748,
            "miami": 1610612748,
            "bucks": 1610612749,
            "milwaukee": 1610612749,
            "timberwolves": 1610612750,
            "wolves": 1610612750,
            "minnesota": 1610612750,
            "pelicans": 1610612740,
            "new orleans": 1610612740,
            "knicks": 1610612752,
            "new york": 1610612752,
            "thunder": 1610612760,
            "okc": 1610612760,
            "oklahoma": 1610612760,
            "magic": 1610612753,
            "orlando": 1610612753,
            "76ers": 1610612755,
            "sixers": 1610612755,
            "philadelphia": 1610612755,
            "suns": 1610612756,
            "phoenix": 1610612756,
            "blazers": 1610612757,
            "trail blazers": 1610612757,
            "portland": 1610612757,
            "kings": 1610612758,
            "sacramento": 1610612758,
            "spurs": 1610612759,
            "san antonio": 1610612759,
            "raptors": 1610612761,
            "toronto": 1610612761,
            "jazz": 1610612762,
            "utah": 1610612762,
            "wizards": 1610612764,
            "washington": 1610612764,
        }

        name_lower = team_name.lower().strip()

        # Exact match
        if name_lower in team_map:
            return team_map[name_lower]

        # Partial match
        for key, tid in team_map.items():
            if key in name_lower or name_lower in key:
                return tid

        return None

    def to_dict(self, analysis: BettingAnalysis) -> dict[str, Any]:
        """Converte BettingAnalysis in dict per output JSON."""
        return {
            "game": {
                "home_team": analysis.home_team,
                "away_team": analysis.away_team,
                "date": analysis.game_date,
                "venue": analysis.venue,
            },
            "form": {
                "home": {
                    "team": analysis.home_form.team_name,
                    "last_10": analysis.home_form.last_10_record,
                    "streak": analysis.home_form.streak,
                    "home_record": analysis.home_form.home_record,
                    "away_record": analysis.home_form.away_record,
                },
                "away": {
                    "team": analysis.away_form.team_name,
                    "last_10": analysis.away_form.last_10_record,
                    "streak": analysis.away_form.streak,
                    "home_record": analysis.away_form.home_record,
                    "away_record": analysis.away_form.away_record,
                },
            },
            "advanced_stats": {
                "home": {
                    "off_rating": analysis.home_advanced.offensive_rating,
                    "def_rating": analysis.home_advanced.defensive_rating,
                    "net_rating": analysis.home_advanced.net_rating,
                    "pace": analysis.home_advanced.pace,
                },
                "away": {
                    "off_rating": analysis.away_advanced.offensive_rating,
                    "def_rating": analysis.away_advanced.defensive_rating,
                    "net_rating": analysis.away_advanced.net_rating,
                    "pace": analysis.away_advanced.pace,
                },
            },
            "injuries": analysis.key_injuries[:10],
            "odds": {
                "bookmakers": analysis.bookmaker_odds,
                "polymarket": analysis.polymarket_odds[:3],
            },
            "predictions": [
                {
                    "market": p.market,
                    "pick": p.pick,
                    "model_probability": f"{p.model_probability:.0%}",
                    "is_value_bet": p.is_value_bet,
                    "edge": f"{p.edge:.1%}" if p.edge > 0 else "N/A",
                    "reasoning": p.reasoning,
                }
                for p in analysis.predictions
            ],
            "confidence": f"{analysis.confidence:.0%}",
            "data_sources_available": analysis.data_completeness,
            "disclaimer": analysis.disclaimer,
        }


# =============================================================================
# Tool Definitions & Executors
# =============================================================================

from me4brain.engine.types import ToolDefinition, ToolParameter


async def nba_betting_analyzer(
    home_team: str | None = None, away_team: str | None = None, analyze_all_today: bool = False
) -> dict[str, Any]:
    """Professional NBA betting analysis engine."""
    analyzer = NBABettingAnalyzer()

    if analyze_all_today:
        results = await analyzer.analyze_daily_slate()
        return {"total_games": len(results), "analyses": [analyzer.to_dict(a) for a in results]}

    if home_team and away_team:
        analysis = await analyzer.analyze_game(home_team, away_team)
        return analyzer.to_dict(analysis)

    return {
        "error": "Missing parameters. Provide home_team/away_team or set analyze_all_today=True"
    }


def get_tool_definitions() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="nba_betting_analyzer",
            description="Professional NBA betting analysis. Analyzes team stats, form, injuries, and betting odds to detect value bets and probabilities. Essential for professional betting queries.",
            parameters={
                "home_team": ToolParameter(
                    type="string",
                    description="Home team name (e.g., 'Lakers')",
                    required=False,
                ),
                "away_team": ToolParameter(
                    type="string",
                    description="Away team name (e.g., 'Celtics')",
                    required=False,
                ),
                "analyze_all_today": ToolParameter(
                    type="boolean",
                    description="If True, analyzes all games scheduled for today",
                    required=False,
                ),
            },
            domain="sports_nba",
            category="betting",
        )
    ]


def get_executors() -> dict:
    return {"nba_betting_analyzer": nba_betting_analyzer}
