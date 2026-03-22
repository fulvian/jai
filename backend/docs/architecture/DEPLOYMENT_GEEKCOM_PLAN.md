# Piano di Implementazione Deployment GeekCom
## Me4Brain + PersAn - Deployment Completo

### Data: 2026-02-17
### Server: GeekCom (100.99.43.29)

---

## 1. Analisi Problemi Attuali

### 1.1 Problemi di Build Docker Identificati

| Problema                      | Causa                                                   | Impatto               |
| ----------------------------- | ------------------------------------------------------- | --------------------- |
| Gateway build fallisce        | Dockerfile cerca `packages/gateway/dist` che non esiste | Deploy bloccato       |
| Frontend build fallisce       | Dockerfile.frontend mancante in `docker/`               | Deploy bloccato       |
| Dipendenze mancanti           | npm install non eseguito prima del build                | Build incompleto      |
| Variabili build-time mancanti | NEXT_PUBLIC_* non passate correttamente                 | Frontend non funziona |

### 1.2 Problemi di Rete

| Problema                             | Causa                               | Soluzione                       |
| ------------------------------------ | ----------------------------------- | ------------------------------- |
| Me4Brain non raggiungibile da PersAn | IP sbagliato o rete non configurata | Usare Tailscale IP 100.99.43.29 |
| Gateway non raggiunge Me4Brain       | ME4BRAIN_URL errato                 | http://100.99.43.29:8089/v1     |
| Frontend non raggiunge Gateway       | NEXT_PUBLIC_GATEWAY_URL errato      | ws://100.99.43.29:3030/ws       |

### 1.3 Problemi di Variabili d'Ambiente

| File                 | Problema           | Soluzione              |
| -------------------- | ------------------ | ---------------------- |
| .env Me4Brain        | Mancante su server | Creare da .env.example |
| .env PersAn          | Mancante su server | Creare da .env.example |
| Variabili produzione | Non settate        | ENVIRONMENT=production |

---

## 2. Architettura Target

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GEEKCOM SERVER                              │
│                         IP: 100.99.43.29                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              DOCKER NETWORK: me4brain-network               │   │
│  │                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │   │
│  │  │   me4brain  │  │   redis     │  │      qdrant        │  │   │
│  │  │    (API)    │  │  (cache)    │  │    (vectors)       │  │   │
│  │  │  port:8089  │  │  port:6379  │  │  ports:6333/6334   │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │   │
│  │         ↑                                         ↑        │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │   │
│  │  │  │   neo   postgres  │4j     │  │      keycloak      │  │   │
│  │  │  (state)   │  │   (graph)   │  │    (auth opt)     │  │   │
│  │  │  port:5432  │  │ ports:7474  │  │    port:8080      │  │   │
│  │  │             │  │      7687   │  │                   │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │   │
│  │                                                             │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              ↑                                      │
│                              │                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              DOCKER NETWORK: persan-network (shared)        │   │
│  │                                                             │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │   │
│  │  │   gateway   │  │   redis     │  │      frontend      │  │   │
│  │  │  port:3030 │  │  port:6379  │  │     port:3020      │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │   │
│  │         ↑                              ↑                     │   │
│  │         │                              │                     │   │
│  │         └──────────┬───────────────────┘                     │   │
│  │                    ↓                                         │   │
│  │              Browser User                                    │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Checklist Pre-Deploy

### 3.1 Repository Sincronizzati

- [ ] Me4Brain: `git pull origin master` su server
- [ ] PersAn: `git pull origin master` su server

### 3.2 File di Configurazione

- [ ] Me4Brain `.env` creato e configurato
- [ ] PersAn `.env` creato e configurato
- [ ] Variabili produzione impostate

### 3.3 Immagini Docker

- [ ] Build Me4Brain completato
- [ ] Build Gateway completato
- [ ] Build Frontend completato

---

## 4. Modalita di Deploy (Approccio Ibrido)

