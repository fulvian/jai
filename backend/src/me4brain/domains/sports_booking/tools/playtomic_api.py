"""Playtomic API Tools - Ricerca e Disponibilità Campi.

Questo modulo implementa le chiamate alle API interne di Playtomic per:
- Ricerca club per città/nome
- Verifica disponibilità campi con filtro orario
- Dettagli club
- Prenotazione campi (richiede autenticazione)

Note:
    Playtomic non ha API pubblica. Questi endpoint sono stati identificati
    tramite analisi del sito web e sono per uso personale.
"""

from typing import Any
import os
import httpx
import structlog
from datetime import datetime

logger = structlog.get_logger(__name__)

TIMEOUT = 30.0
PLAYTOMIC_BASE = "https://playtomic.com"
PLAYTOMIC_API = "https://playtomic.com/api"

# Headers per simulare browser
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    "Referer": "https://playtomic.com/",
}


# =============================================================================
# Ricerca Club
# =============================================================================


async def playtomic_search_clubs(
    query: str,
    sport: str = "PADEL",
    limit: int = 20,
) -> dict[str, Any]:
    """Cerca club sportivi per città o nome.

    Args:
        query: Città o nome club da cercare (es. "Milano", "SPH")
        sport: Sport da filtrare (PADEL, TENNIS)
        limit: Numero massimo risultati

    Returns:
        dict con lista club trovati
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=DEFAULT_HEADERS) as client:
            # Prima otteniamo il buildId corrente dal sito
            build_id = await _get_build_id(client)

            if not build_id:
                # Fallback: usa API search diretta
                return await _search_clubs_api(client, query, sport, limit)

            # Usa l'endpoint Next.js data
            url = f"{PLAYTOMIC_BASE}/_next/data/{build_id}/en/search.json"
            params = {"q": query}

            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            # Parsing della risposta Next.js - nuova struttura Storyblok
            page_props = data.get("pageProps", {})

            # Cerca i club nel nuovo path: story.content.body[0].items[*].__blokData.clubs
            clubs_data = []
            try:
                story = page_props.get("story", {})
                content = story.get("content", {})
                body = content.get("body", [])
                if body:
                    items = body[0].get("items", [])
                    for item in items:
                        if item.get("component") == "club_search_results":
                            blok_data = item.get("__blokData", {})
                            clubs_data = blok_data.get("clubs", [])
                            break
            except (IndexError, KeyError, TypeError):
                # Fallback al vecchio path per retrocompatibilità
                clubs_data = page_props.get("clubs", [])

            clubs = []
            for club in clubs_data[:limit]:
                # Estrai i dati con i nuovi nomi dei campi
                address_data = club.get("address", {})
                if isinstance(address_data, str):
                    address_str = address_data
                    city_str = None
                else:
                    address_str = address_data.get("street")
                    city_str = address_data.get("city")

                club_info = {
                    "tenant_id": club.get("tenant_id") or club.get("slug") or club.get("id"),
                    "name": club.get("name") or club.get("tenant_name"),
                    "address": address_str or club.get("address"),
                    "city": city_str,
                    "province": address_data.get("province")
                    if isinstance(address_data, dict)
                    else None,
                    "country": address_data.get("country_code")
                    if isinstance(address_data, dict)
                    else None,
                    "latitude": address_data.get("coordinate", {}).get("lat")
                    if isinstance(address_data, dict)
                    else None,
                    "longitude": address_data.get("coordinate", {}).get("lon")
                    if isinstance(address_data, dict)
                    else None,
                    "sports": club.get("sports", []),
                    "images": club.get("images", [])[:1],  # Solo prima immagine
                    "playtomic_url": f"https://playtomic.com/clubs/{club.get('slug') or club.get('tenant_id')}",
                }

                # Non filtrare per sport se la lista sports è vuota (molti club non la hanno)
                if sport and club_info["sports"]:
                    if not any(s.upper() == sport.upper() for s in club_info.get("sports", [])):
                        continue

                clubs.append(club_info)

            return {
                "query": query,
                "sport": sport,
                "clubs": clubs,
                "count": len(clubs),
                "source": "Playtomic",
            }

    except Exception as e:
        logger.error("playtomic_search_clubs_error", error=str(e), query=query)
        return {"error": str(e), "source": "Playtomic"}


async def _get_build_id(client: httpx.AsyncClient) -> str | None:
    """Ottiene il buildId corrente di Next.js."""
    try:
        resp = await client.get(f"{PLAYTOMIC_BASE}/search")
        if resp.status_code == 200:
            # Cerca buildId nel HTML
            import re

            match = re.search(r'"buildId"\s*:\s*"([^"]+)"', resp.text)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


async def _search_clubs_api(
    client: httpx.AsyncClient,
    query: str,
    sport: str,
    limit: int,
) -> dict[str, Any]:
    """Fallback: ricerca club via API diretta."""
    try:
        # API alternativa per ricerca
        url = f"{PLAYTOMIC_API}/v1/tenants"
        params = {
            "q": query,
            "sport_id": sport,
            "size": limit,
        }

        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        clubs = []
        for club in data.get("data", [])[:limit]:
            clubs.append(
                {
                    "tenant_id": club.get("tenant_id"),
                    "name": club.get("tenant_name"),
                    "address": club.get("address"),
                    "city": club.get("city"),
                    "sports": club.get("sports", []),
                }
            )

        return {
            "query": query,
            "sport": sport,
            "clubs": clubs,
            "count": len(clubs),
            "source": "Playtomic",
        }
    except Exception as e:
        return {"error": str(e), "source": "Playtomic"}


# =============================================================================
# Disponibilità Campi
# =============================================================================


async def playtomic_club_availability(
    tenant_id: str,
    date: str,
    time_from: str | None = None,
    time_to: str | None = None,
    sport: str = "PADEL",
) -> dict[str, Any]:
    """Ottieni disponibilità campi per un club.

    Args:
        tenant_id: ID del club Playtomic
        date: Data in formato YYYY-MM-DD
        time_from: Ora inizio fascia (HH:MM, opzionale)
        time_to: Ora fine fascia (HH:MM, opzionale)
        sport: Sport (PADEL, TENNIS)

    Returns:
        dict con slot disponibili per ogni campo
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=DEFAULT_HEADERS) as client:
            url = f"{PLAYTOMIC_API}/v1/availability"
            params = {
                "tenant_id": tenant_id,
                "sport_id": sport,
                "local_start_min": f"{date}T00:00:00",
                "local_start_max": f"{date}T23:59:59",
            }

            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            resources = []
            for resource in data:
                resource_id = resource.get("resource_id")
                resource_name = resource.get("name", f"Campo {resource_id[:8]}")

                slots = []
                for slot in resource.get("slots", []):
                    start_time = slot.get("start_time", "")[:5]  # HH:MM

                    # Applica filtro orario se specificato
                    if time_from and start_time < time_from:
                        continue
                    if time_to and start_time >= time_to:
                        continue

                    slots.append(
                        {
                            "start_time": start_time,
                            "duration": slot.get("duration"),  # minuti
                            "price": slot.get("price"),
                            "currency": slot.get("currency", "EUR"),
                            "available": slot.get("available", True),
                        }
                    )

                if slots:  # Solo risorse con slot disponibili nel range
                    resources.append(
                        {
                            "resource_id": resource_id,
                            "name": resource_name,
                            "slots": slots,
                            "slots_count": len(slots),
                        }
                    )

            return {
                "tenant_id": tenant_id,
                "date": date,
                "sport": sport,
                "time_filter": {
                    "from": time_from,
                    "to": time_to,
                }
                if time_from or time_to
                else None,
                "resources": resources,
                "total_slots": sum(r["slots_count"] for r in resources),
                "source": "Playtomic",
            }

    except Exception as e:
        logger.error(
            "playtomic_club_availability_error",
            error=str(e),
            tenant_id=tenant_id,
            date=date,
        )
        return {"error": str(e), "source": "Playtomic"}


