# Changelog - jAI (formerly PersAn) — Personal AI Assistant Frontend

Tutti i cambiamenti significativi a questo progetto saranno documentati in questo file.
## [Unreleased]

### Fixed - Providers Tab Input Visibility (2026-03-16)

**Issue**: Nella scheda "Providers" del Settings Panel, le caselle di input (text, number, select, checkbox) avevano testo bianco su sfondo bianco, rendendo il testo invisibile.

**Root Cause**: 
- Le classi Tailwind usate (`bg-bg-tertiary`, `text-text-primary`) non esistono nella configurazione Tailwind del progetto
- Tailwind ignora le classi non riconosciute, mantenendo lo sfondo bianco di default del browser

**Fix**: 
- Aggiunti inline styles con variabili CSS (`var(--bg-tertiary)`, `var(--text-primary)`) a tutti gli input, select e checkbox
- Aggiunta regola CSS globale per le `<option>` dei select
- Pattern coerente con `ParameterInput.tsx` esistente

**Files Modified**:
- `frontend/src/components/settings/ProvidersTab.tsx` - Inline styles per tutti gli elementi del form
- `frontend/src/app/globals.css` - Regola CSS globale per select option

**Note**: Il supporto per modelli multipli era già implementato. La funzionalità "+ Add Model" è ora visibile e utilizzabile.

---

### Fixed - ChatPanel Infinite Loop During Streaming (2026-03-16)

**Issue**: Errore "Maximum update depth exceeded" che causava crash dell'applicazione durante l'input utente mentre era in corso uno streaming SSE.

**Root Cause**: 
1. `handleInputChange` aveva `[setInput]` come dipendenza nel `useCallback` - inutile e potenzialmente problematico durante re-render rapidi
2. Il componente sottoscriveva l'intero oggetto `sessionStates` che viene ricreato ad ogni token durante lo streaming, causando re-render eccessivi

**Fix**: 
1. Rimossa dipendenza `[setInput]` dal `useCallback` di `handleInputChange` - `setInput` da `useState` è già stabile
2. Sostituita sottoscrizione a `sessionStates` con selettore diretto per la sessione corrente, evitando re-render quando altre sessioni vengono aggiornate

**Files Modified**:
- `frontend/src/components/chat/ChatPanel.tsx` - Ottimizzazione store subscription e fix handleInputChange

---

### Fixed - Dropdown Glassmorphism in Settings Panel (2026-03-15)

**Issue**: Nella scheda "LLM Models" del Settings Panel, i menu a tendina per selezionare i modelli LLM avevano sfondo trasparente senza glassmorfismo, rendendo illeggibile il testo che si sovrapponeva alla grafica sottostante.

**Root Cause**: 
- Dropdown usava `bg-bg-tertiary` (colore solido `#3a3a3c`) senza `backdrop-filter`
- Tailwind JIT non generava correttamente l'effetto glassmorfismo

**Fix**: 
- Sostituito `bg-bg-tertiary border border-border rounded-lg shadow-lg` con `glass-panel-floating`
- La classe `glass-panel-floating` include: `backdrop-filter: blur(24px) saturate(180%)`, background semi-trasparente, border e shadow

**Files Modified**:
- `frontend/src/components/settings/ModelSelector.tsx` - Dropdown principale (riga 107) e tooltip info (riga 63)
- `frontend/src/components/settings/ParameterInput.tsx` - Tooltip info (riga 80)

---

### Fixed - Settings Panel UX Improvements Complete (2026-03-15)

**Scope**: Completata implementazione piano UX Settings Panel con localizzazione italiana, feedback visivo toggle, e raccomandazioni hardware.

**Issues Resolved**:
1. **Didascalie Oscure (C1)**: Tutte le label ora in italiano con descrizioni chiare, tooltip ed esempi
2. **Selezione Modello Non Visibile (C2)**: ModelSelector mostra sempre il modello selezionato con badge Locale/Cloud
3. **Toggle Senza Feedback (C3)**: Toggle con colori verde (ON) / rosso (OFF) + indicatore testuale
4. **Parametri Senza Default (C4)**: ParameterInput con raccomandazioni hardware dinamiche via API

**Files Modified**:
- `frontend/src/components/settings/Toggle.tsx` (fix tipo prop `label`)
- `frontend/src/components/settings/index.ts` (aggiunti exports)

**Files Already Implemented**:
- `frontend/src/components/settings/settingsLabels.ts` (costanti IT)
- `frontend/src/components/settings/ModelSelector.tsx`
- `frontend/src/components/settings/ParameterInput.tsx`
- `frontend/src/components/settings/LLMModelsTab.tsx`
- `frontend/src/components/settings/AdvancedTab.tsx`
- `frontend/src/hooks/useSettings.ts` (useHardwareRecommendations)
- `packages/gateway/src/routes/config.ts` (proxy /recommendations/hardware)

**Backend** (Me4BrAIn):
- `src/me4brain/api/routes/llm_config.py` - Endpoint `/v1/config/llm/recommendations/hardware` già presente

---

### Fixed - Settings Panel & UI Bugs (2026-03-15)

**Issues Resolved**:

1. **Sidebar Settings Button** (`Sidebar.tsx:176-181`)
   - Button had no `onClick` handler — clicking did nothing
   - Added `useSettingsStore` import and `openSettings()` call
   - Settings panel now opens correctly from sidebar footer

2. **Gauge Component JSX Error** (`ResourcesTab.tsx:50-55`)
   - Invalid JSX: `<div>` nested inside `<svg>` element
   - Refactored: wrapped SVG and text overlay in relative container
   - Text overlay now positioned as absolute sibling to SVG (not child)

3. **Type Error in useSettings** (`useSettings.ts:174`)
   - Used undefined type `LLMModelInfo[]` instead of `AvailableModel[]`
   - Fixed type reference to use existing `AvailableModel` interface

4. **LLMModelsTab React Key Error** (`LLMModelsTab.tsx:101`)
   - Models array treated as strings but contained objects
   - Fixed: use `model.id` as key/value, `model.name` for display
   - Resolved "Objects are not valid as a React child" error