> [!IMPORTANT]\n> **Due modalita complementari**: Stabile (immagine) e Dev (volumi). Scegliere in base al contesto.

### 4.1 Panoramica Modalita

| Modalita | File Compose | Codice | Velocita Iterazione | Uso Consigliato |
| -------- | ------------ | ------ | ------------------- | --------------- |\n| **Stabile** | `docker-compose.geekcom.yml` | Cotto nell'immagine | Lento (~5-8 min build) | Deploy production, release |
| **Dev** | `+ docker-compose.geekcom.dev.yml` | Volume montato | Veloce (~5-10 sec restart) | Sviluppo, debugging, hotfix |

### 4.2 Modalita Stabile (Production)

**Quando usarla**: Deploy finali, release, ambienti che devono essere riproducibili.

```bash\n# === WORKFLOW MODALITA STABILE ===\n\n# 1. Sincronizza codice locale → server\nrsync -avz --exclude '.git' --exclude '__pycache__' \\\n  /path/to/me4brain/ root@100.99.43.29:/root/persan_me4brain/me4brain/\n\n# 2. Build immagine (5-8 minuti)\nssh root@100.99.43.29 "cd /root/persan_me4brain/me4brain/docker && \\\n  docker compose -f docker-compose.geekcom.yml build me4brain"\n\n# 3. Riavvia container\nssh root@100.99.43.29 "cd /root/persan_me4brain/me4brain/docker && \\\n  docker compose -f docker-compose.geekcom.yml up -d me4brain"\n\n# 4. Verifica health\nssh root@100.99.43.29 "curl -s http://localhost:8089/health"\n```\n\n**Vantaggi**:\n- Immagine immutabile e versionabile\n- Rollback semplice con tag (`me4brain:v1.2.3`)\n- Riproducibile al 100%\n\n### 4.3 Modalita Dev (Hot Reload)\n\n**Quando usarla**: Sviluppo attivo, iterazioni rapide, debugging.\n\n```bash\n# === WORKFLOW MODALITA DEV ===\n\n# 1. Sincronizza solo i file modificati (veloce)\nrsync -avz /path/to/me4brain/src/ root@100.99.43.29:/root/persan_me4brain/me4brain/src/\n\n# 2. Riavvia container (5-10 secondi)\nssh root@100.99.43.29 "cd /root/persan_me4brain/me4brain/docker && \\\n  docker compose -f docker-compose.geekcom.yml -f docker-compose.geekcom.dev.yml restart me4brain"\n\n# 3. Verifica logs (opzionale)\nssh root@100.99.43.29 "docker logs --tail 50 me4brain-api"\n```\n\n**Vantaggi**:\n- Iterazione velocissima\n- Nessun rebuild necessario\n- Ideale per debugging\n\n> [!CAUTION]\n> **Rischi della modalita Dev**:\n> - Il codice sul server puo "driftare" dal repository git\n> - Rollback piu complesso (bisogna risincronizzare)\n> - **Semper** passare alla modalita Stabile dopo aver finito lo sviluppo\n\n### 4.4 Transizione Dev → Stabile\n\nQuando hai finito l'iterazione rapida e vuoi "congelare" il codice:\n\n```bash\n# 1. Ferma il container dev\nssh root@100.99.43.29 "cd /root/persan_me4brain/me4brain/docker && \\\n  docker compose -f docker-compose.geekcom.yml -f docker-compose.geekcom.dev.yml down me4brain"\n\n# 2. Ricostruisci l'immagine con il codice aggiornato\nssh root@100.99.43.29 "cd /root/persan_me4brain/me4brain/docker && \\\n  docker compose -f docker-compose.geekcom.yml build --no-cache me4brain"\n\n# 3. Avvia in modalita stabile\nssh root@100.99.43.29 "cd /root/persan_me4brain/me4brain/docker && \\\n  docker compose -f docker-compose.geekcom.yml up -d me4brain"\n```\n\n### 4.5 Struttura File Compose\n\n```\nme4brain/docker/\n├── docker-compose.yml              # Base (dev locale con volumi)\n├── docker-compose.geekcom.yml      # Produzione stabile (codice cotto)\n├── docker-compose.geekcom.dev.yml  # Override per hot reload\n├── docker-compose.dev.yml          # Dev locale alternativo\n└── .env.geekcom                    # Variabili produzione\n```\n\n**Come funziona l'override**:\n- `docker-compose.geekcom.yml` definisce la configurazione base\n- `docker-compose.geekcom.dev.yml` aggiunge solo i volumi sorgenti\n- Docker Compose fa merge delle due configurazioni\n\n---

