/**
 * WaveformVisualizer Component
 * 
 * Visualizzatore audio con animazione waveform.
 * Design: cerchi concentrici animati stile Apple Siri
 */

'use client';

import { cn } from '@/lib/utils';

interface WaveformVisualizerProps {
    /** Se l'audio è attivo */
    isActive: boolean;
    /** Tipo di audio (input = mic, output = speaker) */
    variant?: 'input' | 'output';
    /** Dimensione */
    size?: 'sm' | 'md' | 'lg';
    /** Classe CSS aggiuntiva */
    className?: string;
}

const sizeClasses = {
    sm: 'w-16 h-16',
    md: 'w-24 h-24',
    lg: 'w-32 h-32',
};

export function WaveformVisualizer({
    isActive,
    variant = 'input',
    size = 'md',
    className,
}: WaveformVisualizerProps) {
    const baseColor = variant === 'input' ? 'red' : 'blue';

    return (
        <div
            className={cn(
                'relative flex items-center justify-center',
                sizeClasses[size],
                className
            )}
        >
            {/* Outer ring 1 */}
            <div
                className={cn(
                    'absolute inset-0 rounded-full border-2 transition-all duration-300',
                    isActive
                        ? `border-${baseColor}-500/40 animate-ping`
                        : 'border-gray-700/30'
                )}
                style={{ animationDuration: '2s' }}
            />

            {/* Outer ring 2 */}
            <div
                className={cn(
                    'absolute inset-2 rounded-full border-2 transition-all duration-300',
                    isActive
                        ? `border-${baseColor}-500/50 animate-pulse`
                        : 'border-gray-700/40'
                )}
            />

            {/* Outer ring 3 */}
            <div
                className={cn(
                    'absolute inset-4 rounded-full border transition-all duration-300',
                    isActive
                        ? `border-${baseColor}-500/60`
                        : 'border-gray-700/50'
                )}
            />

            {/* Inner glow */}
            <div
                className={cn(
                    'absolute inset-6 rounded-full transition-all duration-300',
                    isActive
                        ? variant === 'input'
                            ? 'bg-gradient-to-br from-red-500/30 to-red-600/20 shadow-lg shadow-red-500/30'
                            : 'bg-gradient-to-br from-blue-500/30 to-blue-600/20 shadow-lg shadow-blue-500/30'
                        : 'bg-gray-800/50'
                )}
            />

            {/* Center circle */}
            <div
                className={cn(
                    'relative w-1/3 h-1/3 rounded-full transition-all duration-200',
                    isActive
                        ? variant === 'input'
                            ? 'bg-red-500 shadow-lg shadow-red-500/50 scale-110'
                            : 'bg-blue-500 shadow-lg shadow-blue-500/50 scale-110'
                        : 'bg-gray-600 scale-100'
                )}
            />

            {/* Bars animation (visible only when active) */}
            {isActive && (
                <div className="absolute inset-0 flex items-center justify-center gap-1">
                    {[...Array(5)].map((_, i) => (
                        <div
                            key={i}
                            className={cn(
                                'w-1 rounded-full',
                                variant === 'input' ? 'bg-red-400' : 'bg-blue-400'
                            )}
                            style={{
                                height: `${20 + Math.random() * 40}%`,
                                animation: `waveform ${0.3 + i * 0.1}s ease-in-out infinite alternate`,
                                animationDelay: `${i * 0.1}s`,
                            }}
                        />
                    ))}
                </div>
            )}

            {/* Keyframes for waveform animation */}
            <style jsx>{`
        @keyframes waveform {
          0% { transform: scaleY(0.3); }
          100% { transform: scaleY(1); }
        }
      `}</style>
        </div>
    );
}

export default WaveformVisualizer;
