# Me4BrAIn SDK

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python SDK per la piattaforma **Me4BrAIn** - Tool Calling Engine per agenti AI.

Permette di integrare facilmente il Tool Calling Engine nelle applicazioni Python, fornendo accesso a **126+ tools** attraverso query in linguaggio naturale o chiamate dirette.

---

## 📦 Installazione

### Da PyPI (quando disponibile)

```bash
pip install me4brain-sdk
```

### Da sorgente (development)

```bash
cd me4brain/sdk
pip install -e .
```

### Con dipendenze di sviluppo

```bash
pip install -e ".[dev]"
```

---

## 🚀 Quick Start

### Client Asincrono

```python
import asyncio
from me4brain_sdk import Me4BrAInClient

async def main():
    async with Me4BrAInClient("http://localhost:8000") as client:
        # Query in linguaggio naturale
        response = await client.engine.query("Qual è il prezzo del Bitcoin?")
        print(response.answer)

asyncio.run(main())
```

### Client Sincrono

```python
from me4brain_sdk import Me4BrAInSyncClient

with Me4BrAInSyncClient("http://localhost:8000") as client:
    response = client.engine.query("Che tempo fa a Roma?")
    print(response.answer)
```

---

## 📖 Guida Completa

### Configurazione Client

Il client può essere configurato tramite parametri o variabili d'ambiente:

```python
from me4brain_sdk import Me4BrAInClient, Me4BrAInConfig

# Configurazione esplicita
client = Me4BrAInClient(
    base_url="http://localhost:8000",
    api_key="your-api-key",
    tenant_id="your-tenant",
    timeout=30.0
)

# Configurazione da oggetto
config = Me4BrAInConfig(
    base_url="http://api.example.com",
    timeout=60.0,
    max_retries=5
)
client = Me4BrAInClient(config=config)
```

#### Variabili d'Ambiente

| Variabile              | Descrizione                 | Default                        |
| ---------------------- | --------------------------- | ------------------------------ |
| `ME4BRAIN_BASE_URL`    | URL base dell'API           | `http://localhost:8089/api/v1` |
| `ME4BRAIN_API_KEY`     | API key per autenticazione  | `None`                         |
| `ME4BRAIN_TENANT_ID`   | Tenant ID per multi-tenancy | `default`                      |
| `ME4BRAIN_TIMEOUT`     | Timeout richieste (secondi) | `30.0`                         |
| `ME4BRAIN_MAX_RETRIES` | Numero massimo retry        | `3`                            |

---

## 🏗️ Architecture Overview

Il Tool Calling Engine utilizza un'architettura a tre fasi per processare le query in linguaggio naturale:

```
┌─────────────────────────────────────────────────────────────┐
│                    Tool Calling Pipeline                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐ │
│  │   Router     │──▶│   Executor   │──▶│   Synthesizer    │ │
│  │ LLM + Tools  │   │   Parallel   │   │      LLM         │ │
│  └──────────────┘   └──────────────┘   └──────────────────┘ │
│                                                              │
│  126+ Tools │ 14 Domains │ Semantic Routing                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Semantic Tool Routing

Le descrizioni dei tool sono ottimizzate per **embedding-based matching**:

- **Action-Oriented**: Ogni tool inizia con un verbo (Get, Search, Find, Create, Track)
- **Source Indication**: Specifica la fonte dati (from CoinGecko, on TMDB, via OpenMeteo)  
- **Trigger Phrases**: Include esempi di query naturali per migliorare il matching

**Esempio descrizione tool:**
```
"Search for movies on TMDB (The Movie Database). Find films by title, 
returns posters, ratings, and overviews. Use when user asks 'find movie X', 
'search for film Y', 'what movies about Z'."
```

Questo pattern permette al Router LLM di selezionare accuratamente i tool appropriati basandosi sulla query utente.

---

## 🔧 API Reference

### Engine Namespace

Il namespace `client.engine` fornisce accesso al Tool Calling Engine.

#### `query()`

Esegue una query in linguaggio naturale attraverso il pipeline completo:
1. **Router**: LLM seleziona i tool appropriati
2. **Executor**: Esegue i tool in parallelo
3. **Synthesizer**: Sintetizza i risultati in una risposta coerente

```python
response = await client.engine.query(
    query="Qual è il prezzo del Bitcoin e che tempo fa a Milano?",
    include_raw_results=True,  # Include risultati raw dei tool
    timeout_seconds=30.0       # Timeout per la query
)

