/**
 * MessageBubble component for rendering chat messages.
 * Includes hover toolbar: Copy, Delete, Edit (user only), Retry (user only).
 */

'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Copy, Check, Trash2, Pencil, RefreshCw, X, Send, ChevronUp, ChevronDown, Brain, ChevronRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';
import type { Message } from '@/types/chat';

interface MessageBubbleProps {
    message: Message;
    messageIndex: number;
    isStreaming?: boolean;
    onDelete?: (index: number) => void;
    onEdit?: (index: number, newContent: string) => void;
    onRetry?: (index: number) => void;
    onFeedback?: (index: number, score: 1 | -1 | 0) => void;
}

export const MessageBubble = React.memo(function MessageBubble({
    message,
    messageIndex,
    isStreaming,
    onDelete,
    onEdit,
    onRetry,
    onFeedback,
}: MessageBubbleProps) {
    const isUser = message.role === 'user';
    const [copied, setCopied] = useState(false);
    const [copiedThinking, setCopiedThinking] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editContent, setEditContent] = useState(message.content);
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const deleteConfirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Cleanup timers on unmount
    useEffect(() => {
        return () => {
            if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
            if (deleteConfirmTimerRef.current) clearTimeout(deleteConfirmTimerRef.current);
        };
    }, []);

    // Auto-resize textarea and focus when entering edit mode
    useEffect(() => {
        if (isEditing && textareaRef.current) {
            textareaRef.current.focus();
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
        }
    }, [isEditing]);

    const handleCopy = useCallback(async () => {
        const textToCopy = message.content;
        if (!textToCopy) return;

        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(textToCopy);
            } else {
                const textArea = document.createElement('textarea');
                textArea.value = textToCopy;
                textArea.style.position = 'fixed';
                textArea.style.left = '-999999px';
                textArea.style.top = '-999999px';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                const successful = document.execCommand('copy');
                document.body.removeChild(textArea);
                if (!successful) throw new Error('execCommand copy failed');
            }
            setCopied(true);
            if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
            copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
        } catch (err) {
            console.error('[MessageBubble] Failed to copy:', err);
        }
    }, [message.content]);

    const handleCopyThinking = useCallback(async () => {
        const textToCopy = message.thinking;
        if (!textToCopy) return;

        try {
            if (navigator.clipboard && window.isSecureContext) {
                await navigator.clipboard.writeText(textToCopy);
            } else {
                const textArea = document.createElement('textarea');
                textArea.value = textToCopy;
                textArea.style.position = 'fixed';
                textArea.style.left = '-999999px';
                textArea.style.top = '-999999px';
                document.body.appendChild(textArea);
                textArea.focus();
                textArea.select();
                const successful = document.execCommand('copy');
                document.body.removeChild(textArea);
                if (!successful) throw new Error('execCommand copy failed');
            }
            setCopiedThinking(true);
            if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
            copyTimerRef.current = setTimeout(() => setCopiedThinking(false), 2000);
        } catch (err) {
            console.error('[MessageBubble] Failed to copy thinking:', err);
        }
    }, [message.thinking]);

    const handleDelete = useCallback(() => {
        if (showDeleteConfirm) {
            onDelete?.(messageIndex);
            setShowDeleteConfirm(false);
        } else {
            setShowDeleteConfirm(true);
            // Auto-dismiss after 3 seconds
            if (deleteConfirmTimerRef.current) clearTimeout(deleteConfirmTimerRef.current);
            deleteConfirmTimerRef.current = setTimeout(() => setShowDeleteConfirm(false), 3000);
        }
    }, [messageIndex, onDelete, showDeleteConfirm]);

    const handleEditStart = useCallback(() => {
        setEditContent(message.content);
        setIsEditing(true);
    }, [message.content]);

    const handleEditCancel = useCallback(() => {
        setIsEditing(false);
        setEditContent(message.content);
    }, [message.content]);

    const handleEditSubmit = useCallback(() => {
        if (editContent.trim() && editContent !== message.content) {
            onEdit?.(messageIndex, editContent.trim());
        }
        setIsEditing(false);
    }, [editContent, message.content, messageIndex, onEdit]);

    const handleRetry = useCallback(() => {
        onRetry?.(messageIndex);
    }, [messageIndex, onRetry]);

    const handleTextareaKeyDown = useCallback(
        (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleEditSubmit();
            }
            if (e.key === 'Escape') {
                handleEditCancel();
            }
        },
        [handleEditSubmit, handleEditCancel]
    );

    // ── Edit mode UI ─────────────────────────────────────────────────
    if (isEditing) {
        return (
            <div className="flex w-full justify-end">
                <div className="max-w-[80%] w-full px-4 py-3 bubble-user">
                    <textarea
                        ref={textareaRef}
                        value={editContent}
                        onChange={(e) => {
                            setEditContent(e.target.value);
                            // Auto-resize
                            e.target.style.height = 'auto';
                            e.target.style.height = `${e.target.scrollHeight}px`;
                        }}
                        onKeyDown={handleTextareaKeyDown}
                        className="w-full bg-transparent text-white resize-none outline-none text-sm leading-relaxed"
                        rows={2}
                        placeholder="Modifica il messaggio..."
                    />
                    <div className="flex items-center justify-end gap-2 mt-2 pt-2 border-t border-white/20">
                        <button
                            onClick={handleEditCancel}
                            className="flex items-center gap-1 px-3 py-1.5 text-xs text-white/70 hover:text-white rounded-md hover:bg-white/10 transition-colors"
                        >
                            <X className="w-3 h-3" />
                            Annulla
                        </button>
                        <button
                            onClick={handleEditSubmit}
                            disabled={!editContent.trim() || editContent === message.content}
                            className={cn(
                                'flex items-center gap-1 px-3 py-1.5 text-xs rounded-md transition-colors',
                                editContent.trim() && editContent !== message.content
                                    ? 'bg-white/20 text-white hover:bg-white/30'
                                    : 'bg-white/5 text-white/30 cursor-not-allowed'
                            )}
                        >
                            <Send className="w-3 h-3" />
                            Salva e Riprova
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    // ── Toolbar helper ────────────────────────────────────────────────
    const renderToolbar = (position: 'top' | 'bottom') => (
        <div
            className={cn(
                `absolute ${position === 'top' ? '-top-8' : '-bottom-8'} flex items-center gap-0.5 p-1 rounded-lg transition-all duration-200`,
                'opacity-0 group-hover:opacity-100 pointer-events-none group-hover:pointer-events-auto',
                'bg-[var(--glass-bg)] backdrop-blur-md border border-[var(--glass-border)] shadow-lg',
                isUser ? 'right-0' : 'left-0'
            )}
        >
            {/* Copy */}
            <button
                onClick={handleCopy}
                className={cn(
                    'p-1.5 rounded-md transition-colors',
                    'hover:bg-[var(--glass-tint-medium)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]',
                    copied && 'text-[var(--tahoe-green)]'
                )}
                title="Copia"
            >
                {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
            </button>

            {/* Edit (user only) */}
            {isUser && (
                <button
                    onClick={handleEditStart}
                    className="p-1.5 rounded-md transition-colors hover:bg-[var(--glass-tint-medium)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
                    title="Modifica"
                >
                    <Pencil className="w-3.5 h-3.5" />
                </button>
            )}

            {/* Retry (user only) */}
            {isUser && (
                <button
                    onClick={handleRetry}
                    className="p-1.5 rounded-md transition-colors hover:bg-[var(--glass-tint-medium)] text-[var(--text-tertiary)] hover:text-[var(--tahoe-blue)]"
                    title="Riprova"
                >
                    <RefreshCw className="w-3.5 h-3.5" />
                </button>
            )}

            {/* Upvote/Downvote (assistant only) */}
            {!isUser && (
                <>
                    <button
                        onClick={() => onFeedback?.(messageIndex, message.feedback?.score === 1 ? 0 : 1)}
                        className={cn(
                            'p-1.5 rounded-md transition-colors',
                            message.feedback?.score === 1
                                ? 'text-orange-400 bg-orange-400/15'
                                : 'hover:bg-[var(--glass-tint-medium)] text-[var(--text-tertiary)] hover:text-orange-400'
                        )}
                        title="Upvote"
                    >
                        <ChevronUp className="w-3.5 h-3.5" />
                    </button>
                    <button
                        onClick={() => onFeedback?.(messageIndex, message.feedback?.score === -1 ? 0 : -1)}
                        className={cn(
                            'p-1.5 rounded-md transition-colors',
                            message.feedback?.score === -1
                                ? 'text-blue-400 bg-blue-400/15'
                                : 'hover:bg-[var(--glass-tint-medium)] text-[var(--text-tertiary)] hover:text-blue-400'
                        )}
                        title="Downvote"
                    >
                        <ChevronDown className="w-3.5 h-3.5" />
                    </button>
                </>
            )}

            {/* Delete */}
            <button
                onClick={handleDelete}
                className={cn(
                    'p-1.5 rounded-md transition-colors',
                    showDeleteConfirm
                        ? 'bg-red-500/20 text-red-400'
                        : 'hover:bg-[var(--glass-tint-medium)] text-[var(--text-tertiary)] hover:text-red-400'
                )}
                title={showDeleteConfirm ? 'Conferma eliminazione' : 'Elimina'}
            >
                <Trash2 className="w-3.5 h-3.5" />
            </button>
        </div>
    );

    // ── Normal rendering ─────────────────────────────────────────────
    return (
        <div
            className={cn(
                'flex w-full group',
                isUser ? 'justify-end' : 'justify-start'
            )}
        >
            <div
                className={cn(
                    'relative max-w-[80%] px-4 py-3',
                    isUser ? 'bubble-user' : 'bubble-assistant',
                    isStreaming && 'animate-ai-pulse'
                )}
            >
                {/* Hover toolbar — top */}
                {!isStreaming && renderToolbar('top')}

                {/* Message content - Rendered as Markdown */}
                <div
                    className="prose prose-sm dark:prose-invert max-w-none overflow-hidden [&>*:first-child]:mt-0 [&>*:last-child]:mb-0"
                    style={{ overflowWrap: 'break-word', wordBreak: 'break-word' }}
                >
                    {isUser ? (
                        <p className="whitespace-pre-wrap break-words leading-relaxed m-0">
                            {message.content}
                        </p>
                    ) : (
                        <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                                a: ({ href, children }) => (
                                    <a
                                        href={href}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-primary hover:underline font-medium"
                                        style={{ wordBreak: 'break-all' }}
                                    >
                                        {children}
                                    </a>
                                ),
                                p: ({ children }) => (
                                    <p className="my-2 leading-relaxed break-words">{children}</p>
                                ),
                                h1: ({ children }) => (
                                    <h1 className="text-lg font-bold mt-4 mb-2 border-b border-white/10 pb-1">{children}</h1>
                                ),
                                h2: ({ children }) => (
                                    <h2 className="text-base font-bold mt-3 mb-2">{children}</h2>
                                ),
                                h3: ({ children }) => (
                                    <h3 className="text-sm font-semibold mt-2 mb-1">{children}</h3>
                                ),
                                table: ({ children }) => (
                                    <div className="overflow-x-auto my-3 -mx-1 px-1 rounded-lg">
                                        <table className="min-w-full text-sm border-collapse border border-white/10 rounded-lg">
                                            {children}
                                        </table>
                                    </div>
                                ),
                                thead: ({ children }) => (
                                    <thead className="bg-white/5">{children}</thead>
                                ),
                                th: ({ children }) => (
                                    <th className="text-left text-xs font-semibold px-3 py-2 border-b border-white/10 whitespace-nowrap">{children}</th>
                                ),
                                td: ({ children }) => (
                                    <td className="text-sm px-3 py-2 border-b border-white/5" style={{ maxWidth: '300px', wordBreak: 'break-word' }}>{children}</td>
                                ),
                                tr: ({ children }) => (
                                    <tr className="hover:bg-white/5 transition-colors">{children}</tr>
                                ),
                                hr: () => (
                                    <hr className="my-4 border-white/10" />
                                ),
                                ul: ({ children }) => (
                                    <ul className="list-disc list-inside my-2 space-y-1">{children}</ul>
                                ),
                                ol: ({ children }) => (
                                    <ol className="list-decimal list-inside my-2 space-y-1">{children}</ol>
                                ),
                                li: ({ children }) => (
                                    <li className="text-sm">{children}</li>
                                ),
                                code: ({ children }) => (
                                    <code className="bg-background/50 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
                                ),
                                blockquote: ({ children }) => (
                                    <blockquote className="border-l-2 border-primary/50 pl-3 my-2 text-sm italic text-[var(--text-secondary)]">{children}</blockquote>
                                ),
                                strong: ({ children }) => (
                                    <strong className="font-semibold text-foreground">{children}</strong>
                                ),
                            }}
                        >
                            {message.content}
                        </ReactMarkdown>
                    )}
                    {isStreaming && (
                        <span className="inline-flex gap-1 ml-2 animate-ai-typing">
                            <span className="w-1.5 h-1.5 rounded-full bg-[var(--tahoe-blue)]"></span>
                            <span className="w-1.5 h-1.5 rounded-full bg-[var(--tahoe-purple)]"></span>
                            <span className="w-1.5 h-1.5 rounded-full bg-[var(--tahoe-teal)]"></span>
                        </span>
                    )}
                </div>

                {/* 🧠 Thinking/Reasoning Section - Stile Claude/ChatGPT */}
                {!isUser && message.thinking && message.thinking.length > 0 && (
                    <details className="mt-3 group/thinking">
                        <summary className="flex items-center gap-2 cursor-pointer text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors select-none py-1.5 px-2 -mx-2 rounded-md hover:bg-[var(--glass-surface)]/50">
                            <ChevronRight className="w-3 h-3 transition-transform group-open/thinking:rotate-90" />
                            <Brain className="w-3.5 h-3.5 text-[var(--tahoe-purple)]" />
                            <span className="font-medium">Ragionamento</span>
                            <span className="text-[var(--text-tertiary)]/60">
                                ({message.thinking.length.toLocaleString('it-IT')} caratteri)
                            </span>
                        </summary>
                        <div className="relative mt-2 p-3 bg-[var(--glass-surface)]/30 rounded-lg border border-dashed border-[var(--glass-border)] text-sm text-[var(--text-secondary)] italic whitespace-pre-wrap break-words leading-relaxed max-h-64 overflow-y-auto">
                            {message.thinking}
                            {/* Copy button for thinking */}
                            <button
                                onClick={(e) => {
                                    e.preventDefault();
                                    e.stopPropagation();
                                    handleCopyThinking();
                                }}
                                className={cn(
                                    'absolute top-2 right-2 p-1.5 rounded-md transition-all',
                                    'opacity-0 group-hover/thinking:opacity-100',
                                    'hover:bg-[var(--glass-tint-medium)]',
                                    copiedThinking 
                                        ? 'text-[var(--tahoe-green)]' 
                                        : 'text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'
                                )}
                                title={copiedThinking ? 'Copiato!' : 'Copia ragionamento'}
                            >
                                {copiedThinking ? (
                                    <Check className="w-3.5 h-3.5" />
                                ) : (
                                    <Copy className="w-3.5 h-3.5" />
                                )}
                            </button>
                        </div>
                    </details>
                )}

                {/* Sources */}
                {message.sources && message.sources.length > 0 && (
                    <div className="mt-3 pt-2 border-t border-border/50">
                        <p className="text-xs text-muted-foreground mb-1">Fonti:</p>
                        <div className="flex flex-wrap gap-1">
                            {message.sources.map((source, idx) => (
                                <a
                                    key={idx}
                                    href={source.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-xs bg-background/50 px-2 py-0.5 rounded hover:underline"
                                >
                                    {source.title || source.domain || `Fonte ${idx + 1}`}
                                </a>
                            ))}
                        </div>
                    </div>
                )}

                {/* Tools used */}
                {message.toolsUsed && message.toolsUsed.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                        {message.toolsUsed.map((tool, idx) => (
                            <span
                                key={idx}
                                className="text-xs bg-primary/20 text-primary px-2 py-0.5 rounded-full"
                            >
                                🔧 {tool}
                            </span>
                        ))}
                    </div>
                )}

                {/* Timestamp */}
                <p className="text-[10px] text-muted-foreground/60 mt-1 text-right" suppressHydrationWarning>
                    {new Date(message.timestamp).toLocaleTimeString('it-IT', {
                        hour: '2-digit',
                        minute: '2-digit',
                    })}
                </p>

                {/* Hover toolbar — bottom */}
                {!isStreaming && renderToolbar('bottom')}
            </div>
        </div>
    );
});
