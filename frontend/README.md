# 🌈 jAI — AI Agent Platform (Progetto PersAn)

> Gateway TypeScript/Fastify per jAI con WebSocket real-time, multi-channel support e integrazione Me4BrAIn

---

## 📋 Quick Start

### Prerequisiti

| Requisito    | Versione | Note                    |
| ------------ | -------- | ----------------------- |
| **Node.js**  | 20+      | `node -v`               |
| **npm**      | 10+      | Incluso con Node.js     |
| **Docker**   | 24+      | Per infrastruttura      |
| **Me4BrAIn** | Running  | `http://localhost:8089` |

> [!CAUTION]
> **Ordine di avvio obbligatorio**: avvia sempre Me4BrAIn **prima** di PersAn.
> Le sessioni chat sono persistite in **Redis** (porta 6389, container Docker di Me4BrAIn).
> Se riavvii solo Me4BrAIn senza poi riavviare PersAn, le sessioni non saranno visibili dal frontend.
> ```bash
> # 1. Me4BrAIn (backend + Docker infra)
> bash ~/me4brain/scripts/start.sh
> # 2. PersAn (gateway + frontend)
> bash ~/persan/scripts/start.sh
> ```

### Setup Rapido

```bash
cd /Users/fulvioventura/persan

# 1. Installa dipendenze
npm install

# 2. Build tutti i packages
npm run build

# 3. Avvia dev (scelta)
npm run dev --filter=gateway     # Solo gateway
npm run dev --filter=frontend    # Solo frontend
```

---

## 🛠️ Development Workflow

### Workflow Raccomandato

| Fase                 | Comando                                    | Tempo           |
| -------------------- | ------------------------------------------ | --------------- |
| **Dev (hot-reload)** | `npm run dev --filter=gateway`             | 2-3s per change |
| **Test pre-commit**  | `npm run build && npm run lint`            | ~30s (cached)   |
| **Prod deploy**      | `docker compose --profile full up --build` | 5-10 min        |

### Scenario 1: Sviluppo Locale (Consigliato)

Esegui Gateway + Frontend in locale, usa Docker solo per infrastruttura:

```bash
# Terminal 1: Infrastruttura Docker
cd docker && docker compose -f docker-compose.gateway.yml up redis -d

# Terminal 2: Gateway (porta 3000)
npm run dev --filter=gateway

# Terminal 3: Frontend (porta 3020)
cd frontend && npm run dev

# Me4BrAIn deve essere già in esecuzione su localhost:8089
```

### Scenario 2: Tutto Docker

```bash
cd docker
docker compose -f docker-compose.gateway.yml up -d
```

### Scenario 3: Me4BrAIn Docker + Gateway Locale

```bash
# Avvia Me4BrAIn in Docker (da ~/me4brain/docker)
docker compose up -d

# Avvia Gateway locale
npm run dev --filter=gateway
```

---

## 🏗️ Architettura

```
persan/
├── packages/
│   ├── gateway/              # Fastify + WebSocket server (porta 3030)
│   ├── me4brain-client/      # SDK TypeScript per Me4BrAIn
│   └── shared/               # Tipi WS message protocol
├── frontend/                 # Next.js 15 + React 19 (porta 3020)
│   ├── src/lib/              # gateway-client.ts
│   └── src/hooks/            # useGateway.ts, useChat.ts
├── docker/
│   ├── docker-compose.gateway.yml
│   └── Dockerfile.gateway
└── turbo.json                # Turborepo config
```

### Flusso Dati

```
Frontend (3020) ──WebSocket──▶ Gateway (3030) ──HTTP/SSE──▶ Me4BrAIn (8089)
                                    │
                                    └──▶ Redis (sessioni)
```

---

## 🔌 API Endpoints

### HTTP

| Endpoint      | Metodo | Descrizione             |
| ------------- | ------ | ----------------------- |
| `/health`     | GET    | Health check            |
| `/ready`      | GET    | Readiness probe (k8s)   |
| `/api/status` | GET    | Status gateway + uptime |

### WebSocket `/ws`

#### Message Types

| Type            | Direction       | Descrizione          |
| --------------- | --------------- | -------------------- |
| `session:init`  | Server → Client | Session ID assegnato |
| `chat:message`  | Client → Server | Messaggio utente     |
| `chat:thinking` | Server → Client | AI sta elaborando    |
| `chat:response` | Server → Client | Risposta AI          |
| `error`         | Server → Client | Errore               |

#### Esempio

```typescript
const ws = new WebSocket('ws://localhost:3000/ws');

// Ricevi session ID
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'session:init') {
    console.log('Session:', msg.data.sessionId);
  }
};

// Invia messaggio
ws.send(JSON.stringify({
  type: 'chat:message',
  data: {
    content: 'Qual è il prezzo del Bitcoin?',
    channel: 'webchat'
  },
  timestamp: Date.now()
}));
```

