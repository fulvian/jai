'use client';

import { Info, AlertTriangle, CheckCircle } from 'lucide-react';
import { SETTINGS_LABELS } from './settingsLabels';

interface HardwareRecommendation {
  recommended_max_tokens: number;
  recommended_context_window: number;
  available_ram_gb: number;
  ram_usage_pct: number;
  is_under_pressure: boolean;
  warnings: string[];
}

interface ParameterInputProps {
  labelKey: 'max_tokens' | 'context_window' | 'temperature';
  value: number;
  onChange: (value: number) => void;
  type?: 'number' | 'range';
  min?: number;
  max?: number;
  step?: number;
  recommendations?: HardwareRecommendation;
  disabled?: boolean;
}

export function ParameterInput({
  labelKey,
  value,
  onChange,
  type = 'number',
  min,
  max,
  step = 1,
  recommendations,
  disabled = false,
}: ParameterInputProps) {
  const labelConfig = SETTINGS_LABELS[labelKey];

  const getRecommendedValue = (): number | null => {
    if (!recommendations) return null;
    if (labelKey === 'max_tokens') return recommendations.recommended_max_tokens;
    if (labelKey === 'context_window') return recommendations.recommended_context_window;
    return null;
  };

  const recommendedValue = getRecommendedValue();
  const isOverRecommended = recommendedValue !== null && value > recommendedValue;
  const isAtRecommended = recommendedValue !== null && value === recommendedValue;

  const getWarningMessage = (): string | null => {
    if (!recommendations || !isOverRecommended) return null;
    
    if (labelKey === 'max_tokens') {
      return `Valore alto (${value}). Consigliato: ${recommendedValue} per ${recommendations.available_ram_gb.toFixed(1)}GB RAM disponibili`;
    }
    if (labelKey === 'context_window') {
      return `Finestra ampia (${value.toLocaleString()}). Consigliato: ${recommendedValue.toLocaleString()} token`;
    }
    return null;
  };

  const warningMessage = getWarningMessage();

  const formatValue = (val: number): string => {
    if (labelKey === 'context_window' || labelKey === 'max_tokens') {
      return val.toLocaleString('it-IT');
    }
    return val.toString();
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
            {recommendedValue && (
              <p className="mt-2 pt-2 border-t border-border text-green-400">
                Valore consigliato: {formatValue(recommendedValue)}
              </p>
            )}
          </div>
        </div>
        {isAtRecommended && (
          <CheckCircle className="w-4 h-4 text-green-400" />
        )}
      </div>

      <p className="text-xs text-text-tertiary">{labelConfig.description}</p>

      {type === 'range' ? (
        <div className="space-y-1">
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(parseFloat(e.target.value))}
            className="w-full accent-accent"
          />
          <div className="flex justify-between text-xs text-text-tertiary">
            <span>{min}</span>
            <span className="font-medium text-text-primary">{formatValue(value)}</span>
            <span>{max}</span>
          </div>
        </div>
      ) : (
        <input
          type="number"
          value={value}
          disabled={disabled}
          min={min}
          max={max}
          step={step}
          onChange={(e) => onChange(parseInt(e.target.value, 10) || 0)}
          style={{
            backgroundColor: 'var(--bg-tertiary)',
            color: 'var(--text-primary)',
          }}
          className={`
            w-full px-3 py-2 border rounded-lg text-sm
            focus:outline-none focus:ring-2 focus:ring-accent/50
            ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
            ${isOverRecommended ? 'border-yellow-500/50' : 'border-border'}
          `}
        />
      )}

      {warningMessage && (
        <div className="flex items-center gap-2 text-xs text-yellow-400">
          <AlertTriangle className="w-3 h-3 flex-shrink-0" />
          <span>{warningMessage}</span>
        </div>
      )}

      {recommendations?.warnings && recommendations.warnings.length > 0 && labelKey === 'context_window' && (
        <div className="space-y-1">
          {recommendations.warnings.map((warning, idx) => (
            <div key={idx} className="flex items-center gap-2 text-xs text-yellow-400">
              <AlertTriangle className="w-3 h-3 flex-shrink-0" />
              <span>{warning}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default ParameterInput;
