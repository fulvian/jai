"""Geo & Weather API Tools."""

from typing import Any
import httpx
import structlog

logger = structlog.get_logger(__name__)
TIMEOUT = 10.0
USER_AGENT = "Me4BrAIn/1.0 (contact@me4brain.ai)"


async def openmeteo_weather(city: str = "Rome") -> dict[str, Any]:
    """Ottieni meteo attuale."""
    try:
        # First geocode city
        # SOTA 2026 Resilience: remove country codes appended by LLM (e.g. "Rome, IT" -> "Rome")
        city_search = city.split(",")[0].strip()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            geo_resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city_search, "count": 1},
            )
            geo_data = geo_resp.json()
            results = geo_data.get("results", [])
            if not results:
                return {"error": f"City not found: {city}"}

            lat, lon = results[0]["latitude"], results[0]["longitude"]
            city_name = results[0].get("name", city)

            weather_resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                    "timezone": "auto",
                },
            )
            weather = weather_resp.json()
            current = weather.get("current", {})

            return {
                "city": city_name,
                "temperature": current.get("temperature_2m"),
                "humidity": current.get("relative_humidity_2m"),
                "wind_speed": current.get("wind_speed_10m"),
                "weather_code": current.get("weather_code"),
                "source": "Open-Meteo",
            }
    except Exception as e:
        logger.error("openmeteo_error", error=str(e))
        return {"error": str(e)}


async def usgs_earthquakes(days: int = 7, min_magnitude: float = 4.5) -> dict[str, Any]:
    """Ottieni terremoti recenti."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
            )
            data = resp.json()
            features = data.get("features", [])[:10]

            quakes = []
            for f in features:
                props = f.get("properties", {})
                quakes.append(
                    {
                        "magnitude": props.get("mag"),
                        "location": props.get("place"),
                        "time": props.get("time"),
                        "url": props.get("url"),
                    }
                )

            return {"earthquakes": quakes, "count": len(quakes), "source": "USGS"}
    except Exception as e:
        return {"error": str(e)}


async def nager_holidays(country: str = "IT", year: int = 2026) -> dict[str, Any]:
    """Ottieni festività nazionali."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(f"https://date.nager.at/api/v3/publicholidays/{year}/{country}")
            holidays = resp.json()[:10]
            return {
                "holidays": [{"date": h.get("date"), "name": h.get("localName")} for h in holidays],
                "country": country,
                "year": year,
                "source": "Nager.Date",
            }
    except Exception as e:
        return {"error": str(e)}


async def openmeteo_forecast(city: str = "Rome", days: int = 7) -> dict[str, Any]:
    """Ottieni previsioni meteo per i prossimi N giorni.

    Args:
        city: Nome città
        days: Numero giorni forecast (1-16)

    Returns:
        dict con previsioni giornaliere
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Geocoding
            # SOTA 2026 Resilience: remove country codes appended by LLM
            city_search = city.split(",")[0].strip()
            geo_resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city_search, "count": 1},
            )
            geo_data = geo_resp.json()
            results = geo_data.get("results", [])
            if not results:
                return {"error": f"City not found: {city}"}

            lat, lon = results[0]["latitude"], results[0]["longitude"]
            city_name = results[0].get("name", city)

            # Forecast
            weather_resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
                    "forecast_days": min(days, 16),
                    "timezone": "auto",
                },
                headers={"User-Agent": USER_AGENT},
            )
            data = weather_resp.json()
            daily = data.get("daily", {})

            forecasts = []
            dates = daily.get("time", [])
            for i, date in enumerate(dates):
                forecasts.append(
                    {
                        "date": date,
                        "temp_max": daily.get("temperature_2m_max", [])[i]
                        if i < len(daily.get("temperature_2m_max", []))
                        else None,
                        "temp_min": daily.get("temperature_2m_min", [])[i]
                        if i < len(daily.get("temperature_2m_min", []))
                        else None,
                        "precipitation_mm": daily.get("precipitation_sum", [])[i]
                        if i < len(daily.get("precipitation_sum", []))
                        else None,
                        "weather_code": daily.get("weather_code", [])[i]
                        if i < len(daily.get("weather_code", []))
                        else None,
                    }
                )

            return {
                "city": city_name,
                "forecasts": forecasts,
                "days": len(forecasts),
                "source": "Open-Meteo",
            }
    except Exception as e:
        logger.error("openmeteo_forecast_error", error=str(e))
        return {"error": str(e)}


async def openmeteo_historical(
    city: str = "Rome",
    start_date: str = "2024-01-01",
    end_date: str = "2024-01-31",
) -> dict[str, Any]:
    """Ottieni dati meteo storici (fino a 80 anni di archivio).

    Args:
        city: Nome città
        start_date: Data inizio (YYYY-MM-DD)
        end_date: Data fine (YYYY-MM-DD)

    Returns:
        dict con dati storici giornalieri
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Geocoding
            # SOTA 2026 Resilience: remove country codes appended by LLM
            city_search = city.split(",")[0].strip()
            geo_resp = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city_search, "count": 1},
            )
            geo_data = geo_resp.json()
            results = geo_data.get("results", [])
            if not results:
                return {"error": f"City not found: {city}"}

            lat, lon = results[0]["latitude"], results[0]["longitude"]
            city_name = results[0].get("name", city)

            # Historical Archive API
            weather_resp = await client.get(
                "https://archive-api.open-meteo.com/v1/archive",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "start_date": start_date,
                    "end_date": end_date,
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
                    "timezone": "auto",
                },
                headers={"User-Agent": USER_AGENT},
            )
            data = weather_resp.json()
            daily = data.get("daily", {})

            historical = []
            dates = daily.get("time", [])
            for i, date in enumerate(dates):
                historical.append(
                    {
                        "date": date,
                        "temp_max": daily.get("temperature_2m_max", [])[i]
                        if i < len(daily.get("temperature_2m_max", []))
                        else None,
                        "temp_min": daily.get("temperature_2m_min", [])[i]
                        if i < len(daily.get("temperature_2m_min", []))
                        else None,
                        "precipitation_mm": daily.get("precipitation_sum", [])[i]
                        if i < len(daily.get("precipitation_sum", []))
                        else None,
                    }
                )

            return {
                "city": city_name,
                "period": f"{start_date} to {end_date}",
                "data": historical,
                "days": len(historical),
                "source": "Open-Meteo Archive",
            }
    except Exception as e:
        logger.error("openmeteo_historical_error", error=str(e))
        return {"error": str(e)}


