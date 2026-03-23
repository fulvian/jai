# REPORT TECNICO COMPLETO
## Sistema di Retrieval e Tool Discovery del Progetto JAI
### Versione Report: 1.0 | Data: 2026-03-23

---

# SEZIONE 1: ARCHITETTURA GENERALE DEL SISTEMA

## 1.1 Panoramica dell'Architettura

Il sistema JAI (Java AI Interface) è un motore di tool calling ibrido che combina:
- **Routing LLM-based** per la classificazione di dominio
- **Retrieval vettoriale** su QDRANT per la selezione degli strumenti
- **Esecuzione parallela** dei tool selezionati
- **Sintesi della risposta** tramite LLM

Il codice risiede in `/Users/fulvio/coding/jai/backend/src/me4brain/`

## 1.2 Componenti Core

| Componente | File | Responsabilità |
|------------|------|----------------|
| `ToolCallingEngine` | `engine/core.py` | Orchestratore principale |
| `ToolCatalog` | `engine/catalog.py` | Catalogo tool discovery |
| `HybridToolRouter` | `engine/hybrid_router/router.py` | Routing ibrido |
| `DomainClassifier` | `engine/hybrid_router/domain_classifier.py` | Classificazione dominio |
| `ToolRetriever` / `LlamaIndexToolRetriever` | `hybrid_router/llama_tool_retriever.py` | Recupero tool |
| `ToolIndexManager` | `hybrid_router/tool_index.py` | Indicizzazione su QDRANT |
| `ParallelExecutor` | `engine/executor.py` | Esecuzione parallela tool |
| `ResponseSynthesizer` | `engine/synthesizer.py` | Sintesi risposta |

## 1.3 Flusso Completo Query-to-Tool

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 0: Security Guardrail (core.py:641-669)               │
│ - ThreatLevel.DANGEROUS/SUSPICIOUS validation               │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 0B: Unified Intent Analyzer (core.py:678-730)          │
│ - IntentType.CONVERSATIONAL → direct LLM response          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: HybridToolRouter.route() (router.py:211-410)       │
│   ├─► Stage 0: ContextRewriter + IntentAnalyzer           │
│   ├─► Stage 1: DomainClassifier.classify_with_fallback()  │
│   ├─► Stage 1b: QueryDecomposer (se multi-intent)         │
│   └─► Stage 2: ToolRetriever.retrieve()                   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: ParallelExecutor.execute() (executor.py)            │
│   - Retry with exponential backoff                          │
│   - Permission validation                                   │
│   - Dependency detection (producers → consumers)            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: ResponseSynthesizer.synthesize()                  │
└─────────────────────────────────────────────────────────────┘
```

---

# SEZIONE 2: DOMAIN CLASSIFICATION SYSTEM

## 2.1 Pipeline di Classificazione

La classificazione del dominio avviene in `DomainClassifier.classify_with_fallback()` (`domain_classifier.py:954-992`):

```python
# 1. Prova: LLM classify con 3 retry e exponential backoff
classification = await classify_with_retries(query, ...)

# 2. Se fallisce: _fallback_classification() basato su keywords
if classification.confidence < 0.5 or not classification.domains:
    classification = _fallback_classification(query)
    used_fallback = True

# 3. Se needs_fallback (nessun dominio o bassa confidenza):
# Aggiunge fallback_domains = ["web_search"]
```

## 2.2 Configurazione

**File:** `types.py` (HybridRouterConfig)

```python
fallback_domains: list[str] = field(default_factory=lambda: ["web_search"])
confidence_threshold: float = 0.5
```

## 2.3 Keyword Map Completo - CRITICO

**File:** `domain_classifier.py` lines 839-952

### Mappa Completa KEYWORD_DOMAIN_MAP

```python
KEYWORD_DOMAIN_MAP = {
    "geo_weather": [
        "meteo", "tempo", "pioggia", "temperatura", "weather",
        "forecast", "neve", "vento",
    ],
    
    "finance_crypto": [
        "prezzo", "bitcoin", "crypto", "azioni", "stock",
        "borsa", "trading", "ethereum", "finanza",
        # NOTA: "scommesse", "betting", "odds" RIMOSSI - appartengono a sports_nba
    ],
    
    "web_search": [
        "cerca", "trova", "search", "find", "ricerca", "notizie", "news",
    ],
    
    "google_workspace": [
        "email", "mail", "gmail", "calendar", "calendario",
        "drive", "documento", "doc", "sheet", "foglio",
    ],
    
    "productivity": [
        "promemoria", "reminder", "nota", "task", "attività", "appuntamento",
    ],
    
    "travel": [
        "volo", "hotel", "viaggio", "prenota", "flight", "booking", "aeroporto",
    ],
    
    "food": [
        "ristorante", "mangiare", "pizza", "cibo", "restaurant", "menu",
    ],
    
    "sports_nba": [
        # Core NBA keywords
        "nba", "basket", "basketball", "partita", "partite",
        # Betting keywords IT
        "scommessa", "scommesse", "pronostico", "pronostici",
        "sistema scommesse", "value bet",
        # Betting keywords EN
        "betting", "bet", "bets", "odds", "spread", "over/under",
        "over under", "moneyline", "point spread", "betting lines",
        "betting tips", "picks", "predictions", "wager",
        # Italian betting
        "analisi scommesse", "pronostico vincente", "sistema vincente",
        # Team names
        "lakers", "celtics", "warriors", "bulls", "heat", "knicks",
        "nets", "bucks", "nuggets", "suns", "76ers", "sixers",
    ],
    
    "sports_booking": [
        "campo", "tennis", "calcetto", "padel", "prenotare campo",
    ],
    
    "science_research": [
        "paper", "ricerca", "arxiv", "pubmed", "scientifica", "studio",
    ],
    
    "medical": [
        "farmaco", "medico", "sintomo", "salute", "medicina", "dottore",
    ],
    
    "entertainment": [
        "film", "musica", "cinema", "netflix", "spotify", "serie tv",
    ],
    
    "shopping": [
        "comprare", "amazon", "negozio", "shop", "acquista",
    ],
}
```

### Logica di Matching

```python
# domain_classifier.py lines 940-946
for domain, keywords in KEYWORD_DOMAIN_MAP.items():
    if any(kw in query_lower for kw in keywords):
        if domain in self._domains:
            detected_domains.append(domain)

