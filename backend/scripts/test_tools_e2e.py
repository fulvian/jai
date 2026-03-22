#!/usr/bin/env python3
"""
Script di test end-to-end per la Tools API.

Flusso:
1. Ricevi query in linguaggio naturale (es. "dimmi il prezzo del bitcoin")
2. Cerca il tool più rilevante via API /search
3. Esegui il tool (con handler per endpoint interni)
4. Restituisci il risultato reale

Usage:
    python scripts/test_tools_e2e.py "dimmi il prezzo del bitcoin"
    python scripts/test_tools_e2e.py "che tempo fa a Roma?"
"""

import argparse
import asyncio
import sys
from typing import Any

import httpx


# Handler per tool "internal://" - simula le chiamate API reali
INTERNAL_HANDLERS: dict[str, callable] = {}


async def handle_coingecko_price(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handler per coingecko_price - chiama API reale CoinGecko."""
    coin_id = arguments.get("coin_id", "bitcoin")
    currency = arguments.get("currency", "usd")

    async with httpx.AsyncClient() as client:
        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": currency,
            "include_24hr_change": "true",
            "include_market_cap": "true",
        }
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if coin_id in data:
            price_data = data[coin_id]
            return {
                "coin": coin_id,
                "currency": currency,
                "price": price_data.get(currency),
                "market_cap": price_data.get(f"{currency}_market_cap"),
                "change_24h": price_data.get(f"{currency}_24h_change"),
            }
        return data


async def handle_openmeteo_weather(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handler per openmeteo_weather - chiama API reale Open-Meteo."""
    lat = arguments.get("latitude", 41.9028)  # Default: Roma
    lon = arguments.get("longitude", 12.4964)

    async with httpx.AsyncClient() as client:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
        }
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        current = data.get("current", {})
        return {
            "location": {"lat": lat, "lon": lon},
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "wind_speed": current.get("wind_speed_10m"),
            "weather_code": current.get("weather_code"),
            "timezone": data.get("timezone"),
        }


async def handle_openmeteo_forecast(arguments: dict[str, Any]) -> dict[str, Any]:
    """Handler per openmeteo_forecast - meteo 7 giorni."""
    lat = arguments.get("latitude", 41.9028)
    lon = arguments.get("longitude", 12.4964)

    async with httpx.AsyncClient() as client:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
        }
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        daily = data.get("daily", {})
        forecast = []
        dates = daily.get("time", [])
        for i, date in enumerate(dates[:7]):
            forecast.append(
                {
                    "date": date,
                    "temp_max": daily.get("temperature_2m_max", [])[i]
                    if i < len(daily.get("temperature_2m_max", []))
                    else None,
                    "temp_min": daily.get("temperature_2m_min", [])[i]
                    if i < len(daily.get("temperature_2m_min", []))
                    else None,
                    "precipitation": daily.get("precipitation_sum", [])[i]
                    if i < len(daily.get("precipitation_sum", []))
                    else None,
                }
            )

        return {
            "location": {"lat": lat, "lon": lon},
            "forecast": forecast,
        }


# Registra handlers
INTERNAL_HANDLERS["coingecko_price"] = handle_coingecko_price
INTERNAL_HANDLERS["openmeteo_weather"] = handle_openmeteo_weather
INTERNAL_HANDLERS["openmeteo_forecast"] = handle_openmeteo_forecast


