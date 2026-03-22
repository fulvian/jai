# 📡 Canali di Comunicazione

PersAn supporta più canali di comunicazione oltre alla WebChat.

## Canali Disponibili

| Canale   | SDK       | Status   |
| -------- | --------- | -------- |
| WebChat  | WebSocket | ✅ Attivo |
| Telegram | grammY    | ✅ Pronto |
| WhatsApp | Baileys   | ✅ Pronto |

---

## Telegram Setup

### 1. Crea Bot

1. Apri Telegram e cerca [@BotFather](https://t.me/BotFather)
2. Invia `/newbot` e segui le istruzioni
3. Copia il **token** fornito

### 2. Configura PersAn

```bash
# .env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11

# Optional: limita accesso a utenti specifici
TELEGRAM_ALLOWED_USERS=username1,username2
```

### 3. Avvia Gateway

```bash
npm run dev --filter=gateway
```

Il bot sarà online e risponderà ai messaggi.

### Comandi Disponibili

- `/start` - Inizia conversazione
- `/help` - Mostra aiuto
- `/status` - Verifica stato

---

## WhatsApp Setup

### 1. Abilita WhatsApp

```bash
# .env
WHATSAPP_ENABLED=true
WHATSAPP_AUTH_DIR=./data/whatsapp-auth
```

### 2. Prima Connessione

1. Avvia il gateway: `npm run dev --filter=gateway`
2. Un **QR code** apparirà nel terminale
3. Apri WhatsApp sul telefono → Impostazioni → Dispositivi collegati → Collega dispositivo
4. Scansiona il QR code

### 3. Sessione Persistente

La sessione viene salvata in `WHATSAPP_AUTH_DIR`. Non serve ri-scansionare il QR ad ogni avvio.

### Whitelist Numeri

```bash
# .env - numeri senza + (es. 393331234567 per +39 333 1234567)
WHATSAPP_ALLOWED_NUMBERS=393331234567,393339876543
```

---

## Architettura

```
┌─────────────────────────────────────────┐
│              ChannelManager             │
│         (orchestrates adapters)         │
└─────────────┬───────────────────────────┘
              │
   ┌──────────┴──────────┐
   ▼                     ▼
┌──────────┐      ┌───────────┐
│ Telegram │      │ WhatsApp  │
│ Adapter  │      │  Adapter  │
│ (grammY) │      │ (Baileys) │
└──────────┘      └───────────┘
```

Ogni adapter:
- Riceve messaggi dalla piattaforma
- Converte in formato `IncomingMessage`
- Passa a `ChannelManager.handleIncoming()`
- Me4BrAIn elabora la query
- Risposta inviata via adapter