**Files Modified**:
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/components/settings/ResourcesTab.tsx`
- `frontend/src/hooks/useSettings.ts`

### Fixed - React Infinite Loop (2026-03-14)

**Issue**: "Maximum update depth exceeded" error on dashboard reload.

**Root Cause**: 
- `getCurrentSession()` and `getSession()` in `useChatStore` were creating new objects on every render via `createEmptySession()`, causing infinite re-renders
- Missing `useCallback` on `handleInputChange` causing unstable function references

**Fix Applied**:
1. Changed `getCurrentSession` and `getSession` to return the shared `emptySessionData` constant instead of creating new objects
2. Added `useCallback` to `handleInputChange` in ChatPanel.tsx for stable reference
3. Added `pendingThinking` to useEffect dependencies
4. Added default `[]` for `activitySteps` to prevent undefined access

**Files Modified**:
- `frontend/src/components/chat/ChatPanel.tsx`
- `frontend/src/stores/useChatStore.ts`

### Fixed - Code Quality & Security Improvements (2026-03-12)

**Scope**: Comprehensive bug fixes addressing memory leaks, security, data integrity, and error handling.

**Issues Resolved**:

1. **Memory Leaks - setTimeout/setInterval without cleanup**
   - `TalkModeOverlay.tsx`: Added `resumeTimerRef` with cleanup useEffect
   - `PromptLibrary.tsx`: Added `copyTimerRef` with cleanup useEffect
   - `MessageBubble.tsx`: Added `copyTimerRef` and `deleteConfirmTimerRef` with cleanup useEffect
   - `CodeBlock.tsx`: Added `copyTimerRef` with cleanup useEffect

2. **CORS Security Configuration**
   - `app.ts`: Added proper origin validation for:
     - Localhost (ports 3020, 3030)
     - Tailscale domains (`*.ts.net`)
     - Tailscale IP range (`100.x.x.x`)
     - Internal Docker networks (`172.x`, `10.x`)
     - Custom `FRONTEND_URL` environment variable

3. **Redis Atomic Operations**
   - `session_manager.ts`: Changed separate `SETEX` + `ZADD` calls to atomic `MULTI/EXEC` transaction for data integrity

4. **Streaming Consolidation**
   - Deleted duplicate `useChatSSE.ts` hook (functionality exists in `useChat.ts`)
   - Added cleanup useEffect in `useChat.ts` to abort all pending requests on component unmount

5. **React Error Boundaries**
   - Created `ErrorBoundary.tsx` with:
     - Generic `ErrorBoundary` class component with fallback UI
     - `ChatErrorBoundary` with chat-specific error UI
     - `MonitorsErrorBoundary` for monitor panels
     - `useErrorBoundary` hook for functional components
   - Updated `layout.tsx` to wrap root with ErrorBoundary
   - Updated `page.tsx` to wrap ChatPanel and IntelDeck with specific error boundaries

**Files Modified**:
- `frontend/src/components/voice/TalkModeOverlay.tsx`
- `frontend/src/components/chat/PromptLibrary.tsx`
- `frontend/src/components/chat/MessageBubble.tsx`
- `frontend/src/components/canvas/blocks/CodeBlock.tsx`
- `frontend/src/hooks/useChat.ts`
- `frontend/src/app/layout.tsx`
- `frontend/src/app/page.tsx`
- `packages/gateway/src/app.ts`
- `packages/gateway/src/services/session_manager.ts`

**Files Created**:
- `frontend/src/components/ErrorBoundary.tsx`

**Files Deleted**:
- `frontend/src/hooks/useChatSSE.ts`

### Fixed - Dashboard E2E Stabilization & Streaming Fix (2026-03-03)

- **Hydration Mismatch**: Risolto errore di sincronizzazione React tramite `suppressHydrationWarning`.
- **Infinite Session Loop**: Fix critico in `useChatStore.ts` con implementazione di `_fetchLock` per prevenire la creazione di sessioni fantasma all'infinito.
- **SSE Protocol Normalization**: Gateway `chat.ts` ora supporta nativamente i campi `message` e `content` per gli eventi di stato, garantendo che i messaggi "Thinking" siano sempre visibili.
- **Atomic Session UI**: Sidebar aggiornata per riflettere istantaneamente la creazione di nuove sessioni senza attendere il polling.

### Added - Phase 4 Complete: Proactive Monitoring System (2026-02-28)

**Scope**: Complete implementation of Proactive Monitoring System in Gateway TypeScript with BullMQ scheduler, parallel evaluator, WebSocket notifications, and frontend integration.

**Phases Completed**:
- **Phase 4.1**: Core Infrastructure (SchedulerService, MonitorManager)
- **Phase 4.2**: Evaluator Implementation (10 monitor types)
- **Phase 4.3**: Notification System (WebSocket integration)
- **Phase 4.4**: Monitor Routes & API (Gateway integration)
- **Phase 4.5**: Frontend Integration (MonitorsPanel update)
- **Phase 4.6**: Testing & Documentation

**Key Features**:
- BullMQ-based job scheduler with Redis persistence
- 10 monitor types with parallel evaluation engine
- Real-time WebSocket notifications
- Zod validation for type safety
- Frontend MonitorsPanel with real-time updates
- Comprehensive API documentation

**Architecture**:
- **Scheduler**: BullMQ + Redis for distributed job scheduling
- **Evaluator**: Parallel execution with Promise.allSettled, timeout handling
- **Notification**: WebSocket push for real-time alerts
- **Manager**: CRUD operations with Zod validation

**Services Created**:
1. `SchedulerService` - BullMQ integration with cron/interval scheduling
2. `EvaluatorService` - 10 monitor type evaluators with parallel execution
3. `MonitorManager` - CRUD + Redis persistence
4. `NotificationService` - WebSocket push notifications
5. `MonitorConfigService` - Zod validation for monitor configs

**Monitor Types Implemented**:
1. **PRICE_WATCH** - Stock/crypto price monitoring with thresholds
2. **SIGNAL_WATCH** - Technical indicators (RSI, MACD)
3. **AUTONOMOUS** - AI-powered autonomous trading decisions
4. **SCHEDULED** - Cron-based scheduled tasks
5. **EVENT_DRIVEN** - Event-triggered monitoring
6. **HEARTBEAT** - Periodic health checks
7. **TASK_REMINDER** - Task deadline reminders
8. **INBOX_WATCH** - Email inbox monitoring
9. **CALENDAR_WATCH** - Calendar event monitoring
10. **FILE_WATCH** - File system change monitoring

**API Endpoints**:
- `POST /api/monitors` - Create monitor
- `GET /api/monitors` - List monitors
- `GET /api/monitors/:id` - Get monitor details
- `DELETE /api/monitors/:id` - Delete monitor
- `POST /api/monitors/:id/pause` - Pause monitor
- `POST /api/monitors/:id/resume` - Resume monitor
- `POST /api/monitors/:id/trigger` - Force evaluation

**Frontend Updates**:
- Updated `MonitorsPanel.tsx` with new Gateway API endpoints
- Fixed API paths (removed trailing slashes)
- Fixed HTTP methods (POST for pause/resume)
- Added `x-user-id` header to all API calls
- Updated type enums (PRICE_WATCH vs price_watch)
- Updated state enums (ACTIVE vs active)
- Client-side stats calculation
- WebSocket integration for real-time notifications

**Documentation**:
- Updated `README.md` with Proactive Monitoring System section
- Created `docs/api/monitors.md` - Comprehensive API documentation
- Created walkthroughs for each phase (4.1-4.6)
- Updated CHANGELOG with Phase 4 summary

**Files Modified**:
- `packages/gateway/src/services/scheduler/` (5 new services)
- `packages/gateway/src/routes/monitors.ts` (refactored)
- `frontend/src/components/monitors/MonitorsPanel.tsx` (updated)
- `packages/shared/src/monitors.ts` (Zod schemas)
- `README.md` (documentation)
- `docs/api/monitors.md` (new)

**Build Status**: ✅ Success (Gateway + Frontend)

**Metrics**:
- Monitor types: 10
- Services: 5
- API endpoints: 7
- Files modified: 15+
- Lines of code: ~3000+
- Test coverage: Existing tests pass

**Next Steps**: Phase 5 - Canvas/A2UI Dashboard, Advanced Features (Natural Language Parser, Multi-channel Notifications)

**Breaking Changes**:
- Monitor routes no longer proxy to Python backend
- Monitor type enums changed from lowercase to uppercase
- Monitor state enums changed from lowercase to uppercase

---

### Added - Phase 4.5 Frontend Integration: MonitorsPanel Gateway API Update (2026-02-28)

**Scope**: Updated frontend MonitorsPanel component to integrate with new Gateway API endpoints

**Components Updated**:
- **MonitorsPanel.tsx** (`frontend/src/components/monitors/MonitorsPanel.tsx`)
  - Fixed API endpoint paths (removed trailing slashes)
  - Fixed HTTP methods (POST instead of PATCH for pause/resume)
  - Added `x-user-id` header to all API calls
  - Updated type enums (PRICE_WATCH vs price_watch)
  - Updated state enums (ACTIVE vs active)
  - Removed `/stats` endpoint call
  - Added client-side stats calculation
  - Updated response format handling

**API Endpoint Updates**:
- **GET `/api/monitors`** - Fixed path (removed trailing slash), added headers
- **POST `/api/monitors`** - Fixed path, added headers, updated response handling
- **POST `/api/monitors/:id/pause`** - Fixed HTTP method (POST instead of PATCH), added headers
- **POST `/api/monitors/:id/resume`** - Fixed HTTP method (POST instead of PATCH), added headers
- **DELETE `/api/monitors/:id`** - Added headers
- **POST `/api/monitors/:id/trigger`** - Added headers

**Type Enum Updates**:
- Monitor types: `price_watch` → `PRICE_WATCH`, `signal_watch` → `SIGNAL_WATCH`, etc.
- Monitor states: `active` → `ACTIVE`, `paused` → `PAUSED`, etc.
- Added new monitor types: `HEARTBEAT`, `TASK_REMINDER`, `INBOX_WATCH`, `CALENDAR_WATCH`, `FILE_WATCH`

**Client-Side Stats Calculation**:
```typescript
function calculateStats(monitors: Monitor[]): MonitorStatsResponse {
    return {
        total_monitors: monitors.length,
        active_monitors: monitors.filter(m => m.state === 'ACTIVE').length,
        total_checks: monitors.reduce((sum, m) => sum + m.checks_count, 0),
        total_triggers: monitors.reduce((sum, m) => sum + m.triggers_count, 0),
        by_type: monitors.reduce((acc, m) => {
            acc[m.type] = (acc[m.type] || 0) + 1;
            return acc;
        }, {} as Record<string, number>),
    };
}
```

**Response Format Handling**:
- Handles both old and new Gateway response formats
- Extracts `monitor` from `{ success: true, monitor: {...} }` format
- Extracts `monitors` from `{ success: true, monitors: [...] }` format

**WebSocket Integration**:
- Verified compatibility with Gateway WebSocket implementation
- No changes needed to `useMonitorNotifications` hook

**Build Status**: ✅ Success (Next.js compilation)

**Files Modified**:
- `frontend/src/components/monitors/MonitorsPanel.tsx` (7 API functions updated, 2 type enums updated)

**Metrics**:
- API endpoints fixed: 7
- Type enums updated: 2
- New monitor types added: 5
- Build status: ✅ Success

**Next Steps**: Manual testing with running system, E2E tests (optional)


### Added - Phase 4.4 Monitor Routes & API: Gateway Integration (2026-02-28)

**Scope**: Complete refactoring of Monitor Routes to eliminate Python backend dependencies and integrate directly with Gateway services

**Components Refactored**:
- **Monitor Routes** (`monitors.ts`)
  - Removed all backend proxy calls (`callBackend()` function)
  - Added Zod validation schemas for all endpoints
  - Integrated MonitorManager for CRUD operations
  - Integrated EvaluatorService for trigger endpoint
  - Standardized error handling and response formats
  - Added structured logging with Pino

**Endpoints Refactored**:
- **POST `/api/monitors`** - Create monitor
  - Zod validation with `MonitorTypeSchema`
  - Direct `monitorManager.createMonitor()` call
  - Returns 201 on success
  
- **GET `/api/monitors`** - List monitors
  - Direct `monitorManager.listMonitors()` call
  - Consistent response format
  
- **GET `/api/monitors/:id`** - Get monitor details
  - Zod param validation
  - Explicit 404 handling
  
- **DELETE `/api/monitors/:id`** - Delete monitor
  - Returns 204 No Content
  - Direct MonitorManager integration
  
- **POST `/api/monitors/:id/pause`** - Pause monitor
  - Zod validation
  - 404 handling for missing monitors
  
- **POST `/api/monitors/:id/resume`** - Resume monitor
  - Zod validation
  - Direct MonitorManager integration
  
- **POST `/api/monitors/:id/trigger`** - Force evaluation (NEW)
  - Manual trigger for testing/debugging
  - Direct EvaluatorService integration
  - Returns evaluation result

**Zod Validation Schemas**:
- `CreateMonitorBodySchema` - Validates monitor creation requests
- `MonitorIdParamsSchema` - Validates route parameters
- `ParseQueryBodySchema` - Validates NL query parsing

**Type Safety Improvements**:
- Used `MonitorTypeSchema` from `@persan/shared`
- Proper enum types for `notify_channels`
- Runtime type validation with Zod
- Consistent with shared types

**Error Handling**:
- Standardized error responses (400, 404, 500)
- Zod validation error details
- Structured logging for debugging
- Proper HTTP status codes

**Natural Language Parser**:
- Kept `/api/monitors/parse` endpoint for Phase 4.5
- TODO: Replace with Me4BrAIn integration

**Technical Highlights**:
- No backend dependency (except `/parse` endpoint)
- Type-safe request validation
- Direct Gateway service integration
- Faster response times (no HTTP proxy overhead)

**Files Modified**:
- `packages/gateway/src/routes/monitors.ts` (292→380 lines, complete rewrite)

**Build Status**: ✅ Success (TypeScript compilation)

**Metrics**:
- Backend calls removed: 7 endpoints
- Zod schemas added: 3
- New endpoints: 1 (`/trigger`)
- Lines of code: +88 lines

**Next Steps**: Phase 4.5 - Frontend Integration & NL Parsing


### Added - Phase 4.3 Notification Service: Real-time Monitor Alerts (2026-02-28)

**Scope**: Implemented NotificationService to deliver real-time monitor alerts via WebSocket with Redis history

**Components Implemented**:
- **NotificationService** (`notification.service.ts`)
  - WebSocket integration via existing ConnectionRegistry
  - Redis history storage (last 50 notifications per user)
  - Replay mechanism for missed notifications on reconnect
  - Severity calculation (info/warning/critical) based on confidence
  - Graceful degradation for offline users and Redis failures

- **Singleton Instance** (`notification-service.instance.ts`)
  - Auto-initialization with Redis from ConfigService
  - Lazy loading support
  - Consistent with MonitorManager pattern

- **EvaluatorService Integration**
  - Implemented `sendNotification()` method (was stub)
  - Format MonitorAlert from evaluation result
  - Call NotificationService on monitor trigger
  - Non-blocking error handling

- **WebSocket Handler Updates** (`handler.ts`)
  - Added notification replay on connection
  - Parallel execution with session buffer replay
  - Structured logging for debugging

- **Shared Types Update** (`@persan/shared`)
  - Updated `MonitorAlertData` interface
  - Added severity field, removed obsolete fields
  - Rebuilt shared package

**Testing Achievements**:
- **Test Pass Rate**: 100% (12/12 tests)
- **Test Coverage**: All public methods covered
- **Test Categories**: sendMonitorAlert (3), getNotificationHistory (3), replayNotifications (3), getSeverity (3)
- **Build Status**: ✅ Success

**Technical Highlights**:
- Leveraged existing `ConnectionRegistry.sendMonitorAlert()` method
- Redis LPUSH + LTRIM pattern for efficient history management
- Auto-initialization pattern reduces boilerplate
- Graceful error handling prevents notification failures from breaking evaluation

**Files Created**:
- `packages/gateway/src/services/scheduler/notification.service.ts` (145 lines)
- `packages/gateway/src/services/scheduler/notification-service.instance.ts` (29 lines)
- `packages/gateway/src/services/scheduler/__tests__/notification.service.test.ts` (312 lines)

**Files Modified**:
- `packages/gateway/src/services/scheduler/evaluator.service.ts` (sendNotification implementation)
- `packages/gateway/src/websocket/handler.ts` (notification replay)
- `packages/shared/src/websocket.ts` (MonitorAlertData type)

**Redis Schema**:
- Key: `notifications:user:{userId}`
- Type: List (newest first)
- Max Size: 50 notifications per user

**Integration Flow**:
1. SchedulerService triggers monitor evaluation
2. EvaluatorService evaluates and detects trigger
3. NotificationService sends alert via WebSocket
4. Redis stores notification for history
5. On reconnect, replay missed notifications

**Next Steps**: Phase 4.4 - Monitor Routes & API


### Added - Phase 4.2 Refactoring: Dependency Injection & 100% Test Coverage (2026-02-28)

**Scope**: Refactored EvaluatorService with Dependency Injection pattern to achieve 100% test pass rate

**Refactoring Implemented**:
- **Interface Abstraction**
  - Created `IMe4BrAInClient` interface for loose coupling
  - Defined complete type contract matching Me4BrAIn client API
  - Includes `ToolCallInfo` type definition

- **Constructor Injection**
  - Added optional `me4brainClient` parameter to EvaluatorService constructor
  - Default production client instantiation for backward compatibility
  - Private readonly field for dependency encapsulation

- **Code Updates**
  - Updated 8 occurrences of global `me4brainClient` to `this.me4brainClient`
  - Maintained existing factory function for singleton export
  - Zero breaking changes to existing code

**Testing Achievements**:
- **Test Pass Rate**: 53% → 100% (+47% improvement)
- **Tests Passing**: 9/17 → 17/17 (+8 tests)
- **Test Implementation**: Complete rewrite with mock client injection
- **Coverage**: All 10 monitor types, error scenarios, edge cases

**Technical Benefits**:
- ✅ SOLID Principles: Dependency Inversion Principle applied
- ✅ 100% Testable: All dependencies mockable
- ✅ Loose Coupling: Interface-based design
- ✅ Backward Compatible: No breaking changes
- ✅ Type Safe: Full TypeScript contracts

**Files Modified**:
- `packages/gateway/src/services/scheduler/interfaces/me4brain-client.interface.ts` (new)
- `packages/gateway/src/services/scheduler/evaluator.service.ts` (refactored)
- `packages/gateway/src/services/scheduler/__tests__/evaluator.service.test.ts` (rewritten)

### Added - Phase 4.2: Proactive Monitoring System - Evaluator Implementation (2026-02-28)

**Scope**: Complete implementation of 10 monitor type evaluators with Me4BrAIn integration

**Components Implemented**:
- **Finance Monitors**
  - `PRICE_WATCH`: Stock price threshold monitoring with Me4BrAIn data fetching
  - `SIGNAL_WATCH`: Technical indicator (RSI, MACD) threshold monitoring
  - `AUTONOMOUS`: Parallel data collection (Promise.allSettled) + LLM-based decision making

- **Generic Monitors**
  - `HEARTBEAT`: Periodic proactive reasoning with calendar/memory context + LLM evaluation
  - `TASK_REMINDER`: Due date calculation with reminder threshold and overdue detection
  - `INBOX_WATCH`: Email monitoring with keyword/sender filtering via Me4BrAIn
  - `CALENDAR_WATCH`: Upcoming event detection with configurable look-ahead window

- **System Monitors**
  - `SCHEDULED`: Cron-based task execution (always triggers)
  - `EVENT_DRIVEN`: External webhook trigger confirmation
  - `FILE_WATCH`: Filesystem monitoring stub (future implementation)

- **Me4BrAIn Integration Helpers**
  - `fetchStockData()`: Finance domain queries (price, change, volume)
  - `fetchTechnicalIndicator()`: Technical analysis data
  - `fetchNewsData()`: Market news headlines
  - `llmEvaluate()`: LLM-based trading recommendations
  - `fetchCalendarContext()`: Google Calendar integration
  - `fetchMemoryContext()`: Working memory retrieval
  - `fetchInboxContext()`: Gmail API integration with filtering

**Technical Highlights**:
- SOTA 2026 patterns: Promise.allSettled for parallel data fetching
- Structured logging with Pino
- Type-safe Me4BrAIn client integration
- Timeout handling (10-20s per API call)
- Graceful error handling with fallback responses
- TypeScript compilation verified

**Files Modified**:
- `packages/gateway/src/services/scheduler/evaluator.service.ts` (complete implementation)

### Added - Phase 4.1: Proactive Monitoring System - Core Infrastructure (2026-02-28)

**Scope**: BullMQ Scheduler Service, Monitor Manager Service, Evaluator Service Stub

**Components Implemented**:
- **SchedulerService** (`packages/gateway/src/services/scheduler/scheduler.service.ts`)
  - BullMQ Queue setup with Redis connection
  - Worker with concurrency control (10 concurrent jobs)
  - Event listeners (completed, failed, stalled)
  - Cron and interval-based scheduling
  - Pause/resume/delete monitor operations
  - Graceful shutdown handling
  - Job retry with exponential backoff (3 attempts, 2s initial delay)

- **MonitorManager** (`packages/gateway/src/services/scheduler/monitor-manager.service.ts`)
  - Redis persistence (hset monitors, sadd user index)
  - CRUD operations (create, get, list, update, delete)
  - Zod validation on create/update
  - Integration with SchedulerService
  - Evaluation result tracking (last 50 results per monitor)
  - Statistics aggregation (total, active, paused, triggered, by type)

- **EvaluatorService Stub** (`packages/gateway/src/services/scheduler/evaluator.service.ts`)
  - Main `evaluate()` dispatcher
  - Type-specific evaluator stubs for 10 monitor types:
    - PRICE_WATCH, SIGNAL_WATCH, AUTONOMOUS (Finance)
    - HEARTBEAT, TASK_REMINDER, INBOX_WATCH, CALENDAR_WATCH (Generic)
    - SCHEDULED, EVENT_DRIVEN, FILE_WATCH (System)
  - Error handling and structured logging
  - Timeout helper for Promise.race
  - Full implementation deferred to Phase 4.2

**Dependencies Added**:
- `bullmq@^5.29.5` - Redis-based job queue
- `ioredis@^5.4.2` - Redis client (already present, version confirmed)
- `uuid@^11.0.5` - Monitor ID generation

**Technical Notes**:
- Fixed TypeScript compilation by using named `Redis` export from `ioredis` instead of default export
- All services use singleton pattern for global access
- Structured logging with Pino for observability
- Type-safe with Zod validation from `@persan/shared`

**Next Steps**: Phase 4.2 - Evaluator Implementation (10 monitor types with Me4BrAIn integration)

---

## [2026-02-28] - PersAn Refounding: Phase 0 & Phase 1

### Added
- **Type Safety Foundation** (`packages/shared/src/`):
  - `engine.ts`: Unified types for Me4BrAIn Engine interaction with discriminated unions for SSE stream events
  - `monitors.ts`: Zod schemas for proactive monitoring system (replaces Python Pydantic models)
  - Expanded `chat.ts` with complete `ChatTurn`, `ChatSession`, and `SessionSummary` types
  
- **Upload Routes** (`packages/gateway/src/routes/upload.ts`) [NEW]:
  - File upload endpoint with OCR processing (PDF, images)
  - Multipart file handling with `@fastify/multipart`
  - Temporary proxy to Python backend until Me4BrAIn SDK has ingestion API
  - Validation, temp file management, automatic cleanup

### Changed
- **Frontend Configuration** (`frontend/src/lib/config.ts`):
  - Eliminated dual-URL architecture (Backend Python + Gateway TypeScript)
  - Single Gateway endpoint configuration via `NEXT_PUBLIC_GATEWAY_URL`
  - All components now use `API_CONFIG` instead of hardcoded URLs
  
- **Removed Hardcoded URLs** from 6 frontend files:
  - `utils.ts`, `ChatInput.tsx`, `ChatPanel.tsx`, `FileUpload.tsx`, `MonitorsPanel.tsx`, `useSessionGraph.ts`

### Architecture
- Frontend now communicates exclusively with Gateway (port 3030)
- Backend Python (port 8888) becomes internal service, no longer exposed to frontend
- Preparation for complete Python backend elimination in future phases

---

## [2026-02-28] - Phase 2: Session Management Unificata (Cache-Aside Pattern)

### Added
- **SessionManager** (`packages/gateway/src/services/session_manager.ts`) [NEW]:
  - Cache-Aside pattern with L1 (in-memory, 1000 sessions, LRU) + L2 (Redis, TTL 30min)
  - Distributed locks (Redis SETNX) for stampede protection
  - Redis pub/sub for multi-instance cache invalidation
  - Probabilistic refresh (10% when TTL < 20%)
  - Graceful degradation (cache-only mode when Me4BrAIn API unavailable)
  - Metrics tracking: hit rate, L1/L2 hits, misses, API errors

- **SessionManager Instance** (`packages/gateway/src/services/session_manager_instance.ts`) [NEW]:
  - Singleton instance with Me4BrAIn Working Memory API integration
  - Exports: `sessionManager`, `ChatSession`, `ChatTurn`, `SessionConfig`, `CacheMetrics`

- **Cache Types** (`packages/shared/src/chat.ts`):
  - `CachedSession`: Session data with TTL metadata
  - `CacheMetrics`: Performance metrics (hit rate, L1/L2 hits, misses, errors)

### Changed
- **Gateway Routes Integration**:
  - `packages/gateway/src/routes/chat.ts`: 18 usages migrated from `chatSessionStore` to `sessionManager`
  - `packages/gateway/src/services/query_executor.ts`: 2 usages migrated
  - `packages/gateway/src/websocket/router.ts`: 1 usage migrated

- **SessionManager API**: Extended with 7 additional methods for full compatibility:
  - `updateTitle()`, `updateSessionConfig()`
  - `deleteTurn()`, `updateTurn()`, `updateTurnFeedback()`
  - `truncateAfter()`, `getTurnContent()`

### Performance
- **Cache Hit Rate**: 98.1% (target >85%, exceeded)
- **L1 Latency**: 0ms (100 operations in 0ms)
- **Write-Through Invalidation**: Verified working
- **Gateway Build**: 0 TypeScript errors

### Testing
- Mock-based standalone test: All tests passed
- Cache-Aside pattern: Verified
- Multi-instance invalidation: Ready (requires Redis)


---

## [2026-02-28] - Phase 3: API Contract & Config Centralization

### Added

- **Shared Types - Error Hierarchy** (`packages/shared/src/errors.ts`) [NEW]:
  - `AppError` base class (abstract) with operational flag and timestamp
  - `NetworkError` for HTTP/connection failures (status, url)
  - `ValidationError` for input validation (field, details)
  - `BusinessError` for domain logic errors (context)
  - `ExternalServiceError` for third-party failures (service, originalError)
  - `ErrorCode` enum organized by category (Network, Validation, Business, External)
  - `Result<T>` type for functional error handling
  - Helper functions: `serializeError()`, `getStatusCodeForError()`

- **Shared Types - Config Schemas** (`packages/shared/src/config.ts`) [NEW]:
  - `EnvSchema` with Zod validation for backend/gateway environment variables
  - `FrontendConfigSchema` for client-side configuration
  - Validation helpers: `validateEnv()`, `validateFrontendConfig()`
  - Type coercion for numeric values, defaults for all fields

- **ConfigService** (`packages/gateway/src/config/config.service.ts`) [NEW]:
  - Singleton pattern for centralized configuration management
  - Zod validation at startup with fail-fast behavior
  - Structured logging with Pino (credential sanitization)
  - Hot-reload support (placeholder for future enhancement)
  - Methods: `get<T>(key)`, `getAll()`, `reload()`

- **Global Error Handler** (`packages/gateway/src/middleware/error-handler.ts`) [NEW]:
  - `errorHandler()` function for Fastify with AppError hierarchy support
  - Correlation IDs for distributed tracing (`x-correlation-id` header)
  - Structured logging with Pino (operational vs programmer errors)
  - Standardized JSON responses with error code and correlation ID
  - `correlationIdMiddleware()` for request tracking

### Changed

- **Gateway Integration**:
  - `packages/gateway/src/index.ts`: ConfigService integration at startup
  - `packages/gateway/src/app.ts`: Global error handler and correlation ID middleware registered
  - Replaced direct `process.env` access with `config.get()`

- **Frontend Configuration** (`frontend/src/lib/config.ts`):
  - Added Zod validation using `validateFrontendConfig()`
  - Replaced `ApiConfig` interface with `FrontendConfig` from `@persan/shared`
  - Breaking change: `restUrl` → `gatewayUrl` (10 files updated)

- **Frontend URL Cleanup** (5 files):
  - `hooks/useVoice.ts`: Replaced hardcoded localhost URL with `API_CONFIG.gatewayUrl`
  - `hooks/useMonitorNotifications.ts`: Replaced hardcoded WS URL with `API_CONFIG.websocketUrl`
  - `lib/gateway-client.ts`: Simplified URL resolution using `API_CONFIG.websocketUrl`
  - All files now use centralized `API_CONFIG` instead of hardcoded URLs

- **Shared Package**:
  - `packages/shared/src/index.ts`: Added exports for `errors` and `config` modules
  - `packages/shared/package.json`: Added test scripts and vitest dependency

### Testing

- **Shared Types Test Suite** (`packages/shared/src/__tests__/`):
  - `errors.test.ts`: 16 tests covering all error classes, serialization, status code mapping
  - `config.test.ts`: 15 tests covering env validation, frontend config, defaults, coercion
  - **Total: 31 tests passed** ✅

### Performance

- **Build Status**: All packages build successfully
  - `@persan/shared`: TypeScript compilation successful
  - `@persan/gateway`: TypeScript compilation successful
  - `persan-frontend`: Next.js build successful (4 static pages)

### Architecture

- Centralized configuration with runtime validation (Zod)
- Standardized error handling with correlation IDs for distributed tracing
- Type-safe configuration across frontend and backend
- Zero hardcoded URLs in frontend (except external services)
- Structured logging with Pino in Gateway

---

## [2026-02-17] - Mobile UI Premium & WebSocket Flow Unification

### Added
- **DeleteSessionModal** (`frontend/src/components/chat/DeleteSessionModal.tsx`) [NEW]:
  - Sostituita conferma nativa browser con modale elegante e coordinata al design system
  - Ottimizzata per l'uso touch su mobile
  
- **Activity Sync via WebSocket**:
  - Supporto completo per la timeline delle attività (thinking, plan, steps, synthesizing) tramite il protocollo WebSocket
  - `QueryExecutor` ora bufferizza tutti i metadati di esecuzione su Redis per il replay post-riconnessione

### Changed
- **Messaging Protocol**: Migrazione dell'invio messaggi primario da SSE a WebSocket (`useGateway.ts`)
- **Mobile UX**: 
  - Header ora `sticky` con top:0 e `z-index: 50`
  - Utilizzo di `100dvh` (Dynamic Viewport Height) in `DashboardLayout.tsx` per prevenire shift del layout causati dalla barra indirizzi mobile
- **Performance**: Memoizzazione di `MessageBubble.tsx` per eliminare il lag di digitazione nel `ChatPanel`

### Fixed
- **Background Continuity**: Risolto problema di perdita dati durante lo streaming se il browser veniva chiuso; i messaggi ora vengono correttamente replayati dal buffer Redis al rientro.

---


### Added
- **QueryExecutor Service** (`packages/gateway/src/services/query_executor.ts`) [NEW]:
  - Gestione asincrona delle query Me4BrAIn in background
  - Persistenza stream chunk in Redis (`persan:buffer:sessionId`) con TTL 1 ora
  - Supporto per "fire-and-forget" lato client: l'esecuzione continua anche a WebSocket chiuso
  
- **Push Notification Service** (`packages/gateway/src/services/push_notifications.ts`) [NEW]:
  - Integrazione Web Push API con chiavi VAPID
  - Endpoint `POST /api/push/subscribe` per registrazione client
  - Invio automatico notifica "Risposta jAI pronta!" al termine del processing background

- **Frontend Resilience**:
  - `GatewayClient`: Persistenza `sessionId` in `localStorage`
  - Auto-reconnect con replay del buffer messaggi (lo stato si ripristina al refresh)
  - Service Worker (`sw.js`) per gestione notifiche push e focus window

### Changed
- **WebSocket Protocol**: Aggiunto supporto per `?sessionId=...` in query string durante handshake
- **Architecture**: Disaccoppiamento ciclo vita WebSocket ↔ ciclo vita Query Me4BrAIn

---

## [2026-02-12] - Fix Deployment Docker: Gateway ↔ Me4Brain Network

### Fixed
- **`docker-compose.gateway.yml`**: Gateway e Me4Brain API erano su reti Docker separate (`docker_persan-network` vs `me4brain_me4brain-network`) — il gateway non poteva raggiungere me4brain-api
- **Soluzione**: Aggiunta rete esterna `me4brain_me4brain-network` al gateway + `ME4BRAIN_URL=http://me4brain-api:8000/v1` (DNS container Docker)
- **`.env`**: Aggiornato `ME4BRAIN_URL` per coerenza con l'architettura containerizzata

