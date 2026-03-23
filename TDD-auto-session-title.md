# TDD: Auto Session Title Generation

## 1. Concept & Vision

Sistema di denominazione automatica delle sessioni chat che utilizza l'LLM per generare titoli descrittivi di 3-5 parole basati sulla query iniziale dell'utente. I titoli devono essere concisi, significativi e facilitare il recupero rapido delle conversazioni dalla sidebar.

## 2. User Journey

```
Come utente, voglio che le mie sessioni chat vengano automaticamente nominate 
in base al contenuto della mia prima domanda, così posso facilmente ritrovarle 
nella lista delle sessioni senza doverle rinominare manualmente.
```

## 3. Technical Design

### 3.1 Architecture Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Gateway   │────▶│  FastAPI     │────▶│  LLM Provider   │
│ (Fastify)   │     │  /generate   │     │  (Ollama/GPT)   │
│             │◀────│  -title      │◀────│                 │
└─────────────┘     └─────────────────┘     └─────────────────┘
```

### 3.2 New Endpoint

**POST** `/api/v1/sessions/generate-title`

Request:
```json
{
  "prompt": "string (required) - First user message, max 2000 chars"
}
```

Response:
```json
{
  "title": "string (3-5 words, max 50 chars)"
}
```

### 3.3 LLM Prompt Design

```
System: "You are a session title generator. Generate a short, descriptive title 
of exactly 3-5 words that summarizes the user's query. 
Respond ONLY with the title, no explanation or punctuation."

User: "{user_prompt}"

Expected output: "Keyword1 Keyword2 Keyword3"
```

### 3.4 Implementation Plan

#### Phase 1: Backend Service (Python)

**New file:** `backend/src/me4brain/api/routes/session_title.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/sessions", tags=["session"])

class GenerateTitleRequest(BaseModel):
    prompt: str = Field(..., max_length=2000)

class GenerateTitleResponse(BaseModel):
    title: str = Field(..., max_length=50)

@router.post("/generate-title", response_model=GenerateTitleResponse)
async def generate_session_title(request: GenerateTitleRequest) -> GenerateTitleResponse:
    """Generate a short session title from the user's first prompt."""
    # Implementation
```

**Dependencies:**
- Reuse existing `DynamicLLMClient` from `me4brain.llm.dynamic_client`
- Configurable via `get_settings().llm_*`

#### Phase 2: Gateway Integration (TypeScript)

**File:** `frontend/packages/gateway/src/services/title_generator.ts`

```typescript
export async function generateSessionTitle(prompt: string): Promise<string> {
  const response = await fetch(`${ME4BRAIN_API_URL}/api/v1/sessions/generate-title`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  });
  
  if (!response.ok) {
    throw new Error('Failed to generate title');
  }
  
  const data = await response.json();
  return data.title;
}
```

#### Phase 3: Integrate in ChatSessionStore

**File:** `frontend/packages/gateway/src/services/chat_session_store.ts`

Modify `addTurn()` method:
- On first user message, call `generateSessionTitle(prompt)` instead of slicing
- Fallback to slice if LLM call fails
- Timeout: 5 seconds max

```typescript
if (turnCount === 1 && turn.role === 'user') {
  try {
    meta.title = await generateSessionTitleWithTimeout(turn.content, 5000);
  } catch {
    // Fallback to simple truncation
    meta.title = turn.content.slice(0, 50) + (turn.content.length > 50 ? '...' : '');
  }
}
```

### 3.5 Error Handling

| Scenario | Behavior |
|----------|----------|
| LLM timeout (>5s) | Fallback to truncation |
| LLM returns empty | Fallback to truncation |
| LLM unavailable | Fallback to truncation |
| Invalid prompt (empty) | Return "Nuova conversazione" |

### 3.6 Configuration

```yaml
# backend/.env or config
SESSION_TITLE_MODEL: "llama3.2"  # Model for title generation
SESSION_TITLE_TIMEOUT: 5  # seconds
SESSION_TITLE_MAX_TOKENS: 20
```

## 4. File Structure

```
backend/src/me4brain/
├── api/routes/
│   └── session_title.py      # NEW: Title generation endpoint
├── llm/
│   └── title_generator.py    # NEW: LLM title generation logic

frontend/packages/gateway/src/
├── services/
│   ├── title_generator.ts    # NEW: Gateway-side title service
│   └── chat_session_store.ts # MODIFY: Integrate title generation
```

## 5. Testing Strategy

### Unit Tests (Python)
- `test_title_generator.py`: Test prompt formatting, response parsing
- Mock LLM responses

### Integration Tests (Python)
- `test_session_title_endpoint.py`: Test API endpoint with real LLM

### Unit Tests (TypeScript)
- `title_generator.test.ts`: Test timeout, fallback, error handling

### E2E Tests
- Create session, verify auto-generated title appears in sidebar

## 6. Acceptance Criteria

- [ ] Session title generated within 5 seconds
- [ ] Title is 3-5 words (max 50 characters)
- [ ] Fallback works when LLM unavailable
- [ ] Title appears correctly in sidebar session list
- [ ] 80%+ test coverage
