# Report Diagnostico Completo - Blocco Dashboard PersAn

**Data:** 2026-02-18 07:26 (UTC+1)  
**Ambiente:** Produzione server Geekom (100.99.43.29) + Locale  
**Sintomo:** Dashboard desktop bloccata, nessuno streaming, nessuna risposta

---

## 📋 Sommario Esecutivo

Il sistema PersAn in modalità desktop presenta un blocco apparente quando viene inviato un prompt: nessuno streaming del pensiero del modello LLM, nessuna risposta, nessun messaggio di errore.

**Analisi completata su:**
- 4 commit GitHub Me4Brain (ultime 36 ore)
- 25+ commit GitHub PersAn (ultime 36 ore)
- Flusso completo Frontend → Gateway → Backend
- Configurazione deploy Geekom

---

## 🔴 CAUSE PIÙ PROBABILI (Distillate)

Dall'analisi di 7 possibili fonti di problema, le **2 cause più probabili** sono:

### 1. WebSocket Non Connesso o Disconnesso Silenziosamente (70% probabilità)

**Sintomi osservati:**
- Sistema appare "bloccato" senza feedback
- Nessun messaggio di errore visibile
- Stato di "pensiero" non mostrato

**Meccanismo di fallimento:**
```
Frontend (ChatPanel.tsx:187)
    ↓ sendWsMessage(fullMessage)
    ↓
useGateway.ts:242-249
    ↓ if (!client || client.getState() !== 'connected') {
    ↓     setError('Non connesso al gateway');
    ↓     return;  // ← BLOCCO SENZA FEEDBACK VISIBILE
    ↓ }
```

**File coinvolti:**
- [`frontend/src/lib/gateway-client.ts:48-105`](../persan/frontend/src/lib/gateway-client.ts:48) - Connessione WS
- [`frontend/src/hooks/useGateway.ts:242-270`](../persan/frontend/src/hooks/useGateway.ts:242) - Invio messaggi
- [`packages/gateway/src/websocket/handler.ts:17-94`](../persan/packages/gateway/src/websocket/handler.ts:17) - Server WS

**Log diagnostici da verificare:**
```javascript
// Nel browser console (F12):
// - "WebSocket error:" → Connessione fallita
// - "Reconnecting in 3000ms" → Tentativi di riconnessione
// - "Max reconnection attempts reached" → Rinuncia

// Sul server Gateway:
// - "Incoming WebSocket connection request" → Connessione ricevuta
// - "WebSocket connection established" → Connessione OK
// - "WebSocket connection closed" → Disconnessione
```

---

### 2. QueryExecutor Fallisce Senza Propagare Errore (60% probabilità)

**Sintomi osservati:**
- Messaggio inviato correttamente
- Thinking indicator mostrato brevemente
- Poi più nulla

**Meccanismo di fallimento:**
```
MessageRouter.handleChat() [router.ts:57-89]
    ↓ chatSessionStore.addTurn() → OK
    ↓ queryExecutor.execute() → Delega in background
    ↓
QueryExecutor.execute() [query_executor.ts:34-44]
    ↓ this.runBackgroundTask().catch((err) => {
    ↓     console.error(...)  // ← ERRORE LOGGATO MA NON INVIATO AL CLIENT
    ↓ })
    ↓
QueryExecutor.runBackgroundTask() [query_executor.ts:46-126]
    ↓ this.me4brain.engine.queryStream() → POSSIBILE FALLIMENTO
    ↓ Se errore: messaggio inviato solo se socket ancora aperto
```

**File coinvolti:**
- [`packages/gateway/src/websocket/router.ts:57-89`](../persan/packages/gateway/src/websocket/router.ts:57)
- [`packages/gateway/src/services/query_executor.ts:34-126`](../persan/packages/gateway/src/services/query_executor.ts:34)
- [`packages/me4brain-client/src/engine.ts:90-196`](../persan/packages/me4brain-client/src/engine.ts:90)

**Log diagnostici da verificare:**
```bash
# Sul server Gateway:
# - "[QueryExecutor] Starting background query for session..." → Query iniziata
# - "[QueryExecutor] Error in background task for session..." → ERRORE
# - "Me4BrAIn HTTP 503: Service Unavailable" → Me4Brain non raggiungibile

# Sul server Me4Brain:
# - "engine_query_started" → Query ricevuta
# - "engine_query_failed" → Errore nell'engine
```

