"""Integration test for complex finance query (Yahooquery + Analytics)."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from me4brain.domains.finance_crypto.analytics.financial_analytics import analyze_asset
from me4brain.domains.finance_crypto.tools.finance_api import yahooquery_historical


@pytest.mark.asyncio
class TestComplexFinanceQuery:
    """Test the full flow: fetch data via yahooquery, analyze with financial_analytics."""

    @pytest.fixture
    def mock_multi_symbol_data(self):
        """Create mock historical data for BTC, ETH, SOL, and S&P 500."""
        dates = pd.date_range(start="2024-01-01", periods=252, freq="B")

        def create_prices(start_price, volatility=0.02, trend=0.0005):
            np.random.seed(hash(start_price) % 2**32)
            returns = np.random.normal(trend, volatility, 252)
            prices = start_price * (1 + returns).cumprod()
            return pd.Series(prices, index=dates)

        data = {
            "BTC": create_prices(42000, 0.03, 0.001),
            "ETH": create_prices(2800, 0.035, 0.0012),
            "SOL": create_prices(95, 0.04, 0.0015),
            "^GSPC": create_prices(5000, 0.015, 0.0003),
        }
        return data

    async def test_full_analysis_flow(self, mock_multi_symbol_data):
        """Test that yahooquery returns proper data structure and analytics work."""
        # Mock yahooquery to return multi-index dataframe
        tickers = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "^GSPC"]
        frames = []
        for ticker in tickers:
            key = ticker.replace("USDT", "")
            df = pd.DataFrame(
                {
                    "open": mock_multi_symbol_data[key] * 0.99,
                    "high": mock_multi_symbol_data[key] * 1.02,
                    "low": mock_multi_symbol_data[key] * 0.98,
                    "close": mock_multi_symbol_data[key],
                    "volume": np.random.randint(1_000_000, 10_000_000, 252),
                }
            )
            frames.append(df)

        multi_index_data = pd.concat(frames, keys=tickers, names=["symbol", "date"])

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = multi_index_data

        with patch("yahooquery.Ticker", return_value=mock_ticker):
            result = await yahooquery_historical(symbols=tickers, period="ytd")

        # Verify yahooquery result structure
        assert "error" not in result
        assert result["source"] == "yahooquery"
        assert set(result["symbols"]) == set(tickers)

        # Verify each ticker has OHLCV data
        for ticker in tickers:
            assert ticker in result["data"]
            assert "ohlcv" in result["data"][ticker]
            assert len(result["data"][ticker]["ohlcv"]) == 252

        # Now test analytics: convert to price series and analyze
        sp500_prices = pd.Series([row["close"] for row in result["data"]["^GSPC"]["ohlcv"]])
        analysis = analyze_asset(sp500_prices, include_technical=True)

        # Verify analytics structure
        assert "volatility" in analysis
        assert "drawdown" in analysis
        assert "ytd_performance" in analysis
        assert "sharpe_ratio" in analysis
        assert "sortino_ratio" in analysis
        assert "ma50" in analysis
        assert "price_vs_ma50" in analysis
        assert "rsi" in analysis
        assert "macd" in analysis
        assert "bollinger_bands" in analysis

        # Validate types
        assert isinstance(analysis["volatility"], float)
        assert isinstance(analysis["drawdown"], dict)
        assert "drawdown_series" in analysis["drawdown"]  # Verify it's included
        assert isinstance(analysis["ytd_performance"], float)
        assert analysis["price_vs_ma50"] in ["above", "below"]

    async def test_batch_query_optimization(self):
        """Verify that batch query returns all symbols in single API call."""
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"close": [100, 101, 102]})

        with patch("yahooquery.Ticker", return_value=mock_ticker):
            result = await yahooquery_historical(symbols=tickers, period="1mo")

        # Should have called Ticker once with all symbols
        assert mock_ticker.history.call_count == 1
        # The historical method should have been called with period and interval
        history_args = mock_ticker.history.call_args
        assert history_args is not None
        assert "period" in history_args.kwargs

    async def test_fallback_on_yahooquery_failure(self):
        """Test that fallback mechanism works when yahooquery fails."""
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("API rate limit exceeded")

        with patch("yahooquery.Ticker", return_value=mock_ticker):
            result = await yahooquery_historical(symbols="AAPL")

        assert "error" in result
        assert result["source"] == "yahooquery"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
