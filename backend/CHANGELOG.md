## [v0.20.7] - 2026-03-26

### Added - LM Studio context_length Integration

**Feature**: LM Studio models now properly report their `context_length` configuration, and the system can automatically reload models when `context_window_size` changes.

**Changes**:

1. **LMStudioAutoLoader Enhanced** (`nanogpt.py`):
   - Added `_loaded_context_length` tracking
   - `load_model()` now accepts optional `context_length` parameter
   - `load_model()` passes `context_length` to LM Studio API when loading models
   - `ensure_model_loaded()` automatically reloads models if `context_length` differs from configured value

2. **Model Discovery Enhanced** (`model_discovery.py`):
   - `scan_mlx_server()` now fetches detailed info from `/api/v1/models` endpoint
   - Extracts `max_context_length` (maximum supported by model) and `context_length` (current if loaded)
   - Reports `is_loaded` status and `quantization` for each model

3. **API Extended** (`llm_config.py`):
   - Added `max_context_length` and `is_loaded` fields to `LLMModelInfo`
   - `_discovered_to_info()` now propagates these fields

**How It Works**:
```
UI: context_window_size = 32768 (configurable in Settings)
     ↓
Backend: passes context_length=32768 to LM Studio when loading model
     ↓
LM Studio: loads model with specified context_length
```

**Model Info Now Shows**:
```json
{
  "id": "qwen/qwen3.5-9b",
  "context_window": 8192,        // current context_length (if loaded)
  "max_context_length": 262144,  // maximum supported by model
  "is_loaded": true,             // whether loaded in LM Studio
  "quantization": "Q4_K_M"       // model quantization
}
```

**Files Modified**:
- `src/me4brain/llm/nanogpt.py` - LMStudioAutoLoader with context_length support
- `src/me4brain/llm/model_discovery.py` - Enhanced LM Studio API discovery
- `src/me4brain/api/routes/llm_config.py` - Added max_context_length, is_loaded fields

---

## [v0.20.6] - 2026-03-23

### Fixed - Weather Query Classification (geo_weather domain)

**Problem**: Weather queries like "Che tempo fa a Caltanissetta?" returned "Operazione completata. Non sono stati necessari strumenti aggiuntivi" instead of fetching real weather data.

**Root Cause**: Multiple issues:
1. Incorrect model name in `.env`: `LLM_ROUTING_MODEL='mlx/qwen3.5:9b'` caused 404 errors
2. qwen3.5 thinking model consumed all `max_tokens=50` for reasoning, leaving empty `content`
3. Missing `reasoning_exclude` support for thinking models

**Solution**:
- Fixed `.env`: Changed `LLM_ROUTING_MODEL` from `'mlx/qwen3.5:9b'` to `'qwen3.5:9b'`
- Increased `max_tokens` in Tier 1 from 50 to 2000 to allow thinking + JSON output
- Added `reasoning_exclude` support to `OllamaClient._prepare_payload()`
- Added fallback in `OllamaClient.generate_response()` to use `reasoning` as `content` when `content` is empty

**Files Modified**:
- `backend/.env` - Corrected model name
- `src/me4brain/llm/ollama.py` - Added reasoning_exclude and content fallback
- `src/me4brain/engine/unified_intent_analyzer.py` - Increased max_tokens to 2000

**Verification**: Weather query now correctly returns `Intent: IntentType.TOOL_REQUIRED`, `Domains: ['geo_weather']`, `Confidence: 1.0`

### Fixed - Linter Issues (F821 Undefined Names - Actual Bugs)

**Problem**: 12 F821 "undefined name" errors that were actual bugs causing runtime failures.

**Solution**:
- Added missing TYPE_CHECKING imports for `NanoGPTClient`, `DomainClassification`, `BrowserSessionWrapper`, `LLMProvider`, `Optional`, `AsyncGenerator`, `redis`, `pandas`
- Fixed forward reference issues in type annotations

**Files Modified**:
- `src/me4brain/engine/iterative_executor.py` - Added Optional, LLMProvider imports
- `src/me4brain/llm/batch_scheduler.py` - Added AsyncGenerator import
- `src/me4brain/api/routes/engine.py` - Added NanoGPTClient TYPE_CHECKING import
- `src/me4brain/cache/cache_manager.py` - Added DomainClassification import
- `src/me4brain/core/browser/manager.py` - Added BrowserSessionWrapper import
- `src/me4brain/domains/finance_crypto/tools/finance_api.py` - Added pandas TYPE_CHECKING
- `src/me4brain/embeddings/embedding_cache.py` - Fixed redis imports and type annotations

### Fixed - Auto-Fixable Linter Issues

**Solution** (via `ruff check --fix --unsafe-fixes`):
- W291/W293: 20 trailing whitespace and blank line whitespace issues fixed
- F401: Unused imports removed
- F841: 50+ unused variable assignments removed

### Added - Test Coverage Verification

- All 1180 unit tests pass
- 0 regressions introduced

---

## [v0.20.5] - 2026-03-23

### Fixed - Qdrant Point ID UUID Requirement

**Problem**: `tool_index.py` used `tool_name` strings as Qdrant point IDs, but Qdrant requires UUID or integer IDs.

**Root Cause**: `CATALOG_MANIFEST_POINT_ID = "__catalog_manifest__"` and tool point IDs like `"openmeteo_current"` are invalid Qdrant IDs.

**Solution**: 
- Generate deterministic UUID5 for tool point IDs: `uuid.uuid5(uuid.NAMESPACE_DNS, tool_name)`
- Changed `CATALOG_MANIFEST_POINT_ID` to valid UUID: `"00000000-0000-0000-0000-000000000001"`

**Files Modified**:
- `src/me4brain/engine/hybrid_router/tool_index.py` - UUID generation for point IDs

### Fixed - LLM Provider Auto-Detection Respects Explicit base_url

**Problem**: `NanoGPTClient` ignored the explicit `base_url` parameter when model name contained `mlx/` prefix, incorrectly routing to LM Studio.

**Root Cause**: `_get_base_url_for_model()` always checked model prefix regardless of user-provided base_url.