## 5. Script di Deployment (Legacy)

### 4.1 Script Principale: `deploy-geekcom.sh`

```bash
#!/bin/bash
set -euo pipefail

SERVER_IP="100.99.43.29"
SERVER_USER="geekcom"
DEPLOY_ROOT="/home/geekcom/persan_me4brain"

echo "🚀 Starting deployment to $SERVER_USER@$SERVER_IP..."

# SSH and execute deployment
ssh "$SERVER_USER@$SERVER_IP" "bash -s" <<'ENDSSH'
set -e

DEPLOY_ROOT="/home/geekcom/persan_me4brain"
ME4BRAIN_DIR="$DEPLOY_ROOT/me4brain"
PERSAN_DIR="$DEPLOY_ROOT/persan"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${GREEN}✅ $1${NC}"; }
err() { echo -e "${RED}❌ $1${NC}"; }

cd "$DEPLOY_ROOT"

# Step 1: Update repositories
log "Updating repositories..."
cd "$ME4BRAIN_DIR" && git pull origin master
cd "$PERSAN_DIR" && git pull origin master

# Step 2: Stop services
log "Stopping services..."
bash scripts/stop.sh || true

# Step 3: Start Me4Brain
log "Starting Me4Brain..."
cd "$ME4BRAIN_DIR"
docker compose -f docker/docker-compose.yml --profile app up -d --build

# Wait for Me4Brain
log "Waiting for Me4Brain health..."
for i in {1..30}; do
    if curl -sf http://localhost:8089/health > /dev/null 2>&1; then
        log "Me4Brain is healthy!"
        break
    fi
    echo "Waiting... ($i/30)"
    sleep 2
done

# Step 4: Start PersAn Gateway
log "Starting PersAn Gateway..."
cd "$PERSAN_DIR"
export ME4BRAIN_URL="http://100.99.43.29:8089/v1"
docker compose -f docker/docker-compose.gateway.yml up -d --build

# Wait for Gateway
log "Waiting for Gateway health..."
for i in {1..15}; do
    if curl -sf http://localhost:3030/health > /dev/null 2>&1; then
        log "Gateway is healthy!"
        break
    fi
    echo "Waiting... ($i/15)"
    sleep 2
done

# Step 5: Build and start Frontend (or use container)
log "Building Frontend..."
cd "$PERSAN_DIR/frontend"

# Create production env file
cat > .env.local <<'EOF'
NEXT_PUBLIC_API_URL=http://100.99.43.29:3030
NEXT_PUBLIC_GATEWAY_URL=ws://100.99.43.29:3030/ws
NEXT_PUBLIC_VAPID_PUBLIC_KEY=BL4oiu3dW48y7DG0O3nuJixDGVaXMjepI4aYvlAI4bbnDRVawfUO3NaAUB7KDpXZ6dO7_HLfD3jxjvpZKb0mrCo
EOF

npm run build

# Start frontend with PM2 or direct
PORT=3020 HOST=0.0.0.0 nohup npm run start > /tmp/persan-frontend.log 2>&1 &

log "Deployment complete!"
echo ""
echo "========================================"
echo "  Services:"
echo "  - Me4Brain API:  http://100.99.43.29:8089"
echo "  - Gateway:       http://100.99.43.29:3030"
echo "  - Frontend:      http://100.99.43.29:3020"
echo "========================================"
ENDSSH

echo "✅ Deployment finished!"
```

