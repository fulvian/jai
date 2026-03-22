'use client';

import { useState, useEffect } from 'react';
import { Info, AlertTriangle, Check, Loader2 } from 'lucide-react';
import { useSettingsStore } from '@/stores/useSettingsStore';
import { useUpdateLLMConfig, useLLMConfig } from '@/hooks/useSettings';
import { Toggle } from './Toggle';
import { OVERFLOW_STRATEGIES_IT, FEATURE_FLAGS_IT } from './settingsLabels';

export function AdvancedTab() {
  const { llmConfig, setLLMConfig } = useSettingsStore();
  const { config, refresh } = useLLMConfig();
  const { updateConfig } = useUpdateLLMConfig();
  const [saving, setSaving] = useState(false);
  const [confirmedStrategy, setConfirmedStrategy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [featureFlags, setFeatureFlags] = useState<Record<string, boolean>>({
    useLocalToolCalling: llmConfig.use_local,
    enableStreaming: true,
    enableCaching: true,
    enableMetrics: false,
  });

  useEffect(() => {
    if (config) {
      setFeatureFlags({
        useLocalToolCalling: config.use_local,
        enableStreaming: config.enable_streaming ?? true,
        enableCaching: config.enable_caching ?? true,
        enableMetrics: config.enable_metrics ?? false,
      });
      if (config.context_overflow_strategy) {
        setConfirmedStrategy(config.context_overflow_strategy);
        setLLMConfig({ context_overflow_strategy: config.context_overflow_strategy });
      }
    }
  }, [config, setLLMConfig]);

  const handleStrategyChange = async (strategy: typeof llmConfig.context_overflow_strategy) => {
    setSaving(true);
    setError(null);

    try {
      const response = await updateConfig({ context_overflow_strategy: strategy });

      if (response?.verified_config?.context_overflow_strategy === strategy) {
        setConfirmedStrategy(strategy);
        setLLMConfig({ context_overflow_strategy: strategy });
        await refresh();
      } else {
        setError("Il backend non ha confermato l'applicazione della strategia");
      }
    } catch (err) {
      console.error('Failed to update strategy:', err);
      setError('Errore durante l\'aggiornamento della strategia');
    } finally {
      setSaving(false);
    }
  };

  const handleFlagToggle = async (key: string) => {
    const newValue = !featureFlags[key];
    setFeatureFlags((prev) => ({ ...prev, [key]: newValue }));

    try {
      await updateConfig({
        enable_streaming: key === 'enableStreaming' ? newValue : featureFlags.enableStreaming,
        enable_caching: key === 'enableCaching' ? newValue : featureFlags.enableCaching,
        enable_metrics: key === 'enableMetrics' ? newValue : featureFlags.enableMetrics,
        use_local_tool_calling: key === 'useLocalToolCalling' ? newValue : featureFlags.useLocalToolCalling,
      });
    } catch (err) {
      console.error('Failed to update feature flags:', err);
      setFeatureFlags((prev) => ({ ...prev, [key]: !newValue }));
    }
  };

  return (
    <div className="space-y-6">
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
          {saving && <Loader2 className="w-4 h-4 animate-spin text-accent" />}
        </div>
        <div className="space-y-3">
          {OVERFLOW_STRATEGIES_IT.map((strategy) => {
            const isSelected = confirmedStrategy === strategy.value;
            const isApplied = !saving && isSelected;

            return (
              <button
                key={strategy.value}
                onClick={() => handleStrategyChange(strategy.value)}
                disabled={saving}
                className={`w-full p-4 rounded-lg border text-left transition-all ${
                  isApplied
                    ? 'border-green-500 bg-green-500/10 shadow-[0_0_10px_rgba(34,197,94,0.2)]'
                    : 'border-border hover:border-white/20 bg-bg-tertiary/50'
                } ${saving ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-text-primary">{strategy.label}</span>
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

      <div className="pt-4 border-t border-border">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Flag Funzionalità</h3>
        <div className="space-y-4">
          {FEATURE_FLAGS_IT.map((flag) => (
            <div key={flag.key} className="flex items-center justify-between p-3 glass-panel-light rounded-lg">
              <div className="flex-1 mr-4">
                <div className="font-medium text-text-primary">{flag.label}</div>
                <div className="text-xs text-text-tertiary">{flag.description}</div>
              </div>
              <Toggle
                enabled={featureFlags[flag.key]}
                onChange={() => handleFlagToggle(flag.key)}
                label
              />
            </div>
          ))}
        </div>
      </div>

      <div className="pt-4 border-t border-border">
        <div className="flex items-center gap-2 mb-4">
          <h3 className="text-sm font-semibold text-text-primary">Zona Pericolosa</h3>
          <AlertTriangle className="w-4 h-4 text-yellow-500" />
        </div>
        <div className="p-4 border border-red-500/30 bg-red-500/5 rounded-lg">
          <div className="flex items-center justify-between">
            <div>
              <div className="font-medium text-text-primary">Ripristina Predefiniti</div>
              <div className="text-xs text-text-tertiary">Ripristina tutte le impostazioni ai valori predefiniti</div>
            </div>
            <button
              onClick={() => {
                if (confirm('Sei sicuro di voler ripristinare tutte le impostazioni ai valori predefiniti?')) {
                  useSettingsStore.getState().resetConfig();
                }
              }}
              className="px-3 py-1.5 text-sm bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors"
            >
              Ripristina
            </button>
          </div>
        </div>
      </div>

      <div className="pt-4 border-t border-border">
        <h3 className="text-sm font-semibold text-text-primary mb-3">Info Sistema</h3>
        <div className="p-4 glass-panel-light rounded-lg space-y-2 text-xs font-mono">
          <div className="flex justify-between">
            <span className="text-text-tertiary">Versione Gateway</span>
            <span className="text-text-secondary">2.0.0-alpha</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-tertiary">Me4BrAIn API</span>
            <span className="text-text-secondary">localhost:8089</span>
          </div>
          <div className="flex justify-between">
            <span className="text-text-tertiary">Finestra Contesto</span>
            <span className="text-text-secondary">{llmConfig.context_window.toLocaleString()} token</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AdvancedTab;
