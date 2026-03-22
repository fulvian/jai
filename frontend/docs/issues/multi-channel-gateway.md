# Issues: Multi-Channel Gateway Integration

> **Status**: 🟡 In sospeso - Da risolvere dopo implementazione  
> **Data**: 2026-02-03  
> **Contesto**: Setup Telegram + WhatsApp gateway con Me4BrAIn

---

## 🟢 Issue #1: Me4BrAIn Timeout Durante Reindicizzazione (PARZIALMENTE RISOLTO)

### Descrizione
Quando Me4BrAIn sta eseguendo operazioni intensive (reindicizzazione, cold start BGE-M3), gli endpoint `/v1/engine/query` e altri non rispondono, causando timeout nel gateway.

### Sintomi
- Il bot Telegram risponde: *"Mi dispiace, si è verificato un errore. Riprova più tardi."*
- Gateway logs: `Me4BrAIn query failed: TimeoutError`
- Me4BrAIn logs: `BGE-M3 Model loading...` o reindicizzazione in corso

### Causa Root
- BGE-M3 cold start richiede ~30-60 secondi
- Reindicizzazione blocca le query
- API FastAPI single-threaded durante operazioni blocking

### ✅ Soluzione Implementata (2026-02-03)
1. **Health check BGE-M3**: Nuovo `check_bge_m3()` che segnala stato "loading" durante cold start
2. **Endpoint /health/models**: Gateway può verificare se modelli AI sono pronti prima di query
3. **BGE-M3 incluso in /health**: Status globale mostra modello loading/ready

### 🟡 Da Completare
- [ ] Aumentare timeout SDK da 30s a 120s per operazioni pesanti
- [ ] Queue system per gestire richieste durante operazioni intensive
- [ ] Background tasks async per reindicizzazione

### File Coinvolti
- `me4brain/api/routes/health.py` (✅ modificato)
- `packages/me4brain-client/src/engine.ts` (timeout - TODO)
- `packages/gateway/src/channels/manager.ts` (error handling - TODO)

---

## 🟢 Issue #2: Redis Authentication Error (RISOLTO)

### Descrizione
Il gateway non riesce a connettersi a Redis, impedendo la persistenza delle sessioni.

### Sintomi
```
Redis connection error: ReplyError: NOAUTH Authentication required.
Redis unavailable, session not persisted
```

### Causa Root
Redis richiede password ma il gateway non la fornisce.

### ✅ Soluzione Implementata (2026-02-03)
1. `session.ts` ora supporta `REDIS_PASSWORD` da env var
2. Aggiornato `.env.example` con `REDIS_URL` e `REDIS_PASSWORD`
3. Migliorato error handling per `NOAUTH` e `WRONGPASS`
4. Aggiunto log "✅ Redis connected successfully" per conferma

### File Modificati
- ✅ `packages/gateway/src/services/session.ts`
- ✅ `.env.example`

---

## 🟢 Issue #3: Neo4j Connection Timeout (RISOLTO)

### Descrizione
Neo4j va in timeout causando blocco dell'API Me4BrAIn.

### Sintomi
```json
{"error": "TimeoutError('timed out')", "event": "neo4j_unexpected_error"}
```

### Causa Root
- Neo4j container diventa unhealthy dopo periodo di inattività
- Connessioni stale non vengono gestite correttamente

### ✅ Soluzione Implementata (2026-02-03)
1. **Connection pooling** con configurazione esplicita:
   - `max_connection_lifetime=3600` (1 hour)
   - `max_connection_pool_size=50`
   - `connection_acquisition_timeout=60s`
   - `connection_timeout=30s`
2. **Retry automatico** con exponential backoff (3 tentativi)
3. **Logging migliorato** per debugging connessioni

### File Modificati
- ✅ `me4brain/memory/semantic.py`

---

## ✅ Issues Risolte

### Issue: Baileys 405 Error (RISOLTO)

**Problema**: WhatsApp non generava QR code, errore 405 "Connection Failure"

**Causa**: Versione protocollo WhatsApp obsoleta in Baileys 6.7.0

**Soluzione Applicata**:
1. Aggiornato Baileys a `7.0.0-rc.9`
2. Implementato `fetchLatestBaileysVersion()` per versione dinamica
3. Aggiunto `qrcode-terminal` per stampa QR manuale

**File Modificati**:
- `packages/gateway/src/channels/whatsapp/adapter.ts`
- `package.json` (dipendenze)

---

## 📋 Checklist Verifica Post-Fix

- [ ] Telegram bot risponde correttamente alle query
- [ ] WhatsApp invia/riceve messaggi
- [ ] Redis session persistence funziona
- [ ] Me4BrAIn risponde anche dopo cold start
- [ ] Neo4j connessione stabile

---

## 🔗 Riferimenti

- [Baileys GitHub Issues](https://github.com/WhiskeySockets/Baileys/issues)
- Gateway: `/Users/fulvioventura/persan/packages/gateway`
- Me4BrAIn: `/Users/fulvioventura/me4brain`
