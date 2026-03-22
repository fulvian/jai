# Domain Handlers SDK - Reference

> **Versione**: 2.1  
> **Ultimo aggiornamento**: 4 Febbraio 2026  
> **Totale Domini**: 15 handlers  
> **Test Coverage**: 291 test, tutti ≥80% coverage

> [!IMPORTANT]
> **v2.1 (04/02/2026)**: Nuovo **Sports Booking Domain** - integrazione Playtomic con OAuth Google persistente!

---

## 🚀 Multi-Domain Orchestration (v2.0 NEW)

Query come *"Confronta prezzo Bitcoin con meteo Roma"* ora attivano **multipli domini in parallelo**.

### Come Funziona

```
Query → analyze_query() → {domains_required: ["finance_crypto", "geo_weather"]}
                ↓
        asyncio.gather(finance.execute(), geo.execute())
                ↓
        aggregate_results() → risposta unificata
```

### Nuovo Formato Analysis

```python
analysis = {
    "intent": "confronto multi-dominio",
    "domains_required": ["finance_crypto", "geo_weather", "sports_nba"],  # NEW!
    "entities": [
        {"type": "financial_instrument", "value": "BTC", "target_domain": "finance_crypto"},
        {"type": "location", "value": "Roma", "target_domain": "geo_weather"},
        {"type": "organization", "value": "Lakers", "target_domain": "sports_nba"}
    ],
    "execution_strategy": "parallel"  # NEW!
}
```

### Entity Routing Automatico

| Tipo Entity            | Target Domain                    |
| ---------------------- | -------------------------------- |
| `location`             | `geo_weather`, `travel`          |
| `financial_instrument` | `finance_crypto`                 |
| `organization` (teams) | `sports_nba`                     |
| `person` (athletes)    | `sports_nba`, `knowledge_media`  |
| `medical_condition`    | `medical`                        |
| `query_text`           | `google_workspace`, `web_search` |
| `sport` (padel/tennis) | `sports_booking`                 |

### Esempio Query Multi-Domain

```python
# Query automaticamente ruota a 2+ domini
"Confronta andamento BTC con previsioni meteo Milano"
→ finance_crypto.execute() ⟂ geo_weather.execute()  # PARALLELE
→ aggregate_results()
→ synthesis cross-domain
```

---

## 📡 SSE Streaming (v2.0.1 Fix)

L'endpoint `/v1/memory/query/stream` restituisce Server-Sent Events con chunk progressivi.

### Formato Chunk

| chunk_type | Descrizione             | Esempio                                                         |
| ---------- | ----------------------- | --------------------------------------------------------------- |
| `start`    | Inizio sessione         | `{"session_id": "...", "thread_id": "..."}`                     |
| `status`   | Status aggiornamento    | `{"content": "Analizzando query..."}`                           |
| `analysis` | Risultato analyze_query | `{"analysis": {...}}`                                           |
| `tool`     | Tool eseguito           | `{"tool_call": {"tool": "openmeteo_weather", "success": true}}` |
| `content`  | Token streaming         | `{"content": "Il meteo a Roma..."}`                             |
| `done`     | Fine risposta           | `{"confidence": 0.9}`                                           |
| `error`    | Errore                  | `{"content": "Error message"}`                                  |

### Flusso Completo

```
1. analyze_query() → Kimi K2.5 (max_tokens=4096)
2. execute_semantic_tool_loop() → Domain handlers
3. retrieve_memory_context() → Episodic memory
4. synthesize_response_stream() → Mistral streaming
```

### Configurazione LLM

```python
# analyze_query: Kimi K2.5 per reasoning complesso
LLMRequest(
    model="moonshotai/kimi-k2.5:thinking",
    max_tokens=4096,  # Piano Pro NanoGPT - no limiti
    temperature=0.0,  # Deterministico per JSON parsing
)

# synthesize_response: Mistral Large per risposta finale
LLMRequest(
    model="mistralai/mistral-large-3-675b-instruct-2512",
    stream=True,  # Token-by-token streaming
)
```

> [!WARNING]
> `max_tokens` troppo basso causa JSON troncato in analyze_query. Minimo consigliato: 2048.

---

## 📋 Architettura

Ogni domain handler implementa l'interfaccia `DomainHandler` definita in `src/me4brain/core/interfaces.py`.

### Interfaccia DomainHandler (ABC)