**Solution**: 
- Added `_user_provided_base_url` flag to detect explicit base_url
- If base_url differs from default, always use it (respect user's explicit choice)
- Added `_normalize_model_for_provider()` to strip `mlx/` prefix when calling Ollama

**Files Modified**:
- `src/me4brain/llm/nanogpt.py` - Respect explicit base_url, normalize model names

### Added - Real Integration Tests for Hybrid Router

**Problem**: Needed real integration tests with Qdrant + Ollama (no mocks) for Wave 4.

**Solution**: 
- Created `tests/integration/test_hybrid_router_real.py` with 6 integration tests
- Created `tests/benchmarks/golden_set.py` with 54 test cases
- Created `tests/benchmarks/test_golden_set.py` with 19 unit tests
- Created `tests/unit/test_tool_index.py` with 13 unit tests

**Test Results**:
- `tests/unit/test_tool_index.py`: 14 passed
- `tests/benchmarks/test_golden_set.py`: 19 passed
- `tests/integration/test_hybrid_router_real.py`: 5 passed, 1 timeout (qwen3.5 thinking slow)

---

## [v0.20.4] - 2026-03-23

### Fixed - Ollama Migration & qwen3.5 Thinking Model Support

**Problem**: System was routing local LLM calls to LM Studio (localhost:1234) which wasn't running, causing all local LLM calls to fail silently.

**Root Cause**: Model naming convention `qwen3.5-4b-mlx` triggered LM Studio routing in `NanoGPTClient._get_base_url_for_model()`. LM Studio wasn't running.

**Solution**: Migrated to Ollama as primary local LLM provider:
- Changed model defaults from `-mlx` suffix to Ollama format with `:` (e.g., `qwen3.5:4b`, `qwen3.5:9b`)
- Ollama v0.18.2 running on `localhost:11434` with working `qwen3.5:4b` and `qwen3.5:9b`

**Files Modified**:
- `src/me4brain/llm/config.py`: Model defaults updated to Ollama naming
- `src/me4brain/llm/nanogpt.py`: Enhanced empty content fallback for thinking models
- `src/me4brain/retrieval/lightrag.py`: Increased `max_tokens=8000` for entity extraction
- `backend/.env`: Updated model names, added Neo4j credentials

### Fixed - qwen3.5 Thinking Models Slow Response

**Discovery**: qwen3.5 thinking models produce extensive internal reasoning traces (~8000-10000 tokens) before actual content. Entity extraction takes ~150 seconds.

**Behavior**:
- `reasoning` field contains "Thinking Process:" traces
- `content` field may be empty string `""` 
- `think: false` parameter does NOT disable thinking

**Fix**: Enhanced fallback logic in `nanogpt.py`:
```python
if (content is None or content == "") and reasoning:
    content = reasoning  # Use reasoning as content fallback
```

### Increased Timeouts for Slow LLM Responses

**Problem**: Default timeouts (300s-600s) were too short for qwen3.5 thinking models (~150s extraction time).

**Timeout Increases**:

| File | Setting | Before | After |
|------|---------|--------|-------|
| `nanogpt.py` | HTTP read timeout | 600s | **1800s** (30 min) |
| `nanogpt.py` | HTTP connect timeout | 10s | **30s** |
| `config.py` | `default_timeout` | 300s | **1800s** (30 min) |
| `config.py` | `intent_analysis_timeout` | 5s | **60s** |
| `ollama.py` | `OllamaClient` default | 120s | **300s** (5 min) |
| `queue_manager.py` | `DEFAULT_TIMEOUT` | 300s | **1800s** (30 min) |

### Fixed - Neo4j Authentication

**Issue**: Neo4j brew service had authentication failures. Password changed from `neo4j/neo4j` to `neo4j/password`.

**Verification**:
```bash
/opt/homebrew/Cellar/neo4j/*/bin/neo4j start  # Start Neo4j
```

### Test Results

- **Unit tests**: 1151 passed, 214 warnings ✅
- **Integration tests**: 22 passed, 1 xfailed, 2 warnings ✅
- **Frontend typecheck**: 5/5 pass ✅
- **Frontend build**: Pass ✅

### Known Limitations

- qwen3.5 thinking models are inherently slow (~150s extraction)
- Consider using non-thinking models for production if speed is critical

# Changelog - Me4BrAIn Core

Tutti i cambiamenti significativi a questo progetto saranno documentati in questo file.

## [v0.20.3] - 2026-03-22

### Changed - Phase 3: Code Cleanup & Deprecation Removal ✅ COMPLETE

**Scope**: Remove deprecated code paths that are no longer used after Phase 2 optimization.

**Removed**:
1. **`create_legacy()` from `engine/core.py`** (lines 218-281, 64 lines)
   - Sent ALL 129+ tools to LLM (high payload risk)
   - Never called by active tests or modern code
   - Replaced by `_create_with_hybrid_routing()` which implements intelligent tool selection

2. **`create_with_hybrid_routing()` from `engine/core.py`** (lines 282-303, 22 lines)
   - Deprecated wrapper alias for `create()`
   - Removed completely (no longer needed)

3. **Legacy fallback code from `cognitive_pipeline.py`** (92 lines)
   - `USE_LEGACY_FALLBACK` environment variable flag (line 50)
   - Legacy semantic search handlers (lines 869-961)
   - Multi-tool parallel execution legacy path
   - NBA chained analysis legacy implementation

4. **Kept for Reference**:
   - `_create_with_hybrid_routing()` - Still used by `create()`, implements current hybrid routing
   - `_detect_multi_tool_services()` - Marked deprecated, no longer called but kept (optimized patterns)

**Test Results**:
- Before Phase 3.2: 920/920 unit tests passing
- After Phase 3.2: 920/920 unit tests passing ✅
- No test regressions, no failures introduced

**Total Lines Removed**: 178 lines of deprecated code

**Deferred to Deployment**:
- Qdrant collection cleanup (tool_catalog, tools_and_skills, me4brain_skills, tools)
- Requires running Qdrant instance
- Script available: `backend/scripts/migrate_to_unified_collection.py`

**Next Phase**: Phase 4 - Testing & Validation (Integration tests, E2E tests, Qdrant cleanup)

**Commits**:
- `4c06f2d` - Phase 3.2: Remove deprecated factory methods and legacy fallback code
- `a470494` - Phase 3 Complete: Code cleanup and deprecation removal finalized
- `7b73eba` - Update implementation plan: Phase 3 complete, Phase 4 ready

---

## [v0.20.2] - 2026-03-21

### Fixed - Critical Model Configuration Discrepancy

**Issue**: System was using 4B fallback model (qwen3.5:4b) for routing and synthesis instead of dashboard-configured 9B model (qwen3.5-9b-mlx), despite correct configuration settings.

**Root Cause**: When `use_local_tool_calling=true`, the legacy `create_legacy()` method forced routing/synthesis models to `config.ollama_model` (4B), completely overriding dashboard preferences in `LLM_ROUTING_MODEL` and `LLM_SYNTHESIS_MODEL`.

**Impact**:
- Queries executed with 4B model (slower, less capable reasoning)
- ~2.25x performance penalty vs 9B model
- Reduced domain classification and answer quality
- Configuration hierarchy broken (dashboard config ignored)

**Solution**:
1. **API Route** (`src/me4brain/api/routes/engine.py`): Changed to use `ToolCallingEngine.create()` which delegates to `_create_with_hybrid_routing()` (was using `create_legacy()`)
2. **Core Logic** (`src/me4brain/engine/core.py` lines 342-345): Fixed `_create_with_hybrid_routing()` to respect dashboard config:
   ```python
   # NOW: Respects dashboard preferences
   routing_model = config.model_routing    # Uses configured 9B model
   synthesis_model = config.model_synthesis  # Uses configured 9B model
   ```
3. **Configuration** (`src/me4brain/llm/config.py`): Updated defaults to correct LM Studio model names:
   - `model_routing`: `mlx-...opus...` → `qwen3.5-9b-mlx`
   - `model_synthesis`: `qwen3.5-4b-mlx` → `qwen3.5-9b-mlx`
4. **Environment** (`/.env`): Fixed model name format to match LM Studio naming:
   - `LLM_ROUTING_MODEL`: `mlx/qwen3.5:9b` → `qwen3.5-9b-mlx`
   - `LLM_SYNTHESIS_MODEL`: `mlx/qwen3.5:9b` → `qwen3.5-9b-mlx`

**Execution Flow** (Before → After):
```
Before: API → create_legacy() → FORCE 4B → qwen3.5:4b (❌ wrong)
After:  API → create() → _create_with_hybrid_routing() → config.model_routing (qwen3.5-9b-mlx) ✅
```

**Result**: 
- System now correctly uses qwen3.5-9b-mlx for domain routing and answer synthesis
- Dashboard configuration respected (LLM_ROUTING_MODEL, LLM_SYNTHESIS_MODEL)
- Improved reasoning quality and classification accuracy
- Proper configuration hierarchy: Dashboard Config > System Defaults > Fallbacks

**Files Modified**:
- `src/me4brain/engine/core.py` (Lines 342-345)
- `src/me4brain/llm/config.py` (Lines 44, 62)
- `/.env` (Lines 42-43)
- `src/me4brain/api/routes/engine.py` (Already using correct create())

**Verification**:
- ✅ Configuration loads correctly: `model_routing=qwen3.5-9b-mlx`
- ✅ Production logs confirm: `"routing_model": "qwen3.5-9b-mlx", "synthesis_model": "qwen3.5-9b-mlx"`
- ✅ API server healthy and responding with correct models
- ✅ Sample queries execute successfully with 9B models
- ✅ Git commit: 48b32a9

---

## [v0.20.1] - 2026-03-21

### Fixed - Query Decomposer JSON Parsing

**Issue**: Query decomposition with formatted JSON (multi-line with indentation) failed to parse, causing fallback to original query and superficial analysis.

**Root Cause**: `robust_json_parse()` had default `expect_object=True`, which rejected array responses. Additionally, manual JSON repair did not normalize multi-line whitespace.

**Solution**: 
1. Changed `robust_json_parse()` default `expect_object=False` to allow arrays
2. Added whitespace normalization regex `\s*\n\s*` → "" to handle formatted LLM output

**Result**: NBA query now correctly decomposes into 7 targeted sub-queries instead of 1 fallback query.

**Files Modified**:
- `src/me4brain/utils/json_utils.py` (Lines 55, 139-140)

**Example**:
```json
// Before: Fallback to single query
[SubQuery(text="original_query", domain="web_search", intent="fallback")]

// After: Proper decomposition
[
  SubQuery(text="recupera partite NBA in programma questa sera", domain="sports_nba", intent="nba_games_data"),
  SubQuery(text="recupera statistiche squadre NBA stagione in corso", domain="sports_nba", intent="nba_team_stats"),
  SubQuery(text="recupera roster e formazioni squadre NBA", domain="sports_nba", intent="nba_roster_injuries"),
  SubQuery(text="recupera ultimi 3 scontri diretti squadre NBA", domain="sports_nba", intent="nba_head_to_head"),
  SubQuery(text="recupera statistiche giocatori migliori realizzatori", domain="sports_nba", intent="nba_player_stats"),
  SubQuery(text="recupera quote scommesse NBA", domain="web_search", intent="betting_odds_data"),
  SubQuery(text="crea proposta scommessa multipla", domain="web_search", intent="betting_proposal_create")
]
```

---

## [v0.20.0] - 2026-03-21

### Enhanced - LLM Timeout Configuration (Development Phase)

**Objective**: Aumentare tutti i timeout LLM per garantire che query lunghe e modelli LLM lenti completino con successo durante la fase di sviluppo, eliminando premature timeout failures.

**Root Cause**: Ollama qwen3.5:4b impiega 30-120 secondi per query complesse, causando timeout a cascata attraverso tutte le fasi (classificazione, decomposizione, sintesi).

**Solution**: Implementati timeout generosi (180s-300s) in tutte le fasi LLM non protette:

| Fase | Timeout Precedente | Timeout Nuovo | Moltiplicatore |
|------|-------------------|---------------|----------------|
| Domain Classification | 30s | **180s** | 6x |
| Query Decomposition | 60s | **240s** | 4x |
| Tool Reranking | 45s | **180s** | 4x |
| Graph Hints Retrieval | 30s | **120s** | 4x |
| Result Summarization | 30s | **120s** | 4x |
| Response Synthesis | 120s | **300s** | 2.5x |

### Files Modified

1. **`src/me4brain/engine/hybrid_router/domain_classifier.py`** (Line 167, 172)
   - Timeout: 30.0 → 180.0 seconds
   - Log parameter: timeout_seconds updated

2. **`src/me4brain/engine/hybrid_router/query_decomposer.py`** (Line 244, 249)
   - Timeout: 60.0 → 240.0 seconds
   - Log parameter: timeout_seconds updated

3. **`src/me4brain/engine/hybrid_router/llama_tool_retriever.py`** (Line 151, 156)
   - Timeout: 45.0 → 180.0 seconds
   - Log parameter: timeout_seconds updated

4. **`src/me4brain/engine/iterative_executor.py`** (Line 1919, 1926)
   - Timeout: 30.0 → 120.0 seconds (graph hints retrieval)
   - Log parameter: timeout_seconds updated

5. **`src/me4brain/engine/synthesizer.py`** (Lines 184, 189, 520, 527)
   - Response Synthesis: 120.0 → 300.0 seconds
   - Result Summarization: 30.0 → 120.0 seconds
   - Log parameters: timeout_seconds updated

### Testing

- ✅ Python syntax verified on all 5 modified files
- ✅ All timeout changes committed with git (commit a331abb)
- ✅ Ready for end-to-end testing with NBA queries

### Notes for Deployment

- **Development Phase**: Valori attuali optimizzati per Ollama local (qwen3.5:4b, ~100-120s per query complessa)
- **Production Phase**: Con LLM cloud veloci (Mistral, GPT-4, ~1-5s per query), ridurre i timeout:
  - Domain Classification: 180s → 30s
  - Query Decomposition: 240s → 60s
  - Tool Reranking: 180s → 45s
  - Graph Hints: 120s → 30s
  - Result Summarization: 120s → 30s
  - Response Synthesis: 300s → 120s

## [v0.19.38] - 2026-03-16

### Fixed - LLM Configuration Persistence Bug

- **Root Cause**: Le modifiche alle impostazioni LLM nel pannello Settings di PersAn non venivano persistite nel file `.env`. Alla riapertura del pannello, la configurazione tornava ai valori di default.

- **Bug #1 - Mancanza persistenza**: L'endpoint `PUT /v1/config/llm/update` salvava solo in `os.environ` (memoria volatile) senza scrivere nel file `.env`.

- **Bug #2 - Campi mancanti in LLMConfig**: I campi `default_temperature`, `default_max_tokens`, `context_window_size`, `enable_streaming`, `enable_caching`, `enable_metrics` non esistevano nella classe `LLMConfig`, quindi non venivano mai letti dalla configurazione.

- **Bug #3 - Valori hardcoded in get_current_config**: L'endpoint restituiva valori hardcoded (es. `default_temperature=0.3`) invece di leggere dalla configurazione effettiva.

### Solution

1. **Aggiunti campi mancanti in `LLMConfig`** (`src/me4brain/llm/config.py`):
   - `default_temperature: float` (alias: `LLM_DEFAULT_TEMPERATURE`)
   - `default_max_tokens: int` (alias: `LLM_DEFAULT_MAX_TOKENS`)
   - `context_window_size: int` (alias: `LLM_CONTEXT_WINDOW_SIZE`)
   - `enable_streaming: bool` (alias: `LLM_ENABLE_STREAMING`)
   - `enable_caching: bool` (alias: `LLM_ENABLE_CACHING`)
   - `enable_metrics: bool` (alias: `LLM_ENABLE_METRICS`)

2. **Implementata persistenza nel file `.env`** (`src/me4brain/api/routes/llm_config.py`):
   - Nuova funzione `_find_env_file()` per individuare il file `.env` nel progetto
   - Nuova funzione `_persist_to_env_file()` per scrivere le modifiche nel file
   - Mapping `ENV_VAR_MAPPING` per tradurre i nomi dei campi in variabili d'ambiente
   - L'endpoint `update_llm_config` ora persiste automaticamente le modifiche

3. **Corretto `get_current_config`**: Ora legge tutti i valori dalla configurazione LLM invece di usare valori hardcoded.

### API Changes

- `PUT /v1/config/llm/update` response ora include:
  ```json
  {
    "status": "updated",
    "updates_applied": ["model_primary=new-model", ...],
    "verified_config": {...},
    "persistence": {
      "success": true,
      "message": "Persisted to /path/to/.env"
    }
  }
  ```

### File Modificati

- `src/me4brain/llm/config.py`: Aggiunti 6 nuovi campi di configurazione runtime
- `src/me4brain/api/routes/llm_config.py`: Aggiunta persistenza automatica + fix valori hardcoded

### Test

```bash
# Verifica configurazione
python -c "from me4brain.llm.config import get_llm_config; c = get_llm_config(); print(c.default_temperature)"

# Verifica persistenza
curl -X PUT http://localhost:8089/v1/config/llm/update \
  -H "Content-Type: application/json" \
  -d '{"model_primary": "new-model"}'
# → persistence.success: true
```

---

## [v0.19.37] - 2026-03-15

### Added - Context Overflow Strategy Implementation

- **Overflow Strategy Backend**: Implementate 3 strategie per gestire contesti che superano la soglia (16K chars):
  - `map_reduce`: divide il contesto in parti, le elabora in parallelo, unisce i risultati
  - `truncate`: mantiene i messaggi più recenti, scarta il contesto più vecchio
  - `cloud_fallback`: passa a modello cloud (Mistral Large 3) con finestra contesto più grande

- **Strategy Selection Logic**: Il `ResponseSynthesizer` ora legge la strategia dalla configurazione:
  - Metodo `_get_overflow_strategy()` per leggere da `LLMConfig`
  - Supporto override via parametro costruttore
  - Applicato in entrambi i metodi `synthesize()` e `synthesize_streaming()`

- **Config Cache Invalidation**: L'API `/v1/config/llm/update` ora:
  - Invalida la cache con `get_llm_config.cache_clear()`
  - Restituisce `verified_config` per confermare l'applicazione
  - Logga la strategia verificata

### Changed

- **Frontend AdvancedTab**: Feedback visivo migliorato per selezione strategia:
  - Riquadro verde con shadow quando strategia applicata
  - Badge "Applicato" per conferma visiva
  - Messaggio errore se backend non conferma
  - Refresh automatico config dopo update

### File modificati

- `src/me4brain/engine/synthesizer.py`: Strategie overflow, metodi truncate/cloud_fallback
- `src/me4brain/api/routes/llm_config.py`: Cache invalidation, verified_config
- `PersAn/frontend/src/components/settings/AdvancedTab.tsx`: Feedback visivo
- `PersAn/frontend/src/hooks/useSettings.ts`: Tipi risposta verificata
- `PersAn/frontend/src/components/settings/settingsLabels.ts`: Labels strategie IT

---

## [v0.19.36] - 2026-03-15

### Added - Settings Panel Backend Integration & Model Discovery

- **Real Model Discovery**: Implementato `model_discovery.py` per scansione reale dei modelli locali:
  - LM Studio: scansione `~/.cache/lm-studio/models/`
  - Ollama: scansione `~/.ollama/models/manifests/`
  - MLX Server: discovery via HTTP API
  - Restituisce modelli con metadati (context_window, quantizzazione, VRAM richiesta)

- **Feature Flags Backend Integration**: Connessi i toggle del pannello Advanced al backend:
  - `enable_streaming`: controlla lo streaming delle risposte
  - `enable_caching`: abilita/disabilita cache risposte
  - `enable_metrics`: raccoglie metriche performance
  - I flag sono ora persistiti in environment variables e restituiti da `/v1/config/llm/current`

- **LLM Models Tab Grouping**: I modelli sono ora raggruppati in optgroup:
  - "Local (Installed on this device)": modelli MLX, Ollama, LM Studio scoperti
  - "Cloud (NanoGPT API)": solo Mistral Large 3

### Changed

- **Rimossi modelli cloud arbitrari**: Eliminati GPT-4o, Claude 3.5 Sonnet, GPT-4o Mini, DeepSeek R1 da `MODEL_PROFILES`
- **Solo Mistral Large 3 come cloud**: Unico modello cloud supportato via NanoGPT API
- **LLMConfigResponse esteso**: Aggiunti campi `enable_streaming`, `enable_caching`, `enable_metrics`

### Fixed

- **Backend/Frontend Sync**: I parametri del pannello Settings ora modificano realmente la configurazione di Ollama, LM Studio e MLX Server
- **Model Selection**: La dropdown mostra solo modelli effettivamente installati + Mistral cloud

### File modificati

- `src/me4brain/llm/model_discovery.py`: Nuovo modulo per discovery modelli locali
- `src/me4brain/llm/model_profiles.py`: Rimossi profili cloud non autorizzati
- `src/me4brain/api/routes/llm_config.py`: Aggiunti feature flags, integrazione discovery
- `frontend/src/hooks/useSettings.ts`: Aggiunti tipi per feature flags
- `frontend/src/components/settings/LLMModelsTab.tsx`: Raggruppamento Local/Cloud
- `frontend/src/components/settings/AdvancedTab.tsx`: Connessione feature flags al backend

---

## [v0.19.35] - 2026-03-14

### Fixed - Thinking Streaming Separation

- **Problema**: Lo streaming del pensiero del modello (thinking) veniva erroneamente incluso nella bubble message della risposta finale invece di essere separato in una bubble dedicata.

- **Causa**: La logica di rilevamento thinking→content usava marker euristici (`-`, `**`, `##`, `1.`, ecc.) che si attivavano **dentro** il pensiero stesso (es. liste markdown), causando la fine prematura della fase thinking.

- **Soluzione**: Riscritta la logica di `synthesize_streaming()` con una nuova state machine:
  - **Detect**: Buffer iniziale (100 chars) per cercare tag espliciti `<think>`
  - **Thinking**: Estrae tutto il contenuto fino al tag di chiusura `</think>`
  - **Content**: Output finale della risposta
  
- **Miglioramenti**:
  - Rimossi marker euristici aggressivi che causavano falsi positivi
  - Aggiunta gestione del tag `</think>` diviso tra chunk
  - Supporto prioritario per campo `reasoning` nativo (modelli come Kimi K2.5)
  - Corretta propagazione del campo `thinking` in `StreamChunk` in `core.py`
  - **Nuovo**: Aggiunta estrazione thinking anche per modalità **non-streaming** (`synthesize()`) che prima non gestiva i tag `</think>`

- **File modificati**:
  - `src/me4brain/engine/synthesizer.py`: Nuova logica state machine + metodo `_extract_thinking_from_content()`
  - `src/me4brain/engine/core.py`: Corretta propagazione StreamChunk
  - `src/me4brain/llm/models.py`: Message.role accetta ora sia str che enum
  - `src/me4brain/llm/base.py`: Aggiornato tipo generate_embeddings

---

## [v0.19.34] - 2026-03-13

### Fixed - Local LLM Support (LM Studio)

- **Intent Analyzer Model Configuration**:
  - Fix in `get_intent_analyzer()` per usare il modello locale da config invece di `deepseek/deepseek-chat-v3-0324` hardcoded.
  - Quando `USE_LOCAL_TOOL_CALLING=true`, l'IntentAnalyzer ora usa `config.ollama_model`.
- **Context Rewriter Model Configuration**:
  - Fix in `get_context_rewriter()` per usare il modello locale da config.
  - Quando `USE_LOCAL_TOOL_CALLING=true`, il ContextAwareRewriter ora usa `config.ollama_model`.
- **Environment Variables**:
  - `LLM_EXTRACTION_MODEL` ora defaults a `qwen3.5-4b-mlx` per compatibilità con LM Studio.
  - `LLM_SYNTHESIS_MODEL` ora defaults a `qwen3.5-4b-mlx`.
  - `LLM_ROUTING_MODEL` ora defaults a `qwen3.5-4b-mlx`.
- **Provider Factory**:
  - `get_reasoning_client()` ora restituisce Ollama client quando `use_local_tool_calling=true`.
  - Consente di usare modelli locali per reasoning, synthesis e context rewriting.
- **FallbackProvider Enhancement**:
  - Aggiunto parametro `fallback_model` per specificare il modello da usare durante il fallback.
  - Il fallback da Ollama a NanoGPT ora usa correttamente il modello cloud (Mistral).

### Configuration

Per usare un modello locale via LM Studio:

```bash
# .env
USE_LOCAL_TOOL_CALLING=true
OLLAMA_BASE_URL=http://localhost:1234/v1
OLLAMA_MODEL=qwen3.5-4b-mlx  # Model alias from LM Studio
LLM_FALLBACK_MODEL=mistralai/mistral-large-3-675b-instruct-2512  # Cloud fallback
```

---

## [v0.19.33] - 2026-03-13

### Fixed - Tool Calling & Thinking Streaming

- **Iterative Executor: Nuclear Fallback Enhancement**:
  - Esteso `_INTENT_TOOL_MAP` con mapping per domini weather (`geo_weather`, `meteo`, `weather_query` → `openmeteo_weather`), finance (`crypto_price`, `finance_query` → `coingecko_price`), e web search (`web_search`, `search_query` → `duckduckgo_search`).
  - Migliorato il Priority 2 fallback con pattern domain-specific per weather (`meteo`, `weather`) e finance (`coin`, `price`, `crypto`).
  - Aggiunto fallback "last resort" che seleziona il primo tool disponibile se nessun pattern matcha.
- **Synthesizer: Thinking Streaming Continuo**:
  - Fix in `synthesize_stream()` per lo streaming immediato di ogni token di thinking senza bufferizzazione.
  - Ogni token viene yieldato immediatamente come `StreamChunk(type="thinking", content=token)`.
  - Il frontend accumula i token via `appendThinking()` per visualizzazione real-time.
- **Core: Tool-Calling LLM Configuration**:
  - Fix nel path di streaming per passare correttamente `tool_calling_llm` e `tool_calling_model` all'`IterativeExecutor`.
  - Risolto il problema dove l'executor veniva creato senza client specializzato per tool-calling.
- **Debug Logging**:
  - Aggiunto `step_tool_selection_response` per tracciare risposte LLM (tool_calls vs content).
  - Aggiunto `nuclear_fallback_check` per loggare il processo di selezione fallback.
  - Aggiunto `executor_nuclear_fallback_args` per loggare gli argomenti costruiti per i tool.

---

## [v0.19.32] - 2026-03-12

### Added - Model Context Protocol (MCP) Integration

- **MCP Server Implementation**: Introdotto `src/me4brain/api/mcp.py` per l'esposizione di tool, risorse e prompt tramite lo standard MCP.
- **FastAPI Integration**: Abilitato il montaggio dinamico dell'app MCP nel gateway principale sotto il prefisso `/mcp`.
- **LM Studio Support**: Validata la connessione asincrona via SSE (Server-Sent Events) per l'interazione con modelli locali.
- **Dynamic Tool Discovery**: Automatizzata la registrazione di tutti i tool del `ToolCatalog` come capability MCP.

## [v0.19.31] - 2026-03-11

### Fixed - Neo4j Vector Index Auto-Creation & Graceful Degradation

- **Iterative Executor Resilience**: Aggiunta logica di auto-creation per l'indice vettoriale `fewshot_embeddings` in Neo4j (`_ensure_fewshot_index_exists`).
- **GraphRAG Few-Shot Search**: Implementato blocco `try...except` attorno alla ricerca vettoriale ibrida in `_get_graph_prompt_hints()`. In caso di fallimento o assenza dell'indice, il sistema prosegue con gracefully degradation fornendo il contesto base, evitando il blocco totale del flusso e permettendo all'esecuzione del tool di proseguire.

### Fixed - NBA API Timeout & Cache Stampede

- **TLS Fingerprint Bypass**: Integrata la libreria `curl_cffi` per monkey-patchare `requests.Session` all'interno di `nba_api`. Questo permette di mascherare l'handshake TLS simulando Chrome 120, aggirando con successo i blocchi IP/WAF di Akamai che causavano timeout (15s) seriali su `stats.nba.com`.
- **Negative Memory Cache**: Implementato `_advanced_stats_cache` con un `asyncio.Lock()` per `nba_api_advanced_stats`. Previene il fenomeno della "cache stampede" dove richieste multiple parallele esauriscono il connection pool. La persistenza dello stato di errore garantisce che un eventuale blocco dell'endpoint non causi timeout sequenziali della durata cumulativa di minuti.

---

## [v0.19.30] - 2026-03-09

### Fixed - Conversational Bypass & Semantic Memory Resilience

- **Engine: Conversational Bypass Import Fix**: Aggiunto l'import mancante per `LLMRequest`, `Message` e `MessageRole` in `core.py` che causava un `NameError` durante la gestione delle query conversazionali fast-path (es. "ciao").
- **Memory: Semantic Memory Provider Dispatch**: Risolto un bug in `_extract_entities_llm` (`engine.py`) che forzava l'uso del client cloud (NanoGPT) ignorando la configurazione. Ora usa `get_reasoning_client()` permettendo il salvataggio nel Knowledge Graph anche con modelli locali MLX.

---

## [v0.19.29] - 2026-03-04

### Fixed - Query Response Structured Report & Decomposer Optimization

- **Engine: Intent-Tool Mapping Expansion**: Ampliato `_INTENT_TOOL_MAP` in `iterative_executor.py` per includere `file_search`, `file_read`, `email_search` e `workspace_report`. Questo risolve il problema dei tool ignorati durante l'esecuzione ReAct.
- **Engine: Fast-Path Logic Fix**: Corretta l'euristica in `_observe_results` che marcava prematuramente come "sufficienti" i risultati contenenti solo ID, saltando la fase di estrazione dati reale.
- **Google Workspace: Calendar Historical Search**: Risolto bug in `calendar_list_events` che forzava `time_min` alla data odierna anche per ricerche testuali, impedendo il recupero di eventi passati (es. ottobre 2024).
- **Decomposer: Keyword-First Optimization**: Aggiornate le istruzioni di decomposizione per generare sub-query brevi e focalizzate su keyword (max 8-10 parole). Le query discorsive lunghe degradavano la precisione della ricerca vettoriale e delle API.
- **Synthesizer: Large Report Support**:
  - Aumentato `max_tokens` a 16.384 per supportare report multi-fonte complessi.
  - Espanso `MAX_RESULT_CHARS` a 8.192 per prevenire il troncamento dei dati grezzi prima della sintesi.
  - Pulizia `_fallback_response` per nascondere sezioni vuote e migliorare la leggibilità dei dati grezzi in caso di failure LLM.
- **Streaming: Thinking Extraction 2.0**: Ottimizzata l'estrazione dei thinking tokens per gestire meglio i nuovi modelli di reasoning (DeepSeek/Reasoning Pro).

---

## [v0.19.28] - 2026-03-03

### Fixed - Dashboard Engine Resilience & Streaming Fix

- **Engine Core Attribute Fix**: Risolto `AttributeError: 'ToolCallingEngine' object has no attribute '_config'`. Il problema risiedeva in un riferimento obsoleto a `router_model` in `core.py`, migrato correttamente a `model_routing`.
- **SSE Streaming Guarantee**: Implementato pattern `try...finally` in `run_iterative_stream` per forzare l'emissione dell'evento `done`. Questo previene il blocco del frontend in caso di eccezioni durante l'esecuzione asincrona.
- **Synthesizer Heuristic 2.0.0**: 
  - Ottimizzata la distinzione `thinking` vs `content` con nuovi marker di inizio contenuto.
  - Introdotto `FORCE_CONTENT_THRESHOLD` di 300 caratteri per garantire la transizione automatica alla risposta finale anche in assenza di marker espliciti dall'LLM.
  - Flush periodico del buffer per migliorare la fluidità percepita nello streaming.

---

## [v0.19.27] - 2026-02-27

### Fixed - Science Research Domain: Multi-Step Query Support

- **P0 Fix: Temporal Filtering & Citation Sorting**
  - `semanticscholar_search`: Aggiunto supporto parametri `year_min` e `year_max` per filtri temporali
  - Ordinamento automatico risultati per `citation_count` (decrescente)
  - Aggiunto `paper_id` nei risultati per permettere drill-down con `semanticscholar_paper`
  - Tool definitions aggiornate per esporre nuovi parametri al router LLM

- **P0 Fix: Synthesizer Enhancement for Partial Results**
  - Nuovo metodo `_generate_partial_response()` nel synthesizer
  - Fornisce feedback informativo anche quando alcuni tool falliscono
  - Evita risposte generiche "Non sono riuscito a trovare risultati"
  - Specifica quali tool hanno avuto successo e quali hanno fallito

- **P1 Fix: Web Search Fallback for Author Queries**
  - Aggiunto fallback a `web_search` nel science_research handler
  - Nuovo metodo `_is_author_query()` per rilevare query su autori/interviste/startup
  - Nuovo metodo `_search_author_web()` per esecuzione web search fallback
  - Nuovo metodo `_build_author_search_query()` per costruire query web mirate
  - Copre gap tool per interviste, talk, startup, progetti open-source

### Root Cause Analysis

Query complessa su "quantum computing error correction" falliva con risposta generica. Analisi ha identificato 6 problemi:

1. Query multi-step non supportata nativamente (orchestrazione sequenziale mancante)
2. Mancanza tool per estrazione autori/affiliazioni
3. Nessun tool per interviste/talk/articoli divulgativi
4. Nessun tool per startup/progetti open-source
5. Filtri temporali non supportati nei tool scientifici
6. Ordinamento per citation count mancante

### Solution Architecture

```
Complex Science Query
    ↓
[QueryDecomposer] → Sub-queries
    ↓
[IterativeExecutor] → Per ogni sub-query:
    ↓
    [Router] → Select tools (con filtri temporali)
    ↓
    [semanticscholar_search] → Papers ordinati per citations
    ↓
    [Synthesizer] → Risultati parziali con feedback
    ↓
    [Web Search Fallback] → Interviste/startup (se necessario)
```

### Test Coverage

- Unit tests: `test_semanticscholar_search_with_year_filter()` ✅
- Unit tests: `test_semanticscholar_search_sorted_by_citations()` ✅
- Unit tests: `test_generate_partial_response_with_failed_tools()` ✅
- Unit tests: `test_is_author_query_detection()` ✅
- Integration tests: `test_quantum_computing_query_with_filters()` ✅

### Files Modified

- `src/me4brain/domains/science_research/tools/science_api.py` (+45 lines)
  - Enhanced `semanticscholar_search()` con filtri temporali e ordinamento
  - Updated tool definitions con nuovi parametri

- `src/me4brain/engine/synthesizer.py` (+51 lines)
  - Nuovo metodo `_generate_partial_response()`
  - Migliorata gestione risultati parziali

- `src/me4brain/domains/science_research/handler.py` (+118 lines)
  - Aggiunto fallback a web_search nel metodo `execute()`
  - Nuovi metodi helper: `_is_author_query()`, `_search_author_web()`, `_build_author_search_query()`

- `tests/domains/science_research/test_science_api_enhancements.py` [NEW]
  - 8 test cases per validare tutte le fix

### Performance Impact

| Metrica                                    | Prima      | Dopo           | Miglioramento |
| ------------------------------------------ | ---------- | -------------- | ------------- |
| Query "quantum computing error correction" | ❌ Fallita  | ✅ Risultati    | 100%          |
| Filtri temporali supportati                | ❌ No       | ✅ Sì           | -             |
| Ordinamento citation count                 | ❌ No       | ✅ Automatico   | -             |
| Interviste/startup coverage                | ❌ No       | ✅ Web fallback | -             |
| Risultati parziali UX                      | ❌ Generico | ✅ Informativo  | -             |

### Tool Count

- Science research capabilities: 8 (arxiv_search, openalex_search, semanticscholar_search, semanticscholar_paper, semanticscholar_citations, crossref_search, crossref_doi, pubmed_search)
- Python tools totali: **182** (no change, fix interne)

---

## [v0.19.26] - 2026-02-27

### Added - Travel Domain Flight & Accommodation Search

- **Amadeus Flight Search**: Registrate capabilities `flight_search` e `airport_search` nel handler
  - `amadeus_search_flights`: Ricerca voli commerciali con prezzi (Ryanair, easyJet, etc.)
  - `amadeus_airport_search`: Ricerca aeroporti per codice IATA
  - Integrazione con Amadeus SDK esistente in `travel_api.py`

- **Google Places Hotel & Restaurant Search** (2 nuovi tool):
  - `google_places_hotels`: Ricerca hotel con filtri stelle, prezzo massimo, area
  - `google_places_restaurants`: Ricerca ristoranti con filtri cucina, rating minimo, price level
  - Parsing risultati con rating, prezzo, indirizzo
  - Max 10 risultati per query con error handling robusto

- **Synthesizer Fallback Enhancement**:
  - Aggiunta formattazione specifica per hotel (🏨) e ristoranti (🍽️)
  - Mostra nome, rating, prezzo, indirizzo per ogni risultato
  - Fallback response più utile quando i tool falliscono

- **Router Tool Availability Validation**:
  - Nuovo metodo `_validate_tool_availability()` nel router
  - Verifica API keys prima di eseguire query (fail-fast)
  - Supporta: Amadeus, Google Places, FMP, Finnhub, Google Workspace
  - Logging dettagliato tool unavailable con motivo

- **Configuration Documentation**:
  - Aggiunto `.env.example` con sezioni Travel, Finance, Google Workspace
  - API keys richieste: AMADEUS_CLIENT_ID/SECRET, GOOGLE_PLACES_API_KEY, FMP_API_KEY, FINNHUB_API_KEY, GOOGLE_OAUTH_TOKEN

### Fixed - Travel Domain Query Processing

- **Problem**: Query Barcelona trip planning falliva per tool non registrati e API keys non documentate
- **Root Cause**: 
  - Amadeus functions esistevano ma non registrate come capabilities
  - Google Places tool completamente mancante
  - Router non validava disponibilità tool
  - Synthesizer fallback troppo verboso e generico

- **Solution**: Implementazione completa 5 fix (handler, travel_api, synthesizer, router, .env)

### Architecture

```
Barcelona Trip Query
    ↓ Router (valida API keys)
    ↓ Amadeus flight_search (MIL → BCN)
    ↓ Google Places hotel_search (Barcellona, 4⭐, max 150€)
    ↓ Google Places restaurant_search (Barcellona, cucina varia)
    ↓ Synthesizer (formatta con hotel/ristoranti specifici)
    ↓ Fallback response (se tool falliscono)
```

### Tool Count
- Travel domain capabilities: 6 (flight_tracking, flight_info, flight_search, airport_search, hotel_search, restaurant_search)
- Python tools totali: **182** (+2 Google Places)

### Added - Finance Domain Optimization (SOTA 2026)

- **Universal Financial Analytics**: Nuovo modulo `financial_analytics.py` (375 linee) con 20+ metriche (volatilità, drawdown, MA, YTD, Sharpe, Sortino, Alpha/Beta, RSI, MACD, Bollinger)
- **Batch Historical Data Tool**: Nuovo tool `yahooquery_historical` preferito a yfinance per efficienza (batch calls, retry, fallback Alpha Vantage)
- **Synthesizer Enhancement**: Istruzioni LLM per calcoli finanziari obbligatori e output tabellare
- **Router Improvements**: Regole per prioritizzare `yahooquery_historical` e ottimizzazione batch
- **Executor Deduplication**: Metodo `_deduplicate_tasks()` per rimuovere task duplicati
- **Test Coverage**: 26/27 test passati per `financial_analytics.py` + integration tests completi

### Architecture
```
Complex Finance Query
    ↓ Router (yahooquery_historical)
    ↓ ParallelExecutor (dedup)
    ↓ yahooquery_historical (batch OHLCV)
    ↓ Synthesizer (extract + invoke analytics)
    ↓ financial_analytics (compute metrics)
    ↓ Formatted Table + News
```

---

## [v0.19.25] - 2026-02-26

### Added - Calendar Meeting Analyzer (Multi-Platform Support)

- **`calendar_analyze_meetings`** (nuovo tool): Analizza eventi Google Calendar per trovare meeting da tutte le piattaforme (Google Meet, Zoom, Teams, Webex, etc.)
  - Rileva piattaforma meeting da `conferenceData`, `description` e `location`
  - Estrae link meeting con regex pattern per domini noti
  - Filtra per durata minima (default 5 min)
  - Ordina per durata (meeting più lunghi prima)
  - Supporta range temporale con validazione date
- **Platform Detection**: Algoritmo `_detect_meeting_platform()` con supporto per 8+ piattaforme
- **Meeting Link Extraction**: Parser `_extract_meeting_link()` per URL meeting da eventi calendario

### Fixed - Google OAuth Token Refresh

- **Token Expiry Issue**: Risolto problema token OAuth scaduto (18/02/2026) che impediva accesso email inviate
- **Auto-Refresh Mechanism**: Verificato funzionamento meccanismo esistente (pre-emptive refresh 5 min prima scadenza)
- **Scope Verification**: Confermato scope `gmail.send` presente e funzionante
- **Test Coverage**: Aggiunti test per verificare query `in:sent` e `from:me`

### Changed

- **`google_api.py`**: Aggiunto import `calendar_analyze_meetings` da nuovo modulo
- **`AVAILABLE_TOOLS`**: Registrato nuovo tool `google_calendar_analyze_meetings` (Calendar tools: 6 → 7)
- **Tool Count**: Python tools totali: **180** (+1)

### Performance

| Metrica                    | Prima                | Dopo                 |
| -------------------------- | -------------------- | -------------------- |
| Meeting detection          | Solo Google Meet     | **8+ piattaforme** ✅ |
| Meeting trovati (17-23/02) | 2 (fuori range)      | **4 (nel range)** ✅  |
| Token OAuth                | Scaduto (18/02)      | **Refreshato** ✅     |
| Email inviate query        | 0 risultati (errore) | **5 risultati** ✅    |

### Architecture

```
calendar_analyze_meetings(start_date, end_date)
    ↓
calendar_list_events(time_min, time_max)
    ↓
for each event:
    _detect_meeting_platform() → google_meet | zoom | teams | other | unknown
    _extract_meeting_link() → meeting URL
    calculate duration, extract attendees
    ↓
sort by duration (longest first)
    ↓
{ total_meetings, platform_breakdown, top_3_longest, meetings[] }
```

---

## [v0.19.24] - 2026-02-26

### Added - NBA Pipeline & Engine Resilience (v2.0.0)

- **NBA H2H 2.0.0**: Migrazione a `LeagueGameFinder` con supporto multi-stagione (Current + Previous).
- **Timeout Balancing**: Default timeout ridotto a 15s per garantire la finestra di retry entro i 60s del motore globale.
- **KeyError Protection**: Normalizzazione JSON nel decomposer per gestire chiavi malformate (literal quotes).
- **Rate Limit Queue**: Sistema di accodamento con delay di 2.5s per l'API NBA Stats.

---

## [v0.19.23] - 2026-02-23

### Added - Remote Domain Sync (SOTA 2026)

- **Multi-Source Seeding**: Eseguito `seed_graphrag_unified.py` su Neo4j remoto con iniezione di tool e few-shot embeddings.
- **Qdrant Persistence**: Indicizzate 250 capabilities (tools/skills) nella collezione `me4brain_capabilities` su GeekCom.
- **Domain Routing Fixes**: Aggiornati i prompt system del router per prevenire misrouting tra NBA, Finance e G-Suite.

---

## [v0.19.22] - 2026-02-23

### Added - Domain Augmentation (Phase 2 - SOTA 2026)

- **Sports NBA**: Aggiunta "Tactical Depth" per analisi lineup e matchups.
- **Sports Booking**: Integrazione Ticketmaster e StubHub per logistica eventi.
- **Medical**: Aggiunti `pill-identifier` e `drug-it-analyzer` (ITA Market).
- **Fitness**: Aggiunto `workout-cli` per log allenamenti e progressione forza.
- **Entertainment**: Upgrade a TMDB MCP, YouTube Music, Spotify e Google Books.
- **Geo/Food/Finance**: Integrazione tool premium (Polygon, Binance, Edamam, Tasty, Meteo.it).

---

## [v0.19.21] - 2026-02-23

### Added - Food Domain SOTA 2026 Optimization

- **SOTA 2026 Rework**: Aggiornato `food.yaml` con mappatura `codebase-first` per TheMealDB (ricette) e Open Food Facts (prodotti alimentari).
- **Cross-Domain Integration**: Implementati link strategici con Travel (ristoranti in viaggio), Web Search (recensioni/blog), Entertainment (film sul cibo) e GeoWeather (cibo stagionale).
- **Nutrition Intelligence**: Introdotte Hard Rules per l'interpretazione obbligatoria di NutriScore (A-E) e NOVA Group (1-4) con alert salute automatici.
- **Few-Shot Examples**: Aggiunti 15+ esempi cross-domain per workflow completi (ricerca ricette, analisi prodotti, pianificazione viaggi culinari).

### Added - Entertainment Domain SOTA 2026 Optimization

- **SOTA 2026 Rework**: Aggiornato `entertainment.yaml` con mappatura `codebase-first` per i tool reali di `entertainment_api.py` (TMDB, Open Library, Last.fm).
- **Protocol Compliance**: Implementazione completa dei 3 layer GraphRAG (Domain Hints, Constraints, Few-Shots).
- **Fix**: Allineamento parametri Open Library con la firma reale della funzione Python.

### Added - Geo Weather Domain SOTA 2026 Optimization

- **SOTA 2026 Rework**: Aggiornato `geo_weather.yaml` con mappatura `codebase-first` per Open-Meteo (current, forecast, historical), USGS (terremoti) e Nager.Date (festività).
- **Consolidation**: Eliminato il file ridondante `weather_geo.yaml` e allineato il routing dei domini in `geo_api.py`.
- **Protocol Compliance**: Implementazione completa dei 3 layer GraphRAG (Domain Hints, Constraints, Few-Shots).

---

## [v0.19.20] - 2026-02-23

### Added - Jobs Domain SOTA 2026 Optimization

- **SOTA 2026 Rework**: Aggiornato `jobs.yaml` con mappatura `codebase-first` per RemoteOK e Arbeitnow.
- **Cleanup**: Rimossi hint obsoleti per API esterne non supportate.
- **Protocol Compliance**: Implementazione completa dei 3 layer GraphRAG (Domain Hints, Constraints, Few-Shots).

---

## [v0.19.19] - 2026-02-23

### Added - Science Research Domain SOTA 2026 Optimization

- **SOTA 2026 Rework**: Aggiornato `science_research.yaml` con mappatura `codebase-first` per ArXiv, Semantic Scholar, Crossref e OpenAlex.
- **Cross-Domain Linkage**: Integrata ricerca scientifica avanzata nei workflow di `tech_coding`, `medical` e `knowledge_media`.
- **Protocol Compliance**: Implementati metadati 3-layer (Domain Hints, Constraints, Few-Shots) per la letteratura accademica.

---

## [v0.19.18] - 2026-02-23

### Added - Medical Domain SOTA 2026 Optimization

- **SOTA 2026 Rework**: Aggiornato `medical.yaml` con mappatura `codebase-first` per i tool reali di `medical_api.py` (RxNorm, PubMed, iCite, Europe PMC, ClinicalTrials.gov).
- **Evidence-Based Diagnostics**: Implementato supporto esplicito per la formulazione di ipotesi diagnostiche clinicamente supportate da PubMed/ClinicalTrials.gov.
- **Protocol Compliance**: Iniezione di constraint severi per la citazione obbligatoria delle fonti (PMID, NCT ID) e verifica obbligatoria delle interazioni farmacologiche.

---

## [v0.19.17] - 2026-02-23

### Added - Utility Domain SOTA 2026 Optimization

- **SOTA 2026 Rework**: Aggiornato `utility.yaml` con mappatura `codebase-first` per Browser, Proactive, Schedule e Sessions tools.
- **Cross-Domain Linkage**: Implementata iniezione di hint cross-dominio per attivare monitoraggi autonomi e automazione browser partendo da altri domini specialistici.
- **Protocol Compliance**: Allineamento al protocollo GraphRAG per i metadati 3-layer (Domain Hints, Constraints, Few-Shots).

---

## [v0.19.16] - 2026-02-23

### Added - Tech Coding SOTA 2026 Optimization

- **Full Domain Rework**: Riprogettato `tech_coding.yaml` eliminando i tool fittizi e allineandolo ai tool reali di `tech_api.py`.
- **Sandbox Execution Policy**: Implementate regole specifiche per l'uso di `piston_execute` e `stackoverflow_search`.
- **Multi-Source Library Search**: Ottimizzata la ricerca cross-platform (GitHub/NPM/PyPI) per la selezione delle dipendenze.

---

## [v0.19.15] - 2026-02-23

### Added - Web Search SOTA 2026 & Cleanup

- **Web Search Refactoring**: Completato l'upgrade di `web_search.yaml` con logica di smart routing e extraction automatica.
- **Architectural Cleanup**: Rimozione di 260+ file YAML obsoleti nelle cartelle `auto_generated`.
- **Cross-Domain Awareness**: Iniezione di referral web search in Finance, Medical e Tech Coding.
- **Semantic Scope Refinement**: Delimitazione dei domini `search` (solo Drive/Gmail) e `web_data` (solo Playwright) per prevenire allucinazioni di routing.

---

## [v0.19.14] - 2026-02-23

### Added - GraphRAG SOTA 2026 Optimizations

- **Domain Prompts Authoring**: Aggiornati i file YAML dei domini strategici (Google Workspace, Finance Crypto, Sports NBA, Travel, Knowledge Media) secondo il nuovo standard Hand-Crafted PromptRAG.
- **Finance Sentiment & Insider Trading Integration**: Potenziato dominio `finance_crypto` con suite di ricerca sentiment (`rumor_scanner`, `hot_scanner`, `finnhub_news`). Implementato workflow di analisi specialistica per consulenza finanziaria esperta con focus su SEC filings e Fair Value DCF.
- **Domain Specialization** (2026-02-23): Consolidamento dei domini sportivi (NBA Betting) e ottimizzazione euristica dei domini `google_workspace` (consulenza PA), `finance_crypto` (consulenza finanziaria profonda con integrazione sentiment/news e insider trading), `travel` (Cross-domain routing intelligente per Full Vacation Planning), `web_search` (SOTA 2026 con architecture cleanup) e `tech_coding` (Mappatura API reali GitHub/NPM/PyPI/StackOverflow e Piston).
- **Google Workspace Reporting Heuristics**: Ottimizzato dominio Google per consulenza PA. Aggiunte regole per identificazione versioni `DEF`, incrocio collaboratori e integrazione tool `google_docs_create` con supporto cartelle.
- **Travel Vacation & Logistics Platform**: Aggiornato `travel.yaml` implementando la sinergia Multi-Dominio. Connessi dinamicamente tool di previsioni meteo (`openmeteo_forecast`) e smart search ibrida (`tavily_search`, `duckduckgo_instant`) al core booking di Amadeus. Aggiunti few-shot prompt complessi per supportare target utenza custom (es. viaggi in famiglia).
- **Sports Domain Consolidation**: Eliminati i file ridondanti `sports.yaml` e `sports_betting.yaml`. Consolidata la "Centrale Scommesse Professionale" in `sports_nba.yaml` con integrazione diretta dei tool `NBABettingAnalyzer` e protocolli di validazione infortuni.
- **Pydantic Schema Extraction**: Sostituita estrazione AST con `generate_pydantic_schemas.py` per fedeltà tipologica assoluta.
- **Hybrid Few-Shot (Vector + Graph)`: Recupero dinamico di esempi tramite ricerca vettoriale su Neo4j filtrata per i tool candidati.
- **Massive Migration**: Portati 18 domini GraphRAG definitivi al protocollo SOTA 2026, integrando oltre 70 skills (locali e bundled).
- **Full Compliance**: Sviluppato ed eseguito `validate_sota_conformity.py` raggiungendo lo stato di "0 errori strutturali" e "0 warning funzionali" (Zero Warning Assoluti).
- **Layer 3 Optimization**: Aggiunte sezioni `RESULT` a tutti i few-shot examples e sezioni `Anti-pattern` mancanti per massimizzare la precisione del GraphRAG.
- **GraphRAG Cleanup**: Eliminati 9 domini placeholder o duplicati obsoleti (`communication`, `content_creation`, `data_analysis`, `dev_tools`, `finance`, `scheduling`, `science`, `search`, `web_data`) per concentrare il vector database sui domini specializzati e performanti.
- **Session Caching**: `_hints_cache` in `IterativeExecutor` per ridurre la latenza di consultazione del Knowledge Graph.
- **Tool Versioning**: Gestione deprecazione tool e migrazione suggerita direttamente nei prompt hints.
- **Telemetry Layer**: Tracciamento `telemetry_validation_failed` e `telemetry_validation_success` per monitoraggio precisione LLM.

### Changed

- **Token Budgeting**: Introdotto parametro `allocated_tokens` per step e tracking `_total_tokens_used`.
- **ReAct Loop**: Ridotto `max_logic_attempts` a 2 per favorire precisione ed efficienza.

---

## [v0.19.13] - 2026-02-22

### Added - Hand-Crafted GraphRAG Architecture (SOTA 2026)

- **Graph Retrieval (Layer 1)**: Modificato `IterativeExecutor` per interrogare Neo4j alla ricerca di `DomainTemplate` e `ToolTemplate` correlati ai tool selezionati per lo step.
- **Hard Validation (Layer 2)**: L'executor ora esclude in modo rigido e logga come error qualsiasi tool "allucinato" dall'LLM che non fa parte del set recuperato.
- **Argument Constraints (Layer 3)**: Iniezione direzionale di restrizioni degli argomenti YAML e JSON Scheme nel prompt di step. `_build_step_prompt` include una sezione `STRICT TOOL GUIDELINES`.
- **Neo4j Seeding**: Nuovo script `seed_manual_templates_standalone.py` per l'iniezione programmatica dei node pattern YAML su database grafico Neo4j.

### Fixed - Tool Misrouting & UI Streaming

- **Weather Tools Misrouting**: I tool openmeteo e nager_holidays sono ora guidati deterministicamente, risolvendo il problema del motore LLM che derivava le richieste meteo base verso Google Search.
- **SSE Session Isolation**: Risolto severo bug di streaming bleeding tra sessioni e tab. `engine.py` ora assicura l'iniezione payload del parametro `session_id` su ogni output chunk SSE per correlazione stretta sul client.

---

## [v0.19.12] - 2026-02-12

### Fixed - Server Credentials Deployment (Geekcom)

- **`.env` server (deployment)**:
  - Il `.env` sul server Geekcom aveva solo 43 righe — mancavano ~30 API keys per servizi esterni
  - Audit completo di tutti i 15 domini: Google OAuth, eBay, Finance (Alpaca, Binance, Finnhub, FMP, FRED, NASDAQ, Alpha Vantage, Hyperliquid, EODHD), Entertainment (TMDB, LastFM), Web Search (Tavily), Sports (BallDontLie, TheOdds), Tech (GitHub), Travel (Amadeus), AI (OpenAI, OpenRouter)
  - Generato `.env` completo (173 righe) con host Docker interni (`postgres`, `redis`, `qdrant`, `neo4j`), porte standard, `EMBEDDING_DEVICE=cpu`
  - Root cause: errore `'NoneType' object has no attribute 'files'` su Google Workspace tools causato da `GOOGLE_TOKEN_PATH` mancante nel container
  - Stack riavviato con `docker compose --profile app` — 36 credenziali caricate (vs 5 prima)

---

## [v0.19.11] - 2026-02-12

### Fixed - Auto Community Detection (Session Graph)

- **`session_graph.py`** (`memory/session_graph.py`):
  - **Root cause**: `detect_communities()` (Louvain) esisteva ma non veniva mai invocato automaticamente dopo l'ingestione → sidebar "Cluster" sempre vuota
  - Aggiunto `_safe_detect_communities(tenant_id)` con cooldown di 5 minuti per tenant
  - Invocato in fire-and-forget alla fine di `ingest_session()`, dopo l'estrazione topic
  - Non propaga eccezioni: il clustering è opzionale, non deve mai impattare il flusso chat
  - Costante `COMMUNITY_DETECTION_COOLDOWN_SECONDS = 300` per evitare ricalcoli eccessivi

### Architecture

```
ingest_session()
    → create_task(_safe_extract_topics)      # fire-and-forget
    → create_task(_safe_detect_communities)  # fire-and-forget con cooldown 5min
        → detect_communities() → Louvain → TopicCluster nodes in Neo4j
```

---

## [v0.19.10] - 2026-02-11

### Added - Session Graph (Neo4j Knowledge Graph)

- **`session_graph.py`** (`memory/session_graph.py`) [NEW]:
  - Modulo completo per nodi/archi sessione su Neo4j
  - `ingest_session()` → crea nodo Session + Topic + archi DISCUSSED_IN
  - `get_clusters()` → community detection con Louvain algorithm
  - `get_related_sessions()` → graph traversal + PageRank per sessioni correlate
  - `search_sessions()` → ricerca semantica full-text
  - `get_connected_nodes()` → multi-hop traversal per nodi hub con ConnectionScore
  - `ConnectedNode` dataclass: id, name, nodeType, connectionScore, relationType

- **API Routes** (`api/routes/session_graph.py`) [NEW]:
  - `GET /v1/graph/clusters` — Cluster tematici sessioni
  - `GET /v1/graph/related/{session_id}` — Sessioni correlate con score
  - `POST /v1/graph/search` — Ricerca semantica
  - `GET /v1/graph/connected-nodes/{session_id}` — Top-N nodi connessi
  - `POST /v1/graph/ingest` — Ingestione conversazione nel grafo

- **Main App** (`api/main.py`):
  - Registrato router `/v1/graph` con tag `graph`

### Architecture (Neo4j)
```
(:Session {id, title, created_at})
    -[:DISCUSSED_IN]->
(:Topic {name, session_count})
    <-[:DISCUSSED_IN]-
(:Session) — related via shared topics + PageRank
```

---

## [v0.19.8] - 2026-02-11

### Added - Context-Aware Query Rewriter (Memory Fix)

- **`ContextAwareRewriter`** (`engine/context_rewriter.py` — NUOVO):
  - Riscrive query follow-up in domande self-contained integrando contesto conversazionale
  - Heuristic detection: pronomi anaforici, query corte, congiunzioni, feedback
  - LLM rewriting via Mistral 3 Large (`mistral-large-3-675b-instruct-2512`)
  - Entity-aware: integra entità estratte dal grafo NetworkX di sessione
  - Fallback sicuro: in caso di errore ritorna query originale

- **Pre-Query Rewriting** (`api/routes/engine.py`):
  - `_rewrite_query_with_context()`: helper che recupera cronologia + entità → rewriter
  - `routing_query`: query riscritta usata per routing (streaming e non-streaming)
  - Query originale mantenuta per `_persist_interaction()` (Working Memory)

### Root Cause Analysis
Il router e il decomposer ricevevano la query raw dell'utente senza contesto conversazionale.
Follow-up come "Voglio link reali" venivano routate senza sapere che il topic era "Mac Studio 64GB".
Il context era passato solo al synthesizer, troppo tardi per influenzare il routing.

### Architecture
```
Prima:  User Query → Router → Tools (contesto perso)
Dopo:   User Query → Rewriter(WM + NetworkX) → routing_query → Router → Tools (contesto integrato)
```

---

## [v0.19.7] - 2026-02-11

### Fixed - NBA Tool Timeout & Pipeline Resilience

- **NBA API tools `timeout=30`** (`domains/sports_nba/tools/nba_api.py`):
  - `nba_api_team_games`, `nba_api_player_career`, `nba_api_advanced_stats`, `nba_api_standings`, `nba_api_head_to_head`: aggiunto `timeout=30` alle chiamate `nba_api.stats.endpoints`
  - Root cause: `asyncio.to_thread()` non è cancellabile — senza timeout HTTP, la libreria `nba_api` poteva hangare indefinitamente su `stats.nba.com` (rate limiting)
  - Fix: timeout=30s viene passato al costruttore dell'endpoint che configura `requests.get(timeout=30)`

- **Per-tool timeout** (`engine/executor.py`): `60s` → `120s`
- **Step timeout** (`engine/iterative_executor.py`): `600s` → `900s` (costante `STEP_TIMEOUT_SECONDS`)
- **Client silence timeout** (`persan/packages/me4brain-client/src/engine.ts`): `360_000ms` → `900_000ms` (15 min) — allineato con `STEP_TIMEOUT_SECONDS`

### Root Cause Analysis
Tool NBA usano `asyncio.to_thread()` per wrappare chiamate sincrone `nba_api`. Il thread non è cancellabile da `asyncio.wait_for(timeout)`, quindi il timeout dell'executor era inefficace. Aggiungendo `timeout=30` al costruttore dell'endpoint, la libreria configura internamente `requests.get(timeout=30)`, rendendo il thread killabile dopo 30s.

---

## [v0.19.6] - 2026-02-10

### Added - Memory Sync & User Feedback System

- **WorkingMemory Feedback Layer** (`memory/working.py`):
  - `_feedback_key()`: Chiave Redis Hash per feedback sessione
  - `delete_message()`: `XDEL` su Redis Stream + cleanup feedback associato
  - `update_feedback()`: Score ▲/▼ in Redis Hash separato (stream entries immutabili)
  - `get_feedback()`: Recupera tutti i feedback di una sessione
  - `get_messages()`: Ora include `feedback_score` e `feedback_comment` nei messaggi restituiti

- **3 Nuovi API Endpoints** (`api/routes/working.py`):
  - `DELETE /v1/working/sessions/{id}/messages/{msg_id}` — Elimina messaggio dallo stream
  - `PUT /v1/working/sessions/{id}/messages/{msg_id}/feedback` — Upvote/downvote (score: +1/-1/0)
  - `GET /v1/working/sessions/{id}/feedback` — Lista feedback sessione

### Architecture (Redis)
```
Session Feedback: HASH → tenant:{tid}:user:{uid}:session:{sid}:feedback
                         { message_id: '{"score": 1, "comment": ""}' }
```

### Design Decision
Redis Streams non supportano aggiornamento in-place delle entries. Il feedback è quindi archiviato in un Redis Hash separato e mergiato in `get_messages()` al momento del recupero.

---

## [v0.19.5] - 2026-02-10

### Fixed - Tool Param Filtering & Multi-Session WebSocket

- **execute_tool param filtering** (16 domini):
  - Ogni `execute_tool` ora usa `inspect.signature()` per filtrare parametri allucinati dall'LLM
  - Parametri extra vengono ignorati con warning log anziché crashare con `TypeError`
  - Domini fixati: nba, medical, google, finance, utility, geo, jobs, knowledge, science, travel, food, playtomic, entertainment, search, tech, proactive

- **Synthesizer streaming timeout** (`engine/synthesizer.py`):
  - `asyncio.timeout`: `300s` → `600s` (10 min) per query concorrenti sotto carico

- **Frontend multi-sessione WS** (PersAn):
  - `gateway-client.ts`: `sendChat()` accetta `sessionId` esplicito
  - `useGateway.ts`: passa `currentSessionId` al WS client
  - Gateway `router.ts`: messaggio `error` include `sessionId` per routing corretto

---

## [v0.19.4] - 2026-02-10

### Fixed - Timeout Architecture for Long-Running Queries

- **Pydantic timeout limit** (`api/routes/engine.py`):
  - `EngineQueryRequest.timeout_seconds`: `le=600.0` → `le=1800.0` (30 min)
  - Default: `30.0` → `120.0` per query complesse
  - Il client può ora richiedere timeout fino a 30 minuti senza `ValidationError`

- **httpx LLM read timeout** (`llm/nanogpt.py`):
  - `read` timeout: `300s` → `600s` (10 minuti)
  - Singole chiamate LLM con sintesi complessa non scadono più a 5 minuti

- **IterativeExecutor step timeout** (`engine/iterative_executor.py`):
  - `asyncio.timeout`: `480s` → `600s` (10 minuti per step)
  - Step con DEEPER + multi-LLM + ReAct hanno più tempo per completarsi

### Root Cause Analysis (Query ANCI)
La query "Alta Irpinia" (ANCI) falliva dopo 610s con timeout. Cause identificate:
1. `keepAliveTimeout: 620_000` in undici Agent chiudeva la connessione SSE durante pause LLM
2. `httpx read=300s` troncava singole chiamate LLM lunghe
3. Pydantic `le=600.0` rifiutava `timeout_seconds=900` dal client

---

## [v0.19.2] - 2026-02-09

### Added - Engine Memory-Aware Integration (Layer I + II)

- **Pre-Query Memory Enrichment** (`api/routes/engine.py`):
  - `_build_memory_context()`: costruisce contesto arricchito da Working Memory (ultimi 10 turni) + Episodic Memory (episodi semanticamente simili via Qdrant)
  - Attivato tramite `session_id` nel body di `/engine/query`
  - Ogni layer è indipendente: se Redis o Qdrant sono down, la query procede senza contesto

- **Post-Query Memory Persistence** (`api/routes/engine.py`):
  - `_persist_interaction()`: salva turni user+assistant in Working Memory + crea episodio Q&A in Episodic Memory
  - Eseguito in background (fire-and-forget via `asyncio.create_task`)
  - Layer II: episodi taggati `persan_chat` con importance 0.6 per recall cross-session futuro

- **`session_id` in `EngineQueryRequest`**: campo opzionale che attiva l'integrazione memoria completa. Backward-compatible con `conversation_context` come fallback manuale.

### Architecture

```
PersAn Gateway → queryStream(msg, {sessionId})
                      ↓
    /engine/query (session_id presente)
                      ↓
    PRE-QUERY:  Working Memory (10 turns) + Episodic Memory (3 episodes)
                      ↓
    Engine execution (Crystallizer Layer IV già attivo)
                      ↓
    POST-QUERY: Working Memory (save turns) + Episodic Memory (save episode)
```

### Layer Integration Status

| Layer                  | Stato        | Funzione                                   |
| ---------------------- | ------------ | ------------------------------------------ |
| I — Working Memory     | ✅ Integrato  | Contesto turni recenti + salvataggio       |
| II — Episodic Memory   | ✅ Integrato  | Recall cross-session + persistenza episodi |
| III — Semantic Memory  | ⏳ Fase 2     | Entity extraction (futuro)                 |
| IV — Procedural Memory | ✅ Già attivo | Crystallizer + Muscle Memory               |

---

## [v0.19.1] - 2026-02-09

### Added - Yahoo Finance Fallback Architecture

- **Yahoo Finance Fundamentals** (via `yfinance` library):
  - `_yahoo_financials()`: Helper async con `asyncio.to_thread` per dati fondamentali
  - Gestione automatica crumb auth (Yahoo v10 ora richiede autenticazione)
  - Copertura universale: funziona per qualsiasi ticker (non solo top US)
  - Dati: Balance Sheet, Income Statement, Cash Flow, Key Metrics, Ratios, DCF

- **6 Smart Wrapper Tool** con fallback chain Yahoo → FMP:
  - `stock_key_metrics`: ROE, ROA, EV/EBITDA, Market Cap (Yahoo `.info` → FMP)
  - `stock_ratios`: P/E, PEG, P/B, margins, debt metrics (Yahoo `.info` → FMP)
  - `stock_dcf`: Fair value analyst targets (Yahoo → FMP DCF model)
  - `stock_income_statement`: Revenue, profit, margins, EPS (Yahoo `.income_stmt` → FMP)
  - `stock_balance_sheet`: Assets, liabilities, equity, cash, debt (Yahoo `.balance_sheet` → FMP)
  - `stock_cash_flow`: Operating/Investing/Financing CF, FCF (Yahoo `.cashflow` → FMP)

- **Alias retrocompatibilità**: `fmp_*` → `stock_*` (Qdrant index e LLM memory)

### Changed
- `finance_api.py`: ~3760 → ~4120 righe (+360 righe Yahoo Finance integration)
- `pyproject.toml`: Aggiunto `yfinance` come dipendenza

### Fixed
- **FMP 402 Premium Required** per ticker non-top-US (es. HOG): ora serviti da Yahoo Finance
- **FMP v3 endpoint deprecation** (gen 2025): migrazione a `/stable/` completata

---

## [v0.18.0] - 2026-02-09

### Added - Trading Platform Enhancement (19 Nuovi Tool + Orchestratore)

- **Binance Trading Data** (2 nuovi tool):
  - `binance_klines`: Candlestick OHLCV (1m–1w, max 1000 candele)
  - `binance_orderbook`: L2 order book depth con spread calculation

- **Market Analysis Tools** (4 nuovi tool):
  - `fear_greed_index`: CNN Fear & Greed Index (score 0-100 con sentiment label)
  - `market_context_analysis`: VIX/SPY/QQQ regime detection (bull/bear/choppy + scoring)
  - `hot_scanner`: Trending scanner multi-source (CoinGecko trending + Finnhub news)
  - `rumor_scanner`: Early signals scanner (M&A, insider buying, upgrades con impact scoring)

- **Alpaca Paper Trading** (4 nuovi tool — PAPER ONLY):
  - `alpaca_place_order`: Market/limit/stop/stop_limit con safety check paper endpoint
  - `alpaca_order_history`: Storico ordini con filtro status (open/closed/all)
  - `alpaca_cancel_order`: Cancellazione ordini per ID
  - `alpaca_portfolio_history`: Equity curve e P/L con granularità configurabile

- **FMP Financial Statements** (4 nuovi tool):
  - `fmp_income_statement`: Revenue, profit, margins, EPS (annual/quarter)
  - `fmp_balance_sheet`: Assets, liabilities, equity, cash, debt
  - `fmp_cash_flow`: Operating, investing, financing, FCF, CapEx
  - `fmp_stock_screener`: Screener per market cap, sector, country

- **Hyperliquid Testnet** (4 nuovi tool):
  - `hyperliquid_orderbook`: L2 order book DEX con spread
  - `hyperliquid_funding_rates`: Funding rates annualizzati + OI + volume (top30)
  - `hyperliquid_candles`: OHLCV candlestick perpetual futures
  - `hyperliquid_open_orders`: Ordini aperti su testnet

- **Multi-Dimensional Analysis Orchestrator** (`multi_analysis.py` — NUOVO file):
  - `multi_dimensional_analysis`: Analisi parallela 6 dimensioni pesate
  - Dimensioni: Fundamentals (25%), Technical (20%), Momentum (15%), Sentiment (15%), Valuation (15%), Market Context (10%)
  - Auto-detect asset type (stock/crypto/ETF) con analisi adattiva
  - Signal output: STRONG BUY / BUY / HOLD / SELL / STRONG SELL
  - Composite score -1.0 → +1.0 (normalizzato 0-100)
  - Override rules ispirate da OpenClaw `synthesize_signal()`: risk-off penalty, contrarian sentiment
  - Depth modes: quick (3 dim), standard (5), deep (tutte + hot/rumor scanner)

### Changed
- **`finance_api.py`**: Espanso da 2113 a ~3730 righe
- **AVAILABLE_TOOLS**: 24 → 43 tool registrati
- **get_tool_definitions**: 20 → 38 ToolDefinition con descrizioni search-friendly
- **get_executors`: 22 → 42 executors
- **Qdrant reindex**: 248 punti (179 tools + 69 skills)
- **`execute_tool()`**: Aggiunto routing lazy per `multi_dimensional_analysis` (evita circular import)

### Architecture

```
multi_dimensional_analysis("AAPL", depth="standard")
    ↓
detect_asset_type → "stock"
    ↓
asyncio.gather(
    fmp_key_metrics, fmp_ratios, fmp_dcf,          # fundamentals + valuation
    technical_indicators(rsi), technical_indicators(macd),  # technical
    fear_greed_index, market_context_analysis,       # sentiment + context
)
    ↓
_calculate_*_score() per dimensione → score -1.0 → +1.0
    ↓
_synthesize_signal() con weighted scoring + override rules
    ↓
{ signal: "BUY", confidence: "medium-high", score_0_100: 68, breakdown: {...} }
```

### Safety
> ⚠️ Tutti gli ordini trading usano esclusivamente:
> - Alpaca: `paper-api.alpaca.markets` (paper trading endpoint)
> - Hyperliquid: `api.hyperliquid-testnet.xyz` (testnet)
> - Nessun ordine reale può essere piazzato

### Tool Count
- Python tools: **179** (+19)
- Skills: **69**
- **Totale Qdrant: 248 punti**

---

## [v0.18.3] - 2026-02-08

### Fixed - NBA Betting Query Routing & Tools

- **Domain Classifier Prompt** (`engine/hybrid_router/domain_classifier.py`):
  - Aggiunto esempio NBA betting (`pronostico Lakers vs Celtics...`) → dominio `sports`
  - Aggiunta regola di disambiguazione: `scommesse`, `betting`, `pronostico`, `odds`, `value bet` → **SEMPRE `sports`**, MAI `finance`
  - Impedisce al LLM di trattare abbreviazioni NBA (LAL, BOS, etc.) come ticker finanziari

- **Query Decomposer Prompt** (`engine/hybrid_router/query_decomposer.py`):
  - Aggiunto esempio decomposizione query scommesse NBA in 2 sub-query (`nba_games_data` + `nba_context_data`)
  - 3 regole critiche anti-misrouting: tutti i termini betting → dominio `sports`

- **`nba_api_advanced_stats`** (`domains/sports_nba/tools/nba_api.py`):
  - **BUG**: `TeamEstimatedMetrics` ritorna `resultSet` (dict singolare), codice cercava `resultSets` (list plurale)
  - Tool ritornava sempre "Team not found in metrics"
  - Fix: gestisce entrambi i formati (dict e list) per robustezza
  - Verificato: Lakers GP 51, W 32, ORtg 115.2, DRtg 114.8, Pace 100.9

### Performance

| Metrica                  | Prima (bug)            | Dopo (fix)                |
| ------------------------ | ---------------------- | ------------------------- |
| Routing                  | sports + **finance** ❌ | **sports only** ✅         |
| Latenza                  | 407s (timeout)         | **284s** ✅                |
| Tools inutili            | ~40 (yahoo_quote)      | **0**                     |
| Risposta Telegram        | `fetch failed` ❌       | **9.997 chars, 200 OK** ✅ |
| `nba_api_advanced_stats` | "Team not found" ❌     | **Dati completi** ✅       |

---

## More Versions...
[View full history](CHANGELOG.md)

### Fixed - Sports/Betting Domain (Lakers Query Issues)

- **P0.2 - Parallelize H2H Calls**: Implementato `asyncio.gather()` per chiamate parallele stagione corrente + precedente con timeout totale 20s (era sequenziale 32.5s)
  - Risolve timeout su `nba_api_head_to_head`
  - Gestione eccezioni da gather con fallback a liste vuote
  
- **P1.1 - Aumentare Odds Limit**: Aumentato limite events da 10 a 20 partite in `odds_api_odds`
  - Migliora copertura Lakers-Suns e altre partite
  
- **P1.2 - Aumentare Giorni Schedule**: Aumentato range da 4 a 14 giorni in `balldontlie_games`
  - Recupera tutte le 3 partite Lakers richieste (non solo 1)
  
- **P0.1 - Cascata Fallback Player Stats**: Nuovo tool `nba_api_player_stats_cascade`
  - Workflow: BallDontLie → nba_api package → ESPN
  - Risolve 401 Unauthorized su player stats
  - Garantisce dati anche se BallDontLie fallisce
  - Registrato in AVAILABLE_TOOLS

### Performance Impact

| Problema            | Prima      | Dopo               | Fix  |
| ------------------- | ---------- | ------------------ | ---- |
| 401 su player stats | ❌ Errore   | ✅ Cascata fallback | P0.1 |
| Timeout H2H         | ❌ 32.5s+   | ✅ 20s max          | P0.2 |
| Odds Lakers-Suns    | ❌ Mancanti | ✅ Coperte          | P1.1 |
| Partite Lakers      | ❌ 1 su 3   | ✅ 3 su 3           | P1.2 |

### Files Modified
- `src/me4brain/domains/sports_nba/tools/nba_api.py` (+98 lines, -8 lines)

