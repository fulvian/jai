"""Finance & Crypto Domain Handler.

Implementazione DomainHandler per dati finanziari e crypto.
Gestisce query su prezzi crypto, azioni, mercati, news.

Volatilità: REAL_TIME (dati cambiano ogni secondo)
Tool-First: Sempre API fresh, mai memoria
"""

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


class FinanceCryptoHandler(DomainHandler):
    """Domain handler per Finance e Crypto queries.

    Capabilities:
    - Crypto: prezzi, trending, chart storici
    - Stock: quote azioni, storico
    - News: notizie mercati finanziari
    - Economic: dati macro FRED

    Example queries:
    - "Prezzo Bitcoin oggi"
    - "Quanto vale Ethereum in euro?"
    - "Quote Apple e Tesla"
    - "Trending crypto"
    """

    # Services gestiti da questo handler
    HANDLED_SERVICES = frozenset(
        {
            "CoinGeckoService",
            "BinanceService",
            "YahooFinanceService",
            "FinnhubService",
            "FREDService",
            "HyperliquidService",
            "AlpacaService",
        }
    )

    # Keywords per routing rapido
    FINANCE_KEYWORDS = frozenset(
        {
            # Crypto
            "crypto",
            "cryptocurrency",
            "criptovaluta",
            "criptovalute",
            "bitcoin",
            "btc",
            "ethereum",
            "eth",
            "solana",
            "sol",
            "xrp",
            "ripple",
            "cardano",
            "ada",
            "dogecoin",
            "doge",
            "bnb",
            "binance",
            "polkadot",
            "dot",
            "avax",
            "avalanche",
            "shiba",
            "pepe",
            "meme",
            "coin",
            "token",
            # Stock
            "stock",
            "azione",
            "azioni",
            "quote",
            "quotazione",
            "apple",
            "aapl",
            "tesla",
            "tsla",
            "nvidia",
            "nvda",
            "microsoft",
            "msft",
            "amazon",
            "amzn",
            "google",
            "googl",
            "meta",
            "netflix",
            "nflx",
            "sp500",
            "nasdaq",
            "dow",
            # Finance
            "prezzo",
            "price",
            "valore",
            "value",
            "market",
            "mercato",
            "trading",
            "borsa",
            "exchange",
            "rally",
            "crash",
            "bull",
            "bear",
            "trend",
            # News
            "news",
            "notizie",
            "aggiornamenti",
            # Economic
            "fed",
            "interest",
            "rate",
            "tasso",
            "inflazione",
            "gdp",
            "pil",
        }
    )

    # Pattern per sub-category
    CRYPTO_PATTERNS = [
        "crypto",
        "bitcoin",
        "btc",
        "ethereum",
        "eth",
        "solana",
        "xrp",
        "cardano",
        "dogecoin",
        "bnb",
        "binance",
        "coin",
        "token",
    ]
    STOCK_PATTERNS = [
        "stock",
        "azione",
        "quote",
        "apple",
        "tesla",
        "nvidia",
        "microsoft",
        "amazon",
        "google",
        "meta",
        "nasdaq",
        "borsa",
    ]
    NEWS_PATTERNS = ["news", "notizie", "aggiornamenti"]
    SEC_PATTERNS = [
        "sec",
        "edgar",
        "10-k",
        "10-q",
        "8-k",
        "filing",
        "filings",
        "bilancio",
        "annual report",
        "quarterly",
        "trimestrale",
        "balance sheet",
        "income statement",
        "earnings",
    ]

    @property
    def domain_name(self) -> str:
        return "finance_crypto"

    @property
    def volatility(self) -> DomainVolatility:
        """Dati finanziari cambiano in real-time."""
        return DomainVolatility.REAL_TIME

    @property
    def default_ttl_hours(self) -> int:
        """TTL molto breve per dati finanziari."""
        return 1  # 1 ora max

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="crypto_prices",
                description="Prezzi crypto real-time (Bitcoin, Ethereum, etc.)",
                keywords=["crypto", "bitcoin", "ethereum", "prezzo", "price"],
                example_queries=[
                    "Prezzo Bitcoin oggi",
                    "Quanto vale Ethereum?",
                    "Crypto trending",
                ],
            ),
            DomainCapability(
                name="stock_quotes",
                description="Quote azioni real-time",
                keywords=["stock", "azione", "quote", "apple", "tesla"],
                example_queries=[
                    "Quote Apple",
                    "Prezzo azioni Tesla",
                    "Valore NVIDIA",
                ],
            ),
            DomainCapability(
                name="market_news",
                description="Notizie mercati finanziari",
                keywords=["news", "notizie", "mercato"],
                example_queries=[
                    "News mercati oggi",
                    "Ultime notizie crypto",
                ],
            ),
        ]

    async def initialize(self) -> None:
        logger.info("finance_crypto_handler_initialized")

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        query_lower = query.lower()

        # Check entities da analisi LLM
        entities = analysis.get("entities", [])
        finance_entities = sum(
            1 for e in entities if any(kw in str(e).lower() for kw in self.FINANCE_KEYWORDS)
        )

        # Check keywords diretti
        keyword_matches = sum(1 for kw in self.FINANCE_KEYWORDS if kw in query_lower)

        # Score
        total_matches = finance_entities + keyword_matches

        if total_matches == 0:
            return 0.0
        elif total_matches == 1:
            return 0.5
        elif total_matches == 2:
            return 0.7
        elif total_matches <= 4:
            return 0.85
        else:
            return 1.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        query_lower = query.lower()
        start_time = datetime.now(UTC)
        results: list[DomainExecutionResult] = []

        logger.info(
            "finance_crypto_execute",
            query_preview=query[:50],
            entities=analysis.get("entities", []),
        )

        # Determina sub-category target
        target_category = self._detect_target_category(query_lower)

        try:
            if target_category == "sec":
                results = [await self._execute_sec(query, analysis)]
            elif target_category == "crypto":
                results = await self._execute_crypto(query, analysis)
            elif target_category == "stock":
                results = [await self._execute_stock(query, analysis)]
            elif target_category == "news":
                results = [await self._execute_news(query, analysis)]
            else:
                # Default: crypto (più comune)
                results = await self._execute_crypto(query, analysis)
        except Exception as e:
            logger.error("finance_crypto_execution_error", error=str(e))
            results = [
                DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name=f"finance_{target_category or 'crypto'}",
                    error=str(e),
                )
            ]

        # Add timing
        latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
        for r in results:
            r.latency_ms = latency_ms

        return results

    def _detect_target_category(self, query: str) -> str | None:
        # SEC EDGAR ha priorità alta (query specifiche)
        for pattern in self.SEC_PATTERNS:
            if pattern in query:
                return "sec"
        for pattern in self.CRYPTO_PATTERNS:
            if pattern in query:
                return "crypto"
        for pattern in self.STOCK_PATTERNS:
            if pattern in query:
                return "stock"
        for pattern in self.NEWS_PATTERNS:
            if pattern in query:
                return "news"
        return None

    async def _execute_crypto(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Esegue query crypto."""
        from me4brain.domains.finance_crypto.tools import finance_api

        results = []

        # Estrai coin IDs dalla query
        coin_ids = self._extract_coin_ids(query, analysis)

        # Get prices
        price_data = await finance_api.coingecko_price(ids=coin_ids)
        results.append(
            DomainExecutionResult(
                success=not price_data.get("error"),
                domain=self.domain_name,
                tool_name="coingecko_price",
                data=price_data if not price_data.get("error") else {},
                error=price_data.get("error"),
            )
        )

        # Get trending se query generica
        if "trend" in query.lower():
            trending_data = await finance_api.coingecko_trending()
            results.append(
                DomainExecutionResult(
                    success=not trending_data.get("error"),
                    domain=self.domain_name,
                    tool_name="coingecko_trending",
                    data=trending_data if not trending_data.get("error") else {},
                    error=trending_data.get("error"),
                )
            )

        return results

    async def _execute_stock(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue query stock."""
        from me4brain.domains.finance_crypto.tools import finance_api

        # Estrai ticker dalla query
        ticker = self._extract_ticker(query, analysis)

        try:
            data = await finance_api.yahoo_quote(symbol=ticker)
            return DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name="yahoo_finance_quote",
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="yahoo_finance_quote",
                error=str(e),
            )

    async def _execute_news(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue query news finanziarie."""
        from me4brain.domains.finance_crypto.tools import finance_api

        try:
            data = await finance_api.finnhub_news()
            return DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name="finnhub_news",
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="finnhub_news",
                error=str(e),
            )

    async def _execute_sec(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue query SEC EDGAR per filings aziendali."""
        from me4brain.domains.finance_crypto.tools import finance_api

        # Estrai ticker dalla query
        ticker = self._extract_ticker(query, analysis)

        # Determina tipo filing (default 10-K)
        form_type = "10-K"
        if "10-q" in query.lower() or "trimestrale" in query.lower():
            form_type = "10-Q"
        elif "8-k" in query.lower():
            form_type = "8-K"

        try:
            data = await finance_api.edgar_filings(
                ticker=ticker,
                form_type=form_type,
                limit=5,
            )
            return DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name="edgar_filings",
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="edgar_filings",
                error=str(e),
            )

    def _extract_coin_ids(self, query: str, analysis: dict[str, Any] | None = None) -> str:
        """Estrae coin IDs usando entity extraction centralizzata."""
        from me4brain.core.nlp_utils import get_all_entities_by_type

        coins = []

        # Mappa nome → CoinGecko ID
        coin_map = {
            "bitcoin": "bitcoin",
            "btc": "bitcoin",
            "ethereum": "ethereum",
            "eth": "ethereum",
            "solana": "solana",
            "sol": "solana",
            "xrp": "ripple",
            "ripple": "ripple",
            "cardano": "cardano",
            "ada": "cardano",
            "dogecoin": "dogecoin",
            "doge": "dogecoin",
            "bnb": "binancecoin",
            "binance": "binancecoin",
            "polkadot": "polkadot",
            "dot": "polkadot",
            "avalanche": "avalanche-2",
            "avax": "avalanche-2",
        }

        # 1. Usa TUTTE le entities tipizzate da LLM analysis
        financial_entities = get_all_entities_by_type(analysis, "financial_instrument")
        for entity in financial_entities:
            entity_lower = entity.lower()
            if entity_lower in coin_map:
                coin_id = coin_map[entity_lower]
                if coin_id not in coins:
                    coins.append(coin_id)
                logger.debug("coin_from_llm_analysis", coin=entity)

        # 2. Fallback: pattern matching nella query (sempre eseguito per catturare missed)
        query_lower = query.lower()
        for key, coin_id in coin_map.items():
            if key in query_lower and coin_id not in coins:
                coins.append(coin_id)

        return ",".join(coins) if coins else "bitcoin,ethereum"

    def _extract_ticker(self, query: str, analysis: dict[str, Any] | None = None) -> str:
        """Estrae ticker usando entity extraction centralizzata.

        IMPORTANTE: Valida che l'entity sia un ticker reale prima di usarlo.
        Pattern ticker US: 1-5 lettere uppercase, opzionalmente con .MI per Italia.
        """
        import re

        from me4brain.core.nlp_utils import get_entity_by_type

        # Pattern per ticker validi: 1-5 lettere uppercase, opzionalmente .MI/.PA/etc
        TICKER_PATTERN = re.compile(
            r"^[A-Z]{2,5}(\.[A-Z]{1,2})?$"
        )  # Min 2 chars: avoid false positives like "I"

        ticker_map = {
            "apple": "AAPL",
            "aapl": "AAPL",
            "tesla": "TSLA",
            "tsla": "TSLA",
            "nvidia": "NVDA",
            "nvda": "NVDA",
            "microsoft": "MSFT",
            "msft": "MSFT",
            "amazon": "AMZN",
            "amzn": "AMZN",
            "google": "GOOGL",
            "googl": "GOOGL",
            "meta": "META",
            "netflix": "NFLX",
            "nflx": "NFLX",
            "fiat": "STLA",
            "stellantis": "STLA",
            "ferrari": "RACE",
            "intesa": "ISP.MI",
            "enel": "ENEL.MI",
            "eni": "ENI.MI",
        }

        # 1. Usa entity tipizzata da LLM analysis
        financial_entity = get_entity_by_type(analysis, "financial_instrument")
        if financial_entity:
            entity_lower = financial_entity.lower()
            # Check ticker_map first (nome completo -> ticker)
            if entity_lower in ticker_map:
                logger.debug(
                    "ticker_from_map", original=financial_entity, ticker=ticker_map[entity_lower]
                )
                return ticker_map[entity_lower]

            # Check se è già un ticker valido (uppercase, matches pattern)
            entity_upper = financial_entity.upper().strip()
            if TICKER_PATTERN.match(entity_upper):
                logger.debug("ticker_from_llm_analysis", ticker=entity_upper)
                return entity_upper

            # NON È UN TICKER VALIDO - log warning e continua con fallback
            logger.warning(
                "invalid_ticker_entity",
                entity=financial_entity,
                reason="Not a valid ticker format, falling back to pattern matching",
            )

        # 2. Fallback: pattern matching nella query
        query_lower = query.lower()
        for key, ticker in ticker_map.items():
            if key in query_lower:
                logger.debug("ticker_from_query_pattern", pattern=key, ticker=ticker)
                return ticker

        # 3. Estrai possibile ticker (parola maiuscola che matcha pattern)
        for word in query.split():
            word_upper = word.upper().strip(",.!?")
            if TICKER_PATTERN.match(word_upper):
                logger.debug("ticker_from_query_word", word=word_upper)
                return word_upper

        logger.warning("ticker_fallback_default", query=query[:50], default="AAPL")
        return "AAPL"  # Default

    def handles_service(self, service_name: str) -> bool:
        return service_name in self.HANDLED_SERVICES

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from me4brain.domains.finance_crypto.tools import finance_api

        logger.info(
            "finance_crypto_execute_tool",
            tool_name=tool_name,
            arguments=arguments,
        )

        return await finance_api.execute_tool(tool_name, arguments)