```python
from abc import ABC, abstractmethod
from typing import Any
from me4brain.core.interfaces import DomainExecutionResult, DomainVolatility, DomainCapability

class DomainHandler(ABC):
    """Base interface for all domain handlers."""
    
    @property
    @abstractmethod
    def domain_name(self) -> str:
        """Nome univoco del dominio (es. 'sports_nba')."""
        ...
    
    @property
    def volatility(self) -> DomainVolatility:
        """Classificazione volatilità dati. Default: SEMI_VOLATILE."""
        return DomainVolatility.SEMI_VOLATILE
    
    @property
    def default_ttl_hours(self) -> int | None:
        """TTL default in ore. None = usa decay formula."""
        return None
    
    @property
    @abstractmethod
    def capabilities(self) -> list[DomainCapability]:
        """Lista capabilities supportate dal dominio."""
        ...
    
    async def initialize(self) -> None:
        """Setup asincrono del dominio."""
        pass
    
    async def shutdown(self) -> None:
        """Cleanup risorse del dominio."""
        pass
    
    @abstractmethod
    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        """
        Determina se questo dominio può gestire la query.
        
        Returns:
            Score 0.0-1.0:
            - 0.0: Non può gestire
            - 0.5: Threshold minimo
            - 1.0: Match perfetto
        """
        ...
    
    @abstractmethod
    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        """
        Esegue la logica specifica del dominio.
        
        Args:
            query: Query originale dell'utente
            analysis: Analisi query da LLM
            context: Contesto sessione (working memory, user prefs, etc.)
        
        Returns:
            Lista di DomainExecutionResult (può chiamare più tool)
        """
        ...
    
    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Esegue un tool specifico del dominio."""
        raise NotImplementedError(f"Tool {tool_name} not implemented")
```

---

## 🔧 Modelli Dati

### DomainExecutionResult

```python
from pydantic import BaseModel, Field

class DomainExecutionResult(BaseModel):
    """Risultato esecuzione di un domain handler."""
    
    success: bool                           # True se esecuzione riuscita
    domain: str                             # Nome del dominio (es. "sports_nba")
    tool_name: str | None = None            # Nome del tool chiamato
    data: dict[str, Any] = Field(default_factory=dict)  # Dati risultato
    error: str | None = None                # Messaggio errore se fallito
    latency_ms: float = 0.0                 # Latenza esecuzione
    cached: bool = False                    # True se risultato da cache
```

> **⚠️ IMPORTANTE**: Usare sempre `domain=` e mai `source=`

### DomainVolatility

```python
from enum import Enum

class DomainVolatility(str, Enum):
    """Classificazione volatilità dati per dominio."""
    
    REAL_TIME = "real_time"      # TTL <1h (live prices, sports scores)
    VOLATILE = "volatile"        # TTL 1-24h (sports, finance, weather)
    PERIODIC = "periodic"        # TTL 1-6h (weather forecasts, news)
    SEMI_VOLATILE = "semi_volatile"  # TTL 7d-6mo (workspace, science)
    STABLE = "stable"            # TTL 1-2yr (medical, knowledge)
    PERMANENT = "permanent"      # Never expires (user preferences)
```

> **⚠️ IMPORTANTE**: Usare solo valori esistenti. `REALTIME` e `DYNAMIC` NON esistono.

### DomainCapability

```python
class DomainCapability(BaseModel):
    """Descrive una capability esposta dal dominio."""
    
    name: str                    # Nome univoco capability
    description: str             # Descrizione per LLM/semantic search
    keywords: list[str] = []     # Keywords per routing
    example_queries: list[str] = []  # Query di esempio
```

---

## 📊 Domini Implementati

| Dominio            | Coverage | Volatility    | Tools |
| ------------------ | -------- | ------------- | ----- |
| `entertainment`    | **100%** | VOLATILE      | 4     |
| `finance_crypto`   | **100%** | REAL_TIME     | 20    |
| `google_workspace` | **99%**  | SEMI_VOLATILE | 38    |
| `sports_nba`       | **100%** | VOLATILE      | 7     |
| `sports_booking`   | **100%** | REAL_TIME     | 6     |
| `medical`          | **99%**  | STABLE        | 8     |
| `knowledge_media`  | **100%** | PERIODIC      | 3     |
| `science_research` | **100%** | SEMI_VOLATILE | 7     |
| `web_search`       | **100%** | VOLATILE      | 4     |
| `tech_coding`      | **98%**  | VOLATILE      | 10    |
| `jobs`             | **97%**  | VOLATILE      | 2     |
| `travel`           | **97%**  | REAL_TIME     | 12    |
| `food`             | **92%**  | PERIODIC      | 6     |
| `geo_weather`      | **82%**  | REAL_TIME     | 3     |
| `utility`          | **89%**  | VOLATILE      | 2     |

---

## 🐍 Esempio Implementazione Handler