# =============================================================================
# Dettagli Club
# =============================================================================


async def playtomic_court_details(tenant_id: str) -> dict[str, Any]:
    """Ottieni dettagli completi di un club.

    Args:
        tenant_id: ID del club Playtomic

    Returns:
        dict con info complete del club
    """
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, headers=DEFAULT_HEADERS) as client:
            url = f"{PLAYTOMIC_API}/v1/tenants/{tenant_id}"

            resp = await client.get(url)
            resp.raise_for_status()
            club = resp.json()

            return {
                "tenant_id": tenant_id,
                "name": club.get("tenant_name"),
                "description": club.get("description"),
                "address": {
                    "street": club.get("address", {}).get("street"),
                    "city": club.get("address", {}).get("city"),
                    "province": club.get("address", {}).get("province"),
                    "postal_code": club.get("address", {}).get("postal_code"),
                    "country": club.get("address", {}).get("country_code"),
                },
                "coordinates": {
                    "lat": club.get("address", {}).get("coordinate", {}).get("lat"),
                    "lon": club.get("address", {}).get("coordinate", {}).get("lon"),
                },
                "phone": club.get("phone"),
                "email": club.get("email"),
                "sports": club.get("sports", []),
                "amenities": club.get("properties", {}).get("amenities", []),
                "opening_hours": club.get("properties", {}).get("opening_hours"),
                "images": club.get("images", []),
                "playtomic_url": f"https://playtomic.com/clubs/{tenant_id}",
                "source": "Playtomic",
            }

    except Exception as e:
        logger.error("playtomic_court_details_error", error=str(e), tenant_id=tenant_id)
        return {"error": str(e), "source": "Playtomic"}


