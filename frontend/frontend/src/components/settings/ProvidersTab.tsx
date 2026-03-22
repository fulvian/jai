'use client';

import { useState } from 'react';
import { Plus, Trash2, RefreshCw, Check, X, Plug, Search, Edit2, Crown, CreditCard } from 'lucide-react';
import { useProviders, useCreateProvider, useUpdateProvider, useDeleteProvider, useTestProvider, useDiscoverModels } from '@/hooks/useSettings';

interface ProviderModel {
  id: string;
  display_name: string;
  context_window: number;
  max_output_tokens: number;
  supports_tools: boolean;
  supports_vision: boolean;
  supports_streaming: boolean;
  access_mode: 'subscription' | 'api_paid' | 'both';
  pricing?: {
    input_per_1m?: number;
    output_per_1m?: number;
  };
}

interface ProviderSubscription {
  enabled: boolean;
  weekly_token_limit?: number;
  reset_day?: number;
  tokens_used_this_week?: number;
}

interface Provider {
  id: string;
  name: string;
  type: string;
  base_url: string;
  api_key?: string;
  api_key_header: string;
  models: ProviderModel[];
  is_local: boolean;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
  last_test?: {
    success: boolean;
    latency_ms: number;
    error?: string;
    models_count?: number;
  };
  subscription?: ProviderSubscription;
}

const PROVIDER_TYPES = [
  { value: 'openai_compatible', label: 'OpenAI Compatible', description: 'OpenAI, vLLM, LM Studio, Ollama, NanoGPT' },
  { value: 'anthropic', label: 'Anthropic (Claude)', description: 'Claude API' },
  { value: 'google_gemini', label: 'Google Gemini', description: 'Google AI Studio' },
  { value: 'mistral', label: 'Mistral AI', description: 'Mistral API' },
  { value: 'deepseek', label: 'DeepSeek', description: 'DeepSeek API' },
  { value: 'cohere', label: 'Cohere', description: 'Cohere API' },
  { value: 'custom', label: 'Custom', description: 'Custom endpoint' },
];

const ACCESS_MODES = [
  { value: 'subscription', label: 'Subscription (PRO)', icon: Crown },
  { value: 'api_paid', label: 'API Paid', icon: CreditCard },
  { value: 'both', label: 'Both', icon: null },
];

