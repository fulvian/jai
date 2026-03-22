# Analisi Architetturale: Gateway TypeScript vs Backend Python

**Data:** 2026-02-17  
**Domanda:** Perché esistono due backend e qual è la differenza?

---

## 📊 Tabella Comparativa

| Aspetto                  | Gateway TypeScript              | Backend Python                      |
| ------------------------ | ------------------------------- | ----------------------------------- |
| **Linguaggio**           | TypeScript/Node.js              | Python/FastAPI                      |
| **Framework**            | Fastify                         | FastAPI                             |
| **Porta default**        | 3030                            | 8888                                |
| **Avviato da start.sh**  | ✅ Sì                            | ❌ No                                |
| **Usato in produzione**  | ✅ Sì                            | ❌ No (attualmente)                  |
| **Persistenza sessioni** | Redis                           | Me4Brain Working Memory             |
| **WebSocket**            | ✅ Implementato                  | ❌ Non implementato                  |
| **CORS**                 | ✅ Permissivo (tutti gli origin) | ⚠️ Restrittivo (solo localhost:3020) |

---

## 🏗️ Funzionalità Gateway TypeScript

**File:** `persan/packages/gateway/src/routes/index.ts`

```
├── /health                    → Health check
├── /ready                     → Readiness check (Kubernetes)
├── /api/status                → Stato gateway
├── /api/chat/*                → Sessioni chat con Redis
│   ├── POST /api/chat                    → SSE streaming
│   ├── GET  /api/chat/sessions           → Lista sessioni
│   ├── POST /api/chat/sessions           → Crea sessione
│   ├── GET  /api/chat/sessions/:id       → Carica sessione
│   ├── DELETE /api/chat/sessions/:id     → Elimina sessione
│   ├── PATCH /api/chat/sessions/:id      → Aggiorna titolo
│   ├── PUT   /api/chat/sessions/:id/config → Aggiorna config
│   ├── DELETE /api/chat/sessions/:id/turns/:idx → Cancella turn
│   ├── PUT   /api/chat/sessions/:id/turns/:idx → Modifica turn
│   └── POST /api/chat/sessions/:id/retry/:idx → Retry query
├── /ws                        → WebSocket real-time
├── /api/voice/*               → Voice routes
├── /api/push/*                → Push notifications
├── /api/approvals/*           → HITL Approval
├── /api/monitors/*            → Monitor/Proactive
├── /api/skills/*              → Proxy a Me4Brain /v1/skills
└── /api/graph/*               → Session Knowledge Graph
```

**Canali supportati:**
- Webchat (dashboard)
- Telegram
- WhatsApp

---

## 🐍 Funzionalità Backend Python

**File:** `persan/backend/main.py`

```
├── /api/health                → Health check
├── /api/chat/*                → Sessioni chat con Me4Brain
│   ├── POST /api/chat                    → SSE streaming
│   ├── POST /api/chat/simple            → Non-streaming
│   ├── POST /api/chat/tool              → Direct tool call
│   ├── GET  /api/chat/sessions          → Lista sessioni
│   ├── POST /api/chat/sessions          → Crea sessione
│   ├── GET  /api/chat/sessions/:id      → Carica sessione
│   ├── DELETE /api/chat/sessions/:id    → Elimina sessione
│   └── PATCH /api/chat/sessions/:id     → Aggiorna titolo
├── /api/upload/*              → File upload
├── /api/tools/*               → Tools
├── /api/skills/*              → Skills
├── /api/monitors/*            → Monitors
├── /api/memory/*              → Memory
└── /api/proactive/*           → NL-to-Monitor
```

**Endpoint MANCANTI rispetto al Gateway:**
- `PUT /api/chat/sessions/:id/config`
- `DELETE /api/chat/sessions/:id/turns/:idx`
- `PUT /api/chat/sessions/:id/turns/:idx`
- `POST /api/chat/sessions/:id/retry/:idx`
- WebSocket `/ws`

---

## 🔗 Come Comunica con Me4Brain

### Gateway TypeScript
```
Frontend → Gateway:3030 → Me4Brain:8000/v1/*
                      ↘ Redis:6389 (sessioni)
```

Il Gateway:
1. Riceve richieste dal frontend
2. Salva le sessioni in **Redis** localmente
3. Chiama Me4Brain per l'elaborazione AI (tool calling, query)

### Backend Python
```
Frontend → Backend:8888 → Me4Brain:8000/v1/*
                        ↘ Me4Brain Working Memory API (sessioni)
```