if not detected_domains:
    detected_domains = self._config.fallback_domains  # = ["web_search"]
```

### Dominio `sports_nba` - CRITICO ISSUE #1

**PROBLEMA IDENTIFICATO:** La keyword list per `sports_nba` è **MANCANTE** le seguenti keywords generiche:

| Keyword MANCANTE | Esempio query |
|-----------------|---------------|
| `games`, `game` | "any **games** tonight?" |
| `score`, `scores` | "what are the **scores**?" |
| `win`, `winning`, `won`, `winner` | "who's **winning**?" |
| `tonight`, `today` | "**tonight**" |
| `schedule` | "**schedule** for this week" |
| `play`, `playing`, `played` | "when do they **play**?" |

**Effetto:** Query come "any games tonight? who's winning?" NON contiene nessuna delle keywords definite → `detected_domains = []` → fallback a `["web_search"]`

## 2.4 Secondary Keyword Source - unified_intent_analyzer.py

**File:** `/Users/fulvio/coding/jai/backend/src/me4brain/engine/unified_intent_analyzer.py`

### `_extract_domains_from_query()` Keywords (lines 658-760)

| Domain | Keywords |
|--------|----------|
| sports_nba | `nba`, `basketball`, `giocatore`, `squadra`, `partita nba`, `lakers`, `celtics`, `warriors` |

**Nota:** Anche qui mancano `games`, `score`, `win`, `winning`, `tonight`, etc.

### AVAILABLE_DOMAINS List (lines 190-208)

```python
AVAILABLE_DOMAINS = {
    "entertainment", "finance_crypto", "food", "geo_weather",
    "google_workspace", "jobs", "knowledge_media", "medical",
    "productivity", "science_research", "shopping", "sports_booking",
    "sports_nba", "tech_coding", "travel", "utility", "web_search",
}
```

---

# SEZIONE 3: SISTEMA DI RETRIEVAL QDRANT

## 3.1 Configurazione QDRANT

**Docker Compose** (`/Users/fulvio/coding/jai/docker-compose.yml`):
```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: jai-qdrant
    ports:
      - "6333:6333"  # HTTP
      - "6334:6334"  # gRPC
    volumes:
      - qdrant_data:/qdrant/storage
```

**Environment Variables** (`backend/.env`):
```
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_URL=http://localhost:6333
QDRANT_GRPC_PORT=6334
```

## 3.2 Collection

**Collection Name:** `me4brain_capabilities`

**Configurazione** (`constants.py`):
```python
CAPABILITIES_COLLECTION = "me4brain_capabilities"
EMBEDDING_DIM = 1024  # BGE-M3 dimension
DISTANCE_METRIC = "COSINE"
```

## 3.3 Embedding Model

**Model:** `BAAI/bge-m3`

**Configurazione** (`embeddings/bge_m3.py`):
- **Dimension:** 1024
- **Device Selection:** MPS (Apple Silicon) → CUDA → CPU
- **Cache:** `models/` directory (HuggingFace cache locale)

**Query Prefix (migliora precision +10-20%):**
```python
QUERY_PREFIX = "Represent this query for retrieval: "
```

**Expected Cosine Similarity Scores:**
| Score Range | Interpretation |
|-------------|----------------|
| 0.70 - 0.85 | Excellent match |
| 0.55 - 0.70 | Good match |
| 0.45 - 0.55 | Fair match |
| 0.30 - 0.45 | Weak match |
| < 0.30 | Irrelevant |

## 3.4 Client Initialization

**Punti di inizializzazione multipli:**

| File | Client Type | Notes |
|------|-------------|-------|
| `memory/procedural.py` | AsyncQdrantClient | Tool memory |
| `memory/episodic.py` | AsyncQdrantClient | gRPC support |
| `engine/core.py` | Both sync & async | 60s timeout |
| `engine/hybrid_router/tool_index.py` | LlamaIndex wrapper | Primary indexing |

## 3.5 Two-Stage Retrieval Architecture

### Stage 1: Coarse Vector Retrieval

**File:** `llama_tool_retriever.py` lines 115-133

```python
retriever = VectorIndexRetriever(
    index=index,
    similarity_top_k=self._config.coarse_top_k,  # 30
    filters=domain_filter,  # Metadata filter per domain
)
nodes = await retriever.aretrieve(query)
```

### Stage 2: LLM Reranking

```python
if self._reranker and len(nodes) > 0:
    nodes = await asyncio.wait_for(
        asyncio.to_thread(_run_reranking),
        timeout=600.0,  # 10 MINUTI - troppo alto!
    )
