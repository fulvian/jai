import { create } from 'zustand';

interface AvailableModel {
  id: string;
  name: string;
  provider: string;
  context_window: number;
  supports_tools: boolean;
  supports_vision: boolean;
}

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

interface SettingsState {
  isOpen: boolean;
  activeTab: 'models' | 'resources' | 'providers' | 'advanced';
  llmConfig: LLMConfig;
  isLoading: boolean;
  error: string | null;
  openSettings: () => void;
  closeSettings: () => void;
  setActiveTab: (tab: 'models' | 'resources' | 'providers' | 'advanced') => void;
  setLLMConfig: (config: Partial<LLMConfig>) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  resetConfig: () => void;
}

// NOTE: These defaults should match the backend defaults in llm/config.py
// The actual server config is fetched via useLLMConfig() hook
const defaultLLMConfig: LLMConfig = {
  model_primary: 'qwen3.5:9b',
  model_routing: 'qwen3.5:9b',
  model_synthesis: 'qwen3.5:9b',
  model_fallback: 'qwen3.5:9b',
  use_local: true,
  context_overflow_strategy: 'map_reduce',
  default_temperature: 0.3,
  default_max_tokens: 8192,
  context_window: 32768,
};

export const useSettingsStore = create<SettingsState>((set) => ({
  isOpen: false,
  activeTab: 'models',
  llmConfig: defaultLLMConfig,
  isLoading: false,
  error: null,
  openSettings: () => set({ isOpen: true }),
  closeSettings: () => set({ isOpen: false }),
  setActiveTab: (tab) => set({ activeTab: tab }),
  setLLMConfig: (config) => set((state) => ({ llmConfig: { ...state.llmConfig, ...config } })),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error }),
  resetConfig: () => set({ llmConfig: defaultLLMConfig }),
}));

