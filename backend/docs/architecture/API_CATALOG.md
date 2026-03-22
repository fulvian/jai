# Me4BrAIn API Catalog

## Routing & Model Execution Policy (llm_local)

Nel branch `llm_local` il catalogo tool viene eseguito con policy **local-only**:

- nessuna dipendenza cloud per routing critico (intent/domain/tool selection)
- fallback cloud disabilitato per default
- coerenza query rewrite applicata lungo decomposition/retrieval/selection

Flag consigliati per ambiente locale:

```env
LLM_LOCAL_ONLY=true
LLM_ALLOW_CLOUD_FALLBACK=false
USE_STAGE0_INTENT_ANALYZER=true
USE_CONTEXT_REWRITE_FOR_ROUTING=true
USE_QUERY_DECOMPOSITION=true
```

> **Ultimo aggiornamento**: 3 Febbraio 2026  
> **Architettura**: Plugin-based modular domains + **Multi-Domain Orchestration v2.0**  
> **Totale Tools**: 125 su 15 domini

> [!NOTE]
> **NEW v2.0**: Supporto **query multi-dominio** - es. "Confronta BTC con meteo Roma" attiva `finance_crypto` + `geo_weather` in parallelo!

---

## 🚀 Multi-Domain Query (NEW)

```
"Confronta Bitcoin con meteo e partita Lakers"
    ↓
analyze_query() → domains_required: ["finance_crypto", "geo_weather", "sports_nba"]
    ↓
asyncio.gather() → esecuzione parallela 3 domini
    ↓
aggregate_results() → risposta cross-domain
```

---

## 📊 Statistiche Domini

| Dominio            | Tools   | Focus                     |
| ------------------ | ------- | ------------------------- |
| `google_workspace` | 38      | G Suite completo          |
| `finance_crypto`   | 20      | Trading + Dati mercati    |
| `tech_coding`      | 10      | GitHub, NPM, PyPI **NEW** |
| `medical`          | 8       | Biomedico specializzato   |
| `science_research` | 7       | Accademico generale       |
| `entertainment`    | 7       | Film, Libri, Musica       |
| `sports_nba`       | 7       | NBA analytics             |
| `food`             | 6       | Ricette e Prodotti        |
| `travel`           | 12      | Voli, Aeroporti, Booking  |
| `web_search`       | 4       | DDG + Tavily              |
| `geo_weather`      | 3       | Meteo e geolocalizzazione |
| `knowledge_media`  | 3       | Wikipedia, News           |
| `jobs`             | 2       | Lavori Remoti             |
| `utility`          | 2       | Network tools             |
| **TOTALE**         | **125** |                           |

---

## 💰 Finance & Crypto (20 tools)

### Market Data

| Tool                 | Provider      | Auth    | Descrizione             |
| -------------------- | ------------- | ------- | ----------------------- |
| `coingecko_price`    | CoinGecko     | No      | Prezzi crypto real-time |
| `coingecko_trending` | CoinGecko     | No      | Crypto trending 24h     |
| `coingecko_chart`    | CoinGecko     | No      | Storico prezzi          |
| `binance_price`      | Binance       | No      | Prezzo crypto           |
| `binance_ticker_24h` | Binance       | No      | Stats 24h               |
| `yahoo_quote`        | Yahoo Finance | No      | Quote azioni            |
| `finnhub_quote`      | Finnhub       | API Key | Quote real-time         |
| `finnhub_news`       | Finnhub       | API Key | News mercati            |

### Economic Data

| Tool           | Provider    | Auth    | Descrizione                 |
| -------------- | ----------- | ------- | --------------------------- |
| `fred_series`  | FRED        | API Key | Serie economiche (GDP, CPI) |
| `fred_search`  | FRED        | API Key | Ricerca serie               |
| `nasdaq_quote` | NASDAQ Data | API Key | Quote NASDAQ                |

### SEC Filings

| Tool                 | Provider  | Auth | Descrizione             |
| -------------------- | --------- | ---- | ----------------------- |
| `edgar_filings`      | SEC EDGAR | No   | Filings 10-K, 10-Q, 8-K |
| `edgar_company_info` | SEC EDGAR | No   | Info azienda            |

### Trading (Paper/Testnet)