---

## 🐳 Docker Configuration

### docker-compose.gateway.yml

| Service   | Porta | Descrizione         |
| --------- | ----- | ------------------- |
| `gateway` | 3030  | Fastify + WebSocket |
| `redis`   | 6389  | Session storage     |

### Environment Variables

```bash
# Gateway
NODE_ENV=development
PORT=3030
REDIS_URL=redis://localhost:6389
ME4BRAIN_URL=http://localhost:8089
LOG_LEVEL=info

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:3030
```

---

## 🔧 Frontend Integration

Il frontend Next.js è già integrato con il Gateway via:

- **`gateway-client.ts`**: Client WebSocket con auto-reconnection
- **`useGateway.ts`**: React hook per chat state management

### Utilizzo nel componente

```tsx
import { useGateway } from '@/hooks/useGateway';

function ChatPage() {
  const { 
    sendMessage, 
    isConnected, 
    connectionState 
  } = useGateway();

  return (
    <div>
      <span>Status: {connectionState}</span>
      <button onClick={() => sendMessage('Ciao!')}>
        Invia
      </button>
    </div>
  );
}
```

---

## ⚙️ Settings Panel

Il pannello impostazioni è accessibile dall'icona ⚙️ nell'header o dalla sidebar. Permette di configurare:

### Tab Disponibili

| Tab | Descrizione |
|-----|-------------|
| **LLM Models** | Selezione modelli primari, routing, synthesis, fallback |
| **Resources** | Monitoraggio risorse sistema (RAM, CPU, contesto) |
| **Advanced** | Configurazioni avanzate e debug |

### Configurazione Modelli

```typescript
// Hook per configurazione LLM
import { useLLMConfig, useAvailableModels } from '@/hooks/useSettings';

function ModelsConfig() {
  const { config } = useLLMConfig();
  const { models } = useAvailableModels();
  
  // models: AvailableModel[] con id, name, provider, context_window, etc.
  // config: LLMConfig con model_primary, model_routing, etc.
}
```

### Store Zustand

```typescript
import { useSettingsStore } from '@/stores/useSettingsStore';

// Azioni disponibili
const { 
  isOpen, 
  openSettings,    // Apre il pannello
  closeSettings,   // Chiude il pannello
  setActiveTab     // Cambia tab ('llm' | 'resources' | 'advanced')
} = useSettingsStore();
```

### Componenti

- `SettingsPanel.tsx` - Container modale con tab navigation
- `LLMModelsTab.tsx` - Selezione modelli con dropdown
- `ResourcesTab.tsx` - Gauge e bar per risorse sistema
- `AdvancedTab.tsx` - Configurazioni avanzate

---

## 🧪 Testing & Development

```bash
# Lint
npm run lint

# Type check
npm run typecheck

# Clean build
npm run clean

# Run tests (quando disponibili)
npm test
```

---

## 🐛 Troubleshooting

### Redis Connection Refused

```bash
# Avvia Redis via Docker
docker run -d -p 6379:6379 redis:7-alpine

# Oppure con brew
brew install redis && brew services start redis
```

### Me4BrAIn Non Raggiungibile

```bash
# Verifica che sia in esecuzione (uvicorn locale su porta 8089)
curl http://localhost:8089/health

# Se usi Docker, usa host.docker.internal
ME4BRAIN_URL=http://host.docker.internal:8089
```

### WebSocket Non Si Connette

1. Verifica che Gateway sia in esecuzione su porta 3030
2. Controlla firewall/proxy settings
3. Usa `ws://` (non `wss://`) in locale

### Neo4j Auth Failure

```bash
# Se password mismatch dopo cambio .env, resetta volume:
docker compose down -v
docker compose up neo4j -d
```

### Sessioni chat sparite dopo restart Me4BrAIn

Se la sidebar mostra zero sessioni dopo un riavvio:

1. **I dati sono salvi**: le sessioni risiedono in Redis, non in memoria
2. **Causa**: il gateway PersAn ha perso la connessione Redis
3. **Fix**: riavvia PersAn con `bash ~/persan/scripts/start.sh`
4. **Verifica**: `docker exec me4brain-redis redis-cli KEYS "persan:chat:*"`


---

## 🔔 Proactive Monitoring System

Sistema di monitoraggio proattivo con notifiche real-time, scheduling intelligente e valutazione parallela.

### Architettura

- **Scheduler**: BullMQ con Redis per job scheduling distribuito
- **Evaluator**: Engine di valutazione parallela con timeout handling
- **Notification**: WebSocket push per notifiche real-time
- **Monitor Manager**: Operazioni CRUD con validazione Zod

### Tipi di Monitor

