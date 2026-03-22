"""Script per sincronizzare catalogo tool in Qdrant.

Svuota la collection tools e re-indicizza solo i tool attualmente funzionanti.
"""

import asyncio
import uuid
from typing import Any

# Tool attualmente implementati e funzionanti
ACTIVE_TOOLS = [
    # ==========================================================================
    # GOOGLE WORKSPACE (15 tools)
    # ==========================================================================
    {
        "name": "google_drive_list_files",
        "description": "Elenca file e cartelle da Google Drive. List files and folders.",
        "endpoint": "internal://GoogleDriveService/list_files",
        "service": "GoogleDriveService",
    },
    {
        "name": "google_drive_get_file",
        "description": "Ottiene metadati di un file Google Drive. Get file metadata.",
        "endpoint": "internal://GoogleDriveService/get_file",
        "service": "GoogleDriveService",
    },
    {
        "name": "google_drive_search",
        "description": "Cerca file per nome in Google Drive. Search files by name.",
        "endpoint": "internal://GoogleDriveService/search",
        "service": "GoogleDriveService",
    },
    {
        "name": "google_gmail_search",
        "description": "Cerca email per query in Gmail. Search emails.",
        "endpoint": "internal://GoogleGmailService/search",
        "service": "GoogleGmailService",
    },
    {
        "name": "google_gmail_get_message",
        "description": "Legge email per ID da Gmail. Read email by ID.",
        "endpoint": "internal://GoogleGmailService/get_message",
        "service": "GoogleGmailService",
    },
    {
        "name": "google_calendar_search",
        "description": "Cerca eventi Google Calendar per testo. Cerca nel titolo, descrizione, location, partecipanti. Search calendar events by text query.",
        "endpoint": "internal://GoogleCalendarService/search",
        "service": "GoogleCalendarService",
        "parameters": {
            "query": {
                "type": "string",
                "description": "Testo da cercare negli eventi",
                "required": True,
            },
            "days": {
                "type": "integer",
                "description": "Giorni passati e futuri da cercare",
                "default": 60,
            },
        },
    },
    {
        "name": "google_calendar_upcoming",
        "description": "Eventi prossimi N giorni da Google Calendar. Upcoming events.",
        "endpoint": "internal://GoogleCalendarService/upcoming",
        "service": "GoogleCalendarService",
    },
    {
        "name": "google_calendar_get_event",
        "description": "Dettagli evento Google Calendar. Event details.",
        "endpoint": "internal://GoogleCalendarService/get_event",
        "service": "GoogleCalendarService",
    },
    {
        "name": "google_docs_get",
        "description": "Legge contenuto documento Google Docs. Read document content.",
        "endpoint": "internal://GoogleDocsService/get",
        "service": "GoogleDocsService",
    },
    {
        "name": "google_docs_create",
        "description": "Crea nuovo documento Google Docs. Create new document.",
        "endpoint": "internal://GoogleDocsService/create",
        "service": "GoogleDocsService",
    },
    {
        "name": "google_sheets_get_values",
        "description": "Valori da spreadsheet Google Sheets. Get spreadsheet values.",
        "endpoint": "internal://GoogleSheetsService/get_values",
        "service": "GoogleSheetsService",
    },
    {
        "name": "google_sheets_get_metadata",
        "description": "Info spreadsheet Google Sheets. Spreadsheet metadata.",
        "endpoint": "internal://GoogleSheetsService/get_metadata",
        "service": "GoogleSheetsService",
    },
    {
        "name": "google_slides_get",
        "description": "Info presentazione Google Slides. Presentation info.",
        "endpoint": "internal://GoogleSlidesService/get",
        "service": "GoogleSlidesService",
    },
    {
        "name": "google_slides_list",
        "description": "Lista slide con testo Google Slides. List slides with text.",
        "endpoint": "internal://GoogleSlidesService/list_slides",
        "service": "GoogleSlidesService",
    },
    {
        "name": "google_meet_create",
        "description": "Crea video meeting Google Meet. Create video meeting.",
        "endpoint": "internal://GoogleMeetService/create",
        "service": "GoogleMeetService",
    },
    {
        "name": "google_meet_get",
        "description": "Dettagli meeting Google Meet. Meeting details.",
        "endpoint": "internal://GoogleMeetService/get",
        "service": "GoogleMeetService",
    },
    # Google Keep - REQUIRES Workspace Enterprise (commented out)
    # {
    #     "name": "google_keep_list",
    #     "description": "Lista note Google Keep. List notes appunti memo promemoria.",
    #     "endpoint": "internal://GoogleKeepService/list_notes",
    #     "service": "GoogleKeepService",
    # },
    # Google Forms
    {
        "name": "google_forms_get",
        "description": "Info modulo Google Forms. Get form details questionario sondaggio.",
        "endpoint": "internal://GoogleFormsService/get_form",
        "service": "GoogleFormsService",
    },
    {
        "name": "google_forms_responses",
        "description": "Risposte modulo Google Forms. Get form responses questionario sondaggio.",
        "endpoint": "internal://GoogleFormsService/get_responses",
        "service": "GoogleFormsService",
    },
    # Google Classroom
    {
        "name": "google_classroom_courses",
        "description": "Lista corsi Google Classroom. List courses classe studenti.",
        "endpoint": "internal://GoogleClassroomService/list_courses",
        "service": "GoogleClassroomService",
    },
    {
        "name": "google_classroom_coursework",
        "description": "Compiti corso Google Classroom. Coursework assignments classe studenti.",
        "endpoint": "internal://GoogleClassroomService/get_coursework",
        "service": "GoogleClassroomService",
    },
    # ==========================================================================
    # FINANCE (11 tools)
    # ==========================================================================
    {
        "name": "binance_klines",
        "description": "STORICO PREZZI CRYPTO: dati storici giornalieri/settimanali Bitcoin Ethereum Solana. Candlestick OHLCV fino a 5+ anni. Usare per: correlazione storica, andamento ultimi N anni/mesi, grafico storico prezzi, historical data, time series.",
        "endpoint": "internal://BinanceService/get_klines",
        "service": "BinanceService",
    },
    {
        "name": "binance_price",
        "description": "PREZZO ATTUALE CRYPTO: prezzo corrente real-time in questo momento. Solo prezzo OGGI, ORA ADESSO. Non storico.",
        "endpoint": "internal://BinanceService/get_price",
        "service": "BinanceService",
    },
    {
        "name": "binance_ticker_24h",
        "description": "Statistiche 24h cryptocurrency Binance. 24h price change volume.",
        "endpoint": "internal://BinanceService/get_ticker_24h",
        "service": "BinanceService",
    },
    {
        "name": "yahoo_finance_history",
        "description": "STORICO PREZZI AZIONI: dati storici giornalieri/settimanali Apple Google Tesla MSFT. Fino a 10+ anni. Usare per: correlazione storica azioni, andamento ultimi N anni/mesi, historical data, time series.",
        "endpoint": "internal://YahooFinanceService/get_history",
        "service": "YahooFinanceService",
    },
    {
        "name": "yahoo_finance_quote",
        "description": "PREZZO ATTUALE AZIONI: quotazione corrente real-time in questo momento. Solo prezzo OGGI, ORA ADESSO. Non storico.",
        "endpoint": "internal://YahooFinanceService/get_quote",
        "service": "YahooFinanceService",
    },
    {
        "name": "coingecko_price",
        "description": "Prezzo corrente cryptocurrency CoinGecko. Current crypto price bitcoin ethereum.",
        "endpoint": "internal://CoinGeckoService/get_price",
        "service": "CoinGeckoService",
    },
    {
        "name": "coingecko_trending",
        "description": "Crypto trending top 7 CoinGecko. Trending cryptocurrencies.",
        "endpoint": "internal://CoinGeckoService/get_trending",
        "service": "CoinGeckoService",
    },
    {
        "name": "fred_search_series",
        "description": "Cerca serie economiche FRED. Search economic data series GDP inflation unemployment.",
        "endpoint": "internal://FREDService/search_series",
        "service": "FREDService",
    },
    {
        "name": "fred_get_observations",
        "description": "Dati storici serie FRED. Historical economic data observations.",
        "endpoint": "internal://FREDService/get_observations",
        "service": "FREDService",
    },
    {
        "name": "finnhub_quote",
        "description": "Quote stock real-time Finnhub. Stock quote price.",
        "endpoint": "internal://FinnhubService/get_quote",
        "service": "FinnhubService",
    },
    {
        "name": "finnhub_news",
        "description": "News mercati finanziari Finnhub. Market news company news.",
        "endpoint": "internal://FinnhubService/get_news",
        "service": "FinnhubService",
    },
    # ==========================================================================
    # SCIENCE & RESEARCH (7 tools)
    # ==========================================================================
    {
        "name": "arxiv_search",
        "description": "Cerca preprint arXiv. Search scientific papers preprints physics math CS.",
        "endpoint": "internal://ArxivService/search",
        "service": "ArxivService",
    },
    {
        "name": "crossref_search",
        "description": "Cerca DOI e metadata articoli Crossref. Search academic papers by DOI.",
        "endpoint": "internal://CrossrefService/search",
        "service": "CrossrefService",
    },
    {
        "name": "semantic_scholar_search",
        "description": "Cerca paper Semantic Scholar. Search academic papers citations.",
        "endpoint": "internal://SemanticScholarService/search",
        "service": "SemanticScholarService",
    },
    {
        "name": "openalex_works",
        "description": "Cerca lavori accademici OpenAlex. Search academic works knowledge graph.",
        "endpoint": "internal://OpenAlexService/get_works",
        "service": "OpenAlexService",
    },
    {
        "name": "europepmc_search",
        "description": "Cerca letteratura life sciences Europe PMC. Search biomedical papers.",
        "endpoint": "internal://EuropePMCService/search",
        "service": "EuropePMCService",
    },
    {
        "name": "pubmed_search",
        "description": "Cerca articoli biomedicali PubMed. Search biomedical literature.",
        "endpoint": "internal://PubMedService/search",
        "service": "PubMedService",
    },
    {
        "name": "pubmed_get_abstracts",
        "description": "Ottiene abstract PubMed. Get article abstracts.",
        "endpoint": "internal://PubMedService/get_abstracts",
        "service": "PubMedService",
    },
    # ==========================================================================
    # KNOWLEDGE & MEDIA (5 tools)
    # ==========================================================================
    {
        "name": "wikipedia_summary",
        "description": "Summary articoli Wikipedia. Get article summary.",
        "endpoint": "internal://WikipediaService/get_summary",
        "service": "WikipediaService",
    },
    {
        "name": "wikipedia_search",
        "description": "Cerca articoli Wikipedia. Search Wikipedia articles.",
        "endpoint": "internal://WikipediaService/search",
        "service": "WikipediaService",
    },
    {
        "name": "openlibrary_search",
        "description": "Cerca libri Open Library. Search books by title author.",
        "endpoint": "internal://OpenLibraryService/search",
        "service": "OpenLibraryService",
    },
    {
        "name": "hackernews_top",
        "description": "Top stories Hacker News. Tech news top stories.",
        "endpoint": "internal://HackerNewsService/get_top",
        "service": "HackerNewsService",
    },
    {
        "name": "duckduckgo_instant",
        "description": "Instant answers DuckDuckGo. Quick answers search.",
        "endpoint": "internal://DuckDuckGoService/instant_answer",
        "service": "DuckDuckGoService",
    },
    # ==========================================================================
    # GEO & WEATHER (6 tools)
    # ==========================================================================
    {
        "name": "openmeteo_weather",
        "description": "Meteo attuale Open-Meteo. Current weather temperature humidity.",
        "endpoint": "internal://OpenMeteoService/get_weather",
        "service": "OpenMeteoService",
    },
    {
        "name": "openmeteo_forecast",
        "description": "Previsioni meteo 7 giorni Open-Meteo. Weather forecast.",
        "endpoint": "internal://OpenMeteoService/get_forecast",
        "service": "OpenMeteoService",
    },
    {
        "name": "nominatim_geocode",
        "description": "Geocoding OSM Nominatim. Convert address to coordinates.",
        "endpoint": "internal://NominatimService/geocode",
        "service": "NominatimService",
    },
    {
        "name": "restcountries_name",
        "description": "Info paesi REST Countries. Country information by name.",
        "endpoint": "internal://RESTCountriesService/get_by_name",
        "service": "RESTCountriesService",
    },
    {
        "name": "usgs_earthquakes",
        "description": "Terremoti recenti USGS. Recent earthquakes worldwide.",
        "endpoint": "internal://USGSService/get_earthquakes",
        "service": "USGSService",
    },
    {
        "name": "nagerdate_holidays",
        "description": "Festività 90+ paesi Nager.Date. Public holidays by country.",
        "endpoint": "internal://NagerDateService/get_holidays",
        "service": "NagerDateService",
    },
    # ==========================================================================
    # UTILITY (3 tools)
    # ==========================================================================
    {
        "name": "ipify_ip",
        "description": "Public IP address ipify. Get current public IP.",
        "endpoint": "internal://IpifyService/get_ip",
        "service": "IpifyService",
    },
    {
        "name": "randomuser_generate",
        "description": "Genera dati fake user RandomUser. Generate fake user data.",
        "endpoint": "internal://RandomUserService/generate",
        "service": "RandomUserService",
    },
    {
        "name": "agify_age",
        "description": "Predici età da nome Agify. Predict age from name.",
        "endpoint": "internal://AgifyService/predict",
        "service": "AgifyService",
    },
    # ==========================================================================
    # SPORTS - NBA & BETTING (6 tools)
    # ==========================================================================
    {
        "name": "nba_upcoming_games",
        "description": "Prossime partite NBA programmate. Upcoming NBA games schedule match partite basket. BallDontLie API.",
        "endpoint": "internal://BallDontLieService/upcoming_games",
        "service": "BallDontLieService",
    },
    {
        "name": "nba_player_search",
        "description": "Cerca giocatore NBA per nome. Search NBA player by name LeBron Curry Durant.",
        "endpoint": "internal://BallDontLieService/get_players",
        "service": "BallDontLieService",
    },
    {
        "name": "nba_player_stats",
        "description": "Statistiche stagionali giocatore NBA. Season averages stats points rebounds assists.",
        "endpoint": "internal://BallDontLieService/season_averages",
        "service": "BallDontLieService",
    },
    {
        "name": "nba_betting_odds",
        "description": "Quote scommesse NBA partite basket. Betting odds NBA games bookmaker bet365 William Hill spread moneyline. The Odds API.",
        "endpoint": "internal://TheOddsAPIService/get_odds",
        "service": "TheOddsAPIService",
    },
    {
        "name": "espn_nba_scoreboard",
        "description": "Scoreboard NBA live punteggi partite in corso. ESPN live scores NBA games risultati.",
        "endpoint": "internal://ESPNService/get_scoreboard",
        "service": "ESPNService",
    },
    {
        "name": "espn_nba_injuries",
        "description": "Infortuni giocatori NBA. NBA player injuries injury report roster doubtful out questionable.",
        "endpoint": "internal://ESPNService/get_injuries",
        "service": "ESPNService",
    },
    {
        "name": "duckduckgo_nba_news",
        "description": "Cerca notizie NBA basket sul web. Search NBA news trades rumors. DuckDuckGo web search.",
        "endpoint": "internal://DuckDuckGoService/news",
        "service": "DuckDuckGoService",
    },
    # ==========================================================================
    # NBA STATS (nba_api library) - 6 tools
    # ==========================================================================
    {
        "name": "nba_search_players",
        "description": "Cerca giocatori NBA per nome con nba_api. Search NBA players by name.",
        "endpoint": "internal://NBAStatsService/search_players",
        "service": "NBAStatsService",
    },
    {
        "name": "nba_player_career_stats",
        "description": "Statistiche carriera giocatore NBA. Career stats points rebounds assists career averages.",
        "endpoint": "internal://NBAStatsService/get_player_career_stats",
        "service": "NBAStatsService",
    },
    {
        "name": "nba_teams",
        "description": "Lista tutte le squadre NBA. List all NBA teams franchises.",
        "endpoint": "internal://NBAStatsService/get_teams",
        "service": "NBAStatsService",
    },
    {
        "name": "nba_team_roster",
        "description": "Roster squadra NBA con giocatori attuali. Team roster current players.",
        "endpoint": "internal://NBAStatsService/get_team_roster",
        "service": "NBAStatsService",
    },
    {
        "name": "nba_game_boxscore",
        "description": "Boxscore partita NBA statistiche complete. Game boxscore full stats.",
        "endpoint": "internal://NBAStatsService/get_game_boxscore",
        "service": "NBAStatsService",
    },
    {
        "name": "nba_live_scoreboard",
        "description": "Partite NBA live in tempo reale oggi. Live games scoreboard today real-time.",
        "endpoint": "internal://NBAStatsService/get_live_scoreboard",
        "service": "NBAStatsService",
    },
    # ==========================================================================
    # TRADING APIs (7 tools)
    # ==========================================================================
    # Hyperliquid (Testnet) - Perpetual Crypto Trading
    {
        "name": "hyperliquid_mids",
        "description": "Mid prices tutti i perpetual crypto Hyperliquid. All perpetual mid prices BTC ETH SOL.",
        "endpoint": "internal://HyperliquidService/get_mids",
        "service": "HyperliquidService",
    },
    {
        "name": "hyperliquid_candles",
        "description": "Candlestick OHLCV perpetual crypto Hyperliquid. Candles chart data.",
        "endpoint": "internal://HyperliquidService/get_candles",
        "service": "HyperliquidService",
    },
    {
        "name": "hyperliquid_meta",
        "description": "Metadata exchange Hyperliquid. Asset info leverage margin perpetuals.",
        "endpoint": "internal://HyperliquidService/get_meta",
        "service": "HyperliquidService",
    },
    # Alpaca (Paper Trading) - Stock Trading
    {
        "name": "alpaca_account",
        "description": "Account portfolio Alpaca paper trading. Equity buying power cash value.",
        "endpoint": "internal://AlpacaService/get_account",
        "service": "AlpacaService",
    },
    {
        "name": "alpaca_positions",
        "description": "Posizioni aperte Alpaca paper trading. Open positions unrealized P&L.",
        "endpoint": "internal://AlpacaService/get_positions",
        "service": "AlpacaService",
    },
    {
        "name": "alpaca_quote",
        "description": "Quote real-time bid ask Alpaca. Real-time stock quote AAPL MSFT.",
        "endpoint": "internal://AlpacaService/get_quote",
        "service": "AlpacaService",
    },
    {
        "name": "alpaca_bars",
        "description": "OHLCV bars storico prezzi Alpaca. Historical bars candlestick.",
        "endpoint": "internal://AlpacaService/get_bars",
        "service": "AlpacaService",
    },
]


