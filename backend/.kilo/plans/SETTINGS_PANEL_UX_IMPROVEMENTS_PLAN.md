# Piano di Miglioramento UX - Settings Panel

**Versione**: 1.0
**Data**: 2026-03-15
**Obiettivo**: Risolvere 4 criticità UX nel pannello Settings di PersAn per gestione modelli LLM e risorse

---

## Indice

1. [Analisi delle Criticità](#1-analisi-delle-criticità)
2. [Soluzioni Proposte](#2-soluzioni-proposte)
3. [Implementazione Dettagliata](#3-implementazione-dettagliata)
4. [File da Modificare](#4-file-da-modificare)
5. [Testing](#5-testing)

---

## 1. Analisi delle Criticità

### C1. Didascalie Oscure e Non Localizzate

**Stato attuale:**
```tsx
// LLMModelsTab.tsx:9-13
const MODEL_ROLES = [
  { key: 'model_primary', label: 'Primary Model', description: 'Main model for reasoning and generation' },
  { key: 'model_routing', label: 'Routing Model', description: 'Fast model for intent classification' },
  ...
];
```

**Problemi:**
- Label in inglese tecnico ("Primary Model", "Routing Model")
- Descrizioni generiche e poco informative
- Nessuna indicazione su quando usare quale modello
- Utente non esperto non capisce la differenza tra i ruoli

### C2. Selezione Modello Non Visibile nel Riepilogo

**Stato attuale:**
```tsx
// LLMModelsTab.tsx:110-133
<select value={localConfig[key]} ...>
  <optgroup label="Local (Installed on this device)">
    {groupedModels.local.map((model) => (
      <option key={model.id} value={model.id}>
        {model.name || model.id}
      </option>
    ))}
  </optgroup>
  ...
</select>
```

**Problemi:**
- Il `<select>` mostra il valore solo quando è aperto
- Una volta chiuso, l'utente non vede quale modello è selezionato
- Non c'è un riepilogo visivo delle scelte effettuate
- Per 4 ruoli modello, l'utente deve aprire 4 dropdown per verificare

### C3. Interruttori Toggle Senza Feedback Visivo

**Stato attuale:**
```tsx
// LLMModelsTab.tsx:186-197
<button
  onClick={() => setLocalConfig({ ...localConfig, use_local: !localConfig.use_local })}
  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
    localConfig.use_local ? 'bg-accent' : 'bg-bg-tertiary'
  }`}
>
  <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
    localConfig.use_local ? 'translate-x-6' : 'translate-x-1'
  }`} />
</button>
```

**Problemi:**
- Il colore `bg-accent` (probabilmente blu/viola) non comunica chiaramente ON/OFF
- `bg-bg-tertiary` per OFF è troppo simile al background
- Manca indicazione testuale dello stato
- L'utente non capisce se l'interruttore è attivo o no

### C4. Max Tokens e Context Window Senza Default Ottimizzati

**Stato attuale:**
```tsx
// LLMModelsTab.tsx:162-179
<input
  type="number"
  value={localConfig.default_max_tokens}
  ...
/>
<input
  type="number"
  value={localConfig.context_window}
  ...
/>
```

**Problemi:**
- Valori hardcoded (8192, 32768) senza calcolo dinamico
- Nessuna considerazione della RAM disponibile
- Nessun suggerimento sul valore ottimale
- Utente può inserire valori troppo alti che causano OOM

---

## 2. Soluzioni Proposte

### S1. Localizzazione Italiana e Descrizioni Migliorate

**Approccio:** Creare un file di costanti localizzate con descrizioni chiare e contestuali.

```tsx
// Nuovo file: frontend/src/lib/constants/settingsLabels.ts

export const MODEL_ROLES_IT = {
  model_primary: {
    label: 'Modello Principale',
    description: 'Usato per reasoning avanzato e generazione risposte complesse',
    tooltip: 'Scegli un modello con buone capacità di ragionamento. Se locale, almeno 4B parametri.',
    example: 'Es: Qwen 3.5 4B, Mistral 7B'
  },
  model_routing: {
    label: 'Modello di Routing',
    description: 'Classifica velocemente gli intent e seleziona i domini',
    tooltip: 'Deve essere veloce. Un modello piccolo (1-4B) è sufficiente.',
    example: 'Es: Qwen 3.5 4B, Phi-3 Mini'
  },
  model_synthesis: {
    label: 'Modello di Sintesi',
    description: 'Riassume e combina i risultati dei tool in una risposta coerente',
    tooltip: 'Deve avere buon contesto e capacità di sintesi.',
    example: 'Es: Qwen 3.5 4B, Llama 3.1 8B'
  },
  model_fallback: {
    label: 'Modello di Riserva (Cloud)',
    description: 'Usato quando il modello locale fallisce o le risorse sono insufficienti',
    tooltip: 'Solo cloud. Mistral Large 3 è l\'unico supportato.',
    example: 'Mistral Large 3 via NanoGPT'
  }
};

export const FEATURE_FLAGS_IT = {
  useLocalToolCalling: {
    label: 'Tool Calling Locale',
    description: 'Esegue le chiamate ai tool sul modello locale invece che sul cloud',
    tooltipOn: 'ON: Tutti i tool vengono eseguiti localmente (più privacy, meno costi)',
    tooltipOff: 'OFF: I tool complessi usano il cloud (più affidabilità)'
  },
  enableStreaming: {
    label: 'Risposte in Streaming',
    description: 'Mostra la risposta parola per parola mentre viene generata',
    tooltipOn: 'ON: Risposta fluida e immediata',
    tooltipOff: 'OFF: Risposta completa solo alla fine'
  },
  enableCaching: {
    label: 'Cache Risposte',
    description: 'Memorizza risposte frequenti per accessi più rapidi',
    tooltipOn: 'ON: Query ripetute sono istantanee',
    tooltipOff: 'OFF: Ogni query viene elaborata da zero'
  },
  enableMetrics: {
    label: 'Metriche Performance',
    description: 'Raccoglie statistiche dettagliate sulle prestazioni',
    tooltipOn: 'ON: Dati disponibili per analisi e ottimizzazione',
    tooltipOff: 'OFF: Nessun overhead di raccolta dati'
  }
};

export const PARAMETER_LABELS_IT = {
  temperature: {
    label: 'Temperatura',
    description: 'Controlla la creatività delle risposte',
    low: '0.0-0.3: Risposte deterministiche e coerenti',
    medium: '0.4-0.7: Bilancio tra creatività e coerenza',
    high: '0.8-2.0: Risposte creative e varie'
  },
  maxTokens: {
    label: 'Token Massimi',
    description: 'Lunghezza massima della risposta generata',
    recommended: 'Valore raccomandato in base alle tue risorse:'
  },
  contextWindow: {
    label: 'Finestra di Contesto',
    description: 'Quantità massima di testo che il modello può elaborare',
    recommended: 'Valore raccomandato in base alle tue risorse:'
  }
};

export const OVERFLOW_STRATEGIES_IT = [
  {
    value: 'map_reduce',
    label: 'Map-Reduce',
    description: 'Divide il contesto in blocchi, li elabora in parallelo e unisce i risultati',
    recommended: true,
    whenToUse: 'Ideale per query complesse con molti tool'
  },
  {
    value: 'truncate',
    label: 'Troncamento',
    description: 'Mantiene solo i messaggi più recenti, scarta il contesto vecchio',
    recommended: false,
    whenToUse: 'Quando la velocità è prioritaria sulla completezza'
  },
  {
    value: 'cloud_fallback',
    label: 'Fallback Cloud',
    description: 'Passa automaticamente al modello cloud con finestra più grande',
    recommended: false,
    whenToUse: 'Quando il contesto supera i limiti del modello locale'
  }
];
```

### S2. Visualizzazione Permanente della Selezione Modello

**Approccio:** Sostituire i `<select>` nascosti con un componente che mostra sempre il valore selezionato.

```tsx
// Nuovo componente: ModelSelector.tsx

interface ModelSelectorProps {
  label: string;
  description: string;
  value: string;
  onChange: (value: string) => void;
  localModels: AvailableModel[];
  cloudModels: AvailableModel[];
}

export function ModelSelector({ label, description, value, onChange, localModels, cloudModels }: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const selectedModel = [...localModels, ...cloudModels].find(m => m.id === value);
  
  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-text-primary">{label}</label>
      <p className="text-xs text-text-tertiary">{description}</p>
      
      {/* Riepilogo sempre visibile */}
      <div className="flex items-center gap-3 p-3 glass-panel-light rounded-lg">
        <div className="flex-1">
          <div className="font-medium text-text-primary">
            {selectedModel?.name || value}
          </div>
          <div className="text-xs text-text-tertiary flex items-center gap-2">
            <span className={`px-1.5 py-0.5 rounded text-xs ${
              selectedModel?.provider.includes('local') 
                ? 'bg-green-500/20 text-green-400' 
                : 'bg-blue-500/20 text-blue-400'
            }`}>
              {selectedModel?.provider.includes('local') ? 'Locale' : 'Cloud'}
            </span>
            <span>{selectedModel?.context_window?.toLocaleString()} token</span>
          </div>
        </div>
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="px-3 py-1.5 text-sm bg-bg-tertiary rounded-lg hover:bg-white/10 transition-colors"
        >
          Cambia
        </button>
      </div>
      
      {/* Dropdown espandibile */}
      {isOpen && (
        <div className="border border-border rounded-lg overflow-hidden">
          {localModels.length > 0 && (
            <div className="border-b border-border">
              <div className="px-3 py-2 text-xs font-medium text-text-tertiary bg-bg-tertiary/50">
                Modelli Locali (installati su questo dispositivo)
              </div>
              {localModels.map((model) => (
                <button
                  key={model.id}
                  onClick={() => { onChange(model.id); setIsOpen(false); }}
                  className={`w-full px-3 py-2 text-left hover:bg-white/5 transition-colors ${
                    value === model.id ? 'bg-accent/20' : ''
                  }`}
                >
                  <div className="font-medium text-text-primary">{model.name}</div>
                  <div className="text-xs text-text-tertiary">
                    {model.context_window?.toLocaleString()} token
                    {model.supports_tools && ' • Tool calling'}
                  </div>
                </button>
              ))}
            </div>
          )}
          {cloudModels.length > 0 && (
            <div>
              <div className="px-3 py-2 text-xs font-medium text-text-tertiary bg-bg-tertiary/50">
                Modelli Cloud (NanoGPT API)
              </div>
              {cloudModels.map((model) => (
                <button
                  key={model.id}
                  onClick={() => { onChange(model.id); setIsOpen(false); }}
                  className={`w-full px-3 py-2 text-left hover:bg-white/5 transition-colors ${
                    value === model.id ? 'bg-accent/20' : ''
                  }`}
                >
                  <div className="font-medium text-text-primary">{model.name}</div>
                  <div className="text-xs text-text-tertiary">
                    {model.context_window?.toLocaleString()} token
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

### S3. Toggle con Feedback Visivo Chiaro (Verde/Rosso)

**Approccio:** Aggiungere colori semantici e indicazione testuale dello stato.

```tsx
// Nuovo componente: Toggle.tsx

interface ToggleProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  label: string;
  description: string;
  tooltipOn?: string;
  tooltipOff?: string;
}

export function Toggle({ enabled, onChange, label, description, tooltipOn, tooltipOff }: ToggleProps) {
  return (
    <div className="flex items-center justify-between p-3 glass-panel-light rounded-lg">
      <div className="flex-1 mr-4">
        <div className="font-medium text-text-primary">{label}</div>
        <div className="text-xs text-text-tertiary">{description}</div>
        {enabled && tooltipOn && (
          <div className="text-xs text-green-400 mt-1">{tooltipOn}</div>
        )}
        {!enabled && tooltipOff && (
          <div className="text-xs text-red-400 mt-1">{tooltipOff}</div>
        )}
      </div>
      
      <button
        onClick={() => onChange(!enabled)}
        className={`relative inline-flex h-7 w-12 items-center rounded-full transition-all duration-200 ${
          enabled 
            ? 'bg-green-500 shadow-lg shadow-green-500/30' 
            : 'bg-red-500 shadow-lg shadow-red-500/30'
        }`}
        title={enabled ? 'Clicca per disattivare' : 'Clicca per attivare'}
      >
        <span
          className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition-transform duration-200 ${
            enabled ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
      
      {/* Indicatore testuale */}
      <span className={`ml-2 text-xs font-medium ${
        enabled ? 'text-green-400' : 'text-red-400'
      }`}>
        {enabled ? 'ON' : 'OFF'}
      </span>
    </div>
  );
}
```

### S4. Valori Default Ottimizzati Basati su Risorse Hardware

**Approccio:** Calcolare dinamicamente i valori raccomandati in base alla RAM disponibile.

#### Backend: Nuovo endpoint per raccomandazioni

```python
# Aggiungere a llm_config.py

@router.get("/recommendations/hardware")
async def get_hardware_recommendations() -> dict[str, Any]:
    """Calcola valori ottimali basati sulle risorse hardware."""
    from me4brain.core.monitoring.resource_monitor import get_resource_monitor
    
    monitor = get_resource_monitor()
    stats = await monitor.get_system_stats()
    
    # Calcolo dinamico
    ram_available_gb = stats.ram_available_gb
    ram_total_gb = stats.ram_total_gb
    
    # Regole empiriche per Apple Silicon:
    # - Il modello LLM usa ~1-2GB per miliardo di parametri (quantizzato 4-bit)
    # - Embedding BGE-M3 usa ~2GB
    # - Sistema operativo + altre app: ~4-6GB
    # - Buffer di sicurezza: 20%
    
    usable_ram_gb = ram_available_gb * 0.8  # 20% buffer
    
    # Max tokens raccomandato (basato su contesto che può stare in memoria)
    # ~1 token = 4 bytes in KV cache
    # Con 4GB disponibili per KV cache: ~1M token teorici, ma limitiamo
    
    if usable_ram_gb >= 12:
        max_tokens_recommended = 16384
        context_window_recommended = 65536
    elif usable_ram_gb >= 8:
        max_tokens_recommended = 8192
        context_window_recommended = 32768
    elif usable_ram_gb >= 4:
        max_tokens_recommended = 4096
        context_window_recommended = 16384
    else:
        max_tokens_recommended = 2048
        context_window_recommended = 8192
    
    # Se sotto pressione, riduci ulteriormente
    if stats.is_under_pressure:
        max_tokens_recommended = min(max_tokens_recommended, 4096)
        context_window_recommended = min(context_window_recommended, 16384)
    
    return {
        "hardware": {
            "ram_total_gb": round(ram_total_gb, 1),
            "ram_available_gb": round(ram_available_gb, 1),
            "ram_usage_pct": round(stats.ram_usage_pct, 1),
            "is_under_pressure": stats.is_under_pressure,
            "resource_level": stats.resource_level.value,
        },
        "recommendations": {
            "max_tokens": max_tokens_recommended,
            "context_window": context_window_recommended,
            "use_cloud_fallback": stats.is_under_pressure,
        },
        "explanation": {
            "max_tokens": f"Basato su {ram_available_gb:.1f}GB RAM disponibile, "
                         f"raccomandiamo max {max_tokens_recommended} token per evitare OOM.",
            "context_window": f"Con {ram_total_gb:.1f}GB RAM totali, "
                             f"una finestra di {context_window_recommended} token è sicura.",
        },
        "warnings": [
            f"RAM al {stats.ram_usage_pct:.1f}% - {'ATTENZIONE' if stats.ram_usage_pct > 75 else 'OK'}",
            f"Swap: {stats.swap_used_gb:.1f}GB - {'CRITICO' if stats.swap_used_gb > 2 else 'OK'}",
        ] if stats.is_under_pressure else [],
    }
```

#### Frontend: Hook per raccomandazioni

```tsx
// Aggiungere a useSettings.ts

export function useHardwareRecommendations() {
  const { data, error, isLoading } = useSWR<HardwareRecommendations>(
    '/api/config/llm/recommendations/hardware',
    fetcher,
    { refreshInterval: 30000 } // Aggiorna ogni 30 secondi
  );

  return {
    recommendations: data,
    isLoading,
    error: error?.message,
  };
}

interface HardwareRecommendations {
  hardware: {
    ram_total_gb: number;
    ram_available_gb: number;
    ram_usage_pct: number;
    is_under_pressure: boolean;
    resource_level: string;
  };
  recommendations: {
    max_tokens: number;
    context_window: number;
    use_cloud_fallback: boolean;
  };
  explanation: {
    max_tokens: string;
    context_window: string;
  };
  warnings: string[];
}
```

#### Frontend: Componente con suggerimenti

```tsx
// Nuovo componente: ParameterInput.tsx

interface ParameterInputProps {
  label: string;
  description: string;
  value: number;
  onChange: (value: number) => void;
  recommended?: number;
  explanation?: string;
  min: number;
  max: number;
  step?: number;
}

export function ParameterInput({ 
  label, description, value, onChange, recommended, explanation, min, max, step = 1 
}: ParameterInputProps) {
  const isRecommended = recommended && value === recommended;
  
  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-text-primary">{label}</label>
      <p className="text-xs text-text-tertiary">{description}</p>
      
      {recommended && (
        <div className="flex items-center gap-2 text-xs">
          <span className="text-text-tertiary">Raccomandato:</span>
          <button
            onClick={() => onChange(recommended)}
            className={`px-2 py-1 rounded transition-colors ${
              isRecommended 
                ? 'bg-green-500/20 text-green-400 border border-green-500/30' 
                : 'bg-bg-tertiary text-text-secondary hover:bg-white/10'
            }`}
          >
            {recommended.toLocaleString()}
          </button>
          {isRecommended && (
            <span className="text-green-400">✓</span>
          )}
        </div>
      )}
      
      <div className="flex items-center gap-3">
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(parseInt(e.target.value))}
          min={min}
          max={max}
          step={step}
          className={`flex-1 px-3 py-2 bg-bg-tertiary border rounded-lg text-sm text-text-primary ${
            recommended && value > recommended * 1.5 
              ? 'border-yellow-500/50' 
              : 'border-border'
          }`}
        />
        <span className="text-xs text-text-tertiary">token</span>
      </div>
      
      {explanation && (
        <p className="text-xs text-text-tertiary italic">{explanation}</p>
      )}
      
      {recommended && value > recommended * 1.5 && (
        <div className="flex items-center gap-1 text-xs text-yellow-400">
          <AlertTriangle className="w-3 h-3" />
          <span>Valore alto - rischio di esaurimento memoria</span>
        </div>
      )}
    </div>
  );
}
```

---

## 3. Implementazione Dettagliata

### Fase 1: Backend - Endpoint Raccomandazioni Hardware

**File:** `src/me4brain/api/routes/llm_config.py`

1. Aggiungere endpoint `GET /v1/config/llm/recommendations/hardware`
2. Implementare logica di calcolo basata su RAM disponibile
3. Includere spiegazioni testuali in italiano
4. Aggiungere warning quando il sistema è sotto pressione

### Fase 2: Frontend - Costanti Localizzate

**File:** `frontend/src/lib/constants/settingsLabels.ts` (nuovo)

1. Creare tutte le costanti localizzate in italiano
2. Includere tooltip e spiegazioni contestuali
3. Aggiungere esempi pratici

### Fase 3: Frontend - Componente Toggle Migliorato

**File:** `frontend/src/components/settings/Toggle.tsx` (nuovo)

1. Implementare toggle con colori verde/rosso
2. Aggiungere indicatore testuale ON/OFF
3. Includere tooltip dinamici

### Fase 4: Frontend - Componente ModelSelector

**File:** `frontend/src/components/settings/ModelSelector.tsx` (nuovo)

1. Implementare selettore con riepilogo sempre visibile
2. Badge Local/Cloud
3. Mostrare context window del modello selezionato

### Fase 5: Frontend - Componente ParameterInput

**File:** `frontend/src/components/settings/ParameterInput.tsx` (nuovo)

1. Input con valore raccomandato cliccabile
2. Warning per valori troppo alti
3. Spiegazione del calcolo

### Fase 6: Frontend - Aggiornamento LLMModelsTab

**File:** `frontend/src/components/settings/LLMModelsTab.tsx`

1. Sostituire `<select>` con `ModelSelector`
2. Sostituire toggle inline con componente `Toggle`
3. Sostituire input number con `ParameterInput`
4. Usare costanti localizzate
5. Aggiungere hook per raccomandazioni hardware

### Fase 7: Frontend - Aggiornamento AdvancedTab

**File:** `frontend/src/components/settings/AdvancedTab.tsx`

1. Sostituire toggle inline con componente `Toggle`
2. Usare costanti localizzate per strategie overflow
3. Aggiungere tooltip esplicativi

### Fase 8: Frontend - Aggiornamento Hook

**File:** `frontend/src/hooks/useSettings.ts`

1. Aggiungere `useHardwareRecommendations()`
2. Aggiornare tipi TypeScript

### Fase 9: Gateway - Proxy Endpoint

**File:** `gateway/src/routes/config.ts` (nel progetto PersAn)

1. Aggiungere proxy per `/api/config/llm/recommendations/hardware`

---

## 4. File da Modificare

### Backend (Me4BrAIn)

| File | Modifica | Priorità |
|------|----------|----------|
| `src/me4brain/api/routes/llm_config.py` | Aggiungere endpoint `/recommendations/hardware` | Alta |

### Frontend (PersAn)

| File | Modifica | Priorità |
|------|----------|----------|
| `frontend/src/lib/constants/settingsLabels.ts` | Nuovo file con costanti IT | Alta |
| `frontend/src/components/settings/Toggle.tsx` | Nuovo componente toggle | Alta |
| `frontend/src/components/settings/ModelSelector.tsx` | Nuovo componente selettore | Alta |
| `frontend/src/components/settings/ParameterInput.tsx` | Nuovo componente input | Alta |
| `frontend/src/components/settings/LLMModelsTab.tsx` | Refactoring completo | Alta |
| `frontend/src/components/settings/AdvancedTab.tsx` | Aggiornamento toggle e label | Media |
| `frontend/src/hooks/useSettings.ts` | Aggiungere hook raccomandazioni | Alta |
| `gateway/src/routes/config.ts` | Proxy nuovo endpoint | Alta |
| `frontend/src/components/settings/index.ts` | Esportare nuovi componenti | Bassa |

---

## 5. Testing

### Test Backend

```bash
# Test endpoint raccomandazioni
curl http://localhost:8089/v1/config/llm/recommendations/hardware | jq

# Verifica calcolo dinamico
# 1. Caricare memoria con processi
# 2. Chiamare endpoint
# 3. Verificare che i valori raccomandati si adattino
```

### Test Frontend

1. **Toggle**: Verificare che il colore cambi da verde (ON) a rosso (OFF)
2. **ModelSelector**: Verificare che il modello selezionato sia sempre visibile
3. **ParameterInput**: Verificare che il valore raccomandato sia cliccabile
4. **Localizzazione**: Verificare che tutte le label siano in italiano
5. **Responsive**: Verificare su schermi piccoli

### Test di Integrazione

1. Cambiare modello → verificare che il riepilogo si aggiorni
2. Attivare toggle → verificare che lo stato sia chiaro
3. Modificare max_tokens oltre il raccomandato → verificare warning
4. Sistema sotto pressione → verificare che i valori raccomandati diminuiscano

---

## 6. Stima Temporale

| Fase | Descrizione | Tempo |
|------|-------------|-------|
| 1 | Backend endpoint raccomandazioni | 2 ore |
| 2 | Costanti localizzate | 1 ora |
| 3 | Componente Toggle | 1 ora |
| 4 | Componente ModelSelector | 2 ore |
| 5 | Componente ParameterInput | 1 ora |
| 6 | Refactoring LLMModelsTab | 2 ore |
| 7 | Aggiornamento AdvancedTab | 1 ora |
| 8 | Aggiornamento hook | 0.5 ore |
| 9 | Gateway proxy | 0.5 ore |
| **Totale** | | **~11 ore** |

---

## 7. Dipendenze

Nessuna nuova dipendenza npm o Python richiesta. Tutti i componenti usano:
- React (già presente)
- Tailwind CSS (già presente)
- Lucide React (già presente)
- SWR (già presente)
- Zustand (già presente)

---

## 8. Note Tecniche

### Colori Toggle

```css
/* ON state */
bg-green-500 shadow-lg shadow-green-500/30

/* OFF state */
bg-red-500 shadow-lg shadow-red-500/30
```

### Calcolo Raccomandazioni

```python
# Formula empirica per Apple Silicon
usable_ram_gb = ram_available_gb * 0.8  # 20% buffer sicurezza

if usable_ram_gb >= 12:
    max_tokens = 16384
    context_window = 65536
elif usable_ram_gb >= 8:
    max_tokens = 8192
    context_window = 32768
elif usable_ram_gb >= 4:
    max_tokens = 4096
    context_window = 16384
else:
    max_tokens = 2048
    context_window = 8192
```

### Struttura Directory Finale

```
frontend/src/
├── components/settings/
│   ├── AdvancedTab.tsx       (aggiornato)
│   ├── LLMModelsTab.tsx      (aggiornato)
│   ├── ModelSelector.tsx     (nuovo)
│   ├── ParameterInput.tsx    (nuovo)
│   ├── ResourcesTab.tsx      (invariato)
│   ├── SettingsPanel.tsx     (invariato)
│   ├── Toggle.tsx            (nuovo)
│   └── index.ts              (aggiornato)
├── hooks/
│   └── useSettings.ts        (aggiornato)
└── lib/constants/
    └── settingsLabels.ts     (nuovo)
```

---

*Piano elaborato da analisi completa di Me4BrAIn + PersAn*