| Tipo               | Descrizione                                 | Use Case                           |
| ------------------ | ------------------------------------------- | ---------------------------------- |
| **PRICE_WATCH**    | Monitoraggio prezzi stock/crypto con soglie | Alert quando AAPL < $150           |
| **SIGNAL_WATCH**   | Monitoraggio indicatori tecnici (RSI, MACD) | Alert su RSI < 30                  |
| **AUTONOMOUS**     | Decisioni trading autonome AI-powered       | Analisi multi-fattore per buy/sell |
| **SCHEDULED**      | Task schedulati con cron                    | Report giornaliero alle 9:00       |
| **EVENT_DRIVEN**   | Monitoraggio eventi trigger                 | Alert su breaking news             |
| **HEARTBEAT**      | Health check periodici                      | Verifica servizi ogni 5 min        |
| **TASK_REMINDER**  | Promemoria scadenze task                    | Alert 1h prima deadline            |
| **INBOX_WATCH**    | Monitoraggio inbox email                    | Alert su email importanti          |
| **CALENDAR_WATCH** | Monitoraggio eventi calendario              | Reminder meeting                   |
| **FILE_WATCH**     | Monitoraggio modifiche filesystem           | Alert su file changes              |

### API Endpoints

#### Crea Monitor

```bash
POST /api/monitors
Content-Type: application/json
x-user-id: {userId}

{
  "type": "PRICE_WATCH",
  "name": "AAPL Alert",
  "description": "Alert quando AAPL scende sotto $150",
  "config": {
    "ticker": "AAPL",
    "condition": "below",
    "threshold": 150
  },
  "interval_minutes": 5,
  "notify_channels": ["push"]
}
```

#### Lista Monitor

```bash
GET /api/monitors
x-user-id: {userId}
```

#### Dettagli Monitor

```bash
GET /api/monitors/:id
x-user-id: {userId}
```

#### Pausa Monitor

```bash
POST /api/monitors/:id/pause
x-user-id: {userId}
```

#### Riprendi Monitor

```bash
POST /api/monitors/:id/resume
x-user-id: {userId}
```

#### Trigger Manuale

```bash
POST /api/monitors/:id/trigger
x-user-id: {userId}
```

#### Elimina Monitor

```bash
DELETE /api/monitors/:id
x-user-id: {userId}
```

### Integrazione WebSocket

Connetti al WebSocket per ricevere notifiche real-time:

```javascript
const ws = new WebSocket('ws://localhost:3030/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'monitor:alert') {
    console.log('Monitor Alert:', data.data);
    // { monitorId, monitorName, title, message, recommendation, confidence }
  }
  
  if (data.type === 'monitor:update') {
    console.log('Monitor Update:', data.data);
    // { monitorId, state, lastCheck, nextCheck }
  }
};
```

### Configurazione

Variabili d'ambiente richieste:

```bash
# Redis (per BullMQ scheduler)
REDIS_URL=redis://localhost:6389

# Me4BrAIn (per valutazioni AI)
ME4BRAIN_API_URL=http://localhost:8000
ME4BRAIN_API_KEY=your-api-key

# Gateway
PORT=3030
```

### Sviluppo

Avvia il sistema di monitoraggio:

```bash
# 1. Avvia Redis (già incluso in Me4BrAIn Docker)
# Redis è disponibile su porta 6389

# 2. Avvia Gateway
cd packages/gateway
npm run dev

# 3. Avvia Frontend
cd frontend
npm run dev
```

### Monitoraggio & Observability

- **BullMQ Dashboard**: Visualizza job schedulati su `http://localhost:3030/admin/queues`
- **Logs**: Log strutturati JSON con Pino
- **WebSocket Status**: Verifica connessioni attive nel MonitorsPanel

### Esempio Completo

```typescript
// 1. Crea un monitor PRICE_WATCH
const monitor = await fetch('http://localhost:3030/api/monitors', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'x-user-id': 'user123'
  },
  body: JSON.stringify({
    type: 'PRICE_WATCH',
    name: 'Tesla Alert',
    description: 'Notifica quando TSLA supera $200',
    config: {
      ticker: 'TSLA',
      condition: 'above',
      threshold: 200
    },
    interval_minutes: 15,
    notify_channels: ['push']
  })
});

// 2. Connetti WebSocket per notifiche
const ws = new WebSocket('ws://localhost:3030/ws');
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === 'monitor:alert') {
    alert(`${msg.data.title}: ${msg.data.message}`);
  }
};

// 3. Monitor viene valutato ogni 15 minuti automaticamente
// 4. Ricevi notifica real-time quando TSLA > $200
```

---

## 📚 Documentazione Aggiuntiva


- [Fase 1: Gateway Foundation](docs/fase1_gateway_foundation.md)
- [WebSocket Protocol](docs/websocket_protocol.md)
- [Me4BrAIn Integration](docs/me4brain_integration.md)
