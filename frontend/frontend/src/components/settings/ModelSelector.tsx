'use client';

import { useState, useMemo } from 'react';
import { ChevronDown, Cpu, Cloud, Info } from 'lucide-react';
import { SETTINGS_LABELS } from './settingsLabels';

interface Model {
  id: string;
  name: string;
  provider: string;
  context_window: number;
  supports_tools: boolean;
  supports_vision: boolean;
}

interface ModelSelectorProps {
  value: string;
  onChange: (value: string) => void;
  models: Model[];
  roleKey: 'model_primary' | 'model_routing' | 'model_synthesis' | 'model_fallback';
  disabled?: boolean;
}

export function ModelSelector({ value, onChange, models, roleKey, disabled = false }: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const labelConfig = SETTINGS_LABELS[roleKey];

  const groupedModels = useMemo(() => {
    const local = models.filter((model) =>
      model.provider.includes('local') ||
      model.provider.includes('mlx') ||
      model.provider.includes('ollama') ||
      model.provider.includes('lmstudio')
    );
    const cloud = models.filter((model) =>
      model.provider.includes('cloud') ||
      model.provider.toLowerCase().includes('nanogpt') ||
      model.provider.includes('custom')
    );
    return { local, cloud };
  }, [models]);

  const selectedModel = models.find(m => m.id === value);
  const isLocal = selectedModel && (
    selectedModel.provider.includes('local') ||
    selectedModel.provider.includes('mlx') ||
    selectedModel.provider.includes('ollama') ||
    selectedModel.provider.includes('lmstudio')
  );

  const handleSelect = (modelId: string) => {
    onChange(modelId);
    setIsOpen(false);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <label className="block text-sm font-medium text-text-primary">
          {labelConfig.label}
        </label>
        <div className="group relative">
          <Info className="w-4 h-4 text-text-tertiary cursor-help" />
          <div className="absolute left-0 bottom-full mb-2 w-72 p-3 glass-panel-floating text-xs text-text-secondary opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
            <p className="mb-2">{labelConfig.tooltip}</p>
            <p className="text-text-tertiary italic">{labelConfig.example}</p>
          </div>
        </div>
      </div>
      
      <p className="text-xs text-text-tertiary">{labelConfig.description}</p>

      <div className="relative">
        <button
          type="button"
          disabled={disabled}
          onClick={() => !disabled && setIsOpen(!isOpen)}
          className={`
            w-full px-3 py-2.5 bg-bg-tertiary border border-border rounded-lg text-left
            flex items-center justify-between gap-2
            focus:outline-none focus:ring-2 focus:ring-accent/50
            ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-border/80'}
          `}
        >
          <div className="flex items-center gap-2 min-w-0">
            {selectedModel ? (
              <>
                {isLocal ? (
                  <Cpu className="w-4 h-4 text-green-400 flex-shrink-0" />
                ) : (
                  <Cloud className="w-4 h-4 text-blue-400 flex-shrink-0" />
                )}
                <span className="text-sm text-text-primary truncate">
                  {selectedModel.name || selectedModel.id}
                </span>
                <span className="text-xs text-text-tertiary flex-shrink-0">
                  ({selectedModel.context_window.toLocaleString()} ctx)
                </span>
              </>
            ) : (
              <span className="text-sm text-text-tertiary">Seleziona un modello...</span>
            )}
          </div>
          <ChevronDown className={`w-4 h-4 text-text-tertiary transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        </button>

        {isOpen && (
          <div className="absolute z-50 w-full mt-1 glass-panel-floating max-h-64 overflow-auto">
            {groupedModels.local.length > 0 && (
              <div>
                <div className="px-3 py-2 text-xs font-semibold text-text-tertiary uppercase tracking-wide bg-bg-secondary/50 flex items-center gap-2">
                  <Cpu className="w-3 h-3" />
                  Locale (Su questo dispositivo)
                </div>
                {groupedModels.local.map((model) => (
                  <button
                    key={model.id}
                    type="button"
                    onClick={() => handleSelect(model.id)}
                    className={`
                      w-full px-3 py-2 text-left hover:bg-bg-secondary/50 transition-colors
                      flex items-center justify-between gap-2
                      ${value === model.id ? 'bg-accent/10 text-accent' : 'text-text-primary'}
                    `}
                  >
                    <span className="text-sm truncate">{model.name || model.id}</span>
                    <span className="text-xs text-text-tertiary flex-shrink-0">
                      {model.context_window.toLocaleString()} ctx
                    </span>
                  </button>
                ))}
              </div>
            )}
            
            {groupedModels.cloud.length > 0 && (
              <div>
                <div className="px-3 py-2 text-xs font-semibold text-text-tertiary uppercase tracking-wide bg-bg-secondary/50 flex items-center gap-2">
                  <Cloud className="w-3 h-3" />
                  Cloud (NanoGPT API)
                </div>
                {groupedModels.cloud.map((model) => (
                  <button
                    key={model.id}
                    type="button"
                    onClick={() => handleSelect(model.id)}
                    className={`
                      w-full px-3 py-2 text-left hover:bg-bg-secondary/50 transition-colors
                      flex items-center justify-between gap-2
                      ${value === model.id ? 'bg-accent/10 text-accent' : 'text-text-primary'}
                    `}
                  >
                    <span className="text-sm truncate">{model.name || model.id}</span>
                    <span className="text-xs text-text-tertiary flex-shrink-0">
                      {model.context_window.toLocaleString()} ctx
                    </span>
                  </button>
                ))}
              </div>
            )}

            {groupedModels.local.length === 0 && groupedModels.cloud.length === 0 && (
              <div className="px-3 py-4 text-sm text-text-tertiary text-center">
                Nessun modello disponibile
              </div>
            )}
          </div>
        )}
      </div>

      {isOpen && (
        <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
      )}
    </div>
  );
}

export default ModelSelector;
