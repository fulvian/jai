from __future__ import annotations

"""Geo/Weather Domain - Weather forecasts, geocoding, location services."""

from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class WeatherCurrent(BaseModel):
    """Current weather conditions."""

    location: str
    temperature: float
    feels_like: float
    humidity: int
    description: str
    icon: str | None = None
    wind_speed: float = 0.0
    wind_direction: str | None = None
    pressure: float | None = None
    visibility: float | None = None
    uv_index: float | None = None


class WeatherForecast(BaseModel):
    """Weather forecast for a day."""

    date: str
    temp_high: float
    temp_low: float
    description: str
    icon: str | None = None
    precipitation_chance: float = 0.0
    humidity: int = 0


class GeoLocation(BaseModel):
    """Geographic location."""

    name: str
    country: str
    lat: float
    lon: float
    state: str | None = None
    timezone: str | None = None


class GeoWeatherDomain(BaseDomain):
    """Geo/Weather domain - weather, geocoding, location services.

    Example:
        # Get current weather
        weather = await client.domains.geo_weather.current("Milan, IT")

        # Get forecast
        forecast = await client.domains.geo_weather.forecast("New York", days=5)

        # Geocode location
        location = await client.domains.geo_weather.geocode("Paris, France")
    """

    @property
    def domain_name(self) -> str:
        return "geo_weather"

    async def current(self, location: str) -> WeatherCurrent:
        """Get current weather for a location.

        Args:
            location: Location string (city, country)

        Returns:
            Current weather conditions
        """
        result = await self._execute_tool(
            "weather_current",
            {"location": location},
        )
        return WeatherCurrent.model_validate(result.get("result", {}))

    async def forecast(
        self,
        location: str,
        days: int = 5,
    ) -> list[WeatherForecast]:
        """Get weather forecast.

        Args:
            location: Location string
            days: Number of days (1-14)

        Returns:
            List of daily forecasts
        """
        result = await self._execute_tool(
            "weather_forecast",
            {"location": location, "days": days},
        )
        forecasts = result.get("result", {}).get("forecast", [])
        return [WeatherForecast.model_validate(f) for f in forecasts]

    async def geocode(self, query: str) -> list[GeoLocation]:
        """Geocode a location string.

        Args:
            query: Location to geocode

        Returns:
            List of matching locations with coordinates
        """
        result = await self._execute_tool(
            "geocode",
            {"query": query},
        )
        locations = result.get("result", {}).get("locations", [])
        return [GeoLocation.model_validate(loc) for loc in locations]

    async def reverse_geocode(
        self,
        lat: float,
        lon: float,
    ) -> GeoLocation:
        """Reverse geocode coordinates.

        Args:
            lat: Latitude
            lon: Longitude

        Returns:
            Location information
        """
        result = await self._execute_tool(
            "reverse_geocode",
            {"lat": lat, "lon": lon},
        )
        return GeoLocation.model_validate(result.get("result", {}))

    async def air_quality(self, location: str) -> dict[str, Any]:
        """Get air quality index.

        Args:
            location: Location string

        Returns:
            Air quality data with AQI
        """
        result = await self._execute_tool(
            "air_quality",
            {"location": location},
        )
        return result.get("result", {})
