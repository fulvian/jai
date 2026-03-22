'use client';

import Image from 'next/image';
import {
    Menu,
    Settings,
    Mic,
    PanelRightClose,
    PanelRightOpen,
    Search,
    ChevronDown,
} from 'lucide-react';
import { useSettingsStore } from '@/stores/useSettingsStore';

interface HeaderProps {
    onToggleSidebar: () => void;
    onToggleCanvas: () => void;
    canvasOpen: boolean;
}

export function Header({ onToggleSidebar, onToggleCanvas, canvasOpen }: HeaderProps) {
    const openSettings = useSettingsStore((state) => state.openSettings);

    return (
        <header className="glass-vibrant h-[var(--header-height)] flex items-center justify-between px-6 z-40 border-b border-white/5">
            {/* Left Section: Traffic Lights + Menu */}
            <div className="flex items-center gap-6">
                <div className="flex gap-2 mr-4">
                    <div className="traffic-light traffic-light-red" />
                    <div className="traffic-light traffic-light-yellow" />
                    <div className="traffic-light traffic-light-green" />
                </div>

                <button
                    className="btn-icon md:hidden"
                    onClick={onToggleSidebar}
                >
                    <Menu size={20} />
                </button>

                {/* Unified Breadcrumb/Title */}
                <div className="flex items-center gap-2 group cursor-default">
                    <Image src="/jAI_logo.png" alt="jAI" width={28} height={28} className="rounded-full" />
                    <h1 className="text-sm font-bold bg-gradient-to-r from-red-400 via-yellow-400 via-green-400 via-blue-400 to-violet-400 bg-clip-text text-transparent opacity-90 group-hover:opacity-100 transition-opacity">
                        jAI
                    </h1>
                    <span className="text-[var(--text-tertiary)] text-[10px] bg-white/5 px-1.5 py-0.5 rounded uppercase tracking-widest font-bold">2.0</span>
                </div>
            </div>

            {/* Center Section: Connectivity Pill */}
            <div className="hidden sm:flex items-center gap-4 bg-white/5 border border-white/5 px-4 py-1.5 rounded-full backdrop-blur-md">
                <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]" />
                    <span className="text-[10px] font-semibold text-[var(--text-secondary)] uppercase tracking-wider">Gateway Live</span>
                </div>
            </div>

            {/* Right Section: Actions */}
            <div className="flex items-center gap-1.5">
                <button
                    className="btn-icon w-9 h-9"
                    title="Voice Mode"
                >
                    <Mic size={18} />
                </button>

                <div className="h-4 w-[1px] bg-white/10 mx-1" />

                <button
                    className="btn-icon w-9 h-9"
                    onClick={onToggleCanvas}
                    title={canvasOpen ? 'Chiudi Area Visuale' : 'Apri Area Visuale'}
                >
                    {canvasOpen ? (
                        <PanelRightClose size={18} className="text-[var(--accent-primary)]" />
                    ) : (
                        <PanelRightOpen size={18} />
                    )}
                </button>

                <button
                    className="btn-icon w-9 h-9"
                    onClick={() => {
                        console.log('Settings button clicked');
                        openSettings();
                    }}
                    title="Proprietà"
                >
                    <Settings size={18} />
                </button>
            </div>
        </header>
    );
}