async def sync_tools_to_qdrant():
    """Svuota e re-indicizza tool in Qdrant."""
    from qdrant_client import AsyncQdrantClient, models
    from me4brain.embeddings import get_embedding_service
    from me4brain.config import get_settings

    settings = get_settings()
    embedding_service = get_embedding_service()

    qdrant_url = f"http://{settings.qdrant_host}:{settings.qdrant_http_port}"
    client = AsyncQdrantClient(
        url=qdrant_url,
        timeout=30,
    )

    collection_name = "tools"

    # Step 1: Svuota collection esistente
    print("🗑️  Svuotando collection tools...")
    try:
        await client.delete_collection(collection_name)
        print("   ✅ Collection eliminata")
    except Exception as e:
        print(f"   ⚠️  Collection non esisteva: {e}")

    # Step 2: Ricrea collection
    print("📦 Creando nuova collection...")
    await client.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=1024,  # BGE-M3 dimension
            distance=models.Distance.COSINE,
        ),
    )
    print("   ✅ Collection creata")

    # Step 3: Indicizza tutti i tool
    print(f"📝 Indicizzando {len(ACTIVE_TOOLS)} tool...")
    points = []

    for i, tool in enumerate(ACTIVE_TOOLS):
        tool_id = str(uuid.uuid4())
        embedding = embedding_service.embed_query(tool["description"])

        points.append(
            models.PointStruct(
                id=tool_id,
                vector=embedding,
                payload={
                    "name": tool["name"],
                    "description": tool["description"],
                    "endpoint": tool["endpoint"],
                    "service": tool["service"],
                    "tenant_id": "me4brain_core",
                    "method": "POST",
                    "status": "ACTIVE",  # Required by search filter
                },
            )
        )

        if (i + 1) % 10 == 0:
            print(f"   Processati {i + 1}/{len(ACTIVE_TOOLS)}...")

    # Upsert in batch
    await client.upsert(
        collection_name=collection_name,
        points=points,
    )

    print(f"\n✅ Sincronizzazione completata!")
    print(f"   Tool indicizzati: {len(ACTIVE_TOOLS)}")

    # Verifica
    info = await client.get_collection(collection_name)
    print(f"   Punti in collection: {info.points_count}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(sync_tools_to_qdrant())
