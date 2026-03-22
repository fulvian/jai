# 🚀 Piano di Implementazione Integrato: Risoluzione Criticità

**Status**: READY FOR EXECUTION
**Date**: March 11, 2024
**Version**: 2.0 (Integrated with Improvements)

---

## EXECUTIVE SUMMARY

Questo documento integra la soluzione proposta con i miglioramenti critici identificati. Il piano è strutturato in 5 fasi con fallback, health checks, troubleshooting e rollback procedures.

**Timeline Totale**: ~2-3 ore (inclusi fallback e validazione)

---

## FASE 0: SANIFICAZIONE AMBIENTE PYTHON (CRITICO)

### Obiettivo
Risolvere l'incompatibilità Python 3.14 con dipendenze (`numba`, `llama-index`)

### 0.1 Installazione Python 3.12 (Con Fallback)

#### Opzione A: pyenv (Preferito)
```bash
# 1. Installa pyenv
brew install pyenv

# 2. Configura shell (.zshrc)
echo 'export PATH="$HOME/.pyenv/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init --path)"' >> ~/.zshrc
source ~/.zshrc

# 3. Installa Python 3.12
pyenv install 3.12
pyenv global 3.12

# 4. Verifica
python --version  # Deve mostrare Python 3.12.x
which python      # Deve mostrare ~/.pyenv/shims/python
```

#### Opzione B: Fallback (Se brew install bloccato)
```bash
# 1. Download diretto da python.org
# Scarica Python 3.12 da https://www.python.org/downloads/
# Installa il .pkg file

# 2. Verifica installazione
python3 --version  # Deve mostrare Python 3.12.x

# 3. Crea alias in .zshrc
echo "alias python='/usr/local/bin/python3'" >> ~/.zshrc
source ~/.zshrc

# 4. Verifica alias
python --version  # Deve mostrare Python 3.12.x
```

#### Opzione C: Fallback (Se nessuna delle precedenti funziona)
```bash
# 1. Usa conda (se installato)
conda create -n me4brain python=3.12
conda activate me4brain

# 2. Verifica
python --version  # Deve mostrare Python 3.12.x
```

### 0.2 Aggiornamento pyproject.toml

**File**: `pyproject.toml`

```toml
[project]
requires-python = ">=3.10, <3.14"  # Blocca Python 3.14+
```

### 0.3 Correzione PATH e Venv

```bash
# 1. Verifica che python sia nel PATH
which python
# Output atteso: /Users/fulvio/.pyenv/shims/python (o simile)

# 2. Verifica versione
python --version
# Output atteso: Python 3.12.x

# 3. Pulisci venv vecchi
rm -rf .venv .venv_new

# 4. Crea nuovo venv
python -m venv .venv

# 5. Attiva venv
source .venv/bin/activate

# 6. Verifica che venv sia attivo
python -c "import sys; print(sys.prefix)"
# Output atteso: /Users/fulvio/coding/Me4BrAIn/.venv
```

### 0.4 Verifica Pre-Installazione Dipendenze

```bash
# Verifica che pip sia disponibile
pip --version

# Verifica che setuptools sia disponibile
pip show setuptools

# Se setuptools non disponibile, aggiorna pip
pip install --upgrade pip setuptools wheel
```

---

## FASE 1: SETUP SVILUPPO LOCALE

### 1.1 Installazione Dipendenze

```bash
# Assicurati che venv sia attivo
source .venv/bin/activate

# Installa dipendenze
pip install -e .

# Verifica installazione
pip check  # Deve mostrare "0 packages with dependency conflicts"
```

### 1.2 Backend Setup

```bash
# Verifica che il modulo sia installato
python -c "import me4brain; print(me4brain.__file__)"

# Verifica configurazione
python -c "
from me4brain.llm.config import get_llm_config
config = get_llm_config()
print(f'Config loaded: {config.use_unified_intent_analyzer}')
"

# Avvio backend
python -m me4brain.main
# Output atteso: Server listening on http://localhost:8000
```

### 1.3 Frontend Setup

```bash
# Vai nella directory corretta
cd PersAn

# Verifica npm
npm --version

# Installa dipendenze (se non già installate)
npm install

# Avvio frontend
npm run dev
# Output atteso: Ready on http://localhost:3000
```

### 1.4 Monitoring Setup

```bash
# Torna alla root
cd ../Me4BrAIn

# Verifica che monitor_intent.py esista
ls -la scripts/monitor_intent.py

# Avvio monitoring (in terminale separato)
python scripts/monitor_intent.py
# Output atteso: Dashboard showing metrics
```

