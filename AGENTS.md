# AGENTS.md - Coding Agent Guidelines for JAI

This document provides essential information for AI coding agents working in this repository.

## Project Overview

JAI is a monorepo containing:
- **Backend**: Me4BrAIn - Hybrid routing LLM engine with agentic memory (Python/FastAPI)
- **Frontend**: PersAn - Conversational AI interface (TypeScript/Next.js/Fastify)

---

## Build/Lint/Test Commands

### Backend (Python)

```bash
cd backend

# Package manager: uv
uv sync                    # Install dependencies
uv sync --extra dev        # Install dev dependencies

# Linting & Formatting (Ruff)
uv run ruff check src tests           # Check lint issues
uv run ruff check --fix .             # Auto-fix lint issues
uv run ruff format .                  # Format code

# Type Checking (mypy)
uv run mypy src/

# Testing (pytest)
uv run pytest                         # Run all tests
uv run pytest tests/unit              # Run unit tests only
uv run pytest tests/integration       # Run integration tests only
uv run pytest tests/unit/test_cache.py              # Run single test file
uv run pytest tests/unit/test_cache.py::TestCacheKey  # Run single test class
uv run pytest tests/unit/test_cache.py::TestCacheKey::test_generate_simple_key  # Single test
uv run pytest -v --cov=src --cov-report=term-missing # With coverage

# Pre-commit
uv run pre-commit install             # Install hooks
uv run pre-commit run --all-files     # Run all hooks

# Run server
uv run me4brain                       # Start API server (port 8089)
```

### Frontend (TypeScript)

```bash
cd frontend

# Package manager: npm
npm install                           # Install dependencies

# Build (Turborepo)
npm run build                         # Build all packages
npm run lint                          # Lint all packages
npm run typecheck                     # Type check all packages

# Testing (Vitest)
npm run test                          # Run all tests
npm test -- --filter=@persan/shared   # Run tests for specific package

# Per-package commands
cd frontend/packages/shared
npm run test                          # Run tests for shared package
npm run build                         # Build shared package
npm run typecheck                     # Type check shared package

# Development
npm run dev                           # Start all in dev mode
cd frontend/frontend && npm run dev   # Start Next.js dev server (port 3020)
```

---

## Code Style Guidelines

### Python (Backend)

#### Imports
```python
# Standard library first
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

# Third-party second
import structlog
from fastapi import FastAPI

# Local imports last (me4brain modules)
from me4brain.config import get_settings
from me4brain.utils.logging import configure_logging
```

#### Type Annotations
- **Always use type hints** (mypy strict mode is enabled)
- Use `async def` for async functions
- Use `AsyncGenerator`, `Awaitable` from `collections.abc`
- Use Pydantic models for data validation

```python
# Correct
async def get_data(id: int) -> dict[str, Any]:
    ...

def process(items: list[str]) -> int | None:
    ...

# Use explicit Optional for clarity when needed
from typing import Optional
def find_user(id: int) -> Optional[User]:
    ...
```

#### Naming Conventions
- **Functions/Methods**: `snake_case` (e.g., `get_user_by_id`, `process_query`)
- **Classes**: `PascalCase` (e.g., `CacheManager`, `ToolCallingEngine`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `MAX_RETRIES`, `DEFAULT_TIMEOUT`)
- **Private methods**: Prefix with `_` (e.g., `_generate_cache_key`)
- **Modules**: `snake_case` (e.g., `cache_manager.py`)

#### Error Handling
- Use structured logging with `structlog`
- Raise specific exceptions with descriptive messages
- Use `tenacity` for retries

```python
import structlog
logger = structlog.get_logger(__name__)

try:
    result = await risky_operation()
except SpecificError as e:
    logger.error("operation_failed", error=str(e), context=additional_info)
    raise
```

#### Testing (pytest)
- Place tests in `tests/` mirroring `src/` structure
- Use `pytest.mark.asyncio` for async tests
- Use descriptive test names: `test_<function>_<scenario>`
- Group related tests in classes: `class TestFeatureName`

```python
class TestCacheKey:
    """Test per generazione cache key."""

    @pytest.mark.asyncio
    async def test_cached_hit(self):
        """Test cache hit."""
        ...
```

