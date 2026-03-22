/**
 * TalkModeOverlay Component
 * 
 * Overlay fullscreen per conversazione vocale continua.
 * Design: glassmorphism macOS Tahoe con waveform centrale
 */

'use client';

import { useEffect, useCallback, useState, useRef } from 'react';
import { useVoice } from '@/hooks/useVoice';
import { cn } from '@/lib/utils';
import { X, Mic, Volume2 } from 'lucide-react';
import { WaveformVisualizer } from './WaveformVisualizer';

interface TalkModeOverlayProps {
    /** Visibilità overlay */
    isOpen: boolean;
    /** Callback chiusura */
    onClose: () => void;
    /** Callback quando viene inviato un messaggio */
    onMessage?: (text: string) => Promise<string>;
    /** Classe CSS aggiuntiva */
    className?: string;
}

export function TalkModeOverlay({
    isOpen,
    onClose,
    onMessage,
    className,
}: TalkModeOverlayProps) {
    const [status, setStatus] = useState<'idle' | 'listening' | 'processing' | 'speaking'>('idle');
    const [lastTranscript, setLastTranscript] = useState('');
    const [currentTranscript, setCurrentTranscript] = useState('');
    const isProcessingRef = useRef(false);
    const processMessageRef = useRef<((text: string) => Promise<void>) | null>(null);

    const {
        isListening,
        isSpeaking,
        startListening,
        stopListening,
        speak,
    } = useVoice({
        onTranscript: (text, isFinal) => {
            if (text.trim()) {
                if (isFinal) {
                    // Testo finale - invia immediatamente
                    processMessageRef.current?.(text);
                } else {
                    // Testo interim - mostra all'utente
                    setCurrentTranscript(text);
                }
            }
        },
    });

    // Ref per tracciare il timer di resume listening
    const resumeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Funzione per processare e inviare il messaggio
    const processMessage = useCallback(async (text: string) => {
        if (!text.trim() || isProcessingRef.current) return;

        isProcessingRef.current = true;
        setLastTranscript(text);
        setCurrentTranscript('');
        stopListening();
        setStatus('processing');

        if (onMessage) {
            try {
                const response = await onMessage(text);
                setStatus('speaking');
                await speak(response);
                // Riprendi ascolto dopo risposta - cleanup gestito da useEffect
                resumeTimerRef.current = setTimeout(() => {
                    if (isOpen) {
                        isProcessingRef.current = false;
                        startListening();
                        setStatus('listening');
                    }
                }, 500);
            } catch (error) {
                console.error('Message error:', error);
                isProcessingRef.current = false;
                setStatus('idle');
            }
        } else {
            isProcessingRef.current = false;
        }
    }, [onMessage, isOpen, stopListening, speak, startListening]);

    // Cleanup timer on unmount or when overlay closes
    useEffect(() => {
        return () => {
            if (resumeTimerRef.current) {
                clearTimeout(resumeTimerRef.current);
                resumeTimerRef.current = null;
            }
        };
    }, [isOpen]);

    // Aggiorna il ref ogni volta che processMessage cambia
    useEffect(() => {
        processMessageRef.current = processMessage;
    }, [processMessage]);

    // Auto-start listening when overlay opens
    useEffect(() => {
        if (isOpen) {
            startListening();
            setStatus('listening');
        } else {
            stopListening();
            setStatus('idle');
        }
    }, [isOpen, startListening, stopListening]);

    // Update status based on voice state
    useEffect(() => {
        if (isSpeaking) {
            setStatus('speaking');
        } else if (isListening) {
            setStatus('listening');
        }
    }, [isListening, isSpeaking]);

    // Close on Escape
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') {
                onClose();
            }
        };

        if (isOpen) {
            window.addEventListener('keydown', handleKeyDown);
            return () => window.removeEventListener('keydown', handleKeyDown);
        }
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    const getStatusText = () => {
        switch (status) {
            case 'listening':
                return currentTranscript || 'Sto ascoltando...';
            case 'processing':
                return 'Elaborando...';
            case 'speaking':
                return 'Rispondo...';
            default:
                return 'Premi per parlare';
        }
    };

    const getStatusIcon = () => {
        switch (status) {
            case 'listening':
                return <Mic className="w-8 h-8" />;
            case 'speaking':
                return <Volume2 className="w-8 h-8" />;
            default:
                return <Mic className="w-8 h-8" />;
        }
    };

    return (
        <div
            className={cn(
                'fixed inset-0 z-50 flex flex-col items-center justify-center',
                'glass-overlay',
                className
            )}
            style={{ background: 'rgba(0, 0, 0, 0.7)', backdropFilter: 'blur(40px) saturate(180%)' }}
        >
            {/* Close button - Glass */}
            <button
                onClick={onClose}
                className="absolute top-6 right-6 p-3 rounded-full glass-button-ghost transition-all hover:scale-105"
                style={{ color: 'var(--text-secondary)' }}
            >
                <X className="w-6 h-6" />
            </button>

            {/* Main content */}
            <div className="flex flex-col items-center gap-8">
                {/* Waveform */}
                <div className="relative">
                    <WaveformVisualizer
                        isActive={isListening || isSpeaking}
                        variant={isSpeaking ? 'output' : 'input'}
                        size="lg"
                    />

                    {/* Center icon - Pulsing AI Orb */}
                    <div className={cn(
                        'absolute inset-0 flex items-center justify-center',
                        status === 'listening' && 'animate-ai-pulse',
                        status === 'speaking' && 'animate-ai-pulse'
                    )}
                        style={{
                            color: status === 'listening' ? 'var(--tahoe-red)' :
                                status === 'speaking' ? 'var(--tahoe-blue)' :
                                    'var(--text-tertiary)'
                        }}>
                        {getStatusIcon()}
                    </div>
                </div>

                {/* Status text */}
                <div className="text-center">
                    <p className={cn(
                        'text-lg font-medium'
                    )}
                        style={{
                            color: status === 'listening' ? 'var(--tahoe-red)' :
                                status === 'speaking' ? 'var(--tahoe-blue)' :
                                    status === 'processing' ? 'var(--tahoe-orange)' :
                                        'var(--text-tertiary)'
                        }}>
                        {getStatusText()}
                    </p>

                    {lastTranscript && status !== 'listening' && (
                        <p className="mt-2 text-sm max-w-md" style={{ color: 'var(--text-quaternary)' }}>
                            Tu: "{lastTranscript}"
                        </p>
                    )}
                </div>

                {/* Instructions */}
                <p className="text-xs" style={{ color: 'var(--text-quaternary)' }}>
                    Premi <kbd className="px-1.5 py-0.5 rounded glass-card text-[var(--text-tertiary)]">ESC</kbd> per chiudere
                </p>
            </div>
        </div>
    );
}

export default TalkModeOverlay;
