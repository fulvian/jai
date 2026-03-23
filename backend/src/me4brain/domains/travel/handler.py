"""Travel Domain Handler."""

from typing import Any

import structlog

from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
)

logger = structlog.get_logger(__name__)


class TravelHandler(DomainHandler):
    """Handler per Voli e Aeroporti."""

    HANDLED_SERVICES = frozenset({"OpenSkyService", "AviationStackService"})

    TRAVEL_KEYWORDS = frozenset(
        {
            "volo",
            "voli",
            "aereo",
            "aeroporto",
            "partenza",
            "arrivo",
            "flight",
            "airport",
            "decollo",
            "atterraggio",
            "compagnia",
            "airline",
            "tracking",
            "live",
            "rotta",
            # Hotel & Accommodation
            "hotel",
            "albergo",
            "alloggio",
            "prenotazione",
            "booking",
            "accommodation",
            "stelle",
            "star",
            # Restaurants
            "ristorante",
            "restaurant",
            "cena",
            "dinner",
            "pranzo",
            "lunch",
            "cucina",
            "cuisine",
            "michelin",
            "stellato",
        }
    )

    @property
    def domain_name(self) -> str:
        return "travel"

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            # Flight Tracking (Real-time)
            DomainCapability(
                name="flight_tracking",
                description="Tracking voli live (OpenSky)",
                required_params=[],
                optional_params=["icao24", "airport"],
            ),
            DomainCapability(
                name="flight_info",
                description="Info voli per codice (AviationStack)",
                required_params=["flight_iata"],
            ),
            # Flight Search (Commercial)
            DomainCapability(
                name="flight_search",
                description="Ricerca voli commerciali con prezzi (Amadeus)",
                required_params=["origin", "destination", "date"],
                optional_params=["return_date", "adults", "max_results"],
            ),
            DomainCapability(
                name="airport_search",
                description="Ricerca aeroporti per nome o codice (Amadeus)",
                required_params=["keyword"],
                optional_params=[],
            ),
            # Accommodation
            DomainCapability(
                name="hotel_search",
                description="Ricerca hotel per città (Google Places)",
                required_params=["city"],
                optional_params=["stars", "max_price", "area"],
            ),
            # Dining
            DomainCapability(
                name="restaurant_search",
                description="Ricerca ristoranti per città (Google Places)",
                required_params=["city"],
                optional_params=["cuisine", "rating_min", "price_level"],
            ),
        ]

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.REAL_TIME

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        """Check if this handler can process the query."""
        query_lower = query.lower()
        matches = sum(1 for kw in self.TRAVEL_KEYWORDS if kw in query_lower)
        if matches >= 2:
            return 0.9
        elif matches == 1:
            return 0.7
        return 0.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        import re

        from .tools.travel_api import execute_tool

        query_lower = query.lower()

        # =====================================================================
        # FLIGHT SEARCH (Amadeus) - Ricerca voli commerciali con prezzi
        # =====================================================================
        if any(
            kw in query_lower
            for kw in ["cerca voli", "find flights", "search flights", "voli da", "flights from"]
        ):
            # Extract origin and destination airports
            airport_pattern = r"\b([A-Z]{3})\b"
            airports = re.findall(airport_pattern, query.upper())

            if len(airports) >= 2:
                origin, destination = airports[0], airports[1]

                # Extract date (simple pattern: YYYY-MM-DD or "prossimo venerdì")
                date_pattern = r"(\d{4}-\d{2}-\d{2})"
                dates = re.findall(date_pattern, query)
                date = dates[0] if dates else None

                if date:
                    data = await execute_tool(
                        "amadeus_search_flights",
                        {
                            "origin": origin,
                            "destination": destination,
                            "date": date,
                        },
                    )
                    return [
                        DomainExecutionResult(
                            success=not data.get("error"),
                            domain=self.domain_name,
                            tool_name="amadeus_search_flights",
                            data=data if not data.get("error") else {},
                            error=data.get("error"),
                        )
                    ]

        # =====================================================================
        # AIRPORT SEARCH (Amadeus) - Ricerca aeroporti
        # =====================================================================
        if any(kw in query_lower for kw in ["aeroporto", "airport", "codice iata"]):
            # Extract city/airport name
            city_match = re.search(
                r"(?:aeroporto|airport|di|in)\s+([A-Za-z\s]+?)(?:\?|$|,)", query, re.IGNORECASE
            )
            if city_match:
                keyword = city_match.group(1).strip()
                data = await execute_tool("amadeus_airport_search", {"keyword": keyword})
                return [
                    DomainExecutionResult(
                        success=not data.get("error"),
                        domain=self.domain_name,
                        tool_name="amadeus_airport_search",
                        data=data if not data.get("error") else {},
                        error=data.get("error"),
                    )
                ]

        # =====================================================================
        # HOTEL SEARCH (Google Places) - Ricerca hotel
        # =====================================================================
        if any(
            kw in query_lower for kw in ["hotel", "albergo", "alloggio", "prenotazione", "booking"]
        ):
            # Extract city
            city_match = re.search(
                r"(?:hotel|albergo|alloggio|a|in)\s+([A-Za-z\s]+?)(?:\?|$|,)", query, re.IGNORECASE
            )
            if city_match:
                city = city_match.group(1).strip()

                # Extract optional parameters
                stars = None
                if "4 stelle" in query_lower or "4-star" in query_lower:
                    stars = 4
                elif "5 stelle" in query_lower or "5-star" in query_lower:
                    stars = 5

                max_price = None
                price_match = re.search(r"(\d+)\s*€", query)
                if price_match:
                    max_price = float(price_match.group(1))

                data = await execute_tool(
                    "google_places_hotels",
                    {
                        "city": city,
                        "stars": stars,
                        "max_price": max_price,
                    },
                )
                return [
                    DomainExecutionResult(
                        success=not data.get("error"),
                        domain=self.domain_name,
                        tool_name="google_places_hotels",
                        data=data if not data.get("error") else {},
                        error=data.get("error"),
                    )
                ]

        # =====================================================================
        # RESTAURANT SEARCH (Google Places) - Ricerca ristoranti
        # =====================================================================
        if any(
            kw in query_lower
            for kw in ["ristorante", "restaurant", "cena", "dinner", "pranzo", "lunch"]
        ):
            # Extract city
            city_match = re.search(r"(?:a|in|di)\s+([A-Za-z\s]+?)(?:\?|$|,)", query, re.IGNORECASE)
            if city_match:
                city = city_match.group(1).strip()

                # Extract optional parameters
                cuisine = None
                if "catalano" in query_lower or "catalan" in query_lower:
                    cuisine = "Catalan"
                elif "fusion" in query_lower:
                    cuisine = "Fusion"
                elif "stellato" in query_lower or "michelin" in query_lower:
                    cuisine = "Fine Dining"

                data = await execute_tool(
                    "google_places_restaurants",
                    {
                        "city": city,
                        "cuisine": cuisine,
                    },
                )
                return [
                    DomainExecutionResult(
                        success=not data.get("error"),
                        domain=self.domain_name,
                        tool_name="google_places_restaurants",
                        data=data if not data.get("error") else {},
                        error=data.get("error"),
                    )
                ]

        # =====================================================================
        # DEFAULT: Flight Tracking (OpenSky) - Tracking voli live
        # =====================================================================
        # Check for specific flight code
        flight_match = re.search(r"[A-Z]{2}\d{3,4}", query.upper())
        if flight_match:
            data = await execute_tool("aviationstack_flight", {"flight_iata": flight_match.group()})
            return [
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="aviationstack_flight",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            ]

        # Check for airport
        airport_match = re.search(r"[A-Z]{4}", query.upper())
        if airport_match and any(kw in query_lower for kw in ["arrivi", "arrival", "aeroporto"]):
            data = await execute_tool("opensky_arrivals", {"airport": airport_match.group()})
            return [
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name="opensky_arrivals",
                    data=data if not data.get("error") else {},
                    error=data.get("error"),
                )
            ]

        # Default: live flights
        data = await execute_tool("opensky_flights_live", {})
        return [
            DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name="opensky_flights_live",
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )
        ]