---

## 🟠 CAUSE SECONDARIE (Da verificare se le prime due sono escluse)

### 3. Redis Non Connesso (40% probabilità)

**Sintomi:**
- Sessioni non persistono dopo refresh
- "Sessione di test" appare automaticamente
- Buffer replay non funziona

**Verifica:**
```bash
# Sul server Geekom
docker exec -it me4brain-redis redis-cli ping
# Output atteso: PONG

# Verifica configurazione Gateway
echo $REDIS_URL
# Output atteso: redis://redis:6379
```

**File:** [`packages/gateway/src/services/query_executor.ts:26-28`](../persan/packages/gateway/src/services/query_executor.ts:26)

---

### 4. Me4Brain Non Raggiungibile (30% probabilità)

**Sintomi:**
- Timeout silenzioso dopo 15 minuti
- Nessuna risposta dal backend

**Verifica:**
```bash
# Dal Gateway container
curl -v http://100.99.43.29:8089/v1/health
# Output atteso: {"status": "healthy", ...}

# Verifica processo
docker ps | grep me4brain
```

**Configurazione:** `ME4BRAIN_URL=http://100.99.43.29:8089/v1` in [`docker/.env.geekcom:8`](../persan/docker/.env.geekcom:8)

---

### 5. ActivityTimeline Non Popolato (25% probabilità)

**Sintomi:**
- Streaming in corso ma timeline vuota
- Messaggi non mostrati durante elaborazione

**Causa:** Gli eventi non vengono mappati correttamente o `activitySteps` rimane vuoto.

**File:** [`frontend/src/components/chat/ActivityTimeline.tsx:74-76`](../persan/frontend/src/components/chat/ActivityTimeline.tsx:74)

```typescript
// La timeline si mostra solo se:
if (!isStreaming || activitySteps.length === 0) return null;
```

---

## 📊 Flusso Dati Completo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (Next.js)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  ChatPanel.tsx                                                              │
│      ↓ handleSubmit() → sendWsMessage(fullMessage)                          │
│      ↓                                                                       │
│  useGateway.ts                                                              │
│      ↓ client.sendChat(message, sessionId)                                  │
│      ↓                                                                       │
│  gateway-client.ts                                                          │
│      ↓ WebSocket.send(JSON.stringify({type: 'chat:message', ...}))          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓ WebSocket
┌─────────────────────────────────────────────────────────────────────────────┐
│                            GATEWAY (Fastify TS)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  websocket/handler.ts                                                       │
│      ↓ socket.on('message') → router.handle()                               │
│      ↓                                                                       │
│  websocket/router.ts                                                        │
│      ↓ handleChat() → chatSessionStore.addTurn()                            │
│      ↓         → queryExecutor.execute()                                    │
│      ↓                                                                       │
│  services/query_executor.ts                                                 │
│      ↓ runBackgroundTask() → me4brain.engine.queryStream()                  │
│      ↓ for await (chunk of stream) {                                        │
│      ↓     connectionRegistry.sendToUser(userId, message)                   │
│      ↓ }                                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓ HTTP SSE
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BACKEND (Me4Brain Python)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  api/routes/engine.py                                                       │
│      ↓ POST /engine/query {stream: true}                                    │
│      ↓ _event_generator()                                                   │
│      ↓     → _build_memory_context()                                        │
│      ↓     → _rewrite_query_with_context()                                  │
│      ↓     → engine.run_iterative_stream()                                  │
│      ↓     → yield SSE events                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔧 Piano di Verifica (Log da Aggiungere)

### Step 1: Log Frontend (Browser Console)

Aprire DevTools (F12) e verificare:

```javascript
// In gateway-client.ts:64-68 - Aggiungere log
this.ws.onopen = () => {
    console.log('✅ [WS] Connected to gateway');
    this.setState('connected');
    // ...
};

this.ws.onerror = (error) => {
    console.error('❌ [WS] Connection error:', error);
    // ...
};

// In useGateway.ts:246 - Aggiungere log
if (!client || client.getState() !== 'connected') {
    console.error('❌ [Gateway] Client not connected, state:', client?.getState());
    setError('Non connesso al gateway');
    return;
}
```

