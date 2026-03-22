'use client';

import { useEffect, useCallback, useState, useRef } from 'react';
import { useChatStore } from '@/stores/useChatStore';
import { useCanvasStore } from '@/stores/useCanvasStore';
import { GatewayClient, type ConnectionState } from '@/lib/gateway-client';
import type { ChatResponse } from '@persan/shared';
import type { StreamChunk } from '@/types/chat';
import { CanvasBlockData } from '@/components/canvas/CanvasBlock';

import { API_CONFIG } from '@/lib/config';

const GATEWAY_URL = API_CONFIG.websocketUrl;

export function useGateway() {
    const clientRef = useRef<GatewayClient | null>(null);
    const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');

    // ✅ SOTA 2026: Strict isolation via Active Streams Map
    // Tracks ALL sessions currently receiving a stream to allow multi-tab resilience
    const activeStreamsRef = useRef<Map<string, boolean>>(new Map());

    // Track which session is streaming via WS (captured at send time)
    const streamingSessionRef = useRef<string | null>(null);

    const {
        currentSessionId,
        sessionStates,
        setSessionId,
        addUserMessage,
        startStreaming,
        appendToken,
        finishStreaming,
        setError,
        addActivity,
        updateLastActivity,
        setSources,
        fetchSessions,
        setThinking,
        setStatusMessage: setStatusMsg,
        appendThinking,
        clearThinking,
    } = useChatStore();

    const { pushBlock, updateBlock, removeBlock } = useCanvasStore();

    // Drive isStreaming for the current session
    const currentSession = currentSessionId ? sessionStates[currentSessionId] : null;
    const isStreaming = currentSession?.isStreaming ?? false;

    // Keep currentSessionId in a ref to avoid re-triggering the useEffect loop
    const sessionIdRef = useRef(currentSessionId);
    useEffect(() => {
        sessionIdRef.current = currentSessionId;
    }, [currentSessionId]);

    // Initialize connection and handle Push Notifications
    useEffect(() => {
        const client = new GatewayClient({
            url: GATEWAY_URL,
            onStateChange: setConnectionState,
            onReconnected: () => {
                // Dopo riconnessione WS, re-iscriviti a tutte le sessioni attive in questa tab
                const activeIds = Array.from(activeStreamsRef.current.keys());
                if (activeIds.length > 0) {
                    client.resubscribe(activeIds);
                }
            },
        });

        clientRef.current = client;
        client.connect();

        // --- Push Notification Setup ---
        const setupPush = async () => {
            if ('serviceWorker' in navigator && 'PushManager' in window) {
                try {
                    const reg = await navigator.serviceWorker.register('/sw.js');
                    if (Notification.permission === 'default') {
                        await Notification.requestPermission();
                    }
                    if (Notification.permission === 'granted') {
                        const subscription = await reg.pushManager.subscribe({
                            userVisibleOnly: true,
                            applicationServerKey: process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY,
                        });
                        await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/push/subscribe`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                userId: 'default',
                                subscription,
                            }),
                        });
                    }
                } catch (err) {
                    console.error('❌ Failed to setup Push:', err);
                }
            }
        };

        setupPush();

        // Handlers for unified WebSocket stream
        const unsubResponse = client.on<StreamChunk>('chat:response', (chunk) => {
            // ✅ STRICT: session_id is now mandatory (enforced by backend Fase 1)
            const incomingSessionId = chunk.session_id;

            if (!incomingSessionId) {
                console.warn('Dropped chunk: missing session_id', chunk);
                return;
            }

            // ✅ ISOLATION: Accept ONLY if this specific tab initiated the stream
            if (!activeStreamsRef.current.has(incomingSessionId)) {
                return;
            }

            const targetSessionId = incomingSessionId;


            // Map chunk types to Store actions (Mirror logic from useChat.ts)
            switch (chunk.type) {
                case 'thinking':
                    setThinking(true, targetSessionId);
                    if (chunk.content) {
                        appendThinking(chunk.content, targetSessionId);
                    } else {
                        setStatusMsg(chunk.message || 'Sto pensando...', targetSessionId);
                    }
                    break;

                case 'status':
                    setThinking(true, targetSessionId);
                    setStatusMsg(chunk.content || null, targetSessionId);
                    break;

                case 'plan':
                    setThinking(false, targetSessionId);
                    setStatusMsg(null, targetSessionId);
                    updateLastActivity({ status: 'done' }, targetSessionId);
                    addActivity({
                        type: 'plan',
                        message: chunk.message || 'Piano pronto',
                        icon: chunk.icon || '✅',
                        status: 'done',
                        areas: chunk.areas,
                    }, targetSessionId);
                    break;

                case 'step_start':
                    setThinking(false, targetSessionId);
                    addActivity({
                        type: 'step_start',
                        message: chunk.message || 'Esecuzione...',
                        icon: chunk.icon || '🔄',
                        status: 'active',
                        step: chunk.step,
                        total: chunk.total,
                    }, targetSessionId);
                    break;

                case 'step_thinking':
                    updateLastActivity({
                        message: chunk.message || 'Sto ragionando...',
                        icon: chunk.icon || '🧠',
                    }, targetSessionId);
                    break;

                case 'step_complete':
                    updateLastActivity({
                        type: 'step_complete',
                        message: chunk.message || 'Completato',
                        icon: '✅',
                        status: 'done',
                    }, targetSessionId);
                    break;

                case 'step_error':
                    updateLastActivity({
                        type: 'step_error',
                        message: chunk.message || 'Errore',
                        icon: '⚠️',
                        status: 'error',
                    }, targetSessionId);
                    break;

                case 'synthesizing':
                    setThinking(false, targetSessionId);
                    setStatusMsg(null, targetSessionId);
                    // Start synthesis with a fresh activity step
                    addActivity({
                        type: 'synthesizing',
                        message: chunk.message || 'Sto preparando la risposta...',
                        icon: chunk.icon || '💬',
                        status: 'active',
                    }, targetSessionId);
                    break;

                case 'content':
                    setThinking(false, targetSessionId);
                    setStatusMsg(null, targetSessionId);
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
                    setThinking(false, targetSessionId);
                    setStatusMsg(null, targetSessionId);
                    updateLastActivity({ status: 'done' }, targetSessionId);
                    finishStreaming(targetSessionId);
                    fetchSessions();

                    // Cleanup tracking
                    activeStreamsRef.current.delete(targetSessionId);
                    if (streamingSessionRef.current === targetSessionId) {
                        streamingSessionRef.current = null;
                    }
                    break;

                case 'error':
                    setThinking(false, targetSessionId);
                    setStatusMsg(null, targetSessionId);
                    setError(chunk.error || 'Errore sconosciuto', targetSessionId);
                    finishStreaming(targetSessionId);

                    // Cleanup tracking
                    activeStreamsRef.current.delete(targetSessionId);
                    if (streamingSessionRef.current === targetSessionId) {
                        streamingSessionRef.current = null;
                    }
                    break;

                default:
                    // Fallback per vecchi mapping o chunk non previsti
                    if (chunk.content && !chunk.type) {
                        appendToken(chunk.content, targetSessionId);
                    }
                    break;
            }
        });

        // Legacy/Generic Thinking handler (if sent separately)
        const unsubThinking = client.on<{ sessionId?: string }>('chat:thinking', (data) => {
            if (data.sessionId) setThinking(true, data.sessionId);
        });

        // Canvas Handlers
        const unsubCanvasPush = client.on<CanvasBlockData>('canvas:push', (data) => pushBlock(data));
        const unsubCanvasUpdate = client.on<{ id: string; data: Partial<CanvasBlockData> }>('canvas:update', (data) => updateBlock(data.id, data.data));
        const unsubCanvasRemove = client.on<{ id: string }>('canvas:remove', (data) => removeBlock(data.id));

        const unsubError = client.on<{ message: string; sessionId?: string }>('error', (data) => {
            const targetId = data.sessionId || Array.from(activeStreamsRef.current.keys())[0] || sessionIdRef.current;
            if (targetId) {
                setThinking(false, targetId);
                setStatusMsg(null, targetId);
                setError(data.message, targetId);
                finishStreaming(targetId);
                // Cleanup tracking
                activeStreamsRef.current.delete(targetId);
            }
            streamingSessionRef.current = null;
        });

        return () => {
            unsubResponse();
            unsubThinking();
            unsubCanvasPush();
            unsubCanvasUpdate();
            unsubCanvasRemove();
            unsubError();
            client.disconnect();
        };
    }, [setSessionId, appendToken, finishStreaming, setError, addActivity, updateLastActivity, setSources, fetchSessions, pushBlock, updateBlock, removeBlock, setThinking, setStatusMsg]);

    // ✅ PHASE 5: Auto-Recovery on Mount
    useEffect(() => {
        const savedSessionId = useChatStore.getState().currentSessionId;
        if (!savedSessionId) return;

        // Auto-reload session history
        useChatStore.getState().loadSession(savedSessionId);

        // Check for active stream on backend
        const checkActive = async () => {
            try {
                const res = await fetch(`${API_CONFIG.gatewayUrl}/api/chat/sessions/${savedSessionId}/status`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.isActive) {
                        // Resubscribe to live stream
                        activeStreamsRef.current.set(savedSessionId, true);
                        if (clientRef.current?.getState() === 'connected') {
                            clientRef.current.resubscribe([savedSessionId]);
                        }
                    }
                }
            } catch (err) {
                console.warn('Silent fail checkActiveRecovery:', err);
            }
        };

        // Wait a bit for WS to connect if needed
        setTimeout(checkActive, 1000);
    }, []);

    const sendMessage = useCallback(async (message: string) => {
        if (!message.trim()) return;

        const client = clientRef.current;
        if (!client || client.getState() !== 'connected') {
            setError('Non connesso al gateway');
            return;
        }

        let targetSessionId = useChatStore.getState().currentSessionId;

        // Lazy Session Creation (Mirroring useChat.ts)
        if (!targetSessionId) {
            targetSessionId = await useChatStore.getState().createNewSession();
            if (!targetSessionId) {
                setError('Impossibile creare una nuova sessione');
                return;
            }
        }

        const targetSession = useChatStore.getState().sessionStates[targetSessionId];
        if (targetSession?.isStreaming) return;

        // Start tracking
        activeStreamsRef.current.set(targetSessionId, true);
        streamingSessionRef.current = targetSessionId;

        addUserMessage(message, targetSessionId);
        clearThinking(targetSessionId);
        startStreaming(targetSessionId);

        client.sendChat(message, targetSessionId);
    }, [addUserMessage, startStreaming, setError]);

    const reconnect = useCallback(() => {
        clientRef.current?.connect();
    }, []);

    return {
        sendMessage,
        reconnect,
        isThinking: currentSession?.isThinking ?? false,
        statusMessage: currentSession?.statusMessage ?? null,
        connectionState,
        isConnected: connectionState === 'connected',
    };
}
