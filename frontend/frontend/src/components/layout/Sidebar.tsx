'use client';

import { useEffect, useCallback, useState, useRef } from 'react';
import {
    Plus,
    Search,
    Settings,
    Pencil,
    Trash2,
} from 'lucide-react';

import { clsx } from 'clsx';
import { useChatStore, type SessionSummary } from '@/stores/useChatStore';
import SessionClusterSidebar from '@/components/sidebar/SessionClusterSidebar';
import { useLayout } from './DashboardLayout';
import { DeleteSessionModal } from '../chat/DeleteSessionModal';
import { useSettingsStore } from '@/stores/useSettingsStore';

type SidebarView = 'list' | 'clusters';

interface SidebarProps {
    isOpen?: boolean;
    onToggle?: () => void;
}

export function Sidebar({ isOpen = true }: SidebarProps) {
    const { isMobile, closeAll } = useLayout();
    const {
        sessions,
        loadingSessions,
        currentSessionId,
        fetchSessions,
        createNewSession,
        loadSession,
        deleteSession,
        updateSessionTitle,
    } = useChatStore();

    const [sidebarView, setSidebarView] = useState<SidebarView>('list');
    const [sessionToDelete, setSessionToDelete] = useState<{ id: string, title?: string } | null>(null);

    const fetchDoneRef = useRef(false);

    // Fetch sessions on mount
    useEffect(() => {
        if (!fetchDoneRef.current) {
            fetchDoneRef.current = true;
            fetchSessions().then(() => {
                const state = useChatStore.getState();
                if (state.currentSessionId) {
                    const session = state.getCurrentSession();
                    if (session.messages.length === 0) {
                        state.loadSession(state.currentSessionId);
                    }
                }
            });
        }
    }, [fetchSessions, loadSession]);

    const handleNewSession = useCallback(async () => {
        await createNewSession();
        if (isMobile) closeAll();
    }, [createNewSession, isMobile, closeAll]);

    const handleSelectSession = useCallback(async (sessionId: string) => {
        if (sessionId !== currentSessionId) {
            await loadSession(sessionId);
        }
        if (isMobile) closeAll();
    }, [currentSessionId, loadSession, isMobile, closeAll]);

    const handleDeleteSession = useCallback((e: React.MouseEvent, sessionId: string, title?: string) => {
        e.stopPropagation();
        setSessionToDelete({ id: sessionId, title });
    }, []);

    const confirmDelete = useCallback(async () => {
        if (sessionToDelete) {
            await deleteSession(sessionToDelete.id);
            setSessionToDelete(null);
        }
    }, [deleteSession, sessionToDelete]);

    const handleUpdateTitle = useCallback(async (sessionId: string, newTitle: string) => {
        await updateSessionTitle(sessionId, newTitle);
    }, [updateSessionTitle]);

    return (
        <aside
            className={clsx(
                "glass-vibrant flex flex-col transition-all duration-300 ease-in-out z-30 border-r border-white/5 h-full",
                isOpen ? "w-full" : "w-0 -translate-x-full"
            )}
        >
            {/* Sidebar Header */}
            <div className="sidebar-header h-[var(--header-height)] flex items-center justify-between px-4 border-b border-white/5">
                <span className="font-semibold text-[var(--text-primary)] text-sm tracking-tight px-0">Sessions</span>
                <button
                    onClick={handleNewSession}
                    className="btn-icon w-8 h-8 rounded-full hover:bg-white/10 flex items-center justify-center transition-colors"
                    title="Nuova Sessione"
                >
                    <Plus size={18} />
                </button>
            </div>

            {/* View Toggle: Lista / Cluster */}
            <div className="sidebar-view-toggle">
                <button
                    className={clsx('sidebar-view-btn', sidebarView === 'list' && 'active')}
                    onClick={() => setSidebarView('list')}
                >
                    📋 Lista
                </button>
                <button
                    className={clsx('sidebar-view-btn', sidebarView === 'clusters' && 'active')}
                    onClick={() => setSidebarView('clusters')}
                >
                    🧩 Cluster
                </button>
            </div>

            {/* ── Vista Lista ─────────────────────────────────────── */}
            {sidebarView === 'list' && (
                <>
                    {/* Search Bar */}
                    <div className="p-3">
                        <div className="relative group">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)] group-focus-within:text-white transition-colors" size={14} />
                            <input
                                type="text"
                                placeholder="Cerca..."
                                className="w-full bg-white/5 border border-white/5 rounded-lg py-1.5 pl-9 pr-3 text-sm focus:outline-none focus:bg-white/10 focus:border-white/10 transition-all font-light"
                            />
                        </div>
                    </div>

                    {/* Sessions List */}
                    <div className="flex-1 overflow-y-auto custom-scrollbar px-2 py-2">
                        <div className="space-y-1">
                            {loadingSessions ? (
                                <div className="text-xs text-[var(--text-tertiary)] p-3">
                                    Caricamento...
                                </div>
                            ) : sessions.length === 0 ? (
                                <div className="text-xs text-[var(--text-tertiary)] p-3">
                                    Nessuna sessione. Clicca + per iniziare.
                                </div>
                            ) : (
                                sessions.map((session) => (
                                    <SessionItem
                                        key={session.session_id}
                                        session={session}
                                        isActive={session.session_id === currentSessionId}
                                        onSelect={() => handleSelectSession(session.session_id)}
                                        onDelete={(e) => handleDeleteSession(e, session.session_id, session.title)}
                                        onUpdateTitle={(newTitle) => handleUpdateTitle(session.session_id, newTitle)}
                                    />
                                ))
                            )}
                        </div>
                    </div>
                </>
            )}

            {/* ── Vista Cluster ────────────────────────────────────── */}
            {sidebarView === 'clusters' && (
                <div className="flex-1 overflow-y-auto custom-scrollbar">
                    <SessionClusterSidebar
                        onSelectSession={(sessionId) => handleSelectSession(sessionId)}
                        activeSessionId={currentSessionId}
                    />
                </div>
            )}

            {/* Sidebar Footer */}
            <div className="p-4 border-t border-white/5 bg-black/10">
                <button 
                    onClick={() => useSettingsStore.getState().openSettings()}
                    className="flex items-center gap-3 w-full p-2 rounded-xl text-sm text-[var(--text-secondary)] hover:bg-white/5 transition-colors group"
                >
                    <Settings size={18} className="group-hover:rotate-45 transition-transform duration-500" />
                    <span>Impostazioni</span>
                </button>
            </div>

            {/* Modal di eliminazione */}
            <DeleteSessionModal
                isOpen={!!sessionToDelete}
                onClose={() => setSessionToDelete(null)}
                onConfirm={confirmDelete}
                sessionTitle={sessionToDelete?.title}
            />
        </aside>
    );
}

