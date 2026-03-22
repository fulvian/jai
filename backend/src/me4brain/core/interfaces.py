"""Core Interfaces for Domain-Driven Architecture.

Definisce le interfacce base per i domain handlers nel pattern
"Brain as a Service". Tutti i domini (sports_nba, finance_crypto, etc.)
devono implementare DomainHandler.

Pattern: Strategy + Plugin Registry
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DomainVolatility(str, Enum):
    """Classificazione volatilità dati per dominio."""

    REAL_TIME = "real_time"  # TTL <1h (live prices, sports scores)
    VOLATILE = "volatile"  # TTL 1-24h (sports, finance, weather)
    PERIODIC = "periodic"  # TTL 1-6h (weather forecasts, news updates)
    SEMI_VOLATILE = "semi_volatile"  # TTL 7d-6mo (workspace, science)
    STABLE = "stable"  # TTL 1-2yr (medical, knowledge)
    PERMANENT = "permanent"  # Never expires (user preferences)


class DomainCapability(BaseModel):
    """Descrive una capability esposta dal dominio.

    Usata per routing semantico delle query ai domini corretti.
    """

    name: str = Field(..., description="Nome univoco capability")
    description: str = Field(..., description="Descrizione per LLM/semantic search")
    keywords: list[str] = Field(
        default_factory=list,
        description="Keywords per routing (es. ['nba', 'basket', 'partita'])",
    )
    example_queries: list[str] = Field(
        default_factory=list,
        description="Query di esempio per training/testing",
    )


class ToolRegistration(BaseModel):
    """Schema per registrazione tool via API.

    Usato da domini esterni che chiamano POST /v1/tools/register.
    """

    name: str = Field(..., description="Nome univoco tool (es. 'nba_upcoming_games')")
    description: str = Field(..., description="Descrizione per semantic search")
    domain: str = Field(..., description="Dominio di appartenenza")
    endpoint: str = Field(..., description="Endpoint HTTP o internal://")
    method: str = Field(default="POST", description="HTTP method")
    api_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="OpenAPI schema per parametri",
    )
    volatility: DomainVolatility = Field(
        default=DomainVolatility.SEMI_VOLATILE,
        description="Classificazione volatilità dati",
    )
    ttl_hours: int | None = Field(
        default=None,
        description="TTL in ore per memory decay (None = usa default dominio)",
    )
    requires_auth: bool = Field(
        default=False,
        description="Richiede autenticazione OAuth/API key",
    )


class DomainExecutionResult(BaseModel):
    """Risultato esecuzione di un domain handler."""

    success: bool
    domain: str
    tool_name: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    latency_ms: float = 0.0
    cached: bool = False


class DomainHandler(ABC):
    """Interfaccia base per tutti i domain handlers.

    Ogni dominio (sports_nba, finance_crypto, google_workspace, etc.)
    deve implementare questa classe per integrarsi nel sistema.

    Lifecycle:
    1. `__init__`: Setup leggero (no I/O)
    2. `initialize()`: Setup asincrono (connessioni, registrazione tool)
    3. `can_handle()`: Chiamato per ogni query per determinare routing
    4. `execute()`: Esecuzione logica dominio
    5. `shutdown()`: Cleanup risorse

    Example:
        class SportsNBAHandler(DomainHandler):
            domain_name = "sports_nba"
            volatility = DomainVolatility.VOLATILE
            default_ttl_hours = 24

            async def can_handle(self, query, analysis):
                triggers = ["nba", "basket", "partita", "lakers"]
                return sum(1 for t in triggers if t in query.lower()) / len(triggers)

            async def execute(self, query, analysis, context):
                # Logica NBA-specific...
                return [DomainExecutionResult(...)]
    """

    @property
    @abstractmethod
    def domain_name(self) -> str:
        """Nome univoco del dominio (es. 'sports_nba').

        Usato per:
        - Routing query
        - Filtering memoria per dominio
        - Logging e metriche
        """
        ...

    @property
    def volatility(self) -> DomainVolatility:
        """Classificazione volatilità dati del dominio.

        Default: SEMI_VOLATILE. Override per domini specifici.
        """
        return DomainVolatility.SEMI_VOLATILE

    @property
    def default_ttl_hours(self) -> int | None:
        """TTL default in ore per episodi di questo dominio.

        None = no TTL (usa decay formula).
        """
        return None

    @property
    @abstractmethod
    def capabilities(self) -> list[DomainCapability]:
        """Lista capabilities supportate dal dominio.

        Usata per:
        - Semantic routing delle query
        - Discovery automatico funzionalità
        - Documentazione API
        """
        ...

    async def initialize(self) -> None:
        """Setup asincrono del dominio.

        Chiamato una volta all'avvio. Usare per:
        - Connessioni a servizi esterni
        - Registrazione tool nel Tool Registry
        - Caricamento configurazioni

        Default: no-op.
        """
        pass

    async def shutdown(self) -> None:
        """Cleanup risorse del dominio.

        Chiamato allo shutdown del sistema. Usare per:
        - Chiusura connessioni
        - Flush buffer
        - Deregistrazione tool

        Default: no-op.
        """
        pass

    @abstractmethod
    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        """Determina se questo dominio può gestire la query.

        Args:
            query: Query originale dell'utente
            analysis: Analisi query da LLM (entities, intent, etc.)

        Returns:
            Score 0.0-1.0 indicante quanto il dominio è adatto.
            - 0.0: Non può gestire
            - 0.5: Threshold minimo per considerazione
            - 1.0: Match perfetto

        Note:
            Implementazione dovrebbe essere veloce (<10ms).
            Usare keyword matching o embedding pre-calcolati.
        """
        ...

    @abstractmethod
    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """Esegue la logica specifica del dominio.

        Args:
            query: Query originale dell'utente
            analysis: Analisi query da LLM
            context: Contesto sessione (working memory, user prefs, etc.)

        Returns:
            Lista di risultati esecuzione (può chiamare più tool)

        Raises:
            asyncio.TimeoutError: Se esecuzione supera timeout (5s default)
            Exception: Errori domain-specific (wrapped in DomainExecutionResult)
        """
        ...

    def handles_service(self, service_name: str) -> bool:
        """Verifica se questo handler gestisce un servizio specifico.

        Args:
            service_name: Nome servizio da endpoint (es. 'balldontlie', 'coingecko')

        Returns:
            True se questo handler può eseguire tool per il servizio.

        Default implementation: False (override nei domini).
        """
        return False

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Esegue un tool specifico del dominio.

        Chiamato da tool_executor quando identifica il dominio corretto.

        Args:
            tool_name: Nome del tool (es. 'nba_upcoming_games')
            arguments: Argomenti per il tool

        Returns:
            Risultato del tool

        Raises:
            NotImplementedError: Se il tool non è supportato
        """
        raise NotImplementedError(f"Tool {tool_name} not implemented in {self.domain_name}")
