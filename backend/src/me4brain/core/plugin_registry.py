"""Plugin Registry for Domain Handlers.

Implementa auto-discovery e registrazione dei domain handlers.
Supporta multi-tenancy con isolation per tenant.

Pattern: Singleton per tenant + Auto-discovery via pkgutil
"""

import asyncio
import importlib
import pkgutil
from typing import Any

import structlog

from me4brain.core.interfaces import DomainHandler

logger = structlog.get_logger(__name__)


class PluginRegistry:
    """Registro domain handlers con multi-tenant isolation.

    Ogni tenant ha la propria istanza del registry per garantire
    isolation completa tra tenant diversi.

    Lifecycle:
    1. `get_instance(tenant_id)`: Ottiene/crea registry per tenant
    2. `discover()`: Auto-discovery handlers in me4brain.domains
    3. `register()`: Registra handler manualmente
    4. `route_query()`: Trova miglior handler per query
    5. `shutdown_all()`: Cleanup a fine vita

    Example:
        registry = await PluginRegistry.get_instance("tenant_abc")
        handler = await registry.route_query("analisi Lakers", analysis)
        if handler:
            results = await handler.execute(query, analysis, context)
    """

    # Per-tenant isolation: ogni tenant ha la propria istanza
    _instances: dict[str, "PluginRegistry"] = {}
    _lock = asyncio.Lock()

    def __init__(self, tenant_id: str) -> None:
        """Inizializza registry per un tenant specifico.

        Args:
            tenant_id: ID tenant per isolation
        """
        self.tenant_id = tenant_id
        self._handlers: dict[str, DomainHandler] = {}
        self._initialized = False

    @classmethod
    async def get_instance(cls, tenant_id: str = "default") -> "PluginRegistry":
        """Ottiene istanza registry per tenant (thread-safe).

        Args:
            tenant_id: ID tenant (default: "default")

        Returns:
            PluginRegistry isolato per il tenant
        """
        async with cls._lock:
            if tenant_id not in cls._instances:
                instance = cls(tenant_id)
                await instance.discover()
                cls._instances[tenant_id] = instance
                logger.info(
                    "plugin_registry_created",
                    tenant_id=tenant_id,
                    handlers=list(instance._handlers.keys()),
                )
            return cls._instances[tenant_id]

    @classmethod
    async def clear_instance(cls, tenant_id: str) -> None:
        """Rimuove istanza registry per tenant (per testing).

        Args:
            tenant_id: ID tenant da rimuovere
        """
        async with cls._lock:
            if tenant_id in cls._instances:
                await cls._instances[tenant_id].shutdown_all()
                del cls._instances[tenant_id]

    async def discover(self, package: str = "me4brain.domains") -> int:
        """Auto-discovery e registrazione domain handlers.

        Cerca moduli in `package` che espongono `get_handler()`.

        Args:
            package: Package da scansionare (default: me4brain.domains)

        Returns:
            Numero di handler scoperti e registrati
        """
        discovered = 0

        try:
            pkg = importlib.import_module(package)
        except ImportError:
            logger.warning(
                "domains_package_not_found",
                package=package,
                tenant_id=self.tenant_id,
            )
            return 0

        # Itera sui submodules del package
        for _, name, is_pkg in pkgutil.iter_modules(pkg.__path__):
            if not is_pkg:
                continue

            try:
                module = importlib.import_module(f"{package}.{name}")

                # Cerca funzione get_handler()
                if hasattr(module, "get_handler"):
                    handler = module.get_handler()

                    if isinstance(handler, DomainHandler):
                        await self.register(handler)
                        discovered += 1
                    else:
                        logger.warning(
                            "invalid_handler_type",
                            module=f"{package}.{name}",
                            type=type(handler).__name__,
                        )
            except Exception as e:
                logger.error(
                    "handler_discovery_failed",
                    module=f"{package}.{name}",
                    error=str(e),
                )

        self._initialized = True
        logger.info(
            "plugin_discovery_complete",
            tenant_id=self.tenant_id,
            discovered=discovered,
            handlers=list(self._handlers.keys()),
        )

        return discovered

    async def register(self, handler: DomainHandler) -> None:
        """Registra un domain handler.

        Chiama `handler.initialize()` per setup asincrono.

        Args:
            handler: Handler da registrare

        Raises:
            ValueError: Se handler con stesso domain_name già registrato
        """
        domain_name = handler.domain_name

        if domain_name in self._handlers:
            logger.warning(
                "handler_already_registered",
                domain=domain_name,
                tenant_id=self.tenant_id,
            )
            return

        # Inizializza handler (setup asincrono)
        try:
            await handler.initialize()
        except Exception as e:
            logger.error(
                "handler_initialization_failed",
                domain=domain_name,
                error=str(e),
            )
            raise

        self._handlers[domain_name] = handler
        logger.info(
            "handler_registered",
            domain=domain_name,
            tenant_id=self.tenant_id,
            capabilities=[c.name for c in handler.capabilities],
        )

    def get_handler(self, domain: str) -> DomainHandler | None:
        """Ottiene handler per dominio specifico.

        Args:
            domain: Nome dominio (es. 'sports_nba')

        Returns:
            Handler se registrato, None altrimenti
        """
        return self._handlers.get(domain)

    def get_all_handlers(self) -> list[DomainHandler]:
        """Ottiene tutti gli handler registrati.

        Returns:
            Lista di tutti i domain handlers
        """
        return list(self._handlers.values())

    async def route_query(
        self,
        query: str,
        analysis: dict[str, Any],
        min_score: float = 0.4,
        prefer_specific_handler: bool = False,
    ) -> DomainHandler | None:
        """Trova il miglior handler per una query.

        Chiama `can_handle()` su tutti gli handler e restituis
        quello con score più alto sopra la soglia.

        REGOLA DI penalità: se web_search è il best ma ma c'è un altro handler
        con score decente (>= 0.35), preferisci quell'ultimo.
        Questo previene il fallback prematuro alla ricerca web quando
        la query riguarda domini specifici (NBA, crypto, meteo, ecc.).

        Args:
            query: Query dell'utente
            analysis: Analisi query da LLM
            min_score: Soglia minima per considerazione (default: 0.4)
            prefer_specific_handler: Se True, preferisce handler specifici su web_search

        Returns:
            Miglior handler se score >= min_score, None altrimenti
        """
        best_handler: DomainHandler | None = None
        best_score = 0.0

        # Valuta tutti gli handler in parallelo
        async def evaluate(handler: DomainHandler) -> tuple[DomainHandler, float]:
            try:
                score = await asyncio.wait_for(
                    handler.can_handle(query, analysis),
                    timeout=0.5,  # 500ms max per valutazione
                )
                return handler, score
            except asyncio.TimeoutError:
                logger.warning(
                    "handler_evaluation_timeout",
                    domain=handler.domain_name,
                )
                return handler, 0.0
            except Exception as e:
                logger.error(
                    "handler_evaluation_failed",
                    domain=handler.domain_name,
                    error=str(e),
                )
                return handler, 0.0

        results = await asyncio.gather(*[evaluate(h) for h in self._handlers.values()])

        # Ordina per score (decrescente)
        sorted_results = sorted(results, key=lambda x: x[1], reverse=True)

        for handler, score in sorted_results:
            if score > best_score:
                best_score = score
                best_handler = handler

        # REGOLA DI PENALITÀ: se web_search è il migliore ma c'è un altro handler con score decente,
        # preferisci quell'ultimo (previene fallback prematuro alla ricerca web)
        WEB_SEARCH_PENALTY_THRESHOLD = 0.35
        SPECIFIC_HANDLER_BOOST = 1.2

        if best_handler and best_handler.domain_name == "web_search":
            for handler, score in sorted_results:
                if handler.domain_name != "web_search" and score >= WEB_SEARCH_PENALTY_THRESHOLD:
                    if score * SPECIFIC_HANDLER_BOOST > best_score:
                        logger.info(
                            "web_search_penalty_applied",
                            original_domain="web_search",
                            original_score=best_score,
                            preferred_domain=handler.domain_name,
                            preferred_score=score,
                            boost_factor=SPECIFIC_HANDLER_BOOST,
                        )
                        best_handler = handler
                        best_score = score * SPECIFIC_HANDLER_BOOST
                        break

        if best_handler and best_score >= min_score:
            logger.debug(
                "query_routed",
                domain=best_handler.domain_name,
                score=best_score,
                query_preview=query[:50],
                candidates_evaluated=len(sorted_results),
            )
            return best_handler

        logger.debug(
            "no_handler_matched",
            best_score=best_score,
            min_score=min_score,
            query_preview=query[:50],
            candidates_evaluated=len(sorted_results),
        )
        return None

    def find_handler_for_service(self, service_name: str) -> DomainHandler | None:
        """Trova handler che gestisce un servizio specifico.

        Usato da tool_executor per delegare esecuzione tool.

        Args:
            service_name: Nome servizio (es. 'balldontlie', 'coingecko')

        Returns:
            Handler che gestisce il servizio, None se non trovato
        """
        for handler in self._handlers.values():
            if handler.handles_service(service_name):
                return handler
        return None

    async def shutdown_all(self) -> None:
        """Shutdown di tutti gli handler registrati.

        Chiama `shutdown()` su ogni handler per cleanup risorse.
        """
        for handler in self._handlers.values():
            try:
                await handler.shutdown()
            except Exception as e:
                logger.error(
                    "handler_shutdown_failed",
                    domain=handler.domain_name,
                    error=str(e),
                )

        self._handlers.clear()
        logger.info(
            "plugin_registry_shutdown",
            tenant_id=self.tenant_id,
        )

    @property
    def handler_count(self) -> int:
        """Numero di handler registrati."""
        return len(self._handlers)

    @property
    def domain_names(self) -> list[str]:
        """Lista nomi domini registrati."""
        return list(self._handlers.keys())
