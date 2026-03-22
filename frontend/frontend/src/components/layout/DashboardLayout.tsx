'use client';

import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { ReactNode, useState, useEffect, useCallback, createContext, useContext, useMemo } from 'react';
import Image from 'next/image';
import { Menu, PanelRight, X } from 'lucide-react';
import { useIsMobile } from '@/hooks/useIsMobile';
import { SettingsPanel } from '@/components/settings/SettingsPanel';

interface LayoutContextType {
    isMobile: boolean | null;
    sidebarOpen: boolean;
    intelDeckOpen: boolean;
    toggleSidebar: () => void;
    toggleIntelDeck: () => void;
    closeAll: () => void;
}

const LayoutContext = createContext<LayoutContextType | undefined>(undefined);

export function useLayout() {
    const context = useContext(LayoutContext);
    if (!context) throw new Error('useLayout must be used within LayoutProvider');
    return context;
}

interface DashboardLayoutProps {
    children: ReactNode;
    sidebar: ReactNode;
    intelDeck: ReactNode;
}


export function DashboardLayout({ children, sidebar, intelDeck }: DashboardLayoutProps) {
    const isMobile = useIsMobile();
    const [mounted, setMounted] = useState(false);
    const [sidebarOpen, setSidebarOpen] = useState(false);
    const [intelDeckOpen, setIntelDeckOpen] = useState(false);

    // Evita errori di idratazione
    useEffect(() => {
        setMounted(true);
    }, []);

    // Chiudi i drawer quando si passa a desktop
    useEffect(() => {
        if (isMobile === false) {
            setSidebarOpen(false);
            setIntelDeckOpen(false);
        }
    }, [isMobile]);

    const toggleSidebar = useCallback(() => {
        setSidebarOpen((prev) => !prev);
        setIntelDeckOpen(false);
    }, []);

    const toggleIntelDeck = useCallback(() => {
        setIntelDeckOpen((prev) => !prev);
        setSidebarOpen(false);
    }, []);

    const closeAll = useCallback(() => {
        setSidebarOpen(false);
        setIntelDeckOpen(false);
    }, []);

    const contextValue = useMemo(() => ({
        isMobile,
        sidebarOpen,
        intelDeckOpen,
        toggleSidebar,
        toggleIntelDeck,
        closeAll,
    }), [isMobile, sidebarOpen, intelDeckOpen, toggleSidebar, toggleIntelDeck, closeAll]);

    return (
        <>
            <LayoutContext.Provider value={contextValue}>
            {(!mounted || isMobile === null) ? (
                /* ── LOADING / HYDRATION SHELL ──────────────────────────────── */
                <div className="flex h-screen w-full flex-col overflow-hidden" style={{ background: 'var(--tahoe-gray-6, #1c1c1e)' }}>
                    <div className="glass-topbar h-12 flex items-center justify-between px-4">
                        <div className="flex items-center gap-3">
                            <div className="flex items-center gap-1.5 mr-2">
                                <span className="w-3 h-3 rounded-full bg-white/10" />
                                <span className="w-3 h-3 rounded-full bg-white/10" />
                                <span className="w-3 h-3 rounded-full bg-white/10" />
                            </div>
                        </div>
                    </div>
                    <div className="flex-grow flex items-center justify-center">
                        <div className="flex flex-col items-center gap-6">
                            <div className="relative">
                                <div className="absolute inset-0 bg-blue-500/20 blur-3xl rounded-full animate-pulse" />
                                <Image src="/jAI_logo.png" alt="jAI" width={64} height={64} className="relative rounded-full" />
                            </div>
                            <div className="animate-pulse text-[var(--text-tertiary)] text-[12px] uppercase tracking-[0.2em] font-medium opacity-50">
                                Initializing jAI...
                            </div>
                        </div>
                    </div>
                    <div className="h-6 border-t border-[var(--glass-border-subtle)]" style={{ background: 'rgba(28, 28, 30, 0.5)' }} />
                </div>
            ) : isMobile ? (
                /* ── MOBILE LAYOUT ─────────────────────────────────────────── */
                <div className="flex h-[100dvh] w-full flex-col overflow-hidden" style={{ background: 'var(--tahoe-gray-6, #1c1c1e)' }}>
                    {/* Mobile TopBar */}

                    <div className="mobile-topbar">
                        <div className="flex items-center gap-3">
                            <button
                                onClick={toggleSidebar}
                                className={`mobile-topbar-btn ${sidebarOpen ? 'active' : ''}`}
                                aria-label="Toggle sessioni"
                            >
                                {sidebarOpen ? <X size={22} /> : <Menu size={22} />}
                            </button>
                            <div className="flex items-center gap-2">
                                <Image src="/jAI_logo.png" alt="jAI" width={32} height={32} className="rounded-full" />
                                <span className="font-bold text-lg tracking-tight bg-gradient-to-r from-red-400 via-yellow-400 via-green-400 via-blue-400 to-violet-400 bg-clip-text text-transparent">jAI</span>
                            </div>
                        </div>

                        <div className="flex items-center gap-3">
                            <div className="hidden xs:flex items-center gap-1.5 text-[10px] opacity-60" style={{ color: 'var(--text-tertiary)' }}>
                                <span className="w-1.5 h-1.5 rounded-full bg-[var(--tahoe-green,#28c840)]" />
                                <span>Live</span>
                            </div>
                            <button
                                onClick={toggleIntelDeck}
                                className={`mobile-topbar-btn ${intelDeckOpen ? 'active' : ''}`}
                                aria-label="Toggle intel deck"
                            >
                                {intelDeckOpen ? <X size={22} /> : <PanelRight size={22} />}
                            </button>
                        </div>
                    </div>

                    {/* Chat — full width */}
                    <div className="flex-1 overflow-hidden relative">
                        {children}
                    </div>

                    {/* Overlay backdrop */}
                    {(sidebarOpen || intelDeckOpen) && (
                        <div className="mobile-overlay" onClick={closeAll} aria-hidden="true" />
                    )}

                    {/* Sidebar Drawer (left) */}
                    {sidebarOpen && (
                        <div className="mobile-drawer mobile-drawer-left">
                            <button className="drawer-close-btn drawer-close-btn-left" onClick={toggleSidebar} aria-label="Chiudi sessioni">
                                <X size={16} />
                            </button>
                            <div className="flex-1 overflow-hidden">
                                {sidebar}
                            </div>
                        </div>
                    )}

                    {/* Intel Deck Drawer (right) */}
                    {intelDeckOpen && (
                        <div className="mobile-drawer mobile-drawer-right">
                            <button className="drawer-close-btn drawer-close-btn-right" onClick={toggleIntelDeck} aria-label="Chiudi intel deck">
                                <X size={16} />
                            </button>
                            <div className="flex-1 overflow-hidden">
                                {intelDeck}
                            </div>
                        </div>
                    )}
                </div>
            ) : (
                /* ── DESKTOP LAYOUT ────────────────────────────────────────── */
                <div className="flex h-screen w-full flex-col overflow-hidden" style={{ background: 'var(--tahoe-gray-6, #1c1c1e)' }}>
                    {/* TopBar - Glass Vibrancy */}
                    <div className="glass-topbar h-12 flex items-center justify-between px-4">
                        <div className="flex items-center gap-3">
                            <div className="flex items-center gap-1.5 mr-2">
                                <span className="w-3 h-3 rounded-full bg-[#ff5f57]" />
                                <span className="w-3 h-3 rounded-full bg-[#febc2e]" />
                                <span className="w-3 h-3 rounded-full bg-[#28c840]" />
                            </div>
                            <Image src="/jAI_logo.png" alt="jAI" width={28} height={28} className="rounded-full" />
                            <span className="font-semibold bg-gradient-to-r from-red-400 via-yellow-400 via-green-400 via-blue-400 to-violet-400 bg-clip-text text-transparent" style={{ letterSpacing: '-0.01em' }}>jAI</span>
                        </div>
                        <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
                            <span className="w-2 h-2 rounded-full bg-[var(--tahoe-green)]" />
                            <span>Me4BrAIn</span>
                        </div>
                    </div>

                    <PanelGroup direction="horizontal" className="flex-grow">
                        <Panel
                            id="sidebar"
                            defaultSize={20}
                            minSize={15}
                            maxSize={30}
                            className="glass-sidebar"
                        >
                            {sidebar}
                        </Panel>

                        <PanelResizeHandle className="w-px bg-[var(--glass-border-subtle)] hover:bg-[var(--tahoe-blue)] transition-all cursor-col-resize" />

                        <Panel id="center" defaultSize={55} minSize={30}>
                            <div className="h-full w-full">{children}</div>
                        </Panel>

                        <PanelResizeHandle className="w-px bg-[var(--glass-border-subtle)] hover:bg-[var(--tahoe-blue)] transition-all cursor-col-resize" />

                        <Panel
                            id="intel-deck"
                            defaultSize={25}
                            minSize={20}
                            maxSize={40}
                            className="glass-sidebar border-l border-[var(--glass-border-subtle)]"
                        >
                            {intelDeck}
                        </Panel>
                    </PanelGroup>

                    <div className="h-6 border-t border-[var(--glass-border-subtle)] px-3 flex items-center text-xs justify-between" style={{ background: 'rgba(28, 28, 30, 0.5)', color: 'var(--text-quaternary)' }}>
                        <div className="flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-[var(--tahoe-green)]" />
                            <span>Ready</span>
                        </div>
                        <div>v2.0.1-tahoe</div>
                    </div>
                </div>
            )}
        </LayoutContext.Provider>
        <SettingsPanel />
        </>
    );
}
