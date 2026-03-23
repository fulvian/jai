"""Finance & Crypto API Tools.

Wrapper async per le API finanziarie:
- CoinGecko: Prezzi crypto, trending
- Yahoo Finance: Quote azioni
- Binance: Candlestick, ticker 24h
- Finnhub: News mercati

Tutte le API sono pubbliche (no auth richiesta).
"""

import os
import re
from datetime import UTC
from pathlib import Path
from typing import Any

import httpx
import structlog
from dotenv import load_dotenv

# Load .env from project root (backend/)
_project_root = Path(__file__).parent.parent.parent
load_dotenv(_project_root / ".env")

logger = structlog.get_logger(__name__)

# Timeout per requests
TIMEOUT = 10.0
USER_AGENT = "Me4BrAIn/2.0 (AI Research Platform; contact@me4brain.ai)"

# EODHD API Key (free tier: 25 calls/day)
EODHD_API_KEY = os.getenv("EODHD_API_KEY", "demo")


def _sanitize_error(error_msg: str) -> str:
    """Rimuove API keys e tokens da messaggi di errore."""
    sanitized = re.sub(
        r"(api_token|api_key|apikey|token|key)=[^&\s\'\"]+",
        r"\1=***REDACTED***",
        str(error_msg),
        flags=re.IGNORECASE,
    )
    # Rimuovi anche URL con token embeddati
    sanitized = re.sub(
        r"https?://[^\s]*api_token=[^\s\'\"]*",
        "[URL REDACTED]",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


# =============================================================================
# CoinGecko (No Auth)
# =============================================================================


async def coingecko_price(
    ids: str | list[str] = "bitcoin,ethereum",
    vs_currencies: str = "usd,eur",
) -> dict[str, Any]:
    """Ottieni prezzi crypto real-time.

    Args:
        ids: Coin IDs separati da virgola (es. "bitcoin,ethereum") o lista ["bitcoin", "ethereum"]
        vs_currencies: Valute target (es. "usd,eur")

    Returns:
        dict con prezzi per ogni coin
    """
    try:
        # Normalize ids to comma-separated string
        if isinstance(ids, list):
            ids_str = ",".join(ids)
        else:
            ids_str = ids

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": ids_str,
                    "vs_currencies": vs_currencies,
                    "include_24hr_change": "true",
                    "include_market_cap": "true",
                },
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            return {
                "prices": data,
                "coins": ids_str.split(","),
                "currencies": vs_currencies.split(","),
                "source": "CoinGecko",
            }

    except Exception as e:
        logger.error("coingecko_price_error", error=str(e))
        return {"error": str(e), "source": "CoinGecko"}


async def coingecko_trending() -> dict[str, Any]:
    """Ottieni crypto trending nelle ultime 24h.

    Returns:
        dict con coins trending
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://api.coingecko.com/api/v3/search/trending",
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            # Format coins
            trending = []
            for item in data.get("coins", []):
                coin = item.get("item", {})
                trending.append(
                    {
                        "id": coin.get("id"),
                        "name": coin.get("name"),
                        "symbol": coin.get("symbol"),
                        "market_cap_rank": coin.get("market_cap_rank"),
                        "price_btc": coin.get("price_btc"),
                    }
                )

            return {
                "coins": trending,  # Add "coins" key for compatibility
                "trending": trending,
                "count": len(trending),
                "source": "CoinGecko",
            }

    except Exception as e:
        logger.error("coingecko_trending_error", error=str(e))
        return {"error": str(e), "source": "CoinGecko"}


# Stock tickers noti che NON sono crypto (evita chiamate CoinGecko inutili)
_KNOWN_STOCK_TICKERS = {
    "HOG",
    "AAPL",
    "TSLA",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "NVDA",
    "AMD",
    "INTC",
    "JPM",
    "BAC",
    "WFC",
    "GS",
    "V",
    "MA",
    "DIS",
    "NFLX",
    "PYPL",
}


async def coingecko_chart(
    coin_id: str = "bitcoin",
    vs_currency: str = "usd",
    days: int = 30,
) -> dict[str, Any]:
    """Ottieni storico prezzi crypto.

    Args:
        coin_id: ID coin CoinGecko (es. "bitcoin", "ethereum")
        vs_currency: Valuta target
        days: Numero giorni storico

    Returns:
        dict con dati storici
    """
    # Validazione: rifiuta stock tickers passati erroneamente
    if coin_id.upper() in _KNOWN_STOCK_TICKERS or (
        len(coin_id) <= 5 and coin_id.upper() == coin_id and coin_id.isalpha()
    ):
        return {
            "error": f"'{coin_id}' sembra un ticker azionario, non un ID CoinGecko. "
            "Usa yahoo_quote o yahooquery_stock_analysis per le azioni.",
            "source": "CoinGecko",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                params={
                    "vs_currency": vs_currency,
                    "days": days,
                },
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            return {
                "coin_id": coin_id,
                "currency": vs_currency,
                "days": days,
                "prices": data.get("prices", [])[-10:],  # Ultimi 10 punti
                "market_caps": data.get("market_caps", [])[-1],
                "volumes": data.get("total_volumes", [])[-1],
                "source": "CoinGecko",
            }

    except Exception as e:
        logger.error("coingecko_chart_error", error=str(e))
        return {"error": _sanitize_error(str(e)), "source": "CoinGecko"}


# =============================================================================
# Binance (No Auth)
# =============================================================================


async def binance_price(symbol: str = "BTCUSDT") -> dict[str, Any]:
    """Ottieni prezzo crypto da Binance.

    Args:
        symbol: Trading pair (es. "BTCUSDT")

    Returns:
        dict con prezzo
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": symbol.upper()},
            )
            response.raise_for_status()
            data = response.json()

            return {
                "symbol": data.get("symbol"),
                "price": float(data.get("price", 0)),
                "source": "Binance",
            }

    except Exception as e:
        logger.error("binance_price_error", error=str(e))
        return {"error": str(e), "source": "Binance"}


async def binance_ticker_24h(symbol: str = "BTCUSDT") -> dict[str, Any]:
    """Ottieni statistiche 24h da Binance.

    Args:
        symbol: Trading pair

    Returns:
        dict con stats 24h
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://api.binance.com/api/v3/ticker/24hr",
                params={"symbol": symbol.upper()},
            )
            response.raise_for_status()
            data = response.json()

            return {
                "symbol": data.get("symbol"),
                "price_change": float(data.get("priceChange", 0)),
                "price_change_percent": float(data.get("priceChangePercent", 0)),
                "high_24h": float(data.get("highPrice", 0)),
                "low_24h": float(data.get("lowPrice", 0)),
                "volume": float(data.get("volume", 0)),  # Add 'volume' key
                "volume_24h": float(data.get("volume", 0)),
                "last_price": float(data.get("lastPrice", 0)),
                "source": "Binance",
            }

    except Exception as e:
        logger.error("binance_ticker_24h_error", error=str(e))
        return {"error": str(e), "source": "Binance"}


async def binance_klines(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    limit: int = 10,
) -> dict[str, Any]:
    """Ottieni candlestick OHLCV da Binance.

    Args:
        symbol: Trading pair (es. "BTCUSDT")
        interval: Intervallo candele: 1m, 5m, 15m, 1h, 4h, 1d, 1w
        limit: Numero candele (max 1000)

    Returns:
        dict con candlestick OHLCV
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://api.binance.com/api/v3/klines",
                params={
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "limit": min(limit, 1000),
                },
            )
            response.raise_for_status()
            data = response.json()

            candles = [
                {
                    "open_time": c[0],
                    "open": float(c[1]),
                    "high": float(c[2]),
                    "low": float(c[3]),
                    "close": float(c[4]),
                    "volume": float(c[5]),
                    "close_time": c[6],
                    "trades": c[8],
                }
                for c in data
            ]

            return {
                "symbol": symbol.upper(),
                "interval": interval,
                "candles": candles,
                "count": len(candles),
                "source": "Binance",
            }

    except Exception as e:
        logger.error("binance_klines_error", error=str(e))
        return {"error": str(e), "source": "Binance"}


async def binance_orderbook(
    symbol: str = "BTCUSDT",
    limit: int = 10,
) -> dict[str, Any]:
    """Ottieni order book depth da Binance.

    Args:
        symbol: Trading pair (es. "BTCUSDT")
        limit: Profondità book (5, 10, 20, 50, 100)

    Returns:
        dict con bids e asks
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://api.binance.com/api/v3/depth",
                params={
                    "symbol": symbol.upper(),
                    "limit": min(limit, 100),
                },
            )
            response.raise_for_status()
            data = response.json()

            bids = [{"price": float(b[0]), "qty": float(b[1])} for b in data.get("bids", [])]
            asks = [{"price": float(a[0]), "qty": float(a[1])} for a in data.get("asks", [])]

            spread = asks[0]["price"] - bids[0]["price"] if bids and asks else 0

            return {
                "symbol": symbol.upper(),
                "bids": bids,
                "asks": asks,
                "best_bid": bids[0]["price"] if bids else None,
                "best_ask": asks[0]["price"] if asks else None,
                "spread": spread,
                "spread_pct": (spread / asks[0]["price"] * 100) if asks and spread else 0,
                "source": "Binance",
            }

    except Exception as e:
        logger.error("binance_orderbook_error", error=str(e))
        return {"error": str(e), "source": "Binance"}


# =============================================================================
# Fear & Greed Index (CNN - No Auth)
# =============================================================================


async def fear_greed_index() -> dict[str, Any]:
    """Ottieni il CNN Fear & Greed Index.

    Returns:
        dict con score, rating e componenti
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            fg_data = data.get("fear_and_greed", {})
            score = fg_data.get("score", 0)

            # Classificazione
            if score <= 25:
                rating = "Extreme Fear"
            elif score <= 45:
                rating = "Fear"
            elif score <= 55:
                rating = "Neutral"
            elif score <= 75:
                rating = "Greed"
            else:
                rating = "Extreme Greed"

            return {
                "score": round(score, 1),
                "rating": rating,
                "previous_close": round(fg_data.get("previous_close", 0), 1),
                "previous_1_week": round(fg_data.get("previous_1_week", 0), 1),
                "previous_1_month": round(fg_data.get("previous_1_month", 0), 1),
                "previous_1_year": round(fg_data.get("previous_1_year", 0), 1),
                "timestamp": fg_data.get("timestamp"),
                "source": "CNN Fear & Greed Index",
            }

    except Exception as e:
        logger.error("fear_greed_error", error=str(e))
        return {"error": str(e), "source": "CNN Fear & Greed Index"}


# =============================================================================
# Market Context Analysis (VIX/SPY/QQQ - No Auth via Yahoo)
# =============================================================================


