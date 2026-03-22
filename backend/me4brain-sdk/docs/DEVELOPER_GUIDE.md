# Me4BrAIn SDK - Developer Documentation

> Complete Python SDK for the Me4BrAIn Agentic Memory Platform

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Client Configuration](#client-configuration)
4. [Memory Namespaces](#memory-namespaces)
   - [Working Memory](#working-memory)
   - [Episodic Memory](#episodic-memory)
   - [Semantic Memory](#semantic-memory)
   - [Procedural Memory](#procedural-memory)
   - [Cognitive Interface](#cognitive-interface)
5. [Tool Integration](#tool-integration)
6. [Domain Domains](#domain-domains)
7. [Error Handling](#error-handling)
8. [Advanced Usage](#advanced-usage)
9. [API Reference](#api-reference)

---

## Installation

```bash
# Basic installation
pip install me4brain-sdk

# With optional dependencies
pip install me4brain-sdk[telemetry]   # OpenTelemetry
pip install me4brain-sdk[security]    # mTLS/HIPAA
pip install me4brain-sdk[langchain]   # LangChain integration
pip install me4brain-sdk[all]         # Everything
```

### From Source

```bash
git clone https://github.com/fulvian/me4brain.git
cd me4brain/me4brain-sdk
pip install -e ".[dev]"
```

---

## Quick Start

### Async Client (Recommended)

```python
import asyncio
from me4brain_sdk import AsyncMe4BrAInClient

async def main():
    async with AsyncMe4BrAInClient(
        base_url="http://localhost:8100",
        api_key="your-api-key",
    ) as client:
        # Simple query
        response = await client.cognitive.query(
            query="What did we discuss yesterday?"
        )
        print(response.answer)

asyncio.run(main())
```

### Sync Client

```python
from me4brain_sdk import Me4BrAInClient

with Me4BrAInClient(
    base_url="http://localhost:8100",
    api_key="your-api-key",
) as client:
    response = client.query("What did we discuss?")
    print(response.answer)
```

---

## Client Configuration

### Full Configuration Options

```python
from me4brain_sdk import AsyncMe4BrAInClient

client = AsyncMe4BrAInClient(
    # Required
    base_url="http://localhost:8100",
    
    # Authentication
    api_key="your-api-key",           # API key for auth
    
    # Tenant/User defaults
    tenant_id="default",              # Default tenant
    user_id="user-1",                 # Default user ID
    
    # HTTP Settings
    timeout=30.0,                     # Request timeout (seconds)
    max_retries=3,                    # Retry attempts
    pool_connections=100,             # Connection pool size
    pool_maxsize=100,                 # Max connections per host
    
    # Custom headers
    extra_headers={
        "X-Request-ID": "custom-id",
        "X-Trace-ID": "trace-123",
    },
)
```

### Environment Variables

```bash
export ME4BRAIN_BASE_URL="http://localhost:8100"
export ME4BRAIN_API_KEY="your-api-key"
export ME4BRAIN_TENANT_ID="default"
```

---

## Memory Namespaces

### Working Memory

Short-term session context management.

```python
# Create a session
session = await client.working.create_session(user_id="user-1")
print(f"Session ID: {session.id}")

# Add conversation turns
await client.working.add_turn(
    session_id=session.id,
    role="user",
    content="What's the weather in Milan?"
)

await client.working.add_turn(
    session_id=session.id,
    role="assistant",
    content="The weather in Milan is sunny, 22°C."
)

# Get session context (sliding window)
context = await client.working.get_context(
    session_id=session.id,
    max_turns=10,
    max_tokens=4000,
)

# List recent sessions
sessions = await client.working.list_sessions(user_id="user-1", limit=10)

# Delete session
await client.working.delete_session(session.id)
```

### Episodic Memory

Long-term autobiographical event storage.

```python
from datetime import datetime

# Store an episode
episode = await client.episodic.store(
    content="Had a productive meeting about Q4 budget with the finance team",
    summary="Q4 budget meeting",
    importance=0.8,
    source="meeting",
    tags=["meeting", "budget", "Q4"],
    event_time=datetime.now(),
    metadata={"attendees": ["Alice", "Bob"]},
)
print(f"Stored episode: {episode.id}")

# Search episodes by semantic similarity
results = await client.episodic.search(
    query="budget discussions",
    limit=10,
    min_score=0.5,
    tags=["meeting"],
    since=datetime(2024, 1, 1),
)

for result in results:
    print(f"  {result.content[:50]}... (score: {result.score:.2f})")

# Get related episodes
related = await client.episodic.get_related(episode.id, limit=5)

# Update episode metadata
await client.episodic.update(
    episode_id=episode.id,
    importance=0.9,
    tags=["meeting", "budget", "Q4", "approved"],
)

# Delete episode
await client.episodic.delete(episode.id)
```

### Semantic Memory

Knowledge graph operations (Neo4j-backed).

```python
# Create an entity
entity = await client.semantic.create_entity(
    name="Apple Inc",
    entity_type="Organization",
    properties={"industry": "Technology", "founded": 1976},
)

# List entities by type (without semantic query)
# Supports pagination with limit/offset
result = await client.semantic.list_entities(
    entity_type="Project",  # Optional: filter by type
    limit=100,
    offset=0,
)
print(f"Total: {result['total']}")
for entity in result["entities"]:
    print(f"  {entity['name']} ({entity['type']})")

# Search entities (semantic search)
results = await client.semantic.search(
    query="technology company",
    limit=10,
    entity_type="Organization",
    cross_layer=True,  # Include other memory layers
)

# Traverse knowledge graph
graph = await client.semantic.traverse(
    start_entity="entity-123",
    max_depth=3,
    max_nodes=50,
    relation_types=["WORKS_AT", "KNOWS", "PART_OF"],
)
print(f"Found {len(graph.nodes)} nodes, {len(graph.edges)} edges")

# Personalized PageRank
ranked = await client.semantic.pagerank(
    seed_entities=["entity-1", "entity-2"],
    top_k=10,
    damping=0.85,
)
for result in ranked:
    print(f"  {result.entity_id}: {result.score:.4f}")

# Create relation between entities
relation = await client.semantic.create_relation(
    source_id="entity-1",
    target_id="entity-2",
    relation_type="WORKS_AT",
    properties={"since": "2020"},
    weight=0.9,
)

# Merge duplicate entities
merge_result = await client.semantic.merge_entities(
    entity_ids=["entity-dup-1", "entity-dup-2"],
    target_name="Merged Entity",
    strategy="keep_all_properties",
)

# Consolidate episodic → semantic
consolidation = await client.semantic.consolidate(
    min_importance=0.7,
    max_age_hours=24,
    dry_run=False,
)
```

### Procedural Memory

Skills and tool pattern management.

```python
# List registered skills
skills = await client.procedural.list_skills(limit=50)
for skill in skills:
    print(f"  {skill.name}: {skill.description}")

# Get intent-to-tool mappings
mappings = await client.procedural.intent_map(
    query="calculate financial projections",
    limit=20,
)
for mapping in mappings:
    print(f"  Intent: {mapping.intent}")
    print(f"  Tools: {mapping.matched_tools}")

# Get muscle memory patterns (cached tool selections)
patterns = await client.procedural.muscle_memory(limit=50)
for pattern in patterns:
    print(f"  {pattern.intent} → {pattern.tool_name} ({pattern.success_count} uses)")

# Search tools
tools = await client.procedural.search_tools(
    query="weather forecast",
    limit=10,
    category="geo_weather",
)

# Register a new skill
skill = await client.procedural.register_skill(
    name="custom_calculator",
    description="Advanced mathematical calculations",
    endpoint="/api/calculate",
    method="POST",
    api_schema={"type": "object", "properties": {...}},
)
```

### Cognitive Interface

Natural language queries with memory integration.

```python
# Standard query
response = await client.cognitive.query(
    query="What did we discuss about the budget?",
    session_id="session-123",
    use_episodic=True,
    use_semantic=True,
    use_procedural=True,
    memory_limit=10,
    min_relevance=0.5,
)

print(f"Answer: {response.answer}")
print(f"Confidence: {response.confidence}")
print(f"Reasoning steps: {len(response.reasoning_steps)}")
print(f"Sources:")
print(f"  - Episodic: {len(response.episodic_results)}")
print(f"  - Semantic: {len(response.semantic_results)}")
print(f"  - Tools used: {response.tools_used}")

# Streaming query
async for chunk in client.cognitive.query_stream(
    query="Summarize all project meetings",
    session_id="session-123",
):
    print(chunk.content, end="", flush=True)
    if chunk.reasoning_step:
        print(f"\n[Reasoning: {chunk.reasoning_step.thought}]")

# Multi-step reasoning
response = await client.cognitive.reason(
    query="What's the best approach to reduce costs?",
    context=[{"type": "document", "content": "..."}],
    max_steps=5,
)

# Plan generation
plan = await client.cognitive.plan(
    goal="Increase sales by 20%",
    constraints=["Budget limited to $10k", "Timeline: 3 months"],
)
```

### SSE Streaming Chunk Types

The `query_stream()` method returns Server-Sent Events (SSE) with different chunk types:

| Chunk Type | Description            | Content                                              |
| ---------- | ---------------------- | ---------------------------------------------------- |
| `start`    | Stream initialization  | `session_id`, `thread_id`                            |
| `status`   | Pipeline status update | Status message (e.g., "Analizzando query...")        |
| `analysis` | Query analysis result  | `intent`, `requires_tools`, `data_needs`, `entities` |
| `tool`     | Tool execution result  | `tool_name`, `success`, `result`                     |
| `content`  | Response token         | Streaming text token                                 |
| `done`     | Stream completion      | `confidence` score                                   |
| `error`    | Error occurred         | Error message                                        |

**Example: Handling All Chunk Types**

```python
async for chunk in client.cognitive.query_stream(query="What's the weather?"):
    match chunk.chunk_type:
        case "start":
            print(f"Session: {chunk.session_id}")
        case "status":
            print(f"[Status] {chunk.content}")
        case "analysis":
            print(f"[Analysis] Intent: {chunk.analysis.get('intent')}")
        case "tool":
            tool = chunk.tool_call
            print(f"[Tool] {tool['tool']}: {'✓' if tool['success'] else '✗'}")
        case "content":
            print(chunk.content, end="", flush=True)
        case "done":
            print(f"\n[Done] Confidence: {chunk.confidence}")
        case "error":
            print(f"[Error] {chunk.content}")

---

## Tool Integration

### Using the Tools Namespace

```python
# List all tools
tools = await client.tools.list(limit=100)

# Search tools
results = await client.tools.search(
    query="calculate taxes",
    limit=10,
    category="finance",
    min_score=0.5,
)

# Execute a tool
execution = await client.tools.execute(
    tool_id="calculator",
    parameters={"expression": "100 * 1.21"},
)
print(f"Result: {execution.result}")
print(f"Success: {execution.success}")
print(f"Latency: {execution.latency_ms}ms")

# List categories
categories = await client.tools.categories()
# ["medical", "finance", "google_workspace", ...]

# Get tool by ID
tool = await client.tools.get("weather_current")

# Register custom tool
new_tool = await client.tools.register(
    name="my_custom_tool",
    description="Does something custom",
    category="utility",
    endpoint="https://api.example.com/custom",
    method="POST",
    api_schema={...},
)
```

---

## Domain Domains

Type-safe wrappers for specialized tool categories.

### Medical Domain

```python
# Drug interactions
result = await client.domains.medical.drug_interactions(
    drugs=["warfarin", "aspirin", "ibuprofen"],
    include_severity=True,
)
print(f"Severity summary: {result.severity_summary}")
for interaction in result.interactions:
    print(f"  {interaction}")

# Drug information
info = await client.domains.medical.drug_info("metformin")

# PubMed search
articles = await client.domains.medical.pubmed_search(
    query="diabetes treatment 2024",
    max_results=10,
    sort="date",
)
for article in articles:
    print(f"  {article.title} - {article.journal}")

# Clinical trials
trials = await client.domains.medical.clinical_trials_search(
    condition="lung cancer",
    status="recruiting",
    max_results=10,
)

# ICD lookup
codes = await client.domains.medical.icd_lookup("diabetes", version="10")
```

### Google Workspace Domain

```python
from datetime import datetime, timedelta

# Calendar events
events = await client.domains.google_workspace.calendar_events(
    max_results=10,
    time_min=datetime.now(),
    time_max=datetime.now() + timedelta(days=7),
)

# Create calendar event
event = await client.domains.google_workspace.calendar_create_event(
    title="Team Meeting",
    start=datetime(2024, 1, 15, 10, 0),
    end=datetime(2024, 1, 15, 11, 0),
    description="Weekly sync",
    attendees=["alice@example.com", "bob@example.com"],
)

# Gmail search
emails = await client.domains.google_workspace.gmail_search(
    query="from:boss@company.com subject:urgent",
    max_results=10,
)

# Send email
await client.domains.google_workspace.gmail_send(
    to=["recipient@example.com"],
    subject="Report",
    body="Please find attached...",
    cc=["manager@example.com"],
)

# Drive search
files = await client.domains.google_workspace.drive_search(
    query="Q4 report",
    max_results=10,
)

# Sheets read
data = await client.domains.google_workspace.sheets_read(
    spreadsheet_id="abc123",
    range="Sheet1!A1:D10",
)
```

### Finance Domain

```python
# Stock quote
quote = await client.domains.finance.stock_quote("AAPL")
print(f"Apple: ${quote.price} ({quote.change_percent:+.2f}%)")

# Stock history
history = await client.domains.finance.stock_history("MSFT", period="1y")

# Crypto price
btc = await client.domains.finance.crypto_price("BTC")
print(f"Bitcoin: ${btc.price_usd:,.2f}")

# Top cryptocurrencies
top_crypto = await client.domains.finance.crypto_list_top(limit=10)

# Financial news
news = await client.domains.finance.financial_news("Apple earnings", max_results=5)

# Currency conversion
result = await client.domains.finance.currency_convert(100, "USD", "EUR")
```

### Geo/Weather Domain

```python
# Current weather
weather = await client.domains.geo_weather.current("Milan, IT")
print(f"{weather.location}: {weather.temperature}°C, {weather.description}")

# Weather forecast
forecast = await client.domains.geo_weather.forecast("New York", days=5)
for day in forecast:
    print(f"  {day.date}: {day.temp_high}°/{day.temp_low}° - {day.description}")

# Geocoding
locations = await client.domains.geo_weather.geocode("Paris, France")
for loc in locations:
    print(f"  {loc.name}, {loc.country}: ({loc.lat}, {loc.lon})")

# Reverse geocode
location = await client.domains.geo_weather.reverse_geocode(45.4642, 9.1900)

# Air quality
aqi = await client.domains.geo_weather.air_quality("Beijing")
```

### Web Search Domain

```python
# Tavily search
results = await client.domains.web_search.tavily(
    query="latest AI developments 2024",
    max_results=10,
    search_depth="advanced",
)

# DuckDuckGo search
results = await client.domains.web_search.duckduckgo("Python tutorials")

# Wikipedia lookup
article = await client.domains.web_search.wikipedia("Artificial Intelligence")
print(f"{article.title}: {article.summary[:200]}...")

# News search
news = await client.domains.web_search.news("technology", max_results=10)
```

### Tech/Coding Domain

```python
# GitHub search
repos = await client.domains.tech_coding.github_search(
    query="fastapi async database",
    max_results=10,
    sort="stars",
)

# GitHub user
user = await client.domains.tech_coding.github_user("torvalds")

# StackOverflow search
questions = await client.domains.tech_coding.stackoverflow_search(
    query="Python async await",
    tagged=["python", "asyncio"],
)

# Code execution (sandboxed)
result = await client.domains.tech_coding.execute_code(
    code="print(sum(range(100)))",
    language="python",
)
print(f"Output: {result.output}")

# Package info
npm_pkg = await client.domains.tech_coding.npm_package("express")
pypi_pkg = await client.domains.tech_coding.pypi_package("fastapi")
```

### Science/Research Domain

```python
# arXiv search
papers = await client.domains.science_research.arxiv(
    query="transformer attention mechanism",
    max_results=10,
    sort_by="relevance",
)

# Semantic Scholar
papers = await client.domains.science_research.semantic_scholar(
    query="BERT language model",
    max_results=10,
    year=2023,
)

# Paper citations
citations = await client.domains.science_research.paper_citations(
    paper_id="649def34f8be52c8b66281af98ae884c09aef38b",
    max_results=20,
)

# Paper references
refs = await client.domains.science_research.paper_references(paper_id)
```

### Entertainment Domain

```python
# Movie search
movies = await client.domains.entertainment.movie_search("Inception")

# Movie details
movie = await client.domains.entertainment.movie_details(27205)

# Music artist
artist = await client.domains.entertainment.music_artist("Radiohead")

# Top tracks
tracks = await client.domains.entertainment.music_top_tracks("Coldplay", limit=10)

# Book search
books = await client.domains.entertainment.book_search("Dune")
```

### Food Domain

```python
# Recipe search
recipes = await client.domains.food.recipe_search("pasta carbonara")

# Recipe details
recipe = await client.domains.food.recipe_by_id("52770")
print(f"Instructions: {recipe.instructions}")

# Nutrition lookup
nutrition = await client.domains.food.nutrition_lookup("3017620422003")  # barcode

# Nutrition search
products = await client.domains.food.nutrition_search("coca cola")
```

### Travel Domain

```python
# Flights in area
flights = await client.domains.travel.flights_in_area(
    lat_min=45.0, lat_max=46.5,
    lon_min=7.0, lon_max=12.0,
)

# Flight by ICAO
flight = await client.domains.travel.flight_by_icao("abc123")

# Airport search
airports = await client.domains.travel.airport_search("Milan")

# Airport info
airport = await client.domains.travel.airport_info("LIML")
```

### Utility Domain

```python
# Calculator
result = await client.domains.utility.calculate("sqrt(144) + 2^3")
print(f"Result: {result.result}")

# QR code generation
qr = await client.domains.utility.qr_code("https://example.com", size=300)
print(f"QR URL: {qr.image_url}")

# Unit conversion
conversion = await client.domains.utility.unit_convert(100, "km", "miles")

# UUID generation
uuid = await client.domains.utility.uuid_generate(version=4)

# Hash text
hash = await client.domains.utility.hash_text("password", algorithm="sha256")
```

### Sports/NBA Domain

```python
# Search players
players = await client.domains.sports_nba.search_players("LeBron")
for player in players:
    print(f"  {player.first_name} {player.last_name} - {player.team}")

# Get player stats
stats = await client.domains.sports_nba.player_stats(player_id=123, season=2024)
print(f"PPG: {stats.points_per_game}, RPG: {stats.rebounds_per_game}")

# List teams
teams = await client.domains.sports_nba.list_teams()

# Today's games
games = await client.domains.sports_nba.games_today()
for game in games:
    print(f"  {game.home_team} vs {game.visitor_team}")

# Games by date
games = await client.domains.sports_nba.games_by_date("2024-01-15")
```

### Knowledge/Media Domain

```python
# Wikipedia article
article = await client.domains.knowledge_media.wikipedia("Python programming")
print(f"{article.title}: {article.summary[:200]}...")

# Wikipedia search
titles = await client.domains.knowledge_media.wikipedia_search("artificial intelligence")
print(f"Found articles: {titles}")

# News search
articles = await client.domains.knowledge_media.news_search("technology AI", max_results=10)
for article in articles:
    print(f"  {article.title} - {article.source}")

# Top headlines
headlines = await client.domains.knowledge_media.news_top_headlines(
    country="us",
    category="technology",
)
```

### Jobs Domain

```python
# Search remote jobs
jobs = await client.domains.jobs.search("python developer", max_results=20)
for job in jobs:
    print(f"  {job.title} at {job.company}")
    print(f"    {job.salary or 'Salary not specified'}")

# List jobs by category
jobs = await client.domains.jobs.list_jobs(category="software-dev", limit=30)

# Get job categories
categories = await client.domains.jobs.categories()
print(f"Available categories: {categories}")
```

---

## Error Handling

```python
from me4brain_sdk import (
    Me4BrAInError,
    Me4BrAInAPIError,
    Me4BrAInConnectionError,
    Me4BrAInTimeoutError,
    Me4BrAInAuthError,
    Me4BrAInRateLimitError,
    Me4BrAInNotFoundError,
    Me4BrAInValidationError,
)

try:
    response = await client.cognitive.query("test")
except Me4BrAInAuthError as e:
    print(f"Authentication failed: {e}")
    # Re-authenticate or refresh token
except Me4BrAInRateLimitError as e:
    print(f"Rate limited, retry after: {e.retry_after}s")
    await asyncio.sleep(e.retry_after)
except Me4BrAInNotFoundError as e:
    print(f"Resource not found: {e}")
except Me4BrAInValidationError as e:
    print(f"Validation error: {e.errors}")
except Me4BrAInTimeoutError as e:
    print(f"Request timed out: {e}")
except Me4BrAInConnectionError as e:
    print(f"Connection failed: {e}")
except Me4BrAInAPIError as e:
    print(f"API error {e.status_code}: {e.message}")
except Me4BrAInError as e:
    print(f"Generic error: {e}")
```

---

## Advanced Usage

### Custom HTTP Configuration

```python
import httpx

# Custom transport
transport = httpx.AsyncHTTPTransport(
    retries=3,
    verify=False,  # For self-signed certs
)

client = AsyncMe4BrAInClient(
    base_url="https://me4brain.local",
    api_key="key",
    # Pass custom headers for mTLS, tracing, etc.
    extra_headers={
        "X-Client-Cert": "...",
        "X-Trace-ID": "...",
    },
)
```

### Context Manager

```python
# Recommended: use as context manager
async with AsyncMe4BrAInClient(...) as client:
    await client.query("test")
# Connection closed automatically
```

### Concurrent Requests

```python
import asyncio

async def main():
    async with AsyncMe4BrAInClient(...) as client:
        # Parallel queries
        results = await asyncio.gather(
            client.episodic.search("budget"),
            client.semantic.search("finance team"),
            client.tools.search("calculator"),
        )
        episodes, entities, tools = results
```

### Retry Configuration

The SDK uses [tenacity](https://tenacity.readthedocs.io/) for retries:

- **Retry on**: 429 (rate limit), 500-599 (server errors), connection errors
- **Backoff**: Exponential (1s, 2s, 4s...)
- **Max attempts**: Configurable via `max_retries`

---

## API Reference

### Models

| Model           | Description                  |
| --------------- | ---------------------------- |
| `Session`       | Working memory session       |
| `Turn`          | Conversation turn in session |
| `Episode`       | Episodic memory event        |
| `Entity`        | Knowledge graph entity       |
| `Relation`      | Entity relationship          |
| `Tool`          | Tool/skill definition        |
| `QueryResponse` | Cognitive query result       |
| `StreamChunk`   | Streaming response chunk     |
| `HealthStatus`  | API health check             |
| `Stats`         | System statistics            |

### Namespaces

| Namespace           | Description          |
| ------------------- | -------------------- |
| `client.working`    | Session management   |
| `client.episodic`   | Event storage/search |
| `client.semantic`   | Knowledge graph      |
| `client.procedural` | Skills/tools         |
| `client.cognitive`  | NL queries           |
| `client.tools`      | Tool execution       |
| `client.admin`      | System admin         |

### Domains

| Domain             | Tools                                      |
| ------------------ | ------------------------------------------ |
| `medical`          | drug_interactions, pubmed, clinical_trials |
| `google_workspace` | calendar, gmail, drive, sheets             |
| `finance`          | stocks, crypto, currency                   |
| `geo_weather`      | weather, geocode                           |
| `web_search`       | tavily, duckduckgo, wikipedia              |
| `tech_coding`      | github, stackoverflow, code_exec           |
| `science_research` | arxiv, semantic_scholar                    |
| `entertainment`    | movies, music, books                       |
| `food`             | recipes, nutrition                         |
| `travel`           | flights, airports                          |
| `utility`          | calculator, qr, uuid                       |
| `sports_nba`       | players, teams, games, stats               |
| `knowledge_media`  | wikipedia, news                            |
| `jobs`             | remote_search, categories                  |

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development setup and guidelines.

## License

MIT License - See [LICENSE](./LICENSE) for details.