async def search_tool(query: str, api_base: str = "http://localhost:8089") -> dict | None:
    """Cerca il tool più rilevante per la query."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{api_base}/v1/tools/search",
            json={"query": query, "limit": 1, "min_score": 0.3},
        )
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results:
            return None

        return results[0]


async def execute_tool(
    tool: dict,
    arguments: dict[str, Any],
    api_base: str = "http://localhost:8089",
) -> dict[str, Any]:
    """Esegue il tool, gestendo anche endpoint interni."""
    tool_name = tool.get("name", "")
    endpoint = tool.get("endpoint", "")

    # Se è un tool interno, usa handler dedicato
    if endpoint.startswith("internal://"):
        handler = INTERNAL_HANDLERS.get(tool_name)
        if handler:
            print(f"  🔧 Usando handler interno per: {tool_name}")
            return await handler(arguments)
        else:
            return {"error": f"No handler for internal tool: {tool_name}"}

    # Altrimenti usa l'API /execute
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{api_base}/v1/tools/execute",
            json={
                "tool_id": tool.get("tool_id"),
                "arguments": arguments,
                "intent": f"Execute {tool_name}",
            },
        )
        response.raise_for_status()
        return response.json()


def extract_arguments_from_query(query: str, tool_name: str) -> dict[str, Any]:
    """Estrae argomenti dalla query in base al tipo di tool."""
    query_lower = query.lower()

    # Crypto
    if "bitcoin" in query_lower or "btc" in query_lower:
        return {"coin_id": "bitcoin", "currency": "usd"}
    if "ethereum" in query_lower or "eth" in query_lower:
        return {"coin_id": "ethereum", "currency": "usd"}
    if "solana" in query_lower or "sol" in query_lower:
        return {"coin_id": "solana", "currency": "usd"}

    # Weather - città italiane
    if "roma" in query_lower or "rome" in query_lower:
        return {"latitude": 41.9028, "longitude": 12.4964}
    if "milano" in query_lower or "milan" in query_lower:
        return {"latitude": 45.4642, "longitude": 9.1900}
    if "napoli" in query_lower or "naples" in query_lower:
        return {"latitude": 40.8518, "longitude": 14.2681}
    if "firenze" in query_lower or "florence" in query_lower:
        return {"latitude": 43.7696, "longitude": 11.2558}
    if "torino" in query_lower or "turin" in query_lower:
        return {"latitude": 45.0703, "longitude": 7.6869}

    # Default
    return {}


async def run_query(query: str, verbose: bool = True) -> dict[str, Any]:
    """Esegue l'intera pipeline: search → execute → result."""
    if verbose:
        print(f'\n🔍 Query: "{query}"\n')
        print("=" * 60)

    # Step 1: Cerca il tool
    if verbose:
        print("📡 Cercando tool rilevante...")

    tool = await search_tool(query)

    if not tool:
        result = {"error": "Nessun tool trovato per questa query"}
        if verbose:
            print(f"❌ {result['error']}")
        return result

    if verbose:
        print(f"  ✅ Trovato: {tool['name']}")
        print(f"     Score: {tool['score']:.2f}")
        print(f"     Categoria: {tool.get('category', 'general')}")
        print(f"     Endpoint: {tool.get('endpoint', 'N/A')[:50]}...")

    # Step 2: Estrai argomenti
    arguments = extract_arguments_from_query(query, tool["name"])
    if verbose:
        print(f"\n📦 Argomenti estratti: {arguments}")

    # Step 3: Esegui il tool
    if verbose:
        print("\n⚡ Eseguendo tool...")

    try:
        result = await execute_tool(tool, arguments)

        if verbose:
            print("\n✅ RISULTATO:")
            print("-" * 40)

            # Formatta output in modo leggibile
            if isinstance(result, dict):
                if "price" in result:
                    # Crypto price
                    print(f"  💰 {result.get('coin', 'Crypto').upper()}")
                    print(
                        f"     Prezzo: ${result.get('price', 'N/A'):,.2f} {result.get('currency', 'USD').upper()}"
                    )
                    if result.get("change_24h"):
                        change = result["change_24h"]
                        emoji = "📈" if change > 0 else "📉"
                        print(f"     24h: {emoji} {change:+.2f}%")
                    if result.get("market_cap"):
                        print(f"     Market Cap: ${result['market_cap']:,.0f}")

                elif "temperature" in result:
                    # Weather
                    print(f"  🌡️ Temperatura: {result.get('temperature')}°C")
                    print(f"  💧 Umidità: {result.get('humidity')}%")
                    print(f"  💨 Vento: {result.get('wind_speed')} km/h")

                elif "forecast" in result:
                    # Forecast
                    print(f"  📅 Previsioni 7 giorni:")
                    for day in result.get("forecast", [])[:3]:
                        print(f"     {day['date']}: {day['temp_min']}-{day['temp_max']}°C")

                else:
                    import json

                    print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(result)

        return {"success": True, "tool": tool["name"], "result": result}

    except Exception as e:
        if verbose:
            print(f"\n❌ Errore esecuzione: {e}")
        return {"success": False, "error": str(e)}


async def main():
    parser = argparse.ArgumentParser(
        description="Test end-to-end della Tools API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python scripts/test_tools_e2e.py "dimmi il prezzo del bitcoin"
  python scripts/test_tools_e2e.py "che tempo fa a Milano?"
  python scripts/test_tools_e2e.py "prezzo ethereum in euro"
  python scripts/test_tools_e2e.py "previsioni meteo Roma"
        """,
    )
    parser.add_argument("query", help="Query in linguaggio naturale")
    parser.add_argument("-q", "--quiet", action="store_true", help="Solo output JSON")

    args = parser.parse_args()

    result = await run_query(args.query, verbose=not args.quiet)

    if args.quiet:
        import json

        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
