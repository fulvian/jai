"""Finance & Crypto Domain Package.

Implementa domain handler per dati finanziari e crypto:
- CoinGecko: Prezzi crypto real-time
- Binance: Candlestick, ticker 24h
- Yahoo Finance: Quote azioni
- Finnhub: News mercati
- FRED: Dati economici

Volatilità: REAL_TIME (dati cambiano ogni secondo)
"""

from me4brain.domains.finance_crypto.handler import FinanceCryptoHandler


def get_handler() -> FinanceCryptoHandler:
    """Factory function for domain handler discovery.

    Called by PluginRegistry during auto-discovery.
    """
    return FinanceCryptoHandler()


__all__ = ["FinanceCryptoHandler", "get_handler"]
