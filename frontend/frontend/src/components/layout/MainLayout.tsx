'use client';

import { ReactNode, useState } from 'react';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { SettingsPanel } from '@/components/settings/SettingsPanel';

interface MainLayoutProps {
    children: ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [canvasOpen, setCanvasOpen] = useState(true);

    return (
        <div className="flex h-screen bg-transparent">
            {/* Sidebar */}
            <Sidebar
                isOpen={sidebarOpen}
                onToggle={() => setSidebarOpen(!sidebarOpen)}
            />

            {/* Main Content */}
            <div className="flex flex-col flex-1 min-w-0">
                {/* Header */}
                <Header
                    onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
                    onToggleCanvas={() => setCanvasOpen(!canvasOpen)}
                    canvasOpen={canvasOpen}
                />

                {/* Content Area */}
                <main className="flex flex-1 overflow-hidden">
                    {children}
                </main>
            </div>

            {/* Settings Modal */}
            <SettingsPanel />
        </div>
    );
}
