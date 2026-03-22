# Me4BrAIn Tools API Reference

**Versione**: 1.0  
**Base URL**: `http://localhost:8089/v1/tools`

---

## 🔐 Autenticazione

L'API supporta autenticazione tramite API Key via header HTTP.

```bash
# Header di autenticazione
X-API-Key: your-secret-key
```

**Modalità Sviluppo**: Se `ME4BRAIN_API_KEY` non è configurata nel `.env`, l'autenticazione è disabilitata (bypass mode).

**Modalità Produzione**: Impostare `ME4BRAIN_API_KEY=your-secret-key` nel file `.env`.

---

## 📚 Endpoints

### POST `/search` - Ricerca Semantica

Cerca tools utilizzando ricerca semantica per intent in linguaggio naturale.

**Request Body:**
```json
{
  "query": "prezzo bitcoin in tempo reale",
  "limit": 10,
  "categories": [],
  "min_score": 0.3
}
```

| Campo        | Tipo     | Default  | Descrizione                       |
| ------------ | -------- | -------- | --------------------------------- |
| `query`      | string   | required | Intent in linguaggio naturale     |
| `limit`      | int      | 10       | Numero massimo risultati (1-50)   |
| `categories` | string[] | []       | Filtro per categorie              |
| `min_score`  | float    | 0.3      | Score minimo per inclusione (0-1) |

**Response:**
```json
{
  "query": "prezzo bitcoin in tempo reale",
  "results": [
    {
      "tool_id": "abc123",
      "name": "coingecko_price",
      "description": "Get current cryptocurrency prices",
      "score": 0.87,
      "category": "coingecko",
      "endpoint": "https://api.coingecko.com/api/v3/simple/price",
      "method": "GET"
    }
  ],
  "total": 1
}
```

**Esempio curl:**
```bash
curl -X POST http://localhost:8089/v1/tools/search \
  -H "Content-Type: application/json" \
  -d '{"query": "prezzo bitcoin", "limit": 5}'
```

---

### GET `/list` - Lista Paginata

Ottiene una lista paginata di tutti i tools disponibili.

**Query Parameters:**
| Parametro       | Tipo   | Default  | Descrizione                            |
| --------------- | ------ | -------- | -------------------------------------- |
| `limit`         | int    | 20       | Numero di risultati per pagina (1-100) |
| `offset`        | int    | 0        | Offset per paginazione                 |
| `status_filter` | string | "ACTIVE" | Filtra per status                      |

**Response:**
```json
{
  "tools": [
    {
      "tool_id": "abc123",
      "name": "coingecko_price",
      "description": "Get current cryptocurrency prices",
      "score": 0.85,
      "category": "coingecko",
      "endpoint": "...",
      "method": "GET"
    }
  ],
  "total": 32664,
  "limit": 20,
  "offset": 0
}
```

**Esempio curl:**
```bash
curl "http://localhost:8089/v1/tools/list?limit=10&offset=0"
```

---

### GET `/{tool_id}` - Dettagli Tool

Ottiene i dettagli completi di un singolo tool.

**Path Parameters:**
| Parametro | Tipo   | Descrizione         |
| --------- | ------ | ------------------- |
| `tool_id` | string | ID univoco del tool |

**Response:**
```json
{
  "id": "abc123",
  "name": "coingecko_price",
  "description": "Get current cryptocurrency prices from CoinGecko",
  "endpoint": "https://api.coingecko.com/api/v3/simple/price",
  "method": "GET",
  "status": "ACTIVE",
  "version": "1.0",
  "api_schema": {
    "parameters": {
      "ids": "string",
      "vs_currencies": "string"
    }
  },
  "success_rate": 0.95,
  "avg_latency_ms": 150.5,
  "total_calls": 1234
}
```

**Esempio curl:**
```bash
curl http://localhost:8089/v1/tools/coingecko_price
```

---

### POST `/execute` - Esecuzione Tool

Esegue un tool con i parametri specificati.

**Request Body:**
```json
{
  "tool_id": "coingecko_price",
  "arguments": {
    "ids": "bitcoin",
    "vs_currencies": "usd"
  },
  "intent": "Get Bitcoin price in USD",
  "use_cache": true
}
```

| Campo       | Tipo   | Default  | Descrizione                      |
| ----------- | ------ | -------- | -------------------------------- |
| `tool_id`   | string | required | ID del tool da eseguire          |
| `arguments` | object | {}       | Argomenti per il tool            |
| `intent`    | string | ""       | Descrizione intent (per caching) |
| `use_cache` | bool   | true     | Usa Muscle Memory cache          |

**Response:**
```json
{
  "success": true,
  "tool_id": "coingecko_price",
  "tool_name": "coingecko_price",
  "result": {
    "bitcoin": {
      "usd": 45000
    }
  },
  "error": null,
  "latency_ms": 150.5,
  "cached": false
}
```

**Esempio curl:**
```bash
curl -X POST http://localhost:8089/v1/tools/execute \
  -H "Content-Type: application/json" \
  -d '{
    "tool_id": "coingecko_price",
    "arguments": {"ids": "bitcoin", "vs_currencies": "usd"}
  }'
```

---

### GET `/categories` - Lista Categorie

Ottiene l'elenco delle categorie disponibili con conteggio tools.

**Response:**
```json
{
  "categories": [
    {"name": "coingecko", "tool_count": 15},
    {"name": "google", "tool_count": 7},
    {"name": "openmeteo", "tool_count": 5}
  ],
  "total_tools": 32664
}
```

**Esempio curl:**
```bash
curl http://localhost:8089/v1/tools/categories
```

---

## 🐍 Esempi Python

### Ricerca Tool

```python
import httpx

async def search_tools(query: str, limit: int = 10):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8089/v1/tools/search",
            json={"query": query, "limit": limit},
            headers={"X-API-Key": "your-secret-key"}  # opzionale
        )
        return response.json()

# Uso
results = await search_tools("meteo roma")
for tool in results["results"]:
    print(f"{tool['name']}: {tool['description']}")
```

### Esecuzione Tool

```python
async def execute_tool(tool_id: str, arguments: dict):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8089/v1/tools/execute",
            json={
                "tool_id": tool_id,
                "arguments": arguments,
                "use_cache": True
            }
        )
        result = response.json()
        if result["success"]:
            return result["result"]
        else:
            raise Exception(result["error"])

# Uso
price = await execute_tool(
    "coingecko_price",
    {"ids": "bitcoin", "vs_currencies": "eur"}
)
print(f"Bitcoin: €{price['bitcoin']['eur']}")
```

---

## ⚠️ Codici di Errore

| Codice | Descrizione                   |
| ------ | ----------------------------- |
| 200    | Successo                      |
| 401    | API Key mancante o non valida |
| 404    | Tool non trovato              |
| 500    | Errore interno del server     |

---

## 🔧 Configurazione

Variabili d'ambiente in `.env`:

```env
# API Key (vuoto = nessuna auth per sviluppo)
ME4BRAIN_API_KEY=

# Port API
ME4BRAIN_PORT=8089
```
