import useSWR, { mutate } from 'swr';
import { API_CONFIG } from '@/lib/config';

// Backend uses snake_case
interface LLMConfig {
  model_primary: string;
  model_routing: string;
  model_synthesis: string;
  model_fallback: string;
  use_local: boolean;
  context_overflow_strategy: 'map_reduce' | 'truncate' | 'cloud_fallback';
  default_temperature: number;
  default_max_tokens: number;
  context_window: number;
  available_models?: AvailableModel[];
  enable_streaming?: boolean;
  enable_caching?: boolean;
  enable_metrics?: boolean;
}

interface AvailableModel {
  id: string;
  name: string;
  provider: string;
  context_window: number;
  supports_tools: boolean;
  supports_vision: boolean;
}

interface LLMConfigUpdate {
  model_primary?: string;
  model_routing?: string;
  model_synthesis?: string;
  model_fallback?: string;
  use_local_tool_calling?: boolean;
  context_overflow_strategy?: 'map_reduce' | 'truncate' | 'cloud_fallback';
  default_temperature?: number;
  default_max_tokens?: number;
  context_window_size?: number;
  enable_streaming?: boolean;
  enable_caching?: boolean;
  enable_metrics?: boolean;
}

interface LLMConfigUpdateResponse {
  status: string;
  updates_applied: string[];
  verified_config?: {
    context_overflow_strategy?: string;
    model_primary?: string;
    model_routing?: string;
    model_synthesis?: string;
    model_fallback?: string;
    use_local_tool_calling?: boolean;
  };
  note: string;
}

interface ResourceStats {
  ram: {
    total_gb: number;
    used_gb: number;
    available_gb: number;
    usage_pct: number;
  };
  swap: {
    used_gb: number;
  };
  cpu: {
    usage_pct: number;
    load_avg: {
      '1m': number;
      '5m': number;
      '15m': number;
    };
  };
  gpu_metal_usage: Record<string, unknown> | null;
  llm_processes: {
    mlx_gb: number;
    embedding_gb: number;
  };
}

interface ContextTrackerStatus {
  max_tokens: number;
  used_tokens: number;
  peak_tokens: number;
  remaining_tokens: number;
  usage_pct: number;
  component_breakdown: Record<string, number>;
}

interface HardwareRecommendations {
  recommended_max_tokens: number;
  recommended_context_window: number;
  available_ram_gb: number;
  ram_usage_pct: number;
  is_under_pressure: boolean;
  resource_level: string;
  warnings: string[];
  recommendations: string[];
}

interface LLMStatus {
  local: {
    available: boolean;
    model_loaded: string;
    inference_speed_tps: number | null;
    process_memory_gb: number;
  };
  cloud: {
    available: boolean;
    provider: string;
    base_url: string;
  };
  resources: {
    ram_usage_pct: number;
    swap_gb: number;
    level: string;
    under_pressure: boolean;
  };
}

const fetcher = async (url: string) => {
  const res = await fetch(`${API_CONFIG.gatewayUrl}${url}`);
  if (!res.ok) throw new Error('Failed to fetch');
  return res.json();
};

export function useResources() {
  const { data, error, isLoading } = useSWR<ResourceStats>(
    '/api/monitoring/resources',
    fetcher,
    { refreshInterval: 5000 }
  );

  return {
    resources: data,
    isLoading,
    error: error?.message,
    refresh: () => mutate('/api/monitoring/resources'),
  };
}

export function useLLMConfig() {
  const { data, error, isLoading, mutate: swrMutate } = useSWR<LLMConfig>(
    '/api/config/llm/current',
    fetcher,
    { revalidateOnFocus: true }
  );

  return {
    config: data,
    isLoading,
    error: error?.message,
    refresh: () => swrMutate(),
  };
}

export function useLLMStatus() {
  const { data, error, isLoading, mutate: swrMutate } = useSWR<LLMStatus>(
    '/api/config/llm/status',
    fetcher,
    { refreshInterval: 10000 }
  );

  return {
    status: data,
    isLoading,
    error: error?.message,
    refresh: () => swrMutate(),
  };
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

    // Force revalidation of the config cache after update
    // Use mutate with undefined to clear cache and trigger re-fetch
    await mutate('/api/config/llm/current', undefined, { revalidate: true });

    return response;
  };

  return { updateConfig };
}

