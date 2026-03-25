# Piano dettagliato di installazione e deployment locale JAI (Ubuntu + AMD ROCm)

**Data**: 2026-03-25  
**Autore**: Analisi tecnica preparatoria (nessuna modifica codice applicata in questa fase)  
**Target host**: Ubuntu 24.04.4 LTS, AMD Ryzen AI 9 HX 370, iGPU Radeon 890M (gfx1150), ROCm 7.2.0  
**Obiettivo operativo**: deployment locale stabile di Frontend (3020) + Gateway (3030) + Backend (8000) + servizi di supporto (PostgreSQL/Redis/Qdrant/Neo4j), con backend su stack PyTorch coerente con hardware AMD.

---

## 1) Executive summary

Dall’analisi congiunta di handoff, documentazione e codebase emergono **tre blocchi principali**:

1. **Risoluzione dipendenze PyTorch non deterministica su backend** (download NVIDIA/CUDA indesiderati durante `uv run`).  
2. **Infrastruttura locale incompleta** (Docker CLI/plugin/permessi non allineati, Redis/Postgres/Qdrant/Neo4j non garantiti in esecuzione).  
3. **Incoerenze di configurazione porte/URL nel Gateway** (presenza di default legacy `8089` in più moduli, mentre architettura JAI punta a `8000`).

Il piano propone una strategia in 8 fasi, con priorità:

- **P0** Stabilizzazione ambiente e prerequisiti sistema  
- **P1** Correzione deterministica della supply chain Python (UV + pin index torch)  
- **P2** Ripristino servizi di supporto (preferenza Docker; fallback apt/native)  
- **P3** Avvio backend + verifica GPU path  
- **P4** Allineamento runtime Gateway/Frontend (senza refactoring funzionale)  
- **P5** Verifica E2E e hardening operativo  

---

## 2) Fonti e evidenze analizzate

### 2.1 Handoff principale
- `docs/handoff/codex-handoff-2026-03-25.md`

### 2.2 Documentazione repository
- `docs/LOCAL_DEPLOYMENT.md`
- `docs/DEPLOYMENT_STATUS.md`
- `docker-compose.dev.yml`
- `backend/pyproject.toml`
- `backend/src/me4brain/config/settings.py`
- `backend/src/me4brain/api/main.py`
- `backend/src/me4brain/api/routes/health.py`
- `frontend/packages/gateway/*` (config/routes/services)

### 2.3 Evidenze runtime host
- OS: Ubuntu 24.04.4 LTS, kernel 6.17
- CPU: Ryzen AI 9 HX 370 (24 thread)
- ROCm: runtime attivo, `rocminfo` rileva GPU `gfx1150`
- `rocm-smi`: VRAM ~94% occupata (implicazioni su modelli embedding)
- Docker socket: `/var/run/docker.sock` `root:docker`, ma utente **non** nel gruppo `docker`
- Docker Compose plugin assente (`docker compose` non disponibile)
- Nessun listener attivo sulle porte applicative principali al momento del check

### 2.4 Riferimenti ufficiali consultati
- UV package indexes / sources / PyTorch integration (docs.astral.sh)
- Docker post-install Linux (docs.docker.com)
- ROCm install + PyTorch on ROCm (rocm.docs.amd.com)
- PyTorch HIP semantics (docs.pytorch.org)

---

## 3) Gap analysis (stato reale vs target)

## Target
- Frontend: `http://localhost:3020`
- Gateway: `http://localhost:3030`
- Backend: `http://localhost:8000`
- DB/caching/vector/graph disponibili e raggiungibili

## Gap identificati

### G1 — Dependency chain torch non controllata
- `backend/pyproject.toml` contiene:
  - `sentence-transformers>=3`
  - `torch>=2.5`
- In assenza di lock robusto e source pinning, `uv run` può risolvere wheel CUDA/NVIDIA su Linux.

