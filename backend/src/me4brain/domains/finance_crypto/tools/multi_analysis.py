"""Multi-Dimensional Analysis Orchestrator.

Ispired by OpenClaw stock-analysis synthesize_signal() pattern.
Lancia analisi fondamentale + tecnica + sentiment in parallelo su un asset,
produce scoring composito pesato e signal finale.

Designed to be called as a native Me4BrAIn tool.
"""

import asyncio
from typing import Any, Literal

import structlog

from me4brain.domains.finance_crypto.tools import finance_api

logger = structlog.get_logger(__name__)

# Pesi per ogni dimensione (ispirato da OpenClaw - normalizzati a 1.0)
DIMENSION_WEIGHTS = {
    "fundamentals": 0.25,
    "technical": 0.20,
    "sentiment": 0.15,
    "market_context": 0.10,
    "momentum": 0.15,
    "valuation": 0.15,
}

# Asset type detection
CRYPTO_SUFFIXES = {"-USD", "USDT", "BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT"}


def _detect_asset_type(symbol: str) -> Literal["stock", "crypto", "etf"]:
    """Identifica se l'asset è stock, crypto o ETF."""
    upper = symbol.upper()
    if any(upper.endswith(s) or upper.startswith(s) for s in CRYPTO_SUFFIXES):
        return "crypto"
    # Semplice euristica per ETF (3-4 char, nessun - nel nome)
    etf_symbols = {"SPY", "QQQ", "DIA", "IWM", "VTI", "VOO", "GLD", "TLT", "XLF", "XLK"}
    if upper in etf_symbols:
        return "etf"
    return "stock"


def _calculate_fundamentals_score(metrics: dict, ratios: dict) -> tuple[float, list[str]]:
    """Score fondamentale -1.0 → +1.0 basato su metriche chiave."""
    score = 0.0
    points: list[str] = []

    if "error" in metrics and "error" in ratios:
        return 0.0, ["⚠️ Dati fondamentali non disponibili"]

    # P/E ratio
    pe = ratios.get("peRatioTTM") or metrics.get("peRatioTTM")
    if pe and isinstance(pe, (int, float)):
        if pe < 15:
            score += 0.3
            points.append(f"✅ P/E basso: {pe:.1f} (value)")
        elif pe > 35:
            score -= 0.2
            points.append(f"⚠️ P/E elevato: {pe:.1f} (growth premium)")

    # ROE
    roe = metrics.get("roeTTM") or ratios.get("returnOnEquityTTM")
    if roe and isinstance(roe, (int, float)):
        if roe > 0.20:
            score += 0.2
            points.append(f"✅ ROE forte: {roe * 100:.1f}%")
        elif roe < 0.05:
            score -= 0.1
            points.append(f"⚠️ ROE debole: {roe * 100:.1f}%")

    # Profit margin
    margin = ratios.get("netProfitMarginTTM")
    if margin and isinstance(margin, (int, float)):
        if margin > 0.15:
            score += 0.15
            points.append(f"✅ Margine netto: {margin * 100:.1f}%")
        elif margin < 0.0:
            score -= 0.3
            points.append(f"🔴 In perdita: margine {margin * 100:.1f}%")

    # Debt/Equity
    de = ratios.get("debtEquityRatioTTM")
    if de and isinstance(de, (int, float)):
        if de > 2.0:
            score -= 0.15
            points.append(f"⚠️ Alto indebitamento D/E: {de:.2f}")
        elif de < 0.5:
            score += 0.1
            points.append(f"✅ Basso debito D/E: {de:.2f}")

    return max(-1.0, min(1.0, score)), points


