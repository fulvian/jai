'use client';

import { TOGGLE_LABELS } from './settingsLabels';

interface ToggleProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  label?: boolean;
  disabled?: boolean;
  size?: 'sm' | 'md';
}

export function Toggle({ enabled, onChange, label, disabled = false, size = 'md' }: ToggleProps) {
  const sizeClasses = size === 'sm' 
    ? 'h-5 w-9' 
    : 'h-6 w-11';
  
  const knobSize = size === 'sm'
    ? 'h-3.5 w-3.5'
    : 'h-4 w-4';
  
  const translateClass = size === 'sm'
    ? (enabled ? 'translate-x-5' : 'translate-x-0.5')
    : (enabled ? 'translate-x-6' : 'translate-x-1');

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        disabled={disabled}
        onClick={() => !disabled && onChange(!enabled)}
        className={`
          relative inline-flex ${sizeClasses} items-center rounded-full 
          transition-colors duration-200 ease-in-out
          focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-bg-primary
          ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          ${enabled 
            ? 'bg-green-500 focus:ring-green-500' 
            : 'bg-red-500 focus:ring-red-500'
          }
        `}
      >
        <span
          className={`
            inline-block ${knobSize} transform rounded-full bg-white shadow-sm
            transition-transform duration-200 ease-in-out
            ${translateClass}
          `}
        />
      </button>
      {label === true && (
        <span className={`
          text-xs font-semibold uppercase tracking-wide
          ${enabled ? 'text-green-400' : 'text-red-400'}
        `}>
          {enabled ? TOGGLE_LABELS.on : TOGGLE_LABELS.off}
        </span>
      )}
    </div>
  );
}

export default Toggle;