### Architecture
```
Gateway (persan-network + me4brain-network)
  → http://me4brain-api:8000/v1 (DNS Docker interno)
  → Risolve "fetch failed" dall'interfaccia jAI su Tailscale
```

---

## [2026-02-12] - UX: Toolbar Messaggi Top + Bottom

### Changed
- **MessageBubble.tsx**: Toolbar azioni (Copy, Edit, Retry, Upvote/Downvote, Delete) ora visibile sia in alto che in basso alla bubble del messaggio
- **Refactor**: Estratto JSX toolbar in `renderToolbar('top' | 'bottom')` — zero duplicazione di codice
- Posizionamento: `absolute -top-8` (top) e `absolute -bottom-8` (bottom), entrambe con hover opacity transition

### UX Improvement
Per messaggi lunghi dell'assistente, l'utente può ora interagire con la toolbar senza scrollare fino alla cima del messaggio.

---

## [2026-02-11] - UI Rebranding: PersAn → jAI 🌈

### Changed
- **Brand Name**: L'interfaccia utente ora si presenta come **jAI** ("j" + "AI") 
- **Logo**: Nuovo logo circolare con lampada da scrivania + rete neurale, sfondo nero e gradiente arcobaleno stile Apple
- **Header** (`Header.tsx`): Logo jAI + testo "jAI" con gradiente rainbow
- **TopBar** (`DashboardLayout.tsx`): Logo jAI + "jAI" con gradiente rainbow (sostituisce emoji 🤖 + "PERSAN")
- **Welcome Screen** (`ChatPanel.tsx`): Logo jAI (80×80) + titolo "jAI" (sostituisce emoji 🤖 + "PersAn")
- **Chat Input** (`ChatInput.tsx`): Placeholder "Chiedi a jAI..." (era "Chiedi a PersAn...")
- **SEO Metadata** (`layout.tsx`): Title "jAI", description aggiornata
- **PWA Manifest** (`manifest.json`): `name: "jAI — Your AI Assistant"`, `short_name: "jAI"`
- **PWA Icons**: Rigenerate (192×192, 512×512) dal nuovo logo arcobaleno

