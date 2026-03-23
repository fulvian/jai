"""Travel API Tools - OpenSky Network, AviationStack, Amadeus.

- OpenSky Network: 100% Gratuito, tracking voli live
- AviationStack: 100 req/mese free tier (deprecated)
- Amadeus Self-Service: Ricerca voli con prezzi (Free Tier Permanente)
"""

import os
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

AVIATIONSTACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY")
TIMEOUT = 20.0


# =============================================================================
# OpenSky Network - Tracking Voli Live (100% Gratuito, Illimitato)
# =============================================================================


async def opensky_flights_live(
    bounds: tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
    """Ottieni voli attualmente in volo.

    Args:
        bounds: (lat_min, lat_max, lon_min, lon_max) per area geografica

    Returns:
        dict con voli live
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            params = {}
            if bounds:
                params["lamin"] = bounds[0]
                params["lamax"] = bounds[1]
                params["lomin"] = bounds[2]
                params["lomax"] = bounds[3]

            resp = await client.get(
                "https://opensky-network.org/api/states/all",
                params=params if params else None,
            )
            resp.raise_for_status()
            data = resp.json()

            flights = []
            for state in (data.get("states") or [])[:50]:  # Limita a 50
                flights.append(
                    {
                        "icao24": state[0],
                        "callsign": (state[1] or "").strip(),
                        "origin_country": state[2],
                        "longitude": state[5],
                        "latitude": state[6],
                        "altitude": state[7],  # meters
                        "velocity": state[9],  # m/s
                        "heading": state[10],
                        "on_ground": state[8],
                    }
                )

            return {
                "timestamp": data.get("time"),
                "flights": flights,
                "count": len(flights),
                "source": "OpenSky Network",
            }

    except Exception as e:
        logger.error("opensky_flights_live_error", error=str(e))
        return {"error": str(e), "source": "OpenSky Network"}


async def opensky_flight_track(icao24: str) -> dict[str, Any]:
    """Traccia storico di un volo specifico.

    NOTE: This endpoint may be deprecated/unreliable. Use opensky_flights_live instead.

    Args:
        icao24: Codice ICAO dell'aereo

    Returns:
        dict con traccia volo
    """
    try:
        import time

        end_time = int(time.time())
        begin_time = end_time - 3600  # Ultima ora

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://opensky-network.org/api/tracks/all",
                params={"icao24": icao24.lower(), "time": 0},
            )

            # Handle 404 gracefully - endpoint may be deprecated
            if resp.status_code == 404:
                return {
                    "error": "Track endpoint may be deprecated. Use opensky_flights_live for current positions.",
                    "hint": "Try opensky_flights_live to get current aircraft positions",
                    "source": "OpenSky Network",
                }

            resp.raise_for_status()
            data = resp.json()

            if not data:
                return {
                    "error": f"Nessun track per {icao24}",
                    "source": "OpenSky Network",
                }

            path = []
            for p in data.get("path", []):
                path.append(
                    {
                        "time": p[0],
                        "latitude": p[1],
                        "longitude": p[2],
                        "altitude": p[3],
                        "heading": p[4],
                        "on_ground": p[5],
                    }
                )

            return {
                "icao24": data.get("icao24"),
                "callsign": data.get("callsign"),
                "start_time": data.get("startTime"),
                "end_time": data.get("endTime"),
                "path": path,
                "source": "OpenSky Network",
            }

    except Exception as e:
        logger.error("opensky_flight_track_error", error=str(e))
        return {"error": str(e), "source": "OpenSky Network"}


async def opensky_arrivals(airport: str, hours: int = 12) -> dict[str, Any]:
    """Arrivi a un aeroporto.

    NOTE: This endpoint may be deprecated/unreliable. Use opensky_flights_live with bounds instead.

    Args:
        airport: Codice ICAO aeroporto (es. LIRF per Fiumicino)
        hours: Ore indietro da cercare (max 24)

    Returns:
        dict con arrivi
    """
    try:
        import time

        end_time = int(time.time())
        begin_time = end_time - (min(hours, 24) * 3600)

        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://opensky-network.org/api/flights/arrival",
                params={
                    "airport": airport.upper(),
                    "begin": begin_time,
                    "end": end_time,
                },
            )

            # Handle 404 gracefully - endpoint may be deprecated
            if resp.status_code == 404:
                return {
                    "error": "Arrivals endpoint may be deprecated. Use opensky_flights_live for current flights.",
                    "hint": "Try opensky_flights_live with geographic bounds to see flights near the airport",
                    "source": "OpenSky Network",
                }

            resp.raise_for_status()
            data = resp.json()

            arrivals = []
            for f in (data or [])[:20]:
                arrivals.append(
                    {
                        "icao24": f.get("icao24"),
                        "callsign": (f.get("callsign") or "").strip(),
                        "departure_airport": f.get("estDepartureAirport"),
                        "arrival_airport": f.get("estArrivalAirport"),
                        "first_seen": f.get("firstSeen"),
                        "last_seen": f.get("lastSeen"),
                    }
                )

            return {
                "airport": airport,
                "arrivals": arrivals,
                "count": len(arrivals),
                "source": "OpenSky Network",
            }

    except Exception as e:
        logger.error("opensky_arrivals_error", error=str(e))
        return {"error": str(e), "source": "OpenSky Network"}


# =============================================================================
# AviationStack - DEPRECATED (Pagamento richiesto)
# Usare invece: adsb_aircraft_by_location, adsb_aircraft_by_callsign
# =============================================================================


async def aviationstack_flight(flight_iata: str) -> dict[str, Any]:
    """[DEPRECATED] Info volo per codice IATA.

    DEPRECATO: Usare adsb_aircraft_by_callsign invece.

    Args:
        flight_iata: Codice volo (es. AZ123)

    Returns:
        dict con info volo
    """
    return {
        "error": "DEPRECATED: AviationStack richiede pagamento. Usa adsb_aircraft_by_callsign invece.",
        "alternative": "adsb_aircraft_by_callsign",
        "source": "AviationStack",
    }


async def aviationstack_airports(search: str) -> dict[str, Any]:
    """[DEPRECATED] Cerca aeroporti.

    DEPRECATO: Usare adsb_aircraft_by_location invece.

    Args:
        search: Nome città o codice IATA

    Returns:
        dict con aeroporti
    """
    return {
        "error": "DEPRECATED: AviationStack richiede pagamento. Usa adsb_aircraft_by_location invece.",
        "alternative": "adsb_aircraft_by_location",
        "source": "AviationStack",
    }


# =============================================================================
# Amadeus Self-Service - Ricerca Voli con Prezzi (Free Tier Permanente)
# https://developers.amadeus.com - OAuth2 via SDK
# =============================================================================

AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID")
AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET")
AMADEUS_ENV = os.getenv("AMADEUS_ENV", "test")  # 'test' or 'production'

# Lazy initialization of Amadeus client
_amadeus_client = None


def _get_amadeus_client():
    """Get or create Amadeus client with lazy initialization."""
    global _amadeus_client
    if _amadeus_client is None:
        if not AMADEUS_CLIENT_ID or not AMADEUS_CLIENT_SECRET:
            return None
        try:
            from amadeus import Client

            _amadeus_client = Client(
                client_id=AMADEUS_CLIENT_ID,
                client_secret=AMADEUS_CLIENT_SECRET,
                hostname=AMADEUS_ENV,  # 'test' or 'production'
            )
        except ImportError:
            logger.error("amadeus_sdk_not_installed", hint="pip install amadeus")
            return None
        except Exception as e:
            logger.error("amadeus_client_init_error", error=str(e))
            return None
    return _amadeus_client


async def amadeus_search_flights(
    origin: str,
    destination: str,
    date: str,
    return_date: str | None = None,
    adults: int = 1,
    max_results: int = 10,
) -> dict[str, Any]:
    """Cerca voli con prezzi tra due aeroporti usando Amadeus.

    Args:
        origin: Codice IATA aeroporto partenza (es. CTA, FCO, MXP)
        destination: Codice IATA aeroporto arrivo (es. FCO, CDG, JFK)
        date: Data partenza formato YYYY-MM-DD
        return_date: Data ritorno formato YYYY-MM-DD (opzionale, per andata/ritorno)
        adults: Numero passeggeri adulti (default 1)
        max_results: Numero massimo risultati (default 10)

    Returns:
        dict con voli, prezzi e dettagli compagnie aeree
    """
    client = _get_amadeus_client()
    if client is None:
        return {
            "error": "Amadeus non configurato",
            "hint": "Aggiungi AMADEUS_CLIENT_ID e AMADEUS_CLIENT_SECRET al file .env",
            "source": "Amadeus",
        }

    try:
        import asyncio

        # Amadeus SDK is synchronous, run in executor
        def _search():
            params = {
                "originLocationCode": origin.upper(),
                "destinationLocationCode": destination.upper(),
                "departureDate": date,
                "adults": adults,
                "max": max_results,
            }
            if return_date:
                params["returnDate"] = return_date

            return client.shopping.flight_offers_search.get(**params)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _search)

        flights = []
        for offer in response.data or []:
            # Extract price
            price_info = offer.get("price", {})

            # Extract itinerary info
            itineraries = offer.get("itineraries", [])
            outbound = itineraries[0] if itineraries else {}
            inbound = itineraries[1] if len(itineraries) > 1 else None

            # Get segments for departure/arrival times
            outbound_segments = outbound.get("segments", [])
            first_segment = outbound_segments[0] if outbound_segments else {}
            last_segment = outbound_segments[-1] if outbound_segments else {}

            flight_info = {
                "price": price_info.get("total"),
                "currency": price_info.get("currency", "EUR"),
                "origin": first_segment.get("departure", {}).get("iataCode"),
                "destination": last_segment.get("arrival", {}).get("iataCode"),
                "departure": first_segment.get("departure", {}).get("at"),
                "arrival": last_segment.get("arrival", {}).get("at"),
                "duration": outbound.get("duration"),  # ISO 8601 duration
                "stops": len(outbound_segments) - 1,
                "carriers": list(set(seg.get("carrierCode", "") for seg in outbound_segments)),
                "flight_numbers": [
                    f"{seg.get('carrierCode', '')}{seg.get('number', '')}"
                    for seg in outbound_segments
                ],
            }

            if inbound:
                inbound_segments = inbound.get("segments", [])
                flight_info["return_departure"] = (
                    inbound_segments[0].get("departure", {}).get("at") if inbound_segments else None
                )
                flight_info["return_arrival"] = (
                    inbound_segments[-1].get("arrival", {}).get("at") if inbound_segments else None
                )
                flight_info["return_duration"] = inbound.get("duration")
                flight_info["return_stops"] = len(inbound_segments) - 1

            flights.append(flight_info)

        return {
            "route": f"{origin.upper()}-{destination.upper()}",
            "date": date,
            "return_date": return_date,
            "adults": adults,
            "flights": flights,
            "count": len(flights),
            "source": "Amadeus",
        }

    except Exception as e:
        error_msg = str(e)
        # Handle Amadeus ResponseError
        if hasattr(e, "response") and hasattr(e.response, "result"):
            error_detail = e.response.result.get("errors", [{}])[0]
            error_msg = error_detail.get("detail", str(e))

        logger.error("amadeus_search_flights_error", error=error_msg)
        return {"error": error_msg, "source": "Amadeus"}


async def amadeus_airport_search(
    keyword: str,
) -> dict[str, Any]:
    """Cerca aeroporti per nome o codice.

    Args:
        keyword: Nome città o codice IATA (es. "Rome", "FCO", "Milano")

    Returns:
        dict con aeroporti trovati
    """
    client = _get_amadeus_client()
    if client is None:
        return {
            "error": "Amadeus non configurato",
            "hint": "Aggiungi AMADEUS_CLIENT_ID e AMADEUS_CLIENT_SECRET al file .env",
            "source": "Amadeus",
        }

    try:
        import asyncio

        def _search():
            return client.reference_data.locations.get(
                keyword=keyword,
                subType="AIRPORT,CITY",
            )

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _search)

        airports = []
        for loc in response.data or []:
            airports.append(
                {
                    "iata_code": loc.get("iataCode"),
                    "name": loc.get("name"),
                    "city": loc.get("address", {}).get("cityName"),
                    "country": loc.get("address", {}).get("countryName"),
                    "type": loc.get("subType"),
                }
            )

        return {
            "keyword": keyword,
            "airports": airports,
            "count": len(airports),
            "source": "Amadeus",
        }

    except Exception as e:
        logger.error("amadeus_airport_search_error", error=str(e))
        return {"error": str(e), "source": "Amadeus"}


async def amadeus_confirm_price(
    flight_offer: dict,
) -> dict[str, Any]:
    """Conferma il prezzo di un volo prima della prenotazione.

    Args:
        flight_offer: Oggetto flight offer restituito da amadeus_search_flights
                      (uno degli elementi della lista 'flights')

    Returns:
        dict con prezzo confermato e dettagli aggiornati
    """
    client = _get_amadeus_client()
    if client is None:
        return {
            "error": "Amadeus non configurato",
            "hint": "Aggiungi AMADEUS_CLIENT_ID e AMADEUS_CLIENT_SECRET al file .env",
            "source": "Amadeus",
        }

    try:
        import asyncio

        def _confirm():
            return client.shopping.flight_offers.pricing.post(flight_offer)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _confirm)

        data = response.data
        if not data:
            return {"error": "Nessun prezzo confermato", "source": "Amadeus"}

        # Extract confirmed pricing
        price_info = data.get("flightOffers", [{}])[0].get("price", {})

        return {
            "confirmed": True,
            "price": price_info.get("total"),
            "currency": price_info.get("currency"),
            "base_price": price_info.get("base"),
            "fees": price_info.get("fees", []),
            "price_per_traveler": data.get("flightOffers", [{}])[0].get("travelerPricings", []),
            "source": "Amadeus",
        }

    except Exception as e:
        error_msg = str(e)
        if hasattr(e, "response") and hasattr(e.response, "result"):
            error_detail = e.response.result.get("errors", [{}])[0]
            error_msg = error_detail.get("detail", str(e))
        logger.error("amadeus_confirm_price_error", error=error_msg)
        return {"error": error_msg, "source": "Amadeus"}


async def amadeus_book_flight(
    flight_offer: dict,
    traveler_first_name: str,
    traveler_last_name: str,
    traveler_date_of_birth: str,
    traveler_gender: str,
    traveler_email: str,
    traveler_phone: str,
    traveler_phone_country_code: str = "39",
) -> dict[str, Any]:
    """Prenota un volo con Amadeus.

    ATTENZIONE: Questa è una prenotazione REALE in ambiente test.
    In produzione, questa operazione ha conseguenze finanziarie.

    Args:
        flight_offer: Oggetto flight offer da amadeus_search_flights (raw response)
        traveler_first_name: Nome del passeggero
        traveler_last_name: Cognome del passeggero
        traveler_date_of_birth: Data di nascita (YYYY-MM-DD)
        traveler_gender: 'MALE' o 'FEMALE'
        traveler_email: Email del passeggero
        traveler_phone: Numero telefono (senza prefisso)
        traveler_phone_country_code: Prefisso internazionale (default '39' per Italia)

    Returns:
        dict con conferma prenotazione e codice PNR
    """
    client = _get_amadeus_client()
    if client is None:
        return {
            "error": "Amadeus non configurato",
            "hint": "Aggiungi AMADEUS_CLIENT_ID e AMADEUS_CLIENT_SECRET al file .env",
            "source": "Amadeus",
        }

    try:
        import asyncio

        # Build traveler object
        travelers = [
            {
                "id": "1",
                "dateOfBirth": traveler_date_of_birth,
                "name": {
                    "firstName": traveler_first_name.upper(),
                    "lastName": traveler_last_name.upper(),
                },
                "gender": traveler_gender.upper(),
                "contact": {
                    "emailAddress": traveler_email,
                    "phones": [
                        {
                            "deviceType": "MOBILE",
                            "countryCallingCode": traveler_phone_country_code,
                            "number": traveler_phone,
                        }
                    ],
                },
            }
        ]

        def _book():
            return client.booking.flight_orders.post(flight_offer, travelers)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _book)

        data = response.data
        if not data:
            return {"error": "Prenotazione fallita", "source": "Amadeus"}

        return {
            "success": True,
            "booking_id": data.get("id"),
            "booking_reference": data.get("associatedRecords", [{}])[0].get("reference"),
            "creation_date": data.get("associatedRecords", [{}])[0].get("creationDate"),
            "travelers": [
                {
                    "name": f"{t.get('name', {}).get('firstName')} {t.get('name', {}).get('lastName')}",
                    "id": t.get("id"),
                }
                for t in data.get("travelers", [])
            ],
            "itineraries": data.get("flightOffers", [{}])[0].get("itineraries", []),
            "price": data.get("flightOffers", [{}])[0].get("price", {}),
            "source": "Amadeus",
        }

    except Exception as e:
        error_msg = str(e)
        if hasattr(e, "response") and hasattr(e.response, "result"):
            error_detail = e.response.result.get("errors", [{}])[0]
            error_msg = error_detail.get("detail", str(e))
        logger.error("amadeus_book_flight_error", error=error_msg)
        return {"error": error_msg, "source": "Amadeus"}


# =============================================================================
# ADS-B One - 100% Gratuito, dati non filtrati (include militari/privati)
# https://api.adsb.one - No API key required
# =============================================================================

ADSB_ONE_BASE = "https://api.adsb.one/v2"


async def adsb_aircraft_by_location(
    lat: float,
    lon: float,
    dist_nm: int = 25,
) -> dict[str, Any]:
    """Ottieni aerei vicino a una posizione geografica.

    Args:
        lat: Latitudine
        lon: Longitudine
        dist_nm: Distanza in miglia nautiche (max 250)

    Returns:
        dict con aerei nella zona
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(f"{ADSB_ONE_BASE}/point/{lat}/{lon}/{min(dist_nm, 250)}")
            resp.raise_for_status()
            data = resp.json()

            aircraft = []
            for ac in (data.get("ac") or [])[:50]:
                aircraft.append(
                    {
                        "icao": ac.get("hex"),
                        "callsign": (ac.get("flight") or "").strip(),
                        "registration": ac.get("r"),
                        "aircraft_type": ac.get("t"),
                        "latitude": ac.get("lat"),
                        "longitude": ac.get("lon"),
                        "altitude_ft": ac.get("alt_baro"),
                        "ground_speed_kts": ac.get("gs"),
                        "heading": ac.get("track"),
                        "vertical_rate": ac.get("baro_rate"),
                        "squawk": ac.get("squawk"),
                        "on_ground": ac.get("alt_baro") == "ground",
                    }
                )

            return {
                "location": {"lat": lat, "lon": lon, "radius_nm": dist_nm},
                "aircraft": aircraft,
                "count": len(aircraft),
                "total_in_area": data.get("total", len(aircraft)),
                "source": "ADS-B One",
            }

    except Exception as e:
        logger.error("adsb_aircraft_location_error", error=str(e))
        return {"error": str(e), "source": "ADS-B One"}


async def adsb_aircraft_by_icao(icao: str) -> dict[str, Any]:
    """Ottieni info su un aereo specifico tramite codice ICAO (hex).

    Args:
        icao: Codice ICAO 24-bit hex (es. "A0B1C2")

    Returns:
        dict con info aereo
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(f"{ADSB_ONE_BASE}/hex/{icao.upper()}")
            resp.raise_for_status()
            data = resp.json()

            ac_list = data.get("ac") or []
            if not ac_list:
                return {
                    "error": f"Aircraft {icao} not found or not transmitting",
                    "source": "ADS-B One",
                }

            ac = ac_list[0]
            return {
                "icao": ac.get("hex"),
                "callsign": (ac.get("flight") or "").strip(),
                "registration": ac.get("r"),
                "aircraft_type": ac.get("t"),
                "operator": ac.get("ownOp"),
                "latitude": ac.get("lat"),
                "longitude": ac.get("lon"),
                "altitude_ft": ac.get("alt_baro"),
                "ground_speed_kts": ac.get("gs"),
                "heading": ac.get("track"),
                "vertical_rate_fpm": ac.get("baro_rate"),
                "squawk": ac.get("squawk"),
                "emergency": ac.get("emergency"),
                "category": ac.get("category"),
                "source": "ADS-B One",
            }

    except Exception as e:
        logger.error("adsb_aircraft_icao_error", error=str(e), icao=icao)
        return {"error": str(e), "source": "ADS-B One"}


async def adsb_aircraft_by_callsign(callsign: str) -> dict[str, Any]:
    """Ottieni info su un volo tramite callsign.

    Args:
        callsign: Callsign del volo (es. "UAL123", "RYR456")

    Returns:
        dict con info volo
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(f"{ADSB_ONE_BASE}/callsign/{callsign.upper()}")
            resp.raise_for_status()
            data = resp.json()

            ac_list = data.get("ac") or []
            if not ac_list:
                return {
                    "error": f"Flight {callsign} not found or not in the air",
                    "source": "ADS-B One",
                }

            ac = ac_list[0]
            return {
                "icao": ac.get("hex"),
                "callsign": (ac.get("flight") or "").strip(),
                "registration": ac.get("r"),
                "aircraft_type": ac.get("t"),
                "operator": ac.get("ownOp"),
                "latitude": ac.get("lat"),
                "longitude": ac.get("lon"),
                "altitude_ft": ac.get("alt_baro"),
                "ground_speed_kts": ac.get("gs"),
                "heading": ac.get("track"),
                "origin": ac.get("dep"),
                "destination": ac.get("dest"),
                "source": "ADS-B One",
            }

    except Exception as e:
        logger.error("adsb_aircraft_callsign_error", error=str(e), callsign=callsign)
        return {"error": str(e), "source": "ADS-B One"}


# =============================================================================
# Google Places API - Hotel & Restaurant Search
# https://developers.google.com/maps/documentation/places/web-service/overview
# =============================================================================

GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")


async def google_places_hotels(
    city: str,
    stars: int | None = None,
    max_price: float | None = None,
    area: str | None = None,
) -> dict[str, Any]:
    """Cerca hotel in una città usando Google Places API.

    Args:
        city: Nome della città (es. "Barcellona", "Roma")
        stars: Numero di stelle (3, 4, 5)
        max_price: Prezzo massimo per notte in EUR
        area: Area/zona specifica (es. "Eixample", "Centro")

    Returns:
        dict con hotel trovati
    """
    if not GOOGLE_PLACES_API_KEY:
        return {
            "error": "Google Places non configurato",
            "hint": "Aggiungi GOOGLE_PLACES_API_KEY al file .env",
            "source": "Google Places",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Build search query
            query = f"hotel {city}"
            if area:
                query += f" {area}"
            if stars:
                query += f" {stars} stelle"

            # Search places
            params = {
                "query": query,
                "key": GOOGLE_PLACES_API_KEY,
                "type": "lodging",
            }

            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "OK":
                return {
                    "error": f"Google Places error: {data.get('status')}",
                    "source": "Google Places",
                }

            hotels = []
            for place in (data.get("results") or [])[:10]:
                # Get place details for more info
                place_id = place.get("place_id")
                details_params = {
                    "place_id": place_id,
                    "fields": "name,rating,formatted_address,opening_hours,price_level,photos",
                    "key": GOOGLE_PLACES_API_KEY,
                }

                details_resp = await client.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params=details_params,
                )
                details_resp.raise_for_status()
                details_data = details_resp.json()

                if details_data.get("status") == "OK":
                    place_details = details_data.get("result", {})
                    hotels.append(
                        {
                            "name": place.get("name"),
                            "address": place.get("formatted_address"),
                            "rating": place.get("rating"),
                            "reviews": place.get("user_ratings_total", 0),
                            "price_level": place_details.get("price_level"),
                            "open_now": place_details.get("opening_hours", {}).get("open_now"),
                            "photo_url": f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photo_reference={place.get('photos', [{}])[0].get('photo_reference')}&key={GOOGLE_PLACES_API_KEY}"
                            if place.get("photos")
                            else None,
                        }
                    )

            return {
                "city": city,
                "area": area,
                "stars": stars,
                "max_price": max_price,
                "hotels": hotels,
                "count": len(hotels),
                "source": "Google Places",
            }

    except Exception as e:
        logger.error("google_places_hotels_error", error=str(e))
        return {"error": str(e), "source": "Google Places"}


async def google_places_restaurants(
    city: str,
    cuisine: str | None = None,
    rating_min: float | None = None,
    price_level: int | None = None,
) -> dict[str, Any]:
    """Cerca ristoranti in una città usando Google Places API.

    Args:
        city: Nome della città (es. "Barcellona", "Roma")
        cuisine: Tipo di cucina (es. "Catalan", "Fusion", "Fine Dining")
        rating_min: Valutazione minima (1-5)
        price_level: Livello di prezzo (1-4, dove 1=economico, 4=lusso)

    Returns:
        dict con ristoranti trovati
    """
    if not GOOGLE_PLACES_API_KEY:
        return {
            "error": "Google Places non configurato",
            "hint": "Aggiungi GOOGLE_PLACES_API_KEY al file .env",
            "source": "Google Places",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            # Build search query
            query = f"restaurant {city}"
            if cuisine:
                query += f" {cuisine}"

            # Search places
            params = {
                "query": query,
                "key": GOOGLE_PLACES_API_KEY,
                "type": "restaurant",
            }

            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "OK":
                return {
                    "error": f"Google Places error: {data.get('status')}",
                    "source": "Google Places",
                }

            restaurants = []
            for place in (data.get("results") or [])[:10]:
                rating = place.get("rating", 0)

                # Filter by rating if specified
                if rating_min and rating < rating_min:
                    continue

                # Get place details for more info
                place_id = place.get("place_id")
                details_params = {
                    "place_id": place_id,
                    "fields": "name,rating,formatted_address,opening_hours,price_level,website,formatted_phone_number,photos",
                    "key": GOOGLE_PLACES_API_KEY,
                }

                details_resp = await client.get(
                    "https://maps.googleapis.com/maps/api/place/details/json",
                    params=details_params,
                )
                details_resp.raise_for_status()
                details_data = details_resp.json()

                if details_data.get("status") == "OK":
                    place_details = details_data.get("result", {})
                    rest_price_level = place_details.get("price_level")

                    # Filter by price level if specified
                    if price_level and rest_price_level and rest_price_level > price_level:
                        continue

                    restaurants.append(
                        {
                            "name": place.get("name"),
                            "address": place.get("formatted_address"),
                            "rating": rating,
                            "reviews": place.get("user_ratings_total", 0),
                            "price_level": rest_price_level,
                            "phone": place_details.get("formatted_phone_number"),
                            "website": place_details.get("website"),
                            "open_now": place_details.get("opening_hours", {}).get("open_now"),
                            "photo_url": f"https://maps.googleapis.com/maps/api/place/photo?maxwidth=400&photo_reference={place.get('photos', [{}])[0].get('photo_reference')}&key={GOOGLE_PLACES_API_KEY}"
                            if place.get("photos")
                            else None,
                        }
                    )

            return {
                "city": city,
                "cuisine": cuisine,
                "rating_min": rating_min,
                "price_level": price_level,
                "restaurants": restaurants,
                "count": len(restaurants),
                "source": "Google Places",
            }

    except Exception as e:
        logger.error("google_places_restaurants_error", error=str(e))
        return {"error": str(e), "source": "Google Places"}


# =============================================================================
# Tool Registry
# =============================================================================

AVAILABLE_TOOLS = {
    # OpenSky (Free, Unlimited)
    "opensky_flights_live": opensky_flights_live,
    "opensky_flight_track": opensky_flight_track,
    "opensky_arrivals": opensky_arrivals,
    # AviationStack (100 req/month - deprecated)
    "aviationstack_flight": aviationstack_flight,
    "aviationstack_airports": aviationstack_airports,
    # Amadeus Self-Service (Free Tier Permanente)
    "amadeus_search_flights": amadeus_search_flights,
    "amadeus_airport_search": amadeus_airport_search,
    "amadeus_confirm_price": amadeus_confirm_price,
    "amadeus_book_flight": amadeus_book_flight,
    # ADS-B One (100% Free, no API key)
    "adsb_aircraft_by_location": adsb_aircraft_by_location,
    "adsb_aircraft_by_icao": adsb_aircraft_by_icao,
    "adsb_aircraft_by_callsign": adsb_aircraft_by_callsign,
    # Google Places (Hotel & Restaurant Search)
    "google_places_hotels": google_places_hotels,
    "google_places_restaurants": google_places_restaurants,
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool travel per nome, filtrando parametri non accettati."""
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {"error": f"Unknown travel tool: {tool_name}"}

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
# Tool Engine Integration
# =============================================================================


def get_tool_definitions() -> list:
    """Generate ToolDefinition objects for all Travel tools."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        # OpenSky
        ToolDefinition(
            name="opensky_flights_live",
            description="Get live flights worldwide from OpenSky Network. Track aircraft positions in real-time. Use when user asks 'flights over X', 'aircraft in the sky now', 'live planes'.",
            parameters={
                "bounds": ToolParameter(
                    type="string",
                    description="Geographic bounding box 'lat_min,lon_min,lat_max,lon_max'",
                    required=False,
                ),
            },
            domain="travel",
            category="flights",
        ),
        ToolDefinition(
            name="opensky_flight_track",
            description="Track the path of a specific aircraft by ICAO code. Get historical positions. Use when user asks 'track flight X', 'where has aircraft Y been', 'flight path of Z'.",
            parameters={
                "icao24": ToolParameter(
                    type="string",
                    description="ICAO 24-bit hex code of the aircraft (e.g., 'abc123')",
                    required=True,
                ),
            },
            domain="travel",
            category="flights",
        ),
        ToolDefinition(
            name="opensky_arrivals",
            description="Get arrivals at an airport by ICAO code. Shows flights landing at airport. Use when user asks 'arrivals at JFK', 'flights landing at Heathrow', 'incoming planes to LAX'.",
            parameters={
                "airport_icao": ToolParameter(
                    type="string",
                    description="Airport ICAO code (e.g., 'KJFK', 'EGLL', 'LIRF')",
                    required=True,
                ),
                "hours_back": ToolParameter(
                    type="integer",
                    description="Hours of history to search (max 24)",
                    required=False,
                ),
            },
            domain="travel",
            category="flights",
        ),
        # AviationStack
        ToolDefinition(
            name="aviationstack_flight",
            description="[DEPRECATED] Get flight info by IATA code. Use adsb_aircraft_by_callsign instead. Use when user asks 'flight UA123 status', 'where is flight AA456'.",
            parameters={
                "flight_iata": ToolParameter(
                    type="string",
                    description="Flight IATA code (e.g., 'UA123', 'AA456')",
                    required=True,
                ),
            },
            domain="travel",
            category="flights",
        ),
        ToolDefinition(
            name="aviationstack_airports",
            description="[DEPRECATED] Search airports by name or code. Use adsb_aircraft_by_location near airport instead. Use when user asks 'cerca aeroporto', 'airport near X', 'codice IATA'.",
            parameters={
                "search": ToolParameter(
                    type="string",
                    description="Airport name or IATA code to search",
                    required=True,
                ),
            },
            domain="travel",
            category="airports",
        ),
        # Amadeus Self-Service (Free Tier Permanente)
        ToolDefinition(
            name="amadeus_search_flights",
            description="Search flights with prices between two airports using Amadeus. Get flight offers with prices, carriers, duration, stops. Use when user asks 'cerca volo Roma Milano', 'flights from CTA to FCO', 'volo per Parigi 15 marzo', 'quanto costa volo'.",
            parameters={
                "origin": ToolParameter(
                    type="string",
                    description="Departure airport IATA code (e.g., 'CTA', 'FCO', 'MXP')",
                    required=True,
                ),
                "destination": ToolParameter(
                    type="string",
                    description="Arrival airport IATA code (e.g., 'FCO', 'CDG', 'JFK')",
                    required=True,
                ),
                "date": ToolParameter(
                    type="string",
                    description="Departure date in YYYY-MM-DD format",
                    required=True,
                ),
                "return_date": ToolParameter(
                    type="string",
                    description="Return date in YYYY-MM-DD format (optional, for round-trip)",
                    required=False,
                ),
                "adults": ToolParameter(
                    type="integer",
                    description="Number of adult passengers (default 1)",
                    required=False,
                ),
            },
            domain="travel",
            category="flights",
        ),
        ToolDefinition(
            name="amadeus_airport_search",
            description="Search airports by name or city. Find IATA codes for airports. Use when user asks 'codice aeroporto Roma', 'airport code for Milan', 'qual è l'aeroporto di Catania'.",
            parameters={
                "keyword": ToolParameter(
                    type="string",
                    description="City name or IATA code to search (e.g., 'Rome', 'Milano', 'FCO')",
                    required=True,
                ),
            },
            domain="travel",
            category="airports",
        ),
        ToolDefinition(
            name="amadeus_confirm_price",
            description="Confirm the price of a flight offer before booking. Use to validate that the price hasn't changed. Required step before amadeus_book_flight.",
            parameters={
                "flight_offer": ToolParameter(
                    type="object",
                    description="The raw flight offer object from Amadeus search response",
                    required=True,
                ),
            },
            domain="travel",
            category="booking",
        ),
        ToolDefinition(
            name="amadeus_book_flight",
            description="Book a flight with Amadeus. Creates a real reservation (test environment). Use when user wants to 'prenota volo', 'book this flight', 'conferma prenotazione'. Requires traveler details.",
            parameters={
                "flight_offer": ToolParameter(
                    type="object",
                    description="The flight offer object from Amadeus search",
                    required=True,
                ),
                "traveler_first_name": ToolParameter(
                    type="string",
                    description="Passenger first name",
                    required=True,
                ),
                "traveler_last_name": ToolParameter(
                    type="string",
                    description="Passenger last name",
                    required=True,
                ),
                "traveler_date_of_birth": ToolParameter(
                    type="string",
                    description="Date of birth (YYYY-MM-DD)",
                    required=True,
                ),
                "traveler_gender": ToolParameter(
                    type="string",
                    description="Gender: MALE or FEMALE",
                    required=True,
                ),
                "traveler_email": ToolParameter(
                    type="string",
                    description="Passenger email address",
                    required=True,
                ),
                "traveler_phone": ToolParameter(
                    type="string",
                    description="Phone number without country code",
                    required=True,
                ),
            },
            domain="travel",
            category="booking",
        ),
        # ADS-B One (Free - 100% Real-time)
        ToolDefinition(
            name="adsb_aircraft_by_location",
            description="Get real-time aircraft near a geographic location (100% free, ADS-B One). Track planes near airports or cities. Use when user asks 'planes near Rome', 'aircraft around JFK', 'flights overhead'.",
            parameters={
                "lat": ToolParameter(
                    type="number", description="Latitude of center point", required=True
                ),
                "lon": ToolParameter(
                    type="number",
                    description="Longitude of center point",
                    required=True,
                ),
                "radius_nm": ToolParameter(
                    type="integer",
                    description="Search radius in nautical miles (max 250)",
                    required=False,
                ),
            },
            domain="travel",
            category="flights",
        ),
        ToolDefinition(
            name="adsb_aircraft_by_icao",
            description="Get real-time info for a specific aircraft by ICAO hex code. Track individual planes. Use when user has aircraft ICAO code like 'A0B1C2'.",
            parameters={
                "icao": ToolParameter(
                    type="string",
                    description="Aircraft ICAO 24-bit hex code (e.g., 'A0B1C2')",
                    required=True,
                ),
            },
            domain="travel",
            category="flights",
        ),
        ToolDefinition(
            name="adsb_aircraft_by_callsign",
            description="Track a live flight by callsign (e.g., UAL123, RYR456). Get real-time position, altitude, speed. Use when user asks 'where is United 123', 'track Ryanair flight'.",
            parameters={
                "callsign": ToolParameter(
                    type="string",
                    description="Flight callsign (e.g., 'UAL123', 'RYR456', 'BAW789')",
                    required=True,
                ),
            },
            domain="travel",
            category="flights",
        ),
    ]


def get_executors() -> dict:
    """Return mapping of tool names to executor functions."""
    return AVAILABLE_TOOLS