| Tool                    | Provider    | Auth    | Descrizione          |
| ----------------------- | ----------- | ------- | -------------------- |
| `alpaca_account`        | Alpaca      | API Key | Info account paper   |
| `alpaca_positions`      | Alpaca      | API Key | Posizioni aperte     |
| `alpaca_quote`          | Alpaca      | API Key | Quote real-time      |
| `alpaca_bars`           | Alpaca      | API Key | OHLCV bars           |
| `hyperliquid_account`   | Hyperliquid | Wallet  | Info account testnet |
| `hyperliquid_positions` | Hyperliquid | Wallet  | Posizioni perp       |
| `hyperliquid_price`     | Hyperliquid | No      | Prezzi crypto        |

---

## 🔷 Google Workspace (37 tools)

OAuth2 richiesto. Setup: `uv run python scripts/google_oauth_setup.py`

### Drive (7 tools)

| Tool                         | Descrizione          |
| ---------------------------- | -------------------- |
| `google_drive_search`        | Cerca file           |
| `google_drive_list_files`    | Elenca file          |
| `google_drive_get_file`      | Metadati file        |
| `google_drive_get_content`   | **Estrae contenuto** |
| `google_drive_export`        | **Esporta PDF/DOCX** |
| `google_drive_create_folder` | **Crea cartella**    |
| `google_drive_copy`          | **Copia file**       |

### Gmail (5 tools)

| Tool                       | Descrizione     |
| -------------------------- | --------------- |
| `google_gmail_search`      | Cerca email     |
| `google_gmail_get_message` | Legge email     |
| `google_gmail_send`        | **Invia email** |
| `google_gmail_reply`       | **Risponde**    |
| `google_gmail_forward`     | **Inoltra**     |

### Calendar (6 tools)

| Tool                           | Descrizione         |
| ------------------------------ | ------------------- |
| `google_calendar_upcoming`     | Prossimi eventi     |
| `google_calendar_list_events`  | Lista eventi        |
| `google_calendar_create_event` | **Crea evento**     |
| `google_calendar_get_event`    | **Dettagli evento** |
| `google_calendar_update_event` | **Modifica evento** |
| `google_calendar_delete_event` | **Cancella evento** |

### Docs (5 tools)

| Tool                       | Descrizione           |
| -------------------------- | --------------------- |
| `google_docs_get`          | Legge documento       |
| `google_docs_create`       | **Crea documento**    |
| `google_docs_insert_text`  | **Inserisce testo**   |
| `google_docs_append_text`  | **Appende testo**     |
| `google_docs_replace_text` | **Trova/sostituisce** |

### Sheets (6 tools)

| Tool                          | Descrizione          |
| ----------------------------- | -------------------- |
| `google_sheets_get_values`    | Legge valori         |
| `google_sheets_get_metadata`  | Info spreadsheet     |
| `google_sheets_create`        | **Crea spreadsheet** |
| `google_sheets_update_values` | **Scrive valori**    |
| `google_sheets_append_row`    | **Aggiunge riga**    |
| `google_sheets_add_sheet`     | **Aggiunge foglio**  |

### Slides (4 tools)

| Tool                     | Descrizione            |
| ------------------------ | ---------------------- |
| `google_slides_get`      | Info presentazione     |
| `google_slides_create`   | **Crea presentazione** |
| `google_slides_get_text` | **Estrae testo**       |

### Altri (Meet, Forms, Classroom)

| Servizio      | Tool                              | Descrizione   |
| ------------- | --------------------------------- | ------------- |
| **Meet**      | `google_meet_create`              | Crea meeting  |
| **Forms**     | `google_forms_get`                | Ottiene form  |
|               | `google_forms_get_responses`      | Risposte form |
| **Classroom** | `google_classroom_list_courses`   | Lista corsi   |
|               | `google_classroom_get_coursework` | Coursework    |

---

## 🏥 Medical (8 tools) - BIOMEDICO

| Tool                  | Provider   | Auth | Descrizione         |
| --------------------- | ---------- | ---- | ------------------- |
| `rxnorm_drug_info`    | NIH RxNorm | No   | Info farmaci        |
| `rxnorm_interactions` | NIH RxNorm | No   | Interazioni farmaci |
| `rxnorm_spelling`     | NIH RxNorm | No   | Spelling farmaci    |
| `icite_metrics`       | NIH iCite  | No   | Metriche citazioni  |
| `icite_batch`         | NIH iCite  | No   | Batch PMID metrics  |
| `pubmed_search`       | PubMed     | No   | Ricerca biomedica   |
| `pubmed_abstract`     | PubMed     | No   | Abstract paper      |
| `europepmc_search`    | Europe PMC | No   | Life sciences       |

---

## 🔬 Science Research (7 tools) - ACCADEMICO GENERALE

