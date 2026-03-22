"""Finance & Crypto Tools Package.

Esporta tool Finance/Crypto per uso da FinanceCryptoHandler.
"""

from me4brain.domains.finance_crypto.tools.finance_api import (
    AVAILABLE_TOOLS,
    binance_price,
    binance_ticker_24h,
    coingecko_chart,
    coingecko_price,
    coingecko_trending,
    execute_tool,
    finnhub_news,
    finnhub_quote,
    get_executors,
    get_tool_definitions,
    yahoo_quote,
)

__all__ = [
    "AVAILABLE_TOOLS",
    "execute_tool",
    # Engine integration
    "get_tool_definitions",
    "get_executors",
    # CoinGecko
    "coingecko_price",
    "coingecko_trending",
    "coingecko_chart",
    # Binance
    "binance_price",
    "binance_ticker_24h",
    # Yahoo
    "yahoo_quote",
    # Finnhub
    "finnhub_news",
    "finnhub_quote",
]
