"""Unit tests for financial_analytics module."""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from me4brain.domains.finance_crypto.analytics.financial_analytics import (
    calculate_returns,
    calculate_log_returns,
    calculate_volatility,
    calculate_drawdown,
    calculate_moving_average,
    calculate_ytd_performance,
    calculate_sharpe_ratio,
    calculate_sortino_ratio,
    calculate_alpha_beta,
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    analyze_asset,
)


@pytest.fixture
def sample_price_series():
    """Create a sample price series for testing."""
    dates = pd.date_range(start="2024-01-01", periods=252, freq="B")  # 1 year business days
    np.random.seed(42)
    returns = np.random.normal(0.0005, 0.02, 252)
    prices = 100 * (1 + returns).cumprod()
    return pd.Series(prices, index=dates)


@pytest.fixture
def sample_benchmark_series():
    """Create a sample benchmark series."""
    dates = pd.date_range(start="2024-01-01", periods=252, freq="B")
    np.random.seed(123)
    returns = np.random.normal(0.0004, 0.015, 252)
    prices = 100 * (1 + returns).cumprod()
    return pd.Series(prices, index=dates)


class TestCalculateReturns:
    def test_simple_returns(self, sample_price_series):
        returns = calculate_returns(sample_price_series)
        assert len(returns) == len(sample_price_series) - 1
        assert not returns.isna().any()
        assert isinstance(returns, pd.Series)

    def test_log_returns(self, sample_price_series):
        log_returns = calculate_log_returns(sample_price_series)
        assert len(log_returns) == len(sample_price_series) - 1
        assert not log_returns.isna().any()


class TestCalculateVolatility:
    def test_volatility_annualized(self, sample_price_series):
        vol = calculate_volatility(sample_price_series, annualize=True)
        assert isinstance(vol, float)
        assert 0 < vol < 1  # Should be between 0% and 100%
        assert not np.isnan(vol)

    def test_volatility_not_annualized(self, sample_price_series):
        vol = calculate_volatility(sample_price_series, annualize=False)
        assert isinstance(vol, float)
        assert 0 < vol < 1

    def test_constant_prices(self):
        constant_series = pd.Series([100.0] * 100)
        vol = calculate_volatility(constant_series)
        assert vol == 0.0


class TestCalculateDrawdown:
    def test_drawdown_structure(self, sample_price_series):
        dd = calculate_drawdown(sample_price_series)
        assert "max_drawdown_pct" in dd
        assert "peak_price" in dd
        assert "trough_price" in dd
        assert "peak_date" in dd
        assert "trough_date" in dd
        assert "drawdown_series" in dd
        assert isinstance(dd["max_drawdown_pct"], float)
        assert dd["max_drawdown_pct"] <= 0  # Drawdown is negative

    def test_drawdown_values(self):
        # Create series with known drawdown
        prices = pd.Series([100, 110, 120, 90, 100, 110])
        dd = calculate_drawdown(prices)
        # Max drawdown from peak 120 to trough 90 = (90-120)/120 = -25%
        assert abs(dd["max_drawdown_pct"] - (-25.0)) < 0.01


class TestCalculateMovingAverage:
    def test_simple_ma(self, sample_price_series):
        ma = calculate_moving_average(sample_price_series, window=50, ma_type="simple")
        assert isinstance(ma, pd.Series)
        assert len(ma) == len(sample_price_series)
        # First 49 values should be NaN
        assert ma.iloc[:49].isna().all()
        assert not ma.iloc[49:].isna().any()

    def test_exponential_ma(self, sample_price_series):
        ema = calculate_moving_average(sample_price_series, window=50, ma_type="exponential")
        assert isinstance(ema, pd.Series)
        assert len(ema) == len(sample_price_series)

    def test_invalid_ma_type(self, sample_price_series):
        with pytest.raises(ValueError):
            calculate_moving_average(sample_price_series, ma_type="invalid")


class TestCalculateYTDPerformance:
    def test_ytd_performance_structure(self, sample_price_series):
        ytd = calculate_ytd_performance(sample_price_series)
        assert isinstance(ytd, float)
        # Should be a percentage
        assert -100 <= ytd <= 1000  # Reasonable range

    def test_ytd_single_year(self):
        # Create series within single year
        dates = pd.date_range(start="2024-01-01", end="2024-12-31", freq="B")
        prices = pd.Series(np.linspace(100, 150, len(dates)), index=dates)
        ytd = calculate_ytd_performance(prices)
        # Should be positive (prices increased)
        assert ytd > 0

    def test_ytd_multi_year(self):
        # Create multi-year series
        dates = pd.date_range(start="2023-01-01", end="2024-12-31", freq="B")
        prices = pd.Series(np.linspace(100, 150, len(dates)), index=dates)
        ytd = calculate_ytd_performance(prices)
        # Should only consider 2024
        assert isinstance(ytd, float)