async def market_context_analysis() -> dict[str, Any]:
    """Analizza contesto mercato: VIX, SPY/QQQ trend, risk-off detection.

    Pattern ispirato da OpenClaw analyze_market_context().

    Returns:
        dict con regime mercato, VIX, trend, safe-haven indicators
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Fetch VIX, SPY, QQQ in parallelo
            import asyncio

            vix_task = client.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX",
                params={"interval": "1d", "range": "1mo"},
                headers={"User-Agent": USER_AGENT},
            )
            spy_task = client.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/SPY",
                params={"interval": "1d", "range": "1mo"},
                headers={"User-Agent": USER_AGENT},
            )
            qqq_task = client.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/QQQ",
                params={"interval": "1d", "range": "1mo"},
                headers={"User-Agent": USER_AGENT},
            )

            vix_resp, spy_resp, qqq_resp = await asyncio.gather(
                vix_task,
                spy_task,
                qqq_task,
            )

            def _extract_price_and_trend(resp: httpx.Response) -> tuple[float, float]:
                data = resp.json()
                result = data.get("chart", {}).get("result", [{}])[0]
                meta = result.get("meta", {})
                closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                current = meta.get("regularMarketPrice", 0)
                # 10-day trend
                valid_closes = [c for c in closes if c is not None]
                if len(valid_closes) >= 10:
                    ten_d_ago = valid_closes[-10]
                    trend = ((current - ten_d_ago) / ten_d_ago) * 100 if ten_d_ago else 0
                else:
                    trend = 0.0
                return current, trend

            vix_price, _ = _extract_price_and_trend(vix_resp)
            spy_price, spy_trend = _extract_price_and_trend(spy_resp)
            qqq_price, qqq_trend = _extract_price_and_trend(qqq_resp)

            # VIX status
            if vix_price < 20:
                vix_status = "calm"
                vix_score = 0.2
            elif vix_price < 30:
                vix_status = "elevated"
                vix_score = 0.0
            else:
                vix_status = "fear"
                vix_score = -0.5

            # Market regime
            avg_trend = (spy_trend + qqq_trend) / 2
            if avg_trend > 3:
                market_regime = "bull"
                regime_score = 0.3
            elif avg_trend < -3:
                market_regime = "bear"
                regime_score = -0.4
            else:
                market_regime = "choppy"
                regime_score = -0.1

            overall_score = (vix_score + regime_score) / 2

            return {
                "vix_level": round(vix_price, 2),
                "vix_status": vix_status,
                "spy_price": round(spy_price, 2),
                "spy_trend_10d": round(spy_trend, 2),
                "qqq_price": round(qqq_price, 2),
                "qqq_trend_10d": round(qqq_trend, 2),
                "market_regime": market_regime,
                "overall_score": round(overall_score, 2),
                "source": "Market Context (Yahoo Finance)",
            }

    except Exception as e:
        logger.error("market_context_error", error=str(e))
        return {"error": str(e), "source": "Market Context"}


# =============================================================================
# Hot Scanner (Ispirato da OpenClaw HotScanner)
# =============================================================================


async def hot_scanner(include_social: bool = True) -> dict[str, Any]:
    """Scansiona mercati per trend virali: crypto trending, stock movers, news.

    Ispirato da OpenClaw HotScanner v2. Fonti:
    - CoinGecko trending crypto
    - Google News RSS finance/crypto
    - Finnhub market news

    Args:
        include_social: Includi fonti social (Reddit-like via news)

    Returns:
        dict con trending crypto, stock news, e summary
    """
    import asyncio

    results: dict[str, Any] = {
        "timestamp": None,
        "crypto_trending": [],
        "market_news": [],
        "summary": "",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            tasks = []

            # 1. CoinGecko trending
            tasks.append(
                client.get(
                    "https://api.coingecko.com/api/v3/search/trending",
                    headers={"accept": "application/json"},
                )
            )

            # 2. Google News RSS Finance
            tasks.append(
                client.get(
                    "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNREpmTjNRU0JXbDBMVWxVR0FBUAE",
                    headers={"User-Agent": USER_AGENT},
                )
            )

            # 3. Finnhub general news
            finnhub_key = os.getenv("FINNHUB_API_KEY")
            if finnhub_key:
                tasks.append(
                    client.get(
                        "https://finnhub.io/api/v1/news",
                        params={"category": "general", "token": finnhub_key},
                    )
                )

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            # Parse CoinGecko trending
            if not isinstance(responses[0], Exception):
                try:
                    cg_data = responses[0].json()
                    for coin in cg_data.get("coins", [])[:10]:
                        item = coin.get("item", {})
                        results["crypto_trending"].append(
                            {
                                "name": item.get("name"),
                                "symbol": item.get("symbol"),
                                "market_cap_rank": item.get("market_cap_rank"),
                                "score": item.get("score"),
                            }
                        )
                except Exception:
                    pass

            # Parse Google News RSS
            if not isinstance(responses[1], Exception):
                try:
                    import xml.etree.ElementTree as ET

                    root = ET.fromstring(responses[1].text)
                    for item in root.findall(".//item")[:8]:
                        title = item.findtext("title", "")
                        link = item.findtext("link", "")
                        pub_date = item.findtext("pubDate", "")
                        results["market_news"].append(
                            {
                                "title": title,
                                "link": link,
                                "published": pub_date,
                                "source": "Google News",
                            }
                        )
                except Exception:
                    pass

            # Parse Finnhub news
            if len(responses) > 2 and not isinstance(responses[2], Exception):
                try:
                    news_data = responses[2].json()
                    for n in news_data[:5]:
                        results["market_news"].append(
                            {
                                "title": n.get("headline", ""),
                                "link": n.get("url", ""),
                                "published": n.get("datetime", ""),
                                "source": n.get("source", "Finnhub"),
                            }
                        )
                except Exception:
                    pass

            # Build summary
            from datetime import datetime

            results["timestamp"] = datetime.now(UTC).isoformat()

            crypto_names = [c["name"] for c in results["crypto_trending"][:5]]
            results["summary"] = (
                f"🔥 Top trending crypto: {', '.join(crypto_names) if crypto_names else 'N/A'}. "
                f"📰 {len(results['market_news'])} notizie di mercato trovate."
            )

            results["source"] = "Hot Scanner (CoinGecko + Google News + Finnhub)"
            return results

    except Exception as e:
        logger.error("hot_scanner_error", error=str(e))
        return {"error": str(e), "source": "Hot Scanner"}


# =============================================================================
# Rumor Scanner (Ispirato da OpenClaw RumorScanner)
# =============================================================================


async def rumor_scanner() -> dict[str, Any]:
    """Scansiona per rumors, segnali precoci, M&A, insider activity.

    Ispirato da OpenClaw RumorScanner. Cerca via Google News RSS
    per keywords: merger, acquisition, insider buying, upgrade, downgrade.

    Returns:
        dict con rumors trovati ordinati per impact score
    """
    import asyncio

    search_queries = [
        "merger+acquisition+stocks",
        "insider+buying+stocks",
        "analyst+upgrade+downgrade",
    ]

    rumors: list[dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            tasks = [
                client.get(
                    f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en",
                    headers={"User-Agent": USER_AGENT},
                )
                for q in search_queries
            ]

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            import xml.etree.ElementTree as ET

            # Impact keywords e scoring (ispirato da OpenClaw calculate_rumor_score)
            impact_keywords = {
                "acquisition": 5,
                "merger": 5,
                "takeover": 5,
                "buyout": 5,
                "insider buying": 4,
                "insider purchase": 4,
                "upgrade": 3,
                "downgrade": 3,
                "price target": 3,
                "fda approval": 4,
                "patent": 3,
                "earnings beat": 3,
                "earnings miss": 3,
                "bankruptcy": 5,
                "delisted": 5,
                "short squeeze": 4,
                "activist investor": 4,
            }

            for i, resp in enumerate(responses):
                if isinstance(resp, Exception):
                    continue
                try:
                    root = ET.fromstring(resp.text)
                    for item in root.findall(".//item")[:5]:
                        title = item.findtext("title", "").lower()
                        pub_date = item.findtext("pubDate", "")

                        # Calculate impact score
                        impact = 1
                        matched_keywords = []
                        for kw, score in impact_keywords.items():
                            if kw in title:
                                impact = max(impact, score)
                                matched_keywords.append(kw)

                        if matched_keywords:
                            # Extract tickers ($AAPL pattern)
                            import re as _re

                            tickers = _re.findall(r"\$([A-Z]{1,5})", item.findtext("title", ""))

                            rumors.append(
                                {
                                    "title": item.findtext("title", ""),
                                    "published": pub_date,
                                    "impact_score": impact,
                                    "keywords": matched_keywords,
                                    "tickers": tickers,
                                    "category": search_queries[i].replace("+", " "),
                                }
                            )
                except Exception:
                    continue

            # Sort by impact
            rumors.sort(key=lambda x: x["impact_score"], reverse=True)

            return {
                "rumors": rumors[:15],
                "count": len(rumors),
                "high_impact": len([r for r in rumors if r["impact_score"] >= 4]),
                "source": "Rumor Scanner (Google News)",
            }

    except Exception as e:
        logger.error("rumor_scanner_error", error=str(e))
        return {"error": str(e), "source": "Rumor Scanner"}


# =============================================================================
# Yahoo Finance (No Auth via yfinance-like scraping)
# =============================================================================


async def yahoo_quote(symbol: str = "AAPL") -> dict[str, Any]:
    """Ottieni quote azione real-time.

    Args:
        symbol: Ticker symbol (es. "AAPL", "TSLA")

    Returns:
        dict con quote
    """
    try:
        # Usa Yahoo Finance API v8 (pubblico)
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "1d"},
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})

            return {
                "symbol": meta.get("symbol"),
                "name": meta.get("shortName"),
                "currency": meta.get("currency"),
                "price": meta.get("regularMarketPrice"),
                "previous_close": meta.get("previousClose"),
                "change": meta.get("regularMarketPrice", 0) - meta.get("previousClose", 0),
                "change_percent": (
                    (meta.get("regularMarketPrice", 0) - meta.get("previousClose", 1))
                    / meta.get("previousClose", 1)
                    * 100
                )
                if meta.get("previousClose")
                else 0,
                "market_state": meta.get("marketState"),
                "source": "Yahoo Finance",
            }

    except Exception as e:
        logger.error("yahoo_quote_error", error=str(e))
        return {"error": _sanitize_error(str(e)), "source": "Yahoo Finance"}


async def yahooquery_stock_analysis(
    symbol: str = "AAPL",
) -> dict[str, Any]:
    """Analisi completa di un titolo azionario con una singola chiamata API.

    Usa yahooquery per ottenere in UNA richiesta: prezzo, fondamentali, KPI,
    target analisti, recommendation trend, e calcola indicatori tecnici
    localmente con pandas-ta.

    Args:
        symbol: Ticker azionario (es. "AAPL", "TSLA", "HOG", "MSFT")

    Returns:
        dict con analisi completa: price, financials, key_stats, recommendation,
        technical_indicators, e trading_levels (stop-loss, take-profit)
    """

    try:
        from yahooquery import Ticker
    except ImportError:
        return {"error": "yahooquery non installato", "symbol": symbol}

    try:
        t = Ticker(symbol)

        # 1 request → tutti i moduli necessari
        modules = t.get_modules(
            [
                "price",
                "financialData",
                "defaultKeyStatistics",
                "summaryDetail",
                "recommendationTrend",
            ]
        )

        if not modules or symbol.lower() not in modules:
            # Prova con uppercase
            sym_key = symbol.upper() if symbol.upper() in modules else symbol.lower()
            if sym_key not in modules:
                return {"error": f"Nessun dato per {symbol}", "symbol": symbol}
        else:
            sym_key = symbol.lower()

        raw = modules[sym_key]
        if isinstance(raw, str):
            return {"error": f"Simbolo non trovato: {raw}", "symbol": symbol}

        # Extract modules
        price_data = raw.get("price", {})
        financial = raw.get("financialData", {})
        key_stats = raw.get("defaultKeyStatistics", {})
        summary = raw.get("summaryDetail", {})
        rec_trend = raw.get("recommendationTrend", {})

        # 📊 Prezzo e Mercato
        current_price = price_data.get("regularMarketPrice", 0)
        result: dict[str, Any] = {
            "symbol": symbol.upper(),
            "name": price_data.get("longName") or price_data.get("shortName", symbol),
            "source": "yahooquery",
            # 📊 Price & Market
            "price": {
                "current": current_price,
                "previous_close": price_data.get("regularMarketPreviousClose"),
                "day_high": price_data.get("regularMarketDayHigh"),
                "day_low": price_data.get("regularMarketDayLow"),
                "change_pct": round(
                    (price_data.get("regularMarketChangePercent", 0) or 0) * 100, 2
                ),
                "market_cap": price_data.get("marketCap"),
                "currency": price_data.get("currency", "USD"),
                "market_state": price_data.get("marketState"),
            },
            # 📋 Fondamentali
            "fundamentals": {
                "pe_trailing": key_stats.get("trailingEps"),
                "pe_forward": key_stats.get("forwardPE"),
                "peg_ratio": key_stats.get("pegRatio"),
                "price_to_book": key_stats.get("priceToBook"),
                "enterprise_value": key_stats.get("enterpriseValue"),
                "ev_to_ebitda": key_stats.get("enterpriseToEbitda"),
                "ev_to_revenue": key_stats.get("enterpriseToRevenue"),
                "beta": key_stats.get("beta"),
                "52w_high": summary.get("fiftyTwoWeekHigh"),
                "52w_low": summary.get("fiftyTwoWeekLow"),
                "50d_avg": summary.get("fiftyDayAverage"),
                "200d_avg": summary.get("twoHundredDayAverage"),
                "dividend_yield": summary.get("dividendYield"),
            },
            # 💰 Financial KPIs
            "financial_kpis": {
                "revenue_growth": financial.get("revenueGrowth"),
                "earnings_growth": financial.get("earningsGrowth"),
                "profit_margins": financial.get("profitMargins"),
                "operating_margins": financial.get("operatingMargins"),
                "gross_margins": financial.get("grossMargins"),
                "return_on_equity": financial.get("returnOnEquity"),
                "return_on_assets": financial.get("returnOnAssets"),
                "debt_to_equity": financial.get("debtToEquity"),
                "current_ratio": financial.get("currentRatio"),
                "free_cash_flow": financial.get("freeCashflow"),
                "target_mean_price": financial.get("targetMeanPrice"),
                "target_high": financial.get("targetHighPrice"),
                "target_low": financial.get("targetLowPrice"),
                "recommendation": financial.get("recommendationKey"),
                "analyst_count": financial.get("numberOfAnalystOpinions"),
            },
        }

        # 📈 Recommendation Trend
        if rec_trend and isinstance(rec_trend, dict):
            trend_data = rec_trend.get("trend", [])
            if trend_data and isinstance(trend_data, list):
                current_trend = trend_data[0] if trend_data else {}
                result["recommendation_trend"] = {
                    "period": current_trend.get("period"),
                    "strong_buy": current_trend.get("strongBuy", 0),
                    "buy": current_trend.get("buy", 0),
                    "hold": current_trend.get("hold", 0),
                    "sell": current_trend.get("sell", 0),
                    "strong_sell": current_trend.get("strongSell", 0),
                }

        # 📈 Technical Indicators (locali con pandas-ta)
        try:
            import pandas_ta as ta_lib

            df = await _fetch_ohlc_yahooquery(symbol)
            if df is not None and not df.empty and len(df) >= 26:
                tech = {}
                # RSI
                rsi = ta_lib.rsi(df["close"], length=14)
                if rsi is not None and not rsi.dropna().empty:
                    tech["rsi_14"] = round(float(rsi.dropna().iloc[-1]), 2)

                # MACD
                macd_df = ta_lib.macd(df["close"])
                if macd_df is not None and not macd_df.dropna().empty:
                    latest_macd = macd_df.dropna().iloc[-1]
                    tech["macd"] = round(float(latest_macd.iloc[0]), 4)
                    tech["macd_signal"] = round(float(latest_macd.iloc[1]), 4)

                # ATR (per stop-loss)
                atr = ta_lib.atr(df["high"], df["low"], df["close"], length=14)
                if atr is not None and not atr.dropna().empty:
                    atr_val = round(float(atr.dropna().iloc[-1]), 4)
                    tech["atr_14"] = atr_val

                    # 🎯 Trading Levels
                    if current_price and current_price > 0:
                        result["trading_levels"] = {
                            "entry_price": current_price,
                            "stop_loss": round(current_price - (2.0 * atr_val), 2),
                            "take_profit_1": round(current_price + (1.5 * atr_val), 2),
                            "take_profit_2": round(current_price + (3.0 * atr_val), 2),
                            "take_profit_3": round(current_price + (4.5 * atr_val), 2),
                            "risk_reward_ratio": "1:0.75 / 1:1.5 / 1:2.25",
                            "position_sizing": "Max 2-3% del portafoglio per trade",
                        }

                # SMA 20/50/200
                for sma_len in [20, 50, 200]:
                    sma = ta_lib.sma(df["close"], length=sma_len)
                    if sma is not None and not sma.dropna().empty:
                        tech[f"sma_{sma_len}"] = round(float(sma.dropna().iloc[-1]), 2)

                # BBands
                bb = ta_lib.bbands(df["close"], length=20)
                if bb is not None and not bb.dropna().empty:
                    bb_latest = bb.dropna().iloc[-1]
                    # pandas-ta BBands order: BBL(0), BBM(1), BBU(2)
                    tech["bb_lower"] = round(float(bb_latest.iloc[0]), 2)
                    tech["bb_middle"] = round(float(bb_latest.iloc[1]), 2)
                    tech["bb_upper"] = round(float(bb_latest.iloc[2]), 2)

                result["technical_indicators"] = tech
        except Exception as tech_err:
            logger.warning("yahooquery_tech_indicators_error", error=str(tech_err))

        return result

    except Exception as e:
        logger.error("yahooquery_stock_analysis_error", error=str(e), symbol=symbol)
        return {"error": _sanitize_error(str(e)), "symbol": symbol}


# =============================================================================
# Finnhub (Requires API Key)
# =============================================================================


async def finnhub_news(category: str = "general") -> dict[str, Any]:
    """Ottieni news mercati finanziari.

    Args:
        category: Categoria news (general, forex, crypto, merger)

    Returns:
        dict con news
    """
    api_key = os.getenv("FINNHUB_API_KEY")

    if not api_key:
        # Fallback: usa RSS feed generico
        return {
            "error": "FINNHUB_API_KEY not configured",
            "hint": "Set FINNHUB_API_KEY in .env for market news",
            "source": "Finnhub",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://finnhub.io/api/v1/news",
                params={"category": category, "token": api_key},
            )
            response.raise_for_status()
            data = response.json()

            # Format news
            news = []
            for item in data[:10]:  # Top 10
                news.append(
                    {
                        "headline": item.get("headline"),
                        "summary": item.get("summary", "")[:200],
                        "source": item.get("source"),
                        "datetime": item.get("datetime"),
                        "url": item.get("url"),
                    }
                )

            return {
                "category": category,
                "news": news,
                "count": len(news),
                "source": "Finnhub",
            }

    except Exception as e:
        logger.error("finnhub_news_error", error=str(e))
        return {"error": str(e), "source": "Finnhub"}


async def finnhub_quote(symbol: str = "AAPL") -> dict[str, Any]:
    """Ottieni quote da Finnhub.

    Args:
        symbol: Ticker symbol

    Returns:
        dict con quote
    """
    api_key = os.getenv("FINNHUB_API_KEY")

    if not api_key:
        return {
            "error": "FINNHUB_API_KEY not configured",
            "source": "Finnhub",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": symbol.upper(), "token": api_key},
            )
            response.raise_for_status()
            data = response.json()

            return {
                "symbol": symbol.upper(),
                "current": data.get("c"),
                "change": data.get("d"),
                "change_percent": data.get("dp"),
                "high": data.get("h"),
                "low": data.get("l"),
                "open": data.get("o"),
                "previous_close": data.get("pc"),
                "source": "Finnhub",
            }

    except Exception as e:
        logger.error("finnhub_quote_error", error=str(e))
        return {"error": str(e), "source": "Finnhub"}


# =============================================================================
# FRED - Federal Reserve Economic Data
# =============================================================================


async def fred_series(
    series_id: str = "GDP",
    limit: int = 10,
) -> dict[str, Any]:
    """Ottieni serie economica FRED.

    Args:
        series_id: ID serie (es. "GDP", "UNRATE", "CPIAUCSL")
        limit: Numero di osservazioni

    Returns:
        dict con dati serie
    """
    api_key = os.getenv("FRED_API_KEY")

    if not api_key:
        return {
            "error": "FRED_API_KEY not configured",
            "source": "FRED",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": limit,
                },
            )
            response.raise_for_status()
            data = response.json()

            observations = data.get("observations", [])

            return {
                "series_id": series_id,
                "observations": [
                    {
                        "date": obs.get("date"),
                        "value": float(obs.get("value")) if obs.get("value") != "." else None,
                    }
                    for obs in observations
                ],
                "count": len(observations),
                "source": "FRED",
            }

    except Exception as e:
        logger.error("fred_series_error", error=str(e))
        return {"error": str(e), "source": "FRED"}


async def fred_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Cerca serie FRED.

    Args:
        query: Termine di ricerca
        limit: Numero risultati

    Returns:
        dict con serie trovate
    """
    api_key = os.getenv("FRED_API_KEY")

    if not api_key:
        return {"error": "FRED_API_KEY not configured", "source": "FRED"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://api.stlouisfed.org/fred/series/search",
                params={
                    "search_text": query,
                    "api_key": api_key,
                    "file_type": "json",
                    "limit": limit,
                },
            )
            response.raise_for_status()
            data = response.json()

            series = [
                {
                    "id": s.get("id"),
                    "title": s.get("title"),
                    "frequency": s.get("frequency"),
                    "units": s.get("units"),
                }
                for s in data.get("seriess", [])
            ]

            return {
                "query": query,
                "series": series,
                "count": len(series),
                "source": "FRED",
            }

    except Exception as e:
        logger.error("fred_search_error", error=str(e))
        return {"error": str(e), "source": "FRED"}


# =============================================================================
# NASDAQ Data API
# =============================================================================


async def nasdaq_quote(symbol: str = "AAPL") -> dict[str, Any]:
    """Ottieni quote da NASDAQ Data API.

    Args:
        symbol: Ticker symbol

    Returns:
        dict con quote
    """
    api_key = os.getenv("NASDAQ_DATA_API_KEY")

    if not api_key:
        return {"error": "NASDAQ_DATA_API_KEY not configured", "source": "NASDAQ Data"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"https://data.nasdaq.com/api/v3/datasets/WIKI/{symbol}/data.json",
                params={"api_key": api_key, "rows": 1},
            )
            response.raise_for_status()
            data = response.json()

            dataset = data.get("dataset_data", {})
            columns = dataset.get("column_names", [])
            values = dataset.get("data", [[]])[0] if dataset.get("data") else []

            # Map columns to values
            quote_data = dict(zip(columns, values)) if columns and values else {}

            return {
                "symbol": symbol,
                "date": quote_data.get("Date"),
                "open": quote_data.get("Open"),
                "high": quote_data.get("High"),
                "low": quote_data.get("Low"),
                "close": quote_data.get("Close"),
                "volume": quote_data.get("Volume"),
                "source": "NASDAQ Data",
            }

    except Exception as e:
        logger.error("nasdaq_quote_error", error=str(e))
        return {"error": str(e), "source": "NASDAQ Data"}


# =============================================================================
# Yahoo Finance Fundamentals (via yfinance - free, universal coverage)
# =============================================================================