### TypeScript (Frontend)

#### Imports
```typescript
// Node/external modules first
import { z } from 'zod';
import { describe, it, expect } from 'vitest';

// Internal modules second (use @persan/* aliases)
import { ErrorCode } from '../errors.js';
import type { Config } from './config.js';
```

#### Type Annotations
- **Always use explicit types** (strict mode enabled)
- Use `type` for object types, `interface` for extendable contracts
- Use discriminated unions for Result types

```typescript
// Result type pattern
export type Result<T, E extends AppError = AppError> =
    | { success: true; data: T }
    | { success: false; error: E };

// Usage
function getSession(id: string): Result<Session> {
    if (!exists(id)) {
        return { success: false, error: new BusinessError(...) };
    }
    return { success: true, data: session };
}
```

#### Naming Conventions
- **Functions/Variables**: `camelCase` (e.g., `getSession`, `isValidUser`)
- **Classes/Interfaces/Types**: `PascalCase` (e.g., `AppError`, `NetworkError`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `ErrorCode`, `MAX_RETRIES`)
- **Files**: `kebab-case.ts` (e.g., `cache-manager.ts`)
- **React components**: `PascalCase.tsx` (e.g., `ChatPanel.tsx`)

#### Error Handling
- Use custom error classes with error codes
- Use Result type instead of throwing when appropriate
- Always serialize errors for API responses

```typescript
export enum ErrorCode {
    NETWORK_TIMEOUT = 'E001',
    VALIDATION_FAILED = 'E100',
    SESSION_NOT_FOUND = 'E200',
}

export class BusinessError extends AppError {
    constructor(
        code: ErrorCode,
        message: string,
        public context?: unknown
    ) {
        super(code, message);
    }
}
```

#### Testing (Vitest)
- Use `describe`/`it` blocks
- Test file naming: `*.test.ts` or `*.spec.ts`
- Place tests in `__tests__/` or adjacent to source

```typescript
describe('Error Types', () => {
    describe('NetworkError', () => {
        it('should create NetworkError with correct properties', () => {
            const error = new NetworkError(ErrorCode.NETWORK_TIMEOUT, 503, '/api/test');
            expect(error.code).toBe(ErrorCode.NETWORK_TIMEOUT);
        });
    });
});
```

---

## Project Structure

```
jai/
├── backend/
│   ├── src/me4brain/      # Main source code
│   │   ├── api/           # FastAPI routes
│   │   ├── config/        # Settings and configuration
│   │   ├── core/          # Core utilities
│   │   ├── engine/        # Tool calling engine
│   │   ├── llm/           # LLM providers
│   │   ├── memory/        # Memory systems
│   │   └── utils/         # Shared utilities
│   ├── tests/
│   │   ├── unit/          # Unit tests
│   │   ├── integration/   # Integration tests
│   │   └── conftest.py    # Pytest fixtures
│   └── pyproject.toml     # Python configuration
├── frontend/
│   ├── frontend/          # Next.js UI app
│   ├── packages/
│   │   ├── gateway/       # Fastify API gateway
│   │   ├── shared/        # Shared types/utilities
│   │   └── me4brain-client/  # Backend API client
│   ├── package.json       # Root package.json
│   └── turbo.json         # Turborepo configuration
└── docker-compose.yml     # Docker services
```

---

## Key Configuration Files

| File | Purpose |
|------|---------|
| `backend/pyproject.toml` | Python deps, ruff, mypy, pytest config |
| `backend/.pre-commit-config.yaml` | Pre-commit hooks |
| `frontend/package.json` | npm workspaces config |
| `frontend/turbo.json` | Turborepo task pipeline |
| `frontend/tsconfig.base.json` | Shared TypeScript config |

---

## Important Notes

- **Python version**: 3.12+
- **Node version**: 20.0.0+
- **Line length**: 100 characters (Python)
- **Test coverage**: Aim for 80%+
- **Async**: Use `asyncio` patterns; avoid `nest_asyncio` (causes deadlocks)
- **Logging**: Use `structlog` (backend), `pino` (frontend gateway)
- **Validation**: Use Pydantic (Python), Zod (TypeScript)