```

### Domain Filtering

**File:** `llama_tool_retriever.py` lines 214-227

```python
def _build_domain_filter(self, domains: list[str]) -> MetadataFilters:
    if len(domains) == 1:
        return MetadataFilters(
            filters=[MetadataFilter(key="domain", value=domains[0])],
        )
    # Multiple domains: OR condition
    return MetadataFilters(
        filters=[MetadataFilter(key="domain", value=domain) for domain in domains],
        condition=FilterCondition.OR,
    )
```

**CRITICO:** Se il dominio è `web_search`, vengono cercati SOLO i tool di web_search. I tool NBA NON vengono mai cercati.

## 3.6 Similarity Thresholds

**File:** `types.py` (HybridRouterConfig)

```python
similarity_thresholds: dict[str, float] = field(
    default_factory=lambda: {
        "low": 0.72,    # Only very relevant tools
        "medium": 0.62, # Moderate threshold
        "high": 0.52,   # Include marginal but still relevant
    }
)
min_similarity_score: float = 0.40  # Absolute floor
```

---

# SEZIONE 4: TOOL INDEXING PIPELINE

## 4.1 Indexing Flow

**Entry Point:** `ToolCallingEngine._create_with_hybrid_routing()` (`core.py:344-359`)

```python
if tool_index is not None:
    indexed_count = await tool_index.build_from_catalog(
        tool_schemas=schemas,
        tool_domains=tool_domains,
        force_rebuild=False,  # Hash-based change detection
    )
```

## 4.2 ToolIndexManager.build_from_catalog()

**File:** `tool_index.py` lines 155-299

### Step 1: Hash-Based Change Detection (lines 179-197)

```python
current_hash = self._compute_catalog_hash(tool_schemas, tool_domains)
stored_hash = self._get_stored_hash()
if stored_hash == current_hash and not force_rebuild:
    # Skip indexing if hash matches
    return 0
```

### Step 2: Collection Recreation (lines 206-218)

```python
self._client.delete_collection(CAPABILITIES_COLLECTION)
await self._ensure_collection()
```

### Step 3: Node Creation (lines 222-275)

Per ogni tool schema:
1. Estrae name, description, parameters
2. Ottiene hierarchical metadata da `tool_hierarchy.yaml`
3. Costruisce SOTA embedding text via `_build_sota_embed_text()`
4. Crea `TextNode` con unified metadata schema

## 4.3 Embedding Text Template

**File:** `tool_index.py` lines 314-357

```python
embed_text = f"""[search_query]: Tool: {tool_name}
Domain: {hierarchy_str}
Purpose: {description}
Use when user wants to: {use_when}
Parameters: {param_hints if param_hints else "none"}
NOT suitable for: {not_suitable}"""
```

### Esempio per `nba_live_scoreboard`

```
[search_query]: Tool: nba_live_scoreboard
Domain: sports_nba
Purpose: Get live NBA scores from ESPN. Shows games in progress, final scores, and today's schedule. Use when user asks 'NBA scores now', 'live games', 'who's winning'.
Use when user wants to: get, list
Parameters: none
NOT suitable for: other sports_nba sub-categories
```

## 4.4 Intent Extraction Issue - CRITICO ISSUE #2

**File:** `tool_index.py` lines 388-421 - `_extract_use_when_phrases()`

```python
def _extract_use_when_phrases(self, description: str, tool_name: str) -> str:
    intent_mappings = {
        "search": "search, find, look for",
        "get": "retrieve, fetch, obtain",
        "list": "list, show, display",
        "create": "create, make, generate",
        "send": "send, transmit, share",
        "calculate": "calculate, compute, evaluate",
        "analyze": "analyze, examine, inspect",
        "check": "check, verify, validate",
        "update": "update, modify, change",
        "delete": "delete, remove, clear",
    }
    
    intents = []
    for keyword, phrases in intent_mappings.items():
        if keyword in desc_lower:
            intents.append(phrases.split(", ")[0])
    
    if not intents:
        words = description.split()[:5]
        intents = [" ".join(words).lower()]
    
    return ", ".join(intents[:3])