async def _yahoo_financials(
    symbol: str,
    statement_type: str,
    limit: int = 4,
) -> dict[str, Any] | None:
    """Fetch financial data via yfinance (handles crumb auth automatically).

    Uses asyncio.to_thread since yfinance is synchronous.

    Args:
        symbol: Ticker symbol (e.g., "AAPL", "HOG")
        statement_type: One of 'balance_sheet', 'income_stmt', 'cash_flow',
                       'key_metrics', 'ratios', 'dcf'
        limit: Max periods to return

    Returns:
        dict with parsed data, or None if it fails.
    """
    import asyncio

    try:

        def _fetch() -> dict[str, Any] | None:
            import yfinance as yf

            ticker = yf.Ticker(symbol)

            if statement_type == "balance_sheet":
                df = ticker.balance_sheet
                if df is None or df.empty:
                    return None
                statements = []
                for col in df.columns[:limit]:
                    s = df[col]
                    total_current_assets = s.get("Current Assets", 0) or 0
                    total_current_liab = s.get("Current Liabilities", 0) or 0
                    statements.append(
                        {
                            "date": col.strftime("%Y-%m-%d"),
                            "total_assets": s.get("Total Assets"),
                            "total_liabilities": s.get("Total Liabilities Net Minority Interest"),
                            "total_equity": s.get("Stockholders Equity"),
                            "cash": s.get("Cash And Cash Equivalents"),
                            "total_debt": s.get("Total Debt"),
                            "net_debt": s.get("Net Debt"),
                            "current_ratio": (
                                round(total_current_assets / total_current_liab, 2)
                                if total_current_liab
                                else None
                            ),
                        }
                    )
                return {
                    "symbol": symbol.upper(),
                    "period": "annual",
                    "statements": statements,
                    "count": len(statements),
                    "source": "Yahoo Finance",
                }

            elif statement_type == "income_stmt":
                df = ticker.income_stmt
                if df is None or df.empty:
                    return None
                statements = []
                for col in df.columns[:limit]:
                    s = df[col]
                    revenue = s.get("Total Revenue", 0) or 0
                    gross = s.get("Gross Profit", 0) or 0
                    op_inc = s.get("Operating Income", 0) or 0
                    net_inc = s.get("Net Income", 0) or 0
                    statements.append(
                        {
                            "date": col.strftime("%Y-%m-%d"),
                            "revenue": revenue,
                            "gross_profit": gross,
                            "operating_income": op_inc,
                            "net_income": net_inc,
                            "eps": s.get("Basic EPS"),
                            "eps_diluted": s.get("Diluted EPS"),
                            "gross_margin": round((gross / revenue) * 100, 2) if revenue else 0,
                            "operating_margin": round((op_inc / revenue) * 100, 2)
                            if revenue
                            else 0,
                            "net_margin": round((net_inc / revenue) * 100, 2) if revenue else 0,
                        }
                    )
                return {
                    "symbol": symbol.upper(),
                    "period": "annual",
                    "statements": statements,
                    "count": len(statements),
                    "source": "Yahoo Finance",
                }

            elif statement_type == "cash_flow":
                df = ticker.cashflow
                if df is None or df.empty:
                    return None
                statements = []
                for col in df.columns[:limit]:
                    s = df[col]
                    statements.append(
                        {
                            "date": col.strftime("%Y-%m-%d"),
                            "operating_cf": s.get("Operating Cash Flow"),
                            "investing_cf": s.get("Investing Cash Flow"),
                            "financing_cf": s.get("Financing Cash Flow"),
                            "free_cash_flow": s.get("Free Cash Flow"),
                            "capex": s.get("Capital Expenditure"),
                            "dividends_paid": s.get("Cash Dividends Paid"),
                            "stock_repurchase": s.get("Repurchase Of Capital Stock"),
                        }
                    )
                return {
                    "symbol": symbol.upper(),
                    "period": "annual",
                    "statements": statements,
                    "count": len(statements),
                    "source": "Yahoo Finance",
                }

            elif statement_type == "key_metrics":
                info = ticker.info
                if not info or not info.get("shortName"):
                    return None
                return {
                    "symbol": symbol.upper(),
                    "market_cap": info.get("marketCap"),
                    "enterprise_value": info.get("enterpriseValue"),
                    "ev_to_ebitda": _safe_round(info.get("enterpriseToEbitda"), 2),
                    "ev_to_sales": _safe_round(info.get("enterpriseToRevenue"), 2),
                    "roe": _safe_round(_safe_pct(info.get("returnOnEquity")), 2),
                    "roa": _safe_round(_safe_pct(info.get("returnOnAssets")), 2),
                    "roic": None,  # yfinance doesn't have ROIC directly
                    "earnings_yield": _safe_round(
                        (1 / info["trailingPE"]) * 100 if info.get("trailingPE") else None, 2
                    ),
                    "fcf_yield": _safe_round(
                        (info.get("freeCashflow", 0) / info.get("marketCap", 1)) * 100
                        if info.get("marketCap")
                        else None,
                        2,
                    ),
                    "current_ratio": _safe_round(info.get("currentRatio"), 2),
                    "graham_number": None,  # Not available in yfinance
                    "source": "Yahoo Finance",
                }

            elif statement_type == "ratios":
                info = ticker.info
                if not info or not info.get("shortName"):
                    return None
                return {
                    "symbol": symbol.upper(),
                    "gross_margin": _safe_round(_safe_pct(info.get("grossMargins")), 2),
                    "operating_margin": _safe_round(_safe_pct(info.get("operatingMargins")), 2),
                    "net_margin": _safe_round(_safe_pct(info.get("profitMargins")), 2),
                    "pe_ratio": _safe_round(info.get("trailingPE"), 2),
                    "peg_ratio": _safe_round(info.get("pegRatio"), 2),
                    "price_to_book": _safe_round(info.get("priceToBook"), 2),
                    "price_to_sales": _safe_round(info.get("priceToSalesTrailing12Months"), 2),
                    "dividend_yield": _safe_round(_safe_pct(info.get("dividendYield")), 2),
                    "payout_ratio": _safe_round(_safe_pct(info.get("payoutRatio")), 2),
                    "debt_to_equity": _safe_round(info.get("debtToEquity"), 2),
                    "debt_to_assets": None,  # Not directly in yfinance .info
                    "interest_coverage": None,  # Not directly in yfinance .info
                    "source": "Yahoo Finance",
                }

            elif statement_type == "dcf":
                info = ticker.info
                if not info or not info.get("shortName"):
                    return None
                # Yahoo doesn't provide DCF directly — estimate from analyst target
                target_price = info.get("targetMeanPrice")
                stock_price = info.get("currentPrice") or info.get("regularMarketPrice", 0)

                if target_price and stock_price:
                    premium_pct = ((stock_price - target_price) / target_price) * 100
                    valuation = "sovrapprezzato" if premium_pct > 0 else "sottopprezzato"
                else:
                    premium_pct = 0
                    valuation = "n/a"

                return {
                    "symbol": symbol.upper(),
                    "fair_value_dcf": round(target_price, 2) if target_price else None,
                    "stock_price": round(stock_price, 2) if stock_price else None,
                    "premium_discount_pct": round(premium_pct, 2),
                    "valuation": valuation,
                    "date": None,
                    "note": "Fair value based on analyst consensus target price (not DCF model)",
                    "source": "Yahoo Finance",
                }

            return None

        return await asyncio.to_thread(_fetch)

    except Exception as e:
        logger.warning("yahoo_financials_error", error=str(e), symbol=symbol, type=statement_type)
        return None


def _safe_round(value: float | None, decimals: int = 2) -> float | None:
    """Safely round a value, returning None if value is None."""
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


def _safe_pct(value: float | None) -> float | None:
    """Convert a ratio (0.14) to percentage (14.0), safely."""
    if value is None:
        return None
    try:
        return float(value) * 100
    except (TypeError, ValueError):
        return None


# =============================================================================
# Smart Wrapper Functions: Yahoo Finance → FMP Fallback
# =============================================================================


async def stock_key_metrics(symbol: str = "AAPL") -> dict[str, Any]:
    """Ottieni metriche chiave fondamentali (P/E, ROE, EV/EBITDA, etc).

    Uses Yahoo Finance as primary source, FMP as fallback.

    Args:
        symbol: Ticker symbol (es. "AAPL", "TSLA", "HOG")

    Returns:
        dict con metriche fondamentali TTM
    """
    # 1. Try Yahoo Finance (free, universal)
    yahoo_result = await _yahoo_financials(symbol, "key_metrics")
    if yahoo_result and "error" not in yahoo_result:
        return yahoo_result

    # 2. Fallback: FMP
    return await fmp_key_metrics(symbol)


async def stock_ratios(symbol: str = "AAPL") -> dict[str, Any]:
    """Ottieni rapporti finanziari (margini, liquidity, efficiency).

    Uses Yahoo Finance as primary source, FMP as fallback.

    Args:
        symbol: Ticker symbol

    Returns:
        dict con ratios TTM
    """
    yahoo_result = await _yahoo_financials(symbol, "ratios")
    if yahoo_result and "error" not in yahoo_result:
        return yahoo_result

    return await fmp_ratios(symbol)


async def stock_dcf(symbol: str = "AAPL") -> dict[str, Any]:
    """Ottieni fair value / valutazione intrinseca del titolo.

    Uses Yahoo Finance analyst targets as primary, FMP DCF model as fallback.

    Args:
        symbol: Ticker symbol

    Returns:
        dict con fair value e confronto con prezzo attuale
    """
    yahoo_result = await _yahoo_financials(symbol, "dcf")
    if yahoo_result and "error" not in yahoo_result:
        return yahoo_result

    return await fmp_dcf(symbol)


async def stock_income_statement(
    symbol: str = "AAPL",
    period: str = "annual",
    limit: int = 4,
) -> dict[str, Any]:
    """Ottieni Income Statement completo (revenue, profit, margini, EPS).

    Uses Yahoo Finance as primary source, FMP as fallback.

    Args:
        symbol: Ticker (es. "AAPL")
        period: "annual" o "quarter"
        limit: Numero periodi (max 10)

    Returns:
        dict con voci income statement
    """
    yahoo_result = await _yahoo_financials(symbol, "income_stmt", limit)
    if yahoo_result and "error" not in yahoo_result:
        return yahoo_result

    return await fmp_income_statement(symbol, period, limit)


async def stock_balance_sheet(
    symbol: str = "AAPL",
    period: str = "annual",
    limit: int = 4,
) -> dict[str, Any]:
    """Ottieni Balance Sheet completo (assets, liabilities, equity, cash, debt).

    Uses Yahoo Finance as primary source, FMP as fallback.

    Args:
        symbol: Ticker
        period: "annual" o "quarter"
        limit: Numero periodi

    Returns:
        dict con voci balance sheet
    """
    yahoo_result = await _yahoo_financials(symbol, "balance_sheet", limit)
    if yahoo_result and "error" not in yahoo_result:
        return yahoo_result

    return await fmp_balance_sheet(symbol, period, limit)


async def stock_cash_flow(
    symbol: str = "AAPL",
    period: str = "annual",
    limit: int = 4,
) -> dict[str, Any]:
    """Ottieni Cash Flow Statement (operating, investing, financing, FCF, CapEx).

    Uses Yahoo Finance as primary source, FMP as fallback.

    Args:
        symbol: Ticker
        period: "annual" o "quarter"
        limit: Numero periodi

    Returns:
        dict con voci cash flow
    """
    yahoo_result = await _yahoo_financials(symbol, "cash_flow", limit)
    if yahoo_result and "error" not in yahoo_result:
        return yahoo_result

    return await fmp_cash_flow(symbol, period, limit)


# =============================================================================
# Financial Modeling Prep (FMP) - Fundamental Data (fallback source)
# =============================================================================


async def fmp_key_metrics(symbol: str = "AAPL") -> dict[str, Any]:
    """Ottieni metriche chiave fondamentali (P/E, ROE, EV/EBITDA, etc).

    Args:
        symbol: Ticker symbol (es. "AAPL", "TSLA")

    Returns:
        dict con metriche fondamentali TTM
    """
    api_key = os.getenv("FMP_API_KEY")

    if not api_key:
        return {"error": "FMP_API_KEY not configured", "source": "FMP"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://financialmodelingprep.com/stable/key-metrics-ttm",
                params={"symbol": symbol, "apikey": api_key},
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list) and data:
                metrics = data[0]
                return {
                    "symbol": symbol,
                    "market_cap": metrics.get("marketCap"),
                    "enterprise_value": metrics.get("enterpriseValueTTM"),
                    "ev_to_ebitda": round(metrics.get("evToEBITDATTM", 0), 2),
                    "ev_to_sales": round(metrics.get("evToSalesTTM", 0), 2),
                    "roe": round(metrics.get("returnOnEquityTTM", 0) * 100, 2),
                    "roa": round(metrics.get("returnOnAssetsTTM", 0) * 100, 2),
                    "roic": round(metrics.get("returnOnInvestedCapitalTTM", 0) * 100, 2),
                    "earnings_yield": round(metrics.get("earningsYieldTTM", 0) * 100, 2),
                    "fcf_yield": round(metrics.get("freeCashFlowYieldTTM", 0) * 100, 2),
                    "current_ratio": round(metrics.get("currentRatioTTM", 0), 2),
                    "graham_number": round(metrics.get("grahamNumberTTM", 0), 2),
                    "source": "Financial Modeling Prep",
                }
            else:
                return {"error": f"No data found for {symbol}", "source": "FMP"}

    except Exception as e:
        logger.error("fmp_key_metrics_error", error=str(e), symbol=symbol)
        return {"error": str(e), "symbol": symbol, "source": "FMP"}


async def fmp_ratios(symbol: str = "AAPL") -> dict[str, Any]:
    """Ottieni rapporti finanziari (margini, liquidity, efficiency).

    Args:
        symbol: Ticker symbol

    Returns:
        dict con ratios TTM
    """
    api_key = os.getenv("FMP_API_KEY")

    if not api_key:
        return {"error": "FMP_API_KEY not configured", "source": "FMP"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://financialmodelingprep.com/stable/ratios-ttm",
                params={"symbol": symbol, "apikey": api_key},
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list) and data:
                ratios = data[0]
                return {
                    "symbol": symbol,
                    # Profitability
                    "gross_margin": round(ratios.get("grossProfitMarginTTM", 0) * 100, 2),
                    "operating_margin": round(ratios.get("operatingProfitMarginTTM", 0) * 100, 2),
                    "net_margin": round(ratios.get("netProfitMarginTTM", 0) * 100, 2),
                    # Valuation
                    "pe_ratio": round(ratios.get("peRatioTTM", 0), 2),
                    "peg_ratio": round(ratios.get("pegRatioTTM", 0), 2),
                    "price_to_book": round(ratios.get("priceToBookRatioTTM", 0), 2),
                    "price_to_sales": round(ratios.get("priceToSalesRatioTTM", 0), 2),
                    # Dividends
                    "dividend_yield": round(ratios.get("dividendYieldTTM", 0) * 100, 2),
                    "payout_ratio": round(ratios.get("payoutRatioTTM", 0) * 100, 2),
                    # Debt
                    "debt_to_equity": round(ratios.get("debtEquityRatioTTM", 0), 2),
                    "debt_to_assets": round(ratios.get("debtRatioTTM", 0), 2),
                    "interest_coverage": round(ratios.get("interestCoverageTTM", 0), 2),
                    "source": "Financial Modeling Prep",
                }
            else:
                return {"error": f"No data found for {symbol}", "source": "FMP"}

    except Exception as e:
        logger.error("fmp_ratios_error", error=str(e), symbol=symbol)
        return {"error": str(e), "symbol": symbol, "source": "FMP"}


async def fmp_dcf(symbol: str = "AAPL") -> dict[str, Any]:
    """Ottieni fair value DCF (Discounted Cash Flow) calcolato.

    Args:
        symbol: Ticker symbol

    Returns:
        dict con DCF fair value e confronto con prezzo attuale
    """
    api_key = os.getenv("FMP_API_KEY")

    if not api_key:
        return {"error": "FMP_API_KEY not configured", "source": "FMP"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://financialmodelingprep.com/stable/discounted-cash-flow",
                params={"symbol": symbol, "apikey": api_key},
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list) and data:
                dcf = data[0]
                fair_value = dcf.get("dcf", 0)
                stock_price = dcf.get("Stock Price", 0)

                # Calcola sovrapprezzo/sottopprezzo
                if fair_value and stock_price:
                    premium_pct = ((stock_price - fair_value) / fair_value) * 100
                    valuation = "sovrapprezzato" if premium_pct > 0 else "sottopprezzato"
                else:
                    premium_pct = 0
                    valuation = "n/a"

                return {
                    "symbol": symbol,
                    "fair_value_dcf": round(fair_value, 2),
                    "stock_price": round(stock_price, 2),
                    "premium_discount_pct": round(premium_pct, 2),
                    "valuation": valuation,
                    "date": dcf.get("date"),
                    "source": "Financial Modeling Prep",
                }
            else:
                return {"error": f"No DCF data for {symbol}", "source": "FMP"}

    except Exception as e:
        logger.error("fmp_dcf_error", error=str(e), symbol=symbol)
        return {"error": str(e), "symbol": symbol, "source": "FMP"}


# =============================================================================
# Technical Indicators (Alpha Vantage + EODHD + pandas-ta)
# =============================================================================

INDICATOR_TYPES = [
    "rsi",
    "macd",
    "bbands",
    "stoch",
    "adx",
    "atr",
    "obv",
    "cci",
    "willr",
    "sma",
    "ema",
    "ichimoku",
    "sar",
]

# ── Asset-Aware Indicator Profiles ──────────────────────────────────────────
# Parametri ottimali per asset class. Crypto usa periodi più corti per via
# del trading 24/7 e maggiore volatilità.
INDICATOR_PROFILES: dict[str, dict[str, dict]] = {
    "stock": {
        "rsi": {"length": 14},
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "bbands": {"length": 20, "std": 2.0},
        "adx": {"length": 14},
        "atr": {"length": 14},
        "stoch": {"k": 14, "d": 3},
        "ichimoku": {"tenkan": 9, "kijun": 26, "senkou": 52},
        "sma": {},  # usa period dall'utente
        "ema": {},
        "sar": {"af0": 0.02, "af": 0.2},
        "cci": {"length": 20},
        "willr": {"length": 14},
        "obv": {},
    },
    "crypto": {
        "rsi": {"length": 10},
        "macd": {"fast": 5, "slow": 35, "signal": 5},
        "bbands": {"length": 12, "std": 2.5},
        "adx": {"length": 14},
        "atr": {"length": 14},
        "stoch": {"k": 5, "d": 3},
        "ichimoku": {"tenkan": 20, "kijun": 60, "senkou": 120},
        "sma": {},
        "ema": {},
        "sar": {"af0": 0.015, "af": 0.15},
        "cci": {"length": 14},
        "willr": {"length": 10},
        "obv": {},
    },
}

_CRYPTO_SUFFIXES = {
    "USDT",
    "BUSD",
    "USDC",
    "USD",
    "BTC",
    "ETH",
    "BNB",
}
_KNOWN_CRYPTO_BASES = {
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "ADA",
    "DOT",
    "AVAX",
    "LINK",
    "MATIC",
    "DOGE",
    "SHIB",
    "UNI",
    "AAVE",
    "LTC",
    "ATOM",
    "NEAR",
    "FTM",
    "ARB",
    "OP",
    "APT",
    "SUI",
    "INJ",
    "TIA",
    "SEI",
    "PEPE",
    "WIF",
    "BONK",
    "BITCOIN",
    "ETHEREUM",
    "SOLANA",
    "RIPPLE",
    "CARDANO",
    "POLKADOT",
}


def _detect_asset_type_simple(symbol: str) -> str:
    """Identifica se un simbolo è stock/etf o crypto.

    Returns:
        'crypto' o 'stock' (include anche etf).
    """
    upper = symbol.upper().replace("-", "").replace("/", "")

    # Suffissi crypto (es. BTCUSDT, ETH-USD)
    for suffix in _CRYPTO_SUFFIXES:
        if upper.endswith(suffix) and len(upper) > len(suffix):
            return "crypto"

    # Base ticker note
    base = symbol.upper().split("-")[0].split("/")[0]
    if base in _KNOWN_CRYPTO_BASES:
        return "crypto"

    return "stock"


async def _fetch_ohlc_yahooquery(symbol: str, period: str = "6mo") -> "pd.DataFrame | None":
    """Fetch OHLC data da Yahoo Finance via yahooquery (primary, no API key).

    Vantaggio: 1 sola chiamata API, nessuna API key necessaria.
    """
    import pandas as pd

    try:
        from yahooquery import Ticker

        t = Ticker(symbol)
        df = t.history(period=period, interval="1d")

        if isinstance(df, pd.DataFrame) and not df.empty:
            # yahooquery restituisce MultiIndex (symbol, date)
            if isinstance(df.index, pd.MultiIndex):
                df = df.droplevel(0)
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
            # Normalizza colonne
            col_map = {c: c.lower() for c in df.columns}
            df = df.rename(columns=col_map)
            # Assicura colonne necessarie
            required = {"open", "high", "low", "close", "volume"}
            if required.issubset(set(df.columns)):
                return df[list(required)].astype(float)
        return None

    except Exception as e:
        logger.warning("yahooquery_ohlc_error", error=str(e), symbol=symbol)
        return None