### G2 — File lock backend non presente
- `backend/uv.lock` non risulta presente (a differenza di quanto riportato in handoff).  
- Implicazione: risoluzione dipendenze potenzialmente variabile tra esecuzioni/host.

### G3 — Incoerenze env backend
- `settings.py` usa prefisso `ME4BRAIN_` per host/port/debug/loglevel (`port` default 8089) e alias specifici per DB/Redis/Qdrant/Neo4j.
- I `.env` correnti usano molte chiavi legacy (`BACKEND_PORT`, `DB_*`) non sempre allineate agli alias effettivamente letti dalle settings runtime.

### G4 — Gateway con default legacy 8089 in più punti
- File con fallback hardcoded a `http://localhost:8089`:
  - `routes/config.ts`
  - `routes/providers.ts`
  - `services/session_manager_instance.ts`
  - `services/graph_session_service.ts` (note/commenti legacy)
  - `services/title_generator.ts` (hardcoded assoluto)
- Rischio: comportamenti divergenti se `ME4BRAIN_URL` non propagato uniformemente.

### G5 — Docker non operativo come utente corrente
- Utente non in gruppo `docker`.
- Compose plugin assente (`docker compose` fallisce).
- Conseguenza: non avviabili facilmente servizi `postgres/redis/qdrant` via `docker-compose.dev.yml`.

### G6 — GPU memory pressure alta
- VRAM già molto occupata da display/desktop (~94%).
- Impatto su stabilità inferenza embedding/torch lato GPU, soprattutto su iGPU condivisa.

---

## 4) Decisioni architetturali raccomandate

## D1 — Rendere deterministico PyTorch con UV (obbligatorio)
Usare configurazione **`[tool.uv.sources] + [[tool.uv.index]] explicit=true`** per pin esplicito di `torch` (e pacchetti correlati se necessario) a index desiderato:

- Opzione A (stabilità immediata): `cpu` index PyTorch
- Opzione B (accelerazione AMD): index ROCm compatibile con stack selezionato

> Nota: su backend applicativo la priorità è la stabilità; ROCm può essere introdotto come step controllato post-stabilizzazione.

## D2 — Uniformare endpoint backend su 8000 (obbligatorio)
Porta canonicale: `8000`.  
Eliminare fallback runtime a `8089` in gateway (attività implementativa futura).

## D3 — Infrastruttura locale via Docker solo dopo remediation host
Prima fix host (`docker` group + compose plugin). Se non possibile entro SLA, fallback temporaneo a servizi nativi (`apt/systemd`) per Redis/Postgres e container singoli per Qdrant/Neo4j o alternative locali.

## D4 — Avvio backend senza `uv run me4brain` finché non è risolto G1
Eseguire check di risoluzione dipendenze prima dello startup completo.

---

## 5) Piano operativo dettagliato (per implementazione successiva)

## Fase 0 — Safety baseline e snapshot
**Obiettivo**: congelare stato e ridurre rischio regressioni.

Attività:
1. Snapshot file chiave (`pyproject.toml`, env, compose, route gateway).
2. Acquisire report baseline:
   - toolchain versioni (`python`, `uv`, `node`, `npm`, `docker`)
   - stato GPU (`rocminfo`, `rocm-smi`)
   - stato porte.
3. Definire cartella evidenze runbook (`docs/issues_analysis/local-deploy-baseline-<date>/`).

Deliverable:
- Baseline report markdown + dump comandi.

---

## Fase 1 — Remediation host Docker
**Obiettivo**: rendere operativo `docker compose` senza sudo continuo.

Attività:
1. Installare/abilitare plugin Compose (pacchetto distro o plugin ufficiale).
2. Aggiungere utente al gruppo docker (`usermod -aG docker $USER`), re-login/newgrp.
3. Verificare:
   - `docker ps`
   - `docker compose version`
   - accesso a `/var/run/docker.sock`.
4. Ripulire eventuale `~/.docker` ownership errata (se in passato usato sudo).

