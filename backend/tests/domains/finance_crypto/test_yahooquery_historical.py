"""Unit tests for yahooquery_historical tool."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from me4brain.domains.finance_crypto.tools.finance_api import yahooquery_historical


@pytest.fixture
def sample_historical_data():
    """Create mock historical data similar to yahooquery response."""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="B")
    data = pd.DataFrame(
        {
            "open": np.random.uniform(100, 110, 100),
            "high": np.random.uniform(105, 115, 100),
            "low": np.random.uniform(95, 105, 100),
            "close": np.random.uniform(100, 110, 100),
            "volume": np.random.randint(1000000, 5000000, 100),
        },
        index=dates,
    )
    return data


class TestYahooqueryHistorical:
    @pytest.mark.asyncio
    async def test_single_symbol_success(self, sample_historical_data):
        """Test successful fetch for single symbol."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = sample_historical_data

        with patch("yahooquery.Ticker", return_value=mock_ticker):
            result = await yahooquery_historical(symbols="AAPL", period="3mo")

        assert "error" not in result
        assert result["source"] == "yahooquery"
        assert result["symbols"] == ["AAPL"]
        assert "AAPL" in result["data"]
        assert result["data"]["AAPL"]["count"] == len(sample_historical_data)

    @pytest.mark.asyncio
    async def test_batch_symbols_success(self, sample_historical_data):
        """Test successful batch fetch for multiple symbols."""
        # yahooquery returns multi-index dataframe for batch
        tickers = ["AAPL", "MSFT"]
        multi_index_data = pd.concat(
            [sample_historical_data, sample_historical_data * 1.05],
            keys=tickers,
            names=["symbol", "date"],
        )

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = multi_index_data

        with patch("yahooquery.Ticker", return_value=mock_ticker):
            result = await yahooquery_historical(symbols=tickers, period="ytd")

        assert "error" not in result
        assert result["symbols"] == tickers
        assert all(ticker in result["data"] for ticker in tickers)

    @pytest.mark.asyncio
    async def test_yahooquery_api_error(self):
        """Test handling of yahooquery API error response."""
        error_data = {"error": "No data found for symbol"}
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = error_data

        with patch("yahooquery.Ticker", return_value=mock_ticker):
            result = await yahooquery_historical(symbols="INVALID", period="1d")

        assert "error" in result
        assert result["source"] == "yahooquery"
        assert "hint" in result

    @pytest.mark.asyncio
    async def test_import_error(self):
        """Test handling when yahooquery is not installed."""
        with patch.dict("sys.modules", {"yahooquery": None}):
            result = await yahooquery_historical(symbols="AAPL")
        assert "error" in result
        assert "yahooquery not installed" in result["error"]

    @pytest.mark.asyncio
    async def test_general_exception(self):
        """Test handling of unexpected exceptions."""
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("Network error")

        with patch("yahooquery.Ticker", return_value=mock_ticker):
            result = await yahooquery_historical(symbols="AAPL")

        assert "error" in result
        assert result["source"] == "yahooquery"

    @pytest.mark.asyncio
    async def test_parameter_validation(self):
        """Test that string symbols are converted to list."""
        mock_history = pd.DataFrame({"close": [100, 101]})
        mock_ticker_cls = MagicMock()
        mock_ticker_instance = MagicMock()
        mock_ticker_instance.history.return_value = mock_history
        mock_ticker_cls.return_value = mock_ticker_instance

        with patch("yahooquery.Ticker", mock_ticker_cls):
            await yahooquery_historical(symbols="AAPL")

        # Verify Ticker called with list
        call_args = mock_ticker_cls.call_args
        assert isinstance(call_args.args[0], list)
        assert call_args.args[0] == ["AAPL"]

    def test_retry_logic(self):
        """Test that yahooquery_historical_with_retry retries on failure."""
        # This would test the retry decorator/function
        # Implementation depends on how retry is structured
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