# Accesso alla risposta
print(response.answer)                    # Risposta sintetizzata
print(response.total_latency_ms)          # Latenza totale in ms
print(len(response.tools_called))         # Numero di tool chiamati

# Dettagli sui tool eseguiti
for tool in response.tools_called:
    print(f"{tool.tool_name}: {'✅' if tool.success else '❌'}")
    print(f"  Argomenti: {tool.arguments}")
    print(f"  Latenza: {tool.latency_ms:.0f}ms")
    if tool.error:
        print(f"  Errore: {tool.error}")

# Risultati raw (se include_raw_results=True)
if response.raw_results:
    for result in response.raw_results:
        print(result)
```

**Parametri:**

| Parametro             | Tipo    | Default    | Descrizione                  |
| --------------------- | ------- | ---------- | ---------------------------- |
| `query`               | `str`   | *required* | Query in linguaggio naturale |
| `include_raw_results` | `bool`  | `False`    | Include risultati JSON raw   |
| `timeout_seconds`     | `float` | `30.0`     | Timeout per la query         |

**Ritorna:** `EngineQueryResponse`

---

#### `call()`

Chiama direttamente un tool per nome, bypassando il router LLM.

```python
# Chiamata diretta con argomenti keyword
result = await client.engine.call(
    "coingecko_price",
    ids="bitcoin,ethereum",
    vs_currencies="usd,eur"
)

print(result)
# Output:
# {
#     "prices": {
#         "bitcoin": {"usd": 77500, "eur": 73800},
#         "ethereum": {"usd": 3200, "eur": 3050}
#     },
#     "source": "CoinGecko"
# }
```

**Parametri:**

| Parametro     | Tipo  | Default    | Descrizione           |
| ------------- | ----- | ---------- | --------------------- |
| `tool_name`   | `str` | *required* | Nome del tool         |
| `**arguments` | `Any` | -          | Argomenti per il tool |

**Ritorna:** Risultato del tool (dict, list, o altro JSON-serializable)

**Eccezioni:** `ToolExecutionError` se l'esecuzione fallisce

---

#### `list_tools()`

Lista i tool disponibili nel catalog con filtri opzionali.

```python
# Lista tutti i tool
all_tools = await client.engine.list_tools()
print(f"Tool totali: {len(all_tools)}")

# Filtra per dominio
finance_tools = await client.engine.list_tools(domain="finance_crypto")
for tool in finance_tools:
    print(f"{tool.name}: {tool.description[:60]}...")

# Filtra per categoria
crypto_tools = await client.engine.list_tools(category="crypto")

# Cerca per nome/descrizione
weather_tools = await client.engine.list_tools(search="weather")
```

**Parametri:**

| Parametro  | Tipo          | Default | Descrizione               |
| ---------- | ------------- | ------- | ------------------------- |
| `domain`   | `str \| None` | `None`  | Filtra per dominio        |
| `category` | `str \| None` | `None`  | Filtra per categoria      |
| `search`   | `str \| None` | `None`  | Cerca in nome/descrizione |

**Ritorna:** `list[ToolInfo]`

---

#### `get_tool()`

Ottiene i dettagli completi di un tool specifico.

```python
tool = await client.engine.get_tool("openmeteo_weather")

print(f"Nome: {tool.name}")
print(f"Dominio: {tool.domain}")
print(f"Descrizione: {tool.description}")
print(f"Parametri:")
for name, param in tool.parameters.items():
    required = "✓" if param.get("required") else "○"
    print(f"  {required} {name}: {param.get('type')} - {param.get('description')}")
