# 🚀 PersAn 2.0 — Piano Architetturale

**Versione**: 2.0  
**Data**: 2026-02-02  
**Obiettivo**: Evolvere PersAn da chatbot a **Personal AI Multi-Agent System**

---

## 1. Executive Summary

PersAn deve diventare un **assistente personale AI universale** ispirato a [OpenClaw](https://github.com/openclaw/openclaw), non più un semplice chatbot ma un sistema di agenti coordinati che gestisce **tutti i flussi di lavoro, ricerca e operatività** dell'utente.

### Evoluzione Proposta

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PERSAN 1.0 (Attuale)                         │
├─────────────────────────────────────────────────────────────────────┤
│  • Web chat React + SSE streaming                                   │
│  • Backend FastAPI → proxy verso Me4BrAIn                           │
│  • Nessuna multi-channel                                            │
│  • Nessuna automazione proattiva                                    │
│  • UI statica                                                       │
└─────────────────────────────────────────────────────────────────────┘
                                   ⬇️
┌─────────────────────────────────────────────────────────────────────┐
│                        PERSAN 2.0 (Proposto)                        │
├─────────────────────────────────────────────────────────────────────┤
│  • Gateway WebSocket (control plane unico)                          │
│  • Multi-Channel Hub (WhatsApp, Telegram, Slack, Discord, iMessage) │
│  • Voice Wake + Talk Mode (always-on speech)                        │
│  • Canvas A2UI (agent-driven visual workspace)                      │
│  • Skills Platform (modular agent capabilities)                     │
│  • Proactive Agent (scheduled tasks, webhooks, eventi)              │
│  • Browser Automation (CDP control)                                 │
│  • Mobile Nodes (iOS/Android companion apps)                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. User Review Required

> [!IMPORTANT]
> **Decisione Architetturale Critica**: Gateway Monolitico vs Microservizi
>
> ✅ **CONFERMATO: Monolitico**. Vedi sezione 2.1 per analisi dettagliata.

> [!NOTE]
> **Chiarimento Me4BrAIn**: Il backend Python FastAPI di PersAn (semplice proxy) viene **sostituito** dal Gateway Node.js. **Me4BrAIn rimane il cervello** — il Gateway lo chiama via SDK per memoria, tool execution e ragionamento. Vedi sezione 2.2.

> [!TIP]
> **UI/UX Design**: Confermato stile **macOS Tahoe con glassmorphism**. Vedi sezione 4.3 per mockup e design system.

### 2.1 Gateway Monolitico vs Microservizi (Approfondimento)

#### Confronto Dettagliato

| Criterio            | 🏛️ Monolitico (Raccomandato)                      | 🔀 Microservizi                            |
| ------------------- | ------------------------------------------------ | ----------------------------------------- |
| **Performance**     | ✅ Superiore: chiamate in-process, no network hop | ❌ Latenza aggiuntiva tra servizi          |
| **Complessità**     | ✅ Bassa: singolo codebase, deploy unico          | ❌ Alta: orchestrazione, service discovery |
| **Manutenibilità**  | ✅ Debug centralizzato, hot-reload facile         | ❌ Debugging distribuito, config drift     |
| **Fault Isolation** | ❌ Crash = tutto down                             | ✅ Crash isolato per servizio              |
| **Dev Speed**       | ✅ Veloce: nessun overhead coordinamento          | ❌ Lento: setup infra, API contracts       |
| **Scaling**         | ❌ Verticale (1 processo)                         | ✅ Orizzontale (per servizio)              |

#### Per Single-User Local-First (il nostro caso)

```
✅ MONOLITICO WINS perché:
• Deployment: 1 container, 1 processo
• Latenza: <5ms per routing interno
• Debug: Stack trace unico, log unificato
• Dev: 1 repo, 1 linguaggio, CI/CD semplice
```

#### Quando Microservizi avrebbero senso

```
❌ Non ora, ma in futuro SE:
• Multi-utente con >100 concurrent users
• Team >5 sviluppatori su componenti diversi
• Requisiti di isolamento (es. canale critico)
• Scaling indipendente (es. voice requires GPU)
```

#### Esempi Real-World

| Progetto         | Architettura | Motivazione                             |
| ---------------- | ------------ | --------------------------------------- |
| **OpenClaw**     | Monolitico   | Single-user, local-first, <10 servizi   |
| **Open WebUI**   | Monolitico   | Local LLM UI, zero distributed overhead |
| **Continue.dev** | Monolitico   | VS Code AI, priorità speed/simplicity   |
| **Jira** (post)  | Microservizi | Multi-tenant, team 100+, enterprise     |

**Decisione Finale**: Gateway Monolitico Node.js. Evoluzione a microservizi solo se necessario.

---

### 2.2 Ruolo di Me4BrAIn nella Nuova Architettura

**Me4BrAIn rimane il cervello backend**. Il Gateway è solo il "sistema nervoso" che gestisce I/O.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PersAn 2.0                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                    GATEWAY (Node.js)                               │    │
│  │                 "Sistema Nervoso" - I/O Layer                      │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐              │    │
│  │  │ WhatsApp │ │ Telegram │ │   Web    │ │  Voice   │  ← Canali    │    │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘              │    │
│  │       └────────────┴────────────┴────────────┘                     │    │
│  │                           │                                        │    │
│  │                    Message Normalization                           │    │
│  │                           │                                        │    │
│  │                    ┌──────▼──────┐                                 │    │
│  │                    │  Pi Agent   │ ← Orchestration locale          │    │
│  │                    └──────┬──────┘                                 │    │
│  └───────────────────────────┼────────────────────────────────────────┘    │
│                              │                                             │
│                              │ HTTP/SDK                                    │
│                              ▼                                             │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │                    ME4BRAIN (Python)                               │   │
│  │                    "Cervello" - Intelligence                       │   │
│  │  ┌──────────────────────────────────────────────────────────────┐ │   │
│  │  │  Working Memory │ Episodic │ Semantic │ Procedural (Tools)   │ │   │
│  │  └──────────────────────────────────────────────────────────────┘ │   │
│  │  ┌──────────────────────────────────────────────────────────────┐ │   │
│  │  │  Hybrid Router │ ReAct Loop │ LightRAG │ 118+ Tools          │ │   │
│  │  └──────────────────────────────────────────────────────────────┘ │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Cosa fa il Gateway (NON fa intelligenza)

| Responsabilità Gateway  | Dettaglio                              |
| ----------------------- | -------------------------------------- |
| ✅ Channel I/O           | Ricezione/invio messaggi multi-canale  |
| ✅ Message Normalization | Conversione formato → schema unificato |
| ✅ Session Management    | Stato sessione, auth, rate limiting    |
| ✅ Voice Processing      | STT/TTS (pre/post elaborazione)        |
| ✅ Canvas Rendering      | Push blocchi visuali al frontend       |
| ❌ **Ragionamento**      | → Delegato a Me4BrAIn                  |
| ❌ **Memoria**           | → Delegato a Me4BrAIn                  |
| ❌ **Tool Execution**    | → Delegato a Me4BrAIn                  |

#### Cosa fa Me4BrAIn (cervello immutato)

| Responsabilità Me4BrAIn | Dettaglio                             |
| ----------------------- | ------------------------------------- |
| ✅ Working Memory        | Context sessione, chat history        |
| ✅ Episodic Memory       | Ricordi personali, preferenze         |
| ✅ Semantic Memory       | Knowledge graph Neo4j                 |
| ✅ Procedural Memory     | 118+ tools, 14 domini                 |
| ✅ Hybrid Router         | BGE-M3 semantic tool selection        |
| ✅ ReAct Agent Loop      | Ragionamento iterativo + tool calling |
| ✅ LLM Orchestration     | NanoGPT (Kimi K2.5, Mistral Large)    |

#### Flow Esempio: "Analizza AAPL via Telegram"

```
1. Telegram → Gateway: "Analizza AAPL"
2. Gateway: normalize({channel: "telegram", text: "Analizza AAPL"})
3. Gateway → Me4BrAIn SDK: POST /v1/cognitive/chat/stream
4. Me4BrAIn: 
   ├── Hybrid Router → seleziona tools [fmp_key_metrics, technical_indicators]
   ├── ReAct Loop → esegue tools, raccoglie dati
   └── Synthesizer → genera risposta
5. Me4BrAIn → Gateway: SSE stream con risposta
6. Gateway → Telegram: invia messaggio formattato
```

> [!CAUTION]  
> **Effort Significativo**: L'evoluzione completa richiede **12 settimane** di sviluppo. Approccio incrementale per fasi.

---

## 3. Analisi Gap: PersAn vs OpenClaw

| Capability            | PersAn 1.0     | OpenClaw       | Gap     |
| --------------------- | -------------- | -------------- | ------- |
| Gateway Control Plane | ❌ Proxy HTTP   | ✅ WebSocket    | 🔴 Alto  |
| Multi-Channel         | ❌ Solo Web     | ✅ 12+ canali   | 🔴 Alto  |
| Voice Wake            | ❌ Nessuno      | ✅ Porcupine    | 🟡 Medio |
| Talk Mode             | ❌ Nessuno      | ✅ Continuo     | 🟡 Medio |
| Canvas/A2UI           | ❌ Nessuno      | ✅ Live Canvas  | 🟡 Medio |
| Skills Platform       | ❌ Hardcoded    | ✅ Bundled/WS   | 🔴 Alto  |
| Browser Automation    | ❌ Nessuno      | ✅ CDP Control  | 🟢 Basso |
| Proactive Execution   | ❌ Nessuno      | ✅ Cron/Webhook | 🟡 Medio |
| Mobile Nodes          | ❌ Nessuno      | ✅ iOS/Android  | 🔴 Alto  |
| Multi-Agent Routing   | ❌ Single Agent | ✅ Isolated WS  | 🔴 Alto  |

---

## 4. Architettura Proposta: PersAn 2.0

### 4.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             PERSAN 2.0 GATEWAY                              │
│                    (Node.js WebSocket Control Plane)                        │
│                         ws://127.0.0.1:18789                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  Sessions   │  │   Channels  │  │    Tools    │  │   Events    │        │
│  │   Manager   │  │   Manager   │  │   Manager   │  │   Broker    │        │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘        │
│         │                │                │                │                │
│         └────────────────┼────────────────┼────────────────┘                │
│                          │                │                                 │
│                    ┌─────┴─────┐    ┌─────┴─────┐                           │
│                    │  Pi Agent │    │  Skills   │                           │
│                    │  Runtime  │    │  Registry │                           │
│                    └─────┬─────┘    └───────────┘                           │
└──────────────────────────┼──────────────────────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
┌─────────────────┐ ┌───────────────┐ ┌───────────────┐
│   ME4BRAIN      │ │    NODES      │ │   CHANNELS    │
│   CORE API      │ │ (iOS/Android/ │ │ (WA/TG/Slack  │
│   Port: 8000    │ │  macOS/Linux) │ │  Discord/Web) │
└─────────────────┘ └───────────────┘ └───────────────┘
```

### 4.2 Core Components

#### 4.2.1 Gateway (New - Node.js)

Il **cuore** del nuovo sistema, ispirato al Gateway OpenClaw:

```typescript
// persan/gateway/src/gateway.ts
interface GatewayConfig {
  bind: "127.0.0.1:18789";
  auth: {
    mode: "local" | "password" | "tailscale";
    secret?: string;
  };
  channels: ChannelConfig[];
  agent: {
    model: "kimi-k2.5-free";  // via NanoGPT
    workspace: "~/.persan/workspace";
  };
}
```

**Funzionalità Core**:
- **WebSocket RPC**: Comunicazione real-time con tutti i client
- **Session Manager**: Gestione sessioni utente isolate
- **Channel Router**: Routing messaggi verso adapters
- **Tool Dispatcher**: Invocazione tools via Me4BrAIn
- **Event Broker**: Pub/sub per notifiche e trigger

#### 4.2.2 Channels Subsystem

> [!NOTE]
> **Scope Confermato**: Solo canali P1 nella prima release.

| Channel      | Libreria                  | Auth            | Priority | Status    |
| ------------ | ------------------------- | --------------- | -------- | --------- |
| **WebChat**  | Native WS                 | Session token   | 🔴 P1     | ✅ Incluso |
| **Telegram** | `grammy`                  | Bot token       | 🔴 P1     | ✅ Incluso |
| **WhatsApp** | `@whiskeysockets/baileys` | QR code pairing | 🔴 P1     | ✅ Incluso |
| Slack        | `@slack/bolt`             | OAuth2          | 🟡 P2     | ⏳ Future  |
| Discord      | `discord.js`              | Bot token       | 🟡 P2     | ⏳ Future  |
| iMessage     | `imsg` (macOS only)       | System access   | 🟢 P3     | ⏳ Future  |

**Message Flow**:
```
Channel Adapter → Normalize Message → Gateway → Me4BrAIn → Response → Channel Adapter
```

#### 4.2.3 Pi Agent Runtime

L'**agente intelligente** che esegue ragionamento e tool calling:

```typescript
// persan/gateway/src/agent/runtime.ts
class PiAgentRuntime {
  private model: string = "kimi-k2.5-free";
  private me4brain: Me4BrAInClient;
  
  async process(session: Session, message: NormalizedMessage): Promise<AgentResponse> {
    // 1. Context retrieval from Me4BrAIn
    const context = await this.me4brain.memory.query(message.text);
    
    // 2. Tool calling via ReAct loop
    const toolResults = await this.me4brain.engine.execute({
      query: message.text,
      context,
      session_id: session.id
    });
    
    // 3. Synthesize response
    return this.synthesize(toolResults);
  }
}
```

#### 4.2.4 Skills Platform

Sistema modulare di capabilities, ispirato a OpenClaw:

```
~/.persan/
├── workspace/
│   ├── AGENTS.md          # Agent personality/instructions
│   ├── SOUL.md            # Deep personality traits
│   ├── TOOLS.md           # Available tools description
│   └── skills/
│       ├── finance/
│       │   └── SKILL.md   # Finance analysis skill
│       ├── research/
│       │   └── SKILL.md   # Academic research skill
│       └── automation/
│           ├── SKILL.md   # Browser automation skill
│           └── scripts/
│               └── linkedin_search.js
```

**SKILL.md Format**:
```yaml
---
name: finance-analyst
description: Analisi finanziaria avanzata con indicatori tecnici
tools: [fmp_key_metrics, technical_indicators, news_search]
---

# Finance Analyst Skill

Questo skill fornisce analisi finanziaria completa...

## Capabilities
1. Fundamental analysis (P/E, ROE, DCF)
2. Technical indicators (RSI, MACD, Bollinger)
3. News sentiment analysis
```

#### 4.2.5 Voice Subsystem

**Wake Word + Talk Mode** per interazione vocale:

```typescript
// persan/gateway/src/voice/talk_mode.ts
class TalkModeController {
  private porcupine: PorcupineWorker;  // Wake word detection
  private stt: SpeechToText;            // Web Speech API
  private tts: TextToSpeech;            // ElevenLabs/native
  
  async activate(): Promise<void> {
    await this.porcupine.listen("hey fulvio");
    this.startContinuousConversation();
  }
  
  private async startContinuousConversation(): Promise<void> {
    while (this.isActive) {
      const userSpeech = await this.stt.listen();
      const response = await this.gateway.sendToAgent(userSpeech);
      await this.tts.speak(response);
    }
  }
}
```

#### 4.2.6 Canvas A2UI

**Agent-driven visual workspace**:

```typescript
// persan/frontend/src/components/Canvas.tsx
interface CanvasBlock {
  id: string;
  type: "chart" | "table" | "card" | "code" | "image" | "custom";
  data: unknown;
  position: { x: number; y: number };
  size: { width: number; height: number };
}

class CanvasController {
  // L'agente può modificare il Canvas in tempo reale
  async pushBlock(block: CanvasBlock): Promise<void> {
    this.ws.send({ type: "canvas.push", block });
  }
  
  async updateBlock(id: string, data: Partial<CanvasBlock>): Promise<void> {
    this.ws.send({ type: "canvas.update", id, data });
  }
}
```

**Use Cases** (universale, non solo finanza):
- 📊 Visualizzazioni dati e grafici interattivi
- 📝 Note, documenti e risultati ricerca
- 💻 Code preview e snippet in tempo reale
- 📋 Tabelle dati strutturate
- 🗺️ Mappe e contenuti geografici
- 🖼️ Immagini e media generati
- 🌐 Web preview e embed

#### 4.2.7 Proactive Agent System (Monitoraggio Autonomo)

> [!NOTE]
> **Ispirazione OpenClaw**: Questa architettura si ispira direttamente al sistema di automazione OpenClaw che include:
> - **[Cron + wakeups](https://docs.openclaw.ai/automation/cron-jobs)**: Task schedulati ricorrenti
> - **[Webhooks](https://docs.openclaw.ai/automation/webhook)**: Trigger event-driven da servizi esterni
> - **[Gmail Pub/Sub](https://docs.openclaw.ai/automation/gmail-pubsub)**: React a email in tempo reale
>
> **Integrazione Me4BrAIn**: Il Proactive Agent **non duplica** la logica di Me4BrAIn. Invece:
> - **Gateway** gestisce: scheduling, state persistence, notification dispatch
> - **Me4BrAIn** gestisce: tool execution (finanza, news), memoria episodica, ragionamento LLM
>
> In pratica: il Gateway è il "timer + notificatore", Me4BrAIn è il "cervello che valuta".

> **Esempio Utente**: "Monitora AAPL finché non valuti il momento per acquistarlo/venderlo"

Questo è il **cuore dell'evoluzione agentica**. Non più solo rispondere a domande, ma **agire autonomamente** nel tempo.

##### Architettura Proactive Agent

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PROACTIVE AGENT SYSTEM                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────┐                                                    │
│  │   USER REQUEST      │ "Monitora AAPL finché non è il momento di          │
│  │   (Intent Capture)  │  acquistare/vendere"                               │
│  └──────────┬──────────┘                                                    │
│             │                                                               │
│             ▼                                                               │
│  ┌─────────────────────┐                                                    │
│  │   GOAL PARSER       │ Estrae:                                            │
│  │   (LLM Analysis)    │ • ticker: AAPL                                     │
│  │                     │ • condition: buy/sell signal                       │
│  │                     │ • duration: indefinito (until condition)           │
│  └──────────┬──────────┘                                                    │
│             │                                                               │
│             ▼                                                               │
│  ┌─────────────────────┐      ┌─────────────────────────────────────────┐  │
│  │   MONITOR REGISTRY  │◄────►│              REDIS                       │  │
│  │   (Persistent)      │      │  • monitors:{id}:config                  │  │
│  │                     │      │  • monitors:{id}:history                 │  │
│  └──────────┬──────────┘      │  • monitors:{id}:state                   │  │
│             │                 └─────────────────────────────────────────┘  │
│             ▼                                                               │
│  ┌─────────────────────┐      ┌─────────────────────────────────────────┐  │
│  │   SCHEDULER         │◄────►│          BullMQ (Job Queue)              │  │
│  │   (APScheduler-like)│      │  • Recurring jobs                        │  │
│  │                     │      │  • Retry on failure                      │  │
│  └──────────┬──────────┘      │  • Backoff strategy                      │  │
│             │                 └─────────────────────────────────────────┘  │
│             │                                                               │
│             ▼ (ogni 15 min)                                                 │
│  ┌─────────────────────┐                                                    │
│  │   EVALUATION LOOP   │                                                    │
│  │   ┌───────────────┐ │      ┌─────────────────────────────────────────┐  │
│  │   │ 1. Fetch Data │ │─────►│         ME4BRAIN API                     │  │
│  │   │    (Me4BrAIn) │ │      │  • technical_indicators(AAPL)            │  │
│  │   └───────┬───────┘ │      │  • fmp_key_metrics(AAPL)                 │  │
│  │           │         │      │  • news_search(AAPL)                     │  │
│  │   ┌───────▼───────┐ │      └─────────────────────────────────────────┘  │
│  │   │ 2. Evaluate   │ │                                                    │
│  │   │    Condition  │ │  LLM valuta: "È il momento giusto?"                │
│  │   └───────┬───────┘ │                                                    │
│  │           │         │                                                    │
│  │   ┌───────▼───────┐ │                                                    │
│  │   │ 3. Decision   │ │  → CONTINUE: aspetta prossimo ciclo                │
│  │   │    Engine     │ │  → TRIGGER: notifica + azione                      │
│  │   └───────────────┘ │  → ABORT: condizione impossibile                   │
│  └─────────────────────┘                                                    │
│             │                                                               │
│             ▼ (se TRIGGER)                                                  │
│  ┌─────────────────────┐                                                    │
│  │   ACTION EXECUTOR   │ Opzioni:                                           │
│  │                     │ • notify_user (Telegram/WhatsApp/Web)              │
│  │                     │ • execute_trade (via broker API)                   │
│  │                     │ • update_canvas (push chart)                       │
│  └─────────────────────┘                                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

##### Tipi di Monitor Supportati

| Tipo             | Trigger                  | Esempio                                       |
| ---------------- | ------------------------ | --------------------------------------------- |
| **Price Watch**  | Prezzo supera soglia     | "Avvisami se AAPL scende sotto $180"          |
| **Signal Watch** | Indicatore tecnico       | "Monitora RSI AAPL, avvisa se <30 (oversold)" |
| **Autonomous**   | Valutazione LLM continua | "Valuta quando comprare/vendere AAPL"         |
| **Scheduled**    | Cron-based               | "Ogni lunedì analizza il mio portafoglio"     |
| **Event-Driven** | Webhook/email trigger    | "Quando arriva email da broker, analizza"     |

##### Implementazione: Monitor "Valuta quando comprare AAPL"

```typescript
// persan/gateway/src/proactive/monitors/stock_advisor.ts

interface StockAdvisorMonitor {
  id: string;
  ticker: string;
  goal: "buy" | "sell" | "both";
  userId: string;
  notifyChannel: "telegram" | "whatsapp" | "web" | "all";
  createdAt: Date;
  state: {
    lastCheck: Date;
    checksCount: number;
    history: EvaluationResult[];
  };
}

class StockAdvisorMonitor {
  private me4brain: Me4BrAInClient;
  private llm: NanoGPTClient;
  
  async evaluate(monitor: StockAdvisorMonitor): Promise<EvaluationResult> {
    // 1. Recupera dati freschi da Me4BrAIn
    const [technicals, fundamentals, news] = await Promise.all([
      this.me4brain.engine.execute({
        query: `technical_indicators ${monitor.ticker}`,
        domains: ["finance_crypto"]
      }),
      this.me4brain.engine.execute({
        query: `fmp_key_metrics ${monitor.ticker}`,
        domains: ["finance_crypto"]
      }),
      this.me4brain.engine.execute({
        query: `news ${monitor.ticker}`,
        domains: ["web_search"]
      })
    ]);
    
    // 2. Chiedi all'LLM di valutare
    const evaluation = await this.llm.generate({
      model: "kimi-k2.5-free",
      prompt: `
        Sei un advisor finanziario. Analizza questi dati per ${monitor.ticker}:
        
        ## Indicatori Tecnici
        ${JSON.stringify(technicals.data)}
        
        ## Fondamentali
        ${JSON.stringify(fundamentals.data)}
        
        ## News Recenti
        ${JSON.stringify(news.data)}
        
        L'utente vuole sapere se è il momento di ${monitor.goal}.
        
        Rispondi in JSON:
        {
          "recommendation": "BUY" | "SELL" | "HOLD" | "WAIT",
          "confidence": 0-100,
          "reasoning": "spiegazione breve",
          "keyFactors": ["factor1", "factor2"],
          "suggestedAction": "descrizione azione"
        }
      `
    });
    
    // 3. Decidi se triggerare
    const result = JSON.parse(evaluation);
    
    if (result.recommendation !== "WAIT" && result.confidence >= 70) {
      await this.trigger(monitor, result);
      return { action: "TRIGGERED", ...result };
    }
    
    return { action: "CONTINUE", ...result };
  }
  
  private async trigger(monitor: StockAdvisorMonitor, result: any): Promise<void> {
    const message = `
🔔 **Alert ${monitor.ticker}**

📊 Raccomandazione: **${result.recommendation}**
📈 Confidenza: ${result.confidence}%

**Motivazione**: ${result.reasoning}

**Fattori chiave**:
${result.keyFactors.map(f => `• ${f}`).join('\n')}

**Azione suggerita**: ${result.suggestedAction}
    `;
    
    // Notifica su tutti i canali configurati
    await this.gateway.notify(monitor.userId, monitor.notifyChannel, message);
    
    // Opzionale: push chart sul Canvas
    await this.gateway.canvas.push(monitor.userId, {
      type: "chart",
      data: { ticker: monitor.ticker, recommendation: result.recommendation }
    });
  }
}
```

##### Flow Completo: "Monitora AAPL"

```
Utente (Telegram): "Monitora AAPL finché non valuti il momento per comprarlo"
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. INTENT PARSING                                                        │
│    Gateway → Me4BrAIn: analyze_query                                     │
│    Output: {intent: "create_monitor", ticker: "AAPL", goal: "buy"}       │
└─────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. MONITOR CREATION                                                      │
│    Gateway: createMonitor(StockAdvisorMonitor)                           │
│    Redis: SET monitors:uuid-123:config {...}                             │
│    BullMQ: scheduleRecurring("evaluate-aapl", "*/15 * * * *")           │
└─────────────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. IMMEDIATE RESPONSE                                                    │
│    Gateway → Telegram: "✅ Monitoraggio AAPL attivato!                   │
│                         Ti avviserò quando sarà il momento di comprare.  │
│                         Controllo ogni 15 minuti."                       │
└─────────────────────────────────────────────────────────────────────────┘
      │
      ▼ (background, ogni 15 min)
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. EVALUATION LOOP (24/7)                                                │
│    BullMQ worker → StockAdvisorMonitor.evaluate()                        │
│    │                                                                     │
│    ├─ Check 1 (09:00): RSI=65, P/E ok, news neutro → WAIT (conf: 45%)   │
│    ├─ Check 2 (09:15): RSI=58, volume up → WAIT (conf: 52%)             │
│    ├─ Check 3 (09:30): RSI=35, price drop -3% → WAIT (conf: 68%)        │
│    └─ Check 4 (09:45): RSI=28, oversold, news positive → BUY! (conf: 85%) │
└─────────────────────────────────────────────────────────────────────────┘
      │
      ▼ (confidence >= 70%)
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. TRIGGER NOTIFICATION                                                  │
│    Gateway → Telegram: "🔔 Alert AAPL - Raccomandazione: BUY (85%)"      │
│    Gateway → Canvas: push chart con entry point                          │
│    Redis: UPDATE monitors:uuid-123:state {triggered: true}               │
└─────────────────────────────────────────────────────────────────────────┘
```

##### Gestione via Comandi

```
/monitors list              → Lista monitor attivi
/monitors status aapl       → Status monitoraggio AAPL
/monitors pause aapl        → Pausa temporanea
/monitors stop aapl         → Cancella monitoraggio
/monitors history aapl      → Storico valutazioni
```

##### Stack Tecnologico Proactive System

| Componente       | Tecnologia    | Ruolo                                     |
| ---------------- | ------------- | ----------------------------------------- |
| Scheduler        | BullMQ        | Job queue con retry, backoff, concurrency |
| State Store      | Redis         | Monitor config, history, state            |
| Evaluation Logic | Me4BrAIn      | Tool execution (finance, news)            |
| Decision Engine  | LLM (NanoGPT) | Valutazione reasoning-based               |
| Notification     | Gateway       | Multi-channel dispatch                    |

---

### 4.3 UI/UX Design System

> [!TIP]
> **Stile Confermato**: macOS Tahoe con glassmorphism. Esperienza nativa Apple su tutte le piattaforme.

#### Design Philosophy

| Principio           | Descrizione                                    |
| ------------------- | ---------------------------------------------- |
| **Apple HIG**       | Aderenza alle Human Interface Guidelines       |
| **Glassmorphism**   | Effetti vetro frosted con blur e trasparenza   |
| **Dark Mode First** | Ottimizzato per OLED e comfort visivo          |
| **Agent-Centric**   | L'AI è protagonista, UI risponde dinamicamente |

#### Color Palette

| Nome              | Hex                           | Uso                   |
| ----------------- | ----------------------------- | --------------------- |
| **System Gray 6** | `#1c1c1e`                     | Background principale |
| **System Gray 5** | `#2c2c2e`                     | Cards, panels         |
| **System Gray 4** | `#3c3c3e`                     | Bordi, divider        |
| **Apple Blue**    | `#0a84ff`                     | Accenti, user bubbles |
| **Glass Fill**    | `rgba(255,255,255,0.1)`       | Glassmorphism panels  |
| **Vibrancy**      | `backdrop-filter: blur(20px)` | Sidebar, toolbar      |

#### Mockup Desktop

![Desktop Tahoe](/Users/fulvioventura/.gemini/antigravity/brain/d788a677-0df8-4d7c-99d2-7ac4a31badb6/persan_tahoe_desktop_1770063841046.png)

**Caratteristiche**:
- 🚦 Traffic lights (semaforo finestra)
- 🪟 Sidebar vibrancy con blur traslucido
- 💬 iMessage-style bubbles (blu utente, glass AI)
- 📊 Canvas universale con pannelli glassmorphism

#### Mockup Mobile (iOS)

![Mobile Tahoe](/Users/fulvioventura/.gemini/antigravity/brain/d788a677-0df8-4d7c-99d2-7ac4a31badb6/persan_tahoe_mobile_1770063856927.png)

**Caratteristiche**:
- 📱 Large title navigation
- 💬 Chat bubbles con glass effect
- 🎤 Voice bar con glassmorphism
- 🌊 Background gradient visibile attraverso elementi

#### Mockup Canvas Universale

![Canvas Tahoe](/Users/fulvioventura/.gemini/antigravity/brain/d788a677-0df8-4d7c-99d2-7ac4a31badb6/persan_tahoe_canvas_1770063875417.png)

**Tipi di Blocco**:
| Icona | Tipo  | Descrizione                       |
| ----- | ----- | --------------------------------- |
| 📝     | Text  | Note, markdown, documenti         |
| 📊     | Chart | Grafici line, bar, candlestick    |
| 📋     | Table | Dati tabulari, spreadsheet-like   |
| 💻     | Code  | Snippets con syntax highlighting  |
| 🖼️     | Image | Immagini, screenshot, generazioni |
| 🌐     | Web   | Embed URL, preview pagine         |

#### Typography

| Elemento | Font           | Weight         |
| -------- | -------------- | -------------- |
| Titoli   | SF Pro Display | Semibold (600) |
| Body     | SF Pro Text    | Regular (400)  |
| Code     | SF Mono        | Regular (400)  |
| UI       | SF Pro Text    | Medium (500)   |

#### Glassmorphism CSS

```css
.glass-panel {
  background: rgba(28, 28, 30, 0.7);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
}

.glass-sidebar {
  background: rgba(44, 44, 46, 0.5);
  backdrop-filter: blur(40px);
}
```

---

## 5. Integrazione con Me4BrAIn

### 5.1 Connessione via SDK

```typescript
// persan/gateway/src/me4brain/client.ts
import { Me4BrAInClient } from "@me4brain/sdk";

const client = new Me4BrAInClient({
  baseUrl: process.env.ME4BRAIN_URL || "http://localhost:8000",
  tenant: "persan",
  apiKey: process.env.ME4BRAIN_API_KEY
});

// Memory operations
await client.memory.ingest({ content: "...", type: "episodic" });
const context = await client.memory.query("...");

// Tool operations
const result = await client.engine.execute({
  query: "Analizza AAPL",
  domains: ["finance_crypto"]
});
```

### 5.2 Backend Capabilities (da Me4BrAIn)

| Layer             | Funzionalità                                   |
| ----------------- | ---------------------------------------------- |
| Working Memory    | Session context, chat history                  |
| Episodic Memory   | Personal facts, preferences, past interactions |
| Semantic Memory   | Knowledge graph, entity relationships          |
| Procedural Memory | 118+ tools across 14 domains                   |

### 5.3 Multi-Domain Query Flow

```
User: "Confronta Tesla con meteo California per vacanza"
          │
          ▼
┌─────────────────────────────────┐
│         PersAn Gateway           │
│    (Multi-Domain Orchestrator)   │
└──────────────┬──────────────────┘
               │ asyncio.gather()
    ┌──────────┼──────────┐
    ▼          ▼          ▼
┌───────┐ ┌───────┐ ┌───────┐
│Finance│ │Weather│ │Travel │
│Domain │ │Domain │ │Domain │
└───────┘ └───────┘ └───────┘
    │          │          │
    └──────────┼──────────┘
               ▼
       Aggregated Response
```

---

## 6. Stack Tecnologico Proposto

### Gateway (New)

| Componente | Tecnologia           | Motivazione                    |
| ---------- | -------------------- | ------------------------------ |
| Runtime    | Node.js 20+ LTS      | Async I/O, WebSocket nativo    |
| Framework  | Fastify              | Performance, WebSocket support |
| WebSocket  | `@fastify/websocket` | Real-time communication        |
| Queue      | BullMQ + Redis       | Job scheduling, rate limiting  |
| State      | Redis                | Session state, caching         |

### Frontend (Evoluzione)

| Componente | Tecnologia          | Cambiamento                      |
| ---------- | ------------------- | -------------------------------- |
| Framework  | Next.js 15          | ✅ Mantiene                       |
| Styling    | Tailwind CSS        | ✅ Mantiene                       |
| State      | Zustand             | ✅ Mantiene                       |
| Transport  | **WebSocket** (new) | 🔄 Da HTTP/SSE a WS               |
| Voice      | Web Speech API      | 🆕 Nuovo                          |
| Canvas     | **Custom A2UI**     | 🆕 Nuovo                          |
| **Design** | **macOS Native**    | 🆕 Apple HIG, System Gray, SF Pro |

### Mobile Nodes (Future)

| Piattaforma | Framework       | Priority |
| ----------- | --------------- | -------- |
| iOS         | Swift + SwiftUI | P3       |
| Android     | Kotlin Compose  | P3       |
| macOS       | Electron/Tauri  | P2       |

---

## 7. Roadmap Fasi

### Fase 0: Fondazione Gateway (2 settimane)

```
Settimana 1-2
├── Gateway WebSocket base
├── Session manager
├── Me4BrAIn SDK TypeScript
└── WebChat adapter (migrare da HTTP a WS)
```

**Deliverable**: Web chat funzionante via WebSocket

---

### Fase 1: Multi-Channel Core (3 settimane)

```
Settimana 3-4
├── Telegram adapter
├── WhatsApp adapter (Baileys)
└── Unified message format

Settimana 5
├── Slack adapter
├── Discord adapter
└── Channel configuration UI
```

**Deliverable**: Messaggistica su 5 canali

---

### Fase 2: Voice & Talk Mode (2 settimane)

```
Settimana 6
├── Speech-to-Text (Web Speech API)
├── Text-to-Speech (native + ElevenLabs)
└── Voice button component

Settimana 7
├── Wake word (Porcupine)
├── Talk Mode continuous conversation
└── PWA manifest per mobile
```

**Deliverable**: Interazione vocale completa

---

### Fase 3: Canvas & A2UI (2 settimane)

```
Settimana 8
├── Canvas component base
├── Block types (chart, table, card, code)
└── Agent → Canvas push API

Settimana 9
├── Interactive blocks (drag, resize)
├── Canvas state persistence
└── Template presets
```

**Deliverable**: Visual workspace dinamico

---

### Fase 4: Skills Platform (2 settimane)

```
Settimana 10
├── Skills registry
├── SKILL.md parser
├── Bundled skills (finance, research, automation)

Settimana 11
├── Skill installation UI
├── Workspace skill management
└── Skill dependencies resolution
```

**Deliverable**: Sistema skill modulare

---

### Fase 5: Proactive Agent (1 settimana)

```
Settimana 12
├── Cron scheduler
├── Webhook triggers
├── Event-based automation
└── Alert system
```

**Deliverable**: Esecuzione autonoma schedulata

---

## 8. Struttura Directory Proposta

```
persan/
├── gateway/                      # 🆕 Node.js Gateway
│   ├── src/
│   │   ├── index.ts              # Entry point
│   │   ├── gateway.ts            # WebSocket server
│   │   ├── config/
│   │   │   └── persan.yaml       # Configuration
│   │   ├── channels/
│   │   │   ├── manager.ts
│   │   │   ├── whatsapp/
│   │   │   ├── telegram/
│   │   │   ├── slack/
│   │   │   ├── discord/
│   │   │   └── webchat/
│   │   ├── agent/
│   │   │   ├── runtime.ts        # Pi Agent
│   │   │   ├── session.ts
│   │   │   └── tools.ts
│   │   ├── voice/
│   │   │   ├── stt.ts
│   │   │   ├── tts.ts
│   │   │   └── wake.ts
│   │   ├── proactive/
│   │   │   ├── scheduler.ts
│   │   │   └── triggers.ts
│   │   ├── skills/
│   │   │   ├── registry.ts
│   │   │   └── parser.ts
│   │   └── me4brain/
│   │       └── client.ts         # Me4BrAIn SDK
│   ├── package.json
│   └── tsconfig.json
│
├── frontend/                      # React UI (evoluzione)
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   │   ├── chat/             # WebSocket chat
│   │   │   ├── canvas/           # 🆕 A2UI Canvas
│   │   │   ├── voice/            # 🆕 Voice UI
│   │   │   └── channels/         # 🆕 Channel management
│   │   ├── hooks/
│   │   │   └── useGateway.ts     # 🆕 WS connection
│   │   └── lib/
│   │       └── gateway-client.ts # 🆕 Gateway SDK
│   └── package.json
│
├── workspace/                     # 🆕 Agent workspace
│   ├── AGENTS.md
│   ├── SOUL.md
│   ├── TOOLS.md
│   └── skills/
│
├── backend/                       # ⚠️ DEPRECATED → Gateway
│   └── (legacy, da rimuovere)
│
├── docs/
│   └── architecture/
│       └── blueprint_persan_v2.md
│
└── docker-compose.yml
```

---

## 9. Verification Plan

### Automated Tests

```bash
# Gateway unit tests
cd gateway && npm test

# Integration tests
npm run test:integration

# E2E multi-channel test
npm run test:e2e
```

**Test Cases Critici**:
1. WebSocket connection lifecycle
2. Multi-channel message routing (5 canali)
3. Me4BrAIn tool execution via gateway
4. Voice STT/TTS round-trip
5. Canvas block push/update
6. Skill loading and execution
7. Proactive task scheduling

### Manual Verification

1. **Browser**: Chat WebSocket con voice toggle
2. **Telegram**: Invia messaggio, ricevi risposta
3. **WhatsApp**: QR pairing + test conversazione
4. **Voice**: "Hey Fulvio" → domanda → risposta audio
5. **Canvas**: Agente pushes chart dinamicamente

---

## 10. Risk Assessment

| Risk                                 | Probabilità | Impatto | Mitigazione                           |
| ------------------------------------ | ----------- | ------- | ------------------------------------- |
| WhatsApp ban (Baileys non ufficiale) | Media       | Alto    | Alternative: WA Business API, Twillio |
| Complessità Gateway                  | Media       | Medio   | Sviluppo incrementale per fasi        |
| Breaking change frontend             | Alta        | Medio   | Astrazione WS client, feature flags   |
| Performance voice su mobile          | Bassa       | Medio   | Web Speech API fallback               |

---

## 11. Timeline Summary

| Fase | Descrizione        | Durata      | Effort |
| ---- | ------------------ | ----------- | ------ |
| 0    | Gateway Foundation | 2 settimane | Alto   |
| 1    | Multi-Channel Core | 3 settimane | Alto   |
| 2    | Voice & Talk Mode  | 2 settimane | Medio  |
| 3    | Canvas & A2UI      | 2 settimane | Medio  |
| 4    | Skills Platform    | 2 settimane | Medio  |
| 5    | Proactive Agent    | 1 settimana | Basso  |

**Totale**: **12 settimane** (~3 mesi)

---

## 12. Decisioni Confermate & Domande Aperte

### ✅ Decisioni Confermate

| Area              | Decisione                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | **Can Canali P1** | WebChat + Telegram + WhatsApp  |
| **UI/UX**         | - [/] Phase 3: Canvas & A2UI
    - [x] Implementation of `useCanvasStore`
    - [x] Creation of `Canvas` and `CanvasBlock` components
    - [x] Specialized blocks (`Chart`, `Table`, `Code`, `Text`)
    - [/] UI Refactoring (macOS Tahoe Design)
        - [x] Deep Glassmorphism & Mesh Gradients
        - [x] iMessage Bubble Revamp (with tails and Apple Blue gradients)
        - [/] Fine-tuning vibrancy and layout
    - [/] Real-time Sync Integration (Gateway)
- [/] Critical Maintenance
    - [/] Resolve ONNX Build Error (preserving Whisper functionality)
    - [x] Restore `useVoice.ts` logic
|
| **Canvas**        | Universale (non solo finanza)  |
| **Design System** | Apple HIG, System Gray, SF Pro |

### ❓ Domande Aperte — Analisi Dettagliata

---

#### 1. Gateway Runtime: Node.js vs Alternative

Il Gateway è il cuore del sistema, quindi la scelta del runtime è fondamentale. Abbiamo tre opzioni principali:

**Opzione A: Node.js 20+ LTS con Fastify** ⭐ Raccomandato

Node.js è la scelta più conservativa e pragmatica. È il runtime più maturo per applicazioni real-time, con un ecosistema vastissimo e documentazione abbondante.

| Pro                                      | Contro                        |
| ---------------------------------------- | ----------------------------- |
| ✅ Ecosistema gigantesco (npm)            | ❌ Single-threaded (CPU bound) |
| ✅ Fastify è il framework più veloce      | ❌ `node_modules` pesante      |
| ✅ Tutte le librerie canali esistono      | ❌ Startup più lento di Bun    |
| ✅ Debugging eccellente (Chrome DevTools) |                               |
| ✅ LTS = stabilità enterprise             |                               |

**Opzione B: Bun**

Bun è il nuovo runtime JavaScript che promette performance native e startup istantaneo. È scritto in Zig ed è compatibile con l'ecosistema npm.

| Pro                             | Contro                            |
| ------------------------------- | --------------------------------- |
| ✅ 4x più veloce di Node.js      | ❌ Meno maturo (v1.0 recente)      |
| ✅ Bundler/test runner integrato | ❌ Alcune API non complete         |
| ✅ Startup istantaneo (<100ms)   | ❌ Meno community/docs             |
| ✅ TypeScript nativo             | ❌ Possibili edge case non testati |

**Opzione C: Deno**

Deno è l'alternativa "secure by default" creata dallo stesso autore di Node.js (Ryan Dahl). Ha un approccio più moderno ma un ecosistema più piccolo.

| Pro                              | Contro                                     |
| -------------------------------- | ------------------------------------------ |
| ✅ TypeScript nativo              | ❌ Ecosistema piccolo                       |
| ✅ Security by default            | ❌ Molte librerie npm non funzionano        |
| ✅ URL imports (no node_modules)  | ❌ Curva di apprendimento                   |
| ✅ Deploy integrato (Deno Deploy) | ❌ Grammy/Baileys potrebbero avere problemi |

**La mia raccomandazione**: **Node.js + Fastify**. È la scelta più sicura per un progetto complesso con integrazioni multiple (Telegram, WhatsApp, WebSocket). Possiamo sempre migrare a Bun in futuro quando sarà più maturo, dato che è compatibile.

---

#### 2. Voice TTS: Soluzione Gratuita e Professionale

La sintesi vocale (Text-to-Speech) è fondamentale per il Talk Mode. La scelta impatta qualità, costi e latenza.

> [!NOTE]
> **Come fa OpenClaw**: OpenClaw usa **ElevenLabs** come provider principale per TTS, con configurazione in `~/.openclaw/openclaw.json`. Supporta voice cloning, interruzione su speech, e streaming PCM.

**Opzione A: Web Speech API** (Browser Native)

L'API browser standard, gratuita e senza dipendenze esterne.

| Pro                       | Contro                            |
| ------------------------- | --------------------------------- |
| ✅ Completamente gratuita  | ❌ Voce robotica, poco naturale    |
| ✅ Zero latenza di rete    | ❌ Qualità varia tra browser       |
| ✅ Funziona offline        | ❌ Poche voci italiane decenti     |
| ✅ Privacy totale (locale) | ❌ Nessun controllo su intonazione |

**Opzione B: Piper TTS** (Open Source Self-Hosted) ⭐ RACCOMANDATO

Piper è un TTS open source ottimizzato per speed e qualità. Funziona completamente offline e supporta 30+ lingue con voci naturali.

| Pro                                          | Contro                         |
| -------------------------------------------- | ------------------------------ |
| ✅ **Completamente gratuito**                 | ❌ Richiede setup iniziale      |
| ✅ **Voci naturali** (migliori di Web Speech) | ❌ Modelli ~50-100MB per lingua |
| ✅ Self-hosted (Docker o binary)              | ❌ Non buono come ElevenLabs    |
| ✅ **Bassa latenza** (<100ms)                 |                                |
| ✅ Supporta italiano                          |                                |
| ✅ Funziona su Raspberry Pi                   |                                |

**Setup Piper**:
```bash
# Download voice model italiano
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it-riccardo_fasol-x_low/it-riccardo_fasol-x_low.onnx

# Esegui TTS
echo "Ciao, come posso aiutarti?" | piper --model it-riccardo_fasol-x_low.onnx --output_file output.wav

# Oppure server Docker
docker run -p 5000:5000 rhasspy/piper --model it-riccardo_fasol-x_low
```

**Opzione C: ElevenLabs** (Premium Cloud)

Il leader di mercato per TTS realistico, come usa OpenClaw.

| Pro                              | Contro                           |
| -------------------------------- | -------------------------------- |
| ✅ Qualità vocale eccezionale     | ❌ Costa ~$5-22/mese              |
| ✅ Voci italiane molto naturali   | ❌ Latenza di rete (~200-500ms)   |
| ✅ Voice cloning disponibile      | ❌ Dipendenza da servizio esterno |
| ✅ Controllo intonazione/emozione | ❌ Privacy: audio passa da loro   |

**Opzione D: Approccio Ibrido Progressivo** ⭐ RACCOMANDATO

```
Fase 1 (v1.0): Piper TTS self-hosted
                → Gratuito, naturale, italiano
                
Fase 2 (v1.5): + ElevenLabs opzionale
                → Per utenti premium / voice cloning
```

**La mia raccomandazione**: **Piper TTS** per la v1. È gratuito, ha voci naturali (molto meglio di Web Speech), funziona offline e ha bassa latenza. ElevenLabs come upgrade premium in futuro.

---

#### 3. Skills & Domains: Bundle Completo con Architettura Scalabile

> [!IMPORTANT]
> **Scelta confermata**: Bundle completo. Ma dobbiamo integrare i **14 domini già esistenti in Me4BrAIn** e definire come aggiungere nuovi domini/skills in futuro.

##### Domini Me4BrAIn Esistenti (già implementati)

Questi domini sono già operativi nel backend Me4BrAIn con 118+ tools:

| # | Dominio | Descrizione | Tools Principali |
|---|---------|-------------|------------------|
| 1 | **finance_crypto** | Finanza, azioni, crypto | crypto_price, yahoo_quote, technical_indicators, fmp_metrics, edgar_filings |
| 2 | **geo_weather** | Meteo e geolocalizzazione | weather_forecast, geocoding |
| 3 | **google_workspace** | Gmail, Calendar, Drive | gmail_search, calendar_events, drive_search |
| 4 | **web_search** | Ricerca web generale | perplexity_search, tavily_search |
| 5 | **science_research** | Paper accademici | arxiv_search, semantic_scholar |
| 6 | **knowledge_media** | Wikipedia, news | wikipedia_search, news_search |
| 7 | **tech_coding** | Coding e GitHub | github_search, stackoverflow |
| 8 | **entertainment** | Film, musica, giochi | tmdb_search, spotify_search |
| 9 | **food** | Ricette, ristoranti | recipe_search, restaurant_finder |
| 10 | **travel** | Voli, hotel, destinazioni | flight_search, hotel_search |
| 11 | **medical** | Informazioni mediche | pubmed_search, drug_info |
| 12 | **jobs** | Lavoro e carriera | linkedin_jobs, glassdoor |
| 13 | **sports_nba** | Sport e NBA | nba_stats, espn_scores |
| 14 | **utility** | Utility varie | calculator, unit_converter, qr_generator |

##### Mapping Domini → Skills PersAn

Ogni dominio Me4BrAIn diventa uno **skill** in PersAn:

```
Me4BrAIn Domain         →    PersAn Skill
─────────────────────────────────────────────
finance_crypto          →    Finance Analyst
geo_weather             →    Weather Assistant
google_workspace        →    Google Workspace
web_search              →    Research Assistant
science_research        →    Academic Researcher
knowledge_media         →    Knowledge Base
tech_coding             →    Code Assistant
entertainment           →    Entertainment Guide
food                    →    Food & Dining
travel                  →    Travel Planner
medical                 →    Health Info
jobs                    →    Career Assistant
sports_nba              →    Sports Tracker
utility                 →    Utilities
```

##### Architettura Skills Scalabile

Come aggiungere nuovi domini/skills in futuro? Due livelli:

**Livello 1: Nuovo Dominio Me4BrAIn** (Backend)

```python
# me4brain/domains/nuovo_dominio/handler.py
class NuovoDominioHandler(DomainHandler):
    @property
    def domain_name(self) -> str:
        return "nuovo_dominio"
    
    @property
    def capabilities(self) -> list[DomainCapability]:
        return [DomainCapability(...)]
    
    async def execute_tool(self, tool_name: str, args: dict) -> dict:
        # Implementazione tool
        ...
```

Il dominio viene **auto-discovered** dal `PluginRegistry`:
```python
registry = await PluginRegistry.get_instance("tenant")
# Scansiona domains/ e carica tutti gli handler
```

**Livello 2: Nuovo Skill PersAn** (Frontend)

```yaml
# ~/.persan/skills/nuovo_skill/SKILL.md
---
name: nuovo-skill
description: Descrizione dello skill
domains: [nuovo_dominio]  # Mappa a domini Me4BrAIn
tools: [tool1, tool2]
---
# Nuovo Skill

Istruzioni per l'agente su come usare questo skill...
```

##### Flow Scalabilità

```
┌─────────────────────────────────────────────────────────────────────┐
│                           AGGIUNTA NUOVO SKILL                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. Crea dominio Me4BrAIn (se non esiste)                          │
│     → me4brain/domains/nuovo_dominio/                               │
│     → handler.py + tools/*.py                                       │
│     → Auto-discovered al restart                                    │
│                                                                     │
│  2. Crea skill PersAn (opzionale, per UI)                          │
│     → ~/.persan/skills/nuovo_skill/SKILL.md                        │
│     → Definisce come presentare il dominio all'utente              │
│                                                                     │
│  3. Gateway rileva automaticamente                                  │
│     → Skills Registry scansiona ~/.persan/skills/                   │
│     → Espone nuova capability via WebSocket                         │
│                                                                     │
│  4. UI aggiorna dinamicamente                                       │
│     → Canvas mostra nuovi block types                               │
│     → Chat suggerisce nuove capabilities                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

##### Configurazione Bundle

```yaml
# ~/.persan/config.yaml
skills:
  bundled:  # Inclusi di default
    - finance_analyst
    - research_assistant
    - google_workspace
    - weather_assistant
    - code_assistant
    - knowledge_base
    - entertainment
    - food_dining
    - travel_planner
    - health_info
    - career_assistant
    - sports_tracker
    - utilities
    
  external:  # Installabili on-demand
    - browser_automation
    - email_marketing
    - social_media_manager
```

**Raccomandazione**: **Bundle completo** di tutti i 14 domini Me4BrAIn esistenti. L'architettura sopra garantisce scalabilità per nuovi skill futuri.

---

#### 4. Mobile Nodes: Priorità di Sviluppo

I "nodes" mobili sono app companion per iOS/Android che permettono di usare PersAn da smartphone con funzionalità native (notifiche push, camera, GPS).

**Opzione A: Rimandare** (Focus Desktop/Web) ⭐ Raccomandato

Concentrarsi sulla web app PWA prima, che funziona già su mobile.

| Pro                            | Contro                       |
| ------------------------------ | ---------------------------- |
| ✅ Meno effort iniziale         | ❌ Esperienza mobile limitata |
| ✅ Focus su core funzionalità   | ❌ No notifiche push native   |
| ✅ PWA funziona comunque        | ❌ No accesso camera/GPS      |
| ✅ Più tempo per Gateway/Canvas |                              |

**Opzione B: iOS Prima**

Sviluppare app nativa Swift/SwiftUI per iPhone.

| Pro                          | Contro                                |
| ---------------------------- | ------------------------------------- |
| ✅ Esperienza premium Apple   | ❌ 4-6 settimane extra                 |
| ✅ Notifiche push native      | ❌ Solo iOS (no Android)               |
| ✅ Siri Shortcuts integration | ❌ Richiede Apple Developer ($99/anno) |
| ✅ Widget Home Screen         |                                       |

**Opzione C: Cross-Platform**

Usare React Native o Flutter per iOS + Android insieme.

| Pro                               | Contro                              |
| --------------------------------- | ----------------------------------- |
| ✅ Due piattaforme con un codebase | ❌ 6-8 settimane extra               |
| ✅ Condivisione codice con web     | ❌ Performance leggermente inferiore |
| ✅ Community React Native grande   | ❌ Debugging più complesso           |

**La mia raccomandazione**: **Rimandare**. La PWA con Telegram/WhatsApp copre già l'uso mobile. Le notifiche arrivano via Telegram. Focalizzarsi sul core (Gateway, Canvas, Skills) è più strategico. Si può aggiungere l'app nativa nella Fase 2 del progetto.

---

### 📋 Riepilogo Raccomandazioni

| Domanda       | Raccomandazione                         | Motivazione                                   |
| ------------- | --------------------------------------- | --------------------------------------------- |
| **Runtime**   | Node.js + Fastify                       | Stabilità, ecosistema, compatibilità librerie |
| **Voice TTS** | Web Speech API (+ ElevenLabs opzionale) | Gratis per iniziare, premium dopo             |
| **Skills**    | Finance + Research + Calendar           | Coprono 90% use case                          |
| **Mobile**    | Rimandare (PWA + Telegram)              | Focus su core, mobile dopo                    |