```

**PROBLEMA:** Estrae solo verbi generici ("get", "list", "retrieve") invece di usare le frasi specifiche "Use when user asks..." già presenti nella description.

**Esempio:**
- Tool description: `"Use when user asks 'NBA scores now', 'live games', 'who's winning'."`
- Extracted intent: `"get, list"` (perde le query patterns specifiche!)

---

# SEZIONE 5: TOOL CATALOG E DOMAIN HANDLERS

## 5.1 ToolCatalog Discovery

**File:** `engine/catalog.py` - `discover_from_domains()` (lines 165-267)

```python
# 1. Import me4brain.domains package
pkg = importlib.import_module("me4brain.domains")

# 2. Iterate submodules
for _, name, is_pkg in pkgutil.iter_modules(pkg.__path__):
    # 3. Per ogni dominio, cerca tools module
    module = importlib.import_module(f"{package}.{name}.tools")
    
    # 4. Estrai get_tool_definitions() e get_executors()
    definitions = module.get_tool_definitions()
    executors = module.get_executors()
```

## 5.2 PluginRegistry Discovery

**File:** `core/plugin_registry.py` - `discover()` (lines 89-148)

```python
async def discover(self, package: str = "me4brain.domains") -> int:
    for _, name, is_pkg in pkgutil.iter_modules(pkg.__path__):
        if hasattr(module, "get_handler"):
            handler = module.get_handler()
            if isinstance(handler, DomainHandler):
                await self.register(handler)
```

---

# SEZIONE 6: SPORTS_NBA DOMAIN - ANALISI APPROFONDITA

## 6.1 Handler Structure

**File:** `/Users/fulvio/coding/jai/backend/src/me4brain/domains/sports_nba/handler.py`

```python
class SportsNbaHandler(DomainHandler):
    domain_name: str = "sports_nba"
    volatility: Volatility = Volatility.VOLATILE  # 24h TTL
    
    # Tool-First: YES - always calls APIs for fresh data
    tool_first: bool = True
```

## 6.2 NBA Keywords in Handler

**File:** `handler.py` lines 57-121

```python
NBA_KEYWORDS = frozenset({
    "nba", "basket", "basketball", "partita", "partite",
    "giocatore", "giocatori",
    # Team names
    "lakers", "celtics", "warriors", "bulls", "heat", "knicks",
    "nets", "suns", "bucks", "76ers", "mavs", "mavericks",
    "nuggets", "clippers",
    # General
    "quote", "scommesse", "betting", "odds", "infortuni", "injuries",
    "standings", "classifica", "roster", "stats", "statistiche",
    # Players
    "lebron", "curry", "doncic", "giannis", "jokic", "durant",
    "tatum", "morant",
    # Betting
    "pronostico", "pronostici", "prediction", "value",
    "analisi betting", "scommessa", "vincente", "winner", "pick",
    "parlay", "under", "over", "spread", "moneyline",
    "favorite", "underdog", "probabilità", "probability",
    "confidence", "affidabilità",
})
```

**Anche QUI mancano:** `games`, `game`, `score`, `scores`, `win`, `winning`, `tonight`, `today`, `schedule`, `play`, `playing`

## 6.3 Betting Analysis Patterns

**File:** `handler.py` lines 159-170

```python
BETTING_ANALYSIS_PATTERNS = [
    "pronostico", "pronostici", "analisi completa", "analisi partita",
    "prediction", "value bet", "scommessa", "analisi betting", "preview", "pick",
]
```

## 6.4 Cascading Execution Priority

**File:** `handler.py` lines 479-547

Per `_execute_games()`:

| Priority | Source | Auth Required | Cost |
|----------|--------|---------------|------|
| 1st | `nba_api_live_scoreboard` | No | FREE |
| 2nd | `espn_scoreboard` | No | FREE |
| 3rd | `balldontlie_games` | Yes | API Key |

## 6.5 NBA Tools List

**File:** `sports_nba/tools/nba_api.py` - `AVAILABLE_TOOLS` (lines 1483-1507)

```python
AVAILABLE_TOOLS = {
    # BallDontLie (backup)
    "nba_upcoming_games": balldontlie_games,
    "nba_player_search": balldontlie_players,
    "nba_player_stats": balldontlie_stats,
    "nba_teams": balldontlie_teams,
    
    # ESPN (free)
    "nba_live_scoreboard": espn_scoreboard,
    "nba_injuries": espn_injuries,
    "nba_standings": espn_standings,
    "nba_team_stats": espn_team_stats,
    "nba_schedule": espn_schedule,
    
    # The Odds API
    "nba_betting_odds": odds_api_odds,
    
    # Polymarket (free)
    "nba_polymarket_odds": polymarket_nba_odds,
    
    # nba_api Package (official - preferred)
    "nba_api_live": nba_api_live_scoreboard,
    "nba_api_team_games": nba_api_team_games,
    "nba_api_player_career": nba_api_player_career,
    "nba_api_advanced_stats": nba_api_advanced_stats,
    "nba_api_standings": nba_api_standings,
    "nba_api_head_to_head": nba_api_head_to_head,
    "nba_api_player_stats_cascade": nba_api_player_stats_cascade,
}
```

**TOTAL: 17 tools**

## 6.6 ToolDefinition Objects con Description Esatte

### nba_live_scoreboard (lines 1613-1619)
```python
ToolDefinition(
    name="nba_live_scoreboard",
    description="Get live NBA scores from ESPN. Shows games in progress, final scores, and today's schedule. Use when user asks 'NBA scores now', 'live games', 'who's winning'.",
    parameters={},
    domain="sports_nba",
    category="live",
)
```

### nba_upcoming_games (lines 1561-1573)
```python
ToolDefinition(
    name="nba_upcoming_games",
    description="Get upcoming NBA games and schedule. Returns dates, teams, and scores for scheduled and past games. Use when user asks 'NBA games today', 'when do Lakers play', 'next NBA matches'.",
    parameters={"team_id": ToolParameter(...)},
    domain="sports_nba",
    category="games",
)
```

### nba_api_live (lines 1647-1653)
```python
ToolDefinition(
    name="nba_api_live",
    description="Get official NBA live scoreboard from NBA Stats API. Returns real-time game data with periods and arenas. Use when user needs official NBA live data.",
    parameters={},
    domain="sports_nba",
    category="live",
)
```

---

# SEZIONE 7: TOOL HIERARCHY YAML - CRITICO ISSUE #3

## 7.1 Struttura Completa

**File:** `/Users/fulvio/coding/jai/backend/config/tool_hierarchy.yaml`

### sports_nba (5 tools)
```yaml
sports_nba:
  stats:
    player: [nba_player_stats]
    team: [nba_team_stats]
  schedule:
    games: [nba_schedule, nba_live_scores]  # MISMATCH: nba_live_scores NOT EXISTS
  standings:
    rankings: [nba_standings]