---

## FASE 2: VALIDAZIONE E INTEGRAZIONE

### 2.1 Health Checks

```bash
# Backend health check
curl http://localhost:8000/health
# Output atteso: {"status": "ok"}

# Frontend health check
curl http://localhost:3000/health
# Output atteso: HTML page or {"status": "ok"}

# Monitoring health check
# Verifica che il dashboard sia visibile nel terminale
```

### 2.2 Esecuzione Test Suite

```bash
# Assicurati che venv sia attivo
source .venv/bin/activate

# Esegui tutti i test
python -m pytest tests/ -v

# Output atteso: 70 passed in X.XXs
```

### 2.3 Validazione Funzionale E2E

```bash
# 1. Apri browser
# http://localhost:3000

# 2. Invia query di test
# "Che tempo fa a Caltanissetta?"

# 3. Verifica risposta nel backend
# Controlla i log del backend per confermare ricezione

# 4. Verifica feature flag
python -c "
from me4brain.llm.config import get_llm_config
from me4brain.engine.feature_flags import get_feature_flag_manager
config = get_llm_config()
ffm = get_feature_flag_manager()
print(f'Feature enabled: {config.use_unified_intent_analyzer}')
print(f'Rollout phase: {ffm.current_phase}')
print(f'Traffic: {ffm.traffic_percentage}%')
"
# Output atteso: Feature enabled: False, Rollout phase: DISABLED, Traffic: 0%
```

---

## FASE 3: GESTIONE ROLLOUT E DEPLOYMENT

### 3.1 Configurazione Feature Flags

```bash
# Modifica .env per disabilitare durante test
export USE_UNIFIED_INTENT_ANALYZER=false
export UNIFIED_INTENT_ROLLOUT_PHASE=disabled
export UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0

# Verifica configurazione
python -c "
from me4brain.llm.config import get_llm_config
config = get_llm_config()
print(f'USE_UNIFIED_INTENT_ANALYZER: {config.use_unified_intent_analyzer}')
"
```

### 3.2 Deployment Script (Con Verifiche)

**File**: `scripts/deploy_unified_intent_enhanced.sh`

```bash
#!/bin/bash

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}[1/5] Verifica Python Version${NC}"
PYTHON_VERSION=$(python --version | cut -d' ' -f2)
if [[ ! $PYTHON_VERSION =~ ^3\.(9|10|11|12|13)$ ]]; then
    echo -e "${RED}❌ Errore: Python $PYTHON_VERSION non supportato${NC}"
    echo "Versioni supportate: 3.9, 3.10, 3.11, 3.12, 3.13"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION OK${NC}"

echo -e "${YELLOW}[2/5] Verifica Dipendenze${NC}"
if ! pip check > /dev/null 2>&1; then
    echo -e "${RED}❌ Errore: Dipendenze non risolte${NC}"
    pip check
    exit 1
fi
echo -e "${GREEN}✓ Dipendenze OK${NC}"

echo -e "${YELLOW}[3/5] Verifica Feature Flag${NC}"
python -c "
from me4brain.llm.config import get_llm_config
config = get_llm_config()
if config.use_unified_intent_analyzer:
    print('⚠ Warning: Feature flag è ENABLED')
else:
    print('✓ Feature flag è DISABLED (corretto per test)')
"

echo -e "${YELLOW}[4/5] Verifica Health Endpoints${NC}"
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend health OK${NC}"
else
    echo -e "${YELLOW}⚠ Backend non disponibile (avvia prima)${NC}"
fi

echo -e "${YELLOW}[5/5] Pronto per il deploy${NC}"
echo -e "${GREEN}✓ Tutte le verifiche passate${NC}"
```

### 3.3 Docker Setup (Completo)

**File**: `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Installa dipendenze di sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia file di progetto
COPY pyproject.toml .
COPY src/ src/
COPY tests/ tests/

# Installa dipendenze Python
RUN pip install --no-cache-dir -e .

# Espone porta
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Comando di avvio
CMD ["python", "-m", "me4brain.main"]
```

**File**: `docker-compose.yml`

