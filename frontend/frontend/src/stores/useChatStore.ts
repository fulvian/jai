/**
 * Chat store with Zustand.
 *
 * Per-session state architecture: each session has its own messages,
 * pendingMessage, activitySteps, isStreaming, and error state.
 * This ensures full isolation between chat sessions.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { Message, Source, SessionConfig } from '@/types/chat';

import { API_CONFIG } from '@/lib/config';
const API_URL = API_CONFIG.gatewayUrl;

/** Session summary for sidebar display */
export interface SessionSummary {
    session_id: string;
    title: string;
    created_at: string;
    updated_at?: string;
    message_count: number;
    config?: SessionConfig;
}

/** Activity step for the real-time progress timeline. */
export interface ActivityStep {
    type: 'thinking' | 'plan' | 'step_start' | 'step_thinking' | 'step_complete' | 'step_error' | 'synthesizing';
    message: string;
    icon: string;
    status: 'active' | 'done' | 'error';
    step?: number;
    total?: number;
    areas?: string[];
    tools?: string[];
    details?: string;
}

/** Per-session state data */
export interface SessionData {
    messages: Message[];
    pendingMessage: string;
    pendingSources: Source[];
    isStreaming: boolean;
    activitySteps: ActivityStep[];
    error: string | null;
    isThinking: boolean;
    statusMessage: string | null;
    pendingThinking: string;
}

/** Default empty session state */
const emptySessionData: SessionData = {
    messages: [],
    pendingMessage: '',
    pendingSources: [],
    isStreaming: false,
    activitySteps: [],
    error: null,
    isThinking: false,
    statusMessage: null,
    pendingThinking: '',
};

function createEmptySession(): SessionData {
    return { ...emptySessionData, messages: [], pendingSources: [], activitySteps: [] };
}

interface ChatState {
    // Per-session state
    sessionStates: Record<string, SessionData>;
    currentSessionId: string | null;

    // Sessions list
    sessions: SessionSummary[];
    loadingSessions: boolean;

    // Helpers - read current session
    getCurrentSession: () => SessionData;
    getSession: (sessionId: string) => SessionData;

    // Actions - Chat (session-scoped)
    setSessionId: (id: string) => void;
    addUserMessage: (content: string, sessionId?: string) => void;
    startStreaming: (sessionId: string) => void;
    appendToken: (token: string, sessionId?: string) => void;
    setSources: (sources: Source[], sessionId?: string) => void;
    finishStreaming: (sessionId?: string) => void;
    setThinking: (isThinking: boolean, sessionId?: string) => void;
    setStatusMessage: (message: string | null, sessionId?: string) => void;
    setError: (error: string, sessionId?: string) => void;
    clearError: (sessionId?: string) => void;
    clearMessages: (sessionId?: string) => void;
    clearSession: () => void;
    addToolCall: (tool: { name: string; result: any; sessionId: string }) => void;
    appendThinking: (token: string, sessionId?: string) => void;
    clearThinking: (sessionId?: string) => void;


    // Actions - Activity (session-scoped)
    addActivity: (step: ActivityStep, sessionId?: string) => void;
    updateLastActivity: (update: Partial<ActivityStep>, sessionId?: string) => void;
    clearActivities: (sessionId?: string) => void;

    // Actions - Message Management
    deleteMessage: (sessionId: string, messageIndex: number) => Promise<void>;
    submitFeedback: (sessionId: string, messageIndex: number, score: 1 | -1 | 0, comment?: string) => Promise<void>;
    truncateFromIndex: (sessionId: string, messageIndex: number) => void;

    // Actions - Sessions Management
    fetchSessions: () => Promise<void>;
    createNewSession: (config?: SessionConfig) => Promise<string | null>;
    loadSession: (sessionId: string) => Promise<void>;
    deleteSession: (sessionId: string) => Promise<void>;
    updateSessionTitle: (sessionId: string, title: string) => Promise<void>;
    updateSessionConfig: (sessionId: string, config: Partial<SessionConfig>) => Promise<void>;
    _fetchLock: boolean;
}