### Note
Il nome interno del progetto e i package (`@persan/shared`, `persan-frontend`, etc.) restano invariati. Il rebranding riguarda esclusivamente l'esperienza utente.

---

## [2026-02-11] - Graph-Based Session Management & Cluster Navigation

### Added
- **Shared Types** (`packages/shared/src/chat.ts`):
  - `SessionCluster`: id, name, description, sessionIds, centroidEmbedding, topTopics
  - `SessionGraphMeta`: topics, clusterName, relatedSessionIds, pageRank
  - `TopicInfo`: id, name, sessionCount

- **Gateway Graph Service** (`packages/gateway/src/services/graph_session_service.ts`) [NEW]:
  - Integrazione con Me4Brain Session Graph API
  - `getClusters()`, `getRelatedSessions()`, `searchSessions()`, `getConnectedNodes()`

- **Gateway Graph Routes** (`packages/gateway/src/routes/graph.ts`) [NEW]:
  - `GET /api/graph/clusters` — Cluster tematici delle sessioni
  - `GET /api/graph/related/:sessionId` — Sessioni correlate via graph traversal
  - `POST /api/graph/search` — Ricerca semantica sessioni
  - `GET /api/graph/connected-nodes/:sessionId` — Nodi connessi nel knowledge graph

- **Frontend Hooks** (`frontend/src/hooks/useSessionGraph.ts`) [NEW]:
  - `useSessionClusters()` — Fetch e cache cluster tematici
  - `useRelatedSessions(sessionId)` — Sessioni correlate con score
  - `useSessionSearch()` — Ricerca semantica full-text
  - `useConnectedNodes(sessionId)` — Nodi hub dal knowledge graph
  - `usePromptLibrary()` — CRUD prompt template con suggerimenti contestuali

