"""Geo & Weather Domain Handler."""

from datetime import UTC, datetime
from typing import Any

import structlog

from me4brain.core.interfaces import (
    DomainCapability,
    DomainExecutionResult,
    DomainHandler,
    DomainVolatility,
)

logger = structlog.get_logger(__name__)


class GeoWeatherHandler(DomainHandler):
    """Domain handler per Geo e Weather queries."""

    GEO_KEYWORDS = frozenset(
        {
            "meteo",
            "weather",
            "tempo",
            "temperatura",
            "temperature",
            "previsioni",
            "forecast",
            "pioggia",
            "rain",
            "neve",
            "snow",
            "vento",
            "wind",
            "umidità",
            "humidity",
            "terremoto",
            "earthquake",
            "sisma",
            "geocode",
            "coordinate",
            "latitudine",
            "longitudine",
            "città",
            "city",
            "paese",
            "country",
            "nazione",
            "festivo",
            "holiday",
            "festività",
        }
    )

    @property
    def domain_name(self) -> str:
        return "geo_weather"

    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.PERIODIC

    @property
    def default_ttl_hours(self) -> int:
        return 6

    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="weather",
                description="Meteo e previsioni",
                keywords=["meteo", "weather", "previsioni"],
                example_queries=["Meteo Roma", "Previsioni Milano"],
            ),
            DomainCapability(
                name="earthquake",
                description="Terremoti recenti",
                keywords=["terremoto", "earthquake"],
                example_queries=["Terremoti ultimi 7 giorni"],
            ),
        ]

    async def initialize(self) -> None:
        logger.info("geo_weather_handler_initialized")

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        query_lower = query.lower()
        matches = sum(1 for kw in self.GEO_KEYWORDS if kw in query_lower)
        if matches == 0:
            return 0.0
        elif matches <= 2:
            return 0.7
        else:
            return 0.9

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        from me4brain.domains.geo_weather.tools import geo_api

        query_lower = query.lower()
        start_time = datetime.now(UTC)

        try:
            if "terremoto" in query_lower or "earthquake" in query_lower:
                data = await geo_api.usgs_earthquakes()
                tool_name = "usgs_earthquakes"
            elif "festiv" in query_lower or "holiday" in query_lower:
                data = await geo_api.nager_holidays()
                tool_name = "nager_holidays"
            else:
                # Default: weather
                city = self._extract_city(query, analysis)
                data = await geo_api.openmeteo_weather(city=city)
                tool_name = "openmeteo_weather"

            # IMPORTANTE: data deve essere SEMPRE un dict, mai None
            # Pydantic DomainExecutionResult richiede dict, None causa ValidationError
            result_data = data if not data.get("error") else {"error": data.get("error")}

            return [
                DomainExecutionResult(
                    success=not data.get("error"),
                    domain=self.domain_name,
                    tool_name=tool_name,
                    data=result_data,
                    error=data.get("error"),
                    latency_ms=(datetime.now(UTC) - start_time).total_seconds() * 1000,
                )
            ]
        except Exception as e:
            # SEMPRE restituire dict per data, mai None
            return [
                DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name="geo_weather",
                    data={"error": str(e)},
                    error=str(e),
                )
            ]

    def _extract_city(self, query: str, analysis: dict[str, Any] | None = None) -> str:
        """Estrae la città usando entity extraction centralizzata.

        Usa analysis["entities"] estratte da LLM, non parsing manuale.
        """
        from me4brain.core.nlp_utils import get_entity_by_type

        # 1. Estrai location da analysis LLM (metodo principale)
        city = get_entity_by_type(analysis, "location")
        if city:
            logger.debug("city_from_llm_analysis", city=city)
            return city

        # 2. Fallback: Estrazione diretta dal testo della query
        # Controllo per nomi di città italiane
        italian_cities = {
            "caltanissetta": "Caltanissetta",
            "roma": "Rome",
            "milano": "Milan",
            "napoli": "Naples",
            "torino": "Turin",
            "firenze": "Florence",
            "venezia": "Venice",
            "bologna": "Bologna",
            "genova": "Genoa",
            "palermo": "Palermo",
            "catania": "Catania",
            "bari": "Bari",
            "verona": "Verona",
            "pisa": "Pisa",
            "cagliari": "Cagliari",
            "trieste": "Trieste",
            "perugia": "Perugia",
            "lamezia": "Lamezia",
            "messina": "Messina",
            "reggio": "Reggio",
            "siena": "Siena",
            "modena": "Modena",
            "rimini": "Rimini",
            "cosenza": "Cosenza",
            "ascoli": "Ascoli",
            "avellino": "Avellino",
            "latina": "Latina",
        }

        # Normalizza la query per la ricerca
        query_lower = query.lower()

        # Cerca nomi di città direttamente nella query
        for city_lower, city_english in italian_cities.items():
            if city_lower in query_lower:
                logger.debug(
                    "city_extracted_direct_query", city=city_english, query_fragment=city_lower
                )
                return city_english

        # 3. Fallback generico
        # Se la query contiene parole chiave di meteo ma nessuna città esplicita, usa "Rome"
        meteorological_keywords = ["meteo", "tempo", "previsioni", "temperatura", "pioggia", "sole"]
        if any(kw in query_lower for kw in meteorological_keywords):
            logger.warning("city_extraction_fallback_default", query=query[:50])
            return "Rome"

        # 4. Ultimo fallback
        logger.warning("city_extraction_unrecognized", query=query[:50])
        return "Rome"

    def handles_service(self, service_name: str) -> bool:
        return service_name in {"OpenMeteoService", "USGSService", "NagerDateService"}

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from me4brain.domains.geo_weather.tools import geo_api

        return await geo_api.execute_tool(tool_name, arguments)
