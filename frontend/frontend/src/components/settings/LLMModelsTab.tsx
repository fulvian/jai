'use client';

import { useState, useEffect, useMemo } from 'react';
import { RefreshCw, Save, AlertCircle } from 'lucide-react';
import { useSettingsStore } from '@/stores/useSettingsStore';
import { useLLMConfig, useUpdateLLMConfig, useAvailableModels, useHardwareRecommendations } from '@/hooks/useSettings';
import { ModelSelector } from './ModelSelector';
import { ParameterInput } from './ParameterInput';
import { Toggle } from './Toggle';
import { SETTINGS_LABELS } from './settingsLabels';

const MODEL_ROLES = [
  { key: 'model_primary', labelKey: 'model_primary' as const },
  { key: 'model_routing', labelKey: 'model_routing' as const },
  { key: 'model_synthesis', labelKey: 'model_synthesis' as const },
  { key: 'model_fallback', labelKey: 'model_fallback' as const },
] as const;

export function LLMModelsTab() {
  const { setLLMConfig, setLoading, setError } = useSettingsStore();
  const { config, isLoading: configLoading, error: configError, refresh } = useLLMConfig();
  const { models, isLoading: modelsLoading } = useAvailableModels();
  const { recommendations } = useHardwareRecommendations();
  const { updateConfig } = useUpdateLLMConfig();
  const [saving, setSaving] = useState(false);
  // NOTE: Initial state should match server defaults until config is fetched
  // The useEffect below syncs with server config once available
  const [localConfig, setLocalConfig] = useState({
    model_primary: '',
    model_routing: '',
    model_synthesis: '',
    model_fallback: '',
    use_local: true,
    context_overflow_strategy: 'map_reduce' as 'map_reduce' | 'truncate' | 'cloud_fallback',
    default_temperature: 0.3,
    default_max_tokens: 8192,
    context_window: 32768,
  });

  // Track if initial config has been loaded from server
  const [configLoaded, setConfigLoaded] = useState(false);

  useEffect(() => {
    if (config && !configLoaded) {
      setLocalConfig({
        model_primary: config.model_primary,
        model_routing: config.model_routing,
        model_synthesis: config.model_synthesis,
        model_fallback: config.model_fallback,
        use_local: config.use_local,
        context_overflow_strategy: config.context_overflow_strategy,
        default_temperature: config.default_temperature,
        default_max_tokens: config.default_max_tokens,
        context_window: config.context_window,
      });
      setConfigLoaded(true);
    }
  }, [config, configLoaded]);

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

  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await updateConfig({
        model_primary: localConfig.model_primary,
        model_routing: localConfig.model_routing,
        model_synthesis: localConfig.model_synthesis,
        model_fallback: localConfig.model_fallback,
        use_local_tool_calling: localConfig.use_local,
        context_overflow_strategy: localConfig.context_overflow_strategy,
        default_max_tokens: localConfig.default_max_tokens,
        context_window_size: localConfig.context_window,
        default_temperature: localConfig.default_temperature,
      });
      
      // Verify that the values were saved correctly
      if (response?.verified_config) {
        console.log('Config saved successfully:', response.verified_config);
      }
      
      // Refresh the config from server to ensure persistence
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save config');
    } finally {
      setSaving(false);
    }
  };

  const isLoading = configLoading || modelsLoading || !configLoaded;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="w-6 h-6 animate-spin text-accent" />
        <span className="ml-3 text-text-secondary">Caricamento configurazione...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {configError && (
        <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400">
          <AlertCircle size={18} />
          <span>{configError}</span>
        </div>
      )}

      <div>
        <h3 className="text-sm font-semibold text-text-primary mb-4">Selezione Modelli</h3>
        <div className="space-y-4">
          {MODEL_ROLES.map(({ key, labelKey }) => (
            <ModelSelector
              key={key}
              roleKey={labelKey}
              value={localConfig[key]}
              onChange={(value) => setLocalConfig({ ...localConfig, [key]: value })}
              models={models}
            />
          ))}
        </div>
      </div>

      <div className="pt-4 border-t border-border">
        <h3 className="text-sm font-semibold text-text-primary mb-4">Parametri di Generazione</h3>
        <div className="grid grid-cols-2 gap-4">
          <ParameterInput
            labelKey="temperature"
            type="range"
            min={0}
            max={2}
            step={0.1}
            value={localConfig.default_temperature}
            onChange={(value) => setLocalConfig({ ...localConfig, default_temperature: value })}
            recommendations={recommendations}
          />

          <ParameterInput
            labelKey="max_tokens"
            type="number"
            min={64}
            max={32768}
            value={localConfig.default_max_tokens}
            onChange={(value) => setLocalConfig({ ...localConfig, default_max_tokens: value })}
            recommendations={recommendations}
          />

          <ParameterInput
            labelKey="context_window"
            type="number"
            min={2048}
            max={131072}
            value={localConfig.context_window}
            onChange={(value) => setLocalConfig({ ...localConfig, context_window: value })}
            recommendations={recommendations}
          />

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <label className="block text-sm font-medium text-text-primary">
                {SETTINGS_LABELS.use_local_tool_calling.label}
              </label>
            </div>
            <p className="text-xs text-text-tertiary">{SETTINGS_LABELS.use_local_tool_calling.description}</p>
            <div className="pt-1">
              <Toggle
                enabled={localConfig.use_local}
                onChange={(enabled) => setLocalConfig({ ...localConfig, use_local: enabled })}
                label
              />
            </div>
          </div>
        </div>
      </div>

      <div className="flex justify-end pt-4">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-accent text-white rounded-lg font-medium hover:bg-accent/90 transition-colors disabled:opacity-50"
        >
          {saving ? (
            <RefreshCw className="w-4 h-4 animate-spin" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          Salva Configurazione
        </button>
      </div>
    </div>
  );
}

export default LLMModelsTab;