- **5 Nuovi Componenti UI**:
  - `GraphExplorer.tsx` [NEW] — Dropdown esplorazione nodi connessi con score bar
  - `PromptLibrary.tsx` [NEW] — Libreria prompt navigabile con search, CRUD, suggerimenti
  - `RelatedSessions.tsx` [NEW] — Lista sessioni correlate con chip e percentuali
  - `SessionClusterSidebar.tsx` [NEW] — Vista cluster tematici nella sidebar
  - Bottone 📚 (BookOpen) nell'area input del ChatPanel — apre PromptLibrary come picker

- **CSS** (`frontend/src/styles/sessions.css`):
  - Stili per `graph-explorer`, `sidebar-view-toggle`, `chat-graph-bar`
  - Chip `chat-related-sessions`, score fill bars
  - Override PromptLibrary inline per IntelDeck

### Changed
- **`Sidebar.tsx`**: Toggle segmented control `📋 Lista / 🧩 Cluster` per switch tra lista cronologica e cluster tematici
- **`ChatPanel.tsx`**: Integrati `GraphExplorer` + `RelatedSessions` sotto i messaggi; bottone 📚 nell'input per PromptLibrary
- **`IntelDeck.tsx`**: Nuovo tab `📚 Prompt` con PromptLibrary inline