# =============================================================================
# Prenotazione (Richiede Autenticazione)
# =============================================================================


async def playtomic_book_court(
    resource_id: str,
    start_time: str,
    duration: int = 90,
) -> dict[str, Any]:
    """Prenota un campo (richiede autenticazione).

    Args:
        resource_id: ID del campo da prenotare
        start_time: Orario inizio (formato ISO: 2026-02-04T18:00:00)
        duration: Durata in minuti (60, 90, 120)

    Returns:
        dict con conferma prenotazione
    """
    from .playtomic_auth import PlaytomicAuth

    try:
        auth = PlaytomicAuth()
        token = await auth.get_valid_token()

        if not token:
            return {
                "error": "Autenticazione richiesta. Esegui: python -m me4brain.domains.sports_booking.setup_auth",
                "source": "Playtomic",
            }

        headers = {
            **DEFAULT_HEADERS,
            "Authorization": f"Bearer {token}",
        }

        async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
            url = f"{PLAYTOMIC_API}/v1/bookings"
            payload = {
                "resource_id": resource_id,
                "start_time": start_time,
                "duration": duration,
            }

            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            booking = resp.json()

            return {
                "success": True,
                "booking_id": booking.get("booking_id"),
                "resource_id": resource_id,
                "start_time": start_time,
                "duration": duration,
                "price": booking.get("price"),
                "status": booking.get("status"),
                "confirmation_code": booking.get("confirmation_code"),
                "source": "Playtomic",
            }

    except Exception as e:
        logger.error(
            "playtomic_book_court_error",
            error=str(e),
            resource_id=resource_id,
        )
        return {"error": str(e), "source": "Playtomic"}


async def playtomic_my_bookings(upcoming_only: bool = True) -> dict[str, Any]:
    """Ottieni le prenotazioni dell'utente.

    Args:
        upcoming_only: Se True, solo prenotazioni future

    Returns:
        dict con lista prenotazioni
    """
    from .playtomic_auth import PlaytomicAuth

    try:
        auth = PlaytomicAuth()
        token = await auth.get_valid_token()

        if not token:
            return {
                "error": "Autenticazione richiesta. Esegui: python -m me4brain.domains.sports_booking.setup_auth",
                "source": "Playtomic",
            }

        headers = {
            **DEFAULT_HEADERS,
            "Authorization": f"Bearer {token}",
        }

        async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
            url = f"{PLAYTOMIC_API}/v1/bookings/me"
            params = {}
            if upcoming_only:
                params["from"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

            bookings = []
            for booking in data.get("data", []):
                bookings.append(
                    {
                        "booking_id": booking.get("booking_id"),
                        "club_name": booking.get("tenant_name"),
                        "court_name": booking.get("resource_name"),
                        "date": booking.get("start_time", "")[:10],
                        "time": booking.get("start_time", "")[11:16],
                        "duration": booking.get("duration"),
                        "sport": booking.get("sport_id"),
                        "price": booking.get("price"),
                        "status": booking.get("status"),
                    }
                )

            return {
                "bookings": bookings,
                "count": len(bookings),
                "upcoming_only": upcoming_only,
                "source": "Playtomic",
            }

    except Exception as e:
        logger.error("playtomic_my_bookings_error", error=str(e))
        return {"error": str(e), "source": "Playtomic"}


async def playtomic_cancel_booking(booking_id: str) -> dict[str, Any]:
    """Cancella una prenotazione.

    Args:
        booking_id: ID della prenotazione da cancellare

    Returns:
        dict con conferma cancellazione
    """
    from .playtomic_auth import PlaytomicAuth

    try:
        auth = PlaytomicAuth()
        token = await auth.get_valid_token()

        if not token:
            return {
                "error": "Autenticazione richiesta. Esegui: python -m me4brain.domains.sports_booking.setup_auth",
                "source": "Playtomic",
            }

        headers = {
            **DEFAULT_HEADERS,
            "Authorization": f"Bearer {token}",
        }

        async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers) as client:
            url = f"{PLAYTOMIC_API}/v1/bookings/{booking_id}"

            resp = await client.delete(url)
            resp.raise_for_status()

            return {
                "success": True,
                "booking_id": booking_id,
                "message": "Prenotazione cancellata con successo",
                "source": "Playtomic",
            }

    except Exception as e:
        logger.error("playtomic_cancel_booking_error", error=str(e), booking_id=booking_id)
        return {"error": str(e), "source": "Playtomic"}


# =============================================================================
# Tool Registry
# =============================================================================


