# Tool Retrieval Fix - 2026-03-28

## Problema

Quando l'utente chiedeva "che tempo fa a Caltanissetta?", il sistema non riusciva a recuperare gli strumenti meteo (openmeteo_weather, openmeteo_forecast), nonostante:

1. La classificazione del dominio funzionasse correttamente (geo_weather con confidence 0.96)
2. Il retrieval vettoriale trovasse i nodi corretti (openmeteo_forecast score 0.50, openmeteo_weather score 0.49)

**Sintomo**: `zero_tools_retrieved_triggering_rescue` → `rescue_failed_all_policies_exhausted`

## Root Cause

Due bug in `backend/src/me4brain/engine/hybrid_router/tool_index.py`:

### Bug 1: Campo `text` non salvato nel payload Qdrant (linee 394-397)

```python
# PRIMA (bug):
payload = {**node.metadata}
# Il campo "text" NON veniva aggiunto al payload

# DOPO (fix):
payload = {**node.metadata}
payload["text"] = node.text  # CRITICAL: necessario per TextNode reconstruction
```

**Errore che causava**: `"1 validation error for TextNode\ntext\n  Input should be a valid string"`

### Bug 2: `schema_json` rimosso dal payload (linee 399-401)

```python
# PRIMA (bug):
for key in ["schema_json", "_catalog_hash"]:
    payload.pop(key, None)

# DOPO (fix):
payload.pop("_catalog_hash", None)  # Solo hash interno, NON schema_json
```

**Impatto**: Quando `_nodes_to_tools()` cercava lo schema nello payload, non lo trovava → tutti gli strumenti venivano scartati con `tool_missing_schema`.

## Fix Applicati

File: `backend/src/me4brain/engine/hybrid_router/tool_index.py`

1. Aggiunto `payload["text"] = node.text` per permettere la ricostruzione di TextNode
2. Rimosso solo `schema_json` dalla lista dei campi da escludere

## Verifica

Dopo il fix, il retrieval funziona:

```
Searching for 'che tempo fa a Caltanissetta?' in 'geo_weather' domain...
Retrieved 2 tools:
- Tool: openmeteo_weather, Score: 10.0000, Domain: geo_weather
- Tool: openmeteo_forecast, Score: 7.0000, Domain: geo_weather
```

## Nota sulla Build dell'Index

L'index Qdrant viene built automaticamente all'avvio del backend via `ToolIndexManager.build_from_catalog()` in `core.py`.

Per rebuild manuale:
```bash
cd /home/fulvio/coding/jai/backend
uv run python -c "
import asyncio
from me4brain.engine.catalog import ToolCatalog
from me4brain.engine.hybrid_router.tool_index import ToolIndexManager
from qdrant_client import AsyncQdrantClient, QdrantClient

async def rebuild():
    client = QdrantClient(url='http://localhost:6333')
    aclient = AsyncQdrantClient(url='http://localhost:6333')
    catalog = ToolCatalog()
    await catalog.discover_from_domains()
    manager = ToolIndexManager(client, aclient)
    await manager.initialize()
    count = await manager.build_from_catalog(
        catalog.get_function_schemas(),
        catalog.get_tool_domains(),
        force_rebuild=True
    )
    print(f'Indexed {count} tools')

asyncio.run(rebuild())
"
```

## Prossimi Passi (Non Completati)

1. **Hybrid Search**: Implementare `QueryFusionRetriever` con vector + BM25
2. **Reranker**: Sostituire LLM reranker lento con `SentenceTransformerRerank`
3. **Test E2E**: Verificare il flusso completo API → tool retrieval → execution

## File Modificati

- `backend/src/me4brain/engine/hybrid_router/tool_index.py` - Fix principalali