def _calculate_technical_score(indicators: dict) -> tuple[float, list[str]]:
    """Score tecnico -1.0 → +1.0 basato su indicatori."""
    score = 0.0
    points: list[str] = []

    if "error" in indicators:
        return 0.0, ["⚠️ Indicatori tecnici non disponibili"]

    # RSI
    rsi = indicators.get("rsi")
    if rsi and isinstance(rsi, (int, float)):
        if rsi > 70:
            score -= 0.3
            points.append(f"🔴 RSI ipercomprato: {rsi:.1f}")
        elif rsi < 30:
            score += 0.3
            points.append(f"✅ RSI ipervenduto: {rsi:.1f}")
        else:
            score += 0.05
            points.append(f"📊 RSI neutrale: {rsi:.1f}")

    # MACD
    macd = indicators.get("macd")
    macd_signal = indicators.get("macd_signal")
    if macd is not None and macd_signal is not None:
        if isinstance(macd, (int, float)) and isinstance(macd_signal, (int, float)):
            if macd > macd_signal:
                score += 0.2
                points.append("✅ MACD bullish (sopra signal)")
            else:
                score -= 0.2
                points.append("🔴 MACD bearish (sotto signal)")

    # ADX (forza trend)
    adx = indicators.get("adx")
    if adx and isinstance(adx, (int, float)):
        if adx > 25:
            points.append(f"📈 Trend forte (ADX: {adx:.1f})")
        else:
            points.append(f"📊 Trend debole (ADX: {adx:.1f})")

    return max(-1.0, min(1.0, score)), points


def _calculate_sentiment_score(fear_greed: dict, market_ctx: dict) -> tuple[float, list[str]]:
    """Score sentiment -1.0 → +1.0."""
    score = 0.0
    points: list[str] = []

    # Fear & Greed (contrarian-like)
    fg_score = fear_greed.get("score")
    fg_rating = fear_greed.get("rating", "")
    if fg_score is not None and isinstance(fg_score, (int, float)):
        if fg_score <= 25:
            score += 0.2  # Contrarian: extreme fear → buy signal
            points.append(f"🟢 Extreme Fear ({fg_score:.0f}) — contrarian bullish")
        elif fg_score >= 75:
            score -= 0.2  # Contrarian: extreme greed → caution
            points.append(f"🔴 Extreme Greed ({fg_score:.0f}) — contrarian bearish")
        else:
            points.append(f"📊 Fear & Greed: {fg_score:.0f} ({fg_rating})")

    # Market context
    market_score = market_ctx.get("overall_score", 0)
    regime = market_ctx.get("market_regime", "unknown")
    vix = market_ctx.get("vix_level")
    if isinstance(market_score, (int, float)):
        score += market_score * 0.5
        points.append(f"📊 Regime mercato: {regime} (VIX: {vix})")

    return max(-1.0, min(1.0, score)), points


def _calculate_valuation_score(dcf: dict) -> tuple[float, list[str]]:
    """Score valutazione -1.0 → +1.0 basato su DCF."""
    score = 0.0
    points: list[str] = []

    if "error" in dcf:
        return 0.0, ["⚠️ Valutazione DCF non disponibile"]

    dcf_price = dcf.get("dcf")
    stock_price = dcf.get("stockPrice")

    if (
        dcf_price
        and stock_price
        and isinstance(dcf_price, (int, float))
        and isinstance(stock_price, (int, float))
    ):
        upside = ((dcf_price - stock_price) / stock_price) * 100
        if upside > 20:
            score += 0.4
            points.append(f"✅ Sottovalutato ({upside:+.1f}% vs DCF ${dcf_price:.2f})")
        elif upside < -20:
            score -= 0.3
            points.append(f"🔴 Sopravvalutato ({upside:+.1f}% vs DCF ${dcf_price:.2f})")
        else:
            score += 0.05
            points.append(f"📊 Fair value vicino ({upside:+.1f}% vs DCF ${dcf_price:.2f})")

    return max(-1.0, min(1.0, score)), points


def _synthesize_signal(
    scores: dict[str, float],
    risk_flags: list[str],
) -> dict[str, Any]:
    """Combina gli score pesati e genera signal finale.

    Pattern ispirato da OpenClaw synthesize_signal() con override rules.
    """
    # Calcolo weighted score
    total_weight = 0.0
    weighted_sum = 0.0

    for dim, score_val in scores.items():
        weight = DIMENSION_WEIGHTS.get(dim, 0.10)
        weighted_sum += score_val * weight
        total_weight += weight

    composite = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Override rules (ispirato da OpenClaw)
    # Risk-off: penalizza score
    if any("risk-off" in f.lower() or "fear" in f.lower() for f in risk_flags):
        composite *= 0.8

    # Mapping a scala 0-100
    score_0_100 = int(max(0, min(100, (composite + 1) * 50)))

    # Signal classification
    if composite >= 0.4:
        signal = "STRONG BUY"
        confidence = "high"
    elif composite >= 0.15:
        signal = "BUY"
        confidence = "medium-high"
    elif composite >= -0.15:
        signal = "HOLD"
        confidence = "medium"
    elif composite >= -0.4:
        signal = "SELL"
        confidence = "medium-high"
    else:
        signal = "STRONG SELL"
        confidence = "high"

    return {
        "signal": signal,
        "confidence": confidence,
        "composite_score": round(composite, 3),
        "score_0_100": score_0_100,
    }


