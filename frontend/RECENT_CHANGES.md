# Recent Changes — PersAn (jAI)

## 2026-03-16: ChatPanel Infinite Loop Fix

### 🔧 React Performance & Stability Fix

- **ChatPanel.tsx**: Risolto errore "Maximum update depth exceeded" che causava crash durante l'input mentre era in corso streaming SSE.
- **Causa Root**: 
  1. `handleInputChange` aveva dipendenza inutile `[setInput]` nel useCallback
  2. Sottoscrizione all'intero oggetto `sessionStates` causava re-render ad ogni token durante streaming
- **Soluzione**:
  - Rimossa dipendenza `[setInput]` - `setInput` da useState è già stabile
  - Sostituito selettore `sessionStates` con selettore diretto per sessione corrente
  ```javascript
  // Before
  const sessionStates = useChatStore((s) => s.sessionStates);
  const currentSession = useMemo(() => sessionStates[currentSessionId], [sessionStates]);
  
  // After
  const currentSession = useChatStore((s) => 
      currentSessionId ? s.sessionStates[currentSessionId] : null
  );
  ```
- **Impatto**: Previene crash e re-render non necessari durante streaming, migliorando stabilità e performance

---

## 2026-03-15: API Providers Management Tab

### 🔌 New Providers Tab in Settings

- **ProvidersTab.tsx** [NEW]: Scheda completa per gestione provider API LLM
  - CRUD provider: aggiunta, modifica, eliminazione
  - Configurazione: nome, tipo (OpenAI/Anthropic/Gemini/Mistral/etc), base URL, API key
  - Gestione modelli con access_mode: subscription (PRO), api_paid, both
  - Subscription settings: weekly_token_limit, reset_day
  - Auto-discovery modelli da endpoint `/v1/models`
  - Test connessione con latenza e conteggio modelli

- **useSettings.ts**: Aggiunti hooks per providers:
  - `useProviders()` - Lista provider
  - `useCreateProvider()` - Crea provider
  - `useUpdateProvider()` - Aggiorna provider
  - `useDeleteProvider()` - Elimina provider
  - `useTestProvider()` - Test connessione
  - `useDiscoverModels()` - Auto-discovery modelli

- **useSettingsStore.ts**: Completata implementazione Zustand store
  - Aggiunto tipo `'providers'` ad activeTab
  - Implementati metodi: openSettings, closeSettings, setActiveTab, setLLMConfig, setLoading, setError, resetConfig

- **SettingsPanel.tsx**: Aggiunto tab "Providers" alla navigazione

- **gateway/src/routes/providers.ts** [NEW]: Proxy routes per API providers

### 🎨 UI Features

- Badge PRO per provider con subscription
- Badge "Local" per provider locali (Ollama, LM Studio)
- Indicatori colorati per access_mode modelli (purple=subscription, yellow=api_paid)
- Form collassabile per modelli con context_window, tools, vision flags
- Password toggle per API key visibility

---

## 2026-03-14: Infinite Loop Fix in ChatPanel

### 🔧 React State Management Fix

- **ChatPanel.tsx**: Risolto errore "Maximum update depth exceeded" che causava un loop infinito durante lo streaming SSE.
- **Causa Root**: Il componente sottoscriveva l'intero store Zustand (`useChatStore()`) senza selector, causando re-render eccessivi quando `statusMessage` e `isThinking` venivano aggiornati più volte al secondo durante lo streaming.
- **Soluzione**:
  - Sostituita la sottoscrizione completa con selector individuali per ogni stato necessario
  - Aggiunto `useMemo` per cachare i dati della sessione corrente
  - Stilizzato il pattern usato in altri componenti (es. `IntelDeck.tsx`)
- **Impatto**: Previene re-render non necessari durante lo streaming, migliorando le performance e la reattività dell'interfaccia

---

## 2026-03-13: Thinking Streaming & Tool Calling Fixes

### 🧠 Thinking Streaming Continuo

- **ActivityTimeline.tsx**: Fix per mantenere il thinking visibile durante tutto lo streaming. Il thinking ora persiste in un'area dedicata che non collassa quando arriva il content.
- **useChatStore.ts**: Introdotto `pendingThinking` state e azione `appendThinking()` per accumulare i token di thinking in tempo reale.
- **MessageBubble.tsx**: Aggiunta sezione collassabile "Mostra ragionamento" che preserva il thinking nel messaggio finale.
- **useGateway.ts**: Gestione corretta dei chunk `thinking` con chiamata a `appendThinking()`.

### 🔧 Tool Calling Fallback Enhancement

- **Intent-Tool Mapping**: Esteso `_INTENT_TOOL_MAP` in Me4BrAIn con mapping per:
  - Weather: `geo_weather`, `meteo`, `weather_query` → `openmeteo_weather`
  - Finance: `crypto_price`, `finance_query` → `coingecko_price`
  - Search: `web_search`, `search_query` → `duckduckgo_search`
- **Priority 2 Fallback**: Migliorato il fallback con pattern domain-specific per weather e finance, più fallback al primo tool disponibile come last resort.
- **Debug Logging**: Aggiunto logging dettagliato per tracciare risposte LLM e processo di selezione fallback.

### 📝 Types & Interfaces

- **chat.ts**: Aggiunto campo `thinking?: string` all'interfaccia `Message` per preservare il ragionamento nel messaggio finale.

---

## 2026-03-03: Dashboard E2E Stabilization & Streaming Fix

### 🛠️ Frontend & State Management

