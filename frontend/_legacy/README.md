# Legacy Code Archive

Questa directory contiene codice deprecato che è stato sostituito durante il refactoring di PersAn.

## Backend Python (Deprecato: 2026-02-28)

**Percorso:** `backend-python-deprecated-2026-02-28/`

**Motivo della deprecazione:**
- Architettura split-brain eliminata
- Funzionalità migrate al Gateway TypeScript e Me4BrAIn
- Frontend ora comunica esclusivamente con Gateway (porta 3030)

**Funzionalità migrate:**
- **Upload/OCR**: Migrato a Me4BrAIn API (`POST /v1/ingestion/upload`)
- **Chat streaming**: Già gestito dal Gateway TypeScript
- **Session management**: Gestito dal Gateway + Me4BrAIn Working Memory API

**Funzionalità NON migrate (non utilizzate):**
- Memory routes (`/memory/*`) - Non usate dal frontend
- Proactive routes (`/api/proactive/*`) - Non usate dal frontend
- Monitors routes (`/monitors/*`) - Proxy non più necessario

**Riferimenti:**
- Commit PersAn: `4cebc83` - "Phase 1 Complete - OCR Migration to Me4BrAIn API"
- Commit Me4BrAIn: `1897f54` - "Expose OCR via HTTP API - Ingestion Endpoint"

**Note:**
Questo codice è mantenuto per riferimento storico e può essere rimosso completamente in futuro.
Se necessario recuperare funzionalità specifiche, consultare questo archivio.