```

### finance_crypto (25 tools - MANY MISSING)
```yaml
finance_crypto:
  crypto:
    price: [coingecko_price, binance_price, hyperliquid_price]  # hyperliquid MISSING
    trending: [coingecko_trending]
    chart: [coingecko_chart]
    account: [hyperliquid_account, hyperliquid_positions]  # MISSING
  stocks:
    quote: [yahoo_quote, finnhub_quote, alpaca_quote, nasdaq_quote]  # alpaca MISSING
    news: [finnhub_news]
    bars: [alpaca_bars]  # MISSING
    account: [alpaca_account, alpaca_positions]  # MISSING
  macro:
    fred: [fred_series, fred_search]
    filings: [edgar_filings, edgar_company_info]  # MISSING
  technicals:
    indicators: [technical_indicators]  # MISSING
  fundamentals:
    metrics: [fmp_key_metrics, fmp_ratios, fmp_dcf]  # MISSING
```

### geo_weather (8 tools - 4 MISSING)
```yaml
geo_weather:
  weather:
    forecast: [openmeteo_forecast, openmeteo_current]
    historical: [openmeteo_historical]
  location:
    geocode: [geocode_address, reverse_geocode]  # MISSING
    timezone: [get_timezone]  # MISSING
  air:
    quality: [air_quality]  # MISSING
```

### web_search (5 tools - 2 MISSING)
```yaml
web_search:
  general:
    search: [duckduckgo_search, brave_search, tavily_search]
    news: [duckduckgo_news]  # MISSING
    images: [duckduckgo_images]  # MISSING
```

### entertainment (6 tools - Spotify MISSING)
```yaml
entertainment:
  movies:
    search: [tmdb_search, tmdb_movie_details]
    trending: [tmdb_trending]
  music:
    search: [spotify_search]  # MISSING - uses lastfm instead
    playlist: [spotify_playlist]  # MISSING