---

## 5. File di Configurazione

### 5.1 Me4Brain `.env` (Production)

```bash
# API Configuration
ME4BRAIN_HOST=0.0.0.0
ME4BRAIN_PORT=8089
ME4BRAIN_DEBUG=false
ME4BRAIN_LOG_LEVEL=INFO
ME4BRAIN_API_KEY=your_production_key

# Database Connections
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=me4brain
POSTGRES_PASSWORD=me4brain_secret_change_me
POSTGRES_DB=me4brain

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=

QDRANT_HOST=qdrant
QDRANT_GRPC_PORT=6333
QDRANT_HTTP_PORT=6334

NEO4J_HOST=neo4j
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j_secret_change_me

# LLM Configuration
NANOGPT_API_KEY=your_nanogpt_api_key
LLM_PRIMARY_MODEL=deepseek/deepseek-v3.2-speciale
LLM_AGENTIC_MODEL=zai-org/glm-4.7:thinking
LLM_VISION_MODEL=moonshotai/kimi-k2.5:thinking
EMBEDDING_MODEL=BAAI/bge-m3

# Production
ENVIRONMENT=production
```

### 5.2 PersAn `.env` (Production)

```bash
# Me4BrAIn Connection - USE TAILSCALE IP!
ME4BRAIN_URL=http://100.99.43.29:8089
ME4BRAIN_API_KEY=your_production_key

# Gateway
PORT=3030
HOST=0.0.0.0
LOG_LEVEL=info

# Redis
REDIS_URL=redis://redis:6379

# Backend
PERSAN_PORT=8888
PERSAN_HOST=0.0.0.0
DEBUG=false

# Frontend - USE TAILSCALE IP!
NEXT_PUBLIC_API_URL=http://100.99.43.29:3030
NEXT_PUBLIC_GATEWAY_URL=ws://100.99.43.29:3030/ws
NEXT_PUBLIC_VAPID_PUBLIC_KEY=BL4oiu3dW48y7DG0O3nuJixDGVaXMjepI4aYvlAI4bbnDRVawfUO3NaAUB7KDpXZ6dO7_HLfD3jxjvpZKb0mrCo

# Production
ENVIRONMENT=production
CORS_ALLOWED_ORIGINS=http://100.99.43.29:3020,http://GIC-com:3020
```

---

## 6. Docker Compose Files

### 6.1 Me4Brain docker-compose.yml (estratto)

```yaml
services:
  me4brain:
    build:
      context: ..
      dockerfile: Dockerfile
    container_name: me4brain-api
    restart: unless-stopped
    profiles: ["app"]
    env_file:
      - ../.env
    ports:
      - "8089:8000"
    environment:
      - REDIS_URL=redis://redis:6379
      - REDIS_HOST=redis
      - QDRANT_URL=http://qdrant:6334
      - QDRANT_HOST=qdrant
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_HOST=neo4j
      - POSTGRES_URL=postgresql://me4brain:${DB_PASSWORD}@postgres:5432/me4brain
      - POSTGRES_HOST=postgres
      - ENVIRONMENT=${ENVIRONMENT:-production}
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      neo4j:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 120s

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
    
  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U me4brain"]

  qdrant:
    image: qdrant/qdrant:v1.16.2
    ports:
      - "6333:6333"
      - "6334:6334"

  neo4j:
    image: neo4j:5.26-community
    ports:
      - "7474:7474"
      - "7687:7687"

networks:
  default:
    name: me4brain-network
    driver: bridge
```

### 6.2 PersAn docker-compose.gateway.yml