async def _calculate_pandas_ta_indicator(
    symbol: str,
    indicator: str,
    period: int,
    asset_type: str | None = None,
) -> dict[str, Any]:
    """Calcola indicatore tecnico localmente con pandas-ta da dati OHLC.

    Strategia OHLC: yahooquery → yfinance → None (fallback ad API esterne).
    Usa INDICATOR_PROFILES per parametri asset-aware (stock vs crypto).
    """
    try:
        import pandas_ta as ta
    except ImportError:
        return {"error": "pandas-ta non installato", "symbol": symbol}

    # Resolve asset-type e profilo parametri
    if asset_type is None:
        asset_type = _detect_asset_type_simple(symbol)
    profile = INDICATOR_PROFILES.get(asset_type, INDICATOR_PROFILES["stock"])
    ind_params = profile.get(indicator, {})

    # Fetch OHLC data (yahooquery primary, yfinance fallback)
    ohlc_period = "1y" if asset_type == "crypto" else "6mo"
    df = await _fetch_ohlc_yahooquery(symbol, period=ohlc_period)
    source = "yahooquery + pandas-ta"

    if df is None or df.empty:
        # Fallback a yfinance (già presente nel progetto)
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            df = ticker.history(period=ohlc_period, interval="1d")
            if df is not None and not df.empty:
                col_map = {c: c.lower() for c in df.columns}
                df = df.rename(columns=col_map)
                source = "yfinance + pandas-ta"
            else:
                return {"error": f"No OHLC data per {symbol}", "symbol": symbol}
        except Exception:
            return {"error": f"No OHLC data per {symbol}", "symbol": symbol}

    # Per Ichimoku crypto servono almeno 120 data points
    min_len = max(period, ind_params.get("senkou", ind_params.get("slow", 26)))
    if len(df) < min_len:
        return {
            "error": f"Dati insufficienti ({len(df)} giorni, servono {min_len}) per {indicator}",
            "symbol": symbol,
        }

    result: dict[str, Any] = {
        "symbol": symbol,
        "indicator": indicator.upper(),
        "asset_type": asset_type,
        "date": str(df.index[-1].date()) if hasattr(df.index[-1], "date") else str(df.index[-1]),
        "source": source,
    }

    try:
        # Risolvi lunghezza: profilo > user period > default
        p_len = ind_params.get("length", period)

        if indicator == "rsi":
            rsi_series = ta.rsi(df["close"], length=p_len)
            if rsi_series is not None and not rsi_series.dropna().empty:
                rsi_val = round(float(rsi_series.dropna().iloc[-1]), 2)
                result["value"] = rsi_val
                result["rsi"] = rsi_val
                result["interpretation"] = _interpret_rsi(rsi_val)
            else:
                return {"error": f"RSI non calcolabile per {symbol}", "symbol": symbol}

        elif indicator == "macd":
            macd_df = ta.macd(
                df["close"],
                fast=ind_params.get("fast", 12),
                slow=ind_params.get("slow", 26),
                signal=ind_params.get("signal", 9),
            )
            if macd_df is not None and not macd_df.dropna().empty:
                latest = macd_df.dropna().iloc[-1]
                result["macd"] = round(float(latest.iloc[0]), 4)
                result["signal"] = round(float(latest.iloc[1]), 4)
                result["histogram"] = round(float(latest.iloc[2]), 4)
                result["interpretation"] = _interpret_macd(result["macd"], result["signal"])
            else:
                return {"error": f"MACD non calcolabile per {symbol}", "symbol": symbol}

        elif indicator == "bbands":
            bb = ta.bbands(df["close"], length=p_len, std=ind_params.get("std", 2.0))
            if bb is not None and not bb.dropna().empty:
                latest = bb.dropna().iloc[-1]
                # pandas-ta BBands order: BBL(0), BBM(1), BBU(2), BBB(3), BBP(4)
                result["lower"] = round(float(latest.iloc[0]), 4)
                result["middle"] = round(float(latest.iloc[1]), 4)
                result["upper"] = round(float(latest.iloc[2]), 4)
                current = float(df["close"].iloc[-1])
                if current > float(latest.iloc[2]):
                    result["interpretation"] = (
                        "Prezzo sopra banda superiore - possibile ipercomprato"
                    )
                elif current < float(latest.iloc[0]):
                    result["interpretation"] = (
                        "Prezzo sotto banda inferiore - possibile ipervenduto"
                    )
                else:
                    result["interpretation"] = "Prezzo nella banda - range normale"
            else:
                return {"error": f"BBands non calcolabili per {symbol}", "symbol": symbol}

        elif indicator == "adx":
            adx_df = ta.adx(df["high"], df["low"], df["close"], length=p_len)
            if adx_df is not None and not adx_df.dropna().empty:
                latest = adx_df.dropna().iloc[-1]
                adx_val = round(float(latest.iloc[0]), 2)
                result["value"] = adx_val
                result["adx"] = adx_val
                if adx_val > 25:
                    result["interpretation"] = f"Trend forte (ADX: {adx_val})"
                else:
                    result["interpretation"] = f"Trend debole (ADX: {adx_val})"
            else:
                return {"error": f"ADX non calcolabile per {symbol}", "symbol": symbol}

        elif indicator == "atr":
            atr_series = ta.atr(df["high"], df["low"], df["close"], length=p_len)
            if atr_series is not None and not atr_series.dropna().empty:
                atr_val = round(float(atr_series.dropna().iloc[-1]), 4)
                result["value"] = atr_val
                result["atr"] = atr_val
                result["interpretation"] = f"Volatilità media su {period} periodi: {atr_val}"
            else:
                return {"error": f"ATR non calcolabile per {symbol}", "symbol": symbol}

        elif indicator == "stoch":
            stoch_df = ta.stoch(
                df["high"],
                df["low"],
                df["close"],
                k=ind_params.get("k", 14),
                d=ind_params.get("d", 3),
            )
            if stoch_df is not None and not stoch_df.dropna().empty:
                latest = stoch_df.dropna().iloc[-1]
                result["k"] = round(float(latest.iloc[0]), 2)
                result["d"] = round(float(latest.iloc[1]), 2)
                result["value"] = result["k"]
            else:
                return {"error": f"Stoch non calcolabile per {symbol}", "symbol": symbol}

        elif indicator == "obv":
            obv_series = ta.obv(df["close"], df["volume"])
            if obv_series is not None and not obv_series.dropna().empty:
                result["value"] = round(float(obv_series.dropna().iloc[-1]), 0)
            else:
                return {"error": f"OBV non calcolabile per {symbol}", "symbol": symbol}

        elif indicator == "cci":
            cci_series = ta.cci(df["high"], df["low"], df["close"], length=p_len)
            if cci_series is not None and not cci_series.dropna().empty:
                result["value"] = round(float(cci_series.dropna().iloc[-1]), 2)
            else:
                return {"error": f"CCI non calcolabile per {symbol}", "symbol": symbol}

        elif indicator == "willr":
            willr_series = ta.willr(df["high"], df["low"], df["close"], length=p_len)
            if willr_series is not None and not willr_series.dropna().empty:
                result["value"] = round(float(willr_series.dropna().iloc[-1]), 2)
            else:
                return {"error": f"Williams %R non calcolabile per {symbol}", "symbol": symbol}

        elif indicator == "sma":
            sma_series = ta.sma(df["close"], length=period)
            if sma_series is not None and not sma_series.dropna().empty:
                result["value"] = round(float(sma_series.dropna().iloc[-1]), 4)
            else:
                return {"error": f"SMA non calcolabile per {symbol}", "symbol": symbol}

        elif indicator == "ema":
            ema_series = ta.ema(df["close"], length=period)
            if ema_series is not None and not ema_series.dropna().empty:
                result["value"] = round(float(ema_series.dropna().iloc[-1]), 4)
            else:
                return {"error": f"EMA non calcolabile per {symbol}", "symbol": symbol}

        elif indicator == "ichimoku":
            ichi = ta.ichimoku(
                df["high"],
                df["low"],
                df["close"],
                tenkan=ind_params.get("tenkan", 9),
                kijun=ind_params.get("kijun", 26),
                senkou=ind_params.get("senkou", 52),
            )
            if ichi is not None and ichi[0] is not None and not ichi[0].dropna().empty:
                ichi_df = ichi[0]
                latest = ichi_df.dropna().iloc[-1]
                # Colonne pandas-ta: ISA_9, ISB_26, ITS_9, IKS_26, ICS_26
                col_map = {c: c for c in ichi_df.columns}
                isa = [c for c in col_map if c.startswith("ISA")]
                isb = [c for c in col_map if c.startswith("ISB")]
                its = [c for c in col_map if c.startswith("ITS")]
                iks = [c for c in col_map if c.startswith("IKS")]

                result["tenkan_sen"] = round(float(latest[its[0]]), 4) if its else None
                result["kijun_sen"] = round(float(latest[iks[0]]), 4) if iks else None
                result["senkou_span_a"] = round(float(latest[isa[0]]), 4) if isa else None
                result["senkou_span_b"] = round(float(latest[isb[0]]), 4) if isb else None

                current_price = float(df["close"].iloc[-1])
                result["interpretation"] = _interpret_ichimoku(current_price, result)
            else:
                return {"error": f"Ichimoku non calcolabile per {symbol}", "symbol": symbol}

        elif indicator == "sar":
            sar_df = ta.psar(
                df["high"],
                df["low"],
                df["close"],
                af0=ind_params.get("af0", 0.02),
                af=ind_params.get("af", 0.2),
            )
            if sar_df is not None and not sar_df.empty:
                latest = sar_df.iloc[-1]
                # PSARl = long (bullish), PSARs = short (bearish) — mutually exclusive
                psar_long_cols = [c for c in sar_df.columns if c.startswith("PSARl")]
                psar_short_cols = [c for c in sar_df.columns if c.startswith("PSARs")]

                psar_long = float(latest[psar_long_cols[0]]) if psar_long_cols else float("nan")
                psar_short = float(latest[psar_short_cols[0]]) if psar_short_cols else float("nan")

                import math

                current_price = float(df["close"].iloc[-1])
                if not math.isnan(psar_long):
                    result["value"] = round(psar_long, 4)
                    result["trend"] = "bullish"
                    result["interpretation"] = f"SAR bullish a ${psar_long:.2f} — trend rialzista"
                elif not math.isnan(psar_short):
                    result["value"] = round(psar_short, 4)
                    result["trend"] = "bearish"
                    result["interpretation"] = f"SAR bearish a ${psar_short:.2f} — trend ribassista"
                else:
                    result["value"] = None
                    result["interpretation"] = "SAR non determinabile"
            else:
                return {"error": f"SAR non calcolabile per {symbol}", "symbol": symbol}

        else:
            return {
                "error": f"Indicatore {indicator} non supportato via pandas-ta",
                "symbol": symbol,
            }

        return result

    except Exception as e:
        logger.warning("pandas_ta_calc_error", error=str(e), symbol=symbol, indicator=indicator)
        return {"error": f"Errore calcolo locale {indicator}: {str(e)}", "symbol": symbol}


async def technical_indicators(
    symbol: str = "AAPL",
    indicator: str = "rsi",
    period: int = 14,
) -> dict[str, Any]:
    """Ottieni indicatori tecnici per analisi trading.

    Args:
        symbol: Ticker symbol (es. "AAPL", "TSLA", "MSFT")
        indicator: Tipo indicatore:
            - rsi: Relative Strength Index (momentum)
            - macd: Moving Average Convergence Divergence
            - bbands: Bollinger Bands (volatilità)
            - stoch: Stochastic Oscillator
            - adx: Average Directional Index (trend strength)
            - atr: Average True Range (volatilità)
            - obv: On Balance Volume
            - cci: Commodity Channel Index
            - willr: Williams %R
            - sma: Simple Moving Average
            - ema: Exponential Moving Average
            - ichimoku: Ichimoku Cloud (richiede calcolo custom)
            - sar: Parabolic SAR (richiede calcolo custom)
        period: Periodo per il calcolo (default 14)

    Returns:
        dict con valore indicatore e interpretazione
    """
    indicator = indicator.lower()

    if indicator not in INDICATOR_TYPES:
        return {
            "error": f"Indicatore '{indicator}' non supportato",
            "supported": INDICATOR_TYPES,
        }

    # Auto-detect asset type per parametri ottimali
    asset_type = _detect_asset_type_simple(symbol)

    # STRATEGIA: pandas-ta locale (da yahooquery/yfinance OHLC) → Alpha Vantage → EODHD
    # Tutti gli indicatori (inclusi Ichimoku e SAR) sono calcolati via pandas-ta
    result = await _calculate_pandas_ta_indicator(symbol, indicator, period, asset_type=asset_type)
    if not result.get("error"):
        return result

    # Fallback 1: Alpha Vantage API
    result = await _fetch_alpha_vantage_indicator(symbol, indicator, period)
    if not result.get("error"):
        return result

    # Fallback 2: EODHD (ultimo resort, rate limited)
    result = await _fetch_eodhd_indicator(symbol, indicator, period)
    return result


async def _fetch_alpha_vantage_indicator(
    symbol: str, indicator: str, period: int
) -> dict[str, Any]:
    """Fetch indicatore da Alpha Vantage API."""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")

    if not api_key:
        return {"error": "ALPHA_VANTAGE_API_KEY not configured"}

    # Mappa indicatori a funzioni Alpha Vantage
    av_functions = {
        "rsi": "RSI",
        "macd": "MACD",
        "bbands": "BBANDS",
        "stoch": "STOCH",
        "adx": "ADX",
        "atr": "ATR",
        "obv": "OBV",
        "cci": "CCI",
        "willr": "WILLR",
        "sma": "SMA",
        "ema": "EMA",
    }

    function = av_functions.get(indicator)
    if not function:
        return {"error": f"Indicatore {indicator} non mappato su Alpha Vantage"}

    try:
        params = {
            "function": function,
            "symbol": symbol,
            "interval": "daily",
            "apikey": api_key,
        }

        # Aggiungi parametri specifici per indicatore
        if indicator in ["rsi", "adx", "atr", "cci", "willr", "sma", "ema"]:
            params["time_period"] = period
        if indicator in ["rsi", "sma", "ema", "bbands"]:
            params["series_type"] = "close"

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://www.alphavantage.co/query",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        # Controlla errori API
        if "Error Message" in data or "Information" in data:
            return {"error": data.get("Error Message") or data.get("Information")}

        # Estrai dati più recenti
        return _parse_alpha_vantage_response(data, indicator, symbol)

    except Exception as e:
        logger.error("alpha_vantage_indicator_error", error=str(e), symbol=symbol)
        return {"error": str(e), "symbol": symbol}


def _parse_alpha_vantage_response(data: dict, indicator: str, symbol: str) -> dict[str, Any]:
    """Parse risposta Alpha Vantage e aggiungi interpretazione."""
    # Trova la chiave dei dati tecnici
    ta_key = None
    for key in data:
        if "Technical Analysis" in key:
            ta_key = key
            break

    if not ta_key or not data.get(ta_key):
        return {"error": "No technical data found", "symbol": symbol}

    ta_data = data[ta_key]
    latest_date = list(ta_data.keys())[0]
    latest_values = ta_data[latest_date]

    result = {
        "symbol": symbol,
        "indicator": indicator.upper(),
        "date": latest_date,
        "source": "Alpha Vantage",
    }

    # Parse valori specifici per indicatore
    if indicator == "rsi":
        rsi_val = float(latest_values.get("RSI", 0))
        result["value"] = round(rsi_val, 2)
        result["interpretation"] = _interpret_rsi(rsi_val)
    elif indicator == "macd":
        result["macd"] = round(float(latest_values.get("MACD", 0)), 4)
        result["signal"] = round(float(latest_values.get("MACD_Signal", 0)), 4)
        result["histogram"] = round(float(latest_values.get("MACD_Hist", 0)), 4)
        result["interpretation"] = _interpret_macd(result["macd"], result["signal"])
    elif indicator == "bbands":
        result["upper"] = round(float(latest_values.get("Real Upper Band", 0)), 2)
        result["middle"] = round(float(latest_values.get("Real Middle Band", 0)), 2)
        result["lower"] = round(float(latest_values.get("Real Lower Band", 0)), 2)
    elif indicator == "stoch":
        slowk = float(latest_values.get("SlowK", 0))
        slowd = float(latest_values.get("SlowD", 0))
        result["slowK"] = round(slowk, 2)
        result["slowD"] = round(slowd, 2)
        result["interpretation"] = _interpret_stochastic(slowk, slowd)
    elif indicator == "adx":
        adx_val = float(latest_values.get("ADX", 0))
        result["value"] = round(adx_val, 2)
        result["interpretation"] = _interpret_adx(adx_val)
    elif indicator in ["atr", "obv", "cci", "willr", "sma", "ema"]:
        key = indicator.upper() if indicator != "willr" else "WILLR"
        result["value"] = round(float(latest_values.get(key, 0)), 4)

    return result


async def _fetch_eodhd_indicator(symbol: str, indicator: str, period: int) -> dict[str, Any]:
    """Fetch indicatore da EODHD API (fallback)."""
    eodhd_map = {
        "rsi": "rsi",
        "macd": "macd",
        "bbands": "bbands",
        "stoch": "stoch",
        "adx": "adx",
        "atr": "atr",
        "obv": "obv",
        "cci": "cci",
        "willr": "wpr",
        "sma": "sma",
        "ema": "ema",
    }

    function = eodhd_map.get(indicator)
    if not function:
        return {"error": f"Indicatore {indicator} non disponibile su EODHD"}

    try:
        # EODHD usa formato SYMBOL.EXCHANGE
        eodhd_symbol = f"{symbol}.US"

        params = {
            "function": function,
            "period": period,
            "api_token": EODHD_API_KEY,
            "fmt": "json",
        }

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"https://eodhd.com/api/technical/{eodhd_symbol}",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        if not data or (isinstance(data, list) and len(data) == 0):
            return {"error": f"No data from EODHD for {symbol}"}

        # Prendi ultimo valore
        latest = data[-1] if isinstance(data, list) else data

        result = {
            "symbol": symbol,
            "indicator": indicator.upper(),
            "date": latest.get("date"),
            "source": "EODHD",
        }

        # Estrai valore principale
        if indicator == "rsi":
            rsi_val = float(latest.get("rsi", 0))
            result["value"] = round(rsi_val, 2)
            result["interpretation"] = _interpret_rsi(rsi_val)
        elif indicator == "macd":
            result["macd"] = round(float(latest.get("macd", 0)), 4)
            result["signal"] = round(float(latest.get("signal", 0)), 4)
            result["histogram"] = round(float(latest.get("divergence", 0)), 4)
        else:
            # Generico
            for k, v in latest.items():
                if k != "date" and isinstance(v, (int, float)):
                    result["value"] = round(float(v), 4)
                    break

        return result

    except Exception as e:
        logger.error("eodhd_indicator_error", error=_sanitize_error(str(e)), symbol=symbol)
        return {"error": _sanitize_error(str(e)), "symbol": symbol}


