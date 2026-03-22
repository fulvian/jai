"""Sports NBA Domain Handler.

Implementazione DomainHandler per il dominio Sports/NBA.
Gestisce query su partite, giocatori, statistiche, quote scommesse,
pronostici e analisi betting professionale.

Volatilità: VOLATILE (24h TTL)
Tool-First: Sì (sempre chiama API per dati freschi)
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog

from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
)

logger = structlog.get_logger(__name__)


class SportsNBAHandler(DomainHandler):
    """Domain handler per NBA sports queries.

    Capabilities:
    - Partite programmate e live
    - Statistiche giocatori (career, season)
    - Classifiche e standings
    - Quote scommesse
    - Infortuni

    Example queries:
    - "Prossima partita Lakers"
    - "Statistiche Lebron James stagione corrente"
    - "Quote scommesse NBA stasera"
    - "Infortuni Lakers"
    """

    # Services gestiti da questo handler
    HANDLED_SERVICES = frozenset(
        {
            "balldontlie",
            "espn",
            "odds_api",
            "nba_stats",
            "polymarket",
            "betting_analyzer",
        }
    )

    # Keywords per routing rapido
    NBA_KEYWORDS = frozenset(
        {
            "nba",
            "basket",
            "basketball",
            "partita",
            "partite",
            "giocatore",
            "giocatori",
            "lakers",
            "celtics",
            "warriors",
            "bulls",
            "heat",
            "knicks",
            "nets",
            "suns",
            "bucks",
            "76ers",
            "mavs",
            "mavericks",
            "nuggets",
            "clippers",
            "quote",
            "scommesse",
            "betting",
            "odds",
            "infortuni",
            "injuries",
            "standings",
            "classifica",
            "roster",
            "stats",
            "statistiche",
            "lebron",
            "curry",
            "doncic",
            "giannis",
            "jokic",
            "durant",
            "tatum",
            "morant",
            # ADDED: Betting analysis keywords
            "pronostico",
            "pronostici",
            "prediction",
            "value",
            "analisi betting",
            "scommessa",
            "vincente",
            "winner",
            "pick",
            "parlay",
            "under",
            "over",
            "spread",
            "moneyline",
            "favorite",
            "underdog",
            "probabilità",
            "probability",
            "confidence",
            "affidabilità",
        }
    )

    # Query patterns per workflow routing
    GAME_PATTERNS = [
        "prossima partita",
        "prossimo match",
        "next game",
        "partite nba",
        "calendario nba",
        "schedule",
    ]

    STATS_PATTERNS = [
        "statistiche",
        "stats",
        "media punti",
        "punti",
        "rimbalzi",
        "assist",
        "career",
    ]

    INJURIES_PATTERNS = [
        "infortuni",
        "injuries",
        "infortunati",
        "indisponibili",
        "out",
        "questionable",
    ]

    ODDS_PATTERNS = [
        "quote",
        "scommesse",
        "odds",
        "betting",
    ]

    BETTING_ANALYSIS_PATTERNS = [
        "pronostico",
        "pronostici",
        "analisi completa",
        "analisi partita",
        "prediction",
        "value bet",
        "scommessa",
        "analisi betting",
        "preview",
        "pick",
    ]

    STANDINGS_PATTERNS = [
        "classifica",
        "standings",
        "conference",
        "playoff",
        "posizione",
        "ranking",
    ]

    @property
    def domain_name(self) -> str:
        """Nome univoco dominio."""
        return "sports_nba"

    @property
    def volatility(self) -> DomainVolatility:
        """Dati NBA sono volatili - cambiano ogni giorno."""
        return DomainVolatility.VOLATILE

    @property
    def default_ttl_hours(self) -> int:
        """TTL 24h per dati NBA."""
        return 24

    @property
    def capabilities(self) -> list[DomainCapability]:
        """Capabilities esposte dal dominio NBA."""
        return [
            DomainCapability(
                name="nba_game_analysis",
                description="Analisi partite NBA con statistiche, quote, infortuni",
                keywords=["nba", "partita", "basket", "quote", "infortuni", "pronostico"],
                example_queries=[
                    "Prossima partita Lakers",
                    "Pronostico Lakers vs Celtics",
                    "Quote scommesse NBA stasera",
                ],
            ),
            DomainCapability(
                name="nba_player_stats",
                description="Statistiche giocatori NBA (career, stagione corrente)",
                keywords=["giocatore", "stats", "statistiche", "punti", "assist", "rimbalzi"],
                example_queries=[
                    "Statistiche Lebron James",
                    "Media punti Stephen Curry stagione",
                    "Career stats Luka Doncic",
                ],
            ),
            DomainCapability(
                name="nba_standings",
                description="Classifiche NBA Eastern/Western conference",
                keywords=["classifica", "standings", "conference", "playoff"],
                example_queries=[
                    "Classifica NBA Western Conference",
                    "Posizione Lakers in classifica",
                ],
            ),
            DomainCapability(
                name="nba_injuries",
                description="Report infortuni squadre NBA",
                keywords=["infortuni", "injuries", "indisponibili", "out"],
                example_queries=[
                    "Infortuni Lakers",
                    "Giocatori indisponibili Celtics",
                ],
            ),
            DomainCapability(
                name="nba_betting_analysis",
                description="Analisi pronostici NBA professionale con value bet, confidence scoring, modello probabilistico",
                keywords=[
                    "pronostico",
                    "scommessa",
                    "value bet",
                    "prediction",
                    "betting",
                    "analisi",
                ],
                example_queries=[
                    "Pronostico Lakers vs Celtics",
                    "Value bet partite NBA stasera",
                    "Analisi betting completa",
                    "Pronostici NBA di oggi",
                ],
            ),
        ]

    async def initialize(self) -> None:
        """Setup handler NBA."""
        logger.info("sports_nba_handler_initialized")

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        """Determina se la query è NBA-related.

        Usa keyword matching veloce + pattern matching per scoring.
        Priorità alta per query di betting analysis.
        """
        query_lower = query.lower()

        # Check entities da analisi LLM
        entities = analysis.get("entities", [])
        nba_entities = sum(
            1 for e in entities if any(kw in str(e).lower() for kw in self.NBA_KEYWORDS)
        )

        # Check keywords diretti nella query
        keyword_matches = sum(1 for kw in self.NBA_KEYWORDS if kw in query_lower)

        # BONUS: Check per betting analysis patterns (alta priorità)
        betting_analysis_score = 0.0
        if any(pattern in query_lower for pattern in self.BETTING_ANALYSIS_PATTERNS):
            betting_analysis_score = 0.4  # Boost +0.4 per queries esplicite di betting

        # BONUS: Check per complete analysis patterns
        complete_analysis_score = 0.0
        if any(
            pattern in query_lower
            for pattern in ["analisi completa", "compendio", "panoramica completa", "preview"]
        ):
            complete_analysis_score = 0.2  # Boost +0.2 per complete analysis

        # Score: combinazione entities + keywords + bonuses
        total_matches = nba_entities + keyword_matches
        base_score = 0.0

        if total_matches == 0:
            base_score = 0.0
        elif total_matches == 1:
            base_score = 0.4
        elif total_matches == 2:
            base_score = 0.6
        elif total_matches <= 4:
            base_score = 0.8
        else:
            base_score = 1.0

        # Applica bonuses
        final_score = min(1.0, base_score + betting_analysis_score + complete_analysis_score)

        return final_score

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Esegue logica NBA con routing intelligente.

        Workflow:
        1. Detect tipo query (game, stats, injuries, odds)
        2. Per query complete (pronostico/analisi), esegue chained analysis
        3. Per query semplici, esegue tool singolo
        """
        query_lower = query.lower()
        start_time = datetime.now(UTC)
        results: list[DomainExecutionResult] = []

        logger.info(
            "sports_nba_execute",
            query_preview=query[:50],
            entities=analysis.get("entities", []),
        )

        # Detect se è query scommesse (BettingAnalyzer) o analisi completa (Chained)
        is_betting_analysis = any(
            pattern in query_lower for pattern in self.BETTING_ANALYSIS_PATTERNS
        )
        is_complete_analysis = any(
            pattern in query_lower
            for pattern in ["analisi completa", "compendio", "panoramica completa", "preview"]
        )

        if is_complete_analysis:
            # Chained Analysis: partite + infortuni + quote + standings
            # Priorità a analisi completa se esplicitamente richiesta
            results = await self._chained_nba_analysis(query, analysis)
        elif is_betting_analysis:
            # Pro Betting Analysis: usa NBABettingAnalyzer
            results = await self._execute_betting_analysis(query, analysis)
        else:
            # Single tool routing
            if self._detect_pattern(query_lower, self.STANDINGS_PATTERNS):
                results = [await self._execute_standings()]
            elif self._detect_pattern(query_lower, self.GAME_PATTERNS):
                results = [await self._execute_games()]
            elif self._detect_pattern(query_lower, self.STATS_PATTERNS):
                player_name = self._extract_player_name(query, analysis)
                results = [await self._execute_player_stats(player_name)]
            elif self._detect_pattern(query_lower, self.INJURIES_PATTERNS):
                results = [await self._execute_injuries()]
            elif self._detect_pattern(query_lower, self.ODDS_PATTERNS):
                results = [await self._execute_odds()]
            else:
                # Default: partite + scoreboard
                results = [await self._execute_games()]

        # Add timing to all results
        latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
        for r in results:
            r.latency_ms = latency_ms

        return results

    async def _chained_nba_analysis(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Esegue analisi NBA completa (multiple API in parallelo).

        Chiamata per query tipo "pronostico prossima partita Lakers".
        Usa nba_api (gratuito) come primario invece di BallDontLie.
        """
        from me4brain.domains.sports_nba.tools import nba_api

        logger.info("nba_chained_analysis_started")

        # Esegui in parallelo: nba_api live, ESPN, injuries, odds, standings
        games_task = nba_api.nba_api_live_scoreboard()  # PRIMARY: gratuito, ufficiale
        scoreboard_task = nba_api.espn_scoreboard()
        injuries_task = nba_api.espn_injuries()
        odds_task = nba_api.odds_api_odds()
        standings_task = nba_api.espn_standings()

        games, scoreboard, injuries, odds, standings = await asyncio.gather(
            games_task,
            scoreboard_task,
            injuries_task,
            odds_task,
            standings_task,
            return_exceptions=True,
        )

        results = []

        # Process games
        if isinstance(games, dict) and not games.get("error"):
            results.append(
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="nba_upcoming_games",
                    data=games,
                )
            )
        else:
            results.append(
                DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name="nba_upcoming_games",
                    error=str(games) if isinstance(games, Exception) else games.get("error"),
                )
            )

        # Process scoreboard
        if isinstance(scoreboard, dict) and not scoreboard.get("error"):
            results.append(
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="nba_live_scoreboard",
                    data=scoreboard,
                )
            )

        # Process injuries
        if isinstance(injuries, dict) and not injuries.get("error"):
            results.append(
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="nba_injuries",
                    data=injuries,
                )
            )

        # Process odds
        if isinstance(odds, dict) and not odds.get("error"):
            results.append(
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="nba_betting_odds",
                    data=odds,
                )
            )

        # Process standings
        if isinstance(standings, dict) and not standings.get("error"):
            results.append(
                DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="nba_standings",
                    data=standings,
                )
            )

        logger.info(
            "nba_chained_analysis_complete",
            total_results=len(results),
            successful=sum(1 for r in results if r.success),
        )

        return results

    async def _execute_games(self) -> DomainExecutionResult:
        """Esegue tool partite NBA con cascata gratuita-first.

        Ordine priorità:
        1. nba_api_live_scoreboard (ufficiale, gratuito, no auth)
        2. espn_scoreboard (fallback gratuito)
        3. balldontlie_games (solo se API key configurata)
        """
        from me4brain.domains.sports_nba.tools import nba_api

        # STEP 1: Try nba_api (official, free, no auth required)
        try:
            data = await nba_api.nba_api_live_scoreboard()
            if not data.get("error") and data.get("games"):
                logger.info(
                    "nba_games_success", source="nba_api", games_count=len(data.get("games", []))
                )
                return DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="nba_api_live_scoreboard",
                    data=data,
                )
        except Exception as e:
            logger.warning("nba_api_live_failed", error=str(e))

        # STEP 2: Try ESPN scoreboard (free, no auth)
        try:
            data = await nba_api.espn_scoreboard()
            if not data.get("error") and data.get("games"):
                logger.info(
                    "nba_games_success", source="espn", games_count=len(data.get("games", []))
                )
                return DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="espn_scoreboard",
                    data=data,
                )
        except Exception as e:
            logger.warning("espn_scoreboard_failed", error=str(e))

        # STEP 3: Try BallDontLie (requires API key)
        try:
            data = await nba_api.balldontlie_games()
            if not data.get("error"):
                logger.info(
                    "nba_games_success",
                    source="balldontlie",
                    games_count=len(data.get("games", [])),
                )
                return DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="balldontlie_games",
                    data=data,
                )
            else:
                logger.warning("balldontlie_error", error=data.get("error"))
        except Exception as e:
            logger.warning("balldontlie_failed", error=str(e))

        # All sources failed
        return DomainExecutionResult(
            success=False,
            domain=self.domain_name,
            tool_name="nba_games_cascade",
            error="All NBA data sources failed (nba_api, ESPN, BallDontLie)",
        )

    async def _execute_player_stats(self, player_name: str) -> DomainExecutionResult:
        """Esegue tool statistiche giocatore."""
        from me4brain.domains.sports_nba.tools import nba_api

        try:
            # Prima cerca giocatore
            players_data = await nba_api.balldontlie_players(search=player_name)
            if players_data.get("error") or not players_data.get("players"):
                return DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name="nba_player_search",
                    error=f"Player not found: {player_name}",
                )

            player = players_data["players"][0]
            player_id = player["id"]

            # Poi recupera stats
            stats_data = await nba_api.balldontlie_stats(player_id=player_id)

            return DomainExecutionResult(
                success=not stats_data.get("error"),
                domain=self.domain_name,
                tool_name="nba_player_stats",
                data={
                    "player": player,
                    "stats": stats_data.get("stats", {}),
                    "source": "BallDontLie API v2",
                },
                error=stats_data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="nba_player_stats",
                error=str(e),
            )

    async def _execute_injuries(self) -> DomainExecutionResult:
        """Esegue tool infortuni NBA."""
        from me4brain.domains.sports_nba.tools import nba_api

        try:
            data = await nba_api.espn_injuries()
            return DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name="nba_injuries",
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="nba_injuries",
                error=str(e),
            )

    async def _execute_odds(self) -> DomainExecutionResult:
        """Esegue tool quote scommesse NBA."""
        from me4brain.domains.sports_nba.tools import nba_api

        try:
            data = await nba_api.odds_api_odds()
            return DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name="nba_betting_odds",
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="nba_betting_odds",
                error=str(e),
            )

    async def _execute_standings(self) -> DomainExecutionResult:
        """Esegue tool classifiche NBA con cascata ESPN -> nba_api."""
        from me4brain.domains.sports_nba.tools import nba_api

        # Try ESPN standings first (lighter, faster)
        try:
            data = await nba_api.espn_standings()
            if not data.get("error"):
                return DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="nba_standings",
                    data=data,
                )
        except Exception as e:
            logger.warning("espn_standings_failed", error=str(e))

        # Fallback: nba_api standings
        try:
            data = await nba_api.nba_api_standings()
            if not data.get("error"):
                return DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="nba_api_standings",
                    data=data,
                )
        except Exception as e:
            logger.warning("nba_api_standings_failed", error=str(e))

        return DomainExecutionResult(
            success=False,
            domain=self.domain_name,
            tool_name="nba_standings",
            error="All standings sources failed",
        )

    async def _execute_betting_analysis(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Esegue analisi pronostici completa via NBABettingAnalyzer.

        Rileva se è per una partita specifica o per il daily slate.
        """
        from me4brain.domains.sports_nba.tools.betting_analyzer import NBABettingAnalyzer
        from me4brain.domains.response_guardrails import (
            apply_response_guardrails,
        )

        analyzer = NBABettingAnalyzer()
        query_lower = query.lower()

        # Detect se ci sono nomi squadre nella query
        home_team = ""
        away_team = ""
        vs_markers = [" vs ", " contro ", " - ", " versus "]

        for marker in vs_markers:
            if marker in query_lower:
                parts = query_lower.split(marker)
                if len(parts) == 2:
                    # Estrai nomi squadre rimuovendo parole comuni
                    home_team = self._clean_team_name(parts[0])
                    away_team = self._clean_team_name(parts[1])
                    break

        if home_team and away_team:
            # Analisi partita specifica
            try:
                betting_analysis = await analyzer.analyze_game(home_team, away_team)
                result = DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="nba_betting_analysis",
                    data=analyzer.to_dict(betting_analysis),
                )
                # Apply guardrails to individual game analysis
                return [apply_response_guardrails(result, self.domain_name)]
            except Exception as e:
                logger.error("betting_analysis_failed", error=str(e))
                return [
                    DomainExecutionResult(
                        success=False,
                        domain=self.domain_name,
                        tool_name="nba_betting_analysis",
                        error=str(e),
                    )
                ]
        else:
            # Daily slate: pronostici per tutte le partite di oggi
            try:
                analyses = await analyzer.analyze_daily_slate()
                results_data = [analyzer.to_dict(a) for a in analyses]
                result = DomainExecutionResult(
                    success=True,
                    domain=self.domain_name,
                    tool_name="nba_daily_betting_analysis",
                    data={
                        "daily_predictions": results_data,
                        "games_analyzed": len(results_data),
                        "source": "NBABettingAnalyzer",
                    },
                )
                # Apply guardrails to daily slate (pagination, compression)
                return [apply_response_guardrails(result, self.domain_name)]
            except Exception as e:
                logger.error("daily_slate_analysis_failed", error=str(e))
                return [
                    DomainExecutionResult(
                        success=False,
                        domain=self.domain_name,
                        tool_name="nba_daily_betting_analysis",
                        error=str(e),
                    )
                ]

    def _detect_pattern(self, query: str, patterns: list[str]) -> bool:
        """Check se query contiene uno dei pattern."""
        return any(pattern in query for pattern in patterns)

    def _extract_player_name(self, query: str, analysis: dict[str, Any]) -> str:
        """Estrae nome giocatore usando entity extraction centralizzata."""
        from me4brain.core.nlp_utils import get_entity_by_type

        # 1. Usa entity tipizzata "person" da LLM analysis
        person = get_entity_by_type(analysis, "person")
        if person:
            logger.debug("player_from_llm_analysis", player=person)
            return person

        # 2. Fallback: keywords giocatori noti
        player_keywords = [
            "lebron",
            "curry",
            "doncic",
            "giannis",
            "jokic",
            "durant",
            "tatum",
            "morant",
        ]
        query_lower = query.lower()
        for kw in player_keywords:
            if kw in query_lower:
                return kw.capitalize()

        return "LeBron"  # Default

    def handles_service(self, service_name: str) -> bool:
        """Verifica se questo handler gestisce il servizio."""
        return service_name in self.HANDLED_SERVICES

    @staticmethod
    def _clean_team_name(raw: str) -> str:
        """Pulisce nome squadra da parole comuni nella query."""
        stop_words = {
            "pronostico",
            "analisi",
            "partita",
            "game",
            "match",
            "betting",
            "prediction",
            "quote",
            "scommesse",
            "prossima",
            "per",
            "di",
            "del",
            "la",
            "il",
            "le",
            "i",
            "a",
            "value",
            "bet",
            "stasera",
            "oggi",
            "domani",
        }
        words = raw.strip().split()
        cleaned = [w for w in words if w.lower() not in stop_words]
        return " ".join(cleaned).strip()

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Esegue tool NBA specifico per nome.

        Usato per chiamate dirette a tool specifici.
        """
        from me4brain.domains.sports_nba.tools import nba_api

        logger.info(
            "sports_nba_execute_tool",
            tool_name=tool_name,
            arguments=arguments,
        )

        return await nba_api.execute_tool(tool_name, arguments)
