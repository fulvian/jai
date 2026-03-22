'use client';

import { useState, useRef, useCallback, KeyboardEvent } from 'react';
import { Send, Paperclip, X, FileText, Image as ImageIcon, Loader2, Sparkles } from 'lucide-react';
import { useChat } from '@/hooks/useChat';
import { useChatStore } from '@/stores/useChatStore';
import { useVoice } from '@/hooks/useVoice';
import { VoiceButton } from '../voice/VoiceButton';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';
import { API_CONFIG } from '@/lib/config';

const API_URL = API_CONFIG.gatewayUrl;
const ACCEPTED_TYPES = ['application/pdf', 'image/jpeg', 'image/png', 'image/bmp'];

export function ChatInput() {
    const [input, setInput] = useState('');
    const [attachedFiles, setAttachedFiles] = useState<any[]>([]);
    const inputRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const currentSession = useChatStore((s) => s.getCurrentSession());
    const { isStreaming, isThinking } = currentSession;
    const { sendMessage } = useChat();

    const { isListening, interimTranscript, toggleListening } = useVoice({
        onTranscript: (text, isFinal) => {
            if (isFinal) {
                setInput(prev => prev + (prev && !prev.endsWith(' ') ? ' ' : '') + text);
            }
        }
    });

    const handleSubmit = async (e?: React.FormEvent) => {
        e?.preventDefault();
        if (!input.trim() || isStreaming) return;
        const msg = input.trim();
        setInput('');
        if (inputRef.current) inputRef.current.style.height = 'auto';
        await sendMessage(msg);
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        setInput(e.target.value);
        e.target.style.height = 'auto';
        e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`;
    };

    return (
        <div className="relative w-full px-4 max-w-4xl mx-auto">
            {/* Floating Glass Bar */}
            <div className={clsx(
                'glass-vibrant rounded-[28px] flex flex-col transition-all duration-500 shadow-[0_20px_50px_rgba(0,0,0,0.4)] border-white/10 overflow-hidden',
                (isListening || isThinking) && 'ring-2 ring-blue-500/30'
            )}>
                <div className="flex items-end gap-2 p-2.5">
                    {/* Attach */}
                    <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        className="btn-icon w-10 h-10 hover:bg-white/10"
                    >
                        <Paperclip size={20} className="text-[var(--text-tertiary)]" />
                    </button>
                    <input ref={fileInputRef} type="file" className="hidden" multiple />

                    {/* Textarea */}
                    <div className="relative flex-1 py-1.5 ml-2">
                        <textarea
                            ref={inputRef}
                            rows={1}
                            value={input}
                            onChange={handleInputChange}
                            onKeyDown={handleKeyDown}
                            placeholder={isListening ? 'Ti ascolto...' : 'Chiedi a jAI...'}
                            className="w-full bg-transparent border-none focus:ring-0 p-0 text-[0.95rem] resize-none max-h-[200px] py-1 placeholder:text-white/20 text-white font-light leading-relaxed"
                            style={{ height: '24px' }}
                        />
                    </div>

                    {/* Action Group */}
                    <div className="flex items-center gap-2 pr-1">
                        <AnimatePresence>
                            {isThinking && (
                                <motion.div
                                    initial={{ scale: 0, opacity: 0 }}
                                    animate={{ scale: 1, opacity: 1 }}
                                    exit={{ scale: 0, opacity: 0 }}
                                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-blue-500/20 text-blue-400 text-[10px] font-bold tracking-widest uppercase border border-blue-500/20 shadow-sm"
                                >
                                    <Sparkles size={12} className="animate-pulse" />
                                    <span>Pensando</span>
                                </motion.div>
                            )}
                        </AnimatePresence>

                        <VoiceButton
                            className="w-10 h-10"
                            listening={isListening}
                            onClick={toggleListening}
                        />

                        <button
                            onClick={handleSubmit}
                            disabled={!input.trim() || isStreaming}
                            className={clsx(
                                'w-10 h-10 rounded-full flex-center transition-all duration-300',
                                input.trim()
                                    ? 'bg-white text-black shadow-lg scale-100 hover:scale-105 active:scale-95'
                                    : 'text-white/20 bg-white/5 opacity-50 scale-90'
                            )}
                        >
                            <Send size={18} />
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