Criteri uscita:
- `docker run hello-world` eseguito senza sudo.
- `docker compose` disponibile.

Rollback:
- usare temporaneamente `sudo docker ...` solo per bootstrap infrastruttura.

---

## Fase 2 — Determinismo dipendenze backend (UV + torch)
**Obiettivo**: bloccare definitivamente download NVIDIA non desiderati.

Attività:
1. Introdurre sezione UV in `backend/pyproject.toml`:
   - `[[tool.uv.index]]` con index PyTorch scelto
   - `explicit = true`
   - `[tool.uv.sources] torch = { index = "..." }`
2. Valutare se pin esteso anche a `torchvision`/`torchaudio`/`pytorch-triton-rocm` (solo se presenti/transitivi necessari).
3. Rigenerare lock backend (`uv lock`) in modo riproducibile.
4. `uv sync` e verifica import:
   - `import torch`
   - `torch.__version__`
   - `torch.cuda.is_available()`
   - `torch.version.hip` (se build ROCm)
5. Verificare assenza download CUDA NVIDIA nei log di sync/run.

Decisione tecnica consigliata:
- **Step 2A**: partire con build CPU per sbloccare sistema.
- **Step 2B**: promuovere a ROCm solo dopo E2E stabile.

Rischi:
- mismatch versione torch/sentence-transformers.
- wheel ROCm non disponibile per combinazione Python/ROCm/arch.

Mitigazioni:
- pin versione torch nota compatibile.
- fallback CPU documentato e automatizzabile.

---

## Fase 3 — Normalizzazione configurazione `.env`
**Obiettivo**: allineare variabili realmente lette da runtime.

Attività:
1. Mappare variabili effettive da `settings.py` (backend) e `validateEnv` (gateway shared).
2. Consolidare env minimi:
   - backend: `ME4BRAIN_HOST`, `ME4BRAIN_PORT=8000`, `ME4BRAIN_DEBUG`, `POSTGRES_*`, `REDIS_*`, `QDRANT_*`, `NEO4J_*`
   - gateway: `PORT=3030`, `ME4BRAIN_URL=http://localhost:8000`, `REDIS_URL=redis://localhost:6379`
   - frontend: endpoint gateway/frontend coerenti.
3. Rimuovere/evitare ambiguità tra `DB_*` vs `POSTGRES_*`, `BACKEND_PORT` vs `ME4BRAIN_PORT`.

Deliverable:
- matrice variabili “definite vs consumate”.

---

## Fase 4 — Avvio infrastruttura dati
**Obiettivo**: rendere disponibili PostgreSQL, Redis, Qdrant, Neo4j.

Percorso preferito:
1. `docker compose -f docker-compose.dev.yml up -d` (postgres/redis/qdrant)
2. Avvio Neo4j (container dedicato o servizio locale)
3. Health checks:
   - Postgres `pg_isready`
   - Redis `PING`
   - Qdrant `/health` o `/collections`
   - Neo4j bolt/http reachability

Fallback (se Docker non pronto):
- installazione nativa minima via apt per Postgres/Redis, Qdrant/Neo4j con binari/container singoli gestiti manualmente.

---

## Fase 5 — Avvio backend con verifiche progressive
**Obiettivo**: backend healthy su `:8000` senza loop dipendenze.

Attività:
1. Test preliminare Python/torch nel venv UV.
2. Startup backend con env normalizzato.
3. Verifica endpoint:
   - `/health/live`
   - `/health/ready`
   - `/health`
   - `/health/models`
4. Analisi log startup su:
   - inizializzazione memorie (qdrant/neo4j)
   - check LLM provider
   - warning degradazione accettabili/non accettabili.

Accettazione fase:
- backend risponde su 8000 senza trigger installazioni massive inattese.

---

## Fase 6 — Allineamento Gateway/Frontend (runtime contract)
**Obiettivo**: eliminare dipendenza implicita da porta 8089.

