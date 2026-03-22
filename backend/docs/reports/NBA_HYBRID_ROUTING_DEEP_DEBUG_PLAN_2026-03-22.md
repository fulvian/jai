# Me4BrAIn Hybrid Routing Deep Debug Report & Implementation Plan (No-Code Phase)

**Data analisi**: 2026-03-22 01:08–01:15 CET  
**Ambito**: Query complessa multi-intent NBA betting  
**Vincolo rispettato**: nessuna modifica al codice applicata in questa fase

---

## 1) Executive summary

La failure principale **non è nel domain routing** (che funziona), ma nella catena LLM/model provisioning tra Stage 1/1b/3:

1. `sports_nba` viene classificato correttamente (fallback keyword), ma con `used_fallback=False` (telemetria fuorviante).
2. Decomposition fallisce e torna query originale quando il modello non è disponibile.
3. Tool retrieval funziona e recupera tool NBA corretti (18 tool, payload ok).
4. Stage 3 (tool selection LLM) fallisce per modello non disponibile (`qwen3.5-9b-mlx` in LM Studio/Ollama), quindi **0 tool eseguiti**.
5. Di conseguenza la synthesis non è realmente il blocco root in questo repro: non viene raggiunta in modo utile perché non ci sono risultati tool.
6. `nba_betting_odds` HTTP 401 è stato riprodotto e la causa root è **OUT_OF_USAGE_CREDITS** (quota esaurita), non formato auth errato.

---

## 2) Evidenze verificate (run reale)

### 2.1 Trace routing full pipeline

Fonte: `/Users/fulvio/.local/share/kilo/tool-output/tool_d12e5098d001SeUpD3lOU0I5U9`

- Stage 1 classifier:
  - `domain_classification_failed` su `qwen3.5-9b-mlx` (`lmstudio_model_not_found`)
  - output fallback: `domains=['sports_nba']`, `confidence=0.6`
- Stage 1b decomposer:
  - `query_decomposition_failed` (stesso motivo modello)
  - fallback single subquery = query originale
- Stage 2 retriever:
  - `tools_retrieved=18`, `payload_bytes=7919`, dominio `sports_nba`
- Stage 3 selection:
  - `execution_tool_selection_failed` (modello non disponibile)
  - `tools_selected=[]`
- Engine output:
  - `engine_no_tools_selected`
  - risposta fallback utente

### 2.2 Test diretto classifier/decomposer

- `test_classifier.py` con `HybridRouterConfig()` default:
  - tenta `model=default` → fail model autoload
  - ritorna fallback keyword su `sports_nba`
- `test_decomposer.py` con default:
  - stesso fail model `default`
  - ritorna 1 subquery fallback
- decomposer con modello disponibile `qwen3.5:4b`:
  - produce 2 sub-query corrette (NBA data + context data)

### 2.3 Verifica 401 The Odds API

Test HTTP reale con key da `.env`:

- status: `401`
- body: `{"error_code":"OUT_OF_USAGE_CREDITS"...}`
- header: `x-requests-used=498`, `x-requests-remaining=2`

Conclusione: auth format accettato, ma piano quota esaurito.

---

## 3) Root cause report per criticità

## Criticità 1 — Model configuration inconsistency

### Problema esatto

1. `HybridRouterConfig` ha default hardcoded invalidi:
   - `router_model="default"`
   - `execution_model_default="default"`
   - `decomposition_model="default"`
   - file: `src/me4brain/engine/hybrid_router/types.py:148,164,179`

2. `QueryDecomposer` usa `self._config.router_model` invece di `decomposition_model`:
   - file: `src/me4brain/engine/hybrid_router/query_decomposer.py:239`

3. Override modelli avviene solo nella factory engine (`ToolCallingEngine._create_with_hybrid_routing`) ma non è garantito in harness/test custom:
   - file: `src/me4brain/engine/core.py:379-383`

### Impatto quantificato

- In harness e test diretti: fallimento immediato LLM (model `default` inesistente).
- In engine reale: modello routing configurato (`qwen3.5-9b-mlx`) ma provider target (LM Studio) senza modelli caricati; Stage 1/1b/3 falliscono.

### Soluzione proposta

1. Implementare `HybridRouterConfig.__post_init__()` che legge env/config (`LLM_ROUTING_MODEL`, `LLM_SYNTHESIS_MODEL`, fallback sensati).
2. In `QueryDecomposer`, usare `decomposition_model` dedicato.
3. Introdurre `resolve_model_availability()` preflight per ogni stage, con fallback deterministico:
   - routing/decomposition: `qwen3.5:4b` se modello primario non disponibile.