AVAILABLE_TOOLS = {
    # Read-only (no auth)
    "playtomic_search_clubs": playtomic_search_clubs,
    "playtomic_club_availability": playtomic_club_availability,
    "playtomic_court_details": playtomic_court_details,
    # Booking (auth required)
    "playtomic_book_court": playtomic_book_court,
    "playtomic_my_bookings": playtomic_my_bookings,
    "playtomic_cancel_booking": playtomic_cancel_booking,
}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool Playtomic per nome, filtrando parametri non accettati."""
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {"error": f"Unknown Playtomic tool: {tool_name}"}

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
    """Generate ToolDefinition objects for all Playtomic tools."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        ToolDefinition(
            name="playtomic_search_clubs",
            description="Cerca club sportivi (padel/tennis) per città o nome su Playtomic. Use when user asks 'cerca campi padel', 'club tennis Milano', 'playtomic Roma'.",
            parameters={
                "query": ToolParameter(
                    type="string",
                    description="Città o nome club da cercare (es. 'Milano', 'SPH')",
                    required=True,
                ),
                "sport": ToolParameter(
                    type="string",
                    description="Sport: PADEL o TENNIS",
                    required=False,
                    default="PADEL",
                ),
            },
            domain="sports",
            category="search",
        ),
        ToolDefinition(
            name="playtomic_club_availability",
            description="Verifica disponibilità campi per un club Playtomic, con filtro opzionale per fascia oraria. Use when user asks 'disponibilità domani', 'slot liberi', 'campi disponibili dalle 18 alle 21'.",
            parameters={
                "tenant_id": ToolParameter(
                    type="string",
                    description="ID del club Playtomic",
                    required=True,
                ),
                "date": ToolParameter(
                    type="string",
                    description="Data in formato YYYY-MM-DD",
                    required=True,
                ),
                "time_from": ToolParameter(
                    type="string",
                    description="Ora inizio fascia (HH:MM, es. '18:00')",
                    required=False,
                ),
                "time_to": ToolParameter(
                    type="string",
                    description="Ora fine fascia (HH:MM, es. '21:00')",
                    required=False,
                ),
                "sport": ToolParameter(
                    type="string",
                    description="Sport: PADEL o TENNIS",
                    required=False,
                    default="PADEL",
                ),
            },
            domain="sports",
            category="availability",
        ),
        ToolDefinition(
            name="playtomic_court_details",
            description="Ottieni informazioni dettagliate su un club Playtomic (indirizzo, servizi, orari apertura). Use when user asks 'info club', 'dettagli centro', 'orari apertura'.",
            parameters={
                "tenant_id": ToolParameter(
                    type="string",
                    description="ID del club Playtomic",
                    required=True,
                ),
            },
            domain="sports",
            category="info",
        ),
        ToolDefinition(
            name="playtomic_book_court",
            description="Prenota un campo su Playtomic (richiede autenticazione). Use when user asks 'prenota campo', 'riserva slot', 'booking padel'.",
            parameters={
                "resource_id": ToolParameter(
                    type="string",
                    description="ID del campo da prenotare",
                    required=True,
                ),
                "start_time": ToolParameter(
                    type="string",
                    description="Orario inizio (formato ISO: 2026-02-04T18:00:00)",
                    required=True,
                ),
                "duration": ToolParameter(
                    type="integer",
                    description="Durata in minuti (60, 90, 120)",
                    required=False,
                    default=90,
                ),
            },
            domain="sports",
            category="booking",
        ),
        ToolDefinition(
            name="playtomic_my_bookings",
            description="Ottieni lista delle tue prenotazioni Playtomic (richiede autenticazione). Use when user asks 'mie prenotazioni', 'le mie partite', 'booking confermati'.",
            parameters={
                "upcoming_only": ToolParameter(
                    type="boolean",
                    description="Se True, solo prenotazioni future",
                    required=False,
                    default=True,
                ),
            },
            domain="sports",
            category="booking",
        ),
        ToolDefinition(
            name="playtomic_cancel_booking",
            description="Cancella una prenotazione Playtomic (richiede autenticazione). Use when user asks 'cancella prenotazione', 'annulla partita', 'disdici campo'.",
            parameters={
                "booking_id": ToolParameter(
                    type="string",
                    description="ID della prenotazione da cancellare",
                    required=True,
                ),
            },
            domain="sports",
            category="booking",
        ),
    ]


def get_executors() -> dict:
    """Get executor functions for ToolCallingEngine.

    Returns:
        Dict mapping tool names to async executor functions.
    """
    return {
        # Read-only (no auth)
        "playtomic_search_clubs": playtomic_search_clubs,
        "playtomic_club_availability": playtomic_club_availability,
        "playtomic_court_details": playtomic_court_details,
        # Booking (auth required)
        "playtomic_book_court": playtomic_book_court,
        "playtomic_my_bookings": playtomic_my_bookings,
        "playtomic_cancel_booking": playtomic_cancel_booking,
    }