export function useResetContextTracker() {
  const reset = async () => {
    const res = await fetch(`${API_CONFIG.gatewayUrl}/api/config/llm/context-tracker/reset`, {
      method: 'POST',
    });
    
    if (!res.ok) throw new Error('Failed to reset context tracker');
    
    mutate('/api/config/llm/status');
    return res.json();
  };

  return { reset };
}

export function useAvailableModels() {
  const { data, error, isLoading } = useSWR<AvailableModel[]>(
    '/api/config/llm/models',
    fetcher
  );

  return {
    models: data ?? [],  // Return the array directly since data is the array of LLMModelInfo objects
    isLoading,
    error: error?.message,
  };
}

export function useContextTracker() {
  const { data, error, isLoading, mutate: swrMutate } = useSWR<ContextTrackerStatus>(
    '/api/monitoring/context-tracker',
    fetcher,
    { refreshInterval: 10000 }
  );

  return {
    tracker: data,
    isLoading,
    error: error?.message,
    refresh: () => swrMutate(),
  };
}

export function useHardwareRecommendations() {
  const { data, error, isLoading, mutate: swrMutate } = useSWR<HardwareRecommendations>(
    '/api/config/llm/recommendations/hardware',
    fetcher,
    { refreshInterval: 30000 }
  );

  return {
    recommendations: data,
    isLoading,
    error: error?.message,
    refresh: () => swrMutate(),
  };
}

// Provider hooks
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
  subscription?: {
    enabled: boolean;
    weekly_token_limit?: number;
    reset_day?: number;
    tokens_used_this_week?: number;
  };
}

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

export function useProviders() {
  const { data, error, isLoading, mutate: swrMutate } = useSWR<Provider[]>(
    '/api/providers',
    fetcher
  );

  return {
    providers: data ?? [],
    isLoading,
    error: error?.message,
    refresh: () => swrMutate(),
  };
}

export function useCreateProvider() {
  const createProvider = async (provider: Partial<Provider>) => {
    const res = await fetch(`${API_CONFIG.gatewayUrl}/api/providers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(provider),
    });
    if (!res.ok) throw new Error('Failed to create provider');
    mutate('/api/providers');
    return res.json();
  };
  return { createProvider };
}

export function useUpdateProvider() {
  const updateProvider = async (id: string, data: Partial<Provider>) => {
    const res = await fetch(`${API_CONFIG.gatewayUrl}/api/providers/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to update provider');
    mutate('/api/providers');
    return res.json();
  };
  return { updateProvider };
}

export function useDeleteProvider() {
  const deleteProvider = async (id: string) => {
    const res = await fetch(`${API_CONFIG.gatewayUrl}/api/providers/${id}`, {
      method: 'DELETE',
    });
    if (!res.ok) throw new Error('Failed to delete provider');
    mutate('/api/providers');
    return res.json();
  };
  return { deleteProvider };
}

export function useTestProvider() {
  const testProvider = async (id: string) => {
    const res = await fetch(`${API_CONFIG.gatewayUrl}/api/providers/${id}/test`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to test provider');
    mutate('/api/providers');
    return res.json();
  };
  return { testProvider };
}

export function useDiscoverModels() {
  const discoverModels = async (id: string) => {
    const res = await fetch(`${API_CONFIG.gatewayUrl}/api/providers/${id}/discover`);
    if (!res.ok) throw new Error('Failed to discover models');
    return res.json();
  };
  return { discoverModels };
}

export function useProviderSubscription() {
  const getSubscription = async (id: string) => {
    const res = await fetch(`${API_CONFIG.gatewayUrl}/api/providers/${id}/subscription`);
    if (!res.ok) throw new Error('Failed to get subscription');
    return res.json();
  };
  return { getSubscription };
}

export function useResetSubscription() {
  const resetSubscription = async (id: string) => {
    const res = await fetch(`${API_CONFIG.gatewayUrl}/api/providers/${id}/subscription/reset`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to reset subscription');
    mutate('/api/providers');
    return res.json();
  };
  return { resetSubscription };
}

export function useResetLLMConfig() {
  const resetConfig = async () => {
    const res = await fetch(`${API_CONFIG.gatewayUrl}/api/config/llm/reset`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to reset LLM config');
    // Revalidate the config cache after reset
    mutate('/api/config/llm/current');
    return res.json();
  };
  return { resetConfig };
}
