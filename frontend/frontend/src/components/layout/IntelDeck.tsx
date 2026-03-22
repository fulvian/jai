/**
 * IntelDeck Component
 *
 * Pannello laterale con tabs per Skills, Monitors e Prompt Library.
 * Stile macOS Tahoe Liquid Glass con segmented control.
 */

'use client';

import { useState, useCallback } from 'react';
import { SkillsPanel } from '@/components/skills';
import MonitorsPanel from '@/components/monitors/MonitorsPanel';
import PromptLibrary from '@/components/chat/PromptLibrary';
import { useChatStore } from '@/stores/useChatStore';
import { cn } from '@/lib/utils';

type Tab = 'skills' | 'monitors' | 'prompts';

export function IntelDeck() {
    const [activeTab, setActiveTab] = useState<Tab>('skills');
    const currentSessionId = useChatStore((s) => s.currentSessionId);

    const handleUsePrompt = useCallback((content: string) => {
        // Copia il contenuto del prompt negli appunti per incollarlo nella chat
        if (content.trim()) {
            navigator.clipboard.writeText(content).catch(() => {
                // Fallback: log silenzioso
                console.warn('[IntelDeck] Clipboard write failed');
            });
        }
    }, []);

    return (
        <div className="flex flex-col h-full overflow-hidden">
            {/* Segmented Control - Glass Tabs */}
            <div className="glass-tabs m-3">
                <button
                    className={cn('glass-tab', activeTab === 'skills' && 'active')}
                    onClick={() => setActiveTab('skills')}
                >
                    <span className="text-sm">🧩</span>
                    <span>Skills</span>
                </button>
                <button
                    className={cn('glass-tab', activeTab === 'monitors' && 'active')}
                    onClick={() => setActiveTab('monitors')}
                >
                    <span className="text-sm">🔔</span>
                    <span>Monitors</span>
                </button>
                <button
                    className={cn('glass-tab', activeTab === 'prompts' && 'active')}
                    onClick={() => setActiveTab('prompts')}
                >
                    <span className="text-sm">📚</span>
                    <span>Prompt</span>
                </button>
            </div>

            {/* Tab Content */}
            <div className="flex-1 overflow-y-auto px-3 pb-3">
                {activeTab === 'skills' && <SkillsPanel />}
                {activeTab === 'monitors' && <MonitorsPanel />}
                {activeTab === 'prompts' && (
                    <PromptLibrary
                        isOpen={true}
                        onClose={() => setActiveTab('skills')}
                        onUsePrompt={handleUsePrompt}
                        currentSessionId={currentSessionId}
                    />
                )}
            </div>
        </div>
    );
}

export default IntelDeck;