interface SessionItemProps {
    session: SessionSummary;
    isActive: boolean;
    onSelect: () => void;
    onDelete: (e: React.MouseEvent) => void;
    onUpdateTitle: (newTitle: string) => void;
}

function SessionItem({ session, isActive, onSelect, onDelete, onUpdateTitle }: SessionItemProps) {
    const [isEditing, setIsEditing] = useState(false);
    const [editValue, setEditValue] = useState(session.title || '');
    const inputRef = useRef<HTMLInputElement>(null);

    const sessionState = useChatStore((s) => s.sessionStates[session.session_id]);
    const { isStreaming = false } = sessionState || {};

    useEffect(() => {
        if (isEditing && inputRef.current) {
            inputRef.current.focus();
            inputRef.current.select();
        }
    }, [isEditing]);

    const formatTimestamp = (dateStr?: string) => {
        if (!dateStr) return '';
        try {
            const sanitized = dateStr.includes(' ') && !dateStr.includes('T')
                ? dateStr.replace(' ', 'T')
                : dateStr;
            const date = new Date(sanitized);
            if (isNaN(date.getTime())) return '';
            const now = new Date();
            const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
            if (diffDays === 0) {
                return date.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
            } else if (diffDays === 1) {
                return 'Ieri';
            } else if (diffDays < 7) {
                return date.toLocaleDateString('it-IT', { weekday: 'short' });
            } else {
                return date.toLocaleDateString('it-IT', { day: 'numeric', month: 'short' });
            }
        } catch (err) {
            return '';
        }
    };

    const handleDoubleClick = (e: React.MouseEvent) => {
        e.stopPropagation();
        setEditValue(session.title || 'Nuova conversazione');
        setIsEditing(true);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            onUpdateTitle(editValue);
            setIsEditing(false);
        } else if (e.key === 'Escape') {
            setEditValue(session.title || '');
            setIsEditing(false);
        }
    };

    return (
        <div
            onClick={onSelect}
            className={clsx(
                "group relative flex flex-col p-3 rounded-xl cursor-pointer transition-all duration-200 border border-transparent select-none",
                isActive
                    ? "bg-white/10 border-white/10 shadow-lg"
                    : "hover:bg-white/5"
            )}
        >
            <div className="flex items-center justify-between gap-2 overflow-hidden">
                <div className="flex items-center gap-2 overflow-hidden flex-1">
                    {isStreaming ? (
                        <div className="w-1.5 h-1.5 rounded-full bg-[var(--tahoe-blue)] animate-pulse shadow-[0_0_8px_var(--tahoe-blue)] flex-shrink-0" />
                    ) : (
                        <div className={clsx("w-1.5 h-1.5 rounded-full flex-shrink-0", isActive ? "bg-white/40" : "bg-white/20")} />
                    )}

                    {isEditing ? (
                        <input
                            ref={inputRef}
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onKeyDown={handleKeyDown}
                            onBlur={() => setIsEditing(false)}
                            className="bg-white/10 border-none outline-none text-xs rounded px-1 py-0.5 w-full text-white"
                        />
                    ) : (
                        <span className={clsx(
                            "text-xs truncate font-medium",
                            isActive ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
                        )}>
                            {session.title || 'Nuova conversazione'}
                        </span>
                    )}
                </div>

                <span className="text-[10px] text-[var(--text-quaternary)] flex-shrink-0 font-light tracking-tight">
                    {formatTimestamp(session.updated_at)}
                </span>
            </div>

            <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                    onClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
                    className="p-1 rounded-md bg-white/5 hover:bg-white/15 text-[var(--text-tertiary)] transition-colors"
                >
                    <Pencil size={12} />
                </button>
                <button
                    onClick={onDelete}
                    className="p-1 rounded-md bg-white/5 hover:bg-red-500/20 text-[var(--text-tertiary)] hover:text-red-400 transition-colors"
                >
                    <Trash2 size={12} />
                </button>
            </div>
        </div>
    );
}