### Removed
- **`CreateSessionDialog`**: Rimosso dialog di selezione tipologia sessione — click su `+` crea sessione direttamente
- **Filter Pills tipologia**: Rimossi filtri per tipo sessione (free/topic/template) dalla sidebar
- **Import `SessionType`**: Non più necessario nella Sidebar

---

## [2026-02-11] - Categorized Sessions (Free / Topic / Template)

### Added
- **Shared Types** (`packages/shared/src/chat.ts`):
  - `SessionType`: `'free' | 'topic' | 'template'`
  - `TemplatePrompt`: id, label, content, enabled, variables, timestamps
  - `SessionConfig`: type, topic, tags, prompts, schedule

- **Gateway Session Store** (`packages/gateway/src/services/chat_session_store.ts`):
  - `config?: SessionConfig` su `ChatSession` e `SessionMeta`
  - `createSession()` accetta config opzionale
  - `updateSessionConfig()` — merge parziale con persistenza Redis

- **Gateway Routes** (`packages/gateway/src/routes/chat.ts`):
  - `POST /api/chat/sessions` accetta `{title, config}` nel body
  - `GET /api/chat/sessions/:id` ritorna config
  - `PUT /api/chat/sessions/:id/config` — aggiorna config sessione

- **Frontend Store** (`frontend/src/stores/useChatStore.ts`):
  - `SessionSummary.config` per tipo sessione nella lista
  - `createNewSession(config?)` — invia config al backend
  - `updateSessionConfig(sessionId, config)` — PUT con update ottimistico

