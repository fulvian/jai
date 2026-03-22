/**
 * ChatPanel - Main chat interface component.
 */

'use client';

import { useEffect, useRef, useState, KeyboardEvent, useCallback, useMemo } from 'react';
import { Send, Square, Paperclip, X, FileText, Image as ImageIcon, Loader2, Mic, BookOpen } from 'lucide-react';
import NextImage from 'next/image';
import { useChatStore } from '@/stores/useChatStore';
import { useChat } from '@/hooks/useChat';
import { MessageBubble } from './MessageBubble';

import { ActivityTimeline } from './ActivityTimeline';
import { VoiceButton } from '../voice/VoiceButton';
import { TalkModeOverlay } from '../voice/TalkModeOverlay';
import TemplatePromptBar from './TemplatePromptBar';
import PromptEditorModal from './PromptEditorModal';
import { GraphExplorer } from './GraphExplorer';
import PromptLibrary from './PromptLibrary';
import { useRelatedSessions, type SessionSearchResult } from '@/hooks/useSessionGraph';
import { cn } from '@/lib/utils';
import { useIsMobile } from '@/hooks/useIsMobile';
import type { Message, TemplatePrompt } from '@/types/chat';
import { API_CONFIG } from '@/lib/config';

const API_URL = API_CONFIG.gatewayUrl;
const ACCEPTED_TYPES = ['application/pdf', 'image/jpeg', 'image/png', 'image/bmp'];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

interface AttachedFile {
    name: string;
    type: string;
    extractedText?: string;
    processing: boolean;
    error?: string;
}