| Tool                        | Provider         | Auth | Descrizione      |
| --------------------------- | ---------------- | ---- | ---------------- |
| `arxiv_search`              | ArXiv            | No   | Preprint search  |
| `crossref_doi`              | Crossref         | No   | DOI lookup       |
| `crossref_search`           | Crossref         | No   | Paper search     |
| `openalex_search`           | OpenAlex         | No   | Academic graph   |
| `semanticscholar_search`    | Semantic Scholar | No   | AI papers        |
| `semanticscholar_paper`     | Semantic Scholar | No   | Paper details    |
| `semanticscholar_citations` | Semantic Scholar | No   | Citation network |

---

## 🏀 Sports NBA (7 tools)

| Tool                 | Provider    | Auth    | Descrizione      |
| -------------------- | ----------- | ------- | ---------------- |
| `nba_upcoming_games` | BallDontLie | API Key | Prossime partite |
| `nba_player_search`  | BallDontLie | API Key | Cerca giocatori  |
| `nba_player_stats`   | BallDontLie | API Key | Stats stagionali |
| `nba_standings`      | BallDontLie | API Key | Classifica       |
| `nba_injuries`       | ESPN        | No      | Infortuni        |
| `nba_scoreboard`     | ESPN        | No      | Punteggi live    |
| `nba_betting_odds`   | TheOddsAPI  | API Key | Quote scommesse  |

---

## 🌍 Geo & Weather (3 tools)

| Tool                 | Provider   | Auth | Descrizione            |
| -------------------- | ---------- | ---- | ---------------------- |
| `openmeteo_weather`  | Open-Meteo | No   | Meteo current/forecast |
| `openmeteo_forecast` | Open-Meteo | No   | Previsioni 7 giorni    |
| `usgs_earthquakes`   | USGS       | No   | Terremoti recenti      |

---

## 📚 Knowledge & Media (3 tools)

| Tool                | Provider    | Auth | Descrizione      |
| ------------------- | ----------- | ---- | ---------------- |
| `wikipedia_search`  | Wikipedia   | No   | Cerca articoli   |
| `wikipedia_summary` | Wikipedia   | No   | Summary articolo |
| `hackernews_top`    | Hacker News | No   | Top stories      |

---

## 🔧 Utility (2 tools)

| Tool            | Provider | Auth | Descrizione     |
| --------------- | -------- | ---- | --------------- |
| `ipinfo_lookup` | IPInfo   | No   | Info IP address |
| `url_preview`   | -        | No   | URL metadata    |

---

## 🔍 Web Search (4 tools)

| Tool                 | Provider   | Auth    | Costo        | Descrizione              |
| -------------------- | ---------- | ------- | ------------ | ------------------------ |
| `duckduckgo_instant` | DuckDuckGo | No      | ∞ Free       | Instant answers          |
| `tavily_search`      | Tavily     | API Key | 1-2 credit   | **Deep AI search**       |
| `tavily_extract`     | Tavily     | API Key | 1 credit/URL | **Estrazione contenuti** |
| `smart_search`       | Auto       | -       | Varies       | **Routing DDG/Tavily**   |

> **Strategia**: DDG per query semplici (free), Tavily per ricerche complesse (1000 credits/mese)

---

## 🎬 Entertainment (7 tools) **NEW**

| Tool                   | Provider     | Auth    | Descrizione        |
| ---------------------- | ------------ | ------- | ------------------ |
| `tmdb_search_movie`    | TMDB         | API Key | Cerca film         |
| `tmdb_movie_details`   | TMDB         | API Key | Dettagli film      |
| `tmdb_trending`        | TMDB         | API Key | Trending film/TV   |
| `openlibrary_search`   | Open Library | No      | Cerca libri        |
| `openlibrary_book`     | Open Library | No      | Dettagli per ISBN  |
| `lastfm_search_artist` | Last.fm      | API Key | Cerca artisti      |
| `lastfm_top_tracks`    | Last.fm      | API Key | Top tracks artista |

---

## 🍕 Food (6 tools) **NEW**

| Tool                    | Provider        | Auth | Descrizione             |
| ----------------------- | --------------- | ---- | ----------------------- |
| `mealdb_search`         | TheMealDB       | No   | Cerca ricette           |
| `mealdb_random`         | TheMealDB       | No   | Ricetta casuale         |
| `mealdb_by_ingredient`  | TheMealDB       | No   | Ricette per ingrediente |
| `mealdb_categories`     | TheMealDB       | No   | Categorie ricette       |
| `openfoodfacts_search`  | Open Food Facts | No   | Cerca prodotti          |
| `openfoodfacts_product` | Open Food Facts | No   | Info per barcode        |

