'use client';

import { RefreshCw, Cpu, HardDrive, MemoryStick, Activity, RotateCcw } from 'lucide-react';
import { useResources, useLLMStatus, useResetContextTracker, useContextTracker } from '@/hooks/useSettings';

function Gauge({ value, max, label, unit, color = 'accent' }: {
  value: number;
  max: number;
  label: string;
  unit: string;
  color?: string;
}) {
  const percentage = Math.min((value / max) * 100, 100);
  const circumference = 2 * Math.PI * 45;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  return (
    <div className="flex flex-col items-center justify-center mt-3">
      <div className="relative w-28 h-28">
        <svg className="w-28 h-28 transform -rotate-90">
          <circle
            cx="56"
            cy="56"
            r="45"
            stroke="currentColor"
            strokeWidth="8"
            fill="none"
            className="text-bg-tertiary"
          />
          <circle
            cx="56"
            cy="56"
            r="45"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            className={`text-${color} transition-all duration-500`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xs text-text-tertiary">{percentage.toFixed(0)}% used</span>
          <span className="text-sm font-medium text-text-secondary">{unit}</span>
        </div>
      </div>
    </div>
  );
}

function MiniBar({ value, max, label, color = 'bg-accent' }: {
  value: number;
  max: number;
  label: string;
  color?: string;
}) {
  const percentage = Math.min((value / max) * 100, 100);

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-text-secondary">{label}</span>
        <span className="text-text-tertiary">{value.toFixed(1)} / {max.toFixed(1)}</span>
      </div>
      <div className="h-2 bg-bg-tertiary rounded-full overflow-hidden">
        <div
          className={`h-full ${color} transition-all duration-300`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

export function ResourcesTab() {
  const { resources, isLoading: resourcesLoading, error: resourcesError, refresh } = useResources();
  const { status, isLoading: statusLoading } = useLLMStatus();
  const { tracker, isLoading: trackerLoading } = useContextTracker();
  const { reset: resetContext } = useResetContextTracker();

  const isLoading = resourcesLoading || statusLoading;

  if (isLoading && !resources) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="w-6 h-6 animate-spin text-accent" />
        <span className="ml-3 text-text-secondary">Loading resources...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary">System Resources</h3>
        <button
          onClick={refresh}
          className="p-2 rounded-lg hover:bg-white/10 transition-colors"
          title="Refresh"
        >
          <RefreshCw className={`w-4 h-4 text-text-secondary ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {resourcesError && (
        <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
          {resourcesError}
        </div>
      )}

      {resources && (
        <>
          <div className="grid grid-cols-2 gap-4">
            <Gauge
              value={resources.ram.used_gb}
              max={resources.ram.total_gb}
              label="RAM"
              unit="GB"
              color="blue-500"
            />
            <Gauge
              value={resources.cpu.usage_pct}
              max={100}
              label="CPU"
              unit="%"
              color="green-500"
            />
          </div>

          <div className="space-y-4">
            <MiniBar
              value={resources.ram.used_gb}
              max={resources.ram.total_gb}
              label="Memory Usage"
              color="bg-blue-500"
            />
            <MiniBar
              value={resources.swap.used_gb}
              max={resources.ram.total_gb}
              label="Swap Usage"
              color="bg-yellow-500"
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div className="p-3 glass-panel-light rounded-lg text-center">
              <div className="flex items-center justify-center gap-1 mb-1">
                <Activity className="w-4 h-4 text-text-tertiary" />
              </div>
              <div className="text-lg font-bold text-text-primary">
                {resources.cpu.load_avg['1m'].toFixed(2)}
              </div>
              <div className="text-xs text-text-tertiary">Load 1m</div>
            </div>
            <div className="p-3 glass-panel-light rounded-lg text-center">
              <div className="text-lg font-bold text-text-primary">
                {resources.cpu.load_avg['5m'].toFixed(2)}
              </div>
              <div className="text-xs text-text-tertiary">Load 5m</div>
            </div>
            <div className="p-3 glass-panel-light rounded-lg text-center">
              <div className="text-lg font-bold text-text-primary">
                {resources.cpu.load_avg['15m'].toFixed(2)}
              </div>
              <div className="text-xs text-text-tertiary">Load 15m</div>
            </div>
          </div>

          <div className="p-4 glass-panel-light rounded-lg">
            <h4 className="text-sm font-medium text-text-secondary mb-3">LLM Process Memory</h4>
            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-center gap-2">
                <MemoryStick className="w-4 h-4 text-purple-400" />
                <div>
                  <div className="text-sm font-medium text-text-primary">
                    {resources.llm_processes.mlx_gb.toFixed(2)} GB
                  </div>
                  <div className="text-xs text-text-tertiary">MLX Models</div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <HardDrive className="w-4 h-4 text-cyan-400" />
                <div>
                  <div className="text-sm font-medium text-text-primary">
                    {resources.llm_processes.embedding_gb.toFixed(2)} GB
                  </div>
                  <div className="text-xs text-text-tertiary">Embeddings</div>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {tracker && (
        <div className="p-4 glass-panel-light rounded-lg">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-medium text-text-secondary">Context Window Tracker</h4>
            <button
              onClick={resetContext}
              className="flex items-center gap-1 px-2 py-1 text-xs bg-bg-tertiary rounded hover:bg-white/10 transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              Reset
            </button>
          </div>
          <MiniBar
            value={tracker.used_tokens}
            max={tracker.max_tokens}
            label="Context Usage"
            color="bg-purple-500"
          />
          <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
            <div className="text-center">
              <div className="font-medium text-text-primary">{tracker.used_tokens.toLocaleString()}</div>
              <div className="text-text-tertiary">Used</div>
            </div>
            <div className="text-center">
              <div className="font-medium text-text-primary">{tracker.remaining_tokens.toLocaleString()}</div>
              <div className="text-text-tertiary">Remaining</div>
            </div>
            <div className="text-center">
              <div className="font-medium text-text-primary">{tracker.peak_tokens.toLocaleString()}</div>
              <div className="text-text-tertiary">Peak</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ResourcesTab;