- **Hydration Fix**: Risolto errore `Hydration Mismatch` tramite `suppressHydrationWarning` nel layout principale.
- **Infinite Session Loop**: Introdotto `_fetchLock` in `useChatStore.ts` per prevenire chiamate ricorsive infinite a `fetchSessions` durante l'inizializzazione.
- **Atomic Session Creation**: Ottimizzata `createNewSession` per un inserimento locale immediato nello store, migliorando la reattività della sidebar.

### 📡 Gateway & SSE Protocol

- **Robust Event Normalization**: Aggiornato `chat.ts` nel Gateway per normalizzare i campi `message` e `content` negli eventi di tipo `thinking` e `status`. Garantisce compatibilità assoluta con il nuovo backend `me4brain`.
- **Frontend Hook Sync**: Aggiornato `useChat.ts` per processare in modo robusto entrambi i campi (`message` o `content`), assicurando che la timeline delle attività e le bolle assistant siano sempre popolate correttamente.

---

### PersAn Refounding: Phase 0 & Phase 1 Complete + OCR Migration

**Phase 0 - Type Safety Foundation:**
- **Unified Type System** (`packages/shared/src/`):
  - `engine.ts` (145 lines): SSE stream types con discriminated unions (`thinking`, `content`, `tool_call`, `done`, etc.), `EngineQueryOptions`, `ToolCallInfo`, `EngineStats`
  - `monitors.ts` (175 lines): Zod schemas per proactive monitoring system (sostituisce Pydantic Python), include `MonitorType`, `MonitorState`, `Decision`, `EvaluationResult`, config schemas per ogni tipo di monitor
  - `chat.ts` espanso: `ChatTurn` completo con feedback e toolsUsed, `ChatSession`, `SessionSummary`
  - `index.ts` aggiornato per esportare i nuovi moduli
- **Build Verification**: `@persan/shared` e `@persan/gateway` compilano senza errori

**Phase 1 - Frontend Consolidation:**
- **Single Gateway Endpoint** (`frontend/src/lib/config.ts`):
  - Eliminata architettura dual-URL (Backend Python porta 8888 + Gateway TypeScript porta 3030)
  - Ora esiste solo `NEXT_PUBLIC_GATEWAY_URL` (porta 3030)
  - `API_CONFIG.restUrl` e `API_CONFIG.websocketUrl` derivati da singola variabile
- **Hardcoded URLs Removed**: Rimossi 6 URL hardcoded da:
  - `utils.ts`, `ChatInput.tsx`, `ChatPanel.tsx`, `FileUpload.tsx`, `MonitorsPanel.tsx`, `useSessionGraph.ts`
  - Tutti ora usano `API_CONFIG` importato da `config.ts`
- **Frontend Build**: Verificato, compila senza errori

**Phase 1 - OCR Migration to Me4BrAIn:**
- **Me4BrAIn Ingestion API** (`me4brain/src/me4brain/api/routes/ingestion.py`) [NEW]:
  - Esposto `HybridOCRService` via HTTP endpoint `POST /v1/ingestion/upload`
  - Supporto PDF, JPEG, PNG, BMP (max 10MB)
  - Strategia ibrida: native PDF extraction (pypdf) + Vision LLM fallback (Kimi K2.5)
  - Response con extracted content, method used, model info, pages count
  - Health check endpoint `/v1/ingestion/health`
- **Gateway Upload Route Update** (`packages/gateway/src/routes/upload.ts`):
  - Eliminato proxy a backend Python (porta 8888)
  - Ora chiama direttamente Me4BrAIn ingestion API (porta 8000)
  - Variabile `BACKEND_URL` sostituita con `ME4BRAIN_URL`
- **Gateway Build**: Verificato, compila senza errori

**Architecture Impact:**
- Frontend → Gateway (porta 3030) → Me4BrAIn (porta 8000)
- Backend Python (porta 8888) **completamente isolato**, non più chiamato da nessun componente
- OCR processing ora gestito nativamente da Me4BrAIn via API HTTP
- Preparazione completa per eliminazione backend Python

## 2026-02-22

### Streaming Resilience & Session Isolation
- **Strict Matching (useGateway.ts)**: Implementata `activeStreamsRef` come dict in memoria per il tracciamento ultra-rigoroso dell'identificativo `session_id`. Eventuali SSE chunks "stranieri" ricevuti da connessioni concorrenti vengono scartati con efficienza zero-leakage, prevenendo race conditions UI in scenari multi-tab.

## 2026-02-17

### Mobile UI Premium Fixes
- **Sticky Header**: Risolto problema dello scroll mobile, l'header ora rimane fisso (`z-index: 50`)
- **Dynamic Viewport**: Implementato `100dvh` per eliminare i saltellamenti causati dalla barra indirizzi mobile
- **Zero Input Lag**: Memoizzazione di `MessageBubble` per una digitazione fluida su dispositivi meno potenti
- **Custom Modals**: Nuova modale `DeleteSessionModal` elegante per sostituire i dialog nativi del browser

### WebSocket Flow Unification (Continuity)
- **Unificazione Core**: Migrazione dell'invio messaggi da SSE a WebSockets per sfruttare il background processing
- **Activity Sync**: Timeline delle attività (Thinking, Planning, Steps) ora sincronizzata anche via WebSocket
- **Redis Replay**: `QueryExecutor` potenziato per bufferizzare e re-inviare l'intera sequenza operativa al rientro dell'utente
- **Frontend Refactor**: `ChatPanel` ora utilizza `useGateway` come percorso primario, garantendo resilienza totale
