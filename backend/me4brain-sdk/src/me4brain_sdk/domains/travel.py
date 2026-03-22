"""Travel Domain - Flight tracking, hotel search."""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field

from me4brain_sdk.domains._base import BaseDomain


class Flight(BaseModel):
    """Flight information."""

    icao24: str
    callsign: str | None = None
    origin_country: str
    longitude: float | None = None
    latitude: float | None = None
    altitude: float | None = None
    velocity: float | None = None
    on_ground: bool = False


class Airport(BaseModel):
    """Airport information."""

    icao: str
    name: str
    city: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class TravelDomain(BaseDomain):
    """Travel domain - flight tracking, airports, travel info.

    Example:
        # Track flights
        flights = await client.domains.travel.flights_in_area(
            lat_min=45.0, lat_max=46.5, lon_min=7.0, lon_max=12.0
        )

        # Search airports
        airports = await client.domains.travel.airport_search("Milan")
    """

    @property
    def domain_name(self) -> str:
        return "travel"

    async def flights_in_area(
        self,
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
    ) -> list[Flight]:
        """Get flights in a geographic area (OpenSky).

        Args:
            lat_min: Minimum latitude
            lat_max: Maximum latitude
            lon_min: Minimum longitude
            lon_max: Maximum longitude

        Returns:
            List of flights in the area
        """
        result = await self._execute_tool(
            "opensky_flights",
            {
                "lat_min": lat_min,
                "lat_max": lat_max,
                "lon_min": lon_min,
                "lon_max": lon_max,
            },
        )
        flights = result.get("result", {}).get("flights", [])
        return [Flight.model_validate(f) for f in flights]

    async def flight_by_icao(self, icao24: str) -> Flight:
        """Get flight by ICAO24 address.

        Args:
            icao24: Aircraft ICAO24 address

        Returns:
            Flight details
        """
        result = await self._execute_tool("opensky_flight", {"icao24": icao24})
        return Flight.model_validate(result.get("result", {}))

    async def airport_search(self, query: str) -> list[Airport]:
        """Search airports.

        Args:
            query: Airport name or city

        Returns:
            List of matching airports
        """
        result = await self._execute_tool("airport_search", {"query": query})
        airports = result.get("result", {}).get("airports", [])
        return [Airport.model_validate(a) for a in airports]

    async def airport_info(self, icao: str) -> Airport:
        """Get airport info by ICAO code.

        Args:
            icao: Airport ICAO code

        Returns:
            Airport information
        """
        result = await self._execute_tool("airport_info", {"icao": icao})
        return Airport.model_validate(result.get("result", {}))
