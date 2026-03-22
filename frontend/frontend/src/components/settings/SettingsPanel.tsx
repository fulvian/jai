'use client';

import { X, Cpu, Settings2, Sliders, Server } from 'lucide-react';
import { useSettingsStore } from '@/stores/useSettingsStore';
import { LLMModelsTab } from './LLMModelsTab';
import { ResourcesTab } from './ResourcesTab';
import { AdvancedTab } from './AdvancedTab';
import { ProvidersTab } from './ProvidersTab';

const TABS = [
  { id: 'models' as const, label: 'LLM Models', icon: Cpu },
  { id: 'resources' as const, label: 'Resources', icon: Settings2 },
  { id: 'providers' as const, label: 'Providers', icon: Server },
  { id: 'advanced' as const, label: 'Advanced', icon: Sliders },
];

export function SettingsPanel() {
  const { isOpen, activeTab, closeSettings, setActiveTab } = useSettingsStore();

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div 
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={closeSettings}
      />
      
      <div className="relative w-full max-w-3xl max-h-[85vh] glass-panel rounded-2xl overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <h2 className="text-lg font-semibold text-text-primary">Settings</h2>
          <button
            onClick={closeSettings}
            className="p-2 rounded-lg hover:bg-white/10 transition-colors"
          >
            <X size={20} className="text-text-secondary" />
          </button>
        </div>

        <div className="flex">
          <div className="w-48 border-r border-white/10 p-2">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors ${
                    activeTab === tab.id
                      ? 'bg-accent text-white'
                      : 'text-text-secondary hover:text-text-primary hover:bg-white/5'
                  }`}
                >
                  <Icon size={18} />
                  {tab.label}
                </button>
              );
            })}
          </div>

          <div className="flex-1 p-6 overflow-y-auto max-h-[calc(85vh-80px)]">
            {activeTab === 'models' && <LLMModelsTab />}
            {activeTab === 'resources' && <ResourcesTab />}
            {activeTab === 'providers' && <ProvidersTab />}
            {activeTab === 'advanced' && <AdvancedTab />}
          </div>
        </div>
      </div>
    </div>
  );
}

export default SettingsPanel;
