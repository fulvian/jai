"""Medical Domain Handler.

Implementazione DomainHandler per query mediche.
Gestisce farmaci (RxNorm) e metriche citazioni (iCite).

Volatilità: STABLE (dati farmaci cambiano raramente)
Tool-First: Sempre API fresh per interazioni farmaci
"""

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


class MedicalHandler(DomainHandler):
    """Domain handler per Medical queries.

    Capabilities:
    - RxNorm: Drug info, interactions
    - iCite: Citation metrics

    Example queries:
    - "Info sul farmaco metformina"
    - "Interazioni tra aspirina e warfarin"
    - "Metriche citazioni per PMID 12345678"
    """

    # Services gestiti da questo handler
    HANDLED_SERVICES = frozenset(
        {
            "RxNormService",
            "iCiteService",
        }
    )

    # Keywords per routing rapido
    MEDICAL_KEYWORDS = frozenset(
        {
            # Generale
            "farmaco",
            "farmaci",
            "drug",
            "drugs",
            "medicina",
            "medicine",
            "medicamento",
            "medicinale",
            # RxNorm
            "rxnorm",
            "interazione",
            "interazioni",
            "interaction",
            "interactions",
            "effetti collaterali",
            "side effects",
            "dosaggio",
            "dosage",
            # iCite
            "icite",
            "citazioni",
            "citation",
            "citations",
            "impact",
            "pmid",
            "pubmed",
        }
    )

    @property
    def domain_name(self) -> str:
        """Nome univoco dominio."""
        return "medical"

    @property
    def volatility(self) -> DomainVolatility:
        """Dati farmaci sono stabili."""
        return DomainVolatility.STABLE

    @property
    def default_ttl_hours(self) -> int:
        """TTL lungo per dati farmaci."""
        return 168  # 1 settimana

    @property
    def capabilities(self) -> list[DomainCapability]:
        """Capabilities esposte dal dominio Medical."""
        return [
            DomainCapability(
                name="rxnorm",
                description="Info farmaci e interazioni via NIH RxNorm",
                keywords=["farmaco", "drug", "interazione", "rxnorm"],
                example_queries=[
                    "Info sulla metformina",
                    "Interazioni aspirina",
                    "Spelling corretto farmaco",
                ],
            ),
            DomainCapability(
                name="icite",
                description="Metriche citazioni biomediche NIH iCite",
                keywords=["citazioni", "citation", "pmid", "impact"],
                example_queries=[
                    "Metriche PMID 12345678",
                    "Impact factor paper",
                ],
            ),
            DomainCapability(
                name="pubmed",
                description="Ricerca paper biomedici su PubMed (NCBI)",
                keywords=["pubmed", "paper", "biomedico", "ricerca medica", "abstract"],
                example_queries=[
                    "Cerca paper su diabete",
                    "Abstract PMID 12345678",
                    "Ricerca biomedica COVID",
                ],
            ),
            DomainCapability(
                name="europepmc",
                description="Ricerca paper life sciences su Europe PMC",
                keywords=["europe pmc", "life sciences", "paper europei"],
                example_queries=[
                    "Paper life sciences su CRISPR",
                    "Ricerca europea su cancro",
                ],
            ),
        ]

    async def initialize(self) -> None:
        """Setup handler Medical."""
        logger.info("medical_handler_initialized")

    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        """Determina se la query è Medical-related."""
        query_lower = query.lower()

        # Check entities da analisi LLM
        entities = analysis.get("entities", [])
        medical_entities = sum(
            1 for e in entities if any(kw in str(e).lower() for kw in self.MEDICAL_KEYWORDS)
        )

        # Check keywords diretti nella query
        keyword_matches = sum(1 for kw in self.MEDICAL_KEYWORDS if kw in query_lower)

        # Score
        total_matches = medical_entities + keyword_matches

        if total_matches == 0:
            return 0.0
        elif total_matches == 1:
            return 0.5
        elif total_matches == 2:
            return 0.7
        elif total_matches <= 4:
            return 0.85
        else:
            return 1.0

    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Esegue logica Medical con routing a sub-service."""
        query_lower = query.lower()
        start_time = datetime.now(UTC)
        results: list[DomainExecutionResult] = []

        logger.info(
            "medical_execute",
            query_preview=query[:50],
            entities=analysis.get("entities", []),
        )

        # Determina sub-service target
        target_service = self._detect_target_service(query_lower)

        try:
            if target_service == "clinicaltrials":
                results = [await self._execute_clinicaltrials(query, analysis)]
            elif target_service == "pubmed":
                results = [await self._execute_pubmed(query, analysis)]
            elif target_service == "rxnorm":
                results = [await self._execute_rxnorm(query, analysis)]
            elif target_service == "icite":
                results = [await self._execute_icite(query, analysis)]
            else:
                # Default: drug search
                results = [await self._execute_rxnorm(query, analysis)]
        except Exception as e:
            logger.error("medical_execution_error", error=str(e))
            results = [
                DomainExecutionResult(
                    success=False,
                    domain=self.domain_name,
                    tool_name=f"medical_{target_service or 'rxnorm'}",
                    error=str(e),
                )
            ]

        # Add timing
        latency_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
        for r in results:
            r.latency_ms = latency_ms

        return results

    def _detect_target_service(self, query: str) -> str | None:
        """Rileva quale sub-service Medical è target della query."""
        query_lower = query.lower()

        # ClinicalTrials patterns - query specifiche per trial clinici
        clinicaltrials_patterns = [
            "trial",
            "trials",
            "clinical trial",
            "sperimentazione",
            "recruiting",
            "arruolamento",
            "fase",
            "phase",
        ]
        for pattern in clinicaltrials_patterns:
            if pattern in query_lower:
                return "clinicaltrials"

        # PubMed patterns - ricerca medica/scientifica
        pubmed_patterns = [
            "alzheimer",
            "cancer",
            "diabetes",
            "treatment",
            "therapy",
            "ricerca",
            "paper",
            "studi",
            "studio",
            "articolo",
            "pubblicazione",
            "research",
            "disease",
            "malattia",
            "effetti",
            "effects",
            "side effects",
            "efficacy",
            "efficacia",
        ]
        for pattern in pubmed_patterns:
            if pattern in query_lower:
                return "pubmed"

        # iCite patterns - citazioni
        icite_patterns = ["icite", "citation", "citazioni", "pmid", "impact"]
        for pattern in icite_patterns:
            if pattern in query_lower:
                return "icite"

        return "rxnorm"  # Default per query farmaci

    async def _execute_rxnorm(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue query RxNorm."""
        from me4brain.domains.medical.tools import medical_api

        # Estrai drug name dalla query
        drug_name = self._extract_drug_name(query)

        try:
            data = await medical_api.rxnorm_drug_info(drug_name=drug_name)
            return DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name="rxnorm_drug_info",
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="rxnorm_drug_info",
                error=str(e),
            )

    async def _execute_icite(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue query iCite."""
        from me4brain.domains.medical.tools import medical_api
        import re

        # Estrai PMID dalla query
        pmid_match = re.search(r"\b(\d{6,8})\b", query)
        pmid = pmid_match.group(1) if pmid_match else "0"

        try:
            data = await medical_api.icite_metrics(pmid=pmid)
            return DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name="icite_metrics",
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="icite_metrics",
                error=str(e),
            )

    async def _execute_pubmed(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue query PubMed per ricerca articoli scientifici."""
        from me4brain.domains.medical.tools import medical_api

        # Estrai termini di ricerca dalla query
        search_term = self._extract_search_term(query)

        try:
            data = await medical_api.pubmed_search(query=search_term, max_results=10)
            return DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name="pubmed_search",
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="pubmed_search",
                error=str(e),
            )

    async def _execute_clinicaltrials(
        self,
        query: str,
        analysis: dict[str, Any],
    ) -> DomainExecutionResult:
        """Esegue query ClinicalTrials.gov per trial clinici."""
        from me4brain.domains.medical.tools import medical_api

        # Estrai condizione dalla query
        search_term = self._extract_search_term(query)

        # Determina status (default RECRUITING)
        status = "RECRUITING"
        if "complet" in query.lower():
            status = "COMPLETED"

        try:
            data = await medical_api.clinicaltrials_search(
                condition=search_term,
                status=status,
                max_results=10,
            )
            return DomainExecutionResult(
                success=not data.get("error"),
                domain=self.domain_name,
                tool_name="clinicaltrials_search",
                data=data if not data.get("error") else {},
                error=data.get("error"),
            )
        except Exception as e:
            return DomainExecutionResult(
                success=False,
                domain=self.domain_name,
                tool_name="clinicaltrials_search",
                error=str(e),
            )

    def _extract_search_term(self, query: str) -> str:
        """Estrae termini di ricerca per PubMed dalla query."""
        stopwords = [
            "cerca",
            "ricerca",
            "trova",
            "articoli",
            "paper",
            "studi",
            "pubblicazioni",
            "su",
            "riguardo",
            "about",
            "on",
            "for",
            "the",
            "il",
            "la",
            "gli",
            "le",
            "un",
            "una",
        ]
        words = query.lower().split()
        filtered = [w for w in words if w not in stopwords and len(w) > 2]
        return " ".join(filtered[:5])  # Max 5 termini

    def _extract_drug_name(self, query: str) -> str:
        """Estrae nome farmaco dalla query."""
        stopwords = [
            "farmaco",
            "drug",
            "medicina",
            "info",
            "sul",
            "sulla",
            "del",
            "della",
            "interazioni",
            "effetti",
            "cosa",
            "è",
            "il",
            "la",
        ]
        words = query.lower().split()
        filtered = [w for w in words if w not in stopwords and len(w) > 2]
        return filtered[0] if filtered else query

    def handles_service(self, service_name: str) -> bool:
        """Verifica se questo handler gestisce il servizio."""
        return service_name in self.HANDLED_SERVICES

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Esegue tool Medical specifico per nome."""
        from me4brain.domains.medical.tools import medical_api

        logger.info(
            "medical_execute_tool",
            tool_name=tool_name,
            arguments=arguments,
        )

        return await medical_api.execute_tool(tool_name, arguments)
