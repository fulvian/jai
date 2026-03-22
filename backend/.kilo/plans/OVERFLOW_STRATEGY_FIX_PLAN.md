# Piano FIX: Strategia Overflow Contesto - AdvancedTab

**Data Analisi**: 2026-03-15
**Priorità**: ALTA
**Status**: ✅ COMPLETATO
**Sessione**: Configurazione preferenze e parametrizzazione

---

## 1. Problema Identificato

L'utente ha segnalato che nella scheda "Advanced" del pannello Settings, quando viene selezionata una delle tre opzioni di "Strategia Overflow Contesto" (map_reduce, truncate, cloud_fallback):

1. **Non è chiaro se la strategia viene applicata** - Nessun feedback visivo conferma all'utente che l'opzione è stata applicata dal sistema
2. **Manca un segnale di conferma** - Il riquadro dell'opzione non cambia colore (es. verde) per indicare che è attiva e applicata
3. **Backend non implementa le strategie** - La strategia è definita nella configurazione ma NON viene letta né applicata nel `ResponseSynthesizer`

---

## 2. Analisi Tecnica

### 2.1 Backend - Strategia NON Applicata

**File**: `src/me4brain/engine/synthesizer.py`

Il synthesizer ha un controllo HARDCODED per il map-reduce:

```python
# Riga 23
MAP_THRESHOLD_CHARS = 16_000

# Riga 94
if len(results_context) > MAP_THRESHOLD_CHARS:
    logger.info("synthesizer_triggering_map_reduce", context_size=len(results_context))
    results_context = await self._map_reduce_results(results, query)
```

**Problema**: La strategia `context_overflow_strategy` NON viene letta dalla configurazione. Le strategie "truncate" e "cloud_fallback" non sono implementate.

### 2.2 Backend - Configurazione Cached

**File**: `src/me4brain/llm/config.py`

```python
@lru_cache
def get_llm_config() -> LLMConfig:
    """Restituisce la configurazione LLM singleton."""
    return LLMConfig()
```

**Problema**: Quando l'API `PUT /v1/config/llm/update` aggiorna `os.environ["CONTEXT_OVERFLOW_STRATEGY"]`, il valore cached NON viene invalidato. Il sistema continua a usare il vecchio valore.

### 2.3 Frontend - Feedback Visivo Mancante

**File**: `PersAn/frontend/src/components/settings/AdvancedTab.tsx`

```tsx
// Riga 33-44
const handleStrategyChange = async (strategy) => {
  setSaving(true);
  try {
    const newConfig = { ...llmConfig, context_overflow_strategy: strategy };
    await updateConfig({ context_overflow_strategy: strategy });
    setLLMConfig(newConfig);  // Aggiorna solo lo store locale
  } catch (err) {
    console.error('Failed to update strategy:', err);
  } finally {
    setSaving(false);
  }
};
```

**Problemi**:
1. Il feedback visivo si basa su `llmConfig.context_overflow_strategy` dello store locale, NON sulla risposta del backend
2. Non c'è un indicatore di "Applicato" o "Confermato"
3. Non c'è un messaggio di successo/errore visibile all'utente
4. Non c'è un reload della configurazione dal backend dopo l'aggiornamento

---

## 3. Piano di Implementazione

### FASE A: Backend - Implementazione Strategie Overflow (CRITICO)

**Tempo stimato**: 4 ore

#### A1. Modificare `ResponseSynthesizer` per leggere la strategia

**File**: `src/me4brain/engine/synthesizer.py`

```python
# Aggiungere import
from me4brain.llm.config import get_llm_config

class ResponseSynthesizer:
    def __init__(
        self,
        llm_client: Any,
        model: str = "deepseek-chat",
        is_local: bool = False,
        overflow_strategy: str | None = None,  # NUOVO parametro
    ) -> None:
        self._llm = llm_client
        self._model = model
        self._is_local = is_local
        self._overflow_strategy = overflow_strategy  # NUOVO
    
    def _get_overflow_strategy(self) -> str:
        """Legge la strategia dalla configurazione corrente."""
        if self._overflow_strategy:
            return self._overflow_strategy
        try:
            config = get_llm_config()
            return config.context_overflow_strategy
        except Exception:
            return "map_reduce"  # Default fallback
    
    async def synthesize(self, query: str, results: list[ToolResult], context: str | None = None) -> str:
        # ... codice esistente ...
        
        results_context = self._format_results(results)
        
        # NUOVO: Applica strategia configurata
        strategy = self._get_overflow_strategy()
        
        if len(results_context) > MAP_THRESHOLD_CHARS:
            if strategy == "map_reduce":
                logger.info("synthesizer_map_reduce_triggered", context_size=len(results_context))
                results_context = await self._map_reduce_results(results, query)
            elif strategy == "truncate":
                logger.info("synthesizer_truncate_triggered", context_size=len(results_context))
                results_context = self._truncate_context(results_context)
            elif strategy == "cloud_fallback":
                logger.info("synthesizer_cloud_fallback_triggered", context_size=len(results_context))
                results_context = await self._cloud_fallback_synthesis(results, query)
        
        # ... resto del codice ...
    
    def _truncate_context(self, context: str, max_chars: int = 12_000) -> str:
        """Tronca il contesto mantenendo le parti più recenti."""
        if len(context) <= max_chars:
            return context
        # Mantiene gli ultimi max_chars caratteri
        return "...[contesto precedente troncato]...\n\n" + context[-max_chars:]
    
    async def _cloud_fallback_synthesis(self, results: list[ToolResult], query: str) -> str:
        """Usa modello cloud per sintesi quando context overflow."""
        from me4brain.llm.provider_factory import get_reasoning_client
        
        cloud_client = get_reasoning_client()
        # Forza uso modello cloud (Mistral Large 3)
        # ... implementazione ...
```