### Step 2: Log Gateway (Server)

```typescript
// In query_executor.ts:41-43 - Modifica critica
this.runBackgroundTask(sessionId, query, requestId, userId, bufferKey).catch((err) => {
    console.error(`[QueryExecutor] CRITICAL ERROR for session ${sessionId}:`, err);
    // AGGIUNGERE: Notifica al client
    connectionRegistry.sendToUser(userId, {
        type: 'error',
        data: { message: `Query execution failed: ${err.message}`, code: 'QUERY_ERROR', sessionId },
        timestamp: Date.now(),
        requestId: requestId,
    });
});
```

### Step 3: Verifica Connessione Redis

```bash
# Sul server Geekom
docker logs me4brain-redis 2>&1 | tail -50

# Verifica che il Gateway si connetta
docker logs persan-gateway 2>&1 | grep -i redis
```

### Step 4: Verifica Me4Brain

```bash
# Health check diretto
curl -X POST http://100.99.43.29:8089/v1/engine/query \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "stream": false}'

# Log Me4Brain
docker logs me4brain-api 2>&1 | tail -100
```

---

## 📝 Commit Recenti Analizzati

### Me4Brain (4 commit, 16-17 Febbraio)

| Commit    | Descrizione                              | Impatto potenziale            |
| --------- | ---------------------------------------- | ----------------------------- |
| `379d1bd` | Capability indexing con tenant_id        | ✅ Nessun impatto su streaming |
| `2117ce9` | 3-tier smart search (Brave, Tavily, DDG) | ⚠️ Modifica handler web_search |
| `1231122` | Fix imports after registry deprecation   | ⚠️ Potenziali import rotti     |
| `664f470` | Unify tools/skills registry              | 🔴 Refactoring importante      |

### PersAn (25+ commit, 16-17 Febbraio)

| Commit    | Descrizione                               | Impatto potenziale      |
| --------- | ----------------------------------------- | ----------------------- |
| `a73248d` | Session validation UUID + diagnostic logs | ✅ Debug migliorato      |
| `cb8b9a3` | Run backend from project root             | ✅ Fix import            |
| `38a3cac` | Hybrid architecture implementation        | 🔴 Cambio architetturale |
| `4da9972` | Restore thought process visualization     | 🔴 Fix ActivityTimeline  |
| `db736af` | Hard revert to synchronous websocket      | 🔴 Cambio gestione WS    |

---

## ✅ Checklist Verifica Ambiente

Prima di procedere con le fix, verificare:

- [ ] **Gateway in esecuzione** su porta 3030
  ```bash
  curl http://100.99.43.29:3030/health
  ```

- [ ] **WebSocket raggiungibile**
  ```javascript
  // Nel browser console:
  const ws = new WebSocket('ws://100.99.43.29:3030/ws');
  ws.onopen = () => console.log('WS OK');
  ws.onerror = (e) => console.error('WS ERROR', e);
  ```

- [ ] **Redis connesso**
  ```bash
  docker exec me4brain-redis redis-cli ping
  ```

- [ ] **Me4Brain raggiungibile**
  ```bash
  curl http://100.99.43.29:8089/v1/health
  ```

- [ ] **Variabili d'ambiente configurate**
  - `NEXT_PUBLIC_API_URL=http://100.99.43.29:3030`
  - `NEXT_PUBLIC_GATEWAY_URL=ws://100.99.43.29:3030/ws`
  - `ME4BRAIN_URL=http://100.99.43.29:8089/v1`
  - `REDIS_URL=redis://redis:6379`

---

## 🎯 Raccomandazioni Immediate

### 1. Aggiungere Log diagnostici (PRIORITÀ ALTA)

Modificare [`query_executor.ts:41-43`](../persan/packages/gateway/src/services/query_executor.ts:41):