4. Allineare stage-LLM selection all’effettivo provider con modelli disponibili (Ollama tags vs LM Studio IDs).

### Test di verifica fix

- Unit: config init senza parametri espliciti non deve mai produrre `default`.
- Integration: con LM Studio vuoto + Ollama disponibile, stage 1/1b/3 devono usare modello fallback funzionante.

---

## Criticità 2 — Incomplete keyword detection

### Problema esatto

Fallback map per `sports_nba` contiene:
- `"scommessa"`, `"pronostico"`, `"odds"`

Mancano:
- `"scommesse"` (plurale), `"betting"`, `"value bet"`, `"spread"`, `"over/under"`

File: `src/me4brain/engine/hybrid_router/domain_classifier.py:293`

### Impatto quantificato

Con fallback attivo:
- `"scommesse"` → `web_search` (errato)
- `"betting"` → `web_search` (errato)
- `"migliori betting lines nba"` funziona solo perché contiene `nba`

### Soluzione proposta

Espandere keyword map con varianti IT/EN, singolare/plurale e pattern betting.

### Test di verifica fix

Unit table-driven (almeno 25 casi solo betting keyword):
- positive (sports_nba), negative (finance_crypto/web_search), mixed queries.

---

## Criticità 3 — Query decomposer fallback broken

### Problema esatto

Qualsiasi errore LLM/parse produce fallback a query originale come singola sub-query:
- file: `src/me4brain/engine/hybrid_router/query_decomposer.py:246-263, 279-294`

Inoltre usa `router_model` invece di `decomposition_model`.

### Impatto quantificato

- Query multi-intent passa intera al retriever → perdita di precisione su intent-specific retrieval.
- Nel trace: `sub_query_count=1` fallback.

### Soluzione proposta

1. Heuristic fallback decomposer (deterministico) quando LLM fallisce:
   - split per connettivi (`e`, `poi`, `then`, `inoltre`) + intent lexicon.
2. Se dominio unico sports_nba + betting markers: generare minimo 2-3 subquery predefinite (games/odds/context).
3. Mettere guardrail sul parse markdown-fenced JSON (` ```json ... ``` `).

### Test di verifica fix

- Unit: parse robusto per fenced JSON, quote sporche, output parziale.
- Integration: query target deve produrre >=2 subquery anche senza LLM.

---

## Criticità 4 — `nba_betting_odds` HTTP 401

### Problema esatto

La chiamata usa query param `apiKey` (corretto), ma la key ha quota esaurita:
- risposta API: `OUT_OF_USAGE_CREDITS`.

File tool: `src/me4brain/domains/sports_nba/tools/nba_api.py:523-560`

### Impatto quantificato

- Intera catena betting odds fallisce sempre finché quota non ripristinata.
- betting analyzer perde un segnale chiave (odds market data).

### Soluzione proposta

1. Gestire esplicitamente error_code (`OUT_OF_USAGE_CREDITS`) con messaggio actionable.
2. Fallback automatico a `nba_polymarket_odds` e/o feed gratuiti.
3. Health-check startup API credits + alerting.

### Test di verifica fix

- Integration con mock 401 `OUT_OF_USAGE_CREDITS`:
  - sistema non crasha
  - fallback odds source attivo
  - synthesis riceve disclaimer dati incompleti.

---

## Criticità 5 — Tool retrieval & synthesis unknowns

### Stato osservato (ora non più unknown per il repro)

- Tool retriever seleziona correttamente tool sports_nba (18).
- Payload size adeguato (`~7.9KB`).
- Blocco reale è Stage 3 LLM selection (model unavailable), non Stage 2.

### Synthesis

Nel repro corrente, synthesis non è il root blocker: senza tool risultati, engine ritorna risposta no-tools.

---

## 4) Piano organico di risoluzione / implementazione (da delegare)

## Fase A — Strumentazione osservabile (prima di fix)

1. **Structured trace contract** per stage 0/1/1b/2/3/synthesis con campi obbligatori:
   - `model_requested`, `provider_resolved`, `model_effective`
   - `fallback_trigger`, `fallback_reason`
   - `duration_ms`, `error_code`, `error_message`
2. **Debug harness unico** che serializza trace JSON a file timestampato.
3. **Correlation ID** per query end-to-end.

