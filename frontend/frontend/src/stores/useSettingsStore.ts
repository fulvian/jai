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

const defaultLLMConfig: LLMConfig = {
  model_primary: 'gpt-4o',
  model_routing: 'gpt-4o-mini',
  model_synthesis: 'gpt-4o',
  model_fallback: 'gpt-4o-mini',
  use_local: false,
  context_overflow_strategy: 'truncate',
  default_temperature: 0.7,
  default_max_tokens: 4096,
  context_window: 128000,
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