```

## 7.2 Discrepanze Critiche

| Domain | Hierarchy Tools | Implementation | Missing |
|--------|-----------------|----------------|---------|
| sports_nba | 5 | 17 | 12 tools missing |
| finance_crypto | 25 | ~13 | ~12 tools missing |
| geo_weather | 8 | 5 | 4 tools missing |
| web_search | 5 | 5 | 2 tools (DDG news/images) |
| entertainment | 6 | 7 | Spotify tools |

**Tool Hierarchy vs Implementation MISMATCH:**
- `nba_live_scores` (in hierarchy) → `nba_api_live` OR `nba_live_scoreboard` (actual)

---

# SEZIONE 8: API KEY LOADING - CRITICO ISSUE #4

## 8.1 API Keys in .env files

**File:** `/Users/fulvio/coding/jai/backend/.env` (line 110)
```
BALLDONTLIE_API_KEY=0baa5751-350b-44b1-bb0b-7808683e4c96
```

**File:** `/Users/fulvio/coding/jai/.env` (line 84)
```
BALLDONTLIE_API_KEY=0baa5751-350b-44b1-bb0b-7808683e4c96
```

## 8.2 Bug in nba_api.py - CRITICO

**File:** `sports_nba/tools/nba_api.py`

**Lines 25-26:**
```python
from dotenv import load_dotenv
```

**Line 52:**
```python
load_dotenv()  # BUG: No path specified!
```

**Problema:** `load_dotenv()` senza path carica `.env` dalla **current working directory**. Se il server parte da una directory diversa da `backend/`, il `.env` non viene trovato.

**Soluzione corretta** (come in altri moduli):
```python
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
load_dotenv(_BACKEND_ROOT / ".env")
```

**Confronto con implementazioni corrette:**

| File | Approach |
|------|----------|
| `user_apis.py` | `HARVESTED_KEYS_PATH = Path(__file__).parent... / "data/harvested_keys.env"` |
| `llm/config.py` | `_PROJECT_ROOT = Path(__file__).resolve().parent...` + `SettingsConfigDict(env_file=...)` |

---

# SEZIONE 9: CASE STUDY NBA - CATENA DI FAILURE

## 9.1 Query Analizzata

```
User: "any games tonight? who's winning?"
```

## 9.2 Flusso di Failure

### Step 0: Intent Analysis
- `unified_intent_analyzer._extract_domains_from_query()` non trova keywords NBA
- Query non è CONVERSATIONAL → prosegue

### Step 1: Domain Classification
```
DomainClassifier.classify_with_fallback()
    │
    ├─► LLM classify() → timeout/fallimento
    │
    └─► _fallback_classification() → KEYWORD MATCHING
            │
            ├─► Query: "any games tonight? who's winning?"
            ├─► sports_nba keywords: ["nba", "basket", "basketball", "partita", ...]
            ├─► MATCH FOUND: NONE (mancano "games", "score", "winning", "tonight")
            └─► detected_domains = []
```

### Step 2: Fallback Domain Assignment
```python
if not detected_domains:
    detected_domains = self._config.fallback_domains  # = ["web_search"]
```

**Result: Domain = `web_search`**

### Step 3: QDRANT Tool Retrieval
```
LlamaIndexToolRetriever.retrieve()
    │
    ├─► Domain filter: web_search ONLY
    ├─► QDRANT search: me4brain_capabilities
    │       └─► WHERE domain = "web_search"
    │       └─► NBA tools are NOT in web_search domain
    │       └─► Result: 0 tools retrieved
    │
    └─► Fallback: smart_search triggered
            └─► Returns Italian football scandal