```yaml
services:
  gateway:
    build:
      context: ..
      dockerfile: docker/Dockerfile.gateway
    ports:
      - "3030:3030"
    environment:
      - NODE_ENV=production
      - PORT=3030
      - ME4BRAIN_URL=${ME4BRAIN_URL:-http://100.99.43.29:8089/v1}
      - LOG_LEVEL=info
      - REDIS_URL=redis://redis:6379
    depends_on:
      - redis
    networks:
      - persan-network
      - me4brain-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3030/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    networks:
      - persan-network

networks:
  persan-network:
    driver: bridge
  me4brain-network:
    external: true
    name: me4brain-network

volumes:
  redis-data:
```

---

## 7. Comandi di Deployment

### 7.1 Deployment Manuale Passo-Passo

```bash
# 1. Connettiti al server
ssh geekcom@100.99.43.29

# 2. Vai nella directory di deploy
cd ~/persan_me4brain

# 3. Aggiorna Me4Brain
cd me4brain
git pull origin master

# 4. Crea .env se non esiste
cp .env.example .env
# Edita .env con i valori corretti

# 5. Avvia Me4Brain
docker compose -f docker/docker-compose.yml --profile app up -d --build

# 6. Verifica health
curl http://localhost:8089/health

# 7. Aggiorna PersAn
cd ../persan
git pull origin master

# 8. Crea .env se non esiste
cp .env.example .env
# Edita .env con i valori corretti

# 9. Crea docker-compose.gateway.yml se non esiste
# (usa il template sopra)

# 10. Avvia Gateway
ME4BRAIN_URL=http://100.99.43.29:8089/v1 docker compose -f docker/docker-compose.gateway.yml up -d --build

# 11. Verifica health
curl http://localhost:3030/health

# 12. Build e avvia Frontend
cd frontend

# Crea env file per production
cat > .env.local <<'EOF'
NEXT_PUBLIC_API_URL=http://100.99.43.29:3030
NEXT_PUBLIC_GATEWAY_URL=ws://100.99.43.29:3030/ws
NEXT_PUBLIC_VAPID_PUBLIC_KEY=BL4oiu3dW48y7DG0O3nuJixDGVaXMjepI4aYvlAI4bbnDRVawfUO3NaAUB7KDpXZ6dO7_HLfD3jxjvpZKb0mrCo
EOF

npm install
npm run build

# Avvia in background
PORT=3020 HOST=0.0.0.0 nohup npm run start > /tmp/frontend.log 2>&1 &

# 13. Verifica
curl http://localhost:3020
```

---

## 8. Risoluzione Problemi Comuni

### 8.1 Me4Brain non parte

```bash
# Check logs
docker logs me4brain-api

# Check ports
netstat -tlnp | grep -E '8089|6379|5432|6334|7474|7687'

# Check resources
docker stats
```

### 8.2 Gateway non raggiunge Me4Brain

```bash
# From gateway container
docker exec -it persan-gateway curl http://100.99.43.29:8089/health

# Check ME4BRAIN_URL env
docker exec -it persan-gateway env | grep ME4BRAIN
```

### 8.3 Frontend non si carica

```bash
# Check logs
tail -f /tmp/frontend.log

# Check NEXT_PUBLIC variables (devono essere build-time!)
# Ricorda: npm run build DEVE essere eseguito con le variabili giuste
```

---

## 9. Health Check Endpoints

| Servizio | Endpoint                        | Atteso            |
| -------- | ------------------------------- | ----------------- |
| Me4Brain | http://100.99.43.29:8089/health | `{"status":"ok"}` |
| Gateway  | http://100.99.43.29:3030/health | `{"status":"ok"}` |
| Frontend | http://100.99.43.29:3020        | HTML response     |

---

## 10. Prossimi Passi

1. **Esegui checklist pre-deploy**
2. **Crea script di deployment automatizzato**
3. **Testa locally**
4. **Deploy su GeekCom**
5. **Verifica health**
6. **Monitora logs**

---

*Documento generato automaticamente - 2026-02-17*
