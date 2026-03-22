/**
 * useChat hook for SSE streaming.
 *
 * Handles:
 * - SSE connection with fetch + ReadableStream
 * - Token parsing and store updates
 * - Abort support
 * - Per-session isolation: captures sessionId at send time
 * - Message management: retry, edit
 */

'use client';

import { useCallback, useRef, useEffect } from 'react';
import { useChatStore } from '@/stores/useChatStore';
import type { StreamChunk } from '@/types/chat';
import type { ActivityStep } from '@/stores/useChatStore';

import { API_CONFIG } from '@/lib/config';

const API_URL = API_CONFIG.gatewayUrl;

export function useChat() {
    // FIX Issue #1: Per-session AbortController map for cross-session isolation
    // Each session gets its own controller so aborting Tab1 doesn't cancel Tab2
    const abortControllersRef = useRef<Map<string, AbortController>>(new Map());

    // Cleanup: abort all pending requests on unmount
    useEffect(() => {
        return () => {
            abortControllersRef.current.forEach((controller, sessionId) => {
                controller.abort();
                // Finish streaming state for each session
                useChatStore.getState().finishStreaming(sessionId);
            });
            abortControllersRef.current.clear();
        };
    }, []);

    const {
        currentSessionId,
        sessionStates,
        setSessionId,
        addUserMessage,
        startStreaming,
        appendToken,
        setSources,
        finishStreaming,
        setError,
        fetchSessions,
        addActivity,
        updateLastActivity,
        truncateFromIndex,
        appendThinking,
        clearThinking,
        setThinking,
    } = useChatStore();

    // Derive isStreaming for the current session
    const currentSession = currentSessionId ? sessionStates[currentSessionId] : null;
    const isStreaming = currentSession?.isStreaming ?? false;

    /**
     * Generic SSE stream reader. Shared by sendMessage, retryMessage, editMessage.
     * Reads SSE chunks and dispatches them to the store for the target session.
     */
    const readSSEStream = useCallback(async (
        response: Response,
        targetSessionId: string,
        signal: AbortSignal
    ) => {
        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.slice(6);
                    if (data === '[DONE]') continue;

                    try {
                        const chunk: StreamChunk = JSON.parse(data);

                        switch (chunk.type) {
                            case 'session':
                                if (chunk.session_id) {
                                    setSessionId(chunk.session_id);
                                }
                                break;

                            case 'status':
                                addActivity({
                                    type: 'thinking',
                                    message: chunk.content || chunk.message || 'Elaborazione...',
                                    icon: '🔄',
                                    status: 'active',
                                }, targetSessionId);
                                break;

                            case 'thinking':
                                setThinking(true, targetSessionId);
                                if (chunk.content) {
                                    // DEBUG: Log thinking chunk size
                                    console.log(`[useChat] 🧠 SSE thinking: ${chunk.content.length} chars, preview: ${chunk.content.substring(0, 50)}...`);
                                    appendThinking(chunk.content, targetSessionId);
                                } else {
                                    addActivity({
                                        type: 'thinking',
                                        message: chunk.message || 'Sto analizzando...',
                                        icon: chunk.icon || '🔍',
                                        status: 'active',
                                    }, targetSessionId);
                                }
                                break;

                            case 'plan':
                                updateLastActivity({ status: 'done' }, targetSessionId);
                                addActivity({
                                    type: 'plan',
                                    message: chunk.content || chunk.message || 'Piano pronto',
                                    icon: chunk.icon || '✅',
                                    status: 'done',
                                    areas: chunk.areas,
                                }, targetSessionId);
                                break;

                            case 'step_start':
                                addActivity({
                                    type: 'step_start',
                                    message: chunk.content || chunk.message || 'Esecuzione...',
                                    icon: chunk.icon || '🔄',
                                    status: 'active',
                                    step: chunk.step,
                                    total: chunk.total,
                                }, targetSessionId);
                                break;

                            case 'step_thinking':
                                updateLastActivity({
                                    message: chunk.content || chunk.message || 'Sto ragionando...',
                                    icon: chunk.icon || '🧠',
                                }, targetSessionId);
                                break;

                            case 'step_complete':
                                updateLastActivity({
                                    type: 'step_complete',
                                    message: chunk.content || chunk.message || 'Completato',
                                    icon: '✅',
                                    status: 'done',
                                }, targetSessionId);
                                break;

                            case 'step_error':
                                updateLastActivity({
                                    type: 'step_error',
                                    message: chunk.content || chunk.message || 'Errore',
                                    icon: '⚠️',
                                    status: 'error',
                                }, targetSessionId);
                                break;

                            case 'synthesizing':
                                addActivity({
                                    type: 'synthesizing',
                                    message: chunk.content || chunk.message || 'Sto preparando la risposta...',
                                    icon: chunk.icon || '💬',
                                    status: 'active',
                                }, targetSessionId);
                                break;

                            case 'content':
                                if (chunk.content) {
                                    appendToken(chunk.content, targetSessionId);
                                }
                                break;

                            case 'sources':
                                if (chunk.sources) {
                                    setSources(chunk.sources, targetSessionId);
                                }
                                break;

                            case 'done':
                                updateLastActivity({ status: 'done' }, targetSessionId);
                                finishStreaming(targetSessionId);
                                fetchSessions();
                                break;

                            case 'error':
                                setError(chunk.error || 'Unknown error', targetSessionId);
                                finishStreaming(targetSessionId);
                                break;
                        }
                    } catch (e) {
                        console.warn('Failed to parse SSE chunk:', data, e);
                    }
                }
            }
        }
    }, [setSessionId, addActivity, updateLastActivity, appendToken, setSources, finishStreaming, setError, fetchSessions]);

    /**
     * Send a new message
     */
    const sendMessage = useCallback(async (message: string) => {
        if (!message.trim()) return;

        let targetSessionId = currentSessionId;

        // Lazy Session Creation: if no current session, create one first.
        if (!targetSessionId) {
            targetSessionId = await useChatStore.getState().createNewSession();
            if (!targetSessionId) {
                console.error('Failed to create session on the fly');
                return;
            }
        }

        const targetSession = useChatStore.getState().sessionStates[targetSessionId];
        if (targetSession?.isStreaming) return;

        addUserMessage(message, targetSessionId);
        clearThinking(targetSessionId);
        startStreaming(targetSessionId);

        try {
            const controller = new AbortController();
            abortControllersRef.current.set(targetSessionId, controller);

            const response = await fetch(`${API_URL}/api/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                },
                body: JSON.stringify({
                    message,
                    session_id: targetSessionId,
                }),
                signal: controller.signal,
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            await readSSEStream(response, targetSessionId, controller.signal);
            finishStreaming(targetSessionId);
            fetchSessions();
        } catch (error) {
            if ((error as Error).name === 'AbortError') {
                finishStreaming(targetSessionId);
            } else {
                setError((error as Error).message, targetSessionId);
            }
        } finally {
            abortControllersRef.current.delete(targetSessionId);
        }
    }, [currentSessionId, addUserMessage, startStreaming, finishStreaming, setError, fetchSessions, readSSEStream]);

    /**
     * Retry a message at the given index.
     * Truncates from the index, then re-sends the query via the retry endpoint.
     */
    const retryMessage = useCallback(async (messageIndex: number) => {
        const targetSessionId = currentSessionId;
        if (!targetSessionId) return;

        const targetSession = useChatStore.getState().sessionStates[targetSessionId];
        if (targetSession?.isStreaming) return;

        // Truncate locally: keep user message, remove only the response after it
        truncateFromIndex(targetSessionId, messageIndex + 1);
        startStreaming(targetSessionId);

        try {
            const controller = new AbortController();
            abortControllersRef.current.set(targetSessionId, controller);

            const response = await fetch(
                `${API_URL}/api/chat/sessions/${targetSessionId}/retry/${messageIndex}`,
                {
                    method: 'POST',
                    headers: { 'Accept': 'text/event-stream' },
                    signal: controller.signal,
                }
            );

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            await readSSEStream(response, targetSessionId, controller.signal);
            finishStreaming(targetSessionId);
            fetchSessions();
        } catch (error) {
            if ((error as Error).name === 'AbortError') {
                finishStreaming(targetSessionId);
            } else {
                setError((error as Error).message, targetSessionId);
            }
        } finally {
            abortControllersRef.current.delete(targetSessionId);
        }
    }, [currentSessionId, truncateFromIndex, startStreaming, finishStreaming, setError, fetchSessions, readSSEStream]);

    /**
     * Edit a message and re-execute it.
     * Updates the turn content, truncates subsequent messages, and re-streams.
     */
    const editMessage = useCallback(async (messageIndex: number, newContent: string) => {
        const targetSessionId = currentSessionId;
        if (!targetSessionId) return;

        const targetSession = useChatStore.getState().sessionStates[targetSessionId];
        if (targetSession?.isStreaming) return;

        // Truncate locally: keep only messages up to and including the edited one
        truncateFromIndex(targetSessionId, messageIndex + 1);

        // Update the local message content immediately
        const state = useChatStore.getState();
        const session = state.sessionStates[targetSessionId];
        if (session) {
            const updatedMessages = [...session.messages];
            if (updatedMessages[messageIndex]) {
                updatedMessages[messageIndex] = {
                    ...updatedMessages[messageIndex],
                    content: newContent,
                };
                useChatStore.setState((s) => ({
                    sessionStates: {
                        ...s.sessionStates,
                        [targetSessionId]: {
                            ...s.sessionStates[targetSessionId],
                            messages: updatedMessages,
                        },
                    },
                }));
            }
        }

        startStreaming(targetSessionId);

        try {
            const controller = new AbortController();
            abortControllersRef.current.set(targetSessionId, controller);

            const response = await fetch(
                `${API_URL}/api/chat/sessions/${targetSessionId}/turns/${messageIndex}`,
                {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'text/event-stream',
                    },
                    body: JSON.stringify({ content: newContent }),
                    signal: controller.signal,
                }
            );

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            await readSSEStream(response, targetSessionId, controller.signal);
            finishStreaming(targetSessionId);
            fetchSessions();
        } catch (error) {
            if ((error as Error).name === 'AbortError') {
                finishStreaming(targetSessionId);
            } else {
                setError((error as Error).message, targetSessionId);
            }
        } finally {
            abortControllersRef.current.delete(targetSessionId);
        }
    }, [currentSessionId, truncateFromIndex, startStreaming, finishStreaming, setError, fetchSessions, readSSEStream]);

    const abort = useCallback(() => {
        // FIX Issue #1: Only abort the CURRENT session, not all sessions
        const sessionId = useChatStore.getState().currentSessionId;
        if (sessionId) {
            const controller = abortControllersRef.current.get(sessionId);
            if (controller) {
                controller.abort();
                abortControllersRef.current.delete(sessionId);
            }
            finishStreaming(sessionId);
        }
    }, [finishStreaming]);

    return {
        sendMessage,
        retryMessage,
        editMessage,
        abort,
        isStreaming,
    };
}