```

## 9.3 Root Cause Analysis

| Priority | Issue | Location | Impact |
|----------|-------|----------|--------|
| 🔴 CRITICAL | Missing generic sports keywords | `domain_classifier.py:886-932` | Query routed to wrong domain |
| 🔴 CRITICAL | API key loading bug | `nba_api.py:52` | Keys not loaded if CWD wrong |
| 🟡 HIGH | Incomplete tool hierarchy | `tool_hierarchy.yaml` | 12+ NBA tools not in hierarchy |
| 🟡 MEDIUM | Generic intent extraction | `tool_index.py:388-421` | Loses specific query patterns |
| 🟢 LOW | Threshold may be too high | `types.py:177` | Filters casual phrasing |

---

# SEZIONE 10: QDRANT INDEXING STATUS

## 10.1 Are Tools Indexed?

**SI** - Gli 18 tool NBA sono indicizzati in QDRANT (`me4brain_capabilities`).

**Pipeline:**
1. `ToolCallingEngine._create_with_hybrid_routing()` chiama `tool_index.build_from_catalog()`
2. `ToolIndexManager` usa hash-based change detection
3. Se catalogo cambiato → reindicizza

## 10.2 Embedded Text per NBA Tools

### nba_live_scoreboard
```
[search_query]: Tool: nba_live_scoreboard
Domain: sports_nba
Purpose: Get live NBA scores from ESPN. Shows games in progress, final scores, and today's schedule. Use when user asks 'NBA scores now', 'live games', 'who's winning'.
Use when user wants to: get, list
Parameters: none
NOT suitable for: other sports_nba sub-categories
```

**Nota:** "who's winning" É PRESENTE nel testo embedded.

## 10.3 Tool Hierarchy Gaps Effect

15 out of 18 NBA tools NON sono in `tool_hierarchy.yaml`:

| Tool | In Hierarchy? | Hierarchy Path |
|------|---------------|----------------|
| nba_live_scoreboard | ❌ NO | - |
| nba_upcoming_games | ❌ NO | - |
| nba_api_live | ❌ NO | - |
| nba_betting_odds | ❌ NO | - |
| nba_player_stats | ✅ YES | sports_nba > stats > player |
| nba_team_stats | ✅ YES | sports_nba > stats > team |
| nba_schedule | ✅ YES | sports_nba > schedule > games |
| nba_standings | ✅ YES | sports_nba > standings > rankings |

**Result:** Per tool non in hierarchy, `hierarchy_str = "sports_nba"` (senza category/skill) → retrieval meno preciso.

---

# SEZIONE 11: ALL DOMAIN HANDLERS STATUS

## 11.1 Sports NBA
- **Tools:** 17
- **API Keys:** BallDontLie (optional), TheOdds (optional)
- **Fallback:** ✅ Excellent cascade
- **Issues:** 2 critici (keywords, API loading)

## 11.2 Finance Crypto
- **Tools:** ~13 implemented, ~12 missing from hierarchy
- **API Keys:** FINNHUB_API_KEY, FRED_API_KEY, NASDAQ_DATA_API_KEY (all optional)
- **Missing:** hyperliquid, alpaca, edgar, technical_indicators, fmp tools
- **Issues:** 12+ tools not implemented

## 11.3 Travel
- **Tools:** 12
- **API Keys:** AMADEUS_CLIENT_ID/SECRET (optional), GOOGLE_PLACES_API_KEY (optional)
- **Issues:** aviationstack deprecated → errors

## 11.4 Geo Weather
- **Tools:** 5 (8 in hierarchy)
- **API Keys:** None (all free APIs)
- **Missing:** geocode_address, reverse_geocode, get_timezone, air_quality

## 11.5 Science Research
- **Tools:** 7
- **API Keys:** None (all free)
- **Issues:** pubmed duplicated in medical domain

## 11.6 Web Search
- **Tools:** 5
- **API Keys:** TAVILY_API_KEY, BRAVE_SEARCH_API_KEY (optional - DDG is free)
- **Fallback:** ✅ Excellent - DDG → Wikipedia cascade
- **Issues:** duckduckgo_news, duckduckgo_images missing

## 11.7 Medical
- **Tools:** 9
- **API Keys:** None (all NIH/public APIs)
- **Issues:** pubmed duplicated in science_research

## 11.8 Entertainment
- **Tools:** 7
- **API Keys:** TMDB_ACCESS_TOKEN (required), LASTFM_API_KEY (required)
- **Missing:** spotify_playlist, spotify_search

---

# SEZIONE 12: CONFIGURAZIONE RETRIEVAL

## 12.1 HybridRouterConfig Defaults

**File:** `types.py`

```python
@dataclass
class HybridRouterConfig:
    # Retrieval
    use_llamaindex_retriever: bool = True  # Default: QDRant-backed
    use_llm_reranker: bool = True  # ABILITATO
    rerank_top_n: int = 15
    coarse_top_k: int = 30
    min_similarity_score: float = 0.40  # Absolute floor
    
    # Thresholds
    similarity_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "low": 0.72,
            "medium": 0.62,
            "high": 0.52,
        }
    )
    confidence_threshold: float = 0.5
    
    # Domain
    fallback_domains: list[str] = field(default_factory=lambda: ["web_search"])
    
    # Complexity
    complex_threshold_tools: int = 10
    complex_threshold_domains: int = 3
    
    # Payload
    max_payload_bytes: int = 28_000  # 70% of 40KB
