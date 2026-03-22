# LLM Timeout Configuration Guide

## Overview

Me4BrAIn implementa timeout protection per tutte le fasi asincrone che coinvolgono LLM, garantendo che il sistema non rimanga in attesa indefinita di risposte LLM lente.

## Development Phase Configuration

Durante la fase di sviluppo con modelli LLM locali lenti (es. Ollama qwen3.5:4b), i timeout sono configurati con margini generosi:

### Timeout Matrix

| Fase | Timeout | Moltiplicatore | Posizione File | Note |
|------|---------|----------------|-----------------|------|
| **1. Domain Classification** | 180s | 6x | `domain_classifier.py:167` | Classificazione dominio della query |
| **2. Query Decomposition** | 240s | 4x | `query_decomposer.py:244` | Scomposizione in sub-query |
| **3. Tool Reranking** | 180s | 4x | `llama_tool_retriever.py:151` | Riordinamento tools per relevance |
| **4. Graph Hints Retrieval** | 120s | 4x | `iterative_executor.py:1919` | Recupero hint da knowledge graph |
| **5. Result Summarization** | 120s | 4x | `synthesizer.py:520` | Sintesi risultati per singolo tool |
| **6. Response Synthesis** | 300s | 2.5x | `synthesizer.py:184` | Sintesi finale risposta multi-fonte |

## Performance Characteristics

### Ollama qwen3.5:4b (Development)

Benchmark con query NBA complessa ("Mostra le statistiche di Luka Doncic, le sue lesioni recenti e le quote di gioco"):

| Fase | Tempo Medio | Timeout | Margine |
|------|------------|---------|---------|
| Domain Classification | 30s | 180s | 150% |
| Query Decomposition | 45s | 240s | 433% |
| Tool Reranking | 35s | 180s | 414% |
| Graph Hints Retrieval | 20s | 120s | 500% |
| Result Summarization | 25s | 120s | 380% |
| Response Synthesis | 85s | 300s | 253% |
| **Total** | **~240s** | **1140s** | **375%** |

### Mistral API / GPT-4 (Production)

Stime per LLM cloud veloci:

| Fase | Tempo Medio | Timeout (Attuale) | Timeout (Ottimale) |
|------|------------|-------------------|-------------------|
| Domain Classification | 2-3s | 180s | 15s |
| Query Decomposition | 3-5s | 240s | 30s |
| Tool Reranking | 2-3s | 180s | 20s |
| Graph Hints Retrieval | 1-2s | 120s | 10s |
| Result Summarization | 2-3s | 120s | 15s |
| Response Synthesis | 5-8s | 300s | 60s |
| **Total** | **~18-30s** | **1140s** | **150s** |

## Implementation Details

### Timeout Protection Pattern

Tutti i timeout sono implementati usando `asyncio.wait_for()`:

```python
try:
    response = await asyncio.wait_for(
        llm_client.generate_response(request),
        timeout=TIMEOUT_SECONDS
    )
except asyncio.TimeoutError:
    logger.warning(
        "phase_timeout",
        timeout_seconds=TIMEOUT_SECONDS,
        fallback="strategy",
        ...
    )
    # Graceful fallback
```

### Fallback Strategies

Quando una fase timeout:

| Fase | Fallback |
|------|----------|
| Domain Classification | Fallback a web_search (conservative) |
| Query Decomposition | Restituisci query originale come singola sub-query |
| Tool Reranking | Continua con tools non riordinati |
| Graph Hints Retrieval | Continua senza hint da knowledge graph |
| Result Summarization | Restituisci dati raw (primi 500 chars) |
| Response Synthesis | Restituisci fallback response (parziale) |

## Configuration Guide

### Modificare i Timeout

#### Option 1: Modifica File Sorgente (Raccomandato)

1. Localizza il file della fase desiderata (vedi "Timeout Matrix" sopra)
2. Modifica il valore `timeout=XXX.0` e `timeout_seconds=XXX`
3. Commit e deploy

