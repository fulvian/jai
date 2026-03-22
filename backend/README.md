# Me4BrAIn Core

**Piattaforma Universale di Memoria Agentica API-First**

> Sistema cognitivo che fornisce memoria a lungo termine, ragionamento su grafi di conoscenza e gestione dello stato per applicazioni AI.

## 🚀 Quick Start

### Prerequisiti

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) - Package manager
- Docker & Docker Compose
- macOS con Apple Silicon (M1/M2/M3) consigliato
- **Opzionale**: [LM Studio](https://lmstudio.ai/) per modelli LLM locali

### Setup

```bash
# 1. Clone e accedi al progetto
cd me4brain

# 2. Copia configurazione
cp .env.example .env
# Modifica .env con le tue API keys

# 3. Avvia tutto
./scripts/start.sh
```

> [!IMPORTANT]
> **Me4BrAIn è solo il backend API.** Per l'interfaccia utente, devi avviare anche **PersAn** (gateway + frontend):
> ```bash
> bash ~/persan/scripts/start.sh
> ```
> Le sessioni chat sono persistite in **Redis** tramite il gateway PersAn. Se riavvii Me4BrAIn senza riavviare PersAn, le sessioni risulteranno invisibili nel frontend.

### Verifica

```bash
# Health check
curl http://localhost:8089/health

# Docs API (solo in debug mode)
open http://localhost:8089/docs
```

> [!NOTE]
> **Porta 8089**: Il servizio me4brain-api è esposto sulla porta **8089** (non 8000). Internamente il container usa la porta 8000, ma è mappata a 8089 sul host.

### Local LLM (LM Studio)

Per usare un modello LLM locale invece dei servizi cloud:

1. **Installa e configura LM Studio**:
   - Scarica da [lmstudio.ai](https://lmstudio.ai/)
   - Carica un modello (es. `qwen3.5-4b-mlx`)
   - Avvia il server locale sulla porta 1234

2. **Configura `.env`**:
   ```bash
   # Abilita modalità locale
   USE_LOCAL_TOOL_CALLING=true

   # LM Studio configuration
   OLLAMA_BASE_URL=http://localhost:1234/v1
   OLLAMA_MODEL=qwen3.5-4b-mlx  # Model alias da LM Studio

   # Fallback cloud (opzionale)
   LLM_FALLBACK_MODEL=mistralai/mistral-large-3-675b-instruct-2512
   ```

3. **Modelli supportati**:
   - Qualsiasi modello caricato in LM Studio
   - Testati: `qwen3.5-4b-mlx`, `qwen3.5-9b-mlx`
    - Nota: Modelli più piccoli possono essere lenti per query complesse

4. **Architettura**:
   ```
   Query → Local LLM (Intent/Routing) → Tool Execution → Local LLM (Synthesis) → Response
                                    ↓
                          Fallback → NanoGPT (Mistral Large)
   ```

### LLM Timeout Configuration (Development Phase)

Per garantire che le query lunghe completino con successo anche con modelli LLM lenti (es. Ollama qwen3.5:4b), i timeout sono configurati con margini generosi:

| Fase | Timeout | Note |
|------|---------|------|
| Domain Classification | **180s** | Classificazione dominio (6x development margin) |
| Query Decomposition | **240s** | Scomposizione query in sub-query (4x development margin) |
| Tool Reranking | **180s** | Riordinamento strumenti per relevance (4x development margin) |
| Graph Hints Retrieval | **120s** | Recupero hint da knowledge graph (4x development margin) |
| Result Summarization | **120s** | Sintesi risultati per tool (4x development margin) |
| Response Synthesis | **300s** | Sintesi finale multi-fonte (2.5x development margin) |

**Nota di Deployment**: In produzione con LLM cloud veloci (Mistral, GPT-4), questi timeout possono essere ridotti. I valori attuali sono ottimizzati per Ollama locale che impiega 30-120 secondi per query complesse.

### Query Decomposition (v0.20.1)

Il sistema decompone query complesse in sub-query specifiche per dominio, migliorando l'accuracy e la completezza delle risposte.

**Esempio - Query NBA**:
```
Input: "Verifica le partite NBA per questa sera, con stats, infortuni, quote scommesse..."

Output: 7 sub-query
  ✅ "Recupera partite NBA in programma" → sports_nba (nba_games_data)
  ✅ "Recupera statistiche squadre NBA" → sports_nba (nba_team_stats)
  ✅ "Recupera roster e formazioni" → sports_nba (nba_roster_injuries)
  ✅ "Recupera ultimi 3 scontri diretti" → sports_nba (nba_head_to_head)
  ✅ "Recupera statistiche giocatori" → sports_nba (nba_player_stats)
  ⚠️ "Recupera quote scommesse" → web_search (betting_odds_data)
  ⚠️ "Crea proposta scommessa multipla" → web_search (betting_proposal_create)
```

**Note**: 
- JSON parsing normalizza output multi-linea da LLM (v0.20.1 fix)
- Fallback a query originale se decomposizione fallisce
- Blocked intents (synthesis, analysis) filtrati automaticamente

## 🏗️ Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                    API GATEWAY (FastAPI)                    │
│              Port: 8089 | JWT via Keycloak                  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  ORCHESTRATOR (LangGraph)                   │
│         Checkpointing: PostgresSaver (Port: 5489)           │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   LAYER I     │   │   LAYER II      │   │  LAYER III-IV   │
│ Working Memory│   │   Episodic +    │   │   Semantic +    │
│    (Redis)    │   │   Procedural    │   │   Knowledge     │
│  Port: 6389   │   │   (Qdrant)      │   │ (Neo4j)         │
└───────────────┘   └─────────────────┘   └─────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                     LAYER V: BROWSER                        │
│     Stagehand + Playwright | Skill Recording | CDP          │
└─────────────────────────────────────────────────────────────┘
```

## 🧠 Skills System (Voyager Pattern)

Me4BrAIn impara automaticamente dalle esecuzioni tool e cristallizza pattern ricorrenti in **skill riutilizzabili**.

### Come Funziona

```
Query → Tool Execution → Trace Recording → Crystallization → Skill Saved
```

| Step | Componente               | Azione                           |
| ---- | ------------------------ | -------------------------------- |
| 1    | `ExecutionMonitor`       | Traccia tool chiamati            |
| 2    | `Crystallizer`           | Genera skill candidate           |
| 3    | `SkillSecurityValidator` | Verifica pattern pericolosi      |
| 4    | `SkillApprovalManager`   | Auto-approve SAFE, queue CONFIRM |
| 5    | `persistence`            | Salva SKILL.md su disco          |

### Risk Levels

| Livello   | Azione        | Esempio Tool                 |
| --------- | ------------- | ---------------------------- |
| 🟢 SAFE    | Auto-save     | search, weather, stock_price |
| 🟡 NOTIFY  | Log only      | file_write, create_doc       |
| 🔴 CONFIRM | HITL required | delete, send_email           |
| ⛔ DENY    | Bloccato      | rm -rf, sudo, eval           |

### API Skills

```bash
# Lista skill in attesa
GET /v1/skills/pending

# Approva skill
POST /v1/skills/pending/{id}/approve

# Rifiuta skill
POST /v1/skills/pending/{id}/reject

# Statistiche
GET /v1/skills/approval-stats
```

### Directory Skills

```
~/.me4brain/skills/crystallized/
└── {skill_id}/
    └── SKILL.md
```

## 🔒 Session Isolation (SSE Streaming)

Me4BrAIn implementa isolamento robusto delle sessioni per il flusso SSE (Server-Sent Events) per garantire che il streaming di pensiero di una sessione non collassi in altre sessioni concorrenti.

### Implementazione

- **Session Context Manager**: Utilizza `session_context()` per propagare il `session_id` attraverso TUTTI i task asincroni
- **Logging**: Ogni evento SSE include il `session_id` per verificare l'isolamento nei log
- **Concurrency**: Supporta 20+ sessioni concorrenti con isolamento garantito

### Verifica

```bash
# Apri 3 tab del browser e invia query concorrenti
# Ogni tab deve mostrare SOLO il suo streaming, non quello delle altre sessioni

# Verifica nei log
docker logs me4brain-api | grep session_id
```

## 🎯 Unified Intent Analysis

Me4BrAIn utilizza **UnifiedIntentAnalyzer** per classificare intelligentemente le query come conversazionali o richiedenti strumenti, eliminando i pattern hardcoded e abilitando il routing scalabile su tutti i domini.

### Caratteristiche

- **Classificazione basata su LLM**: Sostituisce i pattern regex con intelligenza LLM
- **Supporto multi-dominio**: Identifica automaticamente i domini rilevanti (meteo, finanza, ricerca, ecc.)
- **Valutazione della complessità**: Classifica le query come semplici, moderate o complesse
- **Punteggi di confidenza**: Fornisce un punteggio di certezza (0.0-1.0) per ogni classificazione
- **Gestione degli errori**: Fallback sicuro in caso di errori LLM

### Utilizzo Rapido

```python
from me4brain.engine.unified_intent_analyzer import UnifiedIntentAnalyzer, IntentType
from me4brain.llm.provider_factory import get_reasoning_client
from me4brain.llm.config import get_llm_config

# Inizializza
llm_client = get_reasoning_client()
config = get_llm_config()
analyzer = UnifiedIntentAnalyzer(llm_client, config)

# Analizza una query
analysis = await analyzer.analyze("Che tempo fa a Roma?")

# Accedi ai risultati
print(f"Intent: {analysis.intent}")  # IntentType.TOOL_REQUIRED
print(f"Domains: {analysis.domains}")  # ["geo_weather"]
print(f"Confidence: {analysis.confidence}")  # 0.95
```

### Con ToolCallingEngine

L'analyzer è integrato automaticamente:

```python
engine = await ToolCallingEngine.create()
response = await engine.run("Che tempo fa a Roma?")
# L'analisi dell'intent avviene automaticamente
```

### Documentazione Completa

- [UnifiedIntentAnalyzer Guide](./docs/unified-intent-analysis.md)
- [Migration Guide da ConversationalDetector](./docs/MIGRATION_GUIDE.md)
- [API Reference](./docs/api/unified-intent-analyzer.md)

## 📚 Documentazione

- [Blueprint v2.0](docs/architecture/blueprint_me4brain_v2.md) - Architettura completa
- [Implementation Plan](docs/architecture/implementation_plan_v1.md) - Piano di sviluppo
- [Changelog](CHANGELOG.md) - Cronologia versioni
- [Recent Changes](RECENT_CHANGES.md) - Ultime modifiche (2026-03-12)
- [Project Memory](PROJECT_MEMORY.md) - Conoscenza core e decisioni
- [Integrations Guide](docs/INTEGRATIONS.md) - MCP (LM Studio), Google Workspace, Finance

## 🛠️ Sviluppo

```bash
# Sync dipendenze
uv sync

# Installa pre-commit hooks
uv run pre-commit install

# Esegui tests
uv run pytest

# Lint & Format
uv run ruff check --fix .
uv run ruff format .

# Type checking
uv run mypy src/
```

## 📦 Servizi Docker

| Servizio     | Porta     | Descrizione                    |
| ------------ | --------- | ------------------------------ |
| me4brain-api | 8089      | API Gateway (FastAPI)          |
| PostgreSQL   | 5489      | LangGraph state                |
| Redis        | 6389      | Working memory + sessioni chat |
| Qdrant       | 6333/6334 | Vector store                   |
| Neo4j        | 7478/7697 | Graph database                 |
| Keycloak     | 8489      | Authentication                 |

> [!WARNING]
> Redis è condiviso tra Me4BrAIn (working memory) e PersAn (sessioni chat).
> Se i container Docker vengono rimossi con `docker compose down -v`, tutte le sessioni chat andranno perse.

```bash
# Start containers
docker compose -f docker/docker-compose.yml up -d

# Stop containers
docker compose -f docker/docker-compose.yml stop

# View logs
docker compose -f docker/docker-compose.yml logs -f
```

## 📄 License

MIT