export function ProvidersTab() {
  const { providers, isLoading, error, refresh } = useProviders();
  const { createProvider } = useCreateProvider();
  const { updateProvider } = useUpdateProvider();
  const { deleteProvider } = useDeleteProvider();
  const { testProvider } = useTestProvider();
  const { discoverModels } = useDiscoverModels();

  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    type: 'openai_compatible',
    base_url: '',
    api_key: '',
    api_key_header: 'Authorization',
    is_local: false,
    is_enabled: true,
    models: [] as ProviderModel[],
    subscription: {
      enabled: false,
      weekly_token_limit: null as number | null,
      reset_day: 1,
    },
  });
  const [testing, setTesting] = useState<string | null>(null);
  const [discovering, setDiscovering] = useState<string | null>(null);
  const [showApiKey, setShowApiKey] = useState(false);

  const resetForm = () => {
    setFormData({
      name: '',
      type: 'openai_compatible',
      base_url: '',
      api_key: '',
      api_key_header: 'Authorization',
      is_local: false,
      is_enabled: true,
      models: [],
      subscription: {
        enabled: false,
        weekly_token_limit: null,
        reset_day: 1,
      },
    });
    setEditingProvider(null);
    setIsCreating(false);
  };

  const handleSave = async () => {
    try {
      const subscriptionData = formData.subscription.enabled
        ? {
            enabled: true,
            weekly_token_limit: formData.subscription.weekly_token_limit ?? undefined,
            reset_day: formData.subscription.reset_day,
          }
        : undefined;
      
      const data = {
        ...formData,
        subscription: subscriptionData,
      };
      
      if (editingProvider) {
        await updateProvider(editingProvider.id, data);
      } else {
        await createProvider(data);
      }
      resetForm();
      refresh();
    } catch (err) {
      console.error('Failed to save provider:', err);
    }
  };

  const handleTest = async (providerId: string) => {
    setTesting(providerId);
    try {
      await testProvider(providerId);
      refresh();
    } finally {
      setTesting(null);
    }
  };

  const handleDiscover = async (providerId: string) => {
    setDiscovering(providerId);
    try {
      const result = await discoverModels(providerId);
      if (result.models && result.models.length > 0) {
        setFormData(prev => ({
          ...prev,
          models: result.models.map((m: any) => ({
            id: m.id,
            display_name: m.display_name || m.id,
            context_window: m.context_window || 32768,
            max_output_tokens: m.max_output_tokens || 4096,
            supports_tools: m.supports_tools ?? true,
            supports_vision: m.supports_vision ?? false,
            supports_streaming: m.supports_streaming ?? true,
            access_mode: 'api_paid',
            pricing: m.pricing,
          })),
        }));
      }
    } finally {
      setDiscovering(null);
    }
  };

  const handleDelete = async (providerId: string) => {
    if (confirm('Are you sure you want to delete this provider?')) {
      await deleteProvider(providerId);
      refresh();
    }
  };

  const addModel = () => {
    setFormData(prev => ({
      ...prev,
      models: [...prev.models, {
        id: '',
        display_name: '',
        context_window: 32768,
        max_output_tokens: 4096,
        supports_tools: true,
        supports_vision: false,
        supports_streaming: true,
        access_mode: 'api_paid',
      }],
    }));
  };

  const updateModel = (index: number, field: keyof ProviderModel, value: any) => {
    setFormData(prev => ({
      ...prev,
      models: prev.models.map((m, i) => i === index ? { ...m, [field]: value } : m),
    }));
  };

  const removeModel = (index: number) => {
    setFormData(prev => ({
      ...prev,
      models: prev.models.filter((_, i) => i !== index),
    }));
  };

  if (isLoading && !providers) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="w-6 h-6 animate-spin text-accent" />
        <span className="ml-3 text-text-secondary">Loading providers...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary">API Providers</h3>
        <button
          onClick={() => setIsCreating(true)}
          className="flex items-center gap-2 px-3 py-1.5 bg-accent text-white rounded-lg text-sm hover:bg-accent/90"
        >
          <Plus size={16} />
          Add Provider
        </button>
      </div>

      {error && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Provider List */}
      <div className="space-y-3">
        {providers?.map((provider) => (
          <div key={provider.id} className="p-4 glass-panel-light rounded-lg">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                <Plug className={`w-5 h-5 ${provider.is_enabled ? 'text-green-400' : 'text-text-tertiary'}`} />
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-text-primary">{provider.name}</span>
                    {provider.subscription?.enabled && (
                      <span className="text-xs px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded-full flex items-center gap-1">
                        <Crown className="w-3 h-3" />
                        PRO
                      </span>
                    )}
                    {provider.is_local && (
                      <span className="text-xs px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded-full">
                        Local
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-text-tertiary">
                    {PROVIDER_TYPES.find(t => t.value === provider.type)?.label || provider.type}
                    {' • '}
                    {provider.models.length} models
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {provider.last_test && (
                  <span className={`text-xs ${provider.last_test.success ? 'text-green-400' : 'text-red-400'}`}>
                    {provider.last_test.success ? `${provider.last_test.latency_ms.toFixed(0)}ms` : 'Failed'}
                  </span>
                )}
                <button
                  onClick={() => handleTest(provider.id)}
                  disabled={testing === provider.id}
                  className="p-1.5 rounded hover:bg-white/10"
                  title="Test connection"
                >
                  <RefreshCw className={`w-4 h-4 text-text-secondary ${testing === provider.id ? 'animate-spin' : ''}`} />
                </button>
                <button
                  onClick={() => {
                    setEditingProvider(provider);
                    setFormData({
                      name: provider.name,
                      type: provider.type,
                      base_url: provider.base_url,
                      api_key: '',
                      api_key_header: provider.api_key_header,
                      is_local: provider.is_local,
                      is_enabled: provider.is_enabled,
                      models: provider.models,
                      subscription: {
                        enabled: provider.subscription?.enabled ?? false,
                        weekly_token_limit: provider.subscription?.weekly_token_limit ?? null,
                        reset_day: provider.subscription?.reset_day ?? 1,
                      },
                    });
                    setIsCreating(true);
                  }}
                  className="p-1.5 rounded hover:bg-white/10"
                  title="Edit"
                >
                  <Edit2 className="w-4 h-4 text-text-secondary" />
                </button>
                <button
                  onClick={() => handleDelete(provider.id)}
                  className="p-1.5 rounded hover:bg-white/10"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4 text-red-400" />
                </button>
              </div>
            </div>
            <div className="text-xs text-text-tertiary font-mono truncate">{provider.base_url}</div>
            
            {/* Models preview */}
            {provider.models.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {provider.models.slice(0, 5).map((model) => (
                  <span
                    key={model.id}
                    className={`text-xs px-2 py-0.5 rounded ${
                      model.access_mode === 'subscription' 
                        ? 'bg-purple-500/20 text-purple-400'
                        : model.access_mode === 'both'
                        ? 'bg-gradient-to-r from-purple-500/20 to-yellow-500/20 text-text-secondary'
                        : ''
                    }`}
                    style={{ 
                      backgroundColor: model.access_mode === 'subscription' || model.access_mode === 'both' ? undefined : 'var(--bg-tertiary)',
                      color: model.access_mode === 'subscription' || model.access_mode === 'both' ? undefined : 'var(--text-tertiary)'
                    }}
                  >
                    {model.display_name || model.id}
                  </span>
                ))}
                {provider.models.length > 5 && (
                  <span className="text-xs text-text-tertiary">+{provider.models.length - 5} more</span>
                )}
              </div>
            )}
          </div>
        ))}
        
        {providers?.length === 0 && (
          <div className="text-center py-8 text-text-tertiary text-sm">
            No providers configured. Click "Add Provider" to get started.
          </div>
        )}
      </div>

      {/* Create/Edit Form */}
      {(isCreating || editingProvider) && (
        <div className="p-4 border border-border rounded-lg space-y-4">
          <div className="flex items-center justify-between">
            <h4 className="font-medium text-text-primary">
              {editingProvider ? 'Edit Provider' : 'New Provider'}
            </h4>
            <button onClick={resetForm} className="p-1 rounded hover:bg-white/10">
              <X className="w-4 h-4 text-text-secondary" />
            </button>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1">Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="My Provider"
                className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary"
                style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1">Type</label>
              <select
                value={formData.type}
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary"
                style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
              >
                {PROVIDER_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
          </div>

            <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">Base URL</label>
            <input
              type="text"
              value={formData.base_url}
              onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
              placeholder="https://api.example.com/v1"
              className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary font-mono"
              style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1">API Key (optional for local)</label>
              <div className="relative">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  value={formData.api_key}
                  onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                  placeholder="sk-..."
                  className="w-full px-3 py-2 pr-10 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary font-mono"
                  style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-primary"
                >
                  {showApiKey ? <X className="w-4 h-4" /> : <Search className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1">API Key Header</label>
              <input
                type="text"
                value={formData.api_key_header}
                onChange={(e) => setFormData({ ...formData, api_key_header: e.target.value })}
                placeholder="Authorization"
                className="w-full px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary"
                style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
              />
            </div>
          </div>

          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
              <input
                type="checkbox"
                checked={formData.is_local}
                onChange={(e) => setFormData({ ...formData, is_local: e.target.checked })}
                className="rounded"
                style={{ accentColor: 'var(--accent-primary)' }}
              />
              Local Provider
            </label>
            <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
              <input
                type="checkbox"
                checked={formData.is_enabled}
                onChange={(e) => setFormData({ ...formData, is_enabled: e.target.checked })}
                className="rounded"
                style={{ accentColor: 'var(--accent-primary)' }}
              />
              Enabled
            </label>
          </div>

          {/* Subscription Settings */}
          <div className="p-3 bg-purple-500/5 border border-purple-500/20 rounded-lg space-y-3">
            <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
              <input
                type="checkbox"
                checked={formData.subscription.enabled}
                onChange={(e) => setFormData({
                  ...formData,
                  subscription: { ...formData.subscription, enabled: e.target.checked },
                })}
                className="rounded"
                style={{ accentColor: 'var(--accent-purple)' }}
              />
              <Crown className="w-4 h-4 text-purple-400" />
              Has Subscription / PRO Plan
            </label>
            
            {formData.subscription.enabled && (
              <div className="grid grid-cols-2 gap-3 pl-6">
                <div>
                  <label className="block text-xs text-text-tertiary mb-1">Weekly Token Limit</label>
                  <input
                    type="number"
                    value={formData.subscription.weekly_token_limit || ''}
                    onChange={(e) => setFormData({
                      ...formData,
                      subscription: { 
                        ...formData.subscription, 
                        weekly_token_limit: e.target.value ? parseInt(e.target.value) : null 
                      },
                    })}
                    placeholder="Unlimited"
                    className="w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded text-sm text-text-primary"
                    style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
                  />
                </div>
                <div>
                  <label className="block text-xs text-text-tertiary mb-1">Reset Day (1=Mon)</label>
                  <select
                    value={formData.subscription.reset_day}
                    onChange={(e) => setFormData({
                      ...formData,
                      subscription: { ...formData.subscription, reset_day: parseInt(e.target.value) },
                    })}
                    className="w-full px-2 py-1.5 bg-bg-tertiary border border-border rounded text-sm text-text-primary"
                    style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-primary)' }}
                  >
                    {[1,2,3,4,5,6,7].map(d => (
                      <option key={d} value={d}>{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][d-1]}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}
          </div>

          {/* Models Section */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-text-secondary">Models</label>
              {editingProvider && (
                <button
                  onClick={() => handleDiscover(editingProvider.id)}
                  disabled={discovering === editingProvider.id}
                  className="flex items-center gap-1 px-2 py-1 text-xs rounded hover:bg-white/10"
                  style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}
                >
                  <Search className={`w-3 h-3 ${discovering === editingProvider.id ? 'animate-spin' : ''}`} />
                  Auto-Discover
                </button>
              )}
            </div>
            
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {formData.models.map((model, idx) => (
                <div key={idx} className="p-3 rounded-lg space-y-2" style={{ backgroundColor: 'var(--bg-tertiary)' }}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 flex-1">
                      <input
                        type="text"
                        value={model.id}
                        onChange={(e) => updateModel(idx, 'id', e.target.value)}
                        placeholder="model-id"
                        className="flex-1 px-2 py-1 border border-border rounded text-xs text-text-primary font-mono"
                        style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
                      />
                      <input
                        type="text"
                        value={model.display_name}
                        onChange={(e) => updateModel(idx, 'display_name', e.target.value)}
                        placeholder="Display Name"
                        className="flex-1 px-2 py-1 border border-border rounded text-xs text-text-primary"
                        style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
                      />
                    </div>
                    <button
                      onClick={() => removeModel(idx)}
                      className="ml-2 p-1 text-red-400 hover:text-red-300"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                  
                  <div className="flex items-center gap-3 text-xs">
                    <select
                      value={model.access_mode}
                      onChange={(e) => updateModel(idx, 'access_mode', e.target.value)}
                      className="px-2 py-1 border border-border rounded text-text-primary"
                      style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
                    >
                      {ACCESS_MODES.map((m) => (
                        <option key={m.value} value={m.value}>{m.label}</option>
                      ))}
                    </select>
                    
                    <input
                      type="number"
                      value={model.context_window}
                      onChange={(e) => updateModel(idx, 'context_window', parseInt(e.target.value))}
                      placeholder="Context"
                      className="w-24 px-2 py-1 border border-border rounded text-text-primary"
                      style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)' }}
                      title="Context Window"
                    />
                    
                    <label className="flex items-center gap-1 text-text-tertiary cursor-pointer">
                      <input
                        type="checkbox"
                        checked={model.supports_tools}
                        onChange={(e) => updateModel(idx, 'supports_tools', e.target.checked)}
                        className="rounded"
                        style={{ accentColor: 'var(--accent-primary)' }}
                      />
                      Tools
                    </label>
                    
                    <label className="flex items-center gap-1 text-text-tertiary cursor-pointer">
                      <input
                        type="checkbox"
                        checked={model.supports_vision}
                        onChange={(e) => updateModel(idx, 'supports_vision', e.target.checked)}
                        className="rounded"
                        style={{ accentColor: 'var(--accent-primary)' }}
                      />
                      Vision
                    </label>
                  </div>
                </div>
              ))}
              
              <button
                onClick={addModel}
                className="w-full p-2 border border-dashed border-border rounded-lg text-xs text-text-tertiary hover:border-accent hover:text-accent transition-colors"
              >
                + Add Model
              </button>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-border">
            <button onClick={resetForm} className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary">
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={!formData.name || !formData.base_url}
              className="flex items-center gap-2 px-4 py-2 bg-accent text-white rounded-lg text-sm hover:bg-accent/90 disabled:opacity-50"
            >
              <Check className="w-4 h-4" />
              Save Provider
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default ProvidersTab;
