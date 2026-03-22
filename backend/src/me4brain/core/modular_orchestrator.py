"""Modular Cognitive Orchestrator - Domain Handler Integration Layer.

Questo modulo integra il nuovo PluginRegistry nella pipeline cognitiva esistente.
Fornisce un'alternativa modulare a execute_semantic_tool_loop() che delega
l'esecuzione ai domain handlers invece di usare logica inline.

Strategy:
1. Mantiene compatibilità con pipeline esistente
2. Usa PluginRegistry per routing query → domain
3. Delega esecuzione a domain handlers
4. Fallback alla logica legacy se nessun handler matched

Usage:
    from me4brain.core.modular_orchestrator import ModularOrchestrator

    orchestrator = ModularOrchestrator(tenant_id)
    results = await orchestrator.execute(query, analysis, context)
"""

from typing import Any

import structlog

from me4brain.core.domain_router import DomainRouter, DomainRouterConfig
from me4brain.core.interfaces import DomainExecutionResult
from me4brain.core.plugin_registry import PluginRegistry
from me4brain.memory.decay import get_decay_config, should_use_tool_first

logger = structlog.get_logger(__name__)


class ModularOrchestrator:
    """Orchestratore modulare che usa domain handlers.

    Comportamento:
    1. Rileva dominio dalla query (PluginRegistry.route_query)
    2. Check volatilità: se tool_first, chiama handler
    3. Delega esecuzione a domain handler con timeout/circuit breaker
    4. Fallback a legacy se nessun handler disponibile

    Example:
        orchestrator = await ModularOrchestrator.create("tenant_abc")
        results = await orchestrator.execute(
            query="Prossima partita Lakers",
            analysis={"entities": ["Lakers", "NBA"]},
            context={"user_id": "fulvio"}
        )
    """

    def __init__(
        self,
        registry: PluginRegistry,
        router_config: DomainRouterConfig | None = None,
    ) -> None:
        """Inizializza orchestratore.

        Args:
            registry: PluginRegistry già inizializzato
            router_config: Configurazione opzionale per DomainRouter
        """
        self.registry = registry
        self.router = DomainRouter(registry, router_config)
        self._legacy_fallback_enabled = True

    @classmethod
    async def create(
        cls,
        tenant_id: str = "default",
        router_config: DomainRouterConfig | None = None,
    ) -> "ModularOrchestrator":
        """Factory asincrono per creare orchestratore.

        Args:
            tenant_id: ID tenant per isolation
            router_config: Configurazione DomainRouter

        Returns:
            ModularOrchestrator pronto per l'uso
        """
        registry = await PluginRegistry.get_instance(tenant_id)
        return cls(registry, router_config)

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Esegue query delegando a domain handlers.

        Supporta:
        - Single domain (legacy): route_query() → singolo handler
        - Multi-domain: analysis["domains_required"] → esecuzione parallela

        Args:
            query: Query utente
            analysis: Analisi query da LLM (intent, entities, domains_required)
            context: Contesto sessione (user_id, memory context, etc.)

        Returns:
            Lista risultati in formato compatibile con pipeline esistente
        """
        # CHECK: Multi-domain mode (nuovo)
        domains_required = analysis.get("domains_required", [])

        if len(domains_required) > 1:
            # MULTI-DOMAIN: usa nuovo orchestrator
            return await self._execute_multi_domain(query, analysis, context, domains_required)

        # SINGLE-DOMAIN: logica esistente
        if domains_required:
            # Prendi il primo dominio specificato dall'LLM
            domain_name = domains_required[0]
            handler = self.registry.get_handler(domain_name)  # get_handler non è async
            use_specified_domain = True
        else:
            # Fallback: routing tradizionale
            handler = await self.registry.route_query(query, analysis)
            use_specified_domain = False

        if handler is None:
            logger.info(
                "no_modular_handler",
                query_preview=query[:50],
                fallback="legacy",
            )
            return []

        domain = handler.domain_name

        # Check volatilità: determina se tool-first
        if should_use_tool_first(domain):
            logger.debug(
                "tool_first_domain",
                domain=domain,
                volatility=get_decay_config(domain).volatility.value,
            )

        # FIX: Se il dominio è stato specificato dall'LLM (domains_required),
        # esegui direttamente handler.execute() per rispettare la selezione.
        # Altrimenti usa route_and_execute che fa routing automatico.
        if use_specified_domain:
            import asyncio

            try:
                results = await asyncio.wait_for(
                    handler.execute(query, analysis, context),
                    timeout=30.0,  # 30s timeout per esecuzione singolo dominio
                )
                logger.info(
                    "specified_domain_execution_success",
                    domain=domain,
                    results_count=len(results) if results else 0,
                )
                return self._convert_to_legacy_format(results)
            except asyncio.TimeoutError:
                logger.error("specified_domain_execution_timeout", domain=domain)
                return [{"success": False, "error": f"Timeout executing {domain}"}]
            except Exception as e:
                logger.error("specified_domain_execution_error", domain=domain, error=str(e))
                return [{"success": False, "error": str(e)}]
        else:
            # Routing automatico: usa route_and_execute
            results = await self.router.route_and_execute(
                query=query,
                analysis=analysis,
                context=context,
            )
            return self._convert_to_legacy_format(results)

    async def _execute_multi_domain(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
        domains: list[str],
    ) -> list[dict[str, Any]]:
        """Esegue multipli domini in parallelo.

        Usa MultiDomainOrchestrator per:
        - Entity routing automatico (target_domain)
        - asyncio.gather parallelo
        - Error isolation per-dominio
        """
        from me4brain.core.multi_domain_orchestrator import (
            MultiDomainOrchestrator,
            aggregate_results,
        )

        logger.info(
            "multi_domain_execution_started",
            domains=domains,
            entity_count=len(analysis.get("entities", [])),
        )

        # Costruisci registry handlers
        domain_registry = {}
        for domain in domains:
            handler = self.registry.get_handler(domain)  # get_handler non è async
            if handler:
                domain_registry[domain] = handler
            else:
                logger.warning("domain_handler_not_found", domain=domain)

        if not domain_registry:
            return []

        # Esegui in parallelo
        orchestrator = MultiDomainOrchestrator(domain_registry)
        results = await orchestrator.execute_parallel(
            domains=list(domain_registry.keys()),
            query=query,
            analysis=analysis,
            context=context,
        )

        # Aggrega e converti in formato legacy
        aggregated = aggregate_results(results)

        legacy_results = []
        for domain, domain_data in aggregated.get("data", {}).items():
            for item in domain_data:
                legacy_results.append(
                    {
                        "success": True,
                        "tool_name": item.get("tool_name", f"{domain}_tool"),
                        "data": item.get("data", {}),
                        "_domain": domain,
                        "from_cache": False,
                    }
                )

        # Aggiungi errori
        for error in aggregated.get("errors", []):
            legacy_results.append(
                {
                    "success": False,
                    "tool_name": f"{error['domain']}_tool",
                    "error": error["error"],
                    "_domain": error["domain"],
                }
            )

        logger.info(
            "multi_domain_execution_complete",
            total_results=len(legacy_results),
            successful=len(aggregated.get("successful_domains", [])),
            failed=len(aggregated.get("failed_domains", [])),
        )

        return legacy_results

    def _convert_to_legacy_format(
        self,
        results: list[DomainExecutionResult],
    ) -> list[dict[str, Any]]:
        """Converte risultati moderni in formato compatibile legacy.

        Il formato legacy usato da cognitive_pipeline:
        {
            "success": bool,
            "tool_name": str,
            "execution_time": float,
            "data": dict | str,
            "error": str | None,
            "from_cache": bool
        }
        """
        legacy_results = []

        for result in results:
            legacy = {
                "success": result.success,
                "tool_name": result.tool_name or f"{result.domain}_handler",
                "execution_time": result.latency_ms / 1000.0,
                "data": result.data,
                "error": result.error,
                "from_cache": result.cached,
                # Extra metadata per nuovo sistema
                "_domain": result.domain,
                "_modular": True,
            }
            legacy_results.append(legacy)

        return legacy_results

    async def shutdown(self) -> None:
        """Shutdown orchestratore e registry."""
        await self.registry.shutdown_all()

    @property
    def available_domains(self) -> list[str]:
        """Lista domini disponibili."""
        return self.registry.domain_names

    @property
    def handler_count(self) -> int:
        """Numero handler registrati."""
        return self.registry.handler_count


# =============================================================================
# Integration Helpers per cognitive_pipeline.py
# =============================================================================


async def try_modular_execution(
    tenant_id: str,
    user_id: str,
    query: str,
    analysis: dict[str, Any],
) -> tuple[bool, list[dict[str, Any]]]:
    """Prova esecuzione modulare, ritorna (success, results).

    Usato da cognitive_pipeline per integrazione graduale:
    1. Prova prima con domain handlers
    2. Se nessun handler matched, ritorna (False, [])
    3. cognitive_pipeline può poi usare logica legacy come fallback

    Args:
        tenant_id: ID tenant
        user_id: ID utente
        query: Query originale
        analysis: Analisi query

    Returns:
        (True, results) se handler ha gestito
        (False, []) se nessun handler disponibile
    """
    try:
        orchestrator = await ModularOrchestrator.create(tenant_id)

        results = await orchestrator.execute(
            query=query,
            analysis=analysis,
            context={"user_id": user_id, "tenant_id": tenant_id},
        )

        if results:
            logger.info(
                "modular_execution_success",
                tenant_id=tenant_id,
                results_count=len(results),
            )
            return True, results

        # Nessun handler matched
        return False, []

    except Exception as e:
        logger.warning(
            "modular_execution_failed",
            error=str(e),
            fallback="legacy",
        )
        return False, []


async def get_modular_stats(tenant_id: str = "default") -> dict[str, Any]:
    """Ottiene statistiche sistema modulare.

    Returns:
        dict con informazioni su handlers, circuit breakers, etc.
    """
    try:
        orchestrator = await ModularOrchestrator.create(tenant_id)

        stats = {
            "tenant_id": tenant_id,
            "handler_count": orchestrator.handler_count,
            "domains": orchestrator.available_domains,
            "circuit_states": {},
        }

        for domain in orchestrator.available_domains:
            cb_stats = orchestrator.router.get_circuit_stats(domain)
            stats["circuit_states"][domain] = {
                "state": cb_stats.state.value,
                "failures": cb_stats.failure_count,
                "successes": cb_stats.success_count,
            }

        return stats

    except Exception as e:
        return {"error": str(e)}
