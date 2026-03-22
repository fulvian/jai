"""Unit tests for yahooquery_historical tool."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
from datetime import datetime

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

        with patch(
            "me4brain.domains.finance_crypto.tools.finance_api.Ticker", return_value=mock_ticker
        ):
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

        with patch(
            "me4brain.domains.finance_crypto.tools.finance_api.Ticker", return_value=mock_ticker
        ):
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

        with patch(
            "me4brain.domains.finance_crypto.tools.finance_api.Ticker", return_value=mock_ticker
        ):
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

        with patch(
            "me4brain.domains.finance_crypto.tools.finance_api.Ticker", return_value=mock_ticker
        ):
            result = await yahooquery_historical(symbols="AAPL")

        assert "error" in result
        assert result["source"] == "yahooquery"

    @pytest.mark.asyncio
    async def test_parameter_validation(self):
        """Test that string symbols are converted to list."""
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame({"close": [100, 101]})

        with patch("me4brain.domains.finance_finance_api.Ticker", return_value=mock_ticker):
            result = await yahooquery_historical(symbols="AAPL")

        # Verify Ticker called with list
        call_args = mock_ticker.history.call_args
        assert isinstance(mock_ticker.call_args[0][0], list)  # First arg should be list

    def test_retry_logic(self):
        """Test that yahooquery_historical_with_retry retries on failure."""
        # This would test the retry decorator/function
        # Implementation depends on how retry is structured
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