async def multi_dimensional_analysis(
    symbol: str,
    depth: str = "standard",
) -> dict[str, Any]:
    """Analisi multi-dimensionale autonoma di un asset.

    Lancia in parallelo analisi fondamentale + tecnica + sentiment + valutazione
    e produce un report strutturato con scoring composito.

    Args:
        symbol: Ticker (es. "AAPL", "BTCUSDT", "ETH-USD")
        depth: "quick" (3 dimensioni), "standard" (5), "deep" (tutte + hot/rumor)

    Returns:
        dict con:
        - signal: STRONG BUY / BUY / HOLD / SELL / STRONG SELL
        - composite_score: -1.0 → +1.0
        - score_0_100: 0 → 100
        - breakdown: score per dimensione con punti chiave
        - risk_flags: warning e caveat
    """
    asset_type = _detect_asset_type(symbol)
    logger.info("multi_analysis_start", symbol=symbol, asset_type=asset_type, depth=depth)

    scores: dict[str, float] = {}
    breakdowns: dict[str, dict] = {}
    risk_flags: list[str] = []
    all_points: dict[str, list[str]] = {}

    # === PHASE 1: Parallel data gathering ===
    async def _safe_call(name: str, coro: Any) -> tuple[str, dict]:
        try:
            result = await coro
            return name, result
        except Exception as e:
            logger.error(f"multi_analysis_{name}_error", error=str(e))
            return name, {"error": str(e)}

    # Build task list based on depth and asset type
    gather_tasks = []

    # Always: sentiment
    gather_tasks.append(_safe_call("fear_greed", finance_api.fear_greed_index()))
    gather_tasks.append(_safe_call("market_context", finance_api.market_context_analysis()))

    if asset_type == "stock":
        # Fondamentali stock
        gather_tasks.append(_safe_call("metrics", finance_api.fmp_key_metrics(symbol=symbol)))
        gather_tasks.append(_safe_call("ratios", finance_api.fmp_ratios(symbol=symbol)))
        gather_tasks.append(_safe_call("dcf", finance_api.fmp_dcf(symbol=symbol)))

        # Tecnici
        gather_tasks.append(
            _safe_call("rsi", finance_api.technical_indicators(symbol=symbol, indicator="rsi"))
        )
        gather_tasks.append(
            _safe_call("macd", finance_api.technical_indicators(symbol=symbol, indicator="macd"))
        )

        if depth in ("standard", "deep"):
            gather_tasks.append(
                _safe_call("adx", finance_api.technical_indicators(symbol=symbol, indicator="adx"))
            )
            gather_tasks.append(
                _safe_call(
                    "bbands", finance_api.technical_indicators(symbol=symbol, indicator="bbands")
                )
            )

        if depth == "deep":
            gather_tasks.append(_safe_call("hot_scan", finance_api.hot_scanner()))
            gather_tasks.append(_safe_call("rumor_scan", finance_api.rumor_scanner()))
            gather_tasks.append(
                _safe_call("income", finance_api.fmp_income_statement(symbol=symbol, limit=2))
            )

    elif asset_type == "crypto":
        # Crypto: usa Binance/CoinGecko
        binance_symbol = symbol.replace("-USD", "USDT").replace("-", "")
        if not binance_symbol.endswith("USDT"):
            binance_symbol = binance_symbol + "USDT"

        gather_tasks.append(
            _safe_call("binance_24h", finance_api.binance_ticker_24h(symbol=binance_symbol))
        )
        gather_tasks.append(
            _safe_call(
                "klines", finance_api.binance_klines(symbol=binance_symbol, interval="1d", limit=30)
            )
        )
        gather_tasks.append(
            _safe_call("coingecko", finance_api.coingecko_price(ids=symbol.split("-")[0].lower()))
        )

        if depth in ("standard", "deep"):
            gather_tasks.append(
                _safe_call(
                    "orderbook", finance_api.binance_orderbook(symbol=binance_symbol, limit=20)
                )
            )

        if depth == "deep":
            gather_tasks.append(_safe_call("hot_scan", finance_api.hot_scanner()))
            gather_tasks.append(_safe_call("funding", finance_api.hyperliquid_funding_rates()))

    else:
        # ETF: simile a stock ma senza fondamentali profondi
        gather_tasks.append(
            _safe_call("rsi", finance_api.technical_indicators(symbol=symbol, indicator="rsi"))
        )
        gather_tasks.append(
            _safe_call("macd", finance_api.technical_indicators(symbol=symbol, indicator="macd"))
        )

    # Execute all in parallel
    results_raw = await asyncio.gather(*gather_tasks)
    results = dict(results_raw)

    # === PHASE 2: Scoring per dimensione ===

    # Sentiment
    fg = results.get("fear_greed", {})
    mc = results.get("market_context", {})
    sent_score, sent_points = _calculate_sentiment_score(fg, mc)
    scores["sentiment"] = sent_score
    all_points["sentiment"] = sent_points

    # Market context → separate dimension score
    mc_score = mc.get("overall_score", 0)
    if isinstance(mc_score, (int, float)):
        scores["market_context"] = mc_score
        all_points["market_context"] = [
            f"Regime: {mc.get('market_regime', '?')}, VIX: {mc.get('vix_level', '?')}"
        ]
    else:
        scores["market_context"] = 0.0
        all_points["market_context"] = ["⚠️ Market context non disponibile"]

    if asset_type == "stock":
        # Fundamentals
        metrics = results.get("metrics", {})
        ratios = results.get("ratios", {})
        fund_score, fund_points = _calculate_fundamentals_score(metrics, ratios)
        scores["fundamentals"] = fund_score
        all_points["fundamentals"] = fund_points

        # Tech
        rsi_data = results.get("rsi", {})
        macd_data = results.get("macd", {})
        adx_data = results.get("adx", {})
        combined_tech = {**rsi_data, **macd_data, **adx_data}
        tech_score, tech_points = _calculate_technical_score(combined_tech)
        scores["technical"] = tech_score
        all_points["technical"] = tech_points

        # Valuation
        dcf = results.get("dcf", {})
        val_score, val_points = _calculate_valuation_score(dcf)
        scores["valuation"] = val_score
        all_points["valuation"] = val_points

        # Momentum placeholder from technicals
        rsi_val = rsi_data.get("rsi", 50)
        if isinstance(rsi_val, (int, float)):
            mom = (rsi_val - 50) / 50 * 0.3
            scores["momentum"] = max(-1.0, min(1.0, mom))
        else:
            scores["momentum"] = 0.0
        all_points["momentum"] = [f"RSI-based momentum: {rsi_val}"]

    elif asset_type == "crypto":
        # Crypto scoring
        b24 = results.get("binance_24h", {})
        change_pct = b24.get("price_change_percent", 0)
        b24.get("volume_24h", 0)

        # Momentum from 24h change
        if isinstance(change_pct, (int, float)):
            mom = max(-1.0, min(1.0, change_pct / 10))
            scores["momentum"] = mom
            all_points["momentum"] = [f"24h change: {change_pct:+.2f}%"]
        else:
            scores["momentum"] = 0.0
            all_points["momentum"] = ["⚠️ Dati 24h non disponibili"]

        # Technical from klines (basic)
        klines = results.get("klines", {})
        candles = klines.get("candles", [])
        if len(candles) >= 14:
            closes = [c["close"] for c in candles]
            # Simple RSI-like calculation
            gains = []
            losses = []
            for i in range(1, len(closes)):
                diff = closes[i] - closes[i - 1]
                if diff > 0:
                    gains.append(diff)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(diff))
            avg_gain = sum(gains[-14:]) / 14
            avg_loss = sum(losses[-14:]) / 14
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 100
            tech_score = (rsi - 50) / 50 * 0.3
            scores["technical"] = max(-1.0, min(1.0, tech_score))
            all_points["technical"] = [f"RSI(14) calcolato: {rsi:.1f}"]
        else:
            scores["technical"] = 0.0
            all_points["technical"] = ["⚠️ Dati insufficienti per analisi tecnica"]

        # Fundament = N/A per crypto
        scores["fundamentals"] = 0.0
        all_points["fundamentals"] = ["N/A per crypto"]
        scores["valuation"] = 0.0
        all_points["valuation"] = ["N/A per crypto"]

    else:
        # ETF
        rsi_data = results.get("rsi", {})
        macd_data = results.get("macd", {})
        combined_tech = {**rsi_data, **macd_data}
        tech_score, tech_points = _calculate_technical_score(combined_tech)
        scores["technical"] = tech_score
        all_points["technical"] = tech_points
        scores["fundamentals"] = 0.0
        all_points["fundamentals"] = ["N/A per ETF"]
        scores["valuation"] = 0.0
        all_points["valuation"] = ["N/A per ETF"]
        scores["momentum"] = tech_score * 0.5
        all_points["momentum"] = tech_points

    # Risk flags
    vix = mc.get("vix_level")
    if vix and isinstance(vix, (int, float)) and vix > 30:
        risk_flags.append(f"🔴 VIX elevato ({vix:.1f}) — risk-off environment")
    if fg.get("score") and fg["score"] <= 20:
        risk_flags.append("🔴 Extreme Fear — mercato in panico")
    if fg.get("score") and fg["score"] >= 85:
        risk_flags.append("⚠️ Extreme Greed — possibile correzione")

    # === PHASE 3: Synthesize signal ===
    signal_result = _synthesize_signal(scores, risk_flags)

    # Build dimension breakdown
    for dim in scores:
        breakdowns[dim] = {
            "score": round(scores[dim], 3),
            "weight": DIMENSION_WEIGHTS.get(dim, 0.10),
            "points": all_points.get(dim, []),
        }

    # Deep scan extras
    extras = {}
    if depth == "deep":
        hot = results.get("hot_scan", {})
        rumor = results.get("rumor_scan", {})
        if not isinstance(hot, dict) or "error" not in hot:
            extras["hot_scanner"] = hot.get("summary", "N/A")
        if not isinstance(rumor, dict) or "error" not in rumor:
            extras["rumor_count"] = rumor.get("count", 0)
            extras["high_impact_rumors"] = rumor.get("high_impact", 0)

    # === PHASE 4: Trading Levels (Stop-Loss, Take-Profit) ===
    trading_levels = {}
    if asset_type == "stock":
        try:
            atr_data = await finance_api.technical_indicators(
                symbol=symbol, indicator="atr", period=14
            )
            atr_val = atr_data.get("atr") or atr_data.get("value")
            current_price = None

            # Recupera prezzo corrente da metrics o dcf
            dcf_data = results.get("dcf", {})
            if dcf_data and isinstance(dcf_data, dict):
                current_price = dcf_data.get("stock_price") or dcf_data.get("stockPrice")
            if not current_price:
                metrics_data = results.get("metrics", {})
                if metrics_data and isinstance(metrics_data, dict):
                    current_price = metrics_data.get("marketCap")  # fallback

            if atr_val and current_price and isinstance(atr_val, (int, float)):
                atr_val = float(atr_val)
                current_price = float(current_price)
                trading_levels = {
                    "entry_price": round(current_price, 2),
                    "stop_loss": round(current_price - (2.0 * atr_val), 2),
                    "take_profit_1": round(current_price + (1.5 * atr_val), 2),
                    "take_profit_2": round(current_price + (3.0 * atr_val), 2),
                    "take_profit_3": round(current_price + (4.5 * atr_val), 2),
                    "atr_14": round(atr_val, 4),
                    "risk_reward_ratio": "1:0.75 / 1:1.5 / 1:2.25",
                    "position_sizing": "Max 2-3% del portafoglio per trade",
                }
        except Exception as tl_err:
            logger.warning("trading_levels_error", error=str(tl_err))

    return {
        "symbol": symbol,
        "asset_type": asset_type,
        "depth": depth,
        "signal": signal_result["signal"],
        "confidence": signal_result["confidence"],
        "composite_score": signal_result["composite_score"],
        "score_0_100": signal_result["score_0_100"],
        "breakdown": breakdowns,
        "risk_flags": risk_flags,
        "trading_levels": trading_levels,
        "extras": extras,
        "source": "Me4BrAIn Multi-Analysis (OpenClaw-inspired)",
    }