function generateId(): string {
    return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

/** Helper: update a specific session's state immutably */
function updateSession(
    state: Pick<ChatState, 'sessionStates'>,
    sessionId: string,
    updater: (session: SessionData) => Partial<SessionData>
): { sessionStates: Record<string, SessionData> } {
    const current = state.sessionStates[sessionId] || createEmptySession();
    const updates = updater(current);
    return {
        sessionStates: {
            ...state.sessionStates,
            [sessionId]: { ...current, ...updates },
        },
    };
}

export const useChatStore = create<ChatState>()(
    persist(
        (set, get) => ({
            // Initial state
            sessionStates: {},
            currentSessionId: null,
            sessions: [],
            loadingSessions: false,
            _fetchLock: false, // Internal guard for recursion

            // Helpers
            getCurrentSession: () => {
                const { currentSessionId, sessionStates } = get();
                if (!currentSessionId) return emptySessionData;
                return sessionStates[currentSessionId] || emptySessionData;
            },

            getSession: (sessionId: string) => {
                const { sessionStates } = get();
                return sessionStates[sessionId] || emptySessionData;
            },

            // Actions - Chat
            setSessionId: (id) => {
                const state = get();
                // Ensure the session has state allocated
                if (!state.sessionStates[id]) {
                    set({
                        currentSessionId: id,
                        ...updateSession(state, id, () => ({})),
                    });
                } else {
                    set({ currentSessionId: id });
                }
            },

            addUserMessage: (content, sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                const message: Message = {
                    id: generateId(),
                    role: 'user',
                    content,
                    timestamp: new Date(),
                };

                set((state) => updateSession(state, targetId, (s) => ({
                    messages: [...s.messages, message],
                })));
            },

            startStreaming: (sessionId: string) => {
                set((state) => updateSession(state, sessionId, () => ({
                    isStreaming: true,
                    pendingMessage: '',
                    pendingSources: [],
                    activitySteps: [],
                    error: null,
                })));
            },

            appendToken: (token, sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, (s) => ({
                    pendingMessage: s.pendingMessage + token,
                })));
            },

            setSources: (sources, sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, () => ({
                    pendingSources: sources,
                })));
            },

            finishStreaming: (sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                const sessionData = get().sessionStates[targetId] || createEmptySession();

                if (sessionData.pendingMessage) {
                    const message: Message = {
                        id: generateId(),
                        role: 'assistant',
                        content: sessionData.pendingMessage,
                        timestamp: new Date(),
                        sources: sessionData.pendingSources.length > 0 ? sessionData.pendingSources : undefined,
                        // 🎯 NEW: Preserve thinking in the final message
                        thinking: sessionData.pendingThinking || undefined,
                    };
                    set((state) => updateSession(state, targetId, (s) => ({
                        messages: [...s.messages, message],
                        pendingMessage: '',
                        pendingSources: [],
                        pendingThinking: '', // Clear thinking after saving
                        isStreaming: false,
                        isThinking: false,
                    })));
                } else {
                    set((state) => updateSession(state, targetId, () => ({
                        pendingMessage: '',
                        pendingSources: [],
                        pendingThinking: '',
                        isStreaming: false,
                        isThinking: false,
                        statusMessage: null,
                    })));
                }
            },

            setThinking: (isThinking, sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, () => ({
                    isThinking,
                    // If we stop thinking, don't necessarily clear pendingThinking yet, 
                    // maybe keep it for history or display until next phase
                })));
            },

            appendThinking: (token, sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, (s) => ({
                    pendingThinking: s.pendingThinking + token,
                })));
            },

            clearThinking: (sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, () => ({
                    pendingThinking: '',
                })));
            },

            setStatusMessage: (message, sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, () => ({
                    statusMessage: message,
                })));
            },

            setError: (error, sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, () => ({
                    error,
                    isStreaming: false,
                })));
            },

            clearError: (sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, () => ({
                    error: null,
                })));
            },

            clearMessages: (sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, () => ({
                    messages: [],
                    pendingMessage: '',
                    pendingSources: [],
                    activitySteps: [],
                })));
            },

            clearSession: () => {
                const { currentSessionId } = get();
                if (currentSessionId) {
                    set((state) => ({
                        currentSessionId: null,
                        sessionStates: {
                            ...state.sessionStates,
                            [currentSessionId]: createEmptySession(),
                        },
                    }));
                } else {
                    set({ currentSessionId: null });
                }
            },

            addToolCall: (tool) => {
                // Log tool call for debugging
                console.log(`[Tool Call] ${tool.name} in session ${tool.sessionId}:`, tool.result);
                // Could add to activity steps or messages in future
            },

            // Activity timeline actions (session-scoped)
            addActivity: (step, sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, (s) => ({
                    activitySteps: [...s.activitySteps, step],
                })));
            },

            updateLastActivity: (update, sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, (s) => {
                    const steps = [...s.activitySteps];
                    if (steps.length > 0) {
                        steps[steps.length - 1] = { ...steps[steps.length - 1], ...update };
                    }
                    return { activitySteps: steps };
                }));
            },

            clearActivities: (sessionId?) => {
                const targetId = sessionId || get().currentSessionId;
                if (!targetId) return;

                set((state) => updateSession(state, targetId, () => ({
                    activitySteps: [],
                })));
            },

            // Actions - Message Management
            deleteMessage: async (sessionId: string, messageIndex: number) => {
                try {
                    const url = `${API_URL}/api/chat/sessions/${sessionId}/turns/${messageIndex}`;
                    const response = await fetch(url, { method: 'DELETE' });

                    if (response.ok || response.status === 404) {
                        // 200: deleted on backend | 404: localStorage out of sync
                        // Reload session to sync local state with Redis
                        await get().loadSession(sessionId);
                    }
                } catch (error) {
                    console.error('Failed to delete message:', error);
                }
            },

            truncateFromIndex: (sessionId: string, messageIndex: number) => {
                set((state) => updateSession(state, sessionId, (s) => ({
                    messages: s.messages.slice(0, messageIndex),
                })));
            },

            submitFeedback: async (sessionId: string, messageIndex: number, score: 1 | -1 | 0, comment?: string) => {
                try {
                    const url = `${API_URL}/api/chat/sessions/${sessionId}/turns/${messageIndex}/feedback`;
                    const response = await fetch(url, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ score, comment }),
                    });

                    if (response.ok) {
                        // Update local state
                        set((state) => updateSession(state, sessionId, (s) => {
                            const newMessages = [...s.messages];
                            if (newMessages[messageIndex]) {
                                newMessages[messageIndex] = {
                                    ...newMessages[messageIndex],
                                    feedback: score === 0 ? undefined : {
                                        score,
                                        comment,
                                        timestamp: new Date().toISOString(),
                                    },
                                };
                            }
                            return { messages: newMessages };
                        }));
                    }
                } catch (error) {
                    console.error('Failed to submit feedback:', error);
                }
            },

            // Actions - Sessions Management
            fetchSessions: async () => {
                set({ loadingSessions: true });
                try {
                    const response = await fetch(`${API_URL}/api/chat/sessions`);
                    if (response.ok) {
                        const data = await response.json();
                        const sessions: SessionSummary[] = data.sessions || [];
                        set({ sessions, loadingSessions: false });

                        // BUG-17 Fix: Auto-create session if none exist AND no current session is active/restored
                        if (sessions.length === 0 && !get().currentSessionId && !get()._fetchLock) {
                            console.log('[useChatStore] No sessions found and no current session, creating default...');
                            set({ _fetchLock: true });
                            await get().createNewSession();
                            set({ _fetchLock: false });
                        }
                    } else {
                        set({ loadingSessions: false });
                    }
                } catch (error) {
                    console.error('Failed to fetch sessions:', error);
                    set({ loadingSessions: false });
                }
            },

            createNewSession: async (config?: SessionConfig) => {
                try {
                    const response = await fetch(`${API_URL}/api/chat/sessions`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ config }),
                    });
                    if (response.ok) {
                        const data = await response.json();
                        const newSessionId = data.session_id;

                        // Create fresh session state - does NOT touch other sessions
                        set((state) => ({
                            currentSessionId: newSessionId,
                            sessionStates: {
                                ...state.sessionStates,
                                [newSessionId]: createEmptySession(),
                            },
                        }));

                        // Refresh sessions list
                        await get().fetchSessions();

                        return newSessionId;
                    }
                } catch (error) {
                    console.error('Failed to create session:', error);
                }
                return null;
            },

            loadSession: async (sessionId: string) => {
                try {
                    const response = await fetch(`${API_URL}/api/chat/sessions/${sessionId}`);
                    if (response.ok) {
                        const data = await response.json();
                        const turns = data.turns || [];

                        // Convert turns to messages
                        const messages: Message[] = turns.map((turn: { role: string; content: string; timestamp?: string }, index: number) => ({
                            id: `loaded-${sessionId}-${index}`,
                            role: turn.role as 'user' | 'assistant',
                            content: turn.content,
                            timestamp: turn.timestamp ? new Date(turn.timestamp) : new Date(),
                        }));

                        // Load session WITHOUT touching other sessions' streaming state
                        set((state) => {
                            const existing = state.sessionStates[sessionId];
                            return {
                                currentSessionId: sessionId,
                                sessionStates: {
                                    ...state.sessionStates,
                                    [sessionId]: {
                                        // Preserve streaming state if session is still streaming
                                        ...(existing || createEmptySession()),
                                        messages,
                                        // Only reset error, keep isStreaming if active
                                        error: null,
                                    },
                                },
                            };
                        });
                    }
                } catch (error) {
                    console.error('Failed to load session:', error);
                }
            },

            deleteSession: async (sessionId: string) => {
                try {
                    const response = await fetch(`${API_URL}/api/chat/sessions/${sessionId}`, {
                        method: 'DELETE',
                    });
                    if (response.ok) {
                        const { currentSessionId } = get();

                        // Remove session state
                        set((state) => {
                            const { [sessionId]: _removed, ...rest } = state.sessionStates;
                            return {
                                sessionStates: rest,
                                ...(currentSessionId === sessionId ? { currentSessionId: null } : {}),
                            };
                        });

                        // Refresh sessions list
                        await get().fetchSessions();
                    }
                } catch (error) {
                    console.error('Failed to delete session:', error);
                }
            },

            updateSessionTitle: async (sessionId: string, title: string) => {
                try {
                    const response = await fetch(
                        `${API_URL}/api/chat/sessions/${sessionId}`,
                        {
                            method: 'PATCH',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ title }),
                        }
                    );
                    if (response.ok) {
                        // Update title locally for immediate feedback
                        set((state) => ({
                            sessions: state.sessions.map((s) =>
                                s.session_id === sessionId ? { ...s, title } : s
                            ),
                        }));
                    }
                } catch (error) {
                    console.error('Failed to update session title:', error);
                }
            },

            updateSessionConfig: async (sessionId: string, config: Partial<SessionConfig>) => {
                try {
                    const response = await fetch(
                        `${API_URL}/api/chat/sessions/${sessionId}/config`,
                        {
                            method: 'PUT',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(config),
                        }
                    );
                    if (response.ok) {
                        // Update config locally for immediate feedback
                        set((state) => ({
                            sessions: state.sessions.map((s) =>
                                s.session_id === sessionId
                                    ? { ...s, config: { ...(s.config ?? { type: 'free' as const }), ...config } }
                                    : s
                            ),
                        }));
                    }
                } catch (error) {
                    console.error('Failed to update session config:', error);
                }
            },
        }),
        {
            name: 'persan-chat-session-storage',
            storage: createJSONStorage(() => localStorage), // FIX: localStorage per sopravvivere a chiusura tab
            partialize: (state) => ({
                currentSessionId: state.currentSessionId,
                // FIX: Include sessionStates (messages + pendingMessage) for recovery after reload
                sessionStates: Object.fromEntries(
                    Object.entries(state.sessionStates).map(([id, data]) => [
                        id,
                        {
                            messages: data.messages,
                            pendingMessage: data.pendingMessage,
                        },
                    ])
                ),
            }),
            version: 3, // FIX: New version for localStorage + sessionStates persistence
            migrate: (persisted: any, version: number) => {
                if (version < 3) {
                    // Migration from v2 (sessionStorage-only) to v3 (localStorage with sessionStates)
                    return {
                        currentSessionId: persisted.currentSessionId ?? null,
                        sessionStates: {}, // Start fresh - old v2 had no sessionStates
                    };
                }
                return persisted;
            },
            onRehydrateStorage: () => (state) => {
                // FIX: Sanitize state after rehydration to reset streaming flags and ensure all fields exist
                if (!state) return;
                for (const [sessionId, data] of Object.entries(state.sessionStates)) {
                    // Ensure all required fields for SessionData exist
                    if (!data.messages) data.messages = [];
                    if (!data.pendingMessage) data.pendingMessage = '';
                    if (!data.pendingSources) data.pendingSources = [];
                    if (!data.activitySteps) data.activitySteps = [];
                    if (data.isStreaming === undefined) data.isStreaming = false;
                    if (data.isThinking === undefined) data.isThinking = false;
                    if (data.statusMessage === undefined) data.statusMessage = null;
                    if (data.error === undefined) data.error = null;
                    if (data.pendingThinking === undefined) data.pendingThinking = '';

                    if (data.isStreaming) data.isStreaming = false;
                    if (data.pendingMessage) {
                        // Convert pendingMessage to a partial assistant message for display
                        data.messages.push({
                            id: `partial-${Date.now()}`,
                            role: 'assistant',
                            content: data.pendingMessage,
                            timestamp: new Date(),
                            isPartial: true, // Mark as incomplete response
                        });
                        data.pendingMessage = '';
                    }
                }
            },
        }
    )
);