AVAILABLE_TOOLS = {
    "openmeteo_weather": openmeteo_weather,
    "openmeteo_forecast": openmeteo_forecast,
    "openmeteo_historical": openmeteo_historical,
    "usgs_earthquakes": usgs_earthquakes,
    "nager_holidays": nager_holidays,
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool geo per nome, filtrando parametri non accettati."""
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {"error": f"Unknown geo tool: {tool_name}"}

    tool_func = AVAILABLE_TOOLS[tool_name]
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
    """Get tool definitions for ToolCallingEngine auto-discovery."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        ToolDefinition(
            name="openmeteo_weather",
            description="Get current weather conditions for any city worldwide. Returns temperature, humidity, wind speed, and weather code in real-time. Use when user asks 'what's the weather in X', 'is it raining in Y', 'temperature in Z', or any current weather query.",
            parameters={
                "city": ToolParameter(
                    type="string",
                    description="City name ONLY, without country codes or commas (e.g., 'Rome', NOT 'Rome, IT')",
                    required=True,
                ),
            },
            domain="geo_weather",
            category="weather",
        ),
        ToolDefinition(
            name="openmeteo_forecast",
            description="Get weather forecast for the next N days for any city. Returns daily high/low temperatures, precipitation probability, and weather conditions. Use when user asks 'will it rain tomorrow', 'weather forecast for next week', 'what's the weather going to be like'.",
            parameters={
                "city": ToolParameter(
                    type="string",
                    description="City name ONLY, without country codes or commas (e.g., 'Rome', NOT 'London, UK')",
                    required=True,
                ),
                "days": ToolParameter(
                    type="integer",
                    description="Number of forecast days (1-16, default 7)",
                    required=False,
                    default="7",
                ),
            },
            domain="geo_weather",
            category="weather",
        ),
        ToolDefinition(
            name="openmeteo_historical",
            description="Get historical weather data for a city over a specific date range. Access up to 80 years of weather archive. Use when user asks 'what was the weather on X date', 'historical temperature data', 'weather last month', or for climate analysis.",
            parameters={
                "city": ToolParameter(
                    type="string",
                    description="City name ONLY, without country codes or commas (e.g., 'Rome', NOT 'Berlin, DE')",
                    required=True,
                ),
                "start_date": ToolParameter(
                    type="string",
                    description="Start date in YYYY-MM-DD format (e.g., '2024-01-01')",
                    required=True,
                ),
                "end_date": ToolParameter(
                    type="string",
                    description="End date in YYYY-MM-DD format (e.g., '2024-01-31')",
                    required=True,
                ),
            },
            domain="geo_weather",
            category="weather",
        ),
        ToolDefinition(
            name="usgs_earthquakes",
            description="Get recent earthquake data worldwide from the U.S. Geological Survey. Returns magnitude, location, and timestamp for seismic events. Use when user asks about earthquakes, seismic activity, 'were there any earthquakes', or tremors.",
            parameters={
                "days": ToolParameter(
                    type="integer",
                    description="Number of days to look back (default 7)",
                    required=False,
                    default="7",
                ),
                "min_magnitude": ToolParameter(
                    type="number",
                    description="Minimum earthquake magnitude to include (e.g., 4.5 for significant quakes)",
                    required=False,
                    default="4.5",
                ),
            },
            domain="geo_weather",
            category="geology",
        ),
        ToolDefinition(
            name="nager_holidays",
            description="Get public holidays and national days off for any country and year. Use when user asks 'when is the next holiday', 'public holidays in Italy', 'is tomorrow a holiday', or bank holidays.",
            parameters={
                "country": ToolParameter(
                    type="string",
                    description="ISO 3166-1 alpha-2 country code (e.g., 'IT' Italy, 'US' USA, 'DE' Germany, 'FR' France)",
                    required=True,
                ),
                "year": ToolParameter(
                    type="integer",
                    description="Year for holidays (e.g., 2024, 2025)",
                    required=False,
                    default="2026",
                ),
            },
            domain="geo_weather",
            category="calendar",
        ),
    ]


def get_executors() -> dict:
    """Get executor functions for ToolCallingEngine."""
    return {
        "openmeteo_weather": openmeteo_weather,
        "openmeteo_forecast": openmeteo_forecast,
        "openmeteo_historical": openmeteo_historical,
        "usgs_earthquakes": usgs_earthquakes,
        "nager_holidays": nager_holidays,
    }