#### A2. Implementare anche in `synthesize_streaming()`

**File**: `src/me4brain/engine/synthesizer.py` (riga ~942)

Applicare la stessa logica di selezione strategia nel metodo streaming.

#### A3. Invalidare cache configurazione dopo update

**File**: `src/me4brain/api/routes/llm_config.py`

```python
@router.put("/update")
async def update_llm_config(update: LLMConfigUpdate) -> dict[str, Any]:
    """Aggiorna configurazione LLM a runtime."""
    import os
    from me4brain.llm.config import get_llm_config
    
    updates_applied = []
    
    if update.context_overflow_strategy is not None:
        os.environ["CONTEXT_OVERFLOW_STRATEGY"] = update.context_overflow_strategy
        updates_applied.append(f"context_overflow_strategy={update.context_overflow_strategy}")
        
        # NUOVO: Invalida la cache per forzare rilettura
        get_llm_config.cache_clear()
    
    # ... resto del codice ...
    
    # NUOVO: Verifica che il valore sia stato applicato
    new_config = get_llm_config()
    applied_strategy = new_config.context_overflow_strategy
    
    logger.info(
        "llm_config_updated",
        updates=updates_applied,
        verified_strategy=applied_strategy,
    )
    
    return {
        "status": "updated",
        "updates_applied": updates_applied,
        "verified_config": {
            "context_overflow_strategy": applied_strategy,
        },
        "note": "Changes are in-memory only. Update .env for persistence.",
    }
```

---

### FASE B: Frontend - Feedback Visivo (ALTO)

**Tempo stimato**: 3 ore

#### B1. Aggiungere stato di conferma visiva

**File**: `PersAn/frontend/src/components/settings/AdvancedTab.tsx`