- **3 Nuovi Componenti UI**:
  - `CreateSessionDialog` — Dialog modale con selezione tipo (💬/🎯/⚡), form topic/tags, form template prompts
  - `TemplatePromptBar` — Barra chip scrollabile, click inserisce, ⌘+click invia direttamente
  - `PromptEditorModal` — CRUD completo: toggle, edit inline, drag&drop reorder, delete

- **CSS Liquid Glass** (`frontend/src/styles/sessions.css`):
  - Stili glassmorphism per dialog, chip, toggle switch, drag handles

### Changed
- **`Sidebar.tsx`**: Pulsante + apre `CreateSessionDialog` (non crea direttamente), icone tipo sessione (💬 free, 🎯 topic, ⚡ template)
- **`ChatPanel.tsx`**: Integrato `TemplatePromptBar` e `PromptEditorModal` per sessioni template

---

## [2026-02-10] - User Feedback System (▲/▼ Reddit-Style)

### Added
- **Feedback Endpoint** (`packages/gateway/src/routes/chat.ts`):
  - `PUT /api/chat/sessions/:id/turns/:idx/feedback` — Upvote/downvote con validazione score
  
- **ChatTurn.feedback** (`packages/gateway/src/services/chat_session_store.ts`):
  - Campo opzionale `{ score: 1|-1, comment?, timestamp }` su ogni turn
  - `updateTurnFeedback()` — LINDEX+LSET su Redis con fallback in-memory

- **Frontend ▲/▼** (`frontend/src/components/chat/MessageBubble.tsx`):
  - Bottoni ChevronUp/ChevronDown su messaggi assistant (inline nel toolbar hover)
  - Toggle: click su freccia attiva → toglie il voto (score=0)
  - Colori: arancione (upvote), blu (downvote)
  
- **Store Action** (`frontend/src/stores/useChatStore.ts`):
  - `submitFeedback()` — PUT API + aggiornamento stato locale
  - `Message.feedback` type in `types/chat.ts`

### Changed
- **`ChatPanel.tsx`**: Passata prop `onFeedback` a `MessageBubble`

---

## [2026-02-10] - Chat Persistence (Redis) + Message Management

### Added
- **Chat Session Store** (`packages/gateway/src/services/chat_session_store.ts`) [NEW]:
  - Persistenza sessioni chat su Redis con fallback in-memory
  - CRUD completo: create, get, list, delete, updateTitle
  - Turn management: addTurn, deleteTurn, editTurn, retryTurn
  - TTL 7 giorni per sessioni, auto-titolazione dal primo messaggio
  - Log startup: `✅ ChatSessionStore: Redis connected`

- **3 nuovi endpoint turn management** (`packages/gateway/src/routes/chat.ts`):
  - `DELETE /api/chat/sessions/:id/turns/:index` — Cancella singolo turn (+ risposta associata)
  - `PUT /api/chat/sessions/:id/turns/:index` — Modifica turn + ri-esecuzione con SSE streaming
  - `POST /api/chat/sessions/:id/retry/:index` — Riprova turn con SSE streaming

- **Message Toolbar** (`frontend/src/components/chat/MessageBubble.tsx`):
  - Toolbar hover su ogni messaggio: Copy, Edit (solo user), Retry (solo user), Delete
  - Edit inline con textarea + "Salva e Riprova" / "Annulla"
  - Delete con doppio click di conferma (auto-dismiss 3s)

- **Store Actions** (`frontend/src/stores/useChatStore.ts`):
  - `deleteMessage(sessionId, index)` — DELETE API + stato locale
  - `truncateFromIndex(sessionId, index)` — Tronca messaggi per retry/edit

- **SSE Shared Reader** (`frontend/src/hooks/useChat.ts`):
  - `readSSEStream()` — Funzione condivisa per tutti gli stream SSE
  - `retryMessage(index)` — Tronca + re-streaming
  - `editMessage(index, newContent)` — Modifica + re-streaming

### Changed
- **`chat.ts`**: Eliminata `Map<string, ChatSession>` in-memory, ora tutto via `ChatSessionStore`
- **`streamQueryToResponse()`**: Estratta come utility condivisa per chat/retry/edit

### Fixed
- **Sessioni chat non persistenti**: Le sessioni ora sopravvivono al riavvio del gateway grazie a Redis

## [2026-02-10] - Activity-Based Timeout + Session Isolation Bug Fixes

### Added
- **Activity-Based Timeout** (`packages/me4brain-client/src/engine.ts`):
  - Sostituito `AbortSignal.timeout` (statico 910s) con timer resettabile
  - Il timer si resetta ad ogni chunk SSE ricevuto dal backend
  - Timeout di silenzio: **360 secondi** (6 min) — scatta solo se nessun dato arriva
  - Query di durata illimitata fintanto che il backend continua a inviare progresso
  - Nuovo campo `chunkSilenceTimeoutMs` in `StreamOptions` per configurazione custom