```

## 12.2 RRF Merge Weights

**File:** `llama_tool_retriever.py`

```python
WEIGHT_STATIC = 0.95       # Curated Python tools
WEIGHT_CRYSTALLIZED = 0.75  # User-verified skills
WEIGHT_LEARNED = 0.60      # Auto-generated skills
```

---

# SEZIONE 13: SUMMARY OF ALL ISSUES

## Critical Issues (Must Fix)

| ID | Issue | File | Line | Fix |
|----|-------|------|------|-----|
| CRIT-001 | Missing sports keywords ("games", "score", "win", "tonight") | `domain_classifier.py` | 886-932 | Add missing keywords |
| CRIT-002 | API key loading without path | `nba_api.py` | 52 | Add absolute path to load_dotenv() |

## High Priority Issues

| ID | Issue | File | Line | Fix |
|----|-------|------|------|-----|
| HIGH-001 | 12 finance_crypto tools missing from hierarchy | `tool_hierarchy.yaml` | - | Add missing tools or update |
| HIGH-002 | 4 geo_weather tools missing | `tool_hierarchy.yaml` | - | Add geocode, timezone, air quality |
| HIGH-003 | 2 web_search tools missing | `tool_hierarchy.yaml` | - | Add duckduckgo_news/images |
| HIGH-004 | 2 Spotify entertainment tools missing | `tool_hierarchy.yaml` | - | Add or update to Last.fm |
| HIGH-005 | NBA tool name mismatch (nba_live_scores vs nba_live_scoreboard) | `tool_hierarchy.yaml` | - | Fix tool name |

## Medium Priority Issues

| ID | Issue | File | Line | Fix |
|----|-------|------|------|-----|
| MED-001 | Generic intent extraction loses specific query patterns | `tool_index.py` | 388-421 | Parse "Use when user asks..." phrases |
| MED-002 | LLM reranking timeout 600s too high | `llama_tool_retriever.py` | 135-167 | Reduce to 60-120s |
| MED-003 | Code duplication (pubmed in medical + science_research) | Multiple | - | Deduplicate |

## Low Priority Issues

| ID | Issue | File | Line | Fix |
|----|-------|------|------|-----|
| LOW-001 | Similarity threshold 0.40 may filter casual queries | `types.py` | 177 | Consider lowering to 0.35 |
| LOW-002 | AviationStack deprecated in travel | `travel/tools/` | - | Remove or warn |
| LOW-003 | No retrieval caching | `llama_tool_retriever.py` | - | Consider adding Redis cache |

---

# SEZIONE 14: RECOMMENDATIONS

## Immediate Fixes (Do First)

1. **Add missing sports keywords** to `domain_classifier.py`:
```python
"sports_nba": [
    # ... existing ...
    # MISSING: Generic sports query terms
    "games", "game",
    "score", "scores", "scoring",
    "win", "winning", "winner", "won",
    "tonight", "today", "schedule",
    "play", "playing", "player",
]
```

2. **Fix API key loading** in `nba_api.py`:
```python
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
load_dotenv(_BACKEND_ROOT / ".env")
```

## High Priority

3. **Sync tool_hierarchy.yaml** with actual implementations:
   - Add all 17 NBA tools with proper hierarchy
   - Add missing finance_crypto tools
   - Add missing geo_weather tools
   - Fix NBA tool name mismatch

4. **Update unified_intent_analyzer.py** with same keywords

## Medium Priority

5. **Improve intent extraction** to parse "Use when user asks..." patterns

6. **Reduce LLM reranking timeout** from 600s to 120s

## Optional

7. Consider adding retrieval caching layer
8. Add configurable similarity thresholds per domain
9. Implement tool suggestion for misspelled domain names

---

# APPENDICE A: File Structure

```
backend/src/me4brain/
├── engine/
│   ├── core.py                    # ToolCallingEngine
│   ├── catalog.py                 # ToolCatalog
│   ├── executor.py                # ParallelExecutor
│   ├── synthesizer.py             # ResponseSynthesizer
│   └── hybrid_router/
│       ├── router.py              # HybridToolRouter
│       ├── domain_classifier.py   # DomainClassifier
│       ├── llama_tool_retriever.py # LlamaIndexToolRetriever
│       ├── tool_retriever.py      # In-memory ToolRetriever
│       ├── tool_index.py          # ToolIndexManager
│       └── constants.py           # Collection names, thresholds
├── core/
│   └── plugin_registry.py         # PluginRegistry
├── config/
│   └── tool_hierarchy.yaml        # Tool domain hierarchy
├── domains/
│   ├── sports_nba/
│   │   ├── handler.py             # SportsNbaHandler
│   │   └── tools/
│   │       ├── __init__.py        # Exports
│   │       ├── nba_api.py         # 17 NBA tools
│   │       └── betting_analyzer.py
│   ├── finance_crypto/
│   ├── travel/
│   ├── geo_weather/
│   ├── web_search/
│   ├── medical/
│   ├── entertainment/
│   └── ... (other domains)
└── embeddings/
    └── bge_m3.py                  # BGE-M3 embedding service
```

---

# APPENDICE B: Query Flow Decision Tree

```
Query received
    │
    ├─► ThreatLevel.DANGEROUS? ──► BLOCK
    │
    ├─► unified_intent_analyzer → CONVERSATIONAL? ──► Direct LLM response
    │
    └─► HybridToolRouter.route()
            │
            ├─► ContextRewriter.rewrite()
            │
            ├─► DomainClassifier.classify_with_fallback()
            │       ├─► LLM classify (3 retries, 30s timeout)
            │       │       └─► success? ──► return domains
            │       └─► _fallback_classification()
            │               └─► keywords match? ──► return domains
            │               └─► no match? ──► add ["web_search"]
            │
            ├─► QueryDecomposer (if multi-intent)
            │
            └─► ToolRetriever.retrieve()
                    │
                    ├─► LlamaIndexToolRetriever (QDRANT)
                    │       ├─► VectorIndexRetriever (domain filtered)
                    │       ├─► LLMRerank (if enabled)
                    │       └─► _fit_to_payload_limit()
                    │
                    └─► ToolRetriever (in-memory fallback)
                            └─► cosine similarity + threshold
```

---

# APPENDICE C: Constants Reference

| Constant | Value | Location |
|----------|-------|----------|
| CAPABILITIES_COLLECTION | "me4brain_capabilities" | constants.py |
| EMBEDDING_DIM | 1024 | constants.py |
| MIN_SIMILARITY_SCORE | 0.48 | constants.py |
| DEFAULT_COARSE_TOP_K | 30 | constants.py |
| MAX_PAYLOAD_BYTES | 100,000 | constants.py |
| WEIGHT_STATIC | 0.95 | llama_tool_retriever.py |
| WEIGHT_CRYSTALLIZED | 0.75 | llama_tool_retriever.py |
| WEIGHT_LEARNED | 0.60 | llama_tool_retriever.py |

---

**FINE REPORT**