```tsx
'use client';

import { useState, useEffect } from 'react';
import { Info, AlertTriangle, Check, Loader2 } from 'lucide-react';
import { useSettingsStore } from '@/stores/useSettingsStore';
import { useUpdateLLMConfig, useLLMConfig } from '@/hooks/useSettings';
import { Toggle } from './Toggle';
import { OVERFLOW_STRATEGIES_IT, FEATURE_FLAGS_IT } from './settingsLabels';

export function AdvancedTab() {
  const { llmConfig, setLLMConfig } = useSettingsStore();
  const { config, mutate } = useLLMConfig();  // NUOVO: mutate per refresh
  const { updateConfig } = useUpdateLLMConfig();
  const [saving, setSaving] = useState(false);
  const [confirmedStrategy, setConfirmedStrategy] = useState<string | null>(null);  // NUOVO
  const [error, setError] = useState<string | null>(null);  // NUOVO
  
  // ... codice esistente ...
  
  // NUOVO: Sincronizza con backend
  useEffect(() => {
    if (config?.context_overflow_strategy) {
      setConfirmedStrategy(config.context_overflow_strategy);
      setLLMConfig({ context_overflow_strategy: config.context_overflow_strategy });
    }
  }, [config]);

  const handleStrategyChange = async (strategy: typeof llmConfig.context_overflow_strategy) => {
    setSaving(true);
    setError(null);
    
    try {
      const response = await updateConfig({ context_overflow_strategy: strategy });
      
      // NUOVO: Verifica risposta backend
      if (response?.verified_config?.context_overflow_strategy === strategy) {
        setConfirmedStrategy(strategy);
        setLLMConfig({ context_overflow_strategy: strategy });
        
        // Refresh config dal backend per conferma
        await mutate();
      } else {
        setError('Il backend non ha confermato l\'applicazione della strategia');
      }
    } catch (err) {
      console.error('Failed to update strategy:', err);
      setError('Errore durante l\'aggiornamento della strategia');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* NUOVO: Messaggio di errore */}
      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}
      
      <div>
        <div className="flex items-center gap-2 mb-4">
          <h3 className="text-sm font-semibold text-text-primary">Strategia Overflow Contesto</h3>
          <div title="Come gestire conversazioni troppo lunghe per la memoria disponibile">
            <Info className="w-4 h-4 text-text-tertiary" />
          </div>
          {/* NUOVO: Indicatore di stato */}
          {saving && <Loader2 className="w-4 h-4 animate-spin text-accent" />}
        </div>
        
        <div className="space-y-3">
          {OVERFLOW_STRATEGIES_IT.map((strategy) => {
            // NUOVO: Usa confirmedStrategy per determinare selezione
            const isSelected = confirmedStrategy === strategy.value;
            const isApplied = !saving && isSelected && confirmedStrategy === strategy.value;
            
            return (
              <button
                key={strategy.value}
                onClick={() => handleStrategyChange(strategy.value)}
                disabled={saving}
                className={`w-full p-4 rounded-lg border text-left transition-all ${
                  isSelected
                    ? 'border-green-500 bg-green-500/10 shadow-[0_0_10px_rgba(34,197,94,0.2)]'  // Verde se applicato
                    : 'border-border hover:border-white/20 bg-bg-tertiary/50'
                } ${saving ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-text-primary">{strategy.label}</span>
                    {/* NUOVO: Badge "Applicato" */}
                    {isApplied && (
                      <span className="flex items-center gap-1 text-xs px-2 py-0.5 bg-green-500/20 text-green-400 rounded-full">
                        <Check className="w-3 h-3" />
                        Applicato
                      </span>
                    )}
                    {strategy.recommended && !isApplied && (
                      <span className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded-full">
                        Consigliato
                      </span>
                    )}
                  </div>
                  {/* NUOVO: Indicatore di caricamento su opzione selezionata */}
                  {saving && llmConfig.context_overflow_strategy === strategy.value && (
                    <Loader2 className="w-4 h-4 animate-spin text-accent" />
                  )}
                </div>
                <p className="text-xs text-text-tertiary mb-2">{strategy.description}</p>
                <p className="text-xs text-text-tertiary/70 italic">{strategy.tooltip}</p>
              </button>
            );
          })}
        </div>
        
        {/* NUOVO: Info sulla strategia attiva */}
        <div className="mt-4 p-3 glass-panel-light rounded-lg">
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <Check className="w-4 h-4 text-green-400" />
            <span>
              Strategia attiva: <strong className="text-text-primary">
                {OVERFLOW_STRATEGIES_IT.find(s => s.value === confirmedStrategy)?.label || 'Non configurata'}
              </strong>
            </span>
          </div>
        </div>
      </div>
      
      {/* ... resto del componente ... */}
    </div>
  );
}
```

#### B2. Aggiungere tipi per risposta API verificata

**File**: `PersAn/frontend/src/hooks/useSettings.ts`

```typescript
// Aggiornare interfaccia risposta
interface LLMConfigUpdateResponse {
  status: string;
  updates_applied: string[];
  verified_config?: {
    context_overflow_strategy?: string;
  };
  note: string;
}