async def _calculate_custom_indicator(symbol: str, indicator: str) -> dict[str, Any]:
    """Calcola Ichimoku e SAR usando pandas-ta da dati OHLC."""
    import pandas as pd

    try:
        import pandas_ta as ta
    except ImportError:
        return {"error": "pandas-ta non installato", "symbol": symbol}

    # Prova Alpha Vantage, poi fallback a EODHD
    df = await _fetch_ohlc_alpha_vantage(symbol)
    source = "Alpha Vantage + pandas-ta"

    if df is None or df.empty:
        df = await _fetch_ohlc_eodhd(symbol)
        source = "EODHD + pandas-ta"

    if df is None or df.empty:
        return {"error": "No OHLC data available from any source", "symbol": symbol}

    result = {
        "symbol": symbol,
        "indicator": indicator.upper(),
        "date": str(df.index[-1].date()),
        "source": source,
    }

    try:
        if indicator == "ichimoku":
            ichimoku_df = ta.ichimoku(df["high"], df["low"], df["close"])[0]
            latest = ichimoku_df.iloc[-1]
            result["tenkan_sen"] = round(latest.get("ITS_9", 0), 2)
            result["kijun_sen"] = round(latest.get("IKS_26", 0), 2)
            result["senkou_span_a"] = round(latest.get("ISA_9", 0), 2)
            result["senkou_span_b"] = round(latest.get("ISB_26", 0), 2)
            result["interpretation"] = _interpret_ichimoku(df["close"].iloc[-1], result)
        elif indicator == "sar":
            sar_series = ta.psar(df["high"], df["low"], df["close"])
            latest_sar = sar_series.iloc[-1]
            current_price = df["close"].iloc[-1]

            psar_long = latest_sar.get("PSARl_0.02_0.2")
            psar_short = latest_sar.get("PSARs_0.02_0.2")

            if pd.notna(psar_long):
                result["sar_value"] = round(psar_long, 2)
                result["trend"] = "bullish"
                result["interpretation"] = "Trend rialzista - SAR sotto il prezzo"
            elif pd.notna(psar_short):
                result["sar_value"] = round(psar_short, 2)
                result["trend"] = "bearish"
                result["interpretation"] = "Trend ribassista - SAR sopra il prezzo"
            else:
                result["sar_value"] = None
                result["trend"] = "undefined"

            result["current_price"] = round(current_price, 2)

        return result

    except Exception as e:
        logger.error("custom_indicator_calc_error", error=str(e), symbol=symbol)
        return {"error": str(e), "symbol": symbol}


async def _fetch_ohlc_alpha_vantage(symbol: str):
    """Fetch OHLC data da Alpha Vantage."""
    import pandas as pd

    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "TIME_SERIES_DAILY",
                    "symbol": symbol,
                    "outputsize": "compact",
                    "apikey": api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

        if "Time Series (Daily)" not in data:
            return None

        ts_data = data["Time Series (Daily)"]
        df = pd.DataFrame.from_dict(ts_data, orient="index")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df.rename(
            columns={
                "1. open": "open",
                "2. high": "high",
                "3. low": "low",
                "4. close": "close",
                "5. volume": "volume",
            }
        )
        return df.astype(float)

    except Exception as e:
        logger.warning("alpha_vantage_ohlc_error", error=str(e), symbol=symbol)
        return None


