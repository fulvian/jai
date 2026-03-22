# Me4BrAIn Working Memory API Reference

**Versione**: 1.1  
**Base URL**: `http://localhost:8000/v1/working`

---

## 🔐 Autenticazione

```bash
X-API-Key: your-secret-key
```

---

## 📚 Endpoints - Sessions

### POST `/sessions` - Crea Sessione

Crea una nuova sessione di working memory con un messaggio di sistema iniziale.

**Request Body:**
```json
{
  "user_id": "default",
  "metadata": {"title": "Nuova Chat"}
}
```

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "default",
  "created_at": "2026-02-04T12:00:00Z"
}
```

---

### GET `/sessions` - Lista Sessioni

Lista tutte le sessioni utente con metadati.

**Query Parameters:**
| Parametro | Tipo   | Default  | Descrizione          |
| --------- | ------ | -------- | -------------------- |
| `user_id` | string | required | ID utente            |
| `limit`   | int    | 50       | Numero max risultati |

**Response:**
```json
{
  "sessions": [
    {
      "session_id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "Chat su progetto ANCI",
      "created_at": "2026-02-04T10:00:00Z",
      "updated_at": "2026-02-04T12:00:00Z",
      "message_count": 15
    }
  ],
  "count": 1
}
```

**Esempio curl:**
```bash
curl "http://localhost:8000/v1/working/sessions?user_id=default&limit=20"
```

---

### GET `/sessions/{session_id}` - Info Sessione

Recupera metadati di una singola sessione.

**Path Parameters:**
| Parametro    | Tipo   | Descrizione       |
| ------------ | ------ | ----------------- |
| `session_id` | string | ID della sessione |

**Query Parameters:**
| Parametro | Tipo   | Required | Descrizione |
| --------- | ------ | -------- | ----------- |
| `user_id` | string | yes      | ID utente   |

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Chat su progetto ANCI",
  "created_at": "2026-02-04T10:00:00Z",
  "updated_at": "2026-02-04T12:00:00Z",
  "message_count": 15
}
```

---

### PATCH `/sessions/{session_id}` - Aggiorna Sessione

Aggiorna metadati sessione (es. titolo).

**Path Parameters:**
| Parametro    | Tipo   | Descrizione       |
| ------------ | ------ | ----------------- |
| `session_id` | string | ID della sessione |

**Query Parameters:**
| Parametro | Tipo   | Required | Descrizione |
| --------- | ------ | -------- | ----------- |
| `user_id` | string | yes      | ID utente   |

**Request Body:**
```json
{
  "title": "Nuovo titolo sessione"
}
```

**Response:**
```json
{
  "updated": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Nuovo titolo sessione"
}
```

**Esempio curl:**
```bash
curl -X PATCH "http://localhost:8000/v1/working/sessions/my-session-id?user_id=default" \
  -H "Content-Type: application/json" \
  -d '{"title": "Nuovo titolo"}'
```

---

### DELETE `/sessions/{session_id}` - Elimina Sessione

Elimina una sessione e tutti i suoi dati (messaggi, grafo, metadati).

**Response:**
```json
{
  "deleted": true,
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## 📚 Endpoints - Messages

### POST `/sessions/{session_id}/messages` - Aggiungi Messaggio

Aggiunge un messaggio alla sessione.

**Request Body:**
```json
{
  "role": "user",
  "content": "Che tempo fa a Roma?",
  "metadata": {}
}
```

**Response:**
```json
{
  "message_id": "1707043200000-0",
  "session_id": "...",
  "created_at": "2026-02-04T12:00:00Z"
}
```

---

### GET `/sessions/{session_id}/messages` - Lista Messaggi

Recupera messaggi di una sessione con paginazione.

**Query Parameters:**
| Parametro | Tipo   | Default | Descrizione              |
| --------- | ------ | ------- | ------------------------ |
| `limit`   | int    | 50      | Numero max messaggi      |
| `before`  | string | -       | ID prima di cui caricare |

---

## 🐍 Esempi Python (SDK)

```python
from me4brain_sdk import AsyncMe4BrAInClient

async with AsyncMe4BrAInClient(base_url="http://localhost:8000") as client:
    # Crea sessione
    session = await client.working.create_session(user_id="user-1")
    
    # Lista sessioni
    sessions = await client.working.list_sessions(user_id="user-1")
    for s in sessions["sessions"]:
        print(f"{s['session_id']}: {s['title']}")
    
    # Aggiorna titolo
    await client.working.update_session(
        session_id=session.session_id,
        user_id="user-1",
        title="Nuova chat importante"
    )
```

---

## 🔧 Architettura Storage (Redis)

| Risorsa          | Redis Type | Chiave                                         |
| ---------------- | ---------- | ---------------------------------------------- |
| Session Index    | SET        | `tenant:{tid}:user:{uid}:sessions:index`       |
| Session Metadata | HASH       | `tenant:{tid}:user:{uid}:session:{sid}:meta`   |
| Message Stream   | STREAM     | `tenant:{tid}:user:{uid}:session:{sid}:stream` |
| Session Graph    | STRING     | `tenant:{tid}:user:{uid}:session:{sid}:graph`  |

**TTL**: 24 ore (86400 secondi) per tutti i dati sessione.
