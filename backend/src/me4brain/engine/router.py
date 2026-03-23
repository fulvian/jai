"""Tool Router - LLM-based routing using native function calling.

The router is responsible for:
1. Presenting available tools to the LLM
2. Receiving tool selection decisions from the LLM
3. Parsing tool calls into executable ToolTasks

Uses OpenAI-compatible function calling API.
"""

from __future__ import annotations

from typing import Any

import structlog

from me4brain.engine.catalog import ToolCatalog
from me4brain.engine.types import ToolTask
from me4brain.llm.models import LLMRequest, Message, Tool, ToolFunction
from me4brain.llm.provider_factory import resolve_model_client

logger = structlog.get_logger(__name__)


class ToolRouter:
    """Routes queries to appropriate tools using LLM function calling.

    The LLM sees ALL available tools and decides:
    1. Which tools to call (can be multiple)
    2. With which arguments

    NO hardcoded fallbacks. The LLM decides everything.

    Example:
        router = ToolRouter(catalog, llm_client)
        tasks = await router.route("Prezzo Bitcoin e meteo Roma")
        # Returns: [ToolTask(tool_name="coingecko_price", ...),
        #           ToolTask(tool_name="openmeteo_weather", ...)]
    """

    def __init__(
        self,
        catalog: ToolCatalog,
        llm_client: Any,  # NanoGPTClient
        model: str = "kimi-k2-5",
    ) -> None:
        """Initialize router.

        Args:
            catalog: Tool catalog with all available tools
            llm_client: LLM client with function calling support
            model: Model to use for routing (Kimi K2.5 recommended)
        """
        self._catalog = catalog
        self._llm = llm_client
        self._model = model

    async def route(
        self,
        query: str,
        context: str | None = None,
        max_tools: int = 100,
    ) -> list[ToolTask]:
        """Determine which tools to call for the query.

        Args:
            query: User's natural language query
            context: Optional additional context
            max_tools: Maximum number of tools to call

        Returns:
            List of ToolTask objects with tool names and arguments.
            Empty list if no tools are needed or LLM decides to answer directly.
        """
        # Get function schemas from catalog
        schemas = self._catalog.get_function_schemas()

        if not schemas:
            logger.warning("router_no_tools_available")
            return []

        # Build tools list for LLM
        tools = self._build_tools_list(schemas)

        # Build system message
        system_prompt = self._build_system_prompt(max_tools)

        # Build user message
        user_content = query
        if context:
            user_content = f"Context: {context}\n\nQuery: {query}"

        # Resolve model client and create LLM request
        client, actual_model = resolve_model_client(self._model)
        request = LLMRequest(
            model=actual_model,
            messages=[
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_content),
            ],
            tools=tools,
            tool_choice="auto",  # Let LLM decide
            parallel_tool_calls=True,  # Allow multiple tools
            temperature=0.0,  # Deterministic for consistent routing
            max_tokens=1024,
        )

        try:
            response = await client.generate_response(request)

            # Parse tool calls from response
            tasks = self._parse_tool_calls(response)

            # Validate tool availability before returning
            validated_tasks = await self._validate_tool_availability(tasks)

            logger.info(
                "router_decision",
                query_preview=query[:50],
                tools_selected=len(validated_tasks),
                tool_names=[t.tool_name for t in validated_tasks],
                tools_unavailable=len(tasks) - len(validated_tasks),
            )

            return validated_tasks[:max_tools]

        except Exception as e:
            logger.error(
                "router_failed",
                error=str(e),
                query_preview=query[:50],
            )
            return []

    async def _validate_tool_availability(self, tasks: list[ToolTask]) -> list[ToolTask]:
        """Validate that required tools are available and configured.

        Checks for:
        - API keys in environment variables
        - Tool configuration status
        - Required dependencies

        Args:
            tasks: List of ToolTask objects to validate

        Returns:
            List of validated ToolTask objects (filtered)
        """
        import os

        validated = []
        unavailable_tools = []

        for task in tasks:
            tool_name = task.tool_name
            is_available = True
            reason = ""

            # Travel domain tools - check for API keys
            if tool_name in [
                "amadeus_search_flights",
                "amadeus_airport_search",
                "amadeus_confirm_price",
                "amadeus_book_flight",
            ]:
                if not os.getenv("AMADEUS_CLIENT_ID") or not os.getenv("AMADEUS_CLIENT_SECRET"):
                    is_available = False
                    reason = "Amadeus API keys not configured"

            elif tool_name in ["google_places_hotels", "google_places_restaurants"]:
                if not os.getenv("GOOGLE_PLACES_API_KEY"):
                    is_available = False
                    reason = "Google Places API key not configured"

            # Finance domain tools
            elif tool_name in [
                "fmp_dcf",
                "fmp_ratios",
                "fmp_key_metrics",
                "fmp_income_statement",
                "fmp_balance_sheet",
                "fmp_cash_flow",
            ]:
                if not os.getenv("FMP_API_KEY"):
                    is_available = False
                    reason = "FMP API key not configured"

            elif tool_name in ["yahooquery_historical", "yahoo_quote"]:
                # yahooquery is free, always available
                is_available = True

            elif tool_name in ["finnhub_news", "finnhub_quote"]:
                if not os.getenv("FINNHUB_API_KEY"):
                    is_available = False
                    reason = "Finnhub API key not configured"

            elif tool_name in ["coingecko_price", "coingecko_market_data"]:
                # CoinGecko free tier, always available
                is_available = True

            elif tool_name in ["binance_ticker", "binance_klines"]:
                # Binance free tier, always available
                is_available = True

            # Google Workspace tools
            elif (
                tool_name in ["google_gmail_search", "google_gmail_send"]
                or tool_name in ["google_calendar_list_events", "google_calendar_create_event"]
                or tool_name in ["google_drive_search", "google_drive_upload"]
            ):
                if not os.getenv("GOOGLE_OAUTH_TOKEN"):
                    is_available = False
                    reason = "Google OAuth token not configured"

            if is_available:
                validated.append(task)
            else:
                unavailable_tools.append((tool_name, reason))

        if unavailable_tools:
            logger.warning(
                "router_tools_unavailable",
                unavailable_tools=unavailable_tools,
                validated_count=len(validated),
            )

        return validated

    def _build_system_prompt(self, max_tools: int) -> str:
        """Build system prompt for routing."""
        from datetime import UTC, datetime

        # Get current date for context
        now = datetime.now(UTC)
        current_date = now.strftime("%Y-%m-%d")
        current_datetime = now.isoformat()

        return f"""Sei un assistente che decide quali strumenti (tools) utilizzare per rispondere alle domande degli utenti.

DATA E ORA CORRENTE: {current_datetime}
DATA OGGI: {current_date}

ISTRUZIONI:
1. Analizza la query dell'utente
2. Seleziona i tool appropriati per ottenere le informazioni richieste
3. Puoi selezionare MULTIPLI tool se la query richiede dati da fonti diverse
4. Massimo {max_tools} tool per query
5. Estrai gli argomenti corretti dalla query

REGOLE CRITICHE PER LE DATE:
- USA SEMPRE {current_date} come riferimento per "oggi", "domani", "questa settimana"
- Per "oggi" → time_min="{current_date}T00:00:00Z", time_max="{current_date}T23:59:59Z"
- Per "domani" → calcola la data successiva
- Per "questa settimana" → calcola la data di fine settimana

REGOLE CRITICHE PER GLI ARGOMENTI:
- NON aggiungere prefissi come "site:", "inurl:", "@" o altri modificatori agli argomenti
- Passa SOLO il valore richiesto (es. per google_drive_search, usa solo "comune di allumiere", NON "comune di allumiere site:drive.google.com")
- Per città, usa solo il nome (es. "Roma", "Caltanissetta"), senza aggiungere paese o regione
- Estrai i numeri correttamente (es. "prossimi 3 giorni" → days=3)

GOOGLE WORKSPACE - REGOLE SPECIALI:
- Se l'utente menziona "email", "mail", "Gmail" → usa SEMPRE google_gmail_search
- Se l'utente menziona "calendario", "calendar", "eventi", "riunioni", "meeting" → usa SEMPRE google_calendar_list_events
- Se l'utente menziona "Google Drive", "documenti", "file" → usa google_drive_search
- Per ricerche storiche (es. "da giugno a dicembre 2025"), usa questi parametri:
  - Gmail: query semplice, il date range va nella query (es. "allumiere after:2025/06/01 before:2025/12/31")
  - Calendar: usa time_min e time_max in formato ISO (es. "2025-06-01T00:00:00Z")
- Se la query richiede più fonti (Drive + Gmail + Calendar), chiama TUTTI i tool corrispondenti

REGOLE PER TASK RICORRENTI VS ONE-TIME:
- Se l'utente vuole impostare un task RICORRENTE/SCHEDULATO (es. "ogni giorno", "ogni ora", "settimanalmente", "every day") → usa create_autonomous_agent
- Se l'utente vuole MONITORARE condizioni nel tempo (es. "avvisami quando", "alert me if") → usa create_autonomous_agent
- Se l'utente vuole un'analisi ADESSO/IMMEDIATA senza scheduling → usa i tool di analisi (fmp_*, yahoo_*, etc.)
- Key distinction: "analyze X every day" → create_autonomous_agent | "analyze X now" → finance tools

REGOLE GENERALI:
- Se la query menziona più entità crypto (es. "Bitcoin ed Ethereum"), chiama il tool una volta con tutti gli ID

REGOLE CRITICHE PER CONFRONTI AZIONARI (Apple vs Tesla, etc.):
- Per ogni TICKER menzionato, devi chiamare i tool finanziari SEPARATAMENTE
- Esempio: "confronta Apple e Tesla" → chiama fmp_dcf(AAPL) + fmp_dcf(TSLA) + fmp_ratios(AAPL) + fmp_ratios(TSLA)
- OGNI ticker richiede la sua chiamata tool, NON concatenarli in una sola chiamata
- I tool come fmp_dcf, fmp_ratios, fmp_key_metrics, yahoo_quote accettano UN SOLO symbol alla volta

- Se la query richiede dati da domini diversi (es. "prezzo crypto e meteo"), usa tool diversi
- Sii preciso con i parametri: estrai esattamente ciò che l'utente chiede

REGOLE CRITICHE PER FINANCE/CRYPTO (SOTA 2026):
- Per dati storici (YTD, performance, volatilità): usa yahooquery_historical (più veloce di yahoo_quote)
  - Esempio: "YTD S&P 500" → yahooquery_historical(symbols="^GSPC", period="ytd")
  - Batch: "YTD BTC, ETH, SOL" → yahooquery_historical(symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"], period="ytd")
- Per news finanziarie: usa finnhub_news (market news) o newsdata_search (query specifica)
  - Esempio: "news BTC ultime 48h" → newsdata_search(query="Bitcoin", country="us")
  - Esempio: "notizie mercato" → finnhub_news(category="general")
- NON usare yahoo_quote per dati storici (solo prezzo corrente)
- NON usare technical_indicators a meno che esplicitamente richiesto
- NON duplicare chiamate: se hai già chiamato yahooquery_historical(BTCUSDT, ytd), non chiamarlo di nuovo

OTTIMIZZAZIONE BATCH:
- yahooquery_historical supporta batch nativo: yahooquery_historical(symbols=["AAPL", "MSFT", "GOOGL"])
- Preferire 1 chiamata batch vs N chiamate singole per ridurre latenza

Se nessun tool è appropriato, rispondi direttamente senza chiamare tool."""

    def _build_tools_list(
        self,
        schemas: list[dict[str, Any]],
    ) -> list[Tool]:
        """Convert OpenAI schemas to LLMRequest Tool objects."""
        tools = []
        for schema in schemas:
            func = schema.get("function", {})
            tools.append(
                Tool(
                    type="function",
                    function=ToolFunction(
                        name=func.get("name", ""),
                        description=func.get("description", ""),
                        parameters=func.get("parameters", {}),
                    ),
                )
            )
        return tools

    def _try_fix_json(self, raw: str) -> dict:
        """Attempt to fix malformed JSON from LLM.

        Common issues:
        - Duplicate objects concatenated
        - Missing closing quotes/braces
        - Extra characters after valid JSON
        """
        import json
        import re

        # Try to find first valid JSON object
        # Pattern: find { ... } that is valid JSON
        matches = re.finditer(r"\{[^{}]*\}", raw)
        for match in matches:
            try:
                obj = json.loads(match.group())
                if obj:  # Non-empty object
                    logger.debug(
                        "router_json_fixed",
                        original=raw[:50],
                        fixed=obj,
                    )
                    return obj
            except json.JSONDecodeError:
                continue

        # Try to fix common issues
        # Remove duplicate objects (keep first)
        if raw.count("{") > 1:
            first_close = raw.find("}")
            if first_close > 0:
                try:
                    fixed = raw[: first_close + 1]
                    # Fix missing closing quote before comma
                    fixed = re.sub(r'": "([^"]*), "', r'": "\1", "', fixed)
                    obj = json.loads(fixed)
                    if obj:
                        logger.debug(
                            "router_json_fixed_truncated",
                            original=raw[:50],
                            fixed=obj,
                        )
                        return obj
                except json.JSONDecodeError:
                    pass

        return {}

    def _parse_tool_calls(self, response: Any) -> list[ToolTask]:
        """Parse tool calls from LLM response.

        Args:
            response: LLMResponse object

        Returns:
            List of ToolTask objects
        """
        import json

        tasks = []

        # Get first choice
        if not response.choices:
            return tasks

        choice = response.choices[0]
        message = choice.message

        # Check for tool calls
        if not message.tool_calls:
            # LLM decided to answer directly without tools
            logger.debug("router_no_tool_calls", finish_reason=choice.finish_reason)
            return tasks

        for tool_call in message.tool_calls:
            try:
                # Parse arguments JSON
                arguments = {}
                if tool_call.function.arguments:
                    try:
                        arguments = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        # Tentativo di fix per JSON malformato
                        raw = tool_call.function.arguments
                        arguments = self._try_fix_json(raw)
                        if not arguments:
                            logger.warning(
                                "router_invalid_arguments_json",
                                tool_name=tool_call.function.name,
                                raw_args=raw[:100],
                            )

                task = ToolTask(
                    tool_name=tool_call.function.name,
                    arguments=arguments,
                    call_id=tool_call.id,
                )
                tasks.append(task)

                logger.debug(
                    "router_tool_parsed",
                    tool_name=task.tool_name,
                    arguments=task.arguments,
                )

            except Exception as e:
                logger.error(
                    "router_tool_parse_error",
                    tool_call=str(tool_call),
                    error=str(e),
                )

        return tasks

    async def route_with_fallback(
        self,
        query: str,
        fallback_tools: list[str] | None = None,
    ) -> list[ToolTask]:
        """Route with explicit fallback tools if LLM fails.

        This is a safety mechanism for production use.

        Args:
            query: User query
            fallback_tools: Tool names to try if LLM returns nothing

        Returns:
            ToolTasks from LLM or fallback
        """
        tasks = await self.route(query)

        if tasks:
            return tasks

        if fallback_tools:
            logger.info(
                "router_using_fallback",
                fallback_tools=fallback_tools,
            )
            return [ToolTask(tool_name=name, arguments={}) for name in fallback_tools]

        return []