class TestCalculateSharpeRatio:
    def test_sharpe_structure(self, sample_price_series):
        sharpe = calculate_sharpe_ratio(sample_price_series)
        assert isinstance(sharpe, float)
        assert not np.isnan(sharpe)

    def test_sharpe_with_risk_free(self, sample_price_series):
        sharpe = calculate_sharpe_ratio(sample_price_series, risk_free_rate=0.02)
        assert isinstance(sharpe, float)

    def test_zero_volatility(self):
        constant_series = pd.Series([100.0] * 100)
        sharpe = calculate_sharpe_ratio(constant_series)
        assert sharpe == 0.0


class TestCalculateSortinoRatio:
    def test_sortino_structure(self, sample_price_series):
        sortino = calculate_sortino_ratio(sample_price_series)
        assert isinstance(sortino, float)
        assert not np.isnan(sortino)

    def test_sortino_vs_sharpe(self, sample_price_series):
        sortino = calculate_sortino_ratio(sample_price_series)
        sharpe = calculate_sharpe_ratio(sample_price_series)
        # Sortino >= Sharpe (downside risk only)
        assert sortino >= sharpe - 0.01  # Allow small diff


class TestCalculateAlphaBeta:
    def test_alpha_beta_structure(self, sample_price_series, sample_benchmark_series):
        ab = calculate_alpha_beta(sample_price_series, sample_benchmark_series)
        assert "alpha" in ab
        assert "beta" in ab
        assert "r_squared" in ab
        assert isinstance(ab["alpha"], float)
        assert isinstance(ab["beta"], float)
        assert 0 <= ab["r_squared"] <= 1

    def test_alpha_beta_perfect_correlation(self):
        # Perfect correlation: beta should be 1, alpha 0
        dates = pd.date_range(start="2024-01-01", periods=100, freq="B")
        asset = pd.Series(np.linspace(100, 110, 100), index=dates)
        benchmark = asset * 1.05  # 5% higher
        ab = calculate_alpha_beta(asset, benchmark)
        assert abs(ab["beta"] - 1.0) < 0.1
        assert abs(ab["alpha"]) < 1.0  # Small alpha

    def test_alpha_beta_insufficient_data(self):
        dates = pd.date_range(start="2024-01-01", periods=2, freq="B")
        asset = pd.Series([100, 101], index=dates)
        benchmark = pd.Series([100, 102], index=dates)
        ab = calculate_alpha_beta(asset, benchmark)
        assert ab["alpha"] == 0.0
        assert ab["beta"] == 0.0


class TestTechnicalIndicators:
    def test_rsi(self, sample_price_series):
        rsi = calculate_rsi(sample_price_series)
        assert isinstance(rsi, pd.Series)
        assert len(rsi) == len(sample_price_series)
        # RSI values should be between 0 and 100 (allow some NaN at start)
        valid_rsi = rsi.dropna()
        assert (valid_rsi >= 0).all() and (valid_rsi <= 100).all()

    def test_macd(self, sample_price_series):
        macd_data = calculate_macd(sample_price_series)
        assert "macd" in macd_data
        assert "signal" in macd_data
        assert "histogram" in macd_data
        for key in macd_data:
            assert isinstance(macd_data[key], pd.Series)
            assert len(macd_data[key]) == len(sample_price_series)

    def test_bollinger_bands(self, sample_price_series):
        bb = calculate_bollinger_bands(sample_price_series)
        assert "upper" in bb
        assert "middle" in bb
        assert "lower" in bb
        for key in bb:
            assert isinstance(bb[key], pd.Series)
        # Upper should be > middle > lower
        valid_idx = bb["middle"].dropna().index
        assert (bb["upper"].loc[valid_idx] > bb["middle"].loc[valid_idx]).all()
        assert (bb["middle"].loc[valid_idx] > bb["lower"].loc[valid_idx]).all()


class TestAnalyzeAsset:
    def test_full_analysis(self, sample_price_series):
        result = analyze_asset(sample_price_series, include_technical=True)
        # Core metrics
        assert "volatility" in result
        assert "drawdown" in result
        assert "ytd_performance" in result
        assert "sharpe_ratio" in result
        assert "sortino_ratio" in result
        # MA50
        assert "ma50" in result
        assert "price_vs_ma50" in result
        assert result["price_vs_ma50"] in ["above", "below"]
        # Technical indicators
        assert "rsi" in result
        assert "macd" in result
        assert "bollinger_bands" in result

    def test_analysis_with_benchmark(self, sample_price_series, sample_benchmark_series):
        result = analyze_asset(sample_price_series, benchmark_prices=sample_benchmark_series)
        assert "alpha_beta" in result

    def test_analysis_without_technical(self, sample_price_series):
        result = analyze_asset(sample_price_series, include_technical=False)
        assert "rsi" not in result
        assert "macd" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