---

## 🛫 Travel (12 tools) **UPDATED**

### Amadeus Self-Service (Free Tier) - NEW

| Tool                     | Provider | Auth    | Descrizione                   |
| ------------------------ | -------- | ------- | ----------------------------- |
| `amadeus_search_flights` | Amadeus  | API Key | Cerca voli con prezzi         |
| `amadeus_airport_search` | Amadeus  | API Key | Cerca aeroporti per nome      |
| `amadeus_confirm_price`  | Amadeus  | API Key | Conferma prezzo prima booking |
| `amadeus_book_flight`    | Amadeus  | API Key | Prenota volo con dati pass.   |

### OpenSky Network (Free)

| Tool                   | Provider        | Auth | Descrizione        |
| ---------------------- | --------------- | ---- | ------------------ |
| `opensky_flights_live` | OpenSky Network | No   | Voli live tracking |
| `opensky_flight_track` | OpenSky Network | No   | Traccia volo       |
| `opensky_arrivals`     | OpenSky Network | No   | Arrivi aeroporto   |

### ADS-B One (Free) - NEW

| Tool                        | Provider  | Auth | Descrizione              |
| --------------------------- | --------- | ---- | ------------------------ |
| `adsb_aircraft_by_location` | ADS-B One | No   | Aerei vicino a posizione |
| `adsb_aircraft_by_icao`     | ADS-B One | No   | Aereo per codice ICAO    |
| `adsb_aircraft_by_callsign` | ADS-B One | No   | Aereo per callsign       |

### AviationStack (Deprecated)

| Tool                     | Provider      | Auth    | Descrizione          |
| ------------------------ | ------------- | ------- | -------------------- |
| `aviationstack_flight`   | AviationStack | API Key | Info volo (100/mese) |
| `aviationstack_airports` | AviationStack | API Key | Cerca aeroporti      |

---

## 💼 Jobs (2 tools) **NEW**

| Tool             | Provider  | Auth | Descrizione        |
| ---------------- | --------- | ---- | ------------------ |
| `remoteok_jobs`  | RemoteOK  | No   | Lavori tech remoti |
| `arbeitnow_jobs` | Arbeitnow | No   | Lavori EU          |

---

## � Tech/Coding (10 tools) **NEW**

### GitHub (4 tools)

| Tool                  | Auth    | Descrizione      |
| --------------------- | ------- | ---------------- |
| `github_repo`         | PAT opt | Info repository  |
| `github_search_repos` | PAT opt | Cerca repos      |
| `github_issues`       | PAT opt | Lista issues     |
| `github_search_code`  | PAT req | Cerca nel codice |

### Package Managers (3 tools)

| Tool           | Provider | Auth | Descrizione         |
| -------------- | -------- | ---- | ------------------- |
| `npm_package`  | NPM      | No   | Info package JS     |
| `npm_search`   | NPM      | No   | Cerca packages      |
| `pypi_package` | PyPI     | No   | Info package Python |

### Q&A & Code Execution (3 tools)

| Tool                   | Provider       | Auth    | Descrizione             |
| ---------------------- | -------------- | ------- | ----------------------- |
| `stackoverflow_search` | Stack Overflow | API Key | Cerca Q&A               |
| `piston_runtimes`      | Piston         | No      | Lista linguaggi         |
| `piston_execute`       | Piston         | No      | **Esegui codice** (50+) |

---

## �🔑 API Keys Richieste

Configurare in `.env`:

```env
# Finance
FINNHUB_API_KEY=...
FRED_API_KEY=...
NASDAQ_DATA_API_KEY=...
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
HYPERLIQUID_WALLET_ADDRESS=...

# Travel (Amadeus)
AMADEUS_CLIENT_ID=...
AMADEUS_CLIENT_SECRET=...
AMADEUS_ENV=test  # or 'production'

# Sports
BALLDONTLIE_API_KEY=...
THE_ODDS_API_KEY=...

# Google (OAuth)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

---

## 🏗️ Architettura Domini

```
src/me4brain/domains/
├── finance_crypto/      # 20 tools
├── google_workspace/    # 16 tools
├── medical/             # 8 tools (NEW)
├── science_research/    # 7 tools
├── sports_nba/          # 7 tools
├── geo_weather/         # 3 tools
├── knowledge_media/     # 3 tools
├── utility/             # 2 tools
└── web_search/          # 1 tool
```

Ogni dominio espone `get_handler()` per auto-discovery via `PluginRegistry`.