```

**Parametri:**

| Parametro   | Tipo  | Default    | Descrizione   |
| ----------- | ----- | ---------- | ------------- |
| `tool_name` | `str` | *required* | Nome del tool |

**Ritorna:** `ToolInfo`

**Eccezioni:** `Me4BrAInError` (404) se tool non trovato

---

#### `stats()`

Ottiene statistiche sul catalog dei tool.

```python
stats = await client.engine.stats()

print(f"Tool totali: {stats.total_tools}")
print(f"Domini: {len(stats.domains)}")

for domain in stats.domains:
    print(f"\n{domain.domain} ({domain.tool_count} tools):")
    for tool_name in domain.tools[:5]:
        print(f"  • {tool_name}")
    if len(domain.tools) > 5:
        print(f"  ... e altri {len(domain.tools) - 5}")
```

**Ritorna:** `CatalogStats`

---

## 📊 Modelli di Risposta

### EngineQueryResponse

```python
class EngineQueryResponse:
    query: str                      # Query originale
    answer: str                     # Risposta sintetizzata
    tools_called: list[ToolCallInfo]  # Tool eseguiti
    total_latency_ms: float         # Latenza totale
    raw_results: list[dict] | None  # Risultati raw (opzionale)
```

### ToolCallInfo

```python
class ToolCallInfo:
    tool_name: str           # Nome del tool
    arguments: dict          # Argomenti passati
    success: bool            # Esecuzione riuscita
    latency_ms: float        # Latenza in ms
    error: str | None        # Messaggio errore (se fallito)
```

### ToolInfo

```python
class ToolInfo:
    name: str                # Nome univoco del tool
    description: str         # Descrizione funzionalità
    domain: str | None       # Dominio (es. "finance_crypto")
    category: str | None     # Categoria (es. "crypto")
    parameters: dict         # Schema parametri
```

### CatalogStats

```python
class CatalogStats:
    total_tools: int              # Numero totale tool
    domains: list[DomainStats]    # Stats per dominio

class DomainStats:
    domain: str           # Nome dominio
    tool_count: int       # Numero tool
    tools: list[str]      # Lista nomi tool
```

---

## 🧠 Skills API (v0.15.0+)

L'SDK supporta il nuovo sistema di **Skill Crystallization** basato sul Voyager pattern.

### Skills Namespace

Il namespace `client.skills` fornisce accesso alla gestione skills.

#### `list_skills()`

Lista le skill disponibili (cristallizzate o esplicite).

```python
# Lista tutte le skill
skills = await client.skills.list_skills()
print(f"Skill totali: {len(skills)}")

# Filtra per tipo
crystallized = await client.skills.list_skills(skill_type="crystallized")
for skill in crystallized:
    print(f"{skill.name}: {skill.description[:60]}...")
```

#### `list_pending()`

Lista le skill in attesa di approvazione HITL.

```python
pending = await client.skills.list_pending()
for skill in pending:
    print(f"[{skill.risk_level}] {skill.name}")
    print(f"  Tool chain: {', '.join(skill.tool_chain)}")
    print(f"  Created: {skill.created_at}")
```

#### `approve()` / `reject()`

Approva o rifiuta una skill in pending.

```python
# Approva skill
result = await client.skills.approve(
    skill_id="abc123",
    note="Approved by admin"
)
print(result.message)

# Rifiuta skill
result = await client.skills.reject(
    skill_id="xyz789",
    note="Not relevant for production"
)
```

#### `approval_stats()`

Ottiene statistiche sul workflow di approvazione.

```python
stats = await client.skills.approval_stats()
print(f"Pending: {stats.pending}")
print(f"Approved: {stats.approved}")
print(f"Rejected: {stats.rejected}")
```

### Modelli Skills

```python
class PendingSkill:
    id: str                    # ID skill
    name: str                  # Nome skill
    description: str           # Descrizione
    risk_level: str            # SAFE, NOTIFY, CONFIRM, DENY
    tool_chain: list[str]      # Tool usati
    status: str                # pending, approved, rejected
    created_at: datetime       # Data creazione

