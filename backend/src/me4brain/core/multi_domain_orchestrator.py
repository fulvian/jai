"""Multi-Domain Orchestrator - Esecuzione parallela domini multipli.

Pattern: Hybrid LLM + Async Fan-Out
- analyze_query() → domains_required[]
- MultiDomainOrchestrator.execute_parallel() → asyncio.gather()
- aggregate_results() → unified JSON

Supporta:
- Query multi-dominio (es. "Confronta BTC con meteo Roma")
- Entity routing automatico (location→geo_weather, ticker→finance)
- Error isolation per-dominio
- Timeout configurabili
"""

import asyncio
from typing import Any

import structlog

from me4brain.core.interfaces import DomainExecutionResult, DomainHandler

logger = structlog.get_logger(__name__)


class MultiDomainOrchestrator:
    """Orchestratore per esecuzione parallela di multipli domini.

    Esempio:
        orchestrator = MultiDomainOrchestrator(domain_registry)
        results = await orchestrator.execute_parallel(
            domains=["finance_crypto", "geo_weather"],
            query="Confronta BTC con meteo Roma",
            analysis={"entities": [...]},
            context={}
        )
    """

    def __init__(
        self,
        domain_registry: dict[str, DomainHandler],
        timeout_per_domain: float = 30.0,  # Increased from 5s: external APIs need more time
    ) -> None:
        self.registry = domain_registry
        self.timeout_per_domain = timeout_per_domain

    async def execute_parallel(
        self,
        domains: list[str],
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, list[DomainExecutionResult]]:
        """Esegue multipli domini in parallelo con timeout e error isolation.

        Args:
            domains: Lista nomi domini da eseguire
            query: Query originale utente
            analysis: Analisi LLM con entities e target_domain
            context: Contesto sessione

        Returns:
            Dict con risultati per dominio: {domain_name: [DomainExecutionResult]}
        """
        if not domains:
            logger.warning("no_domains_to_execute")
            return {}

        # Filtra entities per dominio target
        domain_entities = self._route_entities_to_domains(analysis, domains)

        logger.info(
            "multi_domain_execution_started",
            domains=domains,
            entity_routing=list(domain_entities.keys()),
        )

        # Crea task paralleli per ogni dominio
        tasks: dict[str, asyncio.Task] = {}
        for domain in domains:
            handler = self.registry.get(domain)
            if handler:
                # Filtra analysis per includere solo entities del dominio
                domain_analysis = self._filter_analysis_for_domain(
                    analysis, domain, domain_entities
                )
                tasks[domain] = asyncio.create_task(
                    self._execute_with_timeout(handler, query, domain_analysis, context),
                    name=f"domain_{domain}",
                )
            else:
                logger.warning("domain_not_found", domain=domain)

        # Esegui in parallelo con error isolation
        results: dict[str, list[DomainExecutionResult]] = {}

        for domain, task in tasks.items():
            try:
                results[domain] = await task
            except asyncio.TimeoutError:
                logger.error("domain_timeout", domain=domain, timeout=self.timeout_per_domain)
                results[domain] = [
                    DomainExecutionResult(
                        success=False,
                        domain=domain,
                        tool_name=None,
                        data={"error": f"Timeout after {self.timeout_per_domain}s"},
                        error=f"Domain {domain} timed out after {self.timeout_per_domain}s",
                    )
                ]
            except Exception as e:
                logger.error("domain_execution_error", domain=domain, error=str(e))
                results[domain] = [
                    DomainExecutionResult(
                        success=False,
                        domain=domain,
                        tool_name=None,
                        data={"error": str(e)},
                        error=str(e),
                    )
                ]

        logger.info(
            "multi_domain_execution_complete",
            total_domains=len(domains),
            successful=sum(1 for r_list in results.values() for r in r_list if r.success),
        )

        return results

    async def _execute_with_timeout(
        self,
        handler: DomainHandler,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Esegue handler con timeout."""
        return await asyncio.wait_for(
            handler.execute(query, analysis, context),
            timeout=self.timeout_per_domain,
        )

    def _route_entities_to_domains(
        self,
        analysis: dict[str, Any],
        domains: list[str],
    ) -> dict[str, list[dict]]:
        """Raggruppa entities per dominio target.

        Returns:
            Dict {domain_name: [entities per quel dominio]}
        """
        entities_by_domain: dict[str, list[dict]] = {d: [] for d in domains}

        for entity in analysis.get("entities", []):
            if isinstance(entity, dict):
                target = entity.get("target_domain")
                if target and target in entities_by_domain:
                    entities_by_domain[target].append(entity)

        return entities_by_domain

    def _filter_analysis_for_domain(
        self,
        analysis: dict[str, Any],
        domain: str,
        domain_entities: dict[str, list[dict]],
    ) -> dict[str, Any]:
        """Crea analysis filtrata con solo entities del dominio."""
        filtered = analysis.copy()
        filtered["entities"] = domain_entities.get(domain, [])
        return filtered


def aggregate_results(
    results: dict[str, list[DomainExecutionResult]],
) -> dict[str, Any]:
    """Aggrega risultati da multipli domini per synthesis.

    Returns:
        {
            "domains_executed": ["finance_crypto", "geo_weather"],
            "successful_domains": ["finance_crypto"],
            "data": {"finance_crypto": {...}, "geo_weather": {...}},
            "errors": [{"domain": "geo_weather", "error": "..."}]
        }
    """
    aggregated: dict[str, Any] = {
        "domains_executed": list(results.keys()),
        "successful_domains": [],
        "failed_domains": [],
        "data": {},
        "errors": [],
    }

    for domain, domain_results in results.items():
        domain_success = False
        domain_data: list[dict] = []

        for r in domain_results:
            if r.success:
                domain_success = True
                if r.data:
                    domain_data.append(
                        {
                            "tool_name": r.tool_name,
                            "data": r.data,
                        }
                    )
            else:
                aggregated["errors"].append(
                    {
                        "domain": domain,
                        "tool_name": r.tool_name,
                        "error": r.error,
                    }
                )

        if domain_success:
            aggregated["successful_domains"].append(domain)
            aggregated["data"][domain] = domain_data
        else:
            aggregated["failed_domains"].append(domain)

    return aggregated