Attività implementative future (code changes previste):
1. Sostituire fallback hardcoded 8089 con `ME4BRAIN_URL` canonicale.
2. Uniformare route proxy e servizi helper.
3. Garantire che `ME4BRAIN_URL` non aggiunga `/v1` dove il client lo aggiunge già.
4. Avviare gateway e validare:
   - startup log URL backend corretto
   - assenza 404/502 da mismatch porta.
5. Avviare frontend su 3020 e validare flussi chat base.

---

## Fase 7 — Verifica end-to-end e criteri di successo
**Obiettivo**: validazione completa contro handoff.

Checklist finale:
1. `curl http://localhost:8000/health` → 200
2. `curl http://localhost:3030` → gateway attivo
3. `curl http://localhost:3020` → frontend attivo
4. Gateway log: Redis connected (no degraded)
5. Backend embedding/torch operativo con backend scelto (CPU o ROCm)
6. Se ROCm abilitato:
   - `torch.cuda.is_available()` true
   - `torch.version.hip` valorizzato

---

## Fase 8 — Hardening operativo e runbook
**Obiettivo**: rendere ripetibile il deployment locale.

Attività:
1. Script bootstrap unico (`scripts/local-deploy-bootstrap.sh`) con check idempotenti.
2. Script health aggregation (`scripts/local-health-check.sh`).
3. Aggiornamento documentazione (`docs/LOCAL_DEPLOYMENT.md`) con sezione AMD/ROCm e troubleshooting reale.
4. Definizione policy di fallback:
   - fallback CPU automatico se GPU non disponibile
   - timeout/avvisi chiari.

---

## 6) Matrice rischi

| Rischio | Prob. | Impatto | Mitigazione |
|---|---:|---:|---|
| Wheel ROCm non compatibile con versione Python corrente | Media | Alta | Strategia 2-step (CPU stable → ROCm), pin versioni note |
| Docker ancora non utilizzabile da utente | Alta | Alta | remediation gruppo + plugin, fallback servizi nativi |
| Mismatch env tra moduli gateway | Alta | Media | refactor centralizzato su ConfigService + audit fallback |
| VRAM insufficiente su iGPU condivisa | Alta | Media | preferire CPU per embeddings o ridurre workload GPU |
| Health check segnala errori cosmetici Neo4j | Media | Bassa | distinguere blocking vs non-blocking nel runbook |

---

## 7) Decisione consigliata per minima2.7 (implementazione)

Ordine operativo raccomandato:

1. **Fix Docker host** (gruppo + compose plugin)  
2. **Pin UV torch index + lock backend**  
3. **Portare backend in stato stabile (anche CPU-only se necessario)**  
4. **Allineare gateway a backend:8000 rimuovendo fallback 8089**  
5. **E2E test completo**  
6. **Opzionale: promozione a ROCm**, solo dopo stabilità

Questo ordine massimizza probabilità di successo e riduce debug combinatorio.

---

## 8) Non-obiettivi di questa fase

- Nessuna modifica codice applicata ora.
- Nessun commit/push effettuato.
- Nessuna alterazione infrastrutturale irreversibile eseguita.

---

## 9) Allegato: incongruenze da correggere nella prossima fase

1. Path target richiesto dall’utente: `/doces/plans` (non standard rispetto a `/docs`).  
2. Documentazione storica mescola porte 3000/3020 e 8089/8000.  
3. `docs/DEPLOYMENT_STATUS.md` indica stato “fully functional”, ma verifica corrente non conferma listener attivi.  
4. `backend/uv.lock` citato in handoff ma assente nell’albero attuale.

---

## 10) Output atteso per fase implementativa successiva

Il modello minima2.7 dovrà produrre:

1. Patch configurazione Python/UV deterministica per torch.
2. Patch config gateway per eliminare fallback legacy 8089.
3. Runbook operativo aggiornato con check e recovery.
4. Report finale con evidenze comando-per-comando e stato servizi.
