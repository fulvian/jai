from __future__ import annotations
"""Finance/Crypto Domain - Stock prices, crypto, portfolio analysis."""

from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class StockQuote(BaseModel):
    """Stock price quote."""

    symbol: str
    price: float
    change: float = 0.0
    change_percent: float = 0.0
    volume: int = 0
    market_cap: float | None = None
    pe_ratio: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None


class CryptoPrice(BaseModel):
    """Cryptocurrency price."""

    symbol: str
    price_usd: float
    change_24h: float = 0.0
    change_7d: float = 0.0
    market_cap: float | None = None
    volume_24h: float | None = None


class FinanceDomain(BaseDomain):
    """Finance domain - stocks, crypto, financial analysis.

    Example:
        # Get stock price
        quote = await client.domains.finance.stock_quote("AAPL")

        # Get crypto price
        crypto = await client.domains.finance.crypto_price("BTC")

        # Search news
        news = await client.domains.finance.financial_news("Apple earnings")
    """

    @property
    def domain_name(self) -> str:
        return "finance_crypto"

    async def stock_quote(self, symbol: str) -> StockQuote:
        """Get current stock quote.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Stock quote with price and metrics
        """
        result = await self._execute_tool(
            "stock_quote",
            {"symbol": symbol},
        )
        return StockQuote.model_validate(result.get("result", {}))

    async def stock_history(
        self,
        symbol: str,
        period: str = "1y",
    ) -> list[dict[str, Any]]:
        """Get historical stock prices.

        Args:
            symbol: Stock ticker
            period: Time period ("1d", "5d", "1mo", "1y", "5y")

        Returns:
            List of historical data points
        """
        result = await self._execute_tool(
            "stock_history",
            {"symbol": symbol, "period": period},
        )
        return result.get("result", {}).get("history", [])

    async def crypto_price(self, symbol: str) -> CryptoPrice:
        """Get cryptocurrency price.

        Args:
            symbol: Crypto symbol (e.g., "BTC", "ETH")

        Returns:
            Crypto price data
        """
        result = await self._execute_tool(
            "crypto_price",
            {"symbol": symbol},
        )
        return CryptoPrice.model_validate(result.get("result", {}))

    async def crypto_list_top(
        self,
        limit: int = 10,
    ) -> list[CryptoPrice]:
        """Get top cryptocurrencies by market cap.

        Args:
            limit: Number of results

        Returns:
            List of top cryptos
        """
        result = await self._execute_tool(
            "crypto_list_top",
            {"limit": limit},
        )
        coins = result.get("result", {}).get("coins", [])
        return [CryptoPrice.model_validate(c) for c in coins]

    async def financial_news(
        self,
        query: str,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Search financial news.

        Args:
            query: Search query
            max_results: Maximum results

        Returns:
            List of news articles
        """
        result = await self._execute_tool(
            "financial_news",
            {"query": query, "max_results": max_results},
        )
        return result.get("result", {}).get("articles", [])

    async def currency_convert(
        self,
        amount: float,
        from_currency: str,
        to_currency: str,
    ) -> dict[str, Any]:
        """Convert between currencies.

        Args:
            amount: Amount to convert
            from_currency: Source currency code
            to_currency: Target currency code

        Returns:
            Conversion result
        """
        result = await self._execute_tool(
            "currency_convert",
            {
                "amount": amount,
                "from_currency": from_currency,
                "to_currency": to_currency,
            },
        )
        return result.get("result", {})