async def _fetch_ohlc_eodhd(symbol: str):
    """Fetch OHLC data da EODHD (fallback)."""
    import pandas as pd

    try:
        eodhd_symbol = f"{symbol}.US"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"https://eodhd.com/api/eod/{eodhd_symbol}",
                params={"api_token": EODHD_API_KEY, "fmt": "json", "period": "d"},
            )
            response.raise_for_status()
            data = response.json()

        if not data or len(data) < 26:  # Ichimoku needs at least 26 days
            return None

        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df.rename(
            columns={
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
        )
        return df[["open", "high", "low", "close", "volume"]].astype(float)

    except Exception as e:
        logger.warning("eodhd_ohlc_error", error=str(e), symbol=symbol)
        return None


def _interpret_rsi(value: float) -> str:
    """Interpreta valore RSI."""
    if value >= 70:
        return "Ipercomprato (overbought) - possibile correzione"
    elif value <= 30:
        return "Ipervenduto (oversold) - possibile rimbalzo"
    elif value >= 60:
        return "Zona alta - momentum positivo"
    elif value <= 40:
        return "Zona bassa - momentum negativo"
    else:
        return "Zona neutra"


def _interpret_macd(macd: float, signal: float) -> str:
    """Interpreta MACD."""
    if macd > signal:
        return "Bullish - MACD sopra signal line"
    elif macd < signal:
        return "Bearish - MACD sotto signal line"
    else:
        return "Neutro - crossover imminente"


def _interpret_stochastic(k: float, d: float) -> str:
    """Interpreta Stochastic."""
    if k > 80 and d > 80:
        return "Ipercomprato"
    elif k < 20 and d < 20:
        return "Ipervenduto"
    elif k > d:
        return "Bullish crossover"
    else:
        return "Bearish crossover"


def _interpret_adx(value: float) -> str:
    """Interpreta ADX (trend strength)."""
    if value >= 50:
        return "Trend molto forte"
    elif value >= 25:
        return "Trend forte"
    elif value >= 20:
        return "Trend debole"
    else:
        return "Assenza di trend (sideways)"


def _interpret_ichimoku(current_price: float, ichimoku: dict) -> str:
    """Interpreta Ichimoku Cloud."""
    span_a = ichimoku.get("senkou_span_a", 0)
    span_b = ichimoku.get("senkou_span_b", 0)
    cloud_top = max(span_a, span_b)
    cloud_bottom = min(span_a, span_b)

    if current_price > cloud_top:
        return "Bullish - Prezzo sopra la nuvola"
    elif current_price < cloud_bottom:
        return "Bearish - Prezzo sotto la nuvola"
    else:
        return "Neutro - Prezzo dentro la nuvola"


# =============================================================================

# SEC EDGAR - Company Filings
# =============================================================================


async def edgar_filings(
    ticker: str = "AAPL",
    form_type: str = "10-K",
    limit: int = 5,
) -> dict[str, Any]:
    """Ottieni filings SEC EDGAR.

    Args:
        ticker: Ticker symbol
        form_type: Tipo form (10-K, 10-Q, 8-K)
        limit: Numero filings

    Returns:
        dict con filings
    """
    # UNIVERSAL TICKER VALIDATION
    # US stock tickers: 1-5 uppercase letters, optionally with . for classes (BRK.A)
    ticker_pattern = r"^[A-Z]{1,5}(\.[A-Z])?$"
    normalized_ticker = ticker.upper().strip()

    if not re.match(ticker_pattern, normalized_ticker):
        logger.warning(
            "edgar_invalid_ticker",
            original=ticker,
            normalized=normalized_ticker,
            reason="Not a valid US stock ticker format",
        )
        return {
            "error": f"Invalid ticker format: '{ticker}'. Expected 1-5 uppercase letters (e.g., AAPL, MSFT, BRK.A)",
            "ticker": ticker,
            "source": "SEC EDGAR",
        }

    try:
        # SEC EDGAR è gratuito, non richiede API key
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Step 1: Get CIK from ticker
            response = await client.get(
                "https://www.sec.gov/cgi-bin/browse-edgar",
                params={
                    "action": "getcompany",
                    "CIK": normalized_ticker,
                    "type": form_type,
                    "dateb": "",
                    "owner": "include",
                    "count": limit,
                    "output": "atom",
                },
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()

            # UNIVERSAL XML VALIDATION - Check response is XML before parsing
            content_type = response.headers.get("content-type", "")
            response_text = response.text

            if "xml" not in content_type.lower() and not response_text.strip().startswith("<?xml"):
                logger.warning(
                    "edgar_non_xml_response",
                    ticker=normalized_ticker,
                    content_type=content_type,
                    body_preview=response_text[:200],
                )
                return {
                    "error": f"SEC EDGAR returned non-XML response for ticker '{normalized_ticker}'. Company may not exist.",
                    "ticker": normalized_ticker,
                    "source": "SEC EDGAR",
                }

            # Parse XML response
            import xml.etree.ElementTree as ET

            try:
                root = ET.fromstring(response_text)
            except ET.ParseError as xml_err:
                logger.error(
                    "edgar_xml_parse_error",
                    ticker=normalized_ticker,
                    error=str(xml_err),
                    body_preview=response_text[:200],
                )
                return {
                    "error": f"XML parse error: {xml_err}. Ticker '{normalized_ticker}' may not exist in SEC database.",
                    "ticker": normalized_ticker,
                    "source": "SEC EDGAR",
                }

            ns = {"atom": "http://www.w3.org/2005/Atom"}

            filings = []
            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                link = entry.find("atom:link", ns)
                updated = entry.find("atom:updated", ns)

                if title is not None:
                    filings.append(
                        {
                            "title": title.text,
                            "link": link.get("href") if link is not None else None,
                            "date": updated.text if updated is not None else None,
                        }
                    )

            return {
                "ticker": normalized_ticker,
                "form_type": form_type,
                "filings": filings[:limit],
                "count": len(filings),
                "source": "SEC EDGAR",
            }

    except Exception as e:
        logger.error("edgar_filings_error", error=str(e), ticker=normalized_ticker)
        return {"error": str(e), "ticker": normalized_ticker, "source": "SEC EDGAR"}


async def edgar_company_info(ticker: str = "AAPL") -> dict[str, Any]:
    """Ottieni info azienda da SEC EDGAR.

    Args:
        ticker: Ticker symbol

    Returns:
        dict con info azienda
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Get company tickers mapping
            response = await client.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers={"User-Agent": USER_AGENT},
            )
            response.raise_for_status()
            data = response.json()

            # Find company by ticker
            for entry in data.values():
                if entry.get("ticker", "").upper() == ticker.upper():
                    cik = str(entry.get("cik_str", "")).zfill(10)
                    return {
                        "ticker": ticker,
                        "cik": cik,
                        "name": entry.get("title"),
                        "edgar_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}",
                        "source": "SEC EDGAR",
                    }

            return {
                "error": f"Company not found: {ticker}",
                "source": "SEC EDGAR",
            }

    except Exception as e:
        logger.error("edgar_company_info_error", error=str(e))
        return {"error": str(e), "source": "SEC EDGAR"}


# =============================================================================
# Alpaca Paper Trading
# =============================================================================


async def alpaca_account() -> dict[str, Any]:
    """Ottieni info account Alpaca Paper Trading.

    Returns:
        dict con info account (equity, cash, buying_power)
    """
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    endpoint = os.getenv("ALPACA_ENDPOINT", "https://paper-api.alpaca.markets/v2")

    if not api_key or not secret_key:
        return {
            "error": "ALPACA_API_KEY or ALPACA_SECRET_KEY not configured",
            "source": "Alpaca",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{endpoint}/account",
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": secret_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            return {
                "account_number": data.get("account_number"),
                "status": data.get("status"),
                "equity": float(data.get("equity", 0)),
                "cash": float(data.get("cash", 0)),
                "buying_power": float(data.get("buying_power", 0)),
                "portfolio_value": float(data.get("portfolio_value", 0)),
                "pattern_day_trader": data.get("pattern_day_trader"),
                "source": "Alpaca Paper",
            }

    except Exception as e:
        logger.error("alpaca_account_error", error=str(e))
        return {"error": str(e), "source": "Alpaca"}


async def alpaca_positions() -> dict[str, Any]:
    """Ottieni posizioni aperte Alpaca.

    Returns:
        dict con lista posizioni
    """
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    endpoint = os.getenv("ALPACA_ENDPOINT", "https://paper-api.alpaca.markets/v2")

    if not api_key or not secret_key:
        return {
            "error": "ALPACA_API_KEY or ALPACA_SECRET_KEY not configured",
            "source": "Alpaca",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{endpoint}/positions",
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": secret_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            positions = [
                {
                    "symbol": p.get("symbol"),
                    "qty": float(p.get("qty", 0)),
                    "market_value": float(p.get("market_value", 0)),
                    "avg_entry_price": float(p.get("avg_entry_price", 0)),
                    "current_price": float(p.get("current_price", 0)),
                    "unrealized_pl": float(p.get("unrealized_pl", 0)),
                    "unrealized_plpc": float(p.get("unrealized_plpc", 0)) * 100,
                }
                for p in data
            ]

            return {
                "positions": positions,
                "count": len(positions),
                "source": "Alpaca Paper",
            }

    except Exception as e:
        logger.error("alpaca_positions_error", error=str(e))
        return {"error": str(e), "source": "Alpaca"}


async def alpaca_quote(symbol: str = "AAPL") -> dict[str, Any]:
    """Ottieni quote real-time da Alpaca.

    Args:
        symbol: Ticker symbol

    Returns:
        dict con quote
    """
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        return {
            "error": "ALPACA_API_KEY or ALPACA_SECRET_KEY not configured",
            "source": "Alpaca",
        }

    try:
        # Use data API for quotes
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"https://data.alpaca.markets/v2/stocks/{symbol}/quotes/latest",
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": secret_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            quote = data.get("quote", {})

            return {
                "symbol": symbol,
                "ask_price": float(quote.get("ap", 0)),
                "ask_size": quote.get("as"),
                "bid_price": float(quote.get("bp", 0)),
                "bid_size": quote.get("bs"),
                "timestamp": quote.get("t"),
                "source": "Alpaca",
            }

    except Exception as e:
        logger.error("alpaca_quote_error", error=str(e))
        return {"error": str(e), "source": "Alpaca"}


async def alpaca_bars(
    symbol: str = "AAPL",
    timeframe: str = "1Day",
    limit: int = 10,
) -> dict[str, Any]:
    """Ottieni OHLCV bars da Alpaca.

    Args:
        symbol: Ticker symbol
        timeframe: 1Min, 5Min, 15Min, 1Hour, 1Day
        limit: Numero barre

    Returns:
        dict con OHLCV bars
    """
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key or not secret_key:
        return {
            "error": "ALPACA_API_KEY or ALPACA_SECRET_KEY not configured",
            "source": "Alpaca",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"https://data.alpaca.markets/v2/stocks/{symbol}/bars",
                params={"timeframe": timeframe, "limit": limit},
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": secret_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            bars = [
                {
                    "timestamp": b.get("t"),
                    "open": float(b.get("o", 0)),
                    "high": float(b.get("h", 0)),
                    "low": float(b.get("l", 0)),
                    "close": float(b.get("c", 0)),
                    "volume": b.get("v"),
                }
                for b in data.get("bars", [])
            ]

            return {
                "symbol": symbol,
                "timeframe": timeframe,
                "bars": bars,
                "count": len(bars),
                "source": "Alpaca",
            }

    except Exception as e:
        logger.error("alpaca_bars_error", error=str(e))
        return {"error": str(e), "source": "Alpaca"}


async def alpaca_place_order(
    symbol: str = "AAPL",
    qty: float = 1,
    side: str = "buy",
    order_type: str = "market",
    limit_price: float | None = None,
    stop_price: float | None = None,
    time_in_force: str = "day",
) -> dict[str, Any]:
    """Invia ordine su Alpaca Paper Trading.

    SOLO PAPER TRADING (sandbox). Non opera mai su mercato reale.

    Args:
        symbol: Ticker (es. "AAPL")
        qty: Quantità azioni
        side: "buy" o "sell"
        order_type: "market", "limit", "stop", "stop_limit"
        limit_price: Prezzo limite (per limit/stop_limit)
        stop_price: Prezzo stop (per stop/stop_limit)
        time_in_force: "day", "gtc", "ioc", "fok"

    Returns:
        dict con dettagli ordine
    """
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    # FORCE paper endpoint - mai usare live
    endpoint = "https://paper-api.alpaca.markets/v2"

    if not api_key or not secret_key:
        return {
            "error": "ALPACA_API_KEY or ALPACA_SECRET_KEY not configured",
            "source": "Alpaca Paper",
        }

    try:
        order_data: dict[str, Any] = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side.lower(),
            "type": order_type.lower(),
            "time_in_force": time_in_force.lower(),
        }

        if limit_price and order_type in ("limit", "stop_limit"):
            order_data["limit_price"] = str(limit_price)
        if stop_price and order_type in ("stop", "stop_limit"):
            order_data["stop_price"] = str(stop_price)

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{endpoint}/orders",
                json=order_data,
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": secret_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            return {
                "order_id": data.get("id"),
                "symbol": data.get("symbol"),
                "qty": data.get("qty"),
                "side": data.get("side"),
                "type": data.get("type"),
                "status": data.get("status"),
                "filled_qty": data.get("filled_qty"),
                "filled_avg_price": data.get("filled_avg_price"),
                "created_at": data.get("created_at"),
                "time_in_force": data.get("time_in_force"),
                "paper_trading": True,
                "source": "Alpaca Paper",
            }

    except httpx.HTTPStatusError as e:
        error_body = e.response.text if e.response else str(e)
        logger.error("alpaca_place_order_error", error=error_body)
        return {"error": f"Order rejected: {error_body}", "source": "Alpaca Paper"}
    except Exception as e:
        logger.error("alpaca_place_order_error", error=str(e))
        return {"error": str(e), "source": "Alpaca Paper"}


async def alpaca_order_history(
    status: str = "all",
    limit: int = 10,
) -> dict[str, Any]:
    """Ottieni storico ordini Alpaca Paper Trading.

    Args:
        status: "open", "closed", "all"
        limit: Numero ordini

    Returns:
        dict con lista ordini
    """
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    endpoint = "https://paper-api.alpaca.markets/v2"

    if not api_key or not secret_key:
        return {
            "error": "ALPACA_API_KEY or ALPACA_SECRET_KEY not configured",
            "source": "Alpaca Paper",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{endpoint}/orders",
                params={"status": status, "limit": limit},
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": secret_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            orders = [
                {
                    "order_id": o.get("id"),
                    "symbol": o.get("symbol"),
                    "qty": o.get("qty"),
                    "side": o.get("side"),
                    "type": o.get("type"),
                    "status": o.get("status"),
                    "filled_qty": o.get("filled_qty"),
                    "filled_avg_price": o.get("filled_avg_price"),
                    "created_at": o.get("created_at"),
                }
                for o in data
            ]

            return {
                "orders": orders,
                "count": len(orders),
                "source": "Alpaca Paper",
            }

    except Exception as e:
        logger.error("alpaca_order_history_error", error=str(e))
        return {"error": str(e), "source": "Alpaca Paper"}


async def alpaca_cancel_order(order_id: str) -> dict[str, Any]:
    """Cancella un ordine su Alpaca Paper Trading.

    Args:
        order_id: ID dell'ordine da cancellare

    Returns:
        dict con stato cancellazione
    """
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    endpoint = "https://paper-api.alpaca.markets/v2"

    if not api_key or not secret_key:
        return {
            "error": "ALPACA_API_KEY or ALPACA_SECRET_KEY not configured",
            "source": "Alpaca Paper",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.delete(
                f"{endpoint}/orders/{order_id}",
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": secret_key,
                },
            )

            if response.status_code == 204:
                return {
                    "order_id": order_id,
                    "status": "cancelled",
                    "source": "Alpaca Paper",
                }
            else:
                return {
                    "order_id": order_id,
                    "status": "cancel_failed",
                    "detail": response.text,
                    "source": "Alpaca Paper",
                }

    except Exception as e:
        logger.error("alpaca_cancel_order_error", error=str(e))
        return {"error": str(e), "source": "Alpaca Paper"}


async def alpaca_portfolio_history(
    period: str = "1M",
    timeframe: str = "1D",
) -> dict[str, Any]:
    """Ottieni storico performance portfolio Alpaca.

    Args:
        period: "1D", "1W", "1M", "3M", "1A", "all"
        timeframe: "1Min", "5Min", "15Min", "1H", "1D"

    Returns:
        dict con equity history
    """
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    endpoint = "https://paper-api.alpaca.markets/v2"

    if not api_key or not secret_key:
        return {
            "error": "ALPACA_API_KEY or ALPACA_SECRET_KEY not configured",
            "source": "Alpaca Paper",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                f"{endpoint}/account/portfolio/history",
                params={"period": period, "timeframe": timeframe},
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": secret_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            equity = data.get("equity", [])
            timestamps = data.get("timestamp", [])
            profit_loss = data.get("profit_loss", [])
            profit_loss_pct = data.get("profit_loss_pct", [])

            history = [
                {
                    "timestamp": timestamps[i] if i < len(timestamps) else None,
                    "equity": equity[i] if i < len(equity) else None,
                    "pl": profit_loss[i] if i < len(profit_loss) else None,
                    "pl_pct": profit_loss_pct[i] if i < len(profit_loss_pct) else None,
                }
                for i in range(len(equity))
            ]

            return {
                "history": history,
                "count": len(history),
                "base_value": data.get("base_value"),
                "source": "Alpaca Paper",
            }

    except Exception as e:
        logger.error("alpaca_portfolio_history_error", error=str(e))
        return {"error": str(e), "source": "Alpaca Paper"}


# =============================================================================
# FMP Financial Statements (Stable API - Free Tier: 250 calls/day, top US tickers)
# =============================================================================


async def fmp_income_statement(
    symbol: str = "AAPL",
    period: str = "annual",
    limit: int = 4,
) -> dict[str, Any]:
    """Ottieni Income Statement completo da FMP.

    Args:
        symbol: Ticker (es. "AAPL")
        period: "annual" o "quarter"
        limit: Numero periodi (max 10)

    Returns:
        dict con voci income statement
    """
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        return {"error": "FMP_API_KEY not configured", "source": "FMP"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://financialmodelingprep.com/stable/income-statement",
                params={
                    "symbol": symbol.upper(),
                    "period": period,
                    "limit": limit,
                    "apikey": api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            statements = [
                {
                    "date": s.get("date"),
                    "revenue": s.get("revenue"),
                    "gross_profit": s.get("grossProfit"),
                    "operating_income": s.get("operatingIncome"),
                    "net_income": s.get("netIncome"),
                    "eps": s.get("eps"),
                    "eps_diluted": s.get("epsdiluted"),
                    "gross_margin": round(s.get("grossProfitRatio", 0) * 100, 2),
                    "operating_margin": round(s.get("operatingIncomeRatio", 0) * 100, 2),
                    "net_margin": round(s.get("netIncomeRatio", 0) * 100, 2),
                }
                for s in data
            ]

            return {
                "symbol": symbol.upper(),
                "period": period,
                "statements": statements,
                "count": len(statements),
                "source": "FMP",
            }

    except Exception as e:
        logger.error("fmp_income_statement_error", error=str(e))
        return {"error": str(e), "source": "FMP"}


async def fmp_balance_sheet(
    symbol: str = "AAPL",
    period: str = "annual",
    limit: int = 4,
) -> dict[str, Any]:
    """Ottieni Balance Sheet completo da FMP.

    Args:
        symbol: Ticker
        period: "annual" o "quarter"
        limit: Numero periodi

    Returns:
        dict con voci balance sheet
    """
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        return {"error": "FMP_API_KEY not configured", "source": "FMP"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://financialmodelingprep.com/stable/balance-sheet-statement",
                params={
                    "symbol": symbol.upper(),
                    "period": period,
                    "limit": limit,
                    "apikey": api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            statements = [
                {
                    "date": s.get("date"),
                    "total_assets": s.get("totalAssets"),
                    "total_liabilities": s.get("totalLiabilities"),
                    "total_equity": s.get("totalStockholdersEquity"),
                    "cash": s.get("cashAndCashEquivalents"),
                    "total_debt": s.get("totalDebt"),
                    "net_debt": s.get("netDebt"),
                    "current_ratio": round(
                        s.get("totalCurrentAssets", 0) / s.get("totalCurrentLiabilities", 1), 2
                    )
                    if s.get("totalCurrentLiabilities")
                    else None,
                }
                for s in data
            ]

            return {
                "symbol": symbol.upper(),
                "period": period,
                "statements": statements,
                "count": len(statements),
                "source": "FMP",
            }

    except Exception as e:
        logger.error("fmp_balance_sheet_error", error=str(e))
        return {"error": str(e), "source": "FMP"}


async def fmp_cash_flow(
    symbol: str = "AAPL",
    period: str = "annual",
    limit: int = 4,
) -> dict[str, Any]:
    """Ottieni Cash Flow Statement da FMP.

    Args:
        symbol: Ticker
        period: "annual" o "quarter"
        limit: Numero periodi

    Returns:
        dict con voci cash flow
    """
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        return {"error": "FMP_API_KEY not configured", "source": "FMP"}

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://financialmodelingprep.com/stable/cash-flow-statement",
                params={
                    "symbol": symbol.upper(),
                    "period": period,
                    "limit": limit,
                    "apikey": api_key,
                },
            )
            response.raise_for_status()
            data = response.json()

            statements = [
                {
                    "date": s.get("date"),
                    "operating_cf": s.get("operatingCashFlow"),
                    "investing_cf": s.get("netCashUsedForInvestingActivites"),
                    "financing_cf": s.get("netCashUsedProvidedByFinancingActivities"),
                    "free_cash_flow": s.get("freeCashFlow"),
                    "capex": s.get("capitalExpenditure"),
                    "dividends_paid": s.get("dividendsPaid"),
                    "stock_repurchase": s.get("commonStockRepurchased"),
                }
                for s in data
            ]

            return {
                "symbol": symbol.upper(),
                "period": period,
                "statements": statements,
                "count": len(statements),
                "source": "FMP",
            }

    except Exception as e:
        logger.error("fmp_cash_flow_error", error=str(e))
        return {"error": str(e), "source": "FMP"}


async def fmp_stock_screener(
    market_cap_min: int = 1_000_000_000,
    sector: str = "",
    country: str = "US",
    limit: int = 20,
) -> dict[str, Any]:
    """Screener azioni con filtri via FMP.

    Args:
        market_cap_min: Market cap minimo in USD
        sector: Settore (es. "Technology", "Healthcare")
        country: Paese (es. "US", "GB")
        limit: Numero risultati (max 100)

    Returns:
        dict con lista azioni filtrate
    """
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        return {"error": "FMP_API_KEY not configured", "source": "FMP"}

    try:
        params: dict[str, Any] = {
            "marketCapMoreThan": market_cap_min,
            "country": country,
            "limit": min(limit, 100),
            "apikey": api_key,
        }
        if sector:
            params["sector"] = sector

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(
                "https://financialmodelingprep.com/stable/stock-screener",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            stocks = [
                {
                    "symbol": s.get("symbol"),
                    "company_name": s.get("companyName"),
                    "sector": s.get("sector"),
                    "industry": s.get("industry"),
                    "market_cap": s.get("marketCap"),
                    "price": s.get("price"),
                    "volume": s.get("volume"),
                    "country": s.get("country"),
                }
                for s in data
            ]

            return {
                "stocks": stocks,
                "count": len(stocks),
                "filters": {
                    "market_cap_min": market_cap_min,
                    "sector": sector or "all",
                    "country": country,
                },
                "source": "FMP Stock Screener",
            }

    except Exception as e:
        logger.error("fmp_stock_screener_error", error=str(e))
        return {"error": str(e), "source": "FMP"}


# =============================================================================
# Hyperliquid Testnet
# =============================================================================


async def hyperliquid_account() -> dict[str, Any]:
    """Ottieni info account Hyperliquid Testnet.

    Returns:
        dict con info account
    """
    wallet_address = os.getenv("HYPERLIQUID_WALLET_ADDRESS")
    testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"

    if not wallet_address:
        return {
            "error": "HYPERLIQUID_WALLET_ADDRESS not configured",
            "source": "Hyperliquid",
        }

    base_url = "https://api.hyperliquid-testnet.xyz" if testnet else "https://api.hyperliquid.xyz"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{base_url}/info",
                json={
                    "type": "clearinghouseState",
                    "user": wallet_address,
                },
            )
            response.raise_for_status()
            data = response.json()

            margin_summary = data.get("marginSummary", {})

            return {
                "wallet": wallet_address,
                "testnet": testnet,
                "account_value": float(margin_summary.get("accountValue", 0)),
                "total_margin_used": float(margin_summary.get("totalMarginUsed", 0)),
                "total_ntl_pos": float(margin_summary.get("totalNtlPos", 0)),
                "source": "Hyperliquid Testnet" if testnet else "Hyperliquid",
            }

    except Exception as e:
        logger.error("hyperliquid_account_error", error=str(e))
        return {"error": str(e), "source": "Hyperliquid"}


async def hyperliquid_positions() -> dict[str, Any]:
    """Ottieni posizioni aperte Hyperliquid.

    Returns:
        dict con lista posizioni
    """
    wallet_address = os.getenv("HYPERLIQUID_WALLET_ADDRESS")
    testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"

    if not wallet_address:
        return {
            "error": "HYPERLIQUID_WALLET_ADDRESS not configured",
            "source": "Hyperliquid",
        }

    base_url = "https://api.hyperliquid-testnet.xyz" if testnet else "https://api.hyperliquid.xyz"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{base_url}/info",
                json={
                    "type": "clearinghouseState",
                    "user": wallet_address,
                },
            )
            response.raise_for_status()
            data = response.json()

            asset_positions = data.get("assetPositions", [])
            positions = [
                {
                    "coin": ap.get("position", {}).get("coin"),
                    "size": float(ap.get("position", {}).get("szi", 0)),
                    "entry_price": float(ap.get("position", {}).get("entryPx", 0)),
                    "unrealized_pnl": float(ap.get("position", {}).get("unrealizedPnl", 0)),
                    "leverage": ap.get("position", {}).get("leverage", {}).get("value"),
                }
                for ap in asset_positions
                if float(ap.get("position", {}).get("szi", 0)) != 0
            ]

            return {
                "positions": positions,
                "count": len(positions),
                "source": "Hyperliquid Testnet" if testnet else "Hyperliquid",
            }

    except Exception as e:
        logger.error("hyperliquid_positions_error", error=str(e))
        return {"error": str(e), "source": "Hyperliquid"}


async def hyperliquid_price(coin: str = "BTC") -> dict[str, Any]:
    """Ottieni prezzo crypto da Hyperliquid.

    Args:
        coin: Coin symbol (es. "BTC", "ETH")

    Returns:
        dict con prezzo
    """
    testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"
    base_url = "https://api.hyperliquid-testnet.xyz" if testnet else "https://api.hyperliquid.xyz"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{base_url}/info",
                json={"type": "allMids"},
            )
            response.raise_for_status()
            data = response.json()

            price = data.get(coin.upper())

            if price:
                return {
                    "coin": coin.upper(),
                    "price": float(price),
                    "source": "Hyperliquid Testnet" if testnet else "Hyperliquid",
                }
            else:
                return {
                    "error": f"Coin not found: {coin}",
                    "available": list(data.keys())[:10],
                    "source": "Hyperliquid",
                }

    except Exception as e:
        logger.error("hyperliquid_price_error", error=str(e))
        return {"error": str(e), "source": "Hyperliquid"}


async def hyperliquid_orderbook(
    coin: str = "BTC",
    depth: int = 10,
) -> dict[str, Any]:
    """Ottieni L2 order book da Hyperliquid.

    Args:
        coin: Coin symbol (es. "BTC", "ETH")
        depth: Profondità book

    Returns:
        dict con bids e asks
    """
    testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"
    base_url = "https://api.hyperliquid-testnet.xyz" if testnet else "https://api.hyperliquid.xyz"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{base_url}/info",
                json={
                    "type": "l2Book",
                    "coin": coin.upper(),
                },
            )
            response.raise_for_status()
            data = response.json()

            levels = data.get("levels", [[], []])
            bids = [
                {"price": float(b.get("px", 0)), "size": float(b.get("sz", 0))}
                for b in levels[0][:depth]
            ]
            asks = [
                {"price": float(a.get("px", 0)), "size": float(a.get("sz", 0))}
                for a in levels[1][:depth]
            ]

            spread = asks[0]["price"] - bids[0]["price"] if bids and asks else 0

            return {
                "coin": coin.upper(),
                "bids": bids,
                "asks": asks,
                "best_bid": bids[0]["price"] if bids else None,
                "best_ask": asks[0]["price"] if asks else None,
                "spread": round(spread, 4),
                "source": "Hyperliquid Testnet" if testnet else "Hyperliquid",
            }

    except Exception as e:
        logger.error("hyperliquid_orderbook_error", error=str(e))
        return {"error": str(e), "source": "Hyperliquid"}


async def hyperliquid_funding_rates() -> dict[str, Any]:
    """Ottieni funding rates per tutti i perpetual su Hyperliquid.

    Returns:
        dict con funding rates per coin
    """
    testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"
    base_url = "https://api.hyperliquid-testnet.xyz" if testnet else "https://api.hyperliquid.xyz"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{base_url}/info",
                json={"type": "metaAndAssetCtxs"},
            )
            response.raise_for_status()
            data = response.json()

            # data è [meta, [asset_ctx, ...]]
            meta = data[0] if len(data) > 0 else {}
            asset_ctxs = data[1] if len(data) > 1 else []

            universe = meta.get("universe", [])

            rates = []
            for i, ctx in enumerate(asset_ctxs):
                if i < len(universe):
                    coin = universe[i].get("name", f"UNKNOWN_{i}")
                    funding = float(ctx.get("funding", 0))
                    mark_px = float(ctx.get("markPx", 0))
                    open_interest = float(ctx.get("openInterest", 0))
                    volume_24h = float(ctx.get("dayNtlVlm", 0))

                    rates.append(
                        {
                            "coin": coin,
                            "funding_rate": round(funding * 100, 6),  # in %
                            "annualized_rate": round(funding * 100 * 3 * 365, 2),  # annualizzato
                            "mark_price": mark_px,
                            "open_interest": open_interest,
                            "volume_24h": volume_24h,
                        }
                    )

            # Sort by absolute funding rate
            rates.sort(key=lambda x: abs(x["funding_rate"]), reverse=True)

            return {
                "rates": rates[:30],
                "count": len(rates),
                "source": "Hyperliquid Testnet" if testnet else "Hyperliquid",
            }

    except Exception as e:
        logger.error("hyperliquid_funding_rates_error", error=str(e))
        return {"error": str(e), "source": "Hyperliquid"}


async def hyperliquid_candles(
    coin: str = "BTC",
    interval: str = "1h",
    limit: int = 10,
) -> dict[str, Any]:
    """Ottieni candlestick OHLCV da Hyperliquid.

    Args:
        coin: Coin symbol (es. "BTC")
        interval: "1m", "5m", "15m", "1h", "4h", "1d"
        limit: Numero candele

    Returns:
        dict con OHLCV candles
    """
    testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"
    base_url = "https://api.hyperliquid-testnet.xyz" if testnet else "https://api.hyperliquid.xyz"

    # Mapping intervallo a millisecondi
    interval_ms = {
        "1m": 60_000,
        "5m": 300_000,
        "15m": 900_000,
        "1h": 3_600_000,
        "4h": 14_400_000,
        "1d": 86_400_000,
    }

    interval_val = interval_ms.get(interval, 3_600_000)

    try:
        import time as _time

        end_time = int(_time.time() * 1000)
        start_time = end_time - (interval_val * limit)

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{base_url}/info",
                json={
                    "type": "candleSnapshot",
                    "req": {
                        "coin": coin.upper(),
                        "interval": interval,
                        "startTime": start_time,
                        "endTime": end_time,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()

            candles = [
                {
                    "timestamp": c.get("t"),
                    "open": float(c.get("o", 0)),
                    "high": float(c.get("h", 0)),
                    "low": float(c.get("l", 0)),
                    "close": float(c.get("c", 0)),
                    "volume": float(c.get("v", 0)),
                }
                for c in data[-limit:]
            ]

            return {
                "coin": coin.upper(),
                "interval": interval,
                "candles": candles,
                "count": len(candles),
                "source": "Hyperliquid Testnet" if testnet else "Hyperliquid",
            }

    except Exception as e:
        logger.error("hyperliquid_candles_error", error=str(e))
        return {"error": str(e), "source": "Hyperliquid"}


async def hyperliquid_open_orders() -> dict[str, Any]:
    """Ottieni ordini aperti su Hyperliquid Testnet.

    Returns:
        dict con lista ordini aperti
    """
    wallet_address = os.getenv("HYPERLIQUID_WALLET_ADDRESS")
    testnet = os.getenv("HYPERLIQUID_TESTNET", "true").lower() == "true"

    if not wallet_address:
        return {
            "error": "HYPERLIQUID_WALLET_ADDRESS not configured",
            "source": "Hyperliquid",
        }

    base_url = "https://api.hyperliquid-testnet.xyz" if testnet else "https://api.hyperliquid.xyz"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{base_url}/info",
                json={
                    "type": "openOrders",
                    "user": wallet_address,
                },
            )
            response.raise_for_status()
            data = response.json()

            orders = [
                {
                    "coin": o.get("coin"),
                    "side": "buy" if o.get("isBuy") else "sell",
                    "price": float(o.get("limitPx", 0)),
                    "size": float(o.get("sz", 0)),
                    "order_id": o.get("oid"),
                    "timestamp": o.get("timestamp"),
                }
                for o in data
            ]

            return {
                "orders": orders,
                "count": len(orders),
                "source": "Hyperliquid Testnet" if testnet else "Hyperliquid",
            }

    except Exception as e:
        logger.error("hyperliquid_open_orders_error", error=str(e))
        return {"error": str(e), "source": "Hyperliquid"}


# =============================================================================
# Tool Registry
# =============================================================================

AVAILABLE_TOOLS = {
    # CoinGecko
    "coingecko_price": coingecko_price,
    "coingecko_trending": coingecko_trending,
    "coingecko_chart": coingecko_chart,
    # Binance
    "binance_price": binance_price,
    "binance_ticker_24h": binance_ticker_24h,
    "binance_klines": binance_klines,
    "binance_orderbook": binance_orderbook,
    # Analysis
    "fear_greed_index": fear_greed_index,
    "market_context_analysis": market_context_analysis,
    "hot_scanner": hot_scanner,
    "rumor_scanner": rumor_scanner,
    # Yahoo Finance
    "yahoo_finance_quote": yahoo_quote,
    "yahoo_quote": yahoo_quote,
    "yahooquery_stock_analysis": yahooquery_stock_analysis,
    # Finnhub
    "finnhub_news": finnhub_news,
    "finnhub_quote": finnhub_quote,
    # FRED
    "fred_series": fred_series,
    "fred_search": fred_search,
    # NASDAQ Data
    "nasdaq_quote": nasdaq_quote,
    # FMP - Fundamental Data
    "stock_key_metrics": stock_key_metrics,
    "stock_ratios": stock_ratios,
    "stock_dcf": stock_dcf,
    "stock_income_statement": stock_income_statement,
    "stock_balance_sheet": stock_balance_sheet,
    "stock_cash_flow": stock_cash_flow,
    "fmp_stock_screener": fmp_stock_screener,
    # Aliases for backward compatibility
    "fmp_key_metrics": stock_key_metrics,
    "fmp_ratios": stock_ratios,
    "fmp_dcf": stock_dcf,
    "fmp_income_statement": stock_income_statement,
    "fmp_balance_sheet": stock_balance_sheet,
    "fmp_cash_flow": stock_cash_flow,
    # Technical Indicators
    "technical_indicators": technical_indicators,
    # SEC EDGAR
    "edgar_filings": edgar_filings,
    "edgar_company_info": edgar_company_info,
    # Alpaca Paper Trading
    "alpaca_account": alpaca_account,
    "alpaca_positions": alpaca_positions,
    "alpaca_quote": alpaca_quote,
    "alpaca_bars": alpaca_bars,
    "alpaca_place_order": alpaca_place_order,
    "alpaca_order_history": alpaca_order_history,
    "alpaca_cancel_order": alpaca_cancel_order,
    "alpaca_portfolio_history": alpaca_portfolio_history,
    # Hyperliquid
    "hyperliquid_account": hyperliquid_account,
    "hyperliquid_positions": hyperliquid_positions,
    "hyperliquid_price": hyperliquid_price,
    "hyperliquid_orderbook": hyperliquid_orderbook,
    "hyperliquid_funding_rates": hyperliquid_funding_rates,
    "hyperliquid_candles": hyperliquid_candles,
    "hyperliquid_open_orders": hyperliquid_open_orders,
}


# Lazy import for multi_analysis (avoids circular import)
def _get_multi_analysis():
    from me4brain.domains.finance_crypto.tools.multi_analysis import multi_dimensional_analysis

    return multi_dimensional_analysis


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool finance per nome.

    Filtra automaticamente parametri non accettati dalla funzione.
    """
    import inspect

    if tool_name == "multi_dimensional_analysis":
        func = _get_multi_analysis()
        sig = inspect.signature(func)
        valid_params = set(sig.parameters.keys())
        filtered_args = {k: v for k, v in arguments.items() if k in valid_params}
        if len(filtered_args) < len(arguments):
            ignored = set(arguments.keys()) - valid_params
            logger.warning(
                "execute_tool_ignored_params",
                tool=tool_name,
                ignored=list(ignored),
            )
        return await func(**filtered_args)

    if tool_name not in AVAILABLE_TOOLS:
        return {
            "error": f"Unknown finance tool: {tool_name}",
            "available": list(AVAILABLE_TOOLS.keys()) + ["multi_dimensional_analysis"],
        }

    tool_func = AVAILABLE_TOOLS[tool_name]

    # Filter arguments to only those the function accepts
    sig = inspect.signature(tool_func)
    valid_params = set(sig.parameters.keys())
    filtered_args = {k: v for k, v in arguments.items() if k in valid_params}

    if len(filtered_args) < len(arguments):
        ignored = set(arguments.keys()) - valid_params
        logger.warning(
            "execute_tool_ignored_params",
            tool=tool_name,
            ignored=list(ignored),
            hint="LLM hallucinated parameters not in function signature",
        )

    return await tool_func(**filtered_args)


# =============================================================================
# Engine Integration - Tool Definitions for auto-discovery
# =============================================================================


def get_tool_definitions() -> list:
    """Get tool definitions for ToolCallingEngine auto-discovery.

    Returns:
        List of ToolDefinition objects with schemas for LLM.
    """
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        # CoinGecko
        ToolDefinition(
            name="coingecko_price",
            description="Get real-time cryptocurrency prices, market cap, and 24h change from CoinGecko. Use when user asks about crypto price, Bitcoin value, Ethereum cost, altcoin quotes, or any cryptocurrency market data. Supports multiple coins in a single call.",
            parameters={
                "ids": ToolParameter(
                    type="string",
                    description="Comma-separated CoinGecko coin IDs (e.g., 'bitcoin,ethereum,solana,cardano'). Use lowercase slugs, not ticker symbols.",
                    required=True,
                ),
                "vs_currencies": ToolParameter(
                    type="string",
                    description="Target fiat currencies for price conversion (e.g., 'usd,eur,gbp')",
                    required=False,
                    default="usd,eur",
                ),
            },
            domain="finance",
            category="price",
        ),
        ToolDefinition(
            name="coingecko_trending",
            description="Get trending cryptocurrencies in the last 24 hours from CoinGecko. Returns hottest coins by search popularity and social buzz. Use when user asks 'trending crypto', 'hot coins today', 'quali crypto sono di tendenza', 'popular cryptocurrencies', or 'cosa sta salendo'.",
            parameters={},
            domain="finance",
            category="trending",
        ),
        ToolDefinition(
            name="coingecko_chart",
            description="Get historical price chart and OHLC data for a cryptocurrency. Use when user asks for price history, price trends, performance over time, monthly/weekly/yearly charts, or historical analysis of Bitcoin, Ethereum, or any crypto.",
            parameters={
                "coin_id": ToolParameter(
                    type="string",
                    description="CoinGecko coin ID in lowercase (e.g., 'bitcoin', 'ethereum', 'solana')",
                    required=True,
                ),
                "vs_currency": ToolParameter(
                    type="string",
                    description="Target fiat currency for chart (e.g., 'usd', 'eur')",
                    required=False,
                    default="usd",
                ),
                "days": ToolParameter(
                    type="integer",
                    description="Number of days of history: 1 (24h), 7 (week), 30 (month), 90 (quarter), 365 (year)",
                    required=False,
                    default="30",
                ),
            },
            domain="finance",
            category="chart",
        ),
        # Binance
        ToolDefinition(
            name="binance_price",
            description="Get real-time cryptocurrency price from Binance exchange. Returns current trading price for any crypto pair. Use when user asks 'Bitcoin price', 'quanto costa ETH', 'BTC/USDT price', 'crypto exchange rate', or 'prezzo criptovaluta'.",
            parameters={
                "symbol": ToolParameter(
                    type="string",
                    description="Trading pair (e.g., 'BTCUSDT', 'ETHUSDT')",
                    required=True,
                ),
            },
            domain="finance",
            category="price",
        ),
        ToolDefinition(
            name="binance_ticker_24h",
            description="Get 24-hour trading statistics from Binance exchange. Returns price change, high/low, volume for any trading pair. Use when user asks 'BTC 24h change', 'volume giornaliero', 'quanto è salito Bitcoin oggi', 'daily crypto stats', or 'trading volume'.",
            parameters={
                "symbol": ToolParameter(
                    type="string",
                    description="Trading pair (e.g., 'BTCUSDT')",
                    required=True,
                ),
            },
            domain="finance",
            category="stats",
        ),
        # Yahoo Finance
        ToolDefinition(
            name="yahoo_quote",
            description="Get real-time stock quote and market data from Yahoo Finance. Returns current price, day high/low, 52-week range, volume, market cap, P/E ratio, dividend yield. Use when user asks for stock price, equity quote, company valuation, or market data for any publicly traded stock.",
            parameters={
                "symbol": ToolParameter(
                    type="string",
                    description="Stock ticker symbol in uppercase (e.g., 'AAPL' for Apple, 'TSLA' for Tesla, 'MSFT' for Microsoft, 'NVDA' for NVIDIA)",
                    required=True,
                ),
            },
            domain="finance",
            category="stock",
        ),
        ToolDefinition(
            name="yahooquery_stock_analysis",
            description="Complete stock analysis in ONE API call. Returns price, fundamentals (P/E, PEG, EV/EBITDA), financial KPIs (margins, ROE, ROA), analyst consensus (buy/hold/sell), technical indicators (RSI, MACD, ATR, SMA, BBands), and trading levels (entry, stop-loss, take-profit). No API key needed. Use when user asks for comprehensive stock analysis, full equity research, 'analisi completa azione', or multi-dimensional stock evaluation.",
            parameters={
                "symbol": ToolParameter(
                    type="string",
                    description="Stock ticker symbol (e.g., 'AAPL', 'HOG', 'TSLA', 'MSFT')",
                    required=True,
                ),
            },
            domain="finance",
            category="stock",
        ),
        # Finnhub
        ToolDefinition(
            name="finnhub_news",
            description="Get latest financial market news and headlines from Finnhub. Returns breaking news, market updates, earnings reports, mergers & acquisitions. Use when user asks for market news, financial headlines, stock news, forex news, or crypto industry news.",
            parameters={
                "category": ToolParameter(
                    type="string",
                    description="News category filter: 'general' (all markets), 'forex' (currency), 'crypto' (cryptocurrency), 'merger' (M&A deals)",
                    required=False,
                    default="general",
                    enum=["general", "forex", "crypto", "merger"],
                ),
            },
            domain="finance",
            category="news",
        ),
        ToolDefinition(
            name="finnhub_quote",
            description="Get comprehensive stock quote with real-time price, day change, high/low, previous close from Finnhub. Use when user asks 'Apple stock price', 'quotazione azione', 'stock quote', 'current stock value', or 'quanto vale un'azione'.",
            parameters={
                "symbol": ToolParameter(
                    type="string",
                    description="Stock ticker symbol",
                    required=True,
                ),
            },
            domain="finance",
            category="stock",
        ),
        # FRED
        ToolDefinition(
            name="fred_series",
            description="Get economic data series from Federal Reserve FRED. Access GDP, unemployment (UNRATE), inflation (CPI), interest rates, and 700k+ economic indicators. Use when user asks 'US GDP', 'tasso disoccupazione', 'inflation rate', 'dati economici', 'Federal Reserve data', or 'macroeconomic indicators'.",
            parameters={
                "series_id": ToolParameter(
                    type="string",
                    description="FRED series ID (e.g., 'GDP', 'UNRATE', 'CPIAUCSL')",
                    required=True,
                ),
                "limit": ToolParameter(
                    type="integer",
                    description="Number of observations",
                    required=False,
                    default="10",
                ),
            },
            domain="finance",
            category="economic",
        ),
        # Stock Fundamentals (Yahoo Finance + FMP fallback)
        ToolDefinition(
            name="stock_key_metrics",
            description="Get key financial metrics TTM (trailing twelve months) for fundamental stock analysis. Returns ROE, ROA, EV/EBITDA, market cap, book value. Multi-source: Yahoo Finance (primary) + FMP (fallback). Use when user asks for company fundamentals, financial health, valuation metrics, or profitability ratios.",
            parameters={
                "symbol": ToolParameter(
                    type="string",
                    description="Stock ticker symbol in uppercase (e.g., 'AAPL' for Apple, 'TSLA' for Tesla, 'MSFT' for Microsoft)",
                    required=True,
                ),
            },
            domain="finance",
            category="fundamentals",
        ),
        ToolDefinition(
            name="stock_ratios",
            description="Get comprehensive financial ratios TTM for stock valuation analysis. Returns P/E ratio, PEG, price-to-book, price-to-sales, profit margins, return ratios, and debt metrics. Multi-source: Yahoo Finance (primary) + FMP (fallback). Use when user asks is a stock cheap/expensive, valuation comparison, margin analysis, or financial ratio analysis.",
            parameters={
                "symbol": ToolParameter(
                    type="string",
                    description="Stock ticker symbol in uppercase (e.g., 'GOOGL', 'AMZN', 'META')",
                    required=True,
                ),
            },
            domain="finance",
            category="fundamentals",
        ),
        ToolDefinition(
            name="stock_dcf",
            description="Get fair value estimate for stock valuation (analyst targets + DCF model). Compares intrinsic value to market price to identify overvalued/undervalued stocks. Multi-source: Yahoo Finance analyst targets (primary) + FMP DCF model (fallback). Use when user asks 'fair value AAPL', 'is Tesla overvalued', 'DCF analysis', 'valore intrinseco', 'stock valuation', or 'quanto dovrebbe valere un'azione'.",
            parameters={
                "symbol": ToolParameter(
                    type="string",
                    description="Stock ticker symbol (call once per ticker)",
                    required=True,
                ),
            },
            domain="finance",
            category="valuation",
        ),
        # Technical Indicators
        ToolDefinition(
            name="technical_indicators",
            description="Calculate technical analysis indicators for stock trading. Supports RSI (overbought/oversold), MACD (momentum/trend), Bollinger Bands (volatility), ADX (trend strength), ATR (volatility), Stochastic (momentum), OBV (volume), CCI (deviation), Williams %R, SMA/EMA (moving averages), Ichimoku Cloud, and Parabolic SAR. Use when user asks for technical analysis, chart signals, buy/sell indicators, or trading analysis.",
            parameters={
                "symbol": ToolParameter(
                    type="string",
                    description="Stock ticker symbol (e.g., 'AAPL', 'TSLA')",
                    required=True,
                ),
                "indicator": ToolParameter(
                    type="string",
                    description="Tipo indicatore: rsi, macd, bbands, stoch, adx, atr, obv, cci, willr, sma, ema, ichimoku, sar",
                    required=True,
                    enum=[
                        "rsi",
                        "macd",
                        "bbands",
                        "stoch",
                        "adx",
                        "atr",
                        "obv",
                        "cci",
                        "willr",
                        "sma",
                        "ema",
                        "ichimoku",
                        "sar",
                    ],
                ),
                "period": ToolParameter(
                    type="integer",
                    description="Periodo per il calcolo (default 14)",
                    required=False,
                    default="14",
                ),
            },
            domain="finance",
            category="technical_analysis",
        ),
        # SEC EDGAR
        ToolDefinition(
            name="edgar_filings",
            description="Get SEC EDGAR regulatory filings for US public companies. Access 10-K annual reports, 10-Q quarterly reports, 8-K event filings. Use when user asks 'Apple annual report', 'Tesla 10-K', 'SEC filings', 'bilancio annuale', 'documenti SEC', or 'company financial reports'.",
            parameters={
                "ticker": ToolParameter(
                    type="string",
                    description="Stock ticker symbol (e.g., 'AAPL')",
                    required=True,
                ),
                "form_type": ToolParameter(
                    type="string",
                    description="Filing type",
                    required=False,
                    default="10-K",
                    enum=["10-K", "10-Q", "8-K"],
                ),
                "limit": ToolParameter(
                    type="integer",
                    description="Number of filings",
                    required=False,
                    default="5",
                ),
            },
            domain="finance",
            category="filings",
        ),
        ToolDefinition(
            name="edgar_company_info",
            description="Get company information from SEC EDGAR database (CIK, official name, links). Use when user asks 'info azienda AAPL', 'company CIK number', 'dati societari', 'official company name', or 'verify stock ticker'.",
            parameters={
                "ticker": ToolParameter(
                    type="string",
                    description="Stock ticker symbol",
                    required=True,
                ),
            },
            domain="finance",
            category="company",
        ),
        # Alpaca
        ToolDefinition(
            name="alpaca_account",
            description="Get Alpaca paper trading account status. Returns equity, cash balance, buying power, and portfolio value. Use when user asks 'my trading account', 'quanto ho nel conto', 'account balance', 'buying power', or 'portfolio equity'.",
            parameters={},
            domain="finance",
            category="trading",
        ),
        ToolDefinition(
            name="alpaca_positions",
            description="Get all open trading positions from Alpaca paper trading account. Returns quantity, market value, profit/loss for each position. Use when user asks 'my portfolio', 'show my positions', 'what stocks do I own', or 'le mie posizioni'.",
            parameters={},
            domain="finance",
            category="trading",
        ),
        ToolDefinition(
            name="alpaca_quote",
            description="Get real-time stock quote from Alpaca Markets with bid/ask spread, last trade price. Covers US equities with low latency. Use when user asks 'stock price AAPL', 'quotazione azione', 'current share price', or 'quanto vale Tesla'.",
            parameters={
                "symbol": ToolParameter(
                    type="string",
                    description="Stock ticker symbol",
                    required=True,
                ),
            },
            domain="finance",
            category="stock",
        ),
        # Hyperliquid
        ToolDefinition(
            name="hyperliquid_price",
            description="Get real-time cryptocurrency perpetual futures price from Hyperliquid decentralized exchange. Returns mark price, funding rate. Use when user asks 'crypto perp price', 'Hyperliquid BTC', 'DEX crypto price', or 'prezzo futures'.",
            parameters={
                "coin": ToolParameter(
                    type="string",
                    description="Coin symbol (e.g., 'BTC', 'ETH')",
                    required=True,
                ),
            },
            domain="finance",
            category="price",
        ),
        # --- NEW TOOLS ---
        # Binance Klines
        ToolDefinition(
            name="binance_klines",
            description="Get candlestick OHLCV chart data from Binance exchange. Returns open, high, low, close, volume for each candle. Use when user asks for 'BTC candles', 'crypto chart data', 'candele Binance', 'candlestick data', or 'OHLCV history'.",
            parameters={
                "symbol": ToolParameter(
                    type="string", description="Trading pair (e.g., 'BTCUSDT')", required=True
                ),
                "interval": ToolParameter(
                    type="string",
                    description="Candle interval: 1m, 5m, 15m, 1h, 4h, 1d, 1w",
                    required=False,
                    default="1h",
                ),
                "limit": ToolParameter(
                    type="integer",
                    description="Number of candles (max 1000)",
                    required=False,
                    default="10",
                ),
            },
            domain="finance",
            category="chart",
        ),
        # Binance Orderbook
        ToolDefinition(
            name="binance_orderbook",
            description="Get order book depth (bids/asks) from Binance. Shows buy/sell pressure, spread, and market depth. Use when user asks for 'order book BTC', 'book di scambi', 'bid ask spread', or 'market depth crypto'.",
            parameters={
                "symbol": ToolParameter(
                    type="string", description="Trading pair (e.g., 'BTCUSDT')", required=True
                ),
                "limit": ToolParameter(
                    type="integer",
                    description="Depth levels (5, 10, 20, 50, 100)",
                    required=False,
                    default="10",
                ),
            },
            domain="finance",
            category="trading",
        ),
        # Fear & Greed
        ToolDefinition(
            name="fear_greed_index",
            description="Get the CNN Fear & Greed Index for overall market sentiment. Returns score 0-100 (Extreme Fear to Extreme Greed) with historical comparison. Use when user asks 'fear and greed index', 'market sentiment', 'sentimento mercato', 'paura o avidità', or 'is market scared'.",
            parameters={},
            domain="finance",
            category="sentiment",
        ),
        # Market Context
        ToolDefinition(
            name="market_context_analysis",
            description="Analyze overall market conditions: VIX volatility, SPY/QQQ trends, risk-off detection. Returns market regime (bull/bear/choppy) and scoring. Use when user asks 'come sta il mercato', 'market overview', 'VIX level', 'is market bullish', 'regime di mercato', 'contesto mercato', or 'risk-on risk-off'.",
            parameters={},
            domain="finance",
            category="analysis",
        ),
        # Hot Scanner
        ToolDefinition(
            name="hot_scanner",
            description="Scan markets for viral trends: trending crypto, market movers, breaking news. Returns top trending coins, market news headlines. Use when user asks 'cosa è trending', 'hot stocks today', 'trending crypto', 'market buzz', 'cosa sta andando', or 'which stocks are moving'.",
            parameters={
                "include_social": ToolParameter(
                    type="boolean",
                    description="Include social sources",
                    required=False,
                    default="true",
                ),
            },
            domain="finance",
            category="trending",
        ),
        # Rumor Scanner
        ToolDefinition(
            name="rumor_scanner",
            description="Scan for early market signals: M&A rumors, insider buying, analyst upgrades/downgrades, buzz with impact scoring. Use when user asks 'market rumors', 'merger news', 'insider buying', 'rumors di mercato', 'acquisitions', or 'segnali precoci'.",
            parameters={},
            domain="finance",
            category="news",
        ),
        # Alpaca Place Order
        ToolDefinition(
            name="alpaca_place_order",
            description="Place a paper trading order on Alpaca (PAPER ONLY). Supports market, limit, stop, stop_limit orders. Use when user asks 'buy AAPL', 'compra azioni', 'place order', 'sell stock', 'ordine di acquisto', or 'paper trade'.",
            parameters={
                "symbol": ToolParameter(
                    type="string", description="Stock ticker (e.g., 'AAPL')", required=True
                ),
                "qty": ToolParameter(
                    type="number", description="Quantity of shares", required=True
                ),
                "side": ToolParameter(
                    type="string",
                    description="'buy' or 'sell'",
                    required=True,
                    enum=["buy", "sell"],
                ),
                "order_type": ToolParameter(
                    type="string",
                    description="Order type",
                    required=False,
                    default="market",
                    enum=["market", "limit", "stop", "stop_limit"],
                ),
                "limit_price": ToolParameter(
                    type="number", description="Limit price (for limit/stop_limit)", required=False
                ),
                "stop_price": ToolParameter(
                    type="number", description="Stop price (for stop/stop_limit)", required=False
                ),
                "time_in_force": ToolParameter(
                    type="string",
                    description="Time in force",
                    required=False,
                    default="day",
                    enum=["day", "gtc", "ioc", "fok"],
                ),
            },
            domain="finance",
            category="trading",
        ),
        # Alpaca Order History
        ToolDefinition(
            name="alpaca_order_history",
            description="Get order history from Alpaca paper trading. Returns past orders with status, fill info. Use when user asks 'my orders', 'order history', 'storico ordini', 'recent trades', or 'ordini passati'.",
            parameters={
                "status": ToolParameter(
                    type="string",
                    description="Filter: 'open', 'closed', 'all'",
                    required=False,
                    default="all",
                    enum=["open", "closed", "all"],
                ),
                "limit": ToolParameter(
                    type="integer", description="Number of orders", required=False, default="10"
                ),
            },
            domain="finance",
            category="trading",
        ),
        # Alpaca Cancel Order
        ToolDefinition(
            name="alpaca_cancel_order",
            description="Cancel an open order on Alpaca paper trading. Use when user asks 'cancel order', 'annulla ordine', or 'delete order'.",
            parameters={
                "order_id": ToolParameter(
                    type="string", description="Order ID to cancel", required=True
                ),
            },
            domain="finance",
            category="trading",
        ),
        # Alpaca Portfolio History
        ToolDefinition(
            name="alpaca_portfolio_history",
            description="Get portfolio performance history from Alpaca paper trading. Returns equity curve, P/L over time. Use when user asks 'portfolio performance', 'rendimento portafoglio', 'equity curve', 'come sta andando il mio portafoglio', or 'profit loss history'.",
            parameters={
                "period": ToolParameter(
                    type="string",
                    description="Period: '1D', '1W', '1M', '3M', '1A', 'all'",
                    required=False,
                    default="1M",
                ),
                "timeframe": ToolParameter(
                    type="string",
                    description="Granularity: '1Min', '5Min', '15Min', '1H', '1D'",
                    required=False,
                    default="1D",
                ),
            },
            domain="finance",
            category="trading",
        ),
        # Stock Income Statement (Yahoo + FMP fallback)
        ToolDefinition(
            name="stock_income_statement",
            description="Get complete Income Statement (revenue, profit, margins, EPS). Multi-source: Yahoo Finance (primary) + FMP (fallback). Use when user asks 'revenue AAPL', 'income statement', 'conto economico', 'ricavi azienda', 'profitto netto', or 'company earnings'.",
            parameters={
                "symbol": ToolParameter(type="string", description="Stock ticker", required=True),
                "period": ToolParameter(
                    type="string",
                    description="'annual' or 'quarter'",
                    required=False,
                    default="annual",
                    enum=["annual", "quarter"],
                ),
                "limit": ToolParameter(
                    type="integer", description="Number of periods", required=False, default="4"
                ),
            },
            domain="finance",
            category="fundamentals",
        ),
        # Stock Balance Sheet (Yahoo + FMP fallback)
        ToolDefinition(
            name="stock_balance_sheet",
            description="Get complete Balance Sheet (assets, liabilities, equity, cash, debt). Multi-source: Yahoo Finance (primary) + FMP (fallback). Use when user asks 'balance sheet AAPL', 'stato patrimoniale', 'company assets', 'debito aziendale', or 'current ratio'.",
            parameters={
                "symbol": ToolParameter(type="string", description="Stock ticker", required=True),
                "period": ToolParameter(
                    type="string",
                    description="'annual' or 'quarter'",
                    required=False,
                    default="annual",
                    enum=["annual", "quarter"],
                ),
                "limit": ToolParameter(
                    type="integer", description="Number of periods", required=False, default="4"
                ),
            },
            domain="finance",
            category="fundamentals",
        ),
        # Stock Cash Flow (Yahoo + FMP fallback)
        ToolDefinition(
            name="stock_cash_flow",
            description="Get Cash Flow Statement (operating, investing, financing, FCF, CapEx). Multi-source: Yahoo Finance (primary) + FMP (fallback). Use when user asks 'cash flow AAPL', 'free cash flow', 'flusso di cassa', 'dividends paid', or 'capex'.",
            parameters={
                "symbol": ToolParameter(type="string", description="Stock ticker", required=True),
                "period": ToolParameter(
                    type="string",
                    description="'annual' or 'quarter'",
                    required=False,
                    default="annual",
                    enum=["annual", "quarter"],
                ),
                "limit": ToolParameter(
                    type="integer", description="Number of periods", required=False, default="4"
                ),
            },
            domain="finance",
            category="fundamentals",
        ),
        # FMP Stock Screener
        ToolDefinition(
            name="fmp_stock_screener",
            description="Screen stocks by market cap, sector, country filters. Use when user asks 'show me large cap tech stocks', 'screener azioni', 'find stocks sector healthcare', 'azioni con market cap alto', or 'stock filter'.",
            parameters={
                "market_cap_min": ToolParameter(
                    type="integer",
                    description="Minimum market cap in USD",
                    required=False,
                    default="1000000000",
                ),
                "sector": ToolParameter(
                    type="string",
                    description="Sector filter (e.g., 'Technology', 'Healthcare')",
                    required=False,
                ),
                "country": ToolParameter(
                    type="string",
                    description="Country (e.g., 'US', 'GB')",
                    required=False,
                    default="US",
                ),
                "limit": ToolParameter(
                    type="integer", description="Max results (1-100)", required=False, default="20"
                ),
            },
            domain="finance",
            category="screener",
        ),
        # Hyperliquid Orderbook
        ToolDefinition(
            name="hyperliquid_orderbook",
            description="Get L2 order book from Hyperliquid DEX. Shows bids/asks, spread for crypto perpetuals. Use when user asks 'Hyperliquid order book', 'book BTC perp', 'spread futures', or 'depth DEX'.",
            parameters={
                "coin": ToolParameter(
                    type="string", description="Coin (e.g., 'BTC', 'ETH')", required=True
                ),
                "depth": ToolParameter(
                    type="integer", description="Book depth", required=False, default="10"
                ),
            },
            domain="finance",
            category="trading",
        ),
        # Hyperliquid Funding Rates
        ToolDefinition(
            name="hyperliquid_funding_rates",
            description="Get funding rates for all perpetual futures on Hyperliquid. Shows annualized rates, open interest, volume. Use when user asks 'funding rates', 'tassi di finanziamento', 'perp funding', 'Hyperliquid rates', or 'carry trade crypto'.",
            parameters={},
            domain="finance",
            category="trading",
        ),
        # Hyperliquid Candles
        ToolDefinition(
            name="hyperliquid_candles",
            description="Get OHLCV candlestick data from Hyperliquid perpetual futures. Use when user asks 'BTC candles Hyperliquid', 'chart perp', 'candele futures', or 'OHLCV Hyperliquid'.",
            parameters={
                "coin": ToolParameter(
                    type="string", description="Coin (e.g., 'BTC')", required=True
                ),
                "interval": ToolParameter(
                    type="string",
                    description="Candle interval: 1m, 5m, 15m, 1h, 4h, 1d",
                    required=False,
                    default="1h",
                ),
                "limit": ToolParameter(
                    type="integer", description="Number of candles", required=False, default="10"
                ),
            },
            domain="finance",
            category="chart",
        ),
        # Hyperliquid Open Orders
        ToolDefinition(
            name="hyperliquid_open_orders",
            description="Get open orders on Hyperliquid testnet. Use when user asks 'my open orders Hyperliquid', 'ordini aperti', 'pending orders DEX', or 'Hyperliquid orders'.",
            parameters={},
            domain="finance",
            category="trading",
        ),
        # Multi-Analysis Orchestrator
        ToolDefinition(
            name="multi_dimensional_analysis",
            description="Run a comprehensive multi-dimensional analysis on any stock, crypto, or ETF. Analyzes fundamentals (P/E, ROE, margins), technicals (RSI, MACD, ADX), sentiment (Fear&Greed, VIX), valuation (DCF), momentum, and market context in parallel. Produces a composite score (0-100), signal (STRONG BUY/BUY/HOLD/SELL/STRONG SELL), and detailed breakdown. Use when user asks 'analizzami AAPL', 'analisi completa Bitcoin', 'should I buy TSLA', 'multi analysis', 'valutazione completa', or 'is this stock a buy'.",
            parameters={
                "symbol": ToolParameter(
                    type="string",
                    description="Ticker symbol (e.g., 'AAPL', 'BTCUSDT', 'ETH-USD', 'SPY')",
                    required=True,
                ),
                "depth": ToolParameter(
                    type="string",
                    description="Analysis depth: 'quick' (3 dimensions), 'standard' (5), 'deep' (all + hot/rumor scanner)",
                    required=False,
                    default="standard",
                    enum=["quick", "standard", "deep"],
                ),
            },
            domain="finance",
            category="analysis",
        ),
    ]


def get_executors() -> dict:
    """Get executor functions for ToolCallingEngine.

    Returns:
        Dict mapping tool names to async executor functions.
    """
    return {
        # CoinGecko
        "coingecko_price": coingecko_price,
        "coingecko_trending": coingecko_trending,
        "coingecko_chart": coingecko_chart,
        # Binance
        "binance_price": binance_price,
        "binance_ticker_24h": binance_ticker_24h,
        "binance_klines": binance_klines,
        "binance_orderbook": binance_orderbook,
        # Analysis
        "fear_greed_index": fear_greed_index,
        "market_context_analysis": market_context_analysis,
        "hot_scanner": hot_scanner,
        "rumor_scanner": rumor_scanner,
        # Yahoo Finance
        "yahoo_quote": yahoo_quote,
        # Finnhub
        "finnhub_news": finnhub_news,
        "finnhub_quote": finnhub_quote,
        # FRED
        "fred_series": fred_series,
        "fred_search": fred_search,
        # FMP - Fundamental Data
        "stock_key_metrics": stock_key_metrics,
        "stock_ratios": stock_ratios,
        "stock_dcf": stock_dcf,
        "stock_income_statement": stock_income_statement,
        "stock_balance_sheet": stock_balance_sheet,
        "stock_cash_flow": stock_cash_flow,
        "fmp_stock_screener": fmp_stock_screener,
        # Aliases for backward compatibility
        "fmp_key_metrics": stock_key_metrics,
        "fmp_ratios": stock_ratios,
        "fmp_dcf": stock_dcf,
        "fmp_income_statement": stock_income_statement,
        "fmp_balance_sheet": stock_balance_sheet,
        "fmp_cash_flow": stock_cash_flow,
        # Technical Indicators
        "technical_indicators": technical_indicators,
        # SEC EDGAR
        "edgar_filings": edgar_filings,
        "edgar_company_info": edgar_company_info,
        # Alpaca Paper Trading
        "alpaca_account": alpaca_account,
        "alpaca_positions": alpaca_positions,
        "alpaca_quote": alpaca_quote,
        "alpaca_bars": alpaca_bars,
        "alpaca_place_order": alpaca_place_order,
        "alpaca_order_history": alpaca_order_history,
        "alpaca_cancel_order": alpaca_cancel_order,
        "alpaca_portfolio_history": alpaca_portfolio_history,
        # Hyperliquid
        "hyperliquid_account": hyperliquid_account,
        "hyperliquid_positions": hyperliquid_positions,
        "hyperliquid_price": hyperliquid_price,
        "hyperliquid_orderbook": hyperliquid_orderbook,
        "hyperliquid_funding_rates": hyperliquid_funding_rates,
        "hyperliquid_candles": hyperliquid_candles,
        "hyperliquid_open_orders": hyperliquid_open_orders,
        # Multi-Analysis (lazy import)
        "multi_dimensional_analysis": _get_multi_analysis(),
    }


# =============================================================================
# COMPONENT 2: yahooquery_historical tool con retry logic e caching
# =============================================================================


async def yahooquery_historical(
    symbols: str | list[str] = "^GSPC",
    period: str = "ytd",
    interval: str = "1d",
    asynchronous: bool = True,
) -> dict[str, Any]:
    """Get historical price data using yahooquery (faster than yfinance for batches).

    Args:
        symbols: Single ticker or list (e.g., ["AAPL", "MSFT", "^GSPC"])
        period: ytd, 1mo, 3mo, 6mo, 1y, 2y, 5y, max
        interval: 1d, 1wk, 1mo
        asynchronous: Use async fetching for multiple tickers (recommended)

    Returns:
        dict with historical OHLCV data per ticker
    """
    try:
        import pandas as pd
        from yahooquery import Ticker

        # Normalize to list
        if isinstance(symbols, str):
            symbols = [symbols]

        logger.info(
            "yahooquery_historical_fetch",
            symbols=symbols,
            period=period,
            interval=interval,
        )

        # Fetch data
        ticker = Ticker(symbols, asynchronous=asynchronous)
        data = ticker.history(period=period, interval=interval)

        # Handle errors
        if isinstance(data, dict) and "error" in data:
            return {
                "error": data["error"],
                "hint": "yahooquery API error. Check ticker symbols and try again.",
                "source": "yahooquery",
            }

        # Format response
        result = {
            "symbols": symbols,
            "period": period,
            "interval": interval,
            "data": {},
            "source": "yahooquery",
        }

        # Parse multi-index DataFrame
        if isinstance(data.index, pd.MultiIndex):
            for symbol in symbols:
                if symbol in data.index.get_level_values(0):
                    symbol_data = data.loc[symbol]
                    result["data"][symbol] = {
                        "ohlcv": symbol_data.to_dict(orient="records"),
                        "count": len(symbol_data),
                    }
        else:
            # Single ticker
            result["data"][symbols[0]] = {
                "ohlcv": data.to_dict(orient="records"),
                "count": len(data),
            }

        logger.info(
            "yahooquery_historical_success",
            symbols=symbols,
            data_points=sum(v.get("count", 0) for v in result["data"].values()),
        )
        return result

    except ImportError:
        logger.error("yahooquery_not_installed")
        return {
            "error": "yahooquery not installed. Install with: pip install yahooquery",
            "source": "yahooquery",
        }
    except Exception as e:
        logger.error("yahooquery_historical_error", error=str(e))
        return {"error": _sanitize_error(str(e)), "source": "yahooquery"}


async def yahooquery_historical_with_retry(
    symbols: str | list[str],
    period: str = "ytd",
    max_retries: int = 3,
) -> dict[str, Any]:
    """yahooquery with retry logic and exponential backoff.

    Args:
        symbols: Single ticker or list
        period: ytd, 1mo, 3mo, 6mo, 1y, 2y, 5y, max
        max_retries: Number of retry attempts

    Returns:
        dict with historical data or error
    """
    import asyncio as aio

    for attempt in range(max_retries):
        try:
            result = await yahooquery_historical(symbols, period)
            if "error" not in result:
                logger.info("yahooquery_success", attempt=attempt + 1)
                return result
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(
                    "yahooquery_max_retries_exceeded",
                    error=str(e),
                    max_retries=max_retries,
                )
                # Fallback to Alpha Vantage
                logger.info("yahooquery_fallback_to_alphavantage")
                return await alphavantage_historical_fallback(symbols, period)

            wait_time = 2**attempt
            logger.info(
                "yahooquery_retry",
                attempt=attempt + 1,
                wait_seconds=wait_time,
                error=str(e),
            )
            await aio.sleep(wait_time)

    return {"error": "Max retries exceeded", "source": "yahooquery"}


async def alphavantage_historical_fallback(
    symbols: str | list[str], period: str = "ytd"
) -> dict[str, Any]:
    """Fallback to Alpha Vantage if yahooquery fails."""
    try:
        from me4brain.integrations.premium_apis import AlphaVantageService

        service = AlphaVantageService()

        if isinstance(symbols, str):
            symbols = [symbols]

        result = {
            "symbols": symbols,
            "period": period,
            "data": {},
            "source": "alphavantage_fallback",
        }

        for symbol in symbols:
            try:
                data = await service.get_daily(symbol)
                if data and "data" in data:
                    result["data"][symbol] = {
                        "ohlcv": data["data"],
                        "count": len(data["data"]),
                    }
            except Exception as e:
                logger.warning(
                    "alphavantage_fallback_error",
                    symbol=symbol,
                    error=str(e),
                )

        return result if result["data"] else {"error": "Fallback failed", "source": "alphavantage"}

    except Exception as e:
        logger.error("alphavantage_fallback_error", error=str(e))
        return {"error": _sanitize_error(str(e)), "source": "alphavantage"}
