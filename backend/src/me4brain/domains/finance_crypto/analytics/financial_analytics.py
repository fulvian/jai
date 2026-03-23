"""Universal Financial Analytics - Industry-standard calculations.

Modulo universale per calcoli finanziari basato su best practices SOTA 2026:
- NumPy/Pandas per metriche core (volatilità, drawdown, MA)
- TA-Lib per technical indicators (RSI, MACD, Bollinger)
- empyrical per performance metrics (Sharpe, Sortino, Alpha/Beta)
- statsmodels per regression (Alpha/Beta vs benchmark)

Supporta analisi di singoli asset e portfolio.
"""

from typing import Any

import numpy as np
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# CORE METRICS (NumPy/Pandas)
# =============================================================================


def calculate_returns(prices: pd.Series) -> pd.Series:
    """Calculate simple returns from price series."""
    return prices.pct_change().dropna()


def calculate_log_returns(prices: pd.Series) -> pd.Series:
    """Calculate log returns from price series."""
    return np.log(prices / prices.shift(1)).dropna()


def calculate_volatility(
    prices: pd.Series,
    annualize: bool = True,
    periods_per_year: int = 252,
) -> float:
    """Calculate annualized volatility (std dev of returns).

    Args:
        prices: Price series
        annualize: If True, annualize the volatility
        periods_per_year: Trading periods per year (252 for daily, 52 for weekly)

    Returns:
        Volatility as decimal (e.g., 0.25 = 25%)
    """
    returns = calculate_returns(prices)
    if len(returns) < 2:
        return 0.0

    vol = returns.std()
    if annualize:
        vol *= np.sqrt(periods_per_year)
    return float(vol)


def calculate_drawdown(prices: pd.Series) -> dict[str, Any]:
    """Calculate maximum drawdown from peak.

    Returns:
        dict with max_drawdown_pct, peak_price, trough_price, peak_date, trough_date
    """
    if len(prices) < 2:
        return {
            "max_drawdown_pct": 0.0,
            "peak_price": float(prices.iloc[0]) if len(prices) > 0 else 0.0,
            "trough_price": float(prices.iloc[0]) if len(prices) > 0 else 0.0,
            "peak_date": str(prices.index[0]) if len(prices) > 0 else "N/A",
            "trough_date": str(prices.index[0]) if len(prices) > 0 else "N/A",
            "drawdown_series": [0.0] if len(prices) > 0 else [],
        }

    rolling_max = prices.expanding().max()
    drawdown = (prices - rolling_max) / rolling_max

    max_dd = drawdown.min()
    trough_idx = drawdown.idxmin()

    # Find peak before trough
    peak_idx = prices[:trough_idx].idxmax()

    return {
        "max_drawdown_pct": float(max_dd * 100),
        "peak_price": float(prices[peak_idx]),
        "trough_price": float(prices[trough_idx]),
        "peak_date": str(peak_idx),
        "trough_date": str(trough_idx),
        "drawdown_series": drawdown.fillna(0.0).tolist(),
    }


def calculate_moving_average(
    prices: pd.Series,
    window: int = 50,
    ma_type: str = "simple",
) -> pd.Series:
    """Calculate moving average.

    Args:
        prices: Price series
        window: Window size (e.g., 50 for MA50)
        ma_type: 'simple' or 'exponential'

    Returns:
        Moving average series
    """
    if ma_type == "simple":
        return prices.rolling(window=window).mean()
    elif ma_type == "exponential":
        return prices.ewm(span=window, adjust=False).mean()
    else:
        raise ValueError(f"Unknown ma_type: {ma_type}")


def calculate_ytd_performance(prices: pd.Series) -> float:
    """Calculate YTD performance.

    Assumes prices index is datetime. Finds first price of current year.

    Returns:
        YTD return as percentage
    """
    if len(prices) < 2:
        return 0.0

    if not isinstance(prices.index, pd.DatetimeIndex):
        try:
            prices.index = pd.to_datetime(prices.index)
        except Exception:
            return 0.0

    current_year = prices.index[-1].year
    ytd_prices = prices[prices.index.year == current_year]

    if len(ytd_prices) < 2:
        return 0.0

    start_price = ytd_prices.iloc[0]
    end_price = ytd_prices.iloc[-1]

    if start_price == 0:
        return 0.0

    return float(((end_price - start_price) / start_price) * 100)


# =============================================================================
# PERFORMANCE METRICS (empyrical-inspired)
# =============================================================================


