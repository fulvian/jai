"""Tool Executor - Esecuzione sicura di tool.

Gestisce l'esecuzione dei tool registrati con:
- Validazione input
- Rate limiting
- Error handling
- Metrics collection
"""

import time
from typing import Any
from uuid import uuid4

import httpx
import structlog
from pydantic import BaseModel, Field

from me4brain.embeddings import get_embedding_service
from me4brain.memory.procedural import (
    ProceduralMemory,
    Tool,
    ToolExecution,
    get_procedural_memory,
)

logger = structlog.get_logger(__name__)


class ExecutionRequest(BaseModel):
    """Richiesta di esecuzione tool."""

    tenant_id: str
    user_id: str
    intent: str
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    """Risultato dell'esecuzione."""

    success: bool
    tool_id: str
    tool_name: str
    result: Any | None = None
    error: str | None = None
    latency_ms: float = 0.0
    from_muscle_memory: bool = False


class ToolExecutor:
    """Esecutore di tool con Muscle Memory integration e Redis caching.

    Workflow:
    1. Cerca in Redis cache (se abilitato)
    2. Cerca in Muscle Memory per bypass
    3. Se miss, esegue il tool
    4. Salva esecuizioni in Redis cache e Muscle Memory
    5. Aggiorna pesi nel Skill Graph
    """

    # Timeout default per chiamate HTTP
    DEFAULT_TIMEOUT = 30.0

    # TTL cache per categoria (in secondi)
    CACHE_TTL = {
        "crypto": 30,  # Prezzi crypto: 30 secondi
        "finance": 60,  # Dati finanziari: 1 minuto
        "trading": 30,  # Trading data: 30 secondi
        "weather": 300,  # Meteo: 5 minuti
        "news": 300,  # Notizie: 5 minuti
        "search": 600,  # Ricerca: 10 minuti
        "science": 3600,  # Paper scientifici: 1 ora
        "medical": 3600,  # Farmaci: 1 ora
        "encyclopedia": 3600,  # Wikipedia: 1 ora
        "utility": 86400,  # Utility: 24 ore
        "geo": 86400,  # Geo data: 24 ore
        "google": 60,  # Google Workspace: 1 minuto
        "default": 300,  # Default: 5 minuti
    }

    def __init__(
        self,
        procedural_memory: ProceduralMemory | None = None,
        http_client: httpx.AsyncClient | None = None,
        redis_url: str | None = None,
    ) -> None:
        """Inizializza l'executor."""
        self._procedural = procedural_memory
        self._http_client = http_client
        self._redis_client = None
        self._redis_available = False

        # Try to initialize Redis
        if redis_url is None:
            import os

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

        try:
            import redis.asyncio as aioredis

            self._redis_client = aioredis.from_url(redis_url, decode_responses=True)
            self._redis_available = True
            logger.info("redis_cache_initialized", url=redis_url.split("@")[-1])
        except Exception as e:
            logger.warning("redis_cache_unavailable", error=str(e))
            self._redis_available = False

    def get_procedural(self) -> ProceduralMemory:
        """Ottiene ProceduralMemory."""
        if self._procedural is None:
            self._procedural = get_procedural_memory()
        return self._procedural

    async def get_http_client(self) -> httpx.AsyncClient:
        """Ottiene il client HTTP."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT)
        return self._http_client

    def _get_cache_key(self, service: str, method: str, args: dict) -> str:
        """Genera chiave cache deterministica."""
        import hashlib
        import json

        args_str = json.dumps(args, sort_keys=True, default=str)
        key_data = f"{service}:{method}:{args_str}"
        return f"me4brain:tool:{hashlib.md5(key_data.encode()).hexdigest()}"

    def _get_ttl_for_category(self, category: str) -> int:
        """Ottiene TTL per categoria."""
        return self.CACHE_TTL.get(category, self.CACHE_TTL["default"])

    async def _get_from_cache(self, cache_key: str) -> dict | None:
        """Legge dalla cache Redis."""
        if not self._redis_available or not self._redis_client:
            return None
        try:
            import json

            data = await self._redis_client.get(cache_key)
            if data:
                logger.debug("cache_hit", key=cache_key[:40])
                return json.loads(data)
        except Exception as e:
            logger.warning("cache_read_error", error=str(e))
        return None

    async def _set_in_cache(self, cache_key: str, data: dict, ttl: int) -> None:
        """Salva nella cache Redis."""
        if not self._redis_available or not self._redis_client:
            return
        try:
            import json

            await self._redis_client.setex(cache_key, ttl, json.dumps(data, default=str))
            logger.debug("cache_set", key=cache_key[:40], ttl=ttl)
        except Exception as e:
            logger.warning("cache_write_error", error=str(e))

    async def _get_tool_from_qdrant(
        self,
        procedural: "ProceduralMemory",
        tool_id: str,
        tenant_id: str,
    ) -> Tool | None:
        """Recupera un tool da Qdrant (fallback quando KuzuDB è locked).

        Args:
            procedural: Istanza ProceduralMemory
            tool_id: ID del tool
            tenant_id: ID tenant

        Returns:
            Tool ricostruito o None se non trovato
        """
        try:
            client = await procedural.get_qdrant()

            # Cerca il tool per ID nella collection tools
            response = await client.retrieve(
                collection_name=procedural.TOOLS_COLLECTION,
                ids=[tool_id],
                with_payload=True,
            )

            if not response:
                logger.warning("tool_not_found_in_qdrant", tool_id=tool_id)
                return None

            point = response[0]
            payload = point.payload or {}

            tool = Tool(
                id=str(point.id),
                name=payload.get("name", "unknown"),
                description=payload.get("description", ""),
                tenant_id=tenant_id,
                endpoint=payload.get("endpoint"),
                method=payload.get("method", "POST"),
                status=payload.get("status", "ACTIVE"),
            )

            logger.info(
                "tool_recovered_from_qdrant",
                tool_id=tool_id,
                tool_name=tool.name,
            )
            return tool

        except Exception as e:
            logger.error("qdrant_tool_recovery_failed", tool_id=tool_id, error=str(e))
            return None

    async def execute(
        self,
        request: ExecutionRequest,
        use_muscle_memory: bool = True,
    ) -> ExecutionResult:
        """Esegue un tool.

        Args:
            request: Richiesta di esecuzione
            use_muscle_memory: Se cercare prima in Muscle Memory

        Returns:
            ExecutionResult con successo/errore
        """
        procedural = self.get_procedural()
        start_time = time.perf_counter()

        # Step 1: Cerca in Muscle Memory
        if use_muscle_memory:
            embedding_service = get_embedding_service()
            intent_embedding = embedding_service.embed_query(request.intent)

            cached_execution = await procedural.find_similar_execution(
                tenant_id=request.tenant_id,
                intent_embedding=intent_embedding,
                tool_id=request.tool_id,
                min_score=0.90,  # Soglia alta per sicurezza
            )

            if cached_execution:
                latency = (time.perf_counter() - start_time) * 1000

                logger.info(
                    "muscle_memory_hit",
                    tool_id=request.tool_id,
                    cached_intent=cached_execution.intent[:50],
                    latency_ms=latency,
                )

                # Usa gli stessi argomenti dell'esecuzione precedente
                # In produzione, si potrebbe anche riusare direttamente l'output
                return ExecutionResult(
                    success=True,
                    tool_id=request.tool_id,
                    tool_name=cached_execution.tool_name,
                    result={
                        "cached": True,
                        "original_output": cached_execution.output_json,
                        "suggested_input": cached_execution.input_json,
                    },
                    latency_ms=latency,
                    from_muscle_memory=True,
                )

        # Step 2: Recupera info del tool
        semantic = procedural.get_semantic()
        entity = await semantic.get_entity(request.tenant_id, request.tool_id)

        if entity is None:
            # Neo4j non ha trovato l'entità - prova fallback su Qdrant
            logger.info("neo4j_entity_none_fallback_qdrant", tool_id=request.tool_id)
            tool = await self._get_tool_from_qdrant(procedural, request.tool_id, request.tenant_id)

            if tool is None:
                return ExecutionResult(
                    success=False,
                    tool_id=request.tool_id,
                    tool_name="unknown",
                    error=f"Tool not found: {request.tool_id}",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )
        else:
            # Ricostruisci Tool dalle properties
            props = entity.properties
            tool = Tool(
                id=entity.id,
                name=entity.name,
                description=props.get("description", ""),
                tenant_id=entity.tenant_id,
                endpoint=props.get("endpoint"),
                method=props.get("method", "POST"),
                api_schema=props.get("api_schema", {}),
                status=props.get("status", "ACTIVE"),
            )

        # Step 3: Esegui il tool
        try:
            result = await self._execute_tool(tool, request.arguments)
            success = True
            error = None
        except Exception as e:
            result = None
            success = False
            error = str(e)
            logger.error(
                "tool_execution_failed",
                tool_id=tool.id,
                error=error,
            )

        latency = (time.perf_counter() - start_time) * 1000

        # Step 4: Aggiorna Skill Graph weights
        await procedural.update_tool_weight(
            tenant_id=request.tenant_id,
            tool_id=request.tool_id,
            success=success,
        )

        # Step 5: Salva in Muscle Memory se successo
        if success and use_muscle_memory:
            embedding_service = get_embedding_service()
            intent_embedding = embedding_service.embed_query(request.intent)

            execution = ToolExecution(
                id=str(uuid4()),
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                intent=request.intent,
                tool_id=request.tool_id,
                tool_name=tool.name,
                input_json=request.arguments,
                output_json=result,
                success=True,
                latency_ms=latency,
            )

            await procedural.save_execution(execution, intent_embedding)

        return ExecutionResult(
            success=success,
            tool_id=tool.id,
            tool_name=tool.name,
            result=result,
            error=error,
            latency_ms=latency,
            from_muscle_memory=False,
        )

    async def _execute_tool(
        self,
        tool: Tool,
        arguments: dict[str, Any],
    ) -> Any:
        """Esegue effettivamente il tool.

        Supporta:
        - HTTP tools (GET, POST, PUT, PATCH, DELETE)
        - INTERNAL tools (servizi Python registrati)
        """
        if not tool.endpoint:
            raise ValueError(f"Tool {tool.name} has no endpoint configured")

        method = tool.method.lower()

        # Gestisci tool INTERNAL (endpoint: internal://ServiceName/method)
        if method == "internal" or tool.endpoint.startswith("internal://"):
            return await self._execute_internal_tool(tool, arguments)

        # Tool HTTP normali
        client = await self.get_http_client()

        # Prepara la request
        url = tool.endpoint

        # Sostituisci path parameters
        for key, value in arguments.items():
            placeholder = f"{{{key}}}"
            if placeholder in url:
                url = url.replace(placeholder, str(value))

        # Prepara body o query params
        body = arguments.get("body")
        params = {k: v for k, v in arguments.items() if k != "body"}

        # Esegui la request
        if method == "get":
            response = await client.get(url, params=params)
        elif method == "post":
            response = await client.post(url, json=body, params=params)
        elif method == "put":
            response = await client.put(url, json=body, params=params)
        elif method == "patch":
            response = await client.patch(url, json=body, params=params)
        elif method == "delete":
            response = await client.delete(url, params=params)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        response.raise_for_status()

        # Parsa risposta
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        else:
            return response.text

    async def _execute_internal_tool(
        self,
        tool: Tool,
        arguments: dict[str, Any],
    ) -> Any:
        """Esegue un tool interno (servizi Python registrati).

        Endpoint format: internal://ServiceName/method_name
        """
        endpoint = tool.endpoint

        # Parse endpoint: internal://CoinGeckoService/get_price
        if endpoint.startswith("internal://"):
            endpoint = endpoint[len("internal://") :]

        parts = endpoint.split("/", 1)
        service_name = parts[0]
        method_name = parts[1] if len(parts) > 1 else "execute"

        logger.info(
            "executing_internal_tool",
            tool_name=tool.name,
            service=service_name,
            method=method_name,
        )

        # Registry dei servizi interni (da espandere)
        result = await self._dispatch_internal_service(service_name, method_name, arguments)

        return result

    async def _dispatch_internal_service(
        self,
        service_name: str,
        method_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Dispatch chiamate ai servizi interni registrati.

        Prima tenta dispatch via domain handlers (architettura modulare),
        poi fallback a handler legacy inline.
        """
        import os
        from me4brain.retrieval.domain_dispatch import dispatch_to_domain

        # NUOVA ARCHITETTURA: Tenta domain handler first
        domain_result = await dispatch_to_domain(
            service_name=service_name,
            method_name=method_name,
            arguments=arguments,
        )
        if domain_result is not None:
            return domain_result

        # LEGACY FALLBACK: Handler inline per servizi non ancora migrati
        handlers = {
            # Crypto (MIGRATO a finance_crypto domain)
            "CoinGeckoService": self._coingecko_handler,
            # Meteo/Geo (MIGRATO a geo_weather domain)
            "OpenMeteoService": self._openmeteo_handler,
            "NominatimService": self._nominatim_handler,
            "SunriseSunsetService": self._sunrise_handler,
            # Finanza (con API key) - alcuni MIGRATI
            "FinnhubService": self._finnhub_handler,
            "AlphaVantageService": self._alphavantage_handler,
            "PolygonService": self._polygon_handler,
            "TwelveDataService": self._twelvedata_handler,
            "FREDService": self._fred_handler,
            "EDGARService": self._edgar_handler,
            "YahooFinanceService": self._yfinance_handler,
            # News/Ricerca (MIGRATO a knowledge_media)
            "HackerNewsService": self._hackernews_handler,
            "NewsDataService": self._newsdata_handler,
            # Enciclopedia (MIGRATO a knowledge_media)
            "WikipediaService": self._wikipedia_handler,
            "OpenLibraryService": self._openlibrary_handler,
            # Utility
            "NASAService": self._nasa_handler,
            "HttpbinService": self._httpbin_handler,
            "IPifyService": self._ipify_handler,
            # Accademia (MIGRATO a science_research)
            "ArXivService": self._arxiv_handler,
            "CrossrefService": self._crossref_handler,
            "SemanticScholarService": self._semanticscholar_handler,
            "EuropePMCService": self._europepmc_handler,
            "PubMedService": self._pubmed_handler,
            "OpenAlexService": self._openalex_handler,
            # Utility FREE
            "AgifyService": self._agify_handler,
            "GenderizeService": self._genderize_handler,
            "RestCountriesService": self._restcountries_handler,
            "NagerDateService": self._nagerdate_handler,
            "USGSEarthquakeService": self._usgs_handler,
            "RandomUserService": self._randomuser_handler,
            # Sport (MIGRATO a sports_nba)
            "BallDontLieService": self._balldontlie_handler,
            # Science/Medical
            "RxNormService": self._rxnorm_handler,
            "iCiteService": self._icite_handler,
            # Search (MIGRATO a web_search)
            "DuckDuckGoService": self._duckduckgo_handler,
            # Trading (with API keys)
            "HyperliquidService": self._hyperliquid_handler,
            "AlpacaService": self._alpaca_handler,
            "BinanceService": self._binance_handler,
            # Sports (MIGRATO a sports_nba)
            "NBAStatsService": self._nba_stats_handler,
            "TheOddsAPIService": self._theoddsapi_handler,
            "ESPNService": self._espn_handler,
            # Google Workspace (MIGRATO a google_workspace)
            "GoogleDriveService": self._google_drive_handler,
            "GoogleGmailService": self._google_gmail_handler,
            "GoogleCalendarService": self._google_calendar_handler,
            "GoogleDocsService": self._google_docs_handler,
            "GoogleSheetsService": self._google_sheets_handler,
            "GoogleSlidesService": self._google_slides_handler,
            "GoogleMeetService": self._google_meet_handler,
            "GoogleFormsService": self._google_forms_handler,
            "GoogleClassroomService": self._google_classroom_handler,
        }

        handler = handlers.get(service_name)
        if handler:
            return await handler(method_name, arguments)
        else:
            # Fallback per servizi non implementati
            logger.warning("unimplemented_service", service=service_name)
            return {
                "error": f"Service {service_name} not yet implemented",
                "service": service_name,
                "method": method_name,
            }

    async def _coingecko_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per CoinGecko API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "get_price":
                coin_id = arguments.get("coin_id", "bitcoin")
                vs_currency = arguments.get("vs_currency", "usd")

                response = await client.get(
                    f"https://api.coingecko.com/api/v3/simple/price",
                    params={"ids": coin_id, "vs_currencies": vs_currency},
                )
                response.raise_for_status()
                data = response.json()

                price = data.get(coin_id, {}).get(vs_currency)
                return {
                    "coin": coin_id,
                    "currency": vs_currency,
                    "price": price,
                    "source": "CoinGecko",
                }
            elif method_name == "get_market_chart":
                # Storico prezzi crypto (max 730 giorni)
                coin_id = arguments.get("coin_id", "bitcoin")
                vs_currency = arguments.get("vs_currency", "usd")
                days = arguments.get("days", 365)  # Default 1 anno

                response = await client.get(
                    f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                    params={"vs_currency": vs_currency, "days": days},
                )
                response.raise_for_status()
                data = response.json()

                # Prendi un sample dei prezzi (ogni settimana circa)
                prices = data.get("prices", [])
                sample_step = max(1, len(prices) // 50)  # Max 50 data points
                sampled_prices = [
                    {"timestamp": int(p[0]), "price": p[1]}
                    for i, p in enumerate(prices)
                    if i % sample_step == 0
                ]

                return {
                    "coin": coin_id,
                    "currency": vs_currency,
                    "days": days,
                    "data_points": len(sampled_prices),
                    "prices": sampled_prices,
                    "source": "CoinGecko",
                }
            else:
                raise ValueError(f"Unknown CoinGecko method: {method_name}")

    async def _openmeteo_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Open-Meteo API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name in ("get_forecast", "get_weather"):
                lat = arguments.get("latitude", 41.9028)  # Roma default
                lon = arguments.get("longitude", 12.4964)

                response = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current_weather": True,
                    },
                )
                response.raise_for_status()
                data = response.json()

                weather = data.get("current_weather", {})
                return {
                    "temperature": weather.get("temperature"),
                    "windspeed": weather.get("windspeed"),
                    "weathercode": weather.get("weathercode"),
                    "source": "Open-Meteo",
                }
                raise ValueError(f"Unknown OpenMeteo method: {method_name}")

    async def _duckduckgo_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per DuckDuckGo Search - Ricerca web REALE."""
        from duckduckgo_search import DDGS

        query = arguments.get("query", "")
        max_results = min(arguments.get("max_results", 5), 10)

        # Headers per evitare rate limiting
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            # Prova prima con backend api, poi html, poi lite
            for backend in ["api", "html", "lite"]:
                try:
                    with DDGS(headers=headers, timeout=20) as ddgs:
                        if method_name in ("search", "text", "instant_answer"):
                            results = list(
                                ddgs.text(query, max_results=max_results, backend=backend)
                            )
                        elif method_name == "news":
                            results = list(ddgs.news(query, max_results=max_results))
                            if results:
                                return {
                                    "query": query,
                                    "articles": [
                                        {
                                            "title": r.get("title"),
                                            "url": r.get("url"),
                                            "date": r.get("date"),
                                        }
                                        for r in results
                                    ],
                                    "source": "DuckDuckGo News",
                                }
                            continue
                        elif method_name == "images":
                            results = list(ddgs.images(query, max_results=max_results))
                            if results:
                                return {
                                    "query": query,
                                    "images": [
                                        {"title": r.get("title"), "url": r.get("image")}
                                        for r in results
                                    ],
                                    "source": "DuckDuckGo Images",
                                }
                            continue
                        else:
                            results = list(
                                ddgs.text(query, max_results=max_results, backend=backend)
                            )

                        if results:
                            return {
                                "query": query,
                                "results": [
                                    {
                                        "title": r.get("title"),
                                        "url": r.get("href"),
                                        "snippet": r.get("body", "")[:200],
                                    }
                                    for r in results
                                ],
                                "source": "DuckDuckGo",
                                "backend": backend,
                            }
                except Exception as be:
                    logger.warning("duckduckgo_backend_failed", backend=backend, error=str(be))
                    continue

            # Se tutti i backend falliscono
            return {"error": "All backends failed", "query": query, "source": "DuckDuckGo"}
        except Exception as e:
            logger.error("duckduckgo_error", error=str(e))
            return {"error": str(e), "query": query, "source": "DuckDuckGo"}

    async def _rxnorm_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per RxNorm (NLM) - Farmaci e interazioni."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            if method_name in ("resolve_rxcui", "get_rxcui"):
                drug_name = arguments.get("drug_name", "aspirin")
                response = await client.get(
                    "https://rxnav.nlm.nih.gov/REST/rxcui.json",
                    params={"name": drug_name, "search": 1},
                )
                response.raise_for_status()
                data = response.json()
                ids = data.get("idGroup", {}).get("rxnormId", [])
                return {
                    "drug_name": drug_name,
                    "rxcui": ids[0] if ids else None,
                    "source": "RxNorm",
                }
            elif method_name == "get_drug_info":
                rxcui = arguments.get("rxcui", "1049221")
                response = await client.get(
                    f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json"
                )
                response.raise_for_status()
                props = response.json().get("properties", {})
                return {
                    "rxcui": rxcui,
                    "name": props.get("name"),
                    "tty": props.get("tty"),
                    "source": "RxNorm",
                }
            elif method_name == "get_interactions":
                rxcui = arguments.get("rxcui", "1049221")
                response = await client.get(
                    "https://rxnav.nlm.nih.gov/REST/interaction/interaction.json",
                    params={"rxcui": rxcui},
                )
                response.raise_for_status()
                data = response.json()
                interactions = data.get("interactionTypeGroup", [])
                if interactions:
                    pairs = (
                        interactions[0]
                        .get("interactionType", [{}])[0]
                        .get("interactionPair", [])[:5]
                    )
                    return {
                        "rxcui": rxcui,
                        "interactions": [
                            {"description": p.get("description", "")[:200]} for p in pairs
                        ],
                        "source": "RxNorm",
                    }
                return {"rxcui": rxcui, "interactions": [], "source": "RxNorm"}
            else:
                return {"error": f"Unknown RxNorm method: {method_name}"}

    async def _icite_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per NIH iCite - Metriche citazioni paper."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            pmids = arguments.get("pmids", ["19304878"])
            if isinstance(pmids, str):
                pmids = [pmids]
            pmid_str = ",".join(str(p) for p in pmids[:50])

            response = await client.get(
                "https://icite.od.nih.gov/api/pubs",
                params={
                    "pmids": pmid_str,
                    "fl": "pmid,relative_citation_ratio,apt,citation_count,nih_percentile,is_clinical",
                },
            )
            response.raise_for_status()
            data = response.json()

            metrics = {}
            for pub in data.get("data", []):
                pmid = str(pub.get("pmid", ""))
                metrics[pmid] = {
                    "rcr": pub.get("relative_citation_ratio"),
                    "apt": pub.get("apt"),
                    "citations": pub.get("citation_count"),
                    "percentile": pub.get("nih_percentile"),
                    "is_clinical": pub.get("is_clinical"),
                }

            return {"pmids": pmids, "metrics": metrics, "source": "NIH iCite"}

    # =========================================================================
    # FINANZA HANDLERS
    # =========================================================================

    async def _finnhub_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Finnhub API (richiede FINNHUB_API_KEY)."""
        import os

        api_key = os.getenv("FINNHUB_API_KEY") or os.getenv("FINNHUB_APY_KEY")
        if not api_key:
            return {"error": "FINNHUB_API_KEY not configured"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "get_quote":
                symbol = arguments.get("symbol", "AAPL").upper()
                response = await client.get(
                    "https://finnhub.io/api/v1/quote",
                    params={"symbol": symbol, "token": api_key},
                )
                response.raise_for_status()
                data = response.json()
                return {
                    "symbol": symbol,
                    "price": data.get("c"),
                    "change": data.get("d"),
                    "percent_change": data.get("dp"),
                    "high": data.get("h"),
                    "low": data.get("l"),
                    "open": data.get("o"),
                    "previous_close": data.get("pc"),
                    "source": "Finnhub",
                }
            elif method_name == "get_news":
                category = arguments.get("category", "general")
                response = await client.get(
                    "https://finnhub.io/api/v1/news",
                    params={"category": category, "token": api_key},
                )
                response.raise_for_status()
                news = response.json()[:5]
                return {
                    "category": category,
                    "articles": [
                        {"headline": n.get("headline"), "url": n.get("url")} for n in news
                    ],
                    "source": "Finnhub",
                }
            elif method_name == "get_company_profile":
                symbol = arguments.get("symbol", "AAPL").upper()
                response = await client.get(
                    "https://finnhub.io/api/v1/stock/profile2",
                    params={"symbol": symbol, "token": api_key},
                )
                response.raise_for_status()
                return {"profile": response.json(), "source": "Finnhub"}
            else:
                return {"error": f"Unknown Finnhub method: {method_name}"}

    async def _alphavantage_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Alpha Vantage API."""
        import os

        api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        if not api_key:
            return {"error": "ALPHA_VANTAGE_API_KEY not configured"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "get_quote":
                symbol = arguments.get("symbol", "AAPL").upper()
                response = await client.get(
                    "https://www.alphavantage.co/query",
                    params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": api_key},
                )
                response.raise_for_status()
                data = response.json().get("Global Quote", {})
                return {
                    "symbol": symbol,
                    "price": data.get("05. price"),
                    "change": data.get("09. change"),
                    "percent_change": data.get("10. change percent"),
                    "source": "Alpha Vantage",
                }
            elif method_name == "get_forex_rate":
                from_curr = arguments.get("from_currency", "EUR")
                to_curr = arguments.get("to_currency", "USD")
                response = await client.get(
                    "https://www.alphavantage.co/query",
                    params={
                        "function": "CURRENCY_EXCHANGE_RATE",
                        "from_currency": from_curr,
                        "to_currency": to_curr,
                        "apikey": api_key,
                    },
                )
                response.raise_for_status()
                data = response.json().get("Realtime Currency Exchange Rate", {})
                return {
                    "from": from_curr,
                    "to": to_curr,
                    "rate": data.get("5. Exchange Rate"),
                    "source": "Alpha Vantage",
                }
            else:
                return {"error": f"Unknown AlphaVantage method: {method_name}"}

    async def _polygon_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Polygon.io API."""
        import os

        api_key = os.getenv("POLYGON_API_KEY")
        if not api_key:
            return {"error": "POLYGON_API_KEY not configured"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name in ("get_ticker_details", "get_previous_close"):
                ticker = arguments.get("ticker", "AAPL").upper()
                response = await client.get(
                    f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev",
                    params={"apiKey": api_key},
                )
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [{}])[0] if data.get("results") else {}
                return {
                    "ticker": ticker,
                    "close": results.get("c"),
                    "open": results.get("o"),
                    "high": results.get("h"),
                    "low": results.get("l"),
                    "volume": results.get("v"),
                    "source": "Polygon",
                }
            else:
                return {"error": f"Unknown Polygon method: {method_name}"}

    async def _twelvedata_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per TwelveData API."""
        import os

        api_key = os.getenv("TWELVE_DATA_API_KEY")
        if not api_key:
            return {"error": "TWELVE_DATA_API_KEY not configured"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            symbol = arguments.get("symbol", "AAPL")
            response = await client.get(
                "https://api.twelvedata.com/price",
                params={"symbol": symbol, "apikey": api_key},
            )
            response.raise_for_status()
            data = response.json()
            return {"symbol": symbol, "price": data.get("price"), "source": "TwelveData"}

    async def _fred_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per FRED (Federal Reserve Economic Data)."""
        import os

        api_key = os.getenv("FRED_API_KEY")
        if not api_key:
            return {"error": "FRED_API_KEY not configured"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name in ("get_series", "get_data"):
                series_id = arguments.get("series_id", "GDP")  # GDP, UNRATE, etc.
                response = await client.get(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": api_key,
                        "file_type": "json",
                        "limit": 10,
                        "sort_order": "desc",
                    },
                )
                response.raise_for_status()
                data = response.json()
                observations = data.get("observations", [])[:5]
                return {
                    "series_id": series_id,
                    "observations": [
                        {"date": o.get("date"), "value": o.get("value")} for o in observations
                    ],
                    "source": "FRED",
                }
            elif method_name == "search":
                query = arguments.get("query", "unemployment")
                response = await client.get(
                    "https://api.stlouisfed.org/fred/series/search",
                    params={
                        "search_text": query,
                        "api_key": api_key,
                        "file_type": "json",
                        "limit": 5,
                    },
                )
                response.raise_for_status()
                series = response.json().get("seriess", [])[:5]
                return {
                    "query": query,
                    "series": [{"id": s.get("id"), "title": s.get("title")} for s in series],
                    "source": "FRED",
                }
            else:
                return {"error": f"Unknown FRED method: {method_name}"}

    async def _edgar_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per SEC EDGAR (filings aziendali USA)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"User-Agent": "Me4BrAIn/1.0 (research@example.com)"}

            if method_name in ("get_filings", "search_filings"):
                cik = arguments.get("cik", "0000320193")  # Apple default
                # Normalizza CIK a 10 cifre
                cik = cik.zfill(10) if cik.isdigit() else cik

                response = await client.get(
                    f"https://data.sec.gov/submissions/CIK{cik}.json",
                    headers=headers,
                )
                if response.status_code != 200:
                    return {"error": f"CIK not found: {cik}"}

                data = response.json()
                filings = data.get("filings", {}).get("recent", {})
                forms = filings.get("form", [])[:5]
                dates = filings.get("filingDate", [])[:5]
                descriptions = filings.get("primaryDocument", [])[:5]

                return {
                    "company": data.get("name"),
                    "cik": cik,
                    "recent_filings": [
                        {"form": f, "date": d, "doc": desc}
                        for f, d, desc in zip(forms, dates, descriptions)
                    ],
                    "source": "SEC EDGAR",
                }
            elif method_name == "get_company":
                ticker = arguments.get("ticker", "AAPL").upper()
                # Cerca company per ticker
                response = await client.get(
                    "https://www.sec.gov/cgi-bin/browse-edgar",
                    params={
                        "action": "getcompany",
                        "CIK": ticker,
                        "type": "10-K",
                        "output": "atom",
                    },
                    headers=headers,
                )
                # Parsing semplificato
                return {
                    "ticker": ticker,
                    "note": "Use CIK for detailed filings",
                    "source": "SEC EDGAR",
                }
            else:
                return {"error": f"Unknown EDGAR method: {method_name}"}

    async def _yfinance_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Yahoo Finance (via API pubblica query1)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name in ("get_quote", "get_price"):
                symbol = arguments.get("symbol", "AAPL").upper()

                # Yahoo Finance API pubblica (non ufficiale ma funzionante)
                response = await client.get(
                    "https://query1.finance.yahoo.com/v8/finance/chart/" + symbol,
                    params={"interval": "1d", "range": "1d"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )

                if response.status_code != 200:
                    return {"error": f"Symbol not found: {symbol}"}

                data = response.json()
                result = data.get("chart", {}).get("result", [{}])[0]
                meta = result.get("meta", {})

                return {
                    "symbol": symbol,
                    "price": meta.get("regularMarketPrice"),
                    "previous_close": meta.get("previousClose"),
                    "currency": meta.get("currency"),
                    "exchange": meta.get("exchangeName"),
                    "source": "Yahoo Finance",
                }
            elif method_name == "get_info":
                symbol = arguments.get("symbol", "AAPL").upper()
                response = await client.get(
                    f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{symbol}",
                    params={"modules": "assetProfile,summaryDetail"},
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if response.status_code != 200:
                    return {"error": f"Symbol not found: {symbol}"}

                data = response.json()
                summary = data.get("quoteSummary", {}).get("result", [{}])[0]
                profile = summary.get("assetProfile", {})
                detail = summary.get("summaryDetail", {})

                return {
                    "symbol": symbol,
                    "industry": profile.get("industry"),
                    "sector": profile.get("sector"),
                    "market_cap": detail.get("marketCap", {}).get("raw"),
                    "source": "Yahoo Finance",
                }
            elif method_name == "get_history":
                # Storico prezzi azioni
                symbol = arguments.get("symbol", "AAPL").upper()
                period = arguments.get("period", "2y")  # 1y, 2y, 5y, max
                interval = arguments.get("interval", "1wk")  # 1d, 1wk, 1mo

                response = await client.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                    params={"interval": interval, "range": period},
                    headers={"User-Agent": "Mozilla/5.0"},
                )

                if response.status_code != 200:
                    return {"error": f"Symbol not found: {symbol}"}

                data = response.json()
                result = data.get("chart", {}).get("result", [{}])[0]
                quotes = result.get("indicators", {}).get("quote", [{}])[0]
                timestamps = result.get("timestamp", [])

                # Costruisci serie temporale
                prices = []
                closes = quotes.get("close", [])
                for i, ts in enumerate(timestamps):
                    if i < len(closes) and closes[i] is not None:
                        prices.append({"timestamp": ts, "price": round(closes[i], 2)})

                return {
                    "symbol": symbol,
                    "period": period,
                    "interval": interval,
                    "data_points": len(prices),
                    "prices": prices,
                    "source": "Yahoo Finance",
                }
            else:
                return {"error": f"Unknown YahooFinance method: {method_name}"}

    # =========================================================================
    # GEO/UTILITY HANDLERS
    # =========================================================================

    async def _nominatim_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Nominatim (OpenStreetMap geocoding)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"User-Agent": "Me4BrAIn/1.0"}
            if method_name == "geocode":
                query = arguments.get("query", "Roma, Italia")
                response = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": query, "format": "json", "limit": 1},
                    headers=headers,
                )
                response.raise_for_status()
                results = response.json()
                if results:
                    r = results[0]
                    return {
                        "query": query,
                        "lat": r.get("lat"),
                        "lon": r.get("lon"),
                        "display_name": r.get("display_name"),
                        "source": "Nominatim",
                    }
                return {"query": query, "error": "Not found"}
            elif method_name == "reverse_geocode":
                lat = arguments.get("latitude", 41.9028)
                lon = arguments.get("longitude", 12.4964)
                response = await client.get(
                    "https://nominatim.openstreetmap.org/reverse",
                    params={"lat": lat, "lon": lon, "format": "json"},
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                return {
                    "lat": lat,
                    "lon": lon,
                    "address": data.get("display_name"),
                    "source": "Nominatim",
                }
            else:
                return {"error": f"Unknown Nominatim method: {method_name}"}

    async def _sunrise_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Sunrise-Sunset API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            lat = arguments.get("latitude", 41.9028)
            lon = arguments.get("longitude", 12.4964)
            response = await client.get(
                "https://api.sunrise-sunset.org/json",
                params={"lat": lat, "lng": lon, "formatted": 0},
            )
            response.raise_for_status()
            data = response.json().get("results", {})
            return {
                "sunrise": data.get("sunrise"),
                "sunset": data.get("sunset"),
                "source": "Sunrise-Sunset API",
            }

    # =========================================================================
    # NEWS/RICERCA HANDLERS
    # =========================================================================

    async def _hackernews_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Hacker News API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "get_top_stories_full":
                # Get top story IDs
                response = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
                response.raise_for_status()
                story_ids = response.json()[:5]  # Top 5

                stories = []
                for sid in story_ids:
                    story_resp = await client.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{sid}.json"
                    )
                    if story_resp.status_code == 200:
                        s = story_resp.json()
                        stories.append(
                            {"title": s.get("title"), "url": s.get("url"), "score": s.get("score")}
                        )

                return {"stories": stories, "source": "Hacker News"}
            else:
                return {"error": f"Unknown HackerNews method: {method_name}"}

    async def _newsdata_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per NewsData API."""
        import os

        api_key = os.getenv("NEWSDATA_API_KEY")
        if not api_key:
            return {"error": "NEWSDATA_API_KEY not configured", "note": "Fallback to HackerNews"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            query = arguments.get("query", "technology")
            response = await client.get(
                "https://newsdata.io/api/1/news",
                params={"apikey": api_key, "q": query, "language": "en"},
            )
            response.raise_for_status()
            articles = response.json().get("results", [])[:5]
            return {
                "query": query,
                "articles": [{"title": a.get("title"), "link": a.get("link")} for a in articles],
                "source": "NewsData",
            }

    # =========================================================================
    # ENCICLOPEDIA HANDLERS
    # =========================================================================

    async def _wikipedia_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Wikipedia API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "get_summary":
                title = arguments.get("title", "Python_(programming_language)")
                response = await client.get(
                    f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "title": data.get("title"),
                        "extract": data.get("extract"),
                        "source": "Wikipedia",
                    }
                return {"error": f"Article not found: {title}"}
            elif method_name == "search":
                query = arguments.get("query", "python")
                response = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={"action": "opensearch", "search": query, "limit": 5, "format": "json"},
                )
                response.raise_for_status()
                data = response.json()
                return {
                    "query": query,
                    "results": data[1] if len(data) > 1 else [],
                    "source": "Wikipedia",
                }
            else:
                return {"error": f"Unknown Wikipedia method: {method_name}"}

    async def _openlibrary_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Open Library API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "search_books":
                query = arguments.get("query", "python")
                response = await client.get(
                    "https://openlibrary.org/search.json",
                    params={"q": query, "limit": 5},
                )
                response.raise_for_status()
                docs = response.json().get("docs", [])[:5]
                return {
                    "query": query,
                    "books": [
                        {"title": d.get("title"), "author": d.get("author_name", [None])[0]}
                        for d in docs
                    ],
                    "source": "Open Library",
                }
            elif method_name == "get_book_by_isbn":
                isbn = arguments.get("isbn", "9780140449136")
                response = await client.get(f"https://openlibrary.org/isbn/{isbn}.json")
                if response.status_code == 200:
                    return {"isbn": isbn, "book": response.json(), "source": "Open Library"}
                return {"error": f"ISBN not found: {isbn}"}
            else:
                return {"error": f"Unknown OpenLibrary method: {method_name}"}

    # =========================================================================
    # UTILITY/SCIENZA HANDLERS
    # =========================================================================

    async def _nasa_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per NASA API."""
        import os

        api_key = os.getenv("NASA_API_KEY", "DEMO_KEY")

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "get_apod":
                response = await client.get(
                    "https://api.nasa.gov/planetary/apod",
                    params={"api_key": api_key},
                )
                response.raise_for_status()
                data = response.json()
                return {
                    "title": data.get("title"),
                    "explanation": data.get("explanation")[:300],
                    "url": data.get("url"),
                    "source": "NASA APOD",
                }
            elif method_name == "search_images":
                query = arguments.get("query", "mars")
                response = await client.get(
                    "https://images-api.nasa.gov/search",
                    params={"q": query, "media_type": "image"},
                )
                response.raise_for_status()
                items = response.json().get("collection", {}).get("items", [])[:5]
                return {
                    "query": query,
                    "images": [{"title": i.get("data", [{}])[0].get("title")} for i in items],
                    "source": "NASA Images",
                }
            else:
                return {"error": f"Unknown NASA method: {method_name}"}

    async def _httpbin_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per httpbin (testing)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            if method_name == "get_ip":
                response = await client.get("https://httpbin.org/ip")
                response.raise_for_status()
                return {"ip": response.json().get("origin"), "source": "httpbin"}
            return {"error": f"Unknown httpbin method: {method_name}"}

    async def _ipify_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per ipify."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://api.ipify.org?format=json")
            response.raise_for_status()
            return {"ip": response.json().get("ip"), "source": "ipify"}

    async def _arxiv_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per arXiv API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            query = arguments.get("query", "machine learning")
            response = await client.get(
                "http://export.arxiv.org/api/query",
                params={"search_query": f"all:{query}", "max_results": 5},
            )
            response.raise_for_status()
            # Parse XML (simplified)
            import re

            titles = re.findall(r"<title>([^<]+)</title>", response.text)[1:6]  # Skip feed title
            return {"query": query, "papers": titles, "source": "arXiv"}

    # =========================================================================
    # UTILITY FREE APIs (No API Key)
    # =========================================================================

    async def _agify_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Agify.io - Predici età da nome."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            name = arguments.get("name", "Michael")
            response = await client.get(
                "https://api.agify.io",
                params={"name": name},
            )
            response.raise_for_status()
            data = response.json()
            return {
                "name": name,
                "age": data.get("age"),
                "count": data.get("count"),
                "source": "Agify",
            }

    async def _genderize_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Genderize.io - Predici genere da nome."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            name = arguments.get("name", "Michael")
            response = await client.get(
                "https://api.genderize.io",
                params={"name": name},
            )
            response.raise_for_status()
            data = response.json()
            return {
                "name": name,
                "gender": data.get("gender"),
                "probability": data.get("probability"),
                "source": "Genderize",
            }

    async def _restcountries_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per RestCountries - Info paesi."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            if method_name == "get_by_name":
                name = arguments.get("name", "Italy")
                response = await client.get(f"https://restcountries.com/v3.1/name/{name}")
                if response.status_code != 200:
                    return {"error": f"Country not found: {name}"}
                data = response.json()[0]
                return {
                    "name": data.get("name", {}).get("common"),
                    "capital": data.get("capital", [None])[0],
                    "population": data.get("population"),
                    "region": data.get("region"),
                    "currencies": list(data.get("currencies", {}).keys()),
                    "source": "RestCountries",
                }
            else:
                return {"error": f"Unknown RestCountries method: {method_name}"}

    async def _nagerdate_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Nager.Date - Festività per paese."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            year = arguments.get("year", 2026)
            country = arguments.get("country_code", "IT")
            response = await client.get(
                f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
            )
            if response.status_code != 200:
                return {"error": f"Holidays not found for {country}/{year}"}
            holidays = response.json()[:10]
            return {
                "country": country,
                "year": year,
                "holidays": [{"date": h.get("date"), "name": h.get("localName")} for h in holidays],
                "source": "Nager.Date",
            }

    async def _usgs_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per USGS Earthquake - Terremoti recenti."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson"
            )
            response.raise_for_status()
            data = response.json()
            features = data.get("features", [])[:5]
            return {
                "earthquakes": [
                    {
                        "magnitude": f.get("properties", {}).get("mag"),
                        "place": f.get("properties", {}).get("place"),
                        "time": f.get("properties", {}).get("time"),
                    }
                    for f in features
                ],
                "source": "USGS Earthquake",
            }

    async def _randomuser_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per RandomUser.me - Genera utenti fake."""
        async with httpx.AsyncClient(timeout=15.0) as client:
            count = min(arguments.get("count", 1), 5)
            response = await client.get(
                "https://randomuser.me/api/",
                params={"results": count},
            )
            response.raise_for_status()
            users = response.json().get("results", [])
            return {
                "users": [
                    {
                        "name": f"{u.get('name', {}).get('first')} {u.get('name', {}).get('last')}",
                        "email": u.get("email"),
                        "country": u.get("location", {}).get("country"),
                    }
                    for u in users
                ],
                "source": "RandomUser",
            }

    # =========================================================================
    # ACCADEMIA (FREE APIs)
    # =========================================================================

    async def _crossref_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Crossref - DOI e paper."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "search":
                query = arguments.get("query", "machine learning")
                response = await client.get(
                    "https://api.crossref.org/works",
                    params={"query": query, "rows": 5},
                )
                response.raise_for_status()
                items = response.json().get("message", {}).get("items", [])[:5]
                return {
                    "query": query,
                    "papers": [
                        {"title": i.get("title", [""])[0], "doi": i.get("DOI")} for i in items
                    ],
                    "source": "Crossref",
                }
            elif method_name == "get_by_doi":
                doi = arguments.get("doi", "10.1038/nature12373")
                response = await client.get(f"https://api.crossref.org/works/{doi}")
                if response.status_code != 200:
                    return {"error": f"DOI not found: {doi}"}
                data = response.json().get("message", {})
                return {
                    "doi": doi,
                    "title": data.get("title", [""])[0],
                    "authors": [a.get("family") for a in data.get("author", [])[:3]],
                    "source": "Crossref",
                }
            else:
                return {"error": f"Unknown Crossref method: {method_name}"}

    async def _semanticscholar_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Semantic Scholar - Paper accademici."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "search_papers":
                query = arguments.get("query", "deep learning")
                response = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params={"query": query, "limit": 5, "fields": "title,year,citationCount"},
                )
                response.raise_for_status()
                papers = response.json().get("data", [])
                return {
                    "query": query,
                    "papers": [
                        {
                            "title": p.get("title"),
                            "year": p.get("year"),
                            "citations": p.get("citationCount"),
                        }
                        for p in papers
                    ],
                    "source": "Semantic Scholar",
                }
            elif method_name == "get_paper":
                paper_id = arguments.get("paper_id", "649def34f8be52c8b66281af98ae884c09aef38b")
                response = await client.get(
                    f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}",
                    params={"fields": "title,abstract,year,citationCount"},
                )
                if response.status_code != 200:
                    return {"error": f"Paper not found: {paper_id}"}
                data = response.json()
                return {
                    "title": data.get("title"),
                    "abstract": (data.get("abstract") or "")[:300],
                    "source": "Semantic Scholar",
                }
            else:
                return {"error": f"Unknown SemanticScholar method: {method_name}"}

    async def _europepmc_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Europe PMC - Paper biomedici."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            query = arguments.get("query", "cancer treatment")
            response = await client.get(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                params={"query": query, "format": "json", "pageSize": 5},
            )
            response.raise_for_status()
            results = response.json().get("resultList", {}).get("result", [])
            return {
                "query": query,
                "papers": [{"title": r.get("title"), "pmid": r.get("pmid")} for r in results],
                "source": "Europe PMC",
            }

    async def _pubmed_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per PubMed - Abstract medici."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "search":
                query = arguments.get("query", "diabetes")
                response = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={"db": "pubmed", "term": query, "retmax": 5, "retmode": "json"},
                )
                response.raise_for_status()
                ids = response.json().get("esearchresult", {}).get("idlist", [])
                return {"query": query, "pmids": ids, "source": "PubMed"}
            elif method_name == "fetch_abstracts":
                pmids = arguments.get("pmids", ["12345678"])
                if isinstance(pmids, list):
                    pmids = ",".join(pmids)
                response = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                    params={"db": "pubmed", "id": pmids, "rettype": "abstract", "retmode": "text"},
                )
                response.raise_for_status()
                return {"pmids": pmids, "abstract": response.text[:500], "source": "PubMed"}
            else:
                return {"error": f"Unknown PubMed method: {method_name}"}

    async def _openalex_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per OpenAlex - Knowledge graph accademico."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "search_works":
                query = arguments.get("query", "artificial intelligence")
                response = await client.get(
                    "https://api.openalex.org/works",
                    params={"search": query, "per_page": 5},
                )
                response.raise_for_status()
                works = response.json().get("results", [])
                return {
                    "query": query,
                    "works": [
                        {"title": w.get("title"), "cited_by": w.get("cited_by_count")}
                        for w in works
                    ],
                    "source": "OpenAlex",
                }
            elif method_name == "search_authors":
                query = arguments.get("query", "John Smith")
                response = await client.get(
                    "https://api.openalex.org/authors",
                    params={"search": query, "per_page": 5},
                )
                response.raise_for_status()
                authors = response.json().get("results", [])
                return {
                    "query": query,
                    "authors": [
                        {"name": a.get("display_name"), "works_count": a.get("works_count")}
                        for a in authors
                    ],
                    "source": "OpenAlex",
                }
            else:
                return {"error": f"Unknown OpenAlex method: {method_name}"}

    # =========================================================================
    # SPORT (FREE APIs)
    # =========================================================================

    async def _balldontlie_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per BallDontLie API v2 - NBA stats con autenticazione."""
        import os
        from datetime import datetime, timedelta

        api_key = os.getenv("BALLDONTLIE_API_KEY")
        if not api_key:
            return {"error": "BALLDONTLIE_API_KEY not configured in .env"}

        headers = {"Authorization": api_key}
        base_url = "https://api.balldontlie.io/v1"

        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            try:
                if method_name in ("get_games", "upcoming_games"):
                    # Prossime partite - oggi e prossimi 3 giorni
                    today = datetime.now()
                    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(4)]

                    all_games = []
                    for date in dates:
                        response = await client.get(
                            f"{base_url}/games",
                            params={"dates[]": date, "per_page": 20},
                        )
                        if response.status_code == 200:
                            games = response.json().get("data", [])
                            for g in games:
                                all_games.append(
                                    {
                                        "id": g.get("id"),
                                        "date": g.get("date"),
                                        "status": g.get("status"),
                                        "home_team": g.get("home_team", {}).get("full_name"),
                                        "away_team": g.get("visitor_team", {}).get("full_name"),
                                        "home_score": g.get("home_team_score"),
                                        "away_score": g.get("visitor_team_score"),
                                    }
                                )

                    return {
                        "games": all_games,
                        "count": len(all_games),
                        "date_range": f"{dates[0]} to {dates[-1]}",
                        "source": "BallDontLie API v2",
                    }

                elif method_name == "get_players":
                    search = arguments.get("search", arguments.get("query", "LeBron"))
                    response = await client.get(
                        f"{base_url}/players",
                        params={"search": search, "per_page": 10},
                    )
                    response.raise_for_status()
                    players = response.json().get("data", [])
                    return {
                        "search": search,
                        "players": [
                            {
                                "id": p.get("id"),
                                "name": f"{p.get('first_name')} {p.get('last_name')}",
                                "team": p.get("team", {}).get("full_name"),
                                "position": p.get("position"),
                                "height": p.get("height"),
                            }
                            for p in players
                        ],
                        "source": "BallDontLie API v2",
                    }

                elif method_name in ("get_stats", "player_stats", "season_averages"):
                    # Statistiche giocatore
                    player_id = arguments.get("player_id")
                    season = arguments.get("season", 2025)

                    if player_id:
                        response = await client.get(
                            f"{base_url}/season_averages",
                            params={"player_ids[]": player_id, "season": season},
                        )
                        if response.status_code == 200:
                            stats = response.json().get("data", [])
                            return {
                                "player_id": player_id,
                                "season": season,
                                "stats": stats,
                                "source": "BallDontLie API v2",
                            }

                    return {"error": "player_id required for stats"}

                elif method_name == "get_teams":
                    response = await client.get(f"{base_url}/teams")
                    response.raise_for_status()
                    teams = response.json().get("data", [])
                    return {
                        "teams": [
                            {
                                "id": t.get("id"),
                                "name": t.get("full_name"),
                                "abbreviation": t.get("abbreviation"),
                                "conference": t.get("conference"),
                                "division": t.get("division"),
                            }
                            for t in teams
                        ],
                        "source": "BallDontLie API v2",
                    }

                else:
                    return {"error": f"Unknown BallDontLie method: {method_name}"}

            except httpx.HTTPStatusError as e:
                logger.error("balldontlie_api_error", status=e.response.status_code)
                return {"error": f"BallDontLie API error: {e.response.status_code}"}
            except Exception as e:
                logger.error("balldontlie_error", error=str(e))
                return {"error": str(e), "source": "BallDontLie"}

    # =========================================================================
    # SPORTS BETTING HANDLERS (The Odds API)
    # =========================================================================

    async def _theoddsapi_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per The Odds API - Quote scommesse NBA e altri sport."""
        import os

        api_key = os.getenv("THE_ODDS_API_KEY")
        if not api_key:
            return {"error": "THE_ODDS_API_KEY not configured in .env"}

        base_url = "https://api.the-odds-api.com/v4"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if method_name in ("get_sports", "list_sports"):
                    response = await client.get(
                        f"{base_url}/sports",
                        params={"apiKey": api_key},
                    )
                    response.raise_for_status()
                    sports = response.json()
                    return {
                        "sports": [
                            {
                                "key": s.get("key"),
                                "title": s.get("title"),
                                "active": s.get("active"),
                            }
                            for s in sports
                            if s.get("active")
                        ],
                        "count": len([s for s in sports if s.get("active")]),
                        "source": "The Odds API",
                    }

                elif method_name in ("get_odds", "nba_odds"):
                    sport = arguments.get("sport", "basketball_nba")
                    regions = arguments.get("regions", "eu")  # eu, us, uk, au
                    markets = arguments.get("markets", "h2h,spreads,totals")

                    response = await client.get(
                        f"{base_url}/sports/{sport}/odds",
                        params={
                            "apiKey": api_key,
                            "regions": regions,
                            "markets": markets,
                            "oddsFormat": "decimal",
                        },
                    )

                    if response.status_code != 200:
                        return {
                            "error": f"API error: {response.status_code}",
                            "source": "The Odds API",
                        }

                    events = response.json()
                    formatted = []
                    for event in events[:10]:  # Limita a 10 partite
                        game_data = {
                            "id": event.get("id"),
                            "home_team": event.get("home_team"),
                            "away_team": event.get("away_team"),
                            "commence_time": event.get("commence_time"),
                            "bookmakers": [],
                        }

                        for bookie in event.get("bookmakers", [])[:3]:  # Top 3 bookmaker
                            bookie_data = {"name": bookie.get("title"), "markets": {}}
                            for market in bookie.get("markets", []):
                                market_key = market.get("key")
                                outcomes = {
                                    o.get("name"): o.get("price")
                                    for o in market.get("outcomes", [])
                                }
                                bookie_data["markets"][market_key] = outcomes
                            game_data["bookmakers"].append(bookie_data)

                        formatted.append(game_data)

                    return {
                        "sport": sport,
                        "events": formatted,
                        "count": len(events),
                        "source": "The Odds API",
                    }

                else:
                    return {"error": f"Unknown TheOddsAPI method: {method_name}"}

            except Exception as e:
                logger.error("theoddsapi_error", error=str(e))
                return {"error": str(e), "source": "The Odds API"}

    # =========================================================================
    # ESPN SPORTS HANDLERS (Free scraping)
    # =========================================================================

    async def _espn_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per ESPN - Scoreboard NBA e infortuni (scraping)."""
        from bs4 import BeautifulSoup

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                if method_name in ("get_scoreboard", "scoreboard", "nba_scoreboard"):
                    # ESPN API pubblica per scoreboard
                    response = await client.get(
                        "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard",
                        headers={"Origin": "https://www.espn.com"},
                    )
                    if response.status_code != 200:
                        return {"error": f"ESPN API error: {response.status_code}"}

                    data = response.json()
                    events = data.get("events", [])
                    games = []
                    for event in events:
                        competition = event.get("competitions", [{}])[0]
                        competitors = competition.get("competitors", [])

                        home = next((c for c in competitors if c.get("homeAway") == "home"), {})
                        away = next((c for c in competitors if c.get("homeAway") == "away"), {})

                        games.append(
                            {
                                "name": event.get("name"),
                                "date": event.get("date"),
                                "status": event.get("status", {}).get("type", {}).get("name"),
                                "home_team": home.get("team", {}).get("displayName"),
                                "home_score": home.get("score"),
                                "away_team": away.get("team", {}).get("displayName"),
                                "away_score": away.get("score"),
                                "venue": competition.get("venue", {}).get("fullName"),
                            }
                        )

                    return {
                        "games": games,
                        "count": len(games),
                        "source": "ESPN API",
                    }

                elif method_name in ("get_injuries", "nba_injuries"):
                    # Scrape pagina infortuni ESPN
                    response = await client.get(
                        "https://www.espn.com/nba/injuries",
                        headers={
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                        },
                    )
                    if response.status_code != 200:
                        return {"error": f"ESPN injuries page error: {response.status_code}"}

                    soup = BeautifulSoup(response.text, "html.parser")
                    injuries = []

                    # Parse tabelle infortuni
                    tables = soup.find_all("table", class_="Table")
                    for table in tables:
                        rows = table.find_all("tr")
                        for row in rows:
                            cols = row.find_all("td")
                            if len(cols) >= 2:
                                name = cols[0].get_text(strip=True)
                                if name and name != "NAME":
                                    injuries.append(
                                        {
                                            "player": name,
                                            "status": cols[1].get_text(strip=True)
                                            if len(cols) > 1
                                            else "",
                                            "details": cols[3].get_text(strip=True)
                                            if len(cols) > 3
                                            else "",
                                            "source": "ESPN",
                                        }
                                    )

                    return {
                        "injuries": injuries[:30],  # Limita a 30
                        "count": len(injuries),
                        "source": "ESPN Injuries",
                    }

                else:
                    return {"error": f"Unknown ESPN method: {method_name}"}

            except Exception as e:
                logger.error("espn_handler_error", error=str(e))
                return {"error": str(e), "source": "ESPN"}

    # =========================================================================
    # TRADING HANDLERS (with API keys)
    # =========================================================================

    async def _hyperliquid_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Hyperliquid (Testnet) - Crypto perpetual trading."""
        import os

        base_url = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid-testnet.xyz")

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name in ("get_candles", "get_ohlcv"):
                symbol = arguments.get("symbol", "BTC")
                interval = arguments.get("interval", "1h")

                # Hyperliquid uses Info API for market data
                response = await client.post(
                    f"{base_url}/info",
                    json={
                        "type": "candleSnapshot",
                        "req": {
                            "coin": symbol,
                            "interval": interval,
                            "startTime": arguments.get("start_time", 0),
                            "endTime": arguments.get("end_time", 0),
                        },
                    },
                )
                if response.status_code != 200:
                    return {"error": f"Hyperliquid API error: {response.status_code}"}

                candles = response.json()
                return {
                    "symbol": symbol,
                    "interval": interval,
                    "candles": candles[:10] if isinstance(candles, list) else [],
                    "source": "Hyperliquid",
                }
            elif method_name == "get_mids":
                # Get all mid prices
                response = await client.post(
                    f"{base_url}/info",
                    json={"type": "allMids"},
                )
                if response.status_code != 200:
                    return {"error": f"Hyperliquid API error: {response.status_code}"}

                mids = response.json()
                return {"mids": mids, "source": "Hyperliquid"}
            elif method_name == "get_meta":
                # Get exchange metadata (assets, leverage, etc)
                response = await client.post(
                    f"{base_url}/info",
                    json={"type": "meta"},
                )
                if response.status_code != 200:
                    return {"error": f"Hyperliquid API error: {response.status_code}"}

                meta = response.json()
                return {"meta": meta, "source": "Hyperliquid"}
            else:
                return {"error": f"Unknown Hyperliquid method: {method_name}"}

    async def _alpaca_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Alpaca (Paper Trading) - Stock trading."""
        import os

        api_key = os.getenv("ALPACA_API_KEY")
        secret_key = os.getenv("ALPACA_SECRET_KEY")
        base_url = os.getenv("ALPACA_ENDPOINT", "https://paper-api.alpaca.markets/v2")

        if not api_key or not secret_key:
            return {"error": "ALPACA_API_KEY and ALPACA_SECRET_KEY not configured"}

        headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }

        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            if method_name == "get_account":
                response = await client.get(f"{base_url}/account")
                if response.status_code != 200:
                    return {"error": f"Alpaca API error: {response.status_code}"}

                account = response.json()
                return {
                    "equity": account.get("equity"),
                    "buying_power": account.get("buying_power"),
                    "cash": account.get("cash"),
                    "portfolio_value": account.get("portfolio_value"),
                    "status": account.get("status"),
                    "source": "Alpaca Paper",
                }
            elif method_name == "get_positions":
                response = await client.get(f"{base_url}/positions")
                if response.status_code != 200:
                    return {"error": f"Alpaca API error: {response.status_code}"}

                positions = response.json()
                return {
                    "positions": [
                        {
                            "symbol": p.get("symbol"),
                            "qty": p.get("qty"),
                            "market_value": p.get("market_value"),
                            "unrealized_pl": p.get("unrealized_pl"),
                        }
                        for p in positions[:10]
                    ],
                    "source": "Alpaca Paper",
                }
            elif method_name == "get_quote":
                symbol = arguments.get("symbol", "AAPL").upper()
                # Use data API for quotes
                data_url = "https://data.alpaca.markets/v2"
                response = await client.get(f"{data_url}/stocks/{symbol}/quotes/latest")
                if response.status_code != 200:
                    return {"error": f"Alpaca quote error: {response.status_code}"}

                data = response.json()
                quote = data.get("quote", {})
                return {
                    "symbol": symbol,
                    "bid": quote.get("bp"),
                    "ask": quote.get("ap"),
                    "bid_size": quote.get("bs"),
                    "ask_size": quote.get("as"),
                    "source": "Alpaca",
                }
            elif method_name == "get_bars":
                symbol = arguments.get("symbol", "AAPL").upper()
                timeframe = arguments.get("timeframe", "1Day")
                data_url = "https://data.alpaca.markets/v2"
                response = await client.get(
                    f"{data_url}/stocks/{symbol}/bars",
                    params={"timeframe": timeframe, "limit": 10},
                )
                if response.status_code != 200:
                    return {"error": f"Alpaca bars error: {response.status_code}"}

                data = response.json()
                bars = data.get("bars", [])
                return {
                    "symbol": symbol,
                    "bars": [
                        {
                            "time": b.get("t"),
                            "open": b.get("o"),
                            "high": b.get("h"),
                            "low": b.get("l"),
                            "close": b.get("c"),
                        }
                        for b in bars
                    ],
                    "source": "Alpaca",
                }
            else:
                return {"error": f"Unknown Alpaca method: {method_name}"}

    async def _binance_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Binance API - Crypto market data (storico illimitato).

        Metodi supportati:
        - get_klines: Candlestick/Klines (storico fino a 5 anni)
        - get_price: Prezzo corrente
        - get_ticker_24h: Statistiche 24h
        """
        import os

        # Binance non richiede auth per dati pubblici
        base_url = "https://api.binance.com/api/v3"

        async with httpx.AsyncClient(timeout=30.0) as client:
            if method_name == "get_klines":
                # Storico crypto - klines/candlestick
                symbol = arguments.get("symbol", "BTCUSDT").upper()
                interval = arguments.get("interval", "1w")  # 1m, 1h, 1d, 1w, 1M
                limit = arguments.get("limit", 104)  # Max 1000, default 2 anni settimanali

                response = await client.get(
                    f"{base_url}/klines",
                    params={"symbol": symbol, "interval": interval, "limit": limit},
                )

                if response.status_code != 200:
                    return {"error": f"Binance API error: {response.status_code}"}

                klines = response.json()

                # Formatta i dati
                prices = []
                for k in klines:
                    prices.append(
                        {
                            "timestamp": int(k[0] / 1000),  # Open time (ms -> s)
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                        }
                    )

                return {
                    "symbol": symbol,
                    "interval": interval,
                    "data_points": len(prices),
                    "prices": prices,
                    "source": "Binance",
                }

            elif method_name == "get_price":
                symbol = arguments.get("symbol", "BTCUSDT").upper()
                response = await client.get(
                    f"{base_url}/ticker/price",
                    params={"symbol": symbol},
                )

                if response.status_code != 200:
                    return {"error": f"Binance price error: {response.status_code}"}

                data = response.json()
                return {
                    "symbol": symbol,
                    "price": float(data.get("price", 0)),
                    "source": "Binance",
                }

            elif method_name == "get_ticker_24h":
                symbol = arguments.get("symbol", "BTCUSDT").upper()
                response = await client.get(
                    f"{base_url}/ticker/24hr",
                    params={"symbol": symbol},
                )

                if response.status_code != 200:
                    return {"error": f"Binance 24h error: {response.status_code}"}

                data = response.json()
                return {
                    "symbol": symbol,
                    "price": float(data.get("lastPrice", 0)),
                    "change_24h": float(data.get("priceChangePercent", 0)),
                    "high_24h": float(data.get("highPrice", 0)),
                    "low_24h": float(data.get("lowPrice", 0)),
                    "volume_24h": float(data.get("volume", 0)),
                    "source": "Binance",
                }

            else:
                return {"error": f"Unknown Binance method: {method_name}"}

    # =========================================================================
    # NBA STATS HANDLER (Free via nba_api library)
    # =========================================================================

    async def _nba_stats_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per NBA Stats - Usa libreria gratuita nba_api."""
        from me4brain.integrations.public_apis import NBAStatsService

        service = NBAStatsService()

        if method_name == "search_players":
            query = arguments.get("query", "")
            return await service.search_players(query)

        elif method_name == "get_player_career_stats":
            player_id = arguments.get("player_id")
            if not player_id:
                return {"error": "player_id required"}
            return await service.get_player_career_stats(player_id)

        elif method_name == "get_teams":
            return await service.get_teams()

        elif method_name == "get_team_roster":
            team_id = arguments.get("team_id")
            season = arguments.get("season", "2024-25")
            if not team_id:
                return {"error": "team_id required"}
            return await service.get_team_roster(team_id, season)

        elif method_name == "get_game_boxscore":
            game_id = arguments.get("game_id")
            if not game_id:
                return {"error": "game_id required"}
            return await service.get_game_boxscore(game_id)

        elif method_name == "get_live_scoreboard":
            return await service.get_live_scoreboard()

        else:
            return {"error": f"Unknown NBA Stats method: {method_name}"}

    # =========================================================================
    # GOOGLE WORKSPACE HANDLERS (OAuth2)
    # =========================================================================

    def _get_google_credentials(self) -> Any:
        """Get Google OAuth2 credentials from environment or token file with auto-refresh."""
        import os
        import json
        from pathlib import Path

        # Try token.json first
        token_path = Path(os.getenv("GOOGLE_TOKEN_PATH", "data/google_token.json"))
        if token_path.exists():
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request

            with open(token_path) as f:
                token_data = json.load(f)

            # Validate required fields for refresh
            refresh_token = token_data.get("refresh_token")
            client_id = token_data.get("client_id") or os.getenv("GOOGLE_CLIENT_ID")
            client_secret = token_data.get("client_secret") or os.getenv("GOOGLE_CLIENT_SECRET")

            if not refresh_token:
                logger.warning(
                    "google_token_missing_refresh_token",
                    message="Token file missing refresh_token. Run: uv run python scripts/google_oauth_setup.py",
                    path=str(token_path),
                )

            if not client_id or not client_secret:
                logger.warning(
                    "google_oauth_missing_credentials",
                    message="Missing client_id or client_secret in token or .env",
                )

            creds = Credentials(
                token=token_data.get("token"),
                refresh_token=refresh_token,
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=client_id,
                client_secret=client_secret,
                scopes=token_data.get("scopes"),
            )

            # Auto-refresh if expired AND we have all required fields
            if creds.expired and creds.refresh_token and client_id and client_secret:
                try:
                    creds.refresh(Request())
                    # Save refreshed token
                    updated_token = {
                        "token": creds.token,
                        "refresh_token": creds.refresh_token,
                        "token_uri": creds.token_uri,
                        "client_id": creds.client_id,
                        "client_secret": creds.client_secret,
                        "scopes": list(creds.scopes) if creds.scopes else token_data.get("scopes"),
                        "expiry": creds.expiry.isoformat() if creds.expiry else None,
                    }
                    with open(token_path, "w") as f:
                        json.dump(updated_token, f, indent=2)
                    logger.info("google_token_refreshed", path=str(token_path))
                except Exception as e:
                    logger.error("google_token_refresh_failed", error=str(e))
                    return None

            return creds

        # Try service account
        sa_path = Path(os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "service_account.json"))
        if sa_path.exists():
            from google.oauth2 import service_account

            return service_account.Credentials.from_service_account_file(
                str(sa_path),
                scopes=[
                    "https://www.googleapis.com/auth/drive.readonly",
                    "https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/calendar.readonly",
                ],
            )

        return None

    async def _google_drive_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Google Drive - File e cartelle."""
        credentials = self._get_google_credentials()
        if not credentials:
            return {
                "error": "Google credentials not configured (GOOGLE_TOKEN_PATH or GOOGLE_SERVICE_ACCOUNT_PATH)"
            }

        from googleapiclient.discovery import build

        service = build("drive", "v3", credentials=credentials)

        if method_name == "list_files":
            folder_id = arguments.get("folder_id", "root")
            page_size = min(arguments.get("limit", 10), 50)

            results = (
                service.files()
                .list(
                    q=f"'{folder_id}' in parents and trashed = false",
                    pageSize=page_size,
                    fields="files(id, name, mimeType, modifiedTime, size)",
                )
                .execute()
            )

            files = results.get("files", [])
            return {
                "folder_id": folder_id,
                "files": [
                    {
                        "id": f.get("id"),
                        "name": f.get("name"),
                        "type": f.get("mimeType"),
                        "modified": f.get("modifiedTime"),
                        "size": f.get("size"),
                    }
                    for f in files
                ],
                "source": "Google Drive",
            }
        elif method_name == "get_file":
            file_id = arguments.get("file_id")
            if not file_id:
                return {"error": "file_id required"}

            file = (
                service.files()
                .get(fileId=file_id, fields="id, name, mimeType, webViewLink")
                .execute()
            )
            return {
                "id": file.get("id"),
                "name": file.get("name"),
                "type": file.get("mimeType"),
                "link": file.get("webViewLink"),
                "source": "Google Drive",
            }
        elif method_name == "search":
            query = arguments.get("query", "")
            logger.info("drive_search_comprehensive", query=query)

            all_files = []
            file_ids_seen = set()

            fields = "files(id, name, mimeType, modifiedTime, description, webViewLink, parents)"

            # 1. Trova cartelle che contengono la query nel nome
            folder_query = f"name contains '{query}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            try:
                folders_result = (
                    service.files()
                    .list(
                        q=folder_query,
                        pageSize=50,
                        fields="files(id, name)",
                    )
                    .execute()
                )
                folders = folders_result.get("files", [])
                logger.info("drive_folders_found", count=len(folders), query=query)

                # 2. Ottieni TUTTI i file dentro queste cartelle
                for folder in folders[:5]:  # Limita a 5 cartelle principali
                    folder_files_result = (
                        service.files()
                        .list(
                            q=f"'{folder['id']}' in parents and trashed=false",
                            pageSize=100,
                            fields=fields,
                        )
                        .execute()
                    )
                    for f in folder_files_result.get("files", []):
                        if f["id"] not in file_ids_seen:
                            file_ids_seen.add(f["id"])
                            all_files.append(f)
            except Exception as e:
                logger.warning("drive_folder_search_error", error=str(e))

            # 3. File con nome contenente la query (non solo cartelle)
            name_query = f"name contains '{query}' and mimeType!='application/vnd.google-apps.folder' and trashed=false"
            try:
                name_result = (
                    service.files()
                    .list(
                        q=name_query,
                        pageSize=50,
                        fields=fields,
                    )
                    .execute()
                )
                for f in name_result.get("files", []):
                    if f["id"] not in file_ids_seen:
                        file_ids_seen.add(f["id"])
                        all_files.append(f)
            except Exception as e:
                logger.warning("drive_name_search_error", error=str(e))

            # 4. File con contenuto indicizzato (fullText)
            content_query = f"fullText contains '{query}' and trashed=false"
            try:
                content_result = (
                    service.files()
                    .list(
                        q=content_query,
                        pageSize=50,
                        fields=fields,
                    )
                    .execute()
                )
                for f in content_result.get("files", []):
                    if f["id"] not in file_ids_seen:
                        file_ids_seen.add(f["id"])
                        all_files.append(f)
            except Exception as e:
                logger.warning("drive_content_search_error", error=str(e))

            # Ordina per data modifica (più recenti prima)
            all_files.sort(key=lambda x: x.get("modifiedTime", ""), reverse=True)

            logger.info("drive_search_complete", total_files=len(all_files), query=query)

            return {
                "query": query,
                "files": [
                    {
                        "id": f.get("id"),
                        "name": f.get("name"),
                        "type": f.get("mimeType"),
                        "modified": f.get("modifiedTime"),
                        "description": f.get("description", ""),
                        "link": f.get("webViewLink", ""),
                    }
                    for f in all_files[:50]  # Max 50 file nel risultato finale
                ],
                "count": len(all_files),
                "source": "Google Drive",
            }
        else:
            return {"error": f"Unknown Google Drive method: {method_name}"}

    async def _google_gmail_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Google Gmail - Email."""
        credentials = self._get_google_credentials()
        if not credentials:
            return {"error": "Google credentials not configured"}

        from googleapiclient.discovery import build

        service = build("gmail", "v1", credentials=credentials)

        if method_name == "search":
            query = arguments.get("query", "")
            max_results = min(arguments.get("limit", 10), 50)

            # Enhanced query: cerca in body, subject E come testo libero
            # Gmail operators: body:"term" cerca nel corpo, subject:"term" nell'oggetto
            if query and not any(
                op in query.lower() for op in ["body:", "subject:", "from:", "to:", "in:"]
            ):
                # Aggiungi operatori per ricerca completa se non già presenti
                enhanced_query = f'{query} OR body:"{query}" OR subject:"{query}"'
            else:
                enhanced_query = query

            logger.info("gmail_search_query", original=query, enhanced=enhanced_query)

            results = (
                service.users()
                .messages()
                .list(userId="me", q=enhanced_query, maxResults=max_results)
                .execute()
            )
            messages = results.get("messages", [])

            # Get snippets for each message
            email_summaries = []
            for msg in messages[:5]:  # Limit to 5 for speed
                detail = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg["id"], format="full")  # full per snippet
                    .execute()
                )
                headers = {
                    h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])
                }
                email_summaries.append(
                    {
                        "id": msg["id"],
                        "subject": headers.get("Subject", ""),
                        "from": headers.get("From", ""),
                        "date": headers.get("Date", ""),
                        "snippet": detail.get("snippet", ""),  # Preview contenuto email
                    }
                )

            return {"query": query, "emails": email_summaries, "source": "Gmail"}
        elif method_name == "get_message":
            message_id = arguments.get("message_id")
            if not message_id:
                return {"error": "message_id required"}

            msg = (
                service.users().messages().get(userId="me", id=message_id, format="full").execute()
            )
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}

            return {
                "id": message_id,
                "subject": headers.get("Subject", ""),
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", ""),
                "source": "Gmail",
            }
        else:
            return {"error": f"Unknown Gmail method: {method_name}"}

    async def _google_calendar_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Google Calendar - Eventi."""
        credentials = self._get_google_credentials()
        if not credentials:
            return {"error": "Google credentials not configured"}

        from googleapiclient.discovery import build
        from datetime import datetime, timedelta

        service = build("calendar", "v3", credentials=credentials)

        # NUOVO: Metodo search per ricerca testuale negli eventi
        if method_name == "search":
            query = arguments.get("query", "").strip()
            days_window = arguments.get("days", 365)  # ±365 giorni per eventi passati/futuri
            now = datetime.utcnow()

            # Cerca sia nel passato che nel futuro
            time_min = (now - timedelta(days=days_window)).isoformat() + "Z"
            time_max = (now + timedelta(days=days_window)).isoformat() + "Z"

            logger.info("calendar_search_query", query=query, days_window=days_window)

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    q=query,  # Parametro ricerca testuale
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=50,
                    singleEvents=True,
                    # orderBy non può essere "relevance" con singleEvents=True
                )
                .execute()
            )

            events = events_result.get("items", [])
            return {
                "query": query,
                "events_found": len(events),
                "events": [
                    {
                        "summary": e.get("summary", ""),
                        "description": e.get("description", "")[:200]
                        if e.get("description")
                        else "",
                        "start": e.get("start", {}).get(
                            "dateTime", e.get("start", {}).get("date", "")
                        ),
                        "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
                        "location": e.get("location", ""),
                        "attendees": [a.get("email") for a in e.get("attendees", [])][:5],
                    }
                    for e in events
                ],
                "source": "Google Calendar",
            }

        elif method_name == "upcoming":
            days = arguments.get("days", 7)
            now = datetime.utcnow()
            time_min = now.isoformat() + "Z"
            time_max = (now + timedelta(days=days)).isoformat() + "Z"

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=10,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )

            events = events_result.get("items", [])
            return {
                "days": days,
                "events": [
                    {
                        "summary": e.get("summary", ""),
                        "start": e.get("start", {}).get(
                            "dateTime", e.get("start", {}).get("date", "")
                        ),
                        "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
                        "location": e.get("location", ""),
                    }
                    for e in events
                ],
                "source": "Google Calendar",
            }
        elif method_name == "get_event":
            event_id = arguments.get("event_id")
            if not event_id:
                return {"error": "event_id required"}

            event = service.events().get(calendarId="primary", eventId=event_id).execute()
            return {
                "id": event_id,
                "summary": event.get("summary", ""),
                "start": event.get("start", {}),
                "end": event.get("end", {}),
                "attendees": [a.get("email") for a in event.get("attendees", [])],
                "source": "Google Calendar",
            }
        else:
            return {"error": f"Unknown Google Calendar method: {method_name}"}

    async def _google_docs_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Google Docs - Documenti."""
        credentials = self._get_google_credentials()
        if not credentials:
            return {"error": "Google credentials not configured"}

        from googleapiclient.discovery import build

        service = build("docs", "v1", credentials=credentials)

        if method_name == "get":
            document_id = arguments.get("document_id")
            if not document_id:
                return {"error": "document_id required"}

            doc = service.documents().get(documentId=document_id).execute()
            # Extract text content
            content = ""
            for element in doc.get("body", {}).get("content", []):
                if "paragraph" in element:
                    for text_run in element["paragraph"].get("elements", []):
                        if "textRun" in text_run:
                            content += text_run["textRun"].get("content", "")

            return {
                "id": document_id,
                "title": doc.get("title", ""),
                "content_preview": content[:500],
                "source": "Google Docs",
            }
        elif method_name == "create":
            title = arguments.get("title", "Untitled Document")
            doc = service.documents().create(body={"title": title}).execute()
            return {
                "id": doc.get("documentId"),
                "title": doc.get("title"),
                "source": "Google Docs",
            }
        else:
            return {"error": f"Unknown Google Docs method: {method_name}"}

    async def _google_sheets_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Google Sheets - Fogli di calcolo."""
        credentials = self._get_google_credentials()
        if not credentials:
            return {"error": "Google credentials not configured"}

        from googleapiclient.discovery import build

        service = build("sheets", "v4", credentials=credentials)

        if method_name == "get_values":
            spreadsheet_id = arguments.get("spreadsheet_id")
            range_name = arguments.get("range", "Sheet1!A1:Z100")
            if not spreadsheet_id:
                return {"error": "spreadsheet_id required"}

            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=range_name)
                .execute()
            )

            values = result.get("values", [])
            return {
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
                "rows": len(values),
                "values": values[:20],  # Limit to 20 rows
                "source": "Google Sheets",
            }
        elif method_name == "get_metadata":
            spreadsheet_id = arguments.get("spreadsheet_id")
            if not spreadsheet_id:
                return {"error": "spreadsheet_id required"}

            spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            sheets = [
                {
                    "title": s.get("properties", {}).get("title"),
                    "id": s.get("properties", {}).get("sheetId"),
                }
                for s in spreadsheet.get("sheets", [])
            ]
            return {
                "spreadsheet_id": spreadsheet_id,
                "title": spreadsheet.get("properties", {}).get("title"),
                "sheets": sheets,
                "source": "Google Sheets",
            }
        else:
            return {"error": f"Unknown Google Sheets method: {method_name}"}

    async def _google_slides_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Google Slides - Presentazioni."""
        credentials = self._get_google_credentials()
        if not credentials:
            return {"error": "Google credentials not configured"}

        from googleapiclient.discovery import build

        service = build("slides", "v1", credentials=credentials)

        if method_name == "get":
            presentation_id = arguments.get("presentation_id")
            if not presentation_id:
                return {"error": "presentation_id required"}

            presentation = service.presentations().get(presentationId=presentation_id).execute()
            slides = presentation.get("slides", [])
            return {
                "id": presentation_id,
                "title": presentation.get("title", ""),
                "slide_count": len(slides),
                "slides": [
                    {
                        "id": s.get("objectId"),
                        "layout": s.get("slideProperties", {}).get("layoutObjectId"),
                    }
                    for s in slides[:10]
                ],
                "source": "Google Slides",
            }
        elif method_name == "list_slides":
            presentation_id = arguments.get("presentation_id")
            if not presentation_id:
                return {"error": "presentation_id required"}

            presentation = service.presentations().get(presentationId=presentation_id).execute()
            slides = []
            for slide in presentation.get("slides", []):
                # Extract text from shapes
                slide_text = []
                for element in slide.get("pageElements", []):
                    if "shape" in element and "text" in element.get("shape", {}):
                        text_elements = element["shape"]["text"].get("textElements", [])
                        for te in text_elements:
                            if "textRun" in te:
                                slide_text.append(te["textRun"].get("content", ""))
                slides.append({"id": slide.get("objectId"), "text": "".join(slide_text)[:200]})

            return {
                "presentation_id": presentation_id,
                "slides": slides[:10],
                "source": "Google Slides",
            }
        else:
            return {"error": f"Unknown Google Slides method: {method_name}"}

    async def _google_meet_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Google Meet - Video conferenze."""
        credentials = self._get_google_credentials()
        if not credentials:
            return {"error": "Google credentials not configured"}

        # Meet usa Calendar API per creare meeting
        if method_name == "create_meeting":
            from googleapiclient.discovery import build
            from datetime import datetime, timedelta

            calendar_service = build("calendar", "v3", credentials=credentials)

            summary = arguments.get("summary", "Quick Meeting")
            duration_minutes = arguments.get("duration_minutes", 30)
            start_time = arguments.get("start_time")

            if not start_time:
                start_time = datetime.utcnow() + timedelta(minutes=5)
            else:
                start_time = datetime.fromisoformat(start_time.replace("Z", "+00:00"))

            end_time = start_time + timedelta(minutes=duration_minutes)

            event = {
                "summary": summary,
                "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
                "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
                "conferenceData": {
                    "createRequest": {"requestId": f"meet-{int(datetime.now().timestamp())}"}
                },
            }

            created_event = (
                calendar_service.events()
                .insert(calendarId="primary", body=event, conferenceDataVersion=1)
                .execute()
            )

            meet_link = created_event.get("hangoutLink", "")
            return {
                "event_id": created_event.get("id"),
                "summary": created_event.get("summary"),
                "meet_link": meet_link,
                "start": created_event.get("start"),
                "source": "Google Meet",
            }
        elif method_name == "get_meeting":
            # Get meeting from calendar event
            from googleapiclient.discovery import build

            calendar_service = build("calendar", "v3", credentials=credentials)
            event_id = arguments.get("event_id")
            if not event_id:
                return {"error": "event_id required"}

            event = calendar_service.events().get(calendarId="primary", eventId=event_id).execute()
            return {
                "event_id": event_id,
                "summary": event.get("summary"),
                "meet_link": event.get("hangoutLink", ""),
                "attendees": [a.get("email") for a in event.get("attendees", [])],
                "source": "Google Meet",
            }
        else:
            return {"error": f"Unknown Google Meet method: {method_name}"}

    async def _google_keep_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Google Keep - Note e liste."""
        credentials = self._get_google_credentials()
        if not credentials:
            return {
                "error": "Google credentials not configured (GOOGLE_TOKEN_PATH or GOOGLE_SERVICE_ACCOUNT_PATH)"
            }

        from googleapiclient.discovery import build

        try:
            service = build("keep", "v1", credentials=credentials)
        except Exception as e:
            return {"error": f"Failed to build Keep service: {e}"}

        if method_name == "list_notes":
            # List all notes
            limit = min(arguments.get("limit", 10), 50)
            try:
                results = service.notes().list(pageSize=limit).execute()
                notes = results.get("notes", [])
                return {
                    "notes": [
                        {
                            "id": n.get("name", "").split("/")[-1] if n.get("name") else "",
                            "title": n.get("title", ""),
                            "body": n.get("body", {}).get("text", {}).get("text", "")[:500],
                            "created": n.get("createTime", ""),
                            "updated": n.get("updateTime", ""),
                            "trashed": n.get("trashed", False),
                        }
                        for n in notes
                        if not n.get("trashed", False)
                    ],
                    "count": len(notes),
                    "source": "Google Keep",
                }
            except Exception as e:
                return {"error": f"Keep API error: {e}"}

        elif method_name == "search":
            # Search notes by query
            query = arguments.get("query", "")
            limit = min(arguments.get("limit", 10), 50)

            if not query:
                return {"error": "query required for search"}

            try:
                # Keep API doesn't have native search, we list and filter
                results = service.notes().list(pageSize=100).execute()
                notes = results.get("notes", [])

                # Filter by query in title or body
                query_lower = query.lower()
                matching = []
                for n in notes:
                    if n.get("trashed", False):
                        continue
                    title = n.get("title", "").lower()
                    body_text = n.get("body", {}).get("text", {}).get("text", "").lower()
                    if query_lower in title or query_lower in body_text:
                        matching.append(
                            {
                                "id": n.get("name", "").split("/")[-1] if n.get("name") else "",
                                "title": n.get("title", ""),
                                "body": n.get("body", {}).get("text", {}).get("text", "")[:500],
                                "created": n.get("createTime", ""),
                            }
                        )
                        if len(matching) >= limit:
                            break

                return {
                    "query": query,
                    "notes": matching,
                    "count": len(matching),
                    "source": "Google Keep",
                }
            except Exception as e:
                return {"error": f"Keep API error: {e}"}

        elif method_name == "get_note":
            # Get single note by ID
            note_id = arguments.get("note_id")
            if not note_id:
                return {"error": "note_id required"}

            try:
                note = service.notes().get(name=f"notes/{note_id}").execute()

                # Handle list items if present
                list_items = []
                if "list" in note.get("body", {}):
                    for item in note.get("body", {}).get("list", {}).get("listItems", []):
                        list_items.append(
                            {
                                "text": item.get("text", {}).get("text", ""),
                                "checked": item.get("checked", False),
                            }
                        )

                return {
                    "id": note_id,
                    "title": note.get("title", ""),
                    "body": note.get("body", {}).get("text", {}).get("text", "")
                    if "text" in note.get("body", {})
                    else "",
                    "list_items": list_items,
                    "created": note.get("createTime", ""),
                    "updated": note.get("updateTime", ""),
                    "color": note.get("color", ""),
                    "source": "Google Keep",
                }
            except Exception as e:
                return {"error": f"Keep API error: {e}"}
        else:
            return {"error": f"Unknown Google Keep method: {method_name}"}

    async def _google_forms_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Google Forms - Moduli e risposte."""
        credentials = self._get_google_credentials()
        if not credentials:
            return {"error": "Google credentials not configured"}

        from googleapiclient.discovery import build

        try:
            service = build("forms", "v1", credentials=credentials)
        except Exception as e:
            return {"error": f"Failed to build Forms service: {e}"}

        if method_name == "get_form":
            form_id = arguments.get("form_id")
            if not form_id:
                return {"error": "form_id required"}

            try:
                form = service.forms().get(formId=form_id).execute()
                return {
                    "id": form_id,
                    "title": form.get("info", {}).get("title", ""),
                    "description": form.get("info", {}).get("description", ""),
                    "responder_uri": form.get("responderUri", ""),
                    "items_count": len(form.get("items", [])),
                    "source": "Google Forms",
                }
            except Exception as e:
                return {"error": f"Forms API error: {e}"}

        elif method_name == "get_responses":
            form_id = arguments.get("form_id")
            if not form_id:
                return {"error": "form_id required"}

            limit = min(arguments.get("limit", 10), 50)
            try:
                responses = (
                    service.forms().responses().list(formId=form_id, pageSize=limit).execute()
                )
                return {
                    "form_id": form_id,
                    "responses": [
                        {
                            "response_id": r.get("responseId", ""),
                            "create_time": r.get("createTime", ""),
                            "answers_count": len(r.get("answers", {})),
                        }
                        for r in responses.get("responses", [])
                    ],
                    "count": len(responses.get("responses", [])),
                    "source": "Google Forms",
                }
            except Exception as e:
                return {"error": f"Forms API error: {e}"}
        else:
            return {"error": f"Unknown Google Forms method: {method_name}"}

    async def _google_classroom_handler(
        self,
        method_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handler per Google Classroom - Corsi e compiti."""
        credentials = self._get_google_credentials()
        if not credentials:
            return {"error": "Google credentials not configured"}

        from googleapiclient.discovery import build

        try:
            service = build("classroom", "v1", credentials=credentials)
        except Exception as e:
            return {"error": f"Failed to build Classroom service: {e}"}

        if method_name == "list_courses":
            limit = min(arguments.get("limit", 10), 50)
            try:
                courses = service.courses().list(pageSize=limit, courseStates=["ACTIVE"]).execute()
                return {
                    "courses": [
                        {
                            "id": c.get("id", ""),
                            "name": c.get("name", ""),
                            "section": c.get("section", ""),
                            "description": c.get("description", "")[:200]
                            if c.get("description")
                            else "",
                            "state": c.get("courseState", ""),
                        }
                        for c in courses.get("courses", [])
                    ],
                    "count": len(courses.get("courses", [])),
                    "source": "Google Classroom",
                }
            except Exception as e:
                return {"error": f"Classroom API error: {e}"}

        elif method_name == "get_coursework":
            course_id = arguments.get("course_id")
            if not course_id:
                return {"error": "course_id required"}

            limit = min(arguments.get("limit", 10), 50)
            try:
                coursework = (
                    service.courses()
                    .courseWork()
                    .list(courseId=course_id, pageSize=limit)
                    .execute()
                )
                return {
                    "course_id": course_id,
                    "coursework": [
                        {
                            "id": cw.get("id", ""),
                            "title": cw.get("title", ""),
                            "description": cw.get("description", "")[:200]
                            if cw.get("description")
                            else "",
                            "state": cw.get("state", ""),
                            "due_date": cw.get("dueDate", {}),
                            "max_points": cw.get("maxPoints", 0),
                        }
                        for cw in coursework.get("courseWork", [])
                    ],
                    "count": len(coursework.get("courseWork", [])),
                    "source": "Google Classroom",
                }
            except Exception as e:
                return {"error": f"Classroom API error: {e}"}
        else:
            return {"error": f"Unknown Google Classroom method: {method_name}"}

    async def close(self) -> None:
        """Chiude le risorse."""
        if self._http_client:
            await self._http_client.aclose()


# Factory
def create_tool_executor() -> ToolExecutor:
    """Crea un nuovo executor."""
    return ToolExecutor()


# Singleton instance
_tool_executor_instance: ToolExecutor | None = None


def get_tool_executor() -> ToolExecutor:
    """Ottiene l'istanza singleton del ToolExecutor.

    Returns:
        ToolExecutor singleton instance
    """
    global _tool_executor_instance
    if _tool_executor_instance is None:
        _tool_executor_instance = ToolExecutor()
    return _tool_executor_instance
