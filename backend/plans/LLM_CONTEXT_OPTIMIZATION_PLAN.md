# Piano di Ottimizzazione LLM Context & Resource Management

**Versione**: 1.0
**Data**: 2026-03-14
**Obiettivo**: Gestione efficiente dei modelli LLM locali, del contesto, delle risorse hardware e supporto a query con 50+ tool call
**Target Hardware**: Apple Silicon M1/M2/M3 Pro con 16-64GB RAM unificata

---

## Indice

1. [Analisi dello Stato Attuale](#1-analisi-dello-stato-attuale)
2. [Problemi Identificati](#2-problemi-identificati)
3. [Best Practice SOTA 2026](#3-best-practice-sota-2026)
4. [Piano di Implementazione](#4-piano-di-implementazione)
5. [UI Preferenze PersAn](#5-ui-preferenze-persan)
6. [Roadmap e Priorità](#6-roadmap-e-priorità)

---

## 1. Analisi dello Stato Attuale

### 1.1 Flusso LLM nella Pipeline

Il sistema Me4BrAIn utilizza un'architettura **dual-provider** con **8 punti di chiamata LLM** per ogni query complessa:

```
Query utente
    │
    ▼
┌─────────────────────────────────────────┐
│ 1. UnifiedIntentAnalyzer (LLM call #1)  │  ← Classifica intent: CONVERSATIONAL vs TOOL_REQUIRED
│    Model: qwen3.5-4b-mlx (locale)       │     max_tokens: 20-300, temp: 0.1
│    File: engine/unified_intent_analyzer.py│
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 2. ContextAwareRewriter (LLM call #2)   │  ← Riscrittura follow-up (solo se detected)
│    Model: qwen3.5-4b-mlx (locale)       │     max_tokens: 500, temp: 0.0
│    File: engine/context_rewriter.py      │     Sliding window: 6 turns, 500 chars/turn
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 3. DomainClassifier (LLM call #3)       │  ← Classifica domini (finance, weather, etc.)
│    Model: qwen3.5-4b-mlx (locale)       │     max_tokens: 200, temp: 0.1
│    File: engine/hybrid_router/           │
│          domain_classifier.py            │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 4. QueryDecomposer (LLM call #4)        │  ← Decomposizione multi-intent in sub-query
│    Model: qwen3.5-4b-mlx (locale)       │     max_tokens: 2000, temp: 0.1
│    File: engine/hybrid_router/           │
│          query_decomposer.py             │
└─────────────────────────────────────────┘
    │
    ▼  (Per OGNI sub-query, ciclo ReAct con max 3 iterazioni)
┌─────────────────────────────────────────┐
│ 5. LlamaIndex LLMRerank (LLM call #5)  │  ← Reranking tool dopo vector search
│    Model: qwen3.5-4b-mlx (via adapter)  │     context_window: 32768
│    File: engine/hybrid_router/           │
│          llama_tool_retriever.py         │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 6. _select_tools_for_step (LLM call #6) │  ← LLM seleziona e parametrizza tool
│    Model: qwen3.5-4b-mlx (locale)       │     tool_choice: "auto", temp: 0.1
│    File: engine/iterative_executor.py    │     Budget: 4000 token/step
│    :1857                                 │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 7. _observe_results (LLM call #7)       │  ← ReAct: analizza risultati → SUFFICIENT/RETRY/DEEPER
│    Model: mistral-large-3 (cloud)       │     Fino a 3 iterazioni per step
│    File: engine/iterative_executor.py    │
│    :1211                                 │
└─────────────────────────────────────────┘
    │
    ▼  (Dopo TUTTI gli step)
┌─────────────────────────────────────────┐
│ 8. ResponseSynthesizer (LLM call #8)    │  ← Sintesi finale risposta naturale
│    Model: qwen3.5-4b-mlx (locale)       │     max_tokens: 16384
│    File: engine/synthesizer.py           │     Map-Reduce se >16K chars
└─────────────────────────────────────────┘
```

### 1.2 Crescita del Contesto per Query Complessa (50+ tool call)

**Scenario**: Query multi-dominio con 8 sub-query, 3 iterazioni ReAct per step, 50+ tool.

| Step | Componente | Token Input Stimati | Crescita |
|------|-----------|-------------------|----------|
| 1 | IntentAnalyzer | ~200 | Fisso |
| 2 | ContextRewriter | ~800 | Fisso (sliding 6 turn) |
| 3 | DomainClassifier | ~500 | Fisso |
| 4 | QueryDecomposer | ~1000 | Fisso |
| 5-7 per step 1 | Rerank + Select + Observe | ~6000 | Fisso per step |
| 5-7 per step 2 | Rerank + Select + Observe | ~8000 | +2K context accum. |
| 5-7 per step 3 | Rerank + Select + Observe | ~10000 | +4K context accum. |
| ... | | | |
| 5-7 per step 8 | Rerank + Select + Observe | ~20000 | +14K context accum. |
| 8 | Synthesizer (con Map-Reduce) | ~30000 | Tutti i risultati |
| **Totale stimato** | | **~100K-150K token** | |

**Per Qwen 3.5-4B-MLX con context window 32K, questo SUPERA il limite al 4°-5° step.**

### 1.3 Catena di Chiamate per 50+ Tool Call

```
8 sub-queries × (1 rerank + 1 select + 1 observe) × 3 iterazioni = ~72 LLM calls
+ 4 calls di pipeline (intent + rewrite + classify + decompose)
+ 1 synthesis finale
+ 8 map-reduce summaries (se attivato)
= ~85 chiamate LLM totali
```

Con il modello locale Qwen 3.5-4B su MLX a ~30 tok/s, il tempo stimato è:
- **~85 calls × ~1500 tok/call avg × (1/30 s/tok) ≈ 70+ minuti**
- Questo è **inaccettabile** per UX e risorse hardware.

### 1.4 Stato Attuale Gestione Risorse

| Meccanismo | Stato | File | Limite |
|-----------|-------|------|--------|
| Token budgeting per step | ✅ Presente | iterative_executor.py:1810 | 4000 tok/step |
| Context summary truncation | ✅ Presente | iterative_executor.py:75 | 2000 chars/result |
| Map-Reduce per synthesis | ✅ Presente | synthesizer.py:382 | Soglia 16K chars |
| Result deduplication | ✅ Presente | synthesizer.py:354 | Hash-based |
| Max tools per step | ✅ Presente | iterative_executor.py:189 | 10 tools |
| Max ReAct iterations | ✅ Presente | iterative_executor.py:190 | 3 loops |
| Fallback provider | ✅ Presente | llm/fallback.py | Auto-failover |
| Conversation sliding window | ✅ Presente | context_rewriter.py | 6 turns, 500 ch |
| **GPU/VRAM monitoring** | ❌ Assente | - | - |
| **Context window tracking** | ❌ Assente | - | Nessun tracking vs limit |
| **Compressione contesto inter-step** | ❌ Assente | - | Cresce linearmente |
| **KV cache management** | ❌ Assente | - | Nessun prefix caching |
| **Adaptive model routing** | ❌ Assente | - | Modello fisso per ruolo |
| **Runtime model switching** | ❌ Assente | - | Solo via .env |
| **Memory pressure detection** | ❌ Assente | - | Nessun OOM prevention |
| **UI per configurazione LLM** | ❌ Assente | PersAn | Settings button non wired |

---

## 2. Problemi Identificati

### P1. CRITICO: Context Window Overflow su Modelli Locali Piccoli
- **Qwen 3.5-4B-MLX** ha 32K context window
- `get_context_summary()` accumula linearmente (2000 chars/risultato × N step)
- Al 5° step con risultati ricchi, il contesto supera 16K token → degradazione
- Al 7°-8° step, rischio overflow → output troncato o incoerente
- **Root cause**: Nessun meccanismo di compressione progressiva del contesto accumulato

### P2. CRITICO: Nessun Monitoraggio VRAM/RAM per LLM Locale
- MLX usa la unified memory Apple Silicon
- Nessun tracking di quanta memoria il modello sta usando
- Nessuna soglia di allarme prima dell'OOM
- Il sistema non sa se il modello locale è sovraccarico
- BGE-M3 (embeddings) + Qwen 3.5-4B competono per la stessa RAM

### P3. ALTO: Troppi LLM Round-Trip per Query Complesse
- ~85 chiamate LLM per una query con 50+ tool
- Ogni round-trip aggiunge latenza (anche locale ~500ms-2s per call)
- Molte call sono ridondanti (rerank per ogni step, observe per ogni iterazione)

### P4. ALTO: Token Budget Troppo Rigido e Non Adattivo
- Budget fisso 4000 token/step in `_select_tools_for_step()` (riga 1810)
- Non tiene conto della dimensione del context window del modello attivo
- Non si adatta alla complessità della query o al numero di step rimanenti
- Può causare short-circuit prematuro (return [] se budget esaurito)

### P5. MEDIO: Nessun Prefix/KV Cache per Prompt Ricorrenti
- System prompt identici ripetuti ad ogni step
- Il modello locale non beneficia di prefix caching
- mlx_lm.server supporta prefix caching ma non è configurato/sfruttato

### P6. MEDIO: Assenza UI per Configurazione Modelli LLM
- Tutti i parametri LLM sono in `.env` (richiedono restart)
- Nessuna API per runtime model switching
- L'utente non può:
  - Selezionare il modello attivo
  - Modificare temperatura, max_tokens, context strategy
  - Monitorare l'uso delle risorse
  - Configurare il fallback behavior

### P7. BASSO: Strategia Context Overflow Limitata
- Solo 3 strategie: `map_reduce`, `truncate`, `cloud_fallback`
- Nessuna compressione incrementale autonoma
- Nessuna "anchored summarization" (mantenere ancore critiche mentre si comprime)

---

## 3. Best Practice SOTA 2026

Basandosi sulla ricerca di letteratura e implementazioni production-grade nel 2025-2026:

### 3.1 Autonomous Context Compression (LangChain Deep Agents SDK, Marzo 2026)
- Il modello decide **quando** comprimere (non a soglia fissa)
- Comprime a "momenti naturali" (fine step, inizio nuova sub-query)
- Preserva "ancore" (decisioni chiave, ID critici, errori)
- **85% compaction rate** mantenendo output quality

### 3.2 Anchored Iterative Summarization (Zylos Research, Feb 2026)
- Suddivide il contesto in: **ancore** (mai compresse) + **narrativa** (comprimibile)
- Ancore: system prompt, IDs estratti, constraints, ultima user query
- Narrativa: risultati tool, reasoning intermedio, observation context
- Compressione iterativa: ogni N step, la narrativa viene summarizzata

### 3.3 Token Budget Dinamico (Context Engineering, Comet 2026)
- Budget calcolato come: `context_window × 0.85 - system_prompt_tokens - output_reserve`
- Distribuito proporzionalmente tra gli step
- Step critici (primi e ultimi) ricevono più budget
- Short-circuit informato: se budget insufficiente, usa cloud fallback per quello step

### 3.4 Trajectory Reduction (Zylos Research, Mar 2026)
- Dopo ogni tool call, il risultato viene immediately summarizzato prima di entrare in contesto
- Solo il summary entra nel context chain, non il raw result
- Riduzione 3-5x del contesto per tool call
- "Piggy-backing": la compressione avviene durante il tempo di attesa della tool execution

### 3.5 Tool Design Discipline (Zylos Research, Mar 2026)
- Tool con output trimmed: max 2KB per tool result prima dell'ingresso in contesto
- Negative-use statements nelle descrizioni tool (quando NON usare)
- Grouping e naming coerente per ridurre confusione LLM

### 3.6 KV Cache e Prefix Caching (dasroot.net, Gen 2026)
- Prefix caching per system prompt condivisi → 90% saving sui token iniziali
- mlx_lm.server supporta prefix caching nativamente
- Raggruppare le call con lo stesso system prompt per massimizzare la cache hit

---

## 4. Piano di Implementazione

### Fase 1: Context Management Critico (Settimana 1-2)

#### 1.1 Adaptive Context Compressor
**Priorità**: CRITICA
**File da creare**: `src/me4brain/engine/context_compressor.py`

```python
class AdaptiveContextCompressor:
    """Compressione autonoma del contesto inter-step.
    
    Strategia a 3 livelli:
    1. LIGHT (context < 40% window): solo dedup + truncation
    2. MEDIUM (context 40-70% window): summarize risultati vecchi, mantieni ancore
    3. AGGRESSIVE (context > 70% window): summarize tutto tranne ancore + ultima query
    """
    
    def __init__(self, context_window: int = 32768, output_reserve: int = 4096):
        self.context_window = context_window
        self.output_reserve = output_reserve
        self.effective_budget = int(context_window * 0.85) - output_reserve
        self._anchors: list[str] = []  # IDs, decisioni critiche
        self._compressed_history: str = ""
    
    def estimate_tokens(self, text: str) -> int:
        """Stima veloce: ~4 chars per token per modelli piccoli."""
        return len(text) // 4
    
    def should_compress(self, current_context: str) -> str:
        """Determina livello di compressione necessario."""
        usage = self.estimate_tokens(current_context) / self.effective_budget
        if usage < 0.4:
            return "LIGHT"
        elif usage < 0.7:
            return "MEDIUM"
        else:
            return "AGGRESSIVE"
    
    async def compress(self, exec_context: ExecutionContext, 
                       current_step: int, total_steps: int) -> str:
        """Comprimi il contesto preservando le ancore."""
        ...
```

**Integrazione**: Chiamato in `IterativeExecutor._execute_step()` PRIMA di `_select_tools_for_step()`.

```python
# In iterative_executor.py, _execute_step():
compressed_context = await self._compressor.compress(
    exec_context, step_id, total_steps
)
# Sostituire exec_context.get_context_summary() con compressed_context
```

#### 1.2 Context Window Tracker
**Priorità**: CRITICA
**File da modificare**: `src/me4brain/engine/iterative_executor.py`

Aggiungere tracking esplicito del context window usage:

```python
class ContextWindowTracker:
    """Traccia l'utilizzo del context window in tempo reale."""
    
    def __init__(self, model_context_window: int = 32768):
        self.max_tokens = model_context_window
        self.used_tokens = 0
        self.peak_tokens = 0
        self._history: list[dict] = []
    
    def record(self, component: str, tokens: int):
        self.used_tokens = tokens  # Current usage
        self.peak_tokens = max(self.peak_tokens, tokens)
        self._history.append({"component": component, "tokens": tokens})
    
    @property
    def usage_pct(self) -> float:
        return self.used_tokens / self.max_tokens
    
    @property
    def remaining(self) -> int:
        return self.max_tokens - self.used_tokens
    
    def can_fit(self, additional_tokens: int) -> bool:
        return (self.used_tokens + additional_tokens) < (self.max_tokens * 0.85)
```

#### 1.3 Immediate Result Summarization (Trajectory Reduction)
**Priorità**: ALTA
**File da modificare**: `src/me4brain/engine/iterative_executor.py`

Dopo ogni tool execution, comprimere SUBITO il risultato prima di aggiungerlo all'`ExecutionContext`:

```python
async def _compress_tool_result(self, result: ToolResult, sub_query: str) -> ToolResult:
    """Comprimi il risultato tool mantenendo i dati essenziali.
    
    Regole:
    - Risultati <500 chars: nessuna compressione
    - 500-2000 chars: estrai solo key fields (IDs, nomi, numeri)
    - >2000 chars: LLM summary in max 200 parole (usa modello locale fast)
    """
    data_str = str(result.data)
    if len(data_str) < 500:
        return result
    
    if len(data_str) < 2000:
        # Compressione strutturale: mantieni solo campi chiave
        compressed = self._extract_essential_fields(result.data)
        return ToolResult(
            tool_name=result.tool_name,
            success=result.success,
            data=compressed,
            latency_ms=result.latency_ms,
        )
    
    # Compressione LLM per risultati grandi
    summary = await self._quick_summarize(result, sub_query)
    return ToolResult(
        tool_name=result.tool_name,
        success=result.success,
        data={"_summary": summary, "_key_ids": self._extract_ids(result.data)},
        latency_ms=result.latency_ms,
    )
```

### Fase 2: Resource Management Hardware (Settimana 2-3)

#### 2.1 Hardware Resource Monitor
**Priorità**: ALTA
**File da creare**: `src/me4brain/core/monitoring/resource_monitor.py`

```python
import psutil
import subprocess

class HardwareResourceMonitor:
    """Monitora risorse hardware per LLM locale su Apple Silicon."""
    
    # Soglie di allarme
    MEMORY_WARNING_PCT = 75   # % RAM usata
    MEMORY_CRITICAL_PCT = 90  # % RAM usata → degradazione LLM
    
    async def get_system_stats(self) -> dict:
        """Statistiche sistema in tempo reale."""
        mem = psutil.virtual_memory()
        return {
            "ram_total_gb": mem.total / (1024**3),
            "ram_used_gb": mem.used / (1024**3),
            "ram_available_gb": mem.available / (1024**3),
            "ram_usage_pct": mem.percent,
            "gpu_metal_usage": await self._get_metal_usage(),
            "mlx_process_rss_gb": self._get_mlx_process_memory(),
            "swap_used_gb": psutil.swap_memory().used / (1024**3),
            "cpu_pct": psutil.cpu_percent(interval=0.1),
        }
    
    async def _get_metal_usage(self) -> dict | None:
        """Rileva utilizzo GPU Metal (Apple Silicon)."""
        try:
            # ioreg per Metal GPU stats
            result = subprocess.run(
                ["ioreg", "-r", "-d", "1", "-c", "IOAccelerator"],
                capture_output=True, text=True, timeout=2
            )
            # Parse per VRAM usage
            ...
        except Exception:
            return None
    
    def _get_mlx_process_memory(self) -> float:
        """Memoria usata dal processo mlx_lm.server."""
        for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
            if 'mlx' in proc.info['name'].lower() or 'python' in proc.info['name'].lower():
                cmdline = proc.cmdline()
                if any('mlx_lm' in arg for arg in cmdline):
                    return proc.info['memory_info'].rss / (1024**3)
        return 0.0
    
    def should_use_cloud_fallback(self, stats: dict) -> bool:
        """Determina se il sistema è sotto pressione e serve il cloud."""
        return (
            stats["ram_usage_pct"] > self.MEMORY_CRITICAL_PCT
            or stats["swap_used_gb"] > 2.0  # Swap > 2GB = degradazione
        )
```

#### 2.2 Adaptive Model Router
**Priorità**: ALTA
**File da creare**: `src/me4brain/llm/adaptive_router.py`

```python
class AdaptiveModelRouter:
    """Routing intelligente dei modelli basato su risorse e complessità.
    
    Seleziona automaticamente:
    - Modello locale per query semplici (< 5 tool call)
    - Cloud per query complesse (> 10 tool call) o sotto pressione memoria
    - Mix per query medie (locale per routing, cloud per synthesis)
    """
    
    def __init__(self, resource_monitor: HardwareResourceMonitor):
        self._monitor = resource_monitor
        self._model_profiles = {}  # Caricato da config
    
    async def select_provider(self, query_complexity: str, 
                               component: str) -> tuple[LLMProvider, str]:
        """Seleziona provider e modello ottimale.
        
        Args:
            query_complexity: "simple" | "moderate" | "complex"
            component: "routing" | "tool_selection" | "observation" | "synthesis"
        """
        stats = await self._monitor.get_system_stats()
        
        # Se risorse critiche: SEMPRE cloud
        if self._monitor.should_use_cloud_fallback(stats):
            return self._cloud_provider, self._cloud_model
        
        # Routing per complessità
        if query_complexity == "simple":
            return self._local_provider, self._local_model
        
        if query_complexity == "complex":
            # Componenti leggeri locali, pesanti cloud
            if component in ("routing", "tool_selection"):
                return self._local_provider, self._local_model
            else:
                return self._cloud_provider, self._cloud_model
        
        # Moderate: tutto locale con fallback
        return self._fallback_provider, self._local_model
```

#### 2.3 Memory Pressure Circuit Breaker
**Priorità**: ALTA
**File da modificare**: `src/me4brain/llm/fallback.py`

Estendere il `FallbackProvider` con memory pressure detection:

```python
class ResourceAwareFallbackProvider(FallbackProvider):
    """FallbackProvider che monitora le risorse prima di ogni call."""
    
    def __init__(self, primary, fallback, resource_monitor, **kwargs):
        super().__init__(primary, fallback, **kwargs)
        self._monitor = resource_monitor
        self._consecutive_local_failures = 0
        self._cooldown_until = 0  # timestamp
    
    async def generate_response(self, request: LLMRequest) -> LLMResponse:
        # Check memory pressure PRIMA di chiamare il modello locale
        if await self._should_skip_local():
            return await self.fallback.generate_response(
                self._get_fallback_request(request)
            )
        
        try:
            response = await super().generate_response(request)
            self._consecutive_local_failures = 0
            return response
        except Exception:
            self._consecutive_local_failures += 1
            if self._consecutive_local_failures >= 3:
                self._cooldown_until = time.time() + 60  # 1 min cooldown
            raise
```

### Fase 3: Ottimizzazione Pipeline per 50+ Tool Call (Settimana 3-4)

#### 3.1 Step Merging e Parallelizzazione Intelligente
**Priorità**: ALTA
**File da modificare**: `src/me4brain/engine/iterative_executor.py`

Per query con 8+ sub-query, raggruppare step indipendenti ed eseguirli in parallelo:

```python
async def _plan_execution_order(self, sub_queries: list[SubQuery]) -> list[list[SubQuery]]:
    """Pianifica l'ordine di esecuzione: step indipendenti in parallelo.
    
    Esempio: "meteo Roma + prezzo Bitcoin + ultimi email"
    → Batch 1: [meteo, bitcoin, email] (tutti indipendenti, esecuzione parallela)
    
    Esempio: "cerca file report → leggilo → crea riassunto"
    → Batch 1: [cerca file]
    → Batch 2: [leggi file] (dipende da batch 1)
    → Batch 3: [crea riassunto] (dipende da batch 2)
    """
    # Analisi dipendenze tra sub-query
    independent_batches = self._detect_dependencies(sub_queries)
    return independent_batches
```

#### 3.2 Lazy Observation (Skip Observe per Risultati Ovvi)
**Priorità**: MEDIA
**File da modificare**: `src/me4brain/engine/iterative_executor.py`

Eliminare la chiamata LLM `_observe_results()` quando i risultati sono chiaramente sufficienti:

```python
async def _smart_observe(self, step_id, sub_query, tool_results, tools, iteration):
    """Observation intelligente: evita LLM call per casi ovvi.
    
    Fast-path (NO LLM):
    - Tutti i tool hanno successo E restituiscono dati non-vuoti → SUFFICIENT
    - Tutti i tool falliscono con errore di rete → RETRY (se iteration < max)
    - Query semplice (singolo tool, singolo dominio) → SUFFICIENT se dati presenti
    
    LLM observation (solo per casi ambigui):
    - Mix di successi e fallimenti
    - Risultati presenti ma potenzialmente incompleti
    - DEEPER necessario (richiede analisi semantica)
    """
    # Fast-path: tutti successo con dati
    successful = [r for r in tool_results if r.success and r.data and not self._is_empty(r.data)]
    if len(successful) == len(tool_results) and len(successful) > 0:
        return {"decision": "SUFFICIENT", "reason": "All tools returned data"}
    
    # Fast-path: tutti vuoti
    if all(not r.success or self._is_empty(r.data) for r in tool_results):
        if iteration < self.MAX_OBSERVE_ITERATIONS - 1:
            return {"decision": "RETRY", "reason": "All tools returned empty", "retry_hint": "..."}
        return {"decision": "SUFFICIENT", "reason": "Max retries reached"}
    
    # Caso ambiguo: usa LLM
    return await self._observe_results(step_id, sub_query, tool_results, tools, iteration)
```

#### 3.3 Prefix Caching per System Prompt
**Priorità**: MEDIA
**File da modificare**: `src/me4brain/llm/ollama.py`

Sfruttare il prefix caching di mlx_lm.server:

```python
class OllamaClient(LLMProvider):
    def __init__(self, ...):
        ...
        self._system_prompt_cache: dict[str, str] = {}  # hash → cached prompt
    
    def _prepare_payload(self, request: LLMRequest) -> dict:
        payload = ...
        
        # Attiva prefix caching per system prompt ripetuti
        # mlx_lm.server mantiene la KV cache del prefix tra le call
        # Ordinare i messaggi con system prompt stabile all'inizio
        # massimizza il cache hit rate
        if request.messages and request.messages[0].role == "system":
            payload["cache_prompt"] = True  # Flag per prefix caching
        
        return payload
```

#### 3.4 Batch LLM Calls (Call Merging)
**Priorità**: MEDIA
**File da creare**: `src/me4brain/llm/batch_scheduler.py`

Per step indipendenti, inviare batch requests più grandi invece di molte piccole:

```python
class LLMBatchScheduler:
    """Raggruppa chiamate LLM indipendenti in batch per efficienza.
    
    Invece di:
      call1 → wait → call2 → wait → call3 → wait
    
    Fa:
      [call1, call2, call3] → wait_all (concorrenti su provider diversi)
    """
    
    async def batch_generate(self, requests: list[LLMRequest]) -> list[LLMResponse]:
        """Esegui richieste indipendenti in parallelo."""
        tasks = [self._provider.generate_response(r) for r in requests]
        return await asyncio.gather(*tasks, return_exceptions=True)
```

### Fase 4: API Backend per Configurazione Runtime (Settimana 4-5)

#### 4.1 LLM Configuration API
**Priorità**: ALTA
**File da creare**: `src/me4brain/api/routes/llm_config.py`

```python
router = APIRouter(prefix="/v1/config/llm", tags=["LLM Configuration"])

class LLMConfigUpdate(BaseModel):
    """Parametri LLM modificabili a runtime."""
    model_primary: str | None = None
    model_routing: str | None = None
    model_synthesis: str | None = None
    model_fallback: str | None = None
    use_local_tool_calling: bool | None = None
    context_overflow_strategy: Literal["map_reduce", "truncate", "cloud_fallback"] | None = None
    default_temperature: float | None = Field(None, ge=0.0, le=2.0)
    default_max_tokens: int | None = Field(None, ge=64, le=32768)
    context_window_size: int | None = Field(None, ge=2048, le=131072)

class LLMModelInfo(BaseModel):
    """Informazioni su un modello disponibile."""
    id: str
    name: str
    provider: str  # "local" | "cloud"
    context_window: int
    supports_tools: bool
    supports_vision: bool
    quantization: str | None = None
    vram_required_gb: float | None = None

@router.get("/models")
async def list_available_models() -> list[LLMModelInfo]:
    """Lista modelli disponibili (locali + cloud)."""
    models = []
    
    # Modelli locali da mlx_lm.server / LM Studio
    local_models = await _discover_local_models()
    models.extend(local_models)
    
    # Modelli cloud da NanoGPT
    cloud_models = _get_cloud_models()
    models.extend(cloud_models)
    
    return models

@router.get("/current")
async def get_current_config() -> LLMConfigResponse:
    """Configurazione LLM corrente."""
    config = get_llm_config()
    return LLMConfigResponse(
        model_primary=config.model_primary,
        model_routing=config.model_routing,
        model_synthesis=config.model_synthesis,
        use_local=config.use_local_tool_calling,
        context_overflow_strategy=config.context_overflow_strategy,
        context_window=32768,  # Dal profilo del modello
    )

@router.put("/update")
async def update_llm_config(update: LLMConfigUpdate) -> LLMConfigResponse:
    """Aggiorna configurazione LLM a runtime (senza restart).
    
    NOTA: Modifica solo la configurazione in-memory.
    Per persistere, scrivi anche su .env.
    """
    ...

@router.get("/status")
async def get_llm_status() -> LLMStatusResponse:
    """Stato runtime dei provider LLM."""
    return {
        "local": {
            "available": await _check_local_server(),
            "model_loaded": "qwen3.5-4b-mlx",
            "inference_speed_tps": await _benchmark_local(),
        },
        "cloud": {
            "available": await _check_cloud_api(),
            "credits_remaining": await _check_credits(),
        },
        "resources": await resource_monitor.get_system_stats(),
    }
```

#### 4.2 Resource Monitoring API
**Priorità**: ALTA
**File da modificare**: `src/me4brain/api/routes/monitoring.py`

Aggiungere endpoint per risorse hardware:

```python
@router.get("/v1/monitoring/resources")
async def get_resource_stats():
    """Statistiche risorse hardware in tempo reale."""
    monitor = HardwareResourceMonitor()
    stats = await monitor.get_system_stats()
    return {
        "hardware": stats,
        "llm_context": {
            "current_usage_pct": context_tracker.usage_pct,
            "peak_usage_pct": context_tracker.peak_tokens / context_tracker.max_tokens,
            "total_tokens_processed": iterative_executor._total_tokens_used,
        },
        "recommendations": _get_recommendations(stats),
    }
```

#### 4.3 Runtime Config Storage (Redis)
**Priorità**: MEDIA
**File da creare**: `src/me4brain/config/runtime_config.py`

```python
class RuntimeConfigStore:
    """Persistenza configurazione runtime in Redis.
    
    Priorità di lettura:
    1. Redis (runtime override)
    2. Environment variables (.env)
    3. Default values
    """
    
    REDIS_PREFIX = "me4brain:config:"
    
    async def get(self, key: str) -> Any:
        """Leggi valore con fallback chain."""
        # 1. Redis override
        value = await self._redis.get(f"{self.REDIS_PREFIX}{key}")
        if value is not None:
            return json.loads(value)
        
        # 2. Environment variable
        env_value = os.environ.get(key)
        if env_value is not None:
            return env_value
        
        # 3. Default
        return self._defaults.get(key)
    
    async def set(self, key: str, value: Any, persist: bool = False):
        """Imposta valore runtime. Se persist=True, aggiorna anche .env."""
        await self._redis.set(f"{self.REDIS_PREFIX}{key}", json.dumps(value))
        
        if persist:
            self._update_env_file(key, value)
```

### Fase 5: UI Preferenze PersAn (Settimana 5-7)

Vedere sezione 5 dedicata.

### Fase 6: Ottimizzazioni Avanzate (Settimana 7-8)

#### 6.1 Model Profiles Registry
**File da creare**: `src/me4brain/llm/model_profiles.py`

```python
MODEL_PROFILES = {
    "qwen3.5-4b-mlx": {
        "context_window": 32768,
        "max_output": 4096,
        "supports_tools": True,
        "supports_vision": False,
        "vram_gb": 3.5,
        "speed_tps": 30,  # tokens/sec su M1 Pro
        "recommended_for": ["routing", "extraction", "tool_selection"],
        "not_recommended_for": ["synthesis_complex", "vision"],
    },
    "mistralai/mistral-large-3-675b-instruct-2512": {
        "context_window": 131072,
        "max_output": 16384,
        "supports_tools": True,
        "supports_vision": False,
        "vram_gb": None,  # Cloud
        "speed_tps": 80,
        "recommended_for": ["synthesis", "reasoning", "complex_observation"],
        "not_recommended_for": [],
    },
    # ... altri modelli
}
```

#### 6.2 Smart Context Window Allocation
```python
class SmartContextAllocator:
    """Alloca il context window budget tra i componenti.
    
    Per un modello con 32K context:
    - System prompt: 2K (fisso, cached)
    - Previous context (compresso): max 8K (adattivo)
    - Current step tools: max 4K
    - User query + extra context: max 2K
    - Output reserve: 4K
    - Safety margin: 2K
    = 22K utilizzabili / 32K
    
    Per 50+ tool call con 8 step:
    - Step 1-2: context compresso 2K
    - Step 3-4: context compresso 4K
    - Step 5-6: context compresso 6K (con aggressive compression)
    - Step 7-8: context compresso 8K (max, ancore only)
    """
    ...
```

---

## 5. UI Preferenze PersAn

### 5.1 Architettura

Il pulsante Settings esiste già in `PersAn/frontend/src/components/layout/Header.tsx` (riga 79) ma non è collegato. La proposta è creare un pannello Settings accessibile da quel pulsante.

```
PersAn Frontend (Next.js, porta 3020)
    │
    ▼
PersAn Gateway (Fastify, porta 3030)
    │
    ▼
Me4BrAIn API (FastAPI, porta 8089)
    ├── GET  /v1/config/llm/models      → Lista modelli disponibili
    ├── GET  /v1/config/llm/current      → Config corrente
    ├── PUT  /v1/config/llm/update       → Aggiorna config runtime
    ├── GET  /v1/config/llm/status       → Stato provider + risorse
    ├── GET  /v1/monitoring/resources     → Stats hardware real-time
    └── GET  /v1/config/preferences      → Preferenze utente
```

### 5.2 Struttura UI Settings Panel

```
┌──────────────────────────────────────────────────────────┐
│  ⚙️ Impostazioni                                    [X]  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  📑 Tab:  [Modelli LLM] [Risorse] [Avanzate]           │
│                                                          │
│  ═══════════════════════════════════════════════════════  │
│                                                          │
│  🤖 MODELLO PRIMARIO                                    │
│  ┌─────────────────────────────────┐                    │
│  │ qwen3.5-4b-mlx (Locale)    ▼   │                    │
│  └─────────────────────────────────┘                    │
│  Context: 32K • Speed: ~30 tok/s • VRAM: 3.5GB         │
│                                                          │
│  🎯 MODELLO ROUTING                                     │
│  ┌─────────────────────────────────┐                    │
│  │ qwen3.5-4b-mlx (Locale)    ▼   │                    │
│  └─────────────────────────────────┘                    │
│                                                          │
│  📝 MODELLO SINTESI                                     │
│  ┌─────────────────────────────────┐                    │
│  │ qwen3.5-4b-mlx (Locale)    ▼   │                    │
│  └─────────────────────────────────┘                    │
│                                                          │
│  🔄 MODELLO FALLBACK                                    │
│  ┌─────────────────────────────────┐                    │
│  │ mistral-large-3 (Cloud)     ▼   │                    │
│  └─────────────────────────────────┘                    │
│                                                          │
│  ─────────────────────────────────────────────────────── │
│                                                          │
│  ⚡ PARAMETRI                                            │
│                                                          │
│  Temperatura:     [====●=========] 0.3                  │
│  Max Tokens:      [========●=====] 8192                 │
│  Context Window:  [========●=====] 32768                │
│                                                          │
│  ─────────────────────────────────────────────────────── │
│                                                          │
│  🔧 STRATEGIA OVERFLOW                                   │
│  ○ Map-Reduce (Raccomandato per locale)                 │
│  ○ Truncate (Più veloce, meno accurato)                 │
│  ○ Cloud Fallback (Usa cloud se context pieno)          │
│                                                          │
│  ─────────────────────────────────────────────────────── │
│                                                          │
│  🏠 PREFERENZA PROVIDER                                  │
│  [✓] Usa modello locale quando possibile                │
│  [✓] Fallback automatico su cloud                       │
│  [ ] Forza solo cloud                                    │
│                                                          │
│                              [Ripristina Default] [Salva]│
└──────────────────────────────────────────────────────────┘
```

### Tab Risorse:
```
┌──────────────────────────────────────────────────────────┐
│  📊 RISORSE SISTEMA (aggiornamento ogni 5s)              │
│                                                          │
│  RAM Totale:    64 GB                                    │
│  RAM Usata:     [████████████░░░░] 48.2 GB (75%)        │
│  RAM Disponib.: 15.8 GB                                  │
│                                                          │
│  GPU Metal:     [██████░░░░░░░░░░] 12.4 GB (38%)        │
│  MLX Process:   3.8 GB                                   │
│  BGE-M3:        0.8 GB                                   │
│                                                          │
│  ─────────────────────────────────────────────────────── │
│                                                          │
│  📈 CONTEXT WINDOW USAGE (sessione corrente)             │
│                                                          │
│  Corrente:      [████████░░░░░░░░] 52%                  │
│  Picco:         [████████████░░░░] 78%                  │
│  Token totali:  23,456                                   │
│                                                          │
│  ─────────────────────────────────────────────────────── │
│                                                          │
│  📊 STATISTICHE SESSIONE                                 │
│  Chiamate LLM:       42                                  │
│  Tool eseguiti:      28                                  │
│  Token consumati:    85,230                              │
│  Tempo inferenza:    45.2s                               │
│  Fallback cloud:     3                                   │
│                                                          │
│  ⚠️ AVVISI                                               │
│  ┌─────────────────────────────────────────────────────┐ │
│  │ ⚠ RAM al 75% - prestazioni possono degradare       │ │
│  │    se supera 85%                                    │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### 5.3 Componenti PersAn da Creare

| Componente | File | Descrizione |
|-----------|------|-------------|
| `SettingsPanel` | `components/settings/SettingsPanel.tsx` | Panel principale con tabs |
| `LLMModelsTab` | `components/settings/LLMModelsTab.tsx` | Selezione modelli e parametri |
| `ResourcesTab` | `components/settings/ResourcesTab.tsx` | Monitoring risorse real-time |
| `AdvancedTab` | `components/settings/AdvancedTab.tsx` | Feature flags, overflow strategy |
| `ModelSelector` | `components/settings/ModelSelector.tsx` | Dropdown selezione modello |
| `ResourceGauge` | `components/settings/ResourceGauge.tsx` | Barra uso risorse |
| `useSettings` | `hooks/useSettings.ts` | Hook per API settings |
| `useResources` | `hooks/useResources.ts` | Hook polling risorse (5s) |
| `settingsStore` | `stores/useSettingsStore.ts` | Zustand store per settings |

### 5.4 Wiring del Pulsante Settings Esistente

In `Header.tsx` (riga 79-84), collegare il pulsante al panel:

```tsx
// Header.tsx
import { useSettingsStore } from '@/stores/useSettingsStore';

// Nel componente:
const { openSettings } = useSettingsStore();

<button 
  className="btn-icon w-9 h-9" 
  title="Impostazioni"
  onClick={openSettings}
>
  <Settings size={18} />
</button>
```

### 5.5 Gateway Endpoints (PersAn Fastify)

Aggiungere proxy endpoints nel gateway PersAn per le nuove API:

```typescript
// gateway/src/routes/config.ts
fastify.get('/api/config/llm/models', async (req, reply) => {
  const response = await fetch(`${ME4BRAIN_URL}/v1/config/llm/models`);
  return response.json();
});

fastify.put('/api/config/llm/update', async (req, reply) => {
  const response = await fetch(`${ME4BRAIN_URL}/v1/config/llm/update`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req.body),
  });
  return response.json();
});

fastify.get('/api/monitoring/resources', async (req, reply) => {
  const response = await fetch(`${ME4BRAIN_URL}/v1/monitoring/resources`);
  return response.json();
});
```

---

## 6. Roadmap e Priorità

### Fase 1 — CRITICO (Settimana 1-2): Context Management
| # | Task | Impatto | Effort | File Principali |
|---|------|---------|--------|----------------|
| 1.1 | AdaptiveContextCompressor | Risolve P1 (overflow) | 3 giorni | engine/context_compressor.py (nuovo) |
| 1.2 | ContextWindowTracker | Risolve P1 (visibilità) | 1 giorno | engine/iterative_executor.py |
| 1.3 | Immediate Result Summarization | Riduce contesto 3-5x | 2 giorni | engine/iterative_executor.py |
| 1.4 | Model Profiles Registry | Foundation per tutto | 1 giorno | llm/model_profiles.py (nuovo) |

### Fase 2 — ALTO (Settimana 2-3): Resource Management
| # | Task | Impatto | Effort | File Principali |
|---|------|---------|--------|----------------|
| 2.1 | HardwareResourceMonitor | Risolve P2 (VRAM) | 2 giorni | core/monitoring/resource_monitor.py (nuovo) |
| 2.2 | AdaptiveModelRouter | Risolve P3 (routing) | 2 giorni | llm/adaptive_router.py (nuovo) |
| 2.3 | ResourceAwareFallback | Risolve P2 (OOM prevent) | 1 giorno | llm/fallback.py |
| 2.4 | Resource Monitoring API | Espone metriche | 1 giorno | api/routes/monitoring.py |

### Fase 3 — ALTO (Settimana 3-4): Pipeline 50+ Tool
| # | Task | Impatto | Effort | File Principali |
|---|------|---------|--------|----------------|
| 3.1 | Step Merging (parallelismo) | Riduce tempo 2-3x | 3 giorni | engine/iterative_executor.py |
| 3.2 | Smart Observation (skip LLM) | Elimina ~30% LLM calls | 1 giorno | engine/iterative_executor.py |
| 3.3 | Prefix Caching config | Riduce latenza 30-50% | 1 giorno | llm/ollama.py |
| 3.4 | Dynamic Token Budget | Risolve P4 (budget) | 2 giorni | engine/iterative_executor.py |

### Fase 4 — MEDIO (Settimana 4-5): API Backend Config
| # | Task | Impatto | Effort | File Principali |
|---|------|---------|--------|----------------|
| 4.1 | LLM Configuration API | Prerequisito per UI | 2 giorni | api/routes/llm_config.py (nuovo) |
| 4.2 | RuntimeConfigStore (Redis) | Persistenza runtime | 1 giorno | config/runtime_config.py (nuovo) |
| 4.3 | Model Discovery API | Lista modelli locali | 1 giorno | api/routes/llm_config.py |
| 4.4 | Resource Stats API | Metriche per UI | 1 giorno | api/routes/monitoring.py |

### Fase 5 — MEDIO (Settimana 5-7): UI PersAn
| # | Task | Impatto | Effort | File Principali |
|---|------|---------|--------|----------------|
| 5.1 | SettingsPanel + Tabs | UI base | 2 giorni | PersAn/components/settings/ |
| 5.2 | LLMModelsTab (model selection) | Core UX | 2 giorni | PersAn/components/settings/ |
| 5.3 | ResourcesTab (monitoring) | Visibilità risorse | 2 giorni | PersAn/components/settings/ |
| 5.4 | AdvancedTab (strategies) | Power users | 1 giorno | PersAn/components/settings/ |
| 5.5 | Zustand store + hooks | State management | 1 giorno | PersAn/stores/ + hooks/ |
| 5.6 | Gateway proxy endpoints | Routing | 1 giorno | PersAn/gateway/src/routes/ |
| 5.7 | Wiring bottone Settings | Collegamento finale | 0.5 giorni | PersAn/components/layout/ |

### Fase 6 — BASSO (Settimana 7-8): Ottimizzazioni Avanzate
| # | Task | Impatto | Effort | File Principali |
|---|------|---------|--------|----------------|
| 6.1 | Batch LLM Calls | Riduce overhead | 2 giorni | llm/batch_scheduler.py (nuovo) |
| 6.2 | VRAM limit tuning (sysctl) | Più memoria per LLM | 0.5 giorni | scripts/tune_vram.sh |
| 6.3 | Autonomous Compression Trigger | LLM decide quando | 2 giorni | engine/context_compressor.py |
| 6.4 | Context Usage SSE Events | Real-time nel frontend | 1 giorno | engine/core.py + PersAn |

---

## Metriche di Successo

| Metrica | Stato Attuale | Obiettivo |
|---------|--------------|-----------|
| Max step prima di overflow (32K ctx) | ~5 step | 15+ step |
| LLM calls per query 50-tool | ~85 | 30-40 |
| Tempo query complessa (8 sub-query) | ~70 min | <15 min |
| Context crescita per step | ~2K-4K token | <500 token (compresso) |
| OOM crashes su query lunghe | Non monitorato | 0 (con fallback) |
| Configurazione modelli | Solo .env (restart) | UI real-time |
| Visibilità risorse hardware | Nessuna | Dashboard real-time |

---

## Note Implementative

### Compatibilità Retroattiva
- Tutte le modifiche devono essere retrocompatibili
- I default devono mantenere il comportamento attuale
- Feature flags per attivare gradualmente le nuove funzionalità

### Testing
- Unit test per `AdaptiveContextCompressor` con input a diverse dimensioni  
- Integration test per pipeline completa con mock LLM
- Load test con 50+ tool call simulati
- Memory pressure test con `stress-ng` per validare il fallback

### Dipendenze
- `psutil` (già presente) per monitoring RAM/CPU
- Nessuna nuova dipendenza Python necessaria per Fase 1-4
- PersAn: nessuna nuova dipendenza npm per Fase 5

---

*Elaborato da analisi codebase completa di Me4BrAIn + PersAn + ricerca SOTA 2026*