```python
from typing import Any
from me4brain.core.interfaces import (
    DomainHandler,
    DomainExecutionResult,
    DomainVolatility,
    DomainCapability,
)

class MyDomainHandler(DomainHandler):
    """Handler per il dominio my_domain."""
    
    KEYWORDS = ["keyword1", "keyword2", "keyword3"]
    
    @property
    def domain_name(self) -> str:
        return "my_domain"
    
    @property
    def volatility(self) -> DomainVolatility:
        return DomainVolatility.VOLATILE  # Solo valori esistenti!
    
    @property
    def default_ttl_hours(self) -> int | None:
        return 24
    
    @property
    def capabilities(self) -> list[DomainCapability]:
        return [
            DomainCapability(
                name="my_capability",
                description="Descrizione per LLM routing",
                keywords=["keyword1", "keyword2"],
                example_queries=["esempio query 1", "esempio query 2"],
            )
        ]
    
    # Signature CORRETTA: (query, analysis, context)
    async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
        query_lower = query.lower()
        matches = sum(1 for kw in self.KEYWORDS if kw in query_lower)
        if matches >= 2:
            return 0.9
        elif matches == 1:
            return 0.7
        return 0.0
    
    # Signature CORRETTA: (query, analysis, context) -> list[DomainExecutionResult]
    async def execute(
        self,
        query: str,
        analysis: dict[str, Any],
        context: dict[str, Any],
    ) -> list[DomainExecutionResult]:
        from .tools.my_api import execute_tool
        
        data = await execute_tool("my_tool", {"query": query})
        
        return [DomainExecutionResult(
            success=not data.get("error"),
            domain=self.domain_name,  # Usare domain, non source!
            tool_name="my_tool",
            data=data if not data.get("error") else None,
            error=data.get("error"),
        )]
    
    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        from .tools.my_api import execute_tool
        return await execute_tool(tool_name, arguments)
```

---

## ⚠️ Errori Comuni da Evitare

### 1. Signature `execute()` errata

❌ **SBAGLIATO**:
```python
async def execute(self, query: str, context: dict | None = None) -> DomainExecutionResult:
```

✅ **CORRETTO**:
```python
async def execute(
    self,
    query: str,
    analysis: dict[str, Any],
    context: dict[str, Any],
) -> list[DomainExecutionResult]:
```

### 2. Attributo `source` invece di `domain`

❌ **SBAGLIATO**:
```python
return DomainExecutionResult(success=True, data=result, source="my_domain")
```

✅ **CORRETTO**:
```python
return DomainExecutionResult(success=True, data=result, domain="my_domain")
```

### 3. Enum volatility inesistenti

❌ **SBAGLIATO**:
```python
return DomainVolatility.REALTIME  # Non esiste!
return DomainVolatility.DYNAMIC   # Non esiste!
```

✅ **CORRETTO**:
```python
return DomainVolatility.REAL_TIME  # Underscore!
return DomainVolatility.VOLATILE   # Per dati dinamici
```

### 4. `can_handle()` sincrono invece di async

❌ **SBAGLIATO**:
```python
def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
    # Errore: "object float can't be used in 'await' expression"
```

✅ **CORRETTO**:
```python
async def can_handle(self, query: str, analysis: dict[str, Any]) -> float:
    # Sempre async, anche se non fa I/O!
```

> [!CAUTION]
> Handler con `can_handle()` sincrono causano errore **500 Internal Server Error** sull'endpoint SSE `/v1/memory/query/stream`.

---

## 🧪 Testing

Ogni handler deve avere test che coprono:

1. **Properties**: `domain_name`, `capabilities`, `volatility`, `default_ttl_hours`
2. **can_handle()**: Score calculation, edge cases, no-match scenarios
3. **execute()**: Tool routing, error handling, API mocking
4. **execute_tool()**: Chiamate dirette a tool API

```bash
# Esegui test handler
uv run pytest tests/unit/test_domain_handlers.py -v

# Con coverage
uv run pytest tests/unit/test_domain_handlers.py --cov=src/me4brain/domains --cov-report=term-missing
```

---

## 📁 Struttura File

```
src/me4brain/domains/
├── __init__.py
├── entertainment/
│   ├── handler.py          # EntertainmentHandler
│   └── tools/
│       └── entertainment_api.py
├── finance_crypto/
│   ├── handler.py          # FinanceCryptoHandler
│   └── tools/
│       └── finance_api.py
├── google_workspace/
│   ├── handler.py          # GoogleWorkspaceHandler
│   └── tools/
│       └── google_api.py
└── ...                      # Altri 11 domini
```
