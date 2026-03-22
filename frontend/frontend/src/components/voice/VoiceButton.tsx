'use client';

import { Mic, MicOff, Volume2, VolumeX } from 'lucide-react';
import { clsx } from 'clsx';
import { motion, AnimatePresence } from 'framer-motion';

interface VoiceButtonProps {
    /** Stato ascolto */
    listening?: boolean;
    /** Stato parlando */
    speaking?: boolean;
    /** Callback click */
    onClick?: () => void;
    /** Disabilitato */
    disabled?: boolean;
    /** Classe aggiuntiva */
    className?: string;
}

export function VoiceButton({
    listening = false,
    speaking = false,
    onClick,
    disabled = false,
    className,
}: VoiceButtonProps) {
    return (
        <div className={clsx('relative', className)}>
            <button
                onClick={onClick}
                disabled={disabled}
                className={clsx(
                    'w-full h-full rounded-full flex items-center justify-center transition-all duration-300',
                    'active:scale-95',
                    listening
                        ? 'text-white glow-danger'
                        : speaking
                            ? 'text-white glow-blue'
                            : 'glass-panel-floating hover:scale-105'
                )}
                style={{
                    background: listening ? 'var(--tahoe-red)' :
                        speaking ? 'var(--tahoe-blue)' :
                            'var(--glass-bg-card)',
                    color: listening || speaking ? 'white' : 'var(--text-secondary)'
                }}
                title={listening ? 'Ferma ascolto' : speaking ? 'Ferma audio' : 'Inizia a parlare'}
            >
                <AnimatePresence mode="wait">
                    {listening ? (
                        <motion.div
                            key="mic"
                            initial={{ scale: 0.8, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.8, opacity: 0 }}
                        >
                            <Mic size={20} />
                        </motion.div>
                    ) : speaking ? (
                        <motion.div
                            key="volume"
                            initial={{ scale: 0.8, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.8, opacity: 0 }}
                        >
                            <Volume2 size={20} className="animate-pulse" />
                        </motion.div>
                    ) : (
                        <motion.div
                            key="idle"
                            initial={{ scale: 0.8, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.8, opacity: 0 }}
                        >
                            <Mic size={20} />
                        </motion.div>
                    )}
                </AnimatePresence>

                {/* Animated Glow Rings for listening */}
                {listening && (
                    <>
                        <motion.div
                            initial={{ scale: 1, opacity: 0.5 }}
                            animate={{ scale: 1.8, opacity: 0 }}
                            transition={{ repeat: Infinity, duration: 1.5 }}
                            className="absolute inset-0 rounded-full pointer-events-none"
                            style={{ border: '2px solid var(--tahoe-red)' }}
                        />
                        <motion.div
                            initial={{ scale: 1, opacity: 0.3 }}
                            animate={{ scale: 1.4, opacity: 0 }}
                            transition={{ repeat: Infinity, duration: 1.5, delay: 0.5 }}
                            className="absolute inset-0 rounded-full pointer-events-none"
                            style={{ border: '1px solid var(--tahoe-red)' }}
                        />
                    </>
                )}

                {/* Animated Glow Rings for speaking */}
                {speaking && (
                    <>
                        <motion.div
                            initial={{ scale: 1, opacity: 0.5 }}
                            animate={{ scale: 1.6, opacity: 0 }}
                            transition={{ repeat: Infinity, duration: 1.2 }}
                            className="absolute inset-0 rounded-full pointer-events-none"
                            style={{ border: '2px solid var(--tahoe-blue)' }}
                        />
                    </>
                )}
            </button>
        </div>
    );
}