### Changed
- **`engine.ts`**: `keepAliveTimeout` da `620_000` (10 min) a `1_800_000` (30 min)
- **`client.ts`**: `keepAliveTimeout` da `620_000` a `1_800_000` (allineato)
- **`types.ts`**: Aggiunto `chunkSilenceTimeoutMs?: number` a `StreamOptions`
- **Default timeout**: `timeoutSeconds` da `900` a `1800` (30 min)

### Fixed
- **`useChat.ts`**: Aggiunta `finishStreaming()` nel case `error` SSE — prima la sessione restava bloccata in streaming infinito dopo un errore
- **`ChatPanel.tsx`**: Fix hydration mismatch con guard `hasMounted`

### Root Cause (Query ANCI)
La query "Alta Irpinia" falliva dopo 610s. Causa: `keepAliveTimeout: 620_000` in undici Agent chiudeva la connessione SSE durante le pause tra chunk causate da chiamate LLM lunghe.

---

## [2026-02-10] - Chat Session Isolation Refactoring

### Fixed
- **Session Isolation**: Risolto bug critico dove le sessioni chat non erano isolate — lo streaming si mescolava tra sessioni e la UI si congelava al cambio sessione.

### Changed
- **`useChatStore.ts`**: Stato da globale a per-sessione con `Record<sessionId, SessionData>`. Ogni sessione ha il proprio `messages`, `pendingMessage`, `isStreaming`, `activitySteps`, `error`.
- **`useChat.ts`**: Closure su `targetSessionId` al momento dell'invio — i token SSE vanno sempre alla sessione corretta anche se l'utente cambia chat.
- **`useGateway.ts`**: `streamingSessionRef` per tracciare quale sessione ha iniziato lo streaming WebSocket.
- **`ChatPanel.tsx`**, **`ActivityTimeline.tsx`**, **`ChatInput.tsx`**: Lettura stato dalla sessione corrente via `getCurrentSession()`.
- **Gateway `router.ts`**: `sessionId` incluso in tutti i messaggi WebSocket (`chat:thinking`, `chat:status`, `chat:tool`, `chat:response`).

### Architecture
Pattern chiave: la closure cattura il `sessionId` all'invio del messaggio e lo usa per TUTTE le operazioni di streaming, garantendo isolamento anche durante navigazione tra sessioni.

---

## [2026-02-09] - Engine Memory Integration

### Changed
- **Me4BrAIn Client** (`packages/me4brain-client/src/engine.ts`):
  - `query()` e `queryStream()` ora passano `session_id` al backend Me4BrAIn
  - Attiva l'integrazione memoria completa (Working + Episodic Memory) lato backend

- **Types** (`packages/me4brain-client/src/types.ts`):
  - `sessionId` spostato da `StreamOptions` a `QueryOptions` (base interface)
  - Entrambi `query()` e `queryStream()` possono ora identificare la sessione

### Architecture
Il gateway già passava `sessionId` — ora il valore arriva fino al backend Me4BrAIn dove attiva il pre-query enrichment (ultimi 10 turni + episodi simili) e post-query persistence (salva turni + crea episodio).

---

## [2026-02-08] - Gateway Timeout Increase

### Changed
- **Me4BrAIn Client Timeout** (`packages/me4brain-client/src/client.ts`):
  - Default timeout da `300000ms` (5 min) → `600000ms` (10 min)
  - Safety margin per pipeline multi-step complesse (NBA betting: 284s)

- **Engine Namespace Timeout** (`packages/me4brain-client/src/engine.ts`):
  - `query()`: `timeout_seconds` da 300 → 600 (+ 10s buffer)
  - `queryStream()`: Timeout fetch e `timeout_seconds` da 300 → 600
  - Entrambi sync e SSE stream aggiornati

### Context
La pipeline NBA betting (97 tool calls, 5 step) impiegava 284s — entro il vecchio timeout ma senza margine di sicurezza. Aumentato a 600s per query complesse future.

---



### Added
- **Extended Conversation Context** (`backend/services/me4brain_service.py`):
  - Context window espanso da 3 assistant → **5 user + 3 assistant** messages
  - 60-70% context budget per conversation history (best practice 2026)
  - Labeled context con `[USER]:`, `[ASSISTANT]:`, `[ENTITIES:]`

- **Entity Tracking** (`_extract_entities` method):
  - Email addresses extraction
  - Crypto tickers: BTC, ETH, SOL, XRP, ADA, DOGE, etc.
  - Stock tickers: $AAPL, $MSFT, etc.
  - Date patterns: YYYY-MM-DD, DD/MM/YYYY
  - Flight codes: AA123, IB456, etc.
  - IATA airport codes: FCO, JFK, LAX, LHR, etc.
  - Tool mentions: gmail_search, drive_list, etc.
  - Proper names extraction

### Changed
- **Context Building**: Prima passava solo 3 messaggi assistant (8000 chars ciascuno), ora costruisce context strutturato con limiti per messaggio (500 chars user, 3000 chars assistant)

---

## [2026-02-04] - Session Management & Editable Titles

### Added
- **Editable Session Titles**:
  - `PATCH /api/chat/sessions/{id}` - Update session title
  - Double-click on title to edit inline
  - Pencil icon button for edit mode
  - Enter to save, Escape to cancel
  - **Me4Brain Integration**: Uses new PATCH `/v1/working/sessions/{id}` endpoint with Redis-backed metadata storage
  - **Local Cache Fallback**: `data/session_titles.json` for backwards compatibility

### Added
- **Session Management**:
  - `POST /api/chat/sessions` - Create new chat sessions
  - `DELETE /api/chat/sessions/{id}` - Delete sessions
  - Sidebar with real session list from Me4Brain API
  - Auto-generated session titles from first user message
  - Session load/delete functionality in UI
- **Frontend Store (`useChatStore.ts`)**:
  - Multi-session state management
  - `fetchSessions()`, `createNewSession()`, `loadSession()`, `deleteSession()` actions
- **Auto-refresh**: Session titles update automatically after AI response

### Changed
- `Sidebar.tsx`: Refactored to use real data from store instead of mock data
- `list_sessions()`: Now extracts titles from first user message (max 50 chars)
- `useChat.ts`: Calls `fetchSessions()` after streaming completes

### Fixed
- Session creation API route 405 error (backend reload issue)
- Sessions persisting correctly via Me4Brain Working Memory API

---

## [2026-02-02] - Verification: Google Workspace Tools Working

### Verified
- **Backend Fix Confirmed**: Dopo fix Docker in Me4BrAIn (v0.14.2), tutti i tool Google Workspace funzionano:
  - ✅ Google Drive Search: 20 file ANCI trovati
  - ✅ Gmail Search: 20 email ANCI trovate
  - ✅ Calendar Upcoming: eventi recuperati correttamente
- **Report ANCI Generato**: Query complessa multi-tool per progetto "Comune di Ventimiglia di Sicilia e Baucina" completata con successo

---

## [2026-02-01] - Frontend Fixes

### Fixed
- **Hydration Error**: Added `suppressHydrationWarning` to timestamp in MessageBubble to prevent Next.js SSR/CSR mismatch
- **Timeout Configuration**: Using `settings.me4brain_timeout` (360s) consistently across all API calls

### Changed
- Chat responses now display correctly formatted Markdown with ReactMarkdown