Il Backend Python:
1. Riceve richieste dal frontend
2. Salva le sessioni tramite **Me4Brain Working Memory API** (`/v1/working/sessions`)
3. Chiama Me4Brain per l'elaborazione AI

---

## 🤔 Perché Esistono Entrambi?

### Ipotesi 1: Evoluzione Architetturale
Il Backend Python è stato creato **prima** come "PersAn API" che usava direttamente Me4Brain. Successivamente è stato aggiunto il Gateway TypeScript per:
- Gestire WebSocket
- Supportare canali multipli (Telegram, WhatsApp)
- Avere latenza più bassa con Redis locale

### Ipotesi 2: Separazione Responsabilità (Non Completata)
- **Gateway TypeScript**: BFF (Backend for Frontend) per routing, WebSocket, canali
- **Backend Python**: Logica business avanzata, integrazioni Python

### Ipotesi 3: Sviluppo Parallelo
Due team hanno sviluppato in parallelo e non è stata fatta la scelta finale.

---

## ⚠️ Problema Attuale

**Lo script `start.sh` avvia solo il Gateway:**

```bash
# Da persan/scripts/start.sh
# Avvia Gateway (background)
cd "$PROJECT_DIR/packages/gateway"
nohup npx tsx --env-file=../../.env src/index.ts > "$GATEWAY_LOG" 2>&1 &

# Avvia Frontend (background)
cd "$PROJECT_DIR/frontend"
nohup npm run dev > "$FRONTEND_LOG" 2>&1 &
```

**Il Backend Python NON viene avviato!** Quindi:
- Tutte le chiamate vanno al Gateway (porta 3030)
- Il Backend Python (porta 8888) è inutilizzato
- Ma il suo codice esiste e potrebbe creare confusione

---

## 🎯 Opzioni per Risolvere

### Opzione A: Mantenere Solo Gateway (Consigliata nel piano)

**Pro:**
- Architettura più semplice
- Già in uso in produzione
- WebSocket funzionanti
- Redis per persistenza veloce

**Contro:**
- Perde integrazione con Me4Brain Working Memory API
- Sessioni solo su Redis (non sincronizzate con memoria Me4Brain)

### Opzione B: Mantenere Solo Backend Python

**Pro:**
- Sessioni su Me4Brain Working Memory (più "cervello centrale")
- Codice Python più facile da mantenere per team Python

**Contro:**
- Manca WebSocket
- Manca endpoint per config, turns, retry
- CORS restrittivo da fixare
- Non testato in produzione

### Opzione C: Gateway come Proxy + Backend Python per Logica

```
Frontend → Gateway:3030 → Backend Python:8888 → Me4Brain:8000
         (WebSocket)      (Business Logic)
```

**Pro:**
- Mantiene WebSocket nel Gateway
- Logica business in Python
- Separazione chiara

**Contro:**
- Architettura più complessa
- Latenza aggiuntiva
- Due codebase da mantenere

### Opzione D: Frontend → Me4Brain Diretto (Architettura "Pura")

```
Frontend → Me4Brain:8000/v1/*
```

**Pro:**
- Massima semplicità
- Me4Brain è il "cervello" unico
- Nessun layer intermedio

**Contro:**
- Perde funzionalità specifiche frontend (WebSocket, canali)
- Me4Brain non ha Redis per sessioni veloci
- Accoppiamento forte frontend-cervello

---

## 💡 Raccomandazione

Rispettando la filosofia **"Me4Brain = Cervello, PersAn = UX"**:

1. **Gateway TypeScript** rimane come **BFF (Backend for Frontend)**
   - Gestisce WebSocket, canali multipli, Redis per sessioni veloci
   - Proxy verso Me4Brain per l'elaborazione AI

2. **Backend Python** può essere:
   - **Rimosso** se non usato
   - **Oppure** trasformato in "Me4Brain Plugin" per logica specifica

3. **Me4Brain** rimane il **cervello centrale**
   - Tool Calling Engine
   - Memoria (Working, Episodic, Semantic)
   - Tutta l'intelligenza AI

Questa architettura rispetta la filosofia:
- Il cervello (Me4Brain) fa il "lavoro pesante"
- Il frontend (PersAn) fornisce l'esperienza utente
- Il Gateway è solo un "adattatore" tecnico per WebSocket/canali

---

**Analisi creata da:** Architect Mode  
**File salvato in:** `docs/reports/ARCHITECTURE_ANALYSIS_GATEWAY_VS_BACKEND.md`