def calculate_sharpe_ratio(
    prices: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Calculate Sharpe ratio.

    Args:
        prices: Price series
        risk_free_rate: Annual risk-free rate (e.g., 0.02 for 2%)
        periods_per_year: Trading periods per year

    Returns:
        Sharpe ratio
    """
    returns = calculate_returns(prices)
    if len(returns) < 2:
        return 0.0

    excess_returns = returns - (risk_free_rate / periods_per_year)

    if returns.std() == 0:
        return 0.0

    sharpe = (excess_returns.mean() / returns.std()) * np.sqrt(periods_per_year)
    return float(sharpe)


def calculate_sortino_ratio(
    prices: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Calculate Sortino ratio (downside deviation only)."""
    returns = calculate_returns(prices)
    if len(returns) < 2:
        return 0.0

    excess_returns = returns - (risk_free_rate / periods_per_year)

    downside_returns = returns[returns < 0]
    if len(downside_returns) == 0 or downside_returns.std() == 0:
        return 0.0

    sortino = (excess_returns.mean() / downside_returns.std()) * np.sqrt(periods_per_year)
    return float(sortino)


def calculate_alpha_beta(
    asset_prices: pd.Series,
    benchmark_prices: pd.Series,
    periods_per_year: int = 252,
) -> dict[str, float]:
    """Calculate alpha and beta vs benchmark using OLS regression.

    Args:
        asset_prices: Asset price series
        benchmark_prices: Benchmark price series (e.g., S&P 500)
        periods_per_year: Trading periods per year

    Returns:
        dict with alpha (annualized), beta, r_squared
    """
    from scipy.stats import linregress

    asset_returns = calculate_returns(asset_prices)
    benchmark_returns = calculate_returns(benchmark_prices)

    if len(asset_returns) < 2 or len(benchmark_returns) < 2:
        return {"alpha": 0.0, "beta": 0.0, "r_squared": 0.0}

    # Align indices
    common_idx = asset_returns.index.intersection(benchmark_returns.index)
    asset_returns = asset_returns.loc[common_idx]
    benchmark_returns = benchmark_returns.loc[common_idx]

    if len(asset_returns) < 2:
        return {"alpha": 0.0, "beta": 0.0, "r_squared": 0.0}

    slope, intercept, r_value, _, _ = linregress(benchmark_returns, asset_returns)

    return {
        "alpha": float(intercept * periods_per_year),  # Annualized
        "beta": float(slope),
        "r_squared": float(r_value**2),
    }


# =============================================================================
# TECHNICAL INDICATORS (TA-Lib wrapper with fallback)
# =============================================================================


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI using TA-Lib or fallback to simple approximation."""
    try:
        import talib

        return pd.Series(talib.RSI(prices.values, timeperiod=period), index=prices.index)
    except ImportError:
        logger.warning("TA-Lib not installed, using simple RSI approximation")
        # Simple RSI approximation
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))


def calculate_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, pd.Series]:
    """Calculate MACD using TA-Lib or fallback to EMA-based."""
    try:
        import talib

        macd, signal_line, hist = talib.MACD(
            prices.values,
            fastperiod=fast,
            slowperiod=slow,
            signalperiod=signal,
        )
        return {
            "macd": pd.Series(macd, index=prices.index),
            "signal": pd.Series(signal_line, index=prices.index),
            "histogram": pd.Series(hist, index=prices.index),
        }
    except ImportError:
        logger.warning("TA-Lib not installed, using EMA-based MACD")
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal).mean()
        return {
            "macd": macd,
            "signal": signal_line,
            "histogram": macd - signal_line,
        }


def calculate_bollinger_bands(
    prices: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> dict[str, pd.Series]:
    """Calculate Bollinger Bands."""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()

    return {
        "upper": sma + (std * std_dev),
        "middle": sma,
        "lower": sma - (std * std_dev),
    }


# =============================================================================
# BATCH ANALYSIS
# =============================================================================


def analyze_asset(
    prices: pd.Series,
    benchmark_prices: pd.Series | None = None,
    include_technical: bool = False,
) -> dict[str, Any]:
    """Comprehensive analysis of a single asset.

    Args:
        prices: Asset price series
        benchmark_prices: Optional benchmark for alpha/beta
        include_technical: Include technical indicators (RSI, MACD, Bollinger)

    Returns:
        dict with all calculated metrics
    """
    result = {
        "volatility": calculate_volatility(prices),
        "drawdown": calculate_drawdown(prices),
        "ytd_performance": calculate_ytd_performance(prices),
        "sharpe_ratio": calculate_sharpe_ratio(prices),
        "sortino_ratio": calculate_sortino_ratio(prices),
    }

    # MA50 comparison
    ma50 = calculate_moving_average(prices, window=50)
    current_price = prices.iloc[-1] if len(prices) > 0 else 0.0
    ma50_value = ma50.iloc[-1] if len(ma50) > 0 and not pd.isna(ma50.iloc[-1]) else None

    if ma50_value and ma50_value > 0:
        result["ma50"] = float(ma50_value)
        result["price_vs_ma50"] = "above" if current_price > ma50_value else "below"
        result["distance_from_ma50_pct"] = float(((current_price - ma50_value) / ma50_value) * 100)

    # Alpha/Beta vs benchmark
    if benchmark_prices is not None and len(benchmark_prices) > 1:
        result["alpha_beta"] = calculate_alpha_beta(prices, benchmark_prices)

    # Technical indicators
    if include_technical and len(prices) > 14:
        try:
            result["rsi"] = float(calculate_rsi(prices).iloc[-1])
            macd_data = calculate_macd(prices)
            result["macd"] = {
                "macd": float(macd_data["macd"].iloc[-1]),
                "signal": float(macd_data["signal"].iloc[-1]),
                "histogram": float(macd_data["histogram"].iloc[-1]),
            }
            bb = calculate_bollinger_bands(prices)
            result["bollinger_bands"] = {
                "upper": float(bb["upper"].iloc[-1]),
                "middle": float(bb["middle"].iloc[-1]),
                "lower": float(bb["lower"].iloc[-1]),
            }
        except Exception as e:
            logger.warning("technical_indicators_error", error=str(e))

    return result