```typescript
this.runBackgroundTask(sessionId, query, requestId, userId, bufferKey).catch((err) => {
    console.error(`[QueryExecutor] CRITICAL: Background task failed for ${sessionId}:`, err);
    // INVIARE ERRORE AL CLIENT
    const errorMsg: WSMessage = {
        type: 'error',
        data: { 
            message: `Query execution failed: ${err.message}`, 
            code: 'BACKGROUND_ERROR', 
            sessionId 
        },
        timestamp: Date.now(),
        requestId: requestId,
    };
    connectionRegistry.sendToUser(userId, errorMsg);
});
```

### 2. Migliorare feedback connessione WS (PRIORITÀ ALTA)

Modificare [`ChatPanel.tsx`](../persan/frontend/src/components/chat/ChatPanel.tsx) per mostrare stato connessione:

```typescript
// Aggiungere indicatore visivo se non connesso
const { isConnected, connectionState } = useGateway();

// Nel render:
{!isConnected && (
    <div className="bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 px-4 py-2">
        Connessione al server in corso... ({connectionState})
    </div>
)}
```

### 3. Verificare che Me4Brain sia in esecuzione (PRIORITÀ CRITICA)

```bash
# Sul server Geekom
docker ps | grep me4brain
docker logs me4brain-api --tail 100
```

---

## 📞 Prossimi Passi

1. **Eseguire verifica checklist** sopra indicata
2. **Confermare quale delle 2 cause principali** è responsabile
3. **Implementare fix** in base alla diagnosi confermata

**Attendendo conferma diagnosi prima di procedere con le correzioni.**

---

## ✅ CORREZIONE EFFETTUATA (2026-02-18 07:55 UTC+1)

### Problema Rilevato

**Isolamento delle reti Docker:** Il container `me4brain-api` era in esecuzione sulla rete `me4brain_me4brain-network` mentre tutti gli altri servizi (Redis, Qdrant, Neo4j, PostgreSQL, Gateway) erano sulla rete `me4brain-network`. Questo causava l'impossibilità di:

1. **Redis non raggiungibile:** Me4Brain non poteva connettersi a Redis per la cache delle sessioni
2. **Qdrant non raggiungibile:** Impossibile eseguire ricerche vettoriali
3. **Neo4j non raggiungibile:** Impossibile accedere alla knowledge graph

### Azioni Correttive Eseguite

1. **Modificato file `.env`:**
   ```bash
   # Prima:
   REDIS_URL=redis://redis:6379
   REDIS_HOST=redis
   
   # Dopo:
   REDIS_URL=redis://172.21.0.7:6379
   REDIS_HOST=172.21.0.7
   ```

2. **Ricreato container `me4brain-api` con networking corretto:**
   ```bash
   docker run -d --name me4brain-api \
     --network me4brain-network \
     -e REDIS_URL=redis://172.21.0.7:6379 \
     -e REDIS_HOST=172.21.0.7 \
     -e QDRANT_URL=http://me4brain-qdrant:6334 \
     ...
   ```

3. **Verificata connettività:** Tutti i servizi ora comunicano correttamente

### Stato Attuale Servizi

| Servizio        | Porta | Stato | Note                     |
| --------------- | ----- | ----- | ------------------------ |
| me4brain-api    | 8000  | ✅ OK  | Health: tutti servizi OK |
| persan-gateway  | 3030  | ✅ OK  | Health: healthy          |
| persan-frontend | 3020  | ✅ OK  | Next.js response 200     |
| persan-redis    | 6379  | ✅ OK  | Health check OK          |
| me4brain-qdrant | 6333  | ✅ OK  | 5 collections            |
| me4brain-neo4j  | 7687  | ✅ OK  | Connesso                 |

### ⚠️ Raccomandazioni Future

1. **Persistent Network Config:** Modificare `docker-compose.yml` per includere sempre `me4brain-api` nella rete `me4brain-network` insieme agli altri servizi

2. **Script di Restart:** Creare uno script che assicuri che tutti i container siano sulle reti corrette dopo un riavvio

3. **Monitoraggio:** Aggiungere health check che verifichino la connettività tra i servizi

---

**Report generato da:** Debug Mode Analysis  
**Ultimo aggiornamento:** 2026-02-18 07:55 UTC+1  
**File salvato in:** `docs/reports/DIAGNOSTIC_REPORT_2026-02-18.md`