class SkillInfo:
    id: str
    name: str
    description: str
    skill_type: str            # explicit, crystallized
    enabled: bool
    usage_count: int
    success_rate: float
    confidence: float

class ApprovalStats:
    pending: int
    approved: int
    rejected: int
```

### Risk Levels

Le skill sono classificate per livello di rischio:

| Livello   | Azione                        | Esempio Tool                 |
| --------- | ----------------------------- | ---------------------------- |
| 🟢 SAFE    | Auto-approvazione             | search, weather, stock_price |
| 🟡 NOTIFY  | Log only                      | file_write, create_doc       |
| 🔴 CONFIRM | Richiede approvazione HITL    | delete, send_email           |
| ⛔ DENY    | Bloccato (pattern pericolosi) | rm -rf, sudo, eval           |

---

## ⚠️ Gestione Errori

L'SDK definisce eccezioni specifiche per diversi tipi di errore:

```python
from me4brain_sdk import (
    Me4BrAInError,       # Base exception
    AuthenticationError,  # 401/403 - Auth fallita
    RateLimitError,       # 429 - Rate limit superato
    ServerError,          # 5xx - Errore server
    ToolExecutionError,   # Tool execution fallita
)

try:
    response = await client.engine.query("Prezzo Bitcoin")
except AuthenticationError as e:
    print(f"Autenticazione fallita: {e.message}")
    print(f"Status code: {e.status_code}")
except RateLimitError:
    print("Rate limit superato, riprova più tardi")
except ToolExecutionError as e:
    print(f"Tool fallito: {e.message}")
except ServerError as e:
    print(f"Errore server: {e.message}")
except Me4BrAInError as e:
    print(f"Errore generico: {e.message}")
```

---

## 🌐 Domini Disponibili

Il Tool Calling Engine include **126 tool** organizzati in **14 domini**:

| Dominio            | Tool | Descrizione                                                          |
| ------------------ | ---- | -------------------------------------------------------------------- |
| `google_workspace` | 38   | Drive, Gmail, Calendar, Docs, Sheets, Slides, Meet, Forms, Classroom |
| `finance_crypto`   | 15   | CoinGecko, Binance, Yahoo Finance, Finnhub, FRED, EDGAR, Alpaca      |
| `sports_nba`       | 10   | BallDontLie, ESPN, Odds API, nba_api                                 |
| `tech_coding`      | 10   | GitHub, NPM, PyPI, Stack Overflow, Piston                            |
| `medical`          | 9    | RxNorm, PubMed, ClinicalTrials.gov, Europe PMC                       |
| `travel`           | 8    | OpenSky, AviationStack, ADS-B One                                    |
| `science_research` | 7    | ArXiv, Crossref, OpenAlex, Semantic Scholar                          |
| `entertainment`    | 6    | TMDB, Open Library, Last.fm                                          |
| `food`             | 6    | TheMealDB, Open Food Facts                                           |
| `geo_weather`      | 5    | OpenMeteo, USGS Earthquakes, Nager Holidays                          |
| `web_search`       | 4    | DuckDuckGo, Tavily                                                   |
| `knowledge_media`  | 3    | Wikipedia, Hacker News, Open Library                                 |
| `jobs`             | 2    | RemoteOK, Arbeitnow                                                  |
| `utility`          | 2    | httpbin                                                              |

### Esempi per Dominio

```python
# Finance
btc = await client.engine.call("coingecko_price", ids="bitcoin")
quote = await client.engine.call("yahoo_quote", symbol="AAPL")

# Weather
weather = await client.engine.call("openmeteo_weather", city="Rome")

# Research
papers = await client.engine.call("arxiv_search", query="transformers", max_results=5)