export function ChatPanel() {
    const [input, setInput] = useState('');
    const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
    const [isTalkMode, setIsTalkMode] = useState(false);
    const [lastVoiceResponse, setLastVoiceResponse] = useState<string | null>(null);
    const [hasMounted, setHasMounted] = useState(false);
    const [isPromptLibraryOpen, setIsPromptLibraryOpen] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const isMobile = useIsMobile();

    // Select only needed state to prevent unnecessary re-renders during streaming
    const currentSessionId = useChatStore((s) => s.currentSessionId);
    const sessions = useChatStore((s) => s.sessions);
    
    // Direct selector for current session - avoids re-renders from other sessions' updates
    const currentSession = useChatStore((s) => 
        currentSessionId ? s.sessionStates[currentSessionId] : null
    );
    
    // Get actions from store (stable references)
    const clearErrorAction = useChatStore((s) => s.clearError);
    const deleteMessageAction = useChatStore((s) => s.deleteMessage);
    const submitFeedbackAction = useChatStore((s) => s.submitFeedback);
    const updateSessionConfigAction = useChatStore((s) => s.updateSessionConfig);
    
    // Destructure with fallbacks to empty session data
    const { messages: rawMessages = [], pendingMessage = '', pendingThinking = '', isStreaming: isCurrentSessionStreaming = false, error = null, isThinking = false, statusMessage = null, activitySteps = [] } = currentSession || {};

    const { sendMessage: sendSSEMessage, retryMessage, editMessage, abort: stopStream } = useChat();



    const clearError = () => clearErrorAction(currentSessionId || undefined);


    // Risolvi config sessione corrente
    const currentSessionMeta = sessions.find((s) => s.session_id === currentSessionId);
    const sessionConfig = currentSessionMeta?.config;
    const isTemplateSession = sessionConfig?.type === 'template';
    const templatePrompts = sessionConfig?.prompts ?? [];

    const [isPromptEditorOpen, setIsPromptEditorOpen] = useState(false);

    // Graph hooks
    const { related } = useRelatedSessions(currentSessionId);

    // Hydration guard: render empty on server, then show real data after mount
    const messages = hasMounted ? rawMessages : [];

    useEffect(() => {
        setHasMounted(true);
    }, []);

    // Auto-scroll to bottom on new messages
    useEffect(() => {
        if (!hasMounted) return;

        const timer = setTimeout(() => {
            if (messagesEndRef.current) {
                messagesEndRef.current.scrollIntoView({
                    behavior: messages.length <= 1 ? 'auto' : 'smooth',
                    block: 'end'
                });
            }
        }, 100);
        return () => clearTimeout(timer);
    }, [messages.length, pendingMessage, pendingThinking, hasMounted, activitySteps.length]);

    // Focus input on mount
    useEffect(() => {
        if (hasMounted && window.innerWidth > 768) {
            inputRef.current?.focus();
        }
    }, [hasMounted]);

    const processFile = useCallback(async (file: File) => {
        if (!ACCEPTED_TYPES.includes(file.type)) {
            setAttachedFiles(prev => [...prev, {
                name: file.name,
                type: file.type,
                processing: false,
                error: 'Tipo non supportato',
            }]);
            return;
        }

        if (file.size > MAX_FILE_SIZE) {
            setAttachedFiles(prev => [...prev, {
                name: file.name,
                type: file.type,
                processing: false,
                error: 'File troppo grande (max 10MB)',
            }]);
            return;
        }

        setAttachedFiles(prev => [...prev, {
            name: file.name,
            type: file.type,
            processing: true,
        }]);

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(`${API_URL}/api/upload`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) throw new Error(`Upload fallito: ${response.status}`);

            const result = await response.json();

            setAttachedFiles(prev => prev.map(f =>
                f.name === file.name
                    ? { ...f, processing: false, extractedText: result.content }
                    : f
            ));
        } catch (err) {
            setAttachedFiles(prev => prev.map(f =>
                f.name === file.name
                    ? { ...f, processing: false, error: (err as Error).message }
                    : f
            ));
        }
    }, []);

    const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files) return;
        Array.from(files).forEach(processFile);
        if (fileInputRef.current) fileInputRef.current.value = '';
    }, [processFile]);

    const removeFile = useCallback((name: string) => {
        setAttachedFiles(prev => prev.filter(f => f.name !== name));
    }, []);

    const handleSubmit = async (e?: React.FormEvent) => {
        e?.preventDefault();

        const attachmentText = attachedFiles
            .filter(f => f.extractedText)
            .map(f => `\n\n[Allegato: ${f.name}]\n${f.extractedText}`)
            .join('');

        const fullMessage = input.trim() + attachmentText;

        if (!fullMessage || isCurrentSessionStreaming) return;

        setInput('');
        if (inputRef.current) {
            inputRef.current.style.height = isMobile ? '38px' : '48px';
        }

        // Use SSE for streaming (SOTA 2026)
        await sendSSEMessage(fullMessage);
    };


    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
        setInput(e.target.value);
        e.target.style.height = 'auto';
        e.target.style.height = Math.min(e.target.scrollHeight, 144) + 'px';
    }, []); // setInput from useState is stable - no dependency needed

    const getFileIcon = (type: string) => {
        if (type === 'application/pdf') return <FileText className="w-3 h-3" />;
        if (type.startsWith('image/')) return <ImageIcon className="w-3 h-3" />;
        return <FileText className="w-3 h-3" />;
    };

    const pendingMessageObj: Message | null = useMemo(() => {
        if (!hasMounted || !pendingMessage) return null;
        return {
            id: 'pending',
            role: 'assistant',
            content: pendingMessage,
            timestamp: new Date(),
            isStreaming: true,
        };
    }, [hasMounted, pendingMessage]);

    const hasContent = input.trim() || attachedFiles.some(f => f.extractedText);
    const isProcessing = attachedFiles.some(f => f.processing);

    // Show status from store (SSE updates it)
    const effectiveStatus = statusMessage || (isThinking ? 'Sto pensando...' : null);


    return (
        <div className="flex flex-col h-full">
            {/* Error banner */}
            {error && (
                <div className="bg-red-500/10 border border-red-500/30 text-red-400 px-4 py-2 text-sm flex justify-between items-center">
                    <span>Errore: {error}</span>
                    <button onClick={clearError} className="text-red-400 hover:text-red-300">✕</button>
                </div>
            )}
            {/* Status indicator (WebSocket) */}
            {effectiveStatus && (
                <div className="bg-blue-500/5 backdrop-blur-md border-b border-blue-500/10 px-4 py-2 flex items-center gap-2 overflow-hidden">
                    <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse flex-shrink-0" />
                    <span className="text-xs text-blue-400 font-light truncate">
                        {effectiveStatus}
                    </span>
                </div>
            )}

            {/* Messages area */}
            <div className="flex-1 overflow-y-auto p-4">
                {messages.length === 0 && !pendingMessage ? (
                    <div className="flex flex-col items-center justify-center h-full text-center px-6">
                        <div className="relative mb-8">
                            <div className="absolute inset-0 bg-blue-500/20 blur-[60px] rounded-full animate-pulse" />
                            <NextImage
                                src="/jAI_logo.png"
                                alt="jAI"
                                width={120}
                                height={120}
                                className="relative rounded-full welcome-logo shadow-2xl border border-white/10"
                            />
                        </div>
                        <h2 className="text-3xl font-bold mb-3 tracking-tight bg-gradient-to-b from-white to-white/60 bg-clip-text text-transparent">jAI</h2>
                        <p className="text-white/40 text-[0.9rem] max-w-[280px] leading-relaxed font-light">
                            Powered by Me4BrAIn.<br />Scrivi o allega un documento per iniziare!
                        </p>
                    </div>
                ) : (
                    <div className="flex flex-col gap-4">
                        {messages.map((message, index) => (
                            <MessageBubble
                                key={message.id}
                                message={message}
                                messageIndex={index}
                                onDelete={(idx) => {
                                    if (currentSessionId) {
                                        deleteMessageAction(currentSessionId, idx);
                                    }
                                }}
                                onEdit={(idx, newContent) => {
                                    editMessage(idx, newContent);
                                }}
                                onRetry={(idx) => {
                                    retryMessage(idx);
                                }}
                                onFeedback={(idx, score) => {
                                    if (currentSessionId) {
                                        submitFeedbackAction(currentSessionId, idx, score);
                                    }
                                }}
                            />
                        ))}
                        <ActivityTimeline />
                        {pendingMessageObj && (
                            <MessageBubble
                                message={pendingMessageObj}
                                messageIndex={-1}
                                isStreaming
                            />
                        )}
                        <div ref={messagesEndRef} />
                    </div>
                )}
            </div>

            {/* Graph Exploration Bar */}
            {currentSessionId && messages.length > 0 && (
                <div className="chat-graph-bar">
                    <GraphExplorer
                        sessionId={currentSessionId}
                        onNodeClick={(node) => {
                            if (node.nodeType === 'session') {
                                useChatStore.getState().loadSession(node.id);
                            }
                        }}
                    />
                    {related.length > 0 && (
                        <div className="chat-related-sessions">
                            <span className="chat-related-label">Sessioni correlate:</span>
                            {related.slice(0, 3).map((r) => (
                                <button
                                    key={r.sessionId}
                                    className="chat-related-chip"
                                    onClick={() => useChatStore.getState().loadSession(r.sessionId)}
                                    title={r.title}
                                >
                                    💬 {r.title?.slice(0, 25) || r.sessionId.slice(0, 8)}
                                    <span className="chat-related-score">
                                        {Math.round(r.score * 100)}%
                                    </span>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Input area - Floating Glass Bar */}
            <div className={cn("p-4", isMobile ? "mobile-input-container" : "border-t border-[var(--glass-border-subtle)] space-y-3")} style={!isMobile ? { background: 'rgba(28, 28, 30, 0.6)' } : {}}>
                {/* Template Prompt Bar */}
                {isTemplateSession && templatePrompts.length > 0 && (
                    <TemplatePromptBar
                        prompts={templatePrompts}
                        onPromptSelect={(prompt) => {
                            setInput((prev) => prev + (prev ? '\n' : '') + prompt.content);
                            inputRef.current?.focus();
                        }}
                        onPromptDirectSend={(prompt) => {
                            sendSSEMessage(prompt.content);
                        }}
                        onManagePrompts={() => setIsPromptEditorOpen(true)}
                    />
                )}

                {/* Prompt Editor Modal */}
                {isTemplateSession && (
                    <PromptEditorModal
                        isOpen={isPromptEditorOpen}
                        prompts={templatePrompts}
                        onClose={() => setIsPromptEditorOpen(false)}
                        onSave={(updatedPrompts) => {
                            if (currentSessionId) {
                                updateSessionConfigAction(currentSessionId, { prompts: updatedPrompts });
                            }
                        }}
                    />
                )}

                {/* Attached files */}
                {attachedFiles.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                        {attachedFiles.map((file) => (
                            <div
                                key={file.name}
                                className={cn(
                                    'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs backdrop-blur-sm',
                                    file.error
                                        ? 'bg-[var(--tahoe-red)]/20 text-[var(--tahoe-red)] border border-[var(--tahoe-red)]/30'
                                        : file.processing
                                            ? 'bg-[var(--tahoe-blue)]/20 text-[var(--tahoe-blue)] border border-[var(--tahoe-blue)]/30 animate-ai-pulse'
                                            : 'bg-[var(--tahoe-green)]/20 text-[var(--tahoe-green)] border border-[var(--tahoe-green)]/30'
                                )}
                            >
                                {file.processing ? (
                                    <Loader2 className="w-3 h-3 animate-spin" />
                                ) : (
                                    getFileIcon(file.type)
                                )}
                                <span className="max-w-[100px] truncate">{file.name}</span>
                                {!file.processing && (
                                    <button onClick={() => removeFile(file.name)} className="hover:opacity-70">
                                        <X className="w-3 h-3" />
                                    </button>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {/* Input row */}
                <form onSubmit={handleSubmit} className={cn("flex gap-2", isMobile ? "mobile-input-pill" : "")}>
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept={ACCEPTED_TYPES.join(',')}
                        onChange={handleFileChange}
                        className="hidden"
                        multiple
                        disabled={isCurrentSessionStreaming}
                    />

                    <div className="flex items-center">
                        <button
                            type="button"
                            onClick={() => fileInputRef.current?.click()}
                            disabled={isCurrentSessionStreaming}
                            className={cn(
                                isMobile ? "mobile-action-btn" : "p-3 rounded-xl glass-button-ghost",
                                "disabled:opacity-50 transition-all duration-200"
                            )}
                        >
                            <Paperclip className="w-5 h-5" />
                        </button>

                        {isMobile && (
                            <button
                                type="button"
                                onClick={() => setIsPromptLibraryOpen(true)}
                                disabled={isCurrentSessionStreaming}
                                className="mobile-action-btn"
                                title="Libreria Prompt"
                            >
                                <BookOpen className="w-5 h-5" />
                            </button>
                        )}
                    </div>

                    {!isMobile && (
                        <button
                            type="button"
                            onClick={() => setIsPromptLibraryOpen(true)}
                            disabled={isCurrentSessionStreaming}
                            className="p-3 rounded-xl glass-button-ghost disabled:opacity-50 transition-all duration-200"
                            title="Libreria Prompt"
                        >
                            <BookOpen className="w-5 h-5" />
                        </button>
                    )}

                    {/* Text input */}
                    <textarea
                        ref={inputRef}
                        value={input}
                        onChange={handleInputChange}
                        onKeyDown={handleKeyDown}
                        placeholder={isCurrentSessionStreaming ? 'Attendere...' : (isMobile ? 'Messaggio...' : 'Scrivi un messaggio...')}
                        disabled={isCurrentSessionStreaming}
                        rows={1}
                        className={cn(
                            "flex-1 px-2 py-3 bg-transparent border-none focus:ring-0 resize-none overflow-y-auto",
                            "placeholder:text-white/30 text-[0.95rem]",
                            !isMobile && "glass-input rounded-xl px-4",
                            "disabled:opacity-50 transition-all duration-200"
                        )}
                        style={{ minHeight: isMobile ? '38px' : '48px', maxHeight: '144px' }}
                    />

                    <div className="flex items-center gap-2">
                        {isCurrentSessionStreaming ? (
                            <button
                                type="button"
                                onClick={stopStream}
                                className={cn(
                                    "flex-center rounded-full",
                                    isMobile ? "w-10 h-10 bg-red-500/20 text-red-400" : "px-4 py-3 rounded-xl bg-red-500/80 text-white",
                                    "transition-all duration-200"
                                )}
                            >
                                <Square className="w-4 h-4 fill-current" />
                                {!isMobile && "Stop"}
                            </button>
                        ) : (
                            <button
                                type="submit"
                                disabled={!hasContent || isProcessing}
                                className={cn(
                                    isMobile ? "mobile-send-btn" : "px-4 py-3 rounded-xl glass-button flex items-center gap-2",
                                    "disabled:opacity-50 transition-all duration-200"
                                )}
                            >
                                <Send className={isMobile ? "w-5 h-5" : "w-4 h-4"} />
                                {!isMobile && "Invia"}
                            </button>
                        )}

                        {!isMobile && (
                            <VoiceButton
                                onClick={() => setIsTalkMode(true)}
                                disabled={isCurrentSessionStreaming}
                                className="w-12 h-12"
                            />
                        )}

                        {isMobile && !hasContent && !isCurrentSessionStreaming && (
                            <VoiceButton
                                onClick={() => setIsTalkMode(true)}
                                disabled={isCurrentSessionStreaming}
                                className="mobile-action-btn"
                            />
                        )}
                    </div>
                </form>

                {/* Prompt Library Modal */}
                <PromptLibrary
                    isOpen={isPromptLibraryOpen}
                    onClose={() => setIsPromptLibraryOpen(false)}
                    onUsePrompt={(content) => {
                        setInput((prev) => prev + (prev ? '\n' : '') + content);
                        setIsPromptLibraryOpen(false);
                        inputRef.current?.focus();
                    }}
                    currentSessionId={currentSessionId}
                />

                {/* Talk Mode Overlay */}
                <TalkModeOverlay
                    isOpen={isTalkMode}
                    onClose={() => setIsTalkMode(false)}
                    onMessage={async (text) => {
                        await sendSSEMessage(text);
                        const targetSessionId = useChatStore.getState().currentSessionId;

                        const startTime = Date.now();
                        const maxWait = 60000;

                        await new Promise<void>((resolve) => {
                            const checkInterval = setInterval(() => {
                                const state = useChatStore.getState();
                                const sessionData = targetSessionId ? state.sessionStates[targetSessionId] : null;
                                if (Date.now() - startTime > maxWait) {
                                    clearInterval(checkInterval);
                                    resolve();
                                    return;
                                }
                                if (sessionData && !sessionData.isStreaming && sessionData.messages.length > 0) {
                                    clearInterval(checkInterval);
                                    resolve();
                                }
                            }, 200);
                        });

                        const state = useChatStore.getState();
                        const sessionData = targetSessionId ? state.sessionStates[targetSessionId] : null;
                        const lastMessage = sessionData?.messages.filter(m => m.role === 'assistant').pop();
                        return lastMessage?.content || 'Scusa, non ho ricevuto una risposta.';
                    }}
                />
            </div>
        </div>
    );
}