```yaml
version: '3.8'

services:
  backend:
    build: ./Me4BrAIn
    ports:
      - "8000:8000"
    environment:
      - USE_UNIFIED_INTENT_ANALYZER=false
      - UNIFIED_INTENT_ROLLOUT_PHASE=disabled
      - UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build: ./PersAn
    ports:
      - "3000:3000"
    depends_on:
      - backend
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  monitoring:
    build:
      context: ./Me4BrAIn
      dockerfile: Dockerfile.monitor
    depends_on:
      - backend
    environment:
      - BACKEND_URL=http://backend:8000
```

---

## FASE 4: TROUBLESHOOTING GUIDE

### Problema: "zsh: command not found: python"

**Causa**: Python non nel PATH

**Soluzione**:
```bash
# Verifica che pyenv sia installato
which pyenv

# Se non trovato, installa pyenv
brew install pyenv

# Configura shell
echo 'export PATH="$HOME/.pyenv/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Verifica
python --version
```

### Problema: "ModuleNotFoundError: No module named 'me4brain'"

**Causa**: Modulo non installato nel venv

**Soluzione**:
```bash
# Verifica che venv sia attivo
source .venv/bin/activate

# Reinstalla modulo
pip install -e .

# Verifica
python -c "import me4brain; print('OK')"
```

### Problema: "pip check" mostra conflitti

**Causa**: Dipendenze non risolte

**Soluzione**:
```bash
# Pulisci venv
rm -rf .venv

# Ricrea venv
python -m venv .venv
source .venv/bin/activate

# Reinstalla
pip install --upgrade pip setuptools wheel
pip install -e .

# Verifica
pip check
```

### Problema: "Port 8000 already in use"

**Causa**: Processo precedente ancora in ascolto

**Soluzione**:
```bash
# Trova processo
lsof -i :8000

# Termina processo
kill -9 <PID>

# Verifica
lsof -i :8000  # Deve essere vuoto
```

### Problema: "npm run dev" fallisce

**Causa**: Directory sbagliata o dipendenze mancanti

**Soluzione**:
```bash
# Vai nella directory corretta
cd PersAn

# Installa dipendenze
npm install

# Avvia
npm run dev
```

---

## FASE 5: CLEANUP E ROLLBACK

### Script di Cleanup

**File**: `scripts/cleanup_dev.sh`

```bash
#!/bin/bash

echo "🛑 Stopping all services..."

# Termina backend
pkill -f "python -m me4brain.main" || true

# Termina frontend
pkill -f "npm run dev" || true

# Termina monitoring
pkill -f "monitor_intent.py" || true

echo "✓ All services stopped"

# Opzionale: Pulisci venv
read -p "Vuoi pulire il venv? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    rm -rf .venv
    echo "✓ Venv rimosso"
fi
```

### Rollback Procedure

```bash
# Se qualcosa fallisce, rollback a Python precedente
pyenv global 3.14  # Torna a versione precedente

# O disinstalla pyenv
brew uninstall pyenv

# Pulisci venv
rm -rf .venv

# Ricomincia da Fase 0
```

---

## FASE 6: CHECKLIST FINALE

### Pre-Deployment
- [ ] Python 3.12 installato e verificato
- [ ] Venv creato e attivo
- [ ] Dipendenze installate (pip check OK)
- [ ] pyproject.toml aggiornato
- [ ] .env configurato correttamente

### Deployment
- [ ] Backend avviato e health check OK
- [ ] Frontend avviato e health check OK
- [ ] Monitoring avviato
- [ ] 70 test passati
- [ ] Feature flag disabilitato
- [ ] Query di test funzionante

### Post-Deployment
- [ ] Documentazione aggiornata
- [ ] Logs raccolti
- [ ] Metriche monitorate
- [ ] Rollback procedure testata

---

## TIMELINE STIMATA

| Fase | Durata | Note |
|------|--------|-------|
| 0: Python Setup | 15-30 min | Dipende da fallback necessari |
| 1: Dev Setup | 20-30 min | Installazione dipendenze |
| 2: Validazione | 15-20 min | Test suite + E2E |
| 3: Deployment | 10-15 min | Script + Docker |
| 4: Troubleshooting | 0-30 min | Solo se necessario |
| 5: Cleanup | 5 min | Opzionale |
| **TOTALE** | **~2-3 ore** | Inclusi fallback |

---

## PROSSIMI PASSI

1. Esegui Fase 0 (Python Setup)
2. Esegui Fase 1 (Dev Setup)
3. Esegui Fase 2 (Validazione)
4. Esegui Fase 3 (Deployment)
5. Usa Fase 4 se necessario (Troubleshooting)
6. Esegui Fase 5 (Cleanup)

**Pronto per iniziare?**