# Tech
repo = await client.engine.call("github_repo", owner="python", repo="cpython")
```

---

## 🧪 Esempi Avanzati

### Query Multi-Domain

```python
async def multi_domain_query():
    async with Me4BrAInClient() as client:
        # Una singola query che utilizza tool da domini diversi
        response = await client.engine.query(
            "Qual è il prezzo del Bitcoin, che tempo fa a Milano, "
            "e quali sono le ultime notizie tech su Hacker News?"
        )
        
        print("Risposta:")
        print(response.answer)
        
        print("\nTool utilizzati:")
        for tool in response.tools_called:
            status = "✅" if tool.success else "❌"
            print(f"  {status} {tool.tool_name} ({tool.latency_ms:.0f}ms)")
```

### Batch Processing

```python
async def batch_crypto_prices():
    async with Me4BrAInClient() as client:
        coins = ["bitcoin", "ethereum", "solana", "cardano"]
        
        # Chiamate parallele con asyncio.gather
        tasks = [
            client.engine.call("coingecko_price", ids=coin, vs_currencies="usd")
            for coin in coins
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for coin, result in zip(coins, results):
            if isinstance(result, Exception):
                print(f"{coin}: ❌ {result}")
            else:
                price = result["prices"][coin]["usd"]
                print(f"{coin}: ${price:,.2f}")
```

### Error Recovery

```python
async def robust_query(query: str, retries: int = 3):
    async with Me4BrAInClient() as client:
        for attempt in range(retries):
            try:
                return await client.engine.query(query)
            except RateLimitError:
                wait = 2 ** attempt
                print(f"Rate limited, waiting {wait}s...")
                await asyncio.sleep(wait)
            except ServerError as e:
                if attempt == retries - 1:
                    raise
                print(f"Server error, retrying... ({e.message})")
        
        raise Me4BrAInError("Max retries exceeded")
```

### Context Manager con Cleanup

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_me4brain_client():
    client = Me4BrAInClient()
    try:
        yield client
    finally:
        await client.close()

# Uso
async with get_me4brain_client() as client:
    response = await client.engine.query("Hello world")
```

---

## 🔒 Autenticazione

### API Key

```python
client = Me4BrAInClient(
    base_url="http://api.example.com",
    api_key="sk-your-secret-key"
)
```

### Multi-Tenancy

```python
client = Me4BrAInClient(
    base_url="http://api.example.com",
    tenant_id="tenant-123",
    api_key="sk-tenant-key"
)
```

---

## 📝 Type Hints

L'SDK è completamente tipizzato per un'ottima esperienza IDE:

```python
from me4brain_sdk import (
    Me4BrAInClient,
    EngineQueryResponse,
    ToolInfo,
    ToolCallInfo,
    CatalogStats,
    DomainStats,
)

async def typed_example() -> EngineQueryResponse:
    async with Me4BrAInClient() as client:
        response: EngineQueryResponse = await client.engine.query("Test")
        tools: list[ToolInfo] = await client.engine.list_tools()
        stats: CatalogStats = await client.engine.stats()
        return response
```

---

## 🧪 Testing

### Unit Tests con Mock

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_query():
    with patch("me4brain_sdk.client.httpx.AsyncClient") as mock:
        mock_client = AsyncMock()
        mock_client.request.return_value.json.return_value = {
            "query": "test",
            "answer": "Test answer",
            "tools_called": [],
            "total_latency_ms": 100,
        }
        mock_client.request.return_value.status_code = 200
        mock.return_value.__aenter__.return_value = mock_client
        
        async with Me4BrAInClient() as client:
            response = await client.engine.query("test")
            assert response.answer == "Test answer"
```

---

## 📄 License

MIT License - vedi [LICENSE](LICENSE) per i dettagli.

---

## 🔗 Link Utili

- [Me4BrAIn Core](https://github.com/fulvian/me4brain) - Backend principale
- [API Documentation](http://localhost:8000/docs) - OpenAPI/Swagger
- [Issue Tracker](https://github.com/fulvian/me4brain/issues) - Bug reports