Esempio:
```bash
# Per phase 2 (Query Decomposition)
vim src/me4brain/engine/hybrid_router/query_decomposer.py
# Cambia linea 244: timeout=240.0 → timeout=180.0
```

#### Option 2: Environment Variables (Non Supportato Attualmente)

Non è possibile configurare i timeout via `.env` perché sono hardcoded. Implementare support in futuro se necessario.

### Per Produzione: Ottimizzare i Timeout

Se deployato con LLM cloud veloci:

```python
# Valori raccomandati per produzione
TIMEOUTS = {
    "domain_classification": 30.0,      # 180s → 30s
    "query_decomposition": 60.0,        # 240s → 60s
    "tool_reranking": 45.0,             # 180s → 45s
    "graph_hints": 30.0,                # 120s → 30s
    "result_summarization": 30.0,       # 120s → 30s
    "response_synthesis": 120.0,        # 300s → 120s
}
```

Script per aggiornare automaticamente:
```bash
./scripts/optimize_timeouts_for_production.sh
```

## Monitoring & Logging

### Timeout Events Logging

Ogni timeout è loggato con:
- `timeout_seconds`: Valore del timeout che è scattato
- `phase`: Nome della fase
- `fallback`: Strategia di fallback applicata
- `query_preview`: Anteprima della query (primi 50 char)

### Analizzare i Timeout nei Log

```bash
# Visualizza tutti gli timeout
docker logs me4brain-api | grep "timeout"

# Conta timeout per fase
docker logs me4brain-api | grep "timeout" | jq '.level,.message'

# Filtra timeout specifici
docker logs me4brain-api | grep "query_decomposition_timeout"
```

## Testing

### Verifica Timeout Protection

```bash
# Test 1: Timeout in Domain Classification
curl -X POST http://localhost:8089/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Very complex multi-part query..."}'

# Nei log dovrebbe comparire:
# - Domain classification attempt
# - Se timeout: "domain_classification_timeout" event
# - Fallback to web_search
```

### Load Testing con Timeout

```bash
# Simula 10 query concorrenti (development timeouts)
for i in {1..10}; do
  curl -X POST http://localhost:8089/v1/query \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"NBA statistics for player $i\"}" &
done
wait

# Monitora timeout nel backend
docker logs me4brain-api | grep "timeout" | wc -l
```

## FAQ

### Q: Perché i timeout sono così alti?

**A**: Durante lo sviluppo, si usa Ollama locale che è molto lento. I timeout alti garantiscono che query complesse completino senza timeout prematura. In produzione con LLM cloud, i timeout possono essere ridotti drasticamente (vedi Produzione).

### Q: Cosa succede se un timeout scatta durante una query?

**A**: Il sistema applica una strategia di fallback per quella fase specifica:
- Se classificazione timeout → fallback a web_search
- Se decomposizione timeout → usa query originale
- Se sintesi timeout → restituisci risposta parziale

La query non fallisce completamente, ma la qualità della risposta degrada progressivamente.

### Q: Posso configurare i timeout via API?

**A**: No, attualmente sono hardcoded. Per supporto dinamico, aprire una issue su GitHub con use case.

### Q: Quali sono i timeout in produzione consigliati?

**A**: Vedi tabella "Produzione" più sopra. In generale, ridurre di 6-10x se usi LLM cloud.

## Related Documentation

- [README.md - LLM Configuration](../README.md#llm-timeout-configuration-development-phase)
- [CHANGELOG.md - v0.20.0](../CHANGELOG.md#enhanced---llm-timeout-configuration-development-phase)
- Implementazione: `src/me4brain/engine/` (vedi "Timeout Matrix")

## Version History

| Versione | Data | Change |
|----------|------|--------|
| 1.0 | 2026-03-21 | Initial implementation (180s-300s) |
