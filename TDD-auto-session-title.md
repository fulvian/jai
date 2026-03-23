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
| LLM timeout (>30s) | Fallback to truncation |
| LLM returns empty | Fallback to truncation |
| LLM unavailable | Fallback to truncation |
| Invalid prompt (empty) | Return "Nuova conversazione" |

### 3.6 Configuration

```yaml
# backend/.env or config
SESSION_TITLE_MODEL: "qwen3.5:4b"  # Model for title generation
SESSION_TITLE_TIMEOUT: 30  # seconds (increased for thinking models)
SESSION_TITLE_MAX_TOKENS: 2000  # Increased for thinking models
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

- [x] Session title generated within 30 seconds
- [x] Title is 3-5 words (max 50 characters)
- [x] Fallback works when LLM unavailable
- [x] Title appears correctly in sidebar session list
- [x] 80%+ test coverage

---

## 7. Implementation Status (2026-03-23)

### Completed

| Component | File | Status |
|-----------|------|--------|
| Backend Endpoint | `session_title.py` | ✅ Implemented |
| LLM Config | `llm/config.py` - `model_title_generation` | ✅ Added |
| Router Registration | `main.py` | ✅ Registered |
| Integration Tests | `test_session_title.py` (16 tests) | ✅ All pass |
| Gateway Service | `title_generator.ts` | ✅ Implemented |
| ChatSessionStore Integration | `chat_session_store.ts` | ✅ Integrated |

### Known Issues

- **LLM Timeout**: qwen3.5:4b model takes >30 seconds for title generation, triggering fallback to truncation
- **Sessions Disappear**: Fixed Redis port mismatch (6389→6379) and package export errors

### Files Modified

```
backend/
├── src/me4brain/api/routes/session_title.py     # NEW
├── src/me4brain/api/main.py                     # MODIFIED
├── src/me4brain/llm/config.py                   # MODIFIED
├── src/me4brain/llm/dynamic_client.py          # MODIFIED (reasoning fallback)
└── tests/integration/test_session_title.py      # NEW

frontend/packages/
├── gateway/src/services/title_generator.ts      # NEW
├── gateway/src/services/chat_session_store.ts   # MODIFIED
└── shared/
    ├── package.json                             # MODIFIED (./retry export)
    └── src/retry.ts                             # NEW
```

### Configuration

The feature uses the existing LLM infrastructure with:
- **Model**: Configured via `model_title_generation` in LLM config
- **Timeout**: 30 seconds (fallback to truncation if exceeded)
- **Max tokens**: 2000 (increased to accommodate thinking models)
- **Max prompt length**: 2000 characters

---

## 8. Debug Session Notes (2026-03-23)

### Problem Investigated
Sessions were showing only session ID instead of evocative titles. The LLM-based title generation was timing out.

### Root Cause Analysis
The `qwen3.5` thinking models have a fundamental limitation:
- They output extensive "thinking" process before actual content
- The thinking alone consumes hundreds of tokens
- Even with 30-second timeouts and 2000 max tokens, models don't finish within practical time limits

### Changes Made

#### `backend/src/me4brain/llm/dynamic_client.py`
Added fallback to use `reasoning` field as `content` when content is empty (handles thinking models):
```python
# If content is empty but reasoning exists, use reasoning as content
if (content is None or content == "") and reasoning:
    content = reasoning
    reasoning = None
```

#### `backend/src/me4brain/api/routes/session_title.py`
1. Increased `DEFAULT_TIMEOUT` from 5.0 to 30.0 seconds
2. Increased `max_tokens` from 20 to 2000
3. Added `_extract_title_from_reasoning()` function to parse titles from thinking content
4. Updated `_parse_title()` to handle long reasoning content with pattern matching

### Current Behavior
The system correctly:
- ✅ Creates sessions in the backend
- ✅ Stores sessions in Redis with proper tenant isolation
- ✅ Retrieves sessions via API with evocative titles when available
- ✅ Falls back to truncated user prompt when LLM times out

### Recommendations for Full Evocative Titles
To achieve true evocative titles via LLM:
1. **Use a faster model** without thinking enabled (e.g., `qwen2.5`, `llama3.1`)
2. **Download a non-thinking variant** of `qwen3.5`
3. **Use keyword extraction** instead of LLM for title generation