export function useUpdateLLMConfig() {
  const updateConfig = async (config: LLMConfigUpdate): Promise<LLMConfigUpdateResponse> => {
    const res = await fetch(`${API_CONFIG.gatewayUrl}/api/config/llm/update`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    
    if (!res.ok) throw new Error('Failed to update config');
    
    const response = await res.json();
    mutate('/api/config/llm/current');
    return response;
  };

  return { updateConfig };
}
```

---

### FASE C: Test e Verifica (MEDIO)

**Tempo stimato**: 2 ore

#### C1. Test Backend

```python
# tests/unit/test_overflow_strategy.py

import pytest
from unittest.mock import patch, AsyncMock
from me4brain.engine.synthesizer import ResponseSynthesizer
from me4brain.engine.types import ToolResult

@pytest.mark.asyncio
async def test_map_reduce_strategy_applied():
    """Verifica che map_reduce venga applicato quando configurato."""
    with patch.dict('os.environ', {'CONTEXT_OVERFLOW_STRATEGY': 'map_reduce'}):
        from me4brain.llm.config import get_llm_config
        get_llm_config.cache_clear()
        
        synthesizer = ResponseSynthesizer(mock_llm, "test-model")
        # Genera contesto > 16K chars
        large_results = [ToolResult(tool_name="test", success=True, data={"content": "x" * 20000})]
        
        # Dovrebbe chiamare _map_reduce_results
        # ...

@pytest.mark.asyncio
async def test_truncate_strategy_applied():
    """Verifica che truncate venga applicato quando configurato."""
    with patch.dict('os.environ', {'CONTEXT_OVERFLOW_STRATEGY': 'truncate'}):
        from me4brain.llm.config import get_llm_config
        get_llm_config.cache_clear()
        
        synthesizer = ResponseSynthesizer(mock_llm, "test-model")
        # Dovrebbe troncare il contesto
        # ...

@pytest.mark.asyncio
async def test_config_cache_invalidated_on_update():
    """Verifica che la cache venga invalidata dopo update API."""
    from me4brain.api.routes.llm_config import update_llm_config
    from me4brain.llm.config import get_llm_config
    
    # Config iniziale
    initial = get_llm_config()
    assert initial.context_overflow_strategy == "map_reduce"
    
    # Update via API
    await update_llm_config(LLMConfigUpdate(context_overflow_strategy="truncate"))
    
    # Verifica nuovo valore
    updated = get_llm_config()
    assert updated.context_overflow_strategy == "truncate"
```

#### C2. Test Frontend E2E

```typescript
// tests/e2e/settings.spec.ts

describe('AdvancedTab - Overflow Strategy', () => {
  it('should show green border when strategy is selected', async () => {
    render(<AdvancedTab />);
    
    const mapReduceButton = screen.getByText('Map-Reduce').closest('button');
    fireEvent.click(mapReduceButton);
    
    // Attendi conferma backend
    await waitFor(() => {
      expect(mapReduceButton).toHaveClass('border-green-500');
    });
    
    // Verifica badge "Applicato"
    expect(screen.getByText('Applicato')).toBeInTheDocument();
  });
  
  it('should show error if backend fails', async () => {
    server.use(
      rest.put('/api/config/llm/update', (req, res, ctx) => {
        return res(ctx.status(500));
      })
    );
    
    render(<AdvancedTab />);
    
    const truncateButton = screen.getByText('Troncamento').closest('button');
    fireEvent.click(truncateButton);
    
    await waitFor(() => {
      expect(screen.getByText(/Errore durante l'aggiornamento/)).toBeInTheDocument();
    });
  });
});
```

---

## 4. Riepilogo File da Modificare

| File | Modifica | Priorità |
|------|----------|----------|
| `src/me4brain/engine/synthesizer.py` | Leggere strategia da config, implementare truncate/cloud_fallback | CRITICO |
| `src/me4brain/api/routes/llm_config.py` | Invalidare cache, restituire verified_config | CRITICO |
| `PersAn/frontend/src/components/settings/AdvancedTab.tsx` | Feedback visivo verde, badge "Applicato", error handling | ALTO |
| `PersAn/frontend/src/hooks/useSettings.ts` | Tipi risposta verificata | MEDIO |
| `tests/unit/test_overflow_strategy.py` | Test backend | MEDIO |

---

## 5. Criteri di Accettazione

1. ✅ Quando l'utente seleziona una strategia, il riquadro diventa **verde** con un badge "Applicato"
2. ✅ Il backend **applica effettivamente** la strategia selezionata nel synthesizer
3. ✅ La cache della configurazione viene **invalidata** dopo l'update
4. ✅ L'API restituisce `verified_config` per confermare l'applicazione
5. ✅ In caso di errore, viene mostrato un **messaggio di errore** visibile
6. ✅ La strategia "truncate" tronca effettivamente il contesto
7. ✅ La strategia "cloud_fallback" usa il modello cloud quando il contesto overflow

---

## 6. Implementazione Completata

**Data completamento**: 2026-03-15

### File Modificati

| File | Modifiche |
|------|-----------|
| `src/me4brain/engine/synthesizer.py` | Aggiunto `_get_overflow_strategy()`, `_truncate_context()`, `_cloud_fallback_synthesis()`, logica selezione in `synthesize()` e `synthesize_streaming()` |
| `src/me4brain/api/routes/llm_config.py` | Aggiunto `cache_clear()`, `verified_config` nella risposta |
| `PersAn/frontend/src/components/settings/AdvancedTab.tsx` | Feedback visivo verde, badge "Applicato", gestione errori, verifica risposta backend |
| `PersAn/frontend/src/hooks/useSettings.ts` | Interfaccia `LLMConfigUpdateResponse` con `verified_config` |
| `PersAn/frontend/src/components/settings/settingsLabels.ts` | `OVERFLOW_STRATEGIES_IT` con 3 strategie |

---

## 6. Ordine di Implementazione Consigliato

1. **Backend A3** - Invalidare cache in `llm_config.py` (10 min)
2. **Backend A1** - Modificare `synthesizer.py` per leggere strategia (1 ora)
3. **Backend A2** - Implementare strategia in streaming (30 min)
4. **Frontend B2** - Aggiornare tipi risposta (15 min)
5. **Frontend B1** - Aggiungere feedback visivo (2 ore)
6. **Test C1/C2** - Verificare funzionamento (1 ora)

**Tempo totale stimato**: ~5 ore

---

*Piano elaborato da analisi codebase Me4BrAIn + PersAn - Sessione 2026-03-15*
