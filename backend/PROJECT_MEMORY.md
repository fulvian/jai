# Project Memory - Me4BrAIn Core

## Architettura Core

Me4BrAIn è un sistema di memoria agentica API-First basato su 4 layer cognitivi:

1. **Working Memory**: Redis Streams + NetworkX (STM).
2. **Episodic Memory**: Qdrant con Tiered Multitenancy.
3. **Semantic Memory**: Neo4j per il Knowledge Graph (migrato da KuzuDB 2026-01-28).
4. **Procedural Memory**: Skill Graph per mappatura Intento -> Tool.

## Decisioni Architetturali (ADR)

- **BGE-M3**: Scelto per il supporto multilingual (IT/EN) superiore e l'efficienza MPS su macOS.
- **Neo4j 5.26** (2026-01-28): Migrazione da KuzuDB (archiviato Ottobre 2025) a Neo4j per supporto LlamaIndex nativo, concurrent writes, e manutenzione attiva.
- **LlamaIndex Integration**: Aggiunto `llama-index-graph-stores-neo4j` per PropertyGraphIndex e `SubQuestionQueryEngine` per query decomposition.
- **Rimozione Pandas**: Il runtime core deve essere leggero. L'estrazione dati dai database deve usare gli iteratori nativi degli SDK.

- **GraphRAG SOTA 2026**: Evoluzione del sistema di retrieval in 3 layer:
  - **Layer 1 (Hybrid Retrieval)**: Selezione tool tramite Graph Traversal + recupero contestuale Few-Shot via Vector Search su Neo4j.
  - **Layer 2 (Versioning & Constraints)**: Validazione rigida degli schemi Pydantic-native e gestione automatica della deprecazione tool.
  - **Layer 3 (Token Budgeting)**: Controllo granulare del consumo token per step ReAct con short-circuit preventivo.
- **Domain Specialization** (2026-02-26): Consolidamento dei domini sportivi (NBA Betting + Tactical Analysis) con ottimizzazione **H2H 2.0.0** (multi-season depth via `LeagueGameFinder`). Ottimizzazione euristica dei domini `google_workspace` (consulenza PA), `finance_crypto` (consulenza finanziaria profonda con Polygon.io, Binance e insider trading), `travel` (Cross-domain routing intelligente), `web_search` (SOTA 2026), `tech_coding` (Mappatura API reali), `utility` (orchestrazione trasversale), `medical` (diagnostica evidence-based e local pharma ITA), `science_research` (ricerca accademica avanzata), `jobs` (ricerca lavoro remota), `food` (ricette Tasty e nutrizione Edamam), `entertainment` (cinema TMDB MCP, musica YouTube/Spotify/Apple Music e libri Google Books) e `geo_weather` (meteo localizzato Meteo.it/NWS).

- **Streaming Engine Resilience** (2026-03-03): Rafforzamento del sistema SSE con invio forzato dell'evento `done` (`try...finally`) e euristica di sintesi basata su caratteri (`FORCE_CONTENT_THRESHOLD`) per prevenire blocchi dello streaming in caso di output LLM destrutturato.
- **Tool Calling & Thinking Streaming Fix** (2026-03-13): Risoluzione di problemi critici nel flusso di esecuzione:
  - **Nuclear Fallback Enhancement**: Esteso `_INTENT_TOOL_MAP` con mapping per weather (`geo_weather`, `meteo`), finance (`crypto_price`), e web search. Migliorato il Priority 2 fallback con pattern domain-specific e fallback al primo tool disponibile.
  - **Thinking Streaming Continuo**: Fix in `synthesizer.py` per lo streaming immediato di ogni token di thinking (non bufferizzato). Il thinking rimane visibile durante tutto lo streaming.
  - **Tool-Calling LLM Configuration**: Fix in `core.py` per passare correttamente `tool_calling_llm` e `tool_calling_model` all'`IterativeExecutor` nel path di streaming.
  - **Debug Logging**: Aggiunto logging dettagliato per tracciare risposte LLM (`step_tool_selection_response`), selezione fallback (`nuclear_fallback_check`), e argomenti costruiti (`executor_nuclear_fallback_args`).
- **Query Quality & Workspace Integration** (2026-03-04): Ottimizzazione della qualità delle risposte tramite:
  - **Keyword-First Decomposition**: Sub-query brevi per massimizzare il retrieval API.
  - **Intent Mapping Alignment**: Sincronizzazione ReAct tra intenti decomposti e tool Google Workspace reali.
  - **Synthesizer Scaling**: Incremento dei limiti di token (16k) e buffer di sintesi (8k) per report multi-fonte ad alta densità informativa.
- **LLM Extraction**: Per l'estrazione dai documenti e la generazione schemi, è preferibile utilizzare **Mistral Large 3**.

## Note Tecniche

- **Auth**: I token JWT devono contenere il claim `tenant_id` per l'isolamento dei dati.
- **Conflict Resolution**: Strategia predefinita `Recency Bias` per risolvere discrepanze tra memoria episodica (fatti recenti) e semantica (conoscenza consolidata).
- **Qdrant Sharding**: In ambienti NanoGPT, preferire `sharding_method=AUTO` per evitare errori di "Shard key not found" durante la creazione dinamica delle collection.

## Osservabilità

- **Prometheus Standard**: Esporre metriche su endpoint `/metrics`. Utilizzare decoratori `@track_latency` per monitorare latenza (bucket standard) e throughput.
- **Sleep Mode**: Il consolidamento della memoria deve avvenire in background (async task) per non bloccare il ciclo cognitivo principale.
