"""Geo & Weather Domain Package."""

from me4brain.domains.geo_weather.handler import GeoWeatherHandler


def get_handler() -> GeoWeatherHandler:
    return GeoWeatherHandler()


__all__ = ["GeoWeatherHandler", "get_handler"]
