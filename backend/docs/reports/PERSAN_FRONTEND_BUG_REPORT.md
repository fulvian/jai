# PersAn Frontend - Report Completo Bug e Criticità

**Data:** 2026-02-17  
**Ambiente:** Produzione su server GIC-com  
**Versione analizzata:** Frontend Next.js 14+ / Gateway Fastify / Backend Python FastAPI

---

## 📋 Sommario Esecutivo

L'analisi ha identificato **7 criticità principali** e **12 bug minori** che impattano l'esperienza utente sia su desktop che su mobile. I problemi più gravi riguardano:

1. **Disallineamento architetturale** tra Gateway TypeScript e Backend Python
2. **Configurazione CORS restrittiva** che blocca richieste da domini di produzione
3. **Fallback in-memory per Redis** che causa perdita sessioni al riavvio
4. **Persistenza localStorage** che entra in conflitto con lo stato del server

---

## 🔴 CRITICITÀ ALTA PRIORITÀ

### 1. Configurazione CORS Restrittiva (CRITICO)

**File:** [`backend/main.py`](../persan/backend/main.py:17-26)

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3020",
        "http://127.0.0.1:3020",
    ],
    ...
)
```

**Problema:** Il backend Python accetta richieste SOLO da `localhost:3020`. In produzione su GIC-com, il frontend probabilmente viene servito da un dominio/IP diverso, causando errori CORS bloccanti.

**Impatto:** 
- Errori HTTP 403/405 su chiamate API
- Impossibile creare/caricare sessioni
- Chat non funzionante

**Soluzione:**
```python
allow_origins=[
    "http://localhost:3020",
    "http://127.0.0.1:3020",
    "http://100.99.43.29:3020",  # IP Tailscale
    "http://GIC-com:3020",       # Server produzione
    # oppure use ["*"] per sviluppo
]
```

---

### 2. Architettura a Tre Livelli con Endpoint Duplicati (CRITICO)

**Componenti coinvolti:**
- **Frontend** (porta 3020) → chiama `/api/chat/*`
- **Gateway TypeScript** (porta 3030) → espone `/api/chat/*` con Redis
- **Backend Python** (porta 8888) → espone `/api/chat/*` con Me4Brain

**Problema:** Esistono DUE backend con gli stessi endpoint ma implementazioni diverse:

| Endpoint                                   | Gateway (TS) | Backend Python |
| ------------------------------------------ | ------------ | -------------- |
| `GET /api/chat/sessions`                   | ✅ Redis      | ✅ Me4Brain API |
| `POST /api/chat/sessions`                  | ✅ Redis      | ✅ Me4Brain API |
| `GET /api/chat/sessions/:id`               | ✅ Redis      | ✅ Me4Brain API |
| `PUT /api/chat/sessions/:id/config`        | ✅ Redis      | ❌ Mancante     |
| `DELETE /api/chat/sessions/:id/turns/:idx` | ✅ Redis      | ❌ Mancante     |
| `POST /api/chat/sessions/:id/retry/:idx`   | ✅ Redis      | ❌ Mancante     |

**Il Frontend chiama il Gateway (porta 3030)**, ma il Backend Python ha endpoint incompleti.

**Soluzione:** 
- Opzione A: Rimuovere il Backend Python e usare solo il Gateway
- Opzione B: Completare gli endpoint mancanti nel Backend Python
- Opzione C: Configurare il Gateway come proxy verso il Backend Python

---

### 3. Fallback In-Memory per Redis (CRITICO)

**File:** [`gateway/src/services/chat_session_store.ts`](../persan/packages/gateway/src/services/chat_session_store.ts:95-98)

```typescript
this.redis.connect().catch(() => {
    this.redisAvailable = false;
    console.warn('⚠️ ChatSessionStore: Redis unavailable, using memory fallback');
});
```

**Problema:** Se Redis non è raggiungibile, il sistema passa silenziosamente a un Map in-memory. Questo causa:
- Perdita di tutte le sessioni al riavvio del Gateway
- Comportamento imprevedibile in cluster multi-istanza
- "Sessione di test" che appare dopo refresh (sessione default creata in memoria)

**Sintomi riportati dall'utente:**
> "Se faccio refresh in una sessione, mi imposta automaticamente una sessione di test con giorno test, mentre cancella quella della sessione."

**Soluzione:**
1. Verificare connessione Redis su GIC-com (porta 6389)
2. Aggiungere health check che fallisce se Redis non è disponibile
3. Loggare errori Redis con livello ERROR invece di WARNING

---

### 4. Hardcoded Fallback URL (ALTO)

**File:** [`frontend/src/stores/useChatStore.ts`](../persan/frontend/src/stores/useChatStore.ts:13)

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://100.99.43.29:3030';
```

**File:** [`frontend/src/hooks/useChat.ts`](../persan/frontend/src/hooks/useChat.ts:1)

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://100.99.43.29:3030';
```

**Problema:** L'IP `100.99.43.29` è un IP Tailscale che potrebbe non essere raggiungibile da:
- Dispositivi mobile su rete cellulare
- Client fuori dalla VPN Tailscale
- Browser con configurazione di rete diversa

**Soluzione:** Usare variabili d'ambiente obbligatorie con validazione:
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL;
if (!API_URL) throw new Error('NEXT_PUBLIC_API_URL is required');
```

---

## 🟠 CRITICITÀ MEDIA PRIORITÀ

### 5. Conflitto localStorage vs Server State (MEDIO)

**File:** [`frontend/src/stores/useChatStore.ts`](../persan/frontend/src/stores/useChatStore.ts:518-550)

```typescript
persist(
    (set, get) => ({ ... }),
    {
        name: 'persan-chat-storage',
        storage: createJSONStorage(() => localStorage),
        partialize: (state) => ({
            currentSessionId: state.currentSessionId,
            sessionStates: Object.fromEntries(
                Object.entries(state.sessionStates).map(([id, data]) => [
                    id,
                    { messages: data.messages } as Partial<SessionData>,
                ])
            ),
        }),
    }
)
```

**Problema:** Lo store persiste i messaggi in localStorage, ma al caricamento:
1. `loadSession()` scarica i messaggi dal server
2. Il merge con localStorage può causare duplicati o messaggi persi
3. Se il server ha meno messaggi (Redis svuotato), il localStorage mostra messaggi "fantasma"

**Soluzione:**
- Opzione A: Disabilitare persistenza messaggi, mantenere solo `currentSessionId`
- Opzione B: Implementare merge intelligente con timestamp
- Opzione C: Aggiungere versione allo schema localStorage per invalidare cache

---

### 6. Endpoint PATCH con Query Parameter (MEDIO)

**File:** [`gateway/src/routes/chat.ts`](../persan/packages/gateway/src/routes/chat.ts:228-248)

```typescript
app.patch<{ Params: SessionParams; Querystring: SessionQuery }>(
    '/api/chat/sessions/:id',
    async (request, reply) => {
        const { title } = request.query;  // Title from query string!
        ...
    }
);
```

**File:** [`frontend/src/stores/useChatStore.ts`](../persan/frontend/src/stores/useChatStore.ts:474-479)

```typescript
const response = await fetch(
    `${API_URL}/api/chat/sessions/${sessionId}?title=${encodeURIComponent(title)}`,
    { method: 'PATCH' }
);
```

**Problema:** Il titolo viene passato come query parameter invece che nel body. Questo è:
- Non RESTful
- Problematico per titoli lunghi o con caratteri speciali
- Incoerente con gli altri endpoint

**Soluzione:** Passare il titolo nel body JSON:
```typescript
// Backend
const { title } = request.body;

// Frontend
fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title })
});
```

---

### 7. WebSocket URL Hardcoded (MEDIO)

**File:** [`frontend/src/hooks/useGateway.ts`](../persan/frontend/src/hooks/useGateway.ts:1)

```typescript
const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || 'ws://100.99.43.29:3030/ws';
```

**Problema:** Stesso problema dell'API URL - IP Tailscale hardcoded.

---

## 🟡 BUG MINORI

### 8. Mancanza di Loading States

**File:** [`frontend/src/stores/useChatStore.ts`](../persan/frontend/src/stores/useChatStore.ts:364-378)

```typescript
fetchSessions: async () => {
    set({ loadingSessions: true });
    try {
        const response = await fetch(`${API_URL}/api/chat/sessions`);
        if (response.ok) {
            const data = await response.json();
            set({ sessions: data.sessions || [], loadingSessions: false });
        } else {
            set({ loadingSessions: false });  // Nessun errore mostrato
        }
    } catch (error) {
        console.error('Failed to fetch sessions:', error);  // Solo console
        set({ loadingSessions: false });  // Nessun feedback utente
    }
},
```

**Problema:** Errori silenti, l'utente non sa se il caricamento è fallito.

---

### 9. Timeout Non Configurato per Fetch

**File:** [`frontend/src/stores/useChatStore.ts`](../persan/frontend/src/stores/useChatStore.ts:367)

```typescript
const response = await fetch(`${API_URL}/api/chat/sessions`);
```

**Problema:** Nessun timeout configurato. Con query lunghe (fino a 10 minuti secondo config), il browser potrebbe interrompere la connessione.

---

### 10. Error Handling Incompleto in useChat

**File:** [`frontend/src/hooks/useChat.ts`](../persan/frontend/src/hooks/useChat.ts:1)

L'hook non gestisce correttamente:
- Riconnessione automatica dopo errore
- Retry con backoff esponenziale
- Cancellazione richieste in-flight

---

### 11. ActivityTimeline Non Aggiornato

**File:** [`frontend/src/components/chat/ActivityTimeline.tsx`](../persan/frontend/src/components/chat/ActivityTimeline.tsx:1)

L'utente ha riportato che il "flusso di pensiero del modello non viene mostrato". Questo suggerisce che:
- Gli eventi `status`, `tool`, `thinking` non vengono renderizzati
- Oppure non vengono ricevuti dal backend

---

### 12. Mobile - Problemi Specifici

**Problemi riportati:**
- Sessioni che scompaiono dopo refresh
- "Sessione di test" che appare automaticamente
- Storia non recuperata

**Cause probabili:**
1. localStorage mobile con quota limitata
2. Swipe/refresh che triggera `clearSession()`
3. Viewport meta tag non ottimizzato

---

## 📊 Matrice di Impatto

| Bug                    | Desktop | Mobile | Severità |
| ---------------------- | ------- | ------ | -------- |
| CORS restrittivo       | 🔴       | 🔴      | Critico  |
| Endpoint duplicati     | 🔴       | 🔴      | Critico  |
| Fallback Redis         | 🔴       | 🔴      | Critico  |
| URL hardcoded          | 🟡       | 🔴      | Alto     |
| Conflitto localStorage | 🟠       | 🔴      | Medio    |
| PATCH query param      | 🟡       | 🟡      | Medio    |
| WebSocket hardcoded    | 🟡       | 🔴      | Medio    |
| Loading states         | 🟡       | 🟡      | Basso    |
| Timeout fetch          | 🟠       | 🟠      | Basso    |

---

## 🔧 Piano di Risoluzione Consigliato

### Fase 1: Hotfix (24-48 ore)

1. **Aggiornare CORS** nel Backend Python per accettare domini di produzione
2. **Verificare connessione Redis** su GIC-com
3. **Aggiornare `.env`** del frontend con URL corretti per produzione

### Fase 2: Stabilizzazione (1 settimana)

1. **Unificare architettura backend** (Gateway OR Python, non entrambi)
2. **Implementare merge intelligente** localStorage/server
3. **Aggiungere error boundary** e feedback utente per errori API

### Fase 3: Refactoring (2 settimane)

1. **Estrarre configurazione** in variabili d'ambiente obbligatorie
2. **Implementare retry logic** con backoff esponenziale
3. **Ottimizzare ActivityTimeline** per mostrare tutti gli eventi

---

## 📝 File Coinvolti

### Frontend
- [`src/stores/useChatStore.ts`](../persan/frontend/src/stores/useChatStore.ts) - State management
- [`src/hooks/useChat.ts`](../persan/frontend/src/hooks/useChat.ts) - SSE streaming
- [`src/hooks/useGateway.ts`](../persan/frontend/src/hooks/useGateway.ts) - WebSocket
- [`src/components/chat/ActivityTimeline.tsx`](../persan/frontend/src/components/chat/ActivityTimeline.tsx) - UI timeline
- [`src/lib/gateway-client.ts`](../persan/frontend/src/lib/gateway-client.ts) - WS client

### Gateway
- [`src/routes/chat.ts`](../persan/packages/gateway/src/routes/chat.ts) - API endpoints
- [`src/services/chat_session_store.ts`](../persan/packages/gateway/src/services/chat_session_store.ts) - Redis store
- [`src/app.ts`](../persan/packages/gateway/src/app.ts) - CORS config

### Backend Python
- [`main.py`](../persan/backend/main.py) - Entry point, CORS
- [`api/routes/chat.py`](../persan/backend/api/routes/chat.py) - API endpoints
- [`services/me4brain_service.py`](../persan/backend/services/me4brain_service.py) - Me4Brain integration

---

## ✅ Checklist Verifica Ambiente GIC-com

Prima di applicare le fix, verificare:

- [ ] Gateway in esecuzione su porta 3030
- [ ] Redis raggiungibile su porta 6389 con password corretta
- [ ] Me4Brain API raggiungibile dal Gateway
- [ ] Variabili d'ambiente configurate:
  - `NEXT_PUBLIC_API_URL`
  - `NEXT_PUBLIC_GATEWAY_URL`
  - `REDIS_URL`
  - `REDIS_PASSWORD`
  - `ME4BRAIN_URL`
- [ ] CORS configurato per il dominio di produzione
- [ ] Certificati SSL validi (se HTTPS)

---

**Report generato da:** Debug Mode Analysis  
**File salvato in:** `docs/reports/PERSAN_FRONTEND_BUG_REPORT.md`