Snippet target (esempio logging):

```python
logger.info(
    "stage_trace",
    stage="stage1b",
    model_requested=config.decomposition_model,
    model_effective=actual_model,
    provider=provider_name,
    duration_ms=duration,
    fallback=fallback_applied,
)
```

## Fase B — Fix core routing

1. **Config hardening**
   - eliminare default `"default"` runtime in tutti i campi modello
   - `__post_init__` + validazione modello disponibile.
2. **Decomposer model separation**
   - usare `decomposition_model`.
3. **Fallback decomposition deterministica**
   - mai ritornare raw query se query complessa multi-intent.
4. **Classifier fallback keyword expansion**
   - betting lexicon completo IT/EN.
5. **`used_fallback` semantics fix**
   - distinguere `llm_fallback_used` vs `fallback_domains_appended`.

## Fase C — Odds resiliency

1. Parse esplicito errori Odds API.
2. Fallback chain: TheOdds -> Polymarket -> no-odds disclaimer.
3. Quota monitor.

## Fase D — Validation

1. Test isolati per ogni fix.
2. Full e2e query target.
3. Regression su altri domini.

---

## 5) Test suite completa proposta (target 85%+)

## Unit tests (>= 50)

- `domain_classifier` (20)
  - keyword variants, ambiguity, fallback semantics.
- `query_decomposer` (15)
  - llm success/fail, fenced json, heuristic fallback.
- `model_resolution` (10)
  - provider/model availability matrix.
- `odds_api_adapter` (10)
  - 200, 401 credits, 429, timeout, malformed.

## Integration tests (>= 20)

- full stage trace assertions (8)
- multi-intent NBA routing (6)
- fallback path with missing models (6)

## E2E (>= 10)

- 5 query complesse sports_nba
- 5 cross-domain query (sports+web/finance/etc.)

## Coverage

- target 85% su package `engine/hybrid_router` + `sports_nba/tools`.

---

## 6) Risposte esplicite alle 6 domande richieste

1. **Quale esattamente è la causa ROOT di `nba_betting_odds` 401?**  
   **Quota API esaurita** (`OUT_OF_USAGE_CREDITS`), non formato header/param errato.

2. **Quando esattamente avviene fallback keyword detection nel classifier?**  
   Nel `classify()` quando la chiamata LLM fallisce (timeout/eccezione/parse JSON fallito) e viene invocato `_fallback_classification()` (`domain_classifier.py:247+`).

3. **Quale modello LLM viene effettivamente usato in cada stage? (trace)**  
   - Stage0 intent analyzer: `qwen3.5:4b` (Ollama)  
   - Stage1 classifier: richiesto `qwen3.5-9b-mlx` (LM Studio path), fallisce `model_not_found`  
   - Stage1b decomposer: richiesto `qwen3.5-9b-mlx`, fallisce  
   - Stage2 reranking: tenta `qwen3.5-9b-mlx` su Ollama, 404 model not found  
   - Stage3 tool selection: richiesto `qwen3.5-9b-mlx`, fallisce

4. **Quale tools il retriever sta effettivamente selezionando?**  
   Nel run verificato: `tools_retrieved=18` nel dominio `sports_nba` (payload ~7.9KB). Lo selection LLM successivo non produce tool calls per failure modello.

5. **Perché synthesis è bloccato? (tool execution? LLM? size limit?)**  
   Nel repro corrente non è bloccata per timeout/size: è “a valle” di **0 tool eseguiti** dovuti a failure Stage 3 model selection.

6. **Dopo fix, quale sarà il success rate per complex multi-intent queries?**  
   Stima realistica (dopo fix + test + fallback odds): **80–90%** su query multi-intent sports_nba, con residuo failure legato a provider esterni (API quota/outage) e qualità modello locale.

---

## 7) Piano operativo di handoff a LLM implementatore

Ordinare l’implementazione in questo ordine:

1. Strumentazione stage trace (A)
2. Config/model hardening + decomposer model fix (B1-B2)
3. Fallback decomposer heuristico + keyword expansion + `used_fallback` semantics (B3-B5)
4. Odds resiliency + quota handling (C)
5. Test suite completa + coverage gate (D)

**Gate di accettazione finale**:
- query target produce tool calls reali (non zero)
- almeno 2 sub-query generate
- odds unavailable gestito con fallback e disclaimer
- e2e passa senza errori bloccanti
