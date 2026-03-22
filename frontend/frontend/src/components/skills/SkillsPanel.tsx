/**
 * SkillsPanel - Pannello principale per gestione skills
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { Search, Upload, RefreshCw, Zap, CloudDownload } from 'lucide-react';
import { SkillCard, Skill } from './SkillCard';
import { ClawHubSearch, ClawHubSkill } from './ClawHubSearch';

interface SkillStats {
    total_explicit: number;
    total_crystallized: number;
    total_usage: number;
    avg_success_rate: number;
    crystallization_rate: number;
}

type TabType = 'installed' | 'clawhub' | 'workspace';

export function SkillsPanel() {
    const [activeTab, setActiveTab] = useState<TabType>('installed');
    const [skills, setSkills] = useState<Skill[]>([]);
    const [stats, setStats] = useState<SkillStats | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);

    // Fetch skills from backend
    const fetchSkills = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const response = await fetch('/api/skills/');
            if (!response.ok) throw new Error('Failed to fetch skills');
            const data = await response.json();
            setSkills(data.skills || []);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            setIsLoading(false);
        }
    }, []);

    // Fetch stats
    const fetchStats = useCallback(async () => {
        try {
            const response = await fetch('/api/skills/stats');
            if (response.ok) {
                const data = await response.json();
                setStats(data);
            }
        } catch (err) {
            console.error('Failed to fetch stats:', err);
        }
    }, []);

    useEffect(() => {
        fetchSkills();
        fetchStats();
    }, [fetchSkills, fetchStats]);

    // Toggle skill
    const handleToggle = async (id: string, enabled: boolean) => {
        try {
            const response = await fetch(`/api/skills/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled }),
            });
            if (response.ok) {
                setSkills(prev => prev.map(s => s.id === id ? { ...s, enabled } : s));
            }
        } catch (err) {
            console.error('Failed to toggle skill:', err);
        }
    };

    // Delete skill
    const handleDelete = async (id: string) => {
        if (!confirm('Sei sicuro di voler eliminare questa skill?')) return;

        try {
            const response = await fetch(`/api/skills/${id}`, { method: 'DELETE' });
            if (response.ok) {
                setSkills(prev => prev.filter(s => s.id !== id));
                fetchStats();
            }
        } catch (err) {
            console.error('Failed to delete skill:', err);
        }
    };

    // Upload SKILL.md
    const handleUpload = async (file: File) => {
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/api/skills/install', {
                method: 'POST',
                body: formData,
            });
            if (response.ok) {
                fetchSkills();
                fetchStats();
            }
        } catch (err) {
            console.error('Failed to upload skill:', err);
        }
    };

    // Install from ClawHub
    const handleInstallFromClawHub = async (skill: ClawHubSkill) => {
        try {
            const response = await fetch(`/api/skills/pull/${skill.slug}`, {
                method: 'POST',
            });
            if (response.ok) {
                fetchSkills();
                fetchStats();
            }
        } catch (err) {
            console.error('Failed to install skill:', err);
        }
    };

    // Filter skills by search
    const filteredSkills = skills.filter(s =>
        s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.description.toLowerCase().includes(searchQuery.toLowerCase())
    );

    return (
        <div className="h-full flex flex-col">
            {/* Header */}
            <div className="p-4 border-b border-border">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <Zap className="w-5 h-5 text-accent" />
                        <h2 className="font-semibold text-text-primary">Skills</h2>
                    </div>
                    <button
                        onClick={() => { fetchSkills(); fetchStats(); }}
                        className="btn-icon"
                        disabled={isLoading}
                    >
                        <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
                    </button>
                </div>

                {/* Stats */}
                {stats && (
                    <div className="grid grid-cols-3 gap-2 mb-4">
                        <div className="glass-panel-light p-2 rounded-lg text-center">
                            <div className="text-lg font-bold text-accent">{stats.total_explicit}</div>
                            <div className="text-xs text-text-tertiary">Explicit</div>
                        </div>
                        <div className="glass-panel-light p-2 rounded-lg text-center">
                            <div className="text-lg font-bold text-purple-400">{stats.total_crystallized}</div>
                            <div className="text-xs text-text-tertiary">Crystallized</div>
                        </div>
                        <div className="glass-panel-light p-2 rounded-lg text-center">
                            <div className="text-lg font-bold text-text-primary">{Math.round((stats.avg_success_rate || 0) * 100)}%</div>
                            <div className="text-xs text-text-tertiary">Success</div>
                        </div>
                    </div>
                )}

                {/* Tabs */}
                <div className="flex gap-1 p-1 bg-bg-tertiary rounded-lg">
                    {(['installed', 'clawhub', 'workspace'] as TabType[]).map(tab => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`flex-1 py-2 px-3 rounded-md text-sm font-medium transition-colors ${activeTab === tab
                                ? 'bg-accent text-white'
                                : 'text-text-secondary hover:text-text-primary'
                                }`}
                        >
                            {tab === 'installed' && 'Installed'}
                            {tab === 'clawhub' && 'ClawHub'}
                            {tab === 'workspace' && 'Workspace'}
                        </button>
                    ))}
                </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
                {activeTab === 'installed' && (
                    <>
                        {/* Search */}
                        <div className="relative mb-4">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary" />
                            <input
                                type="text"
                                placeholder="Cerca skills..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pl-10 pr-4 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent/50"
                            />
                        </div>

                        {/* Upload */}
                        <label className="flex items-center justify-center gap-2 p-3 mb-4 border-2 border-dashed border-border rounded-lg cursor-pointer hover:border-accent/50 transition-colors">
                            <Upload className="w-4 h-4 text-text-tertiary" />
                            <span className="text-sm text-text-secondary">Upload SKILL.md</span>
                            <input
                                type="file"
                                accept=".md"
                                className="hidden"
                                onChange={(e) => {
                                    const file = e.target.files?.[0];
                                    if (file) handleUpload(file);
                                }}
                            />
                        </label>

                        {/* Skills Grid */}
                        {error ? (
                            <div className="text-center text-red-400 py-8">{error}</div>
                        ) : isLoading ? (
                            <div className="text-center text-text-tertiary py-8">Caricamento...</div>
                        ) : filteredSkills.length === 0 ? (
                            <div className="text-center text-text-tertiary py-8">
                                Nessuna skill installata
                            </div>
                        ) : (
                            <div className="grid gap-3">
                                {filteredSkills.map(skill => (
                                    <SkillCard
                                        key={skill.id}
                                        skill={skill}
                                        onToggle={handleToggle}
                                        onDelete={handleDelete}
                                        onViewDetails={setSelectedSkill}
                                    />
                                ))}
                            </div>
                        )}
                    </>
                )}

                {activeTab === 'clawhub' && (
                    <ClawHubSearch onInstall={handleInstallFromClawHub} />
                )}

                {activeTab === 'workspace' && (
                    <div className="text-center text-text-tertiary py-8">
                        <CloudDownload className="w-8 h-8 mx-auto mb-2 opacity-50" />
                        <p>Workspace sync coming soon</p>
                        <p className="text-xs mt-1">~/.persan/workspace/skills/</p>
                    </div>
                )}
            </div>

            {/* Skill Details Modal */}
            {selectedSkill && (
                <div
                    className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
                    onClick={() => setSelectedSkill(null)}
                >
                    <div
                        className="glass-panel max-w-lg w-full max-h-[80vh] overflow-y-auto rounded-2xl p-6"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <h3 className="text-lg font-semibold text-text-primary mb-2">
                            {selectedSkill.name}
                        </h3>
                        <span className={`inline-block text-xs px-2 py-0.5 rounded-full mb-4 ${selectedSkill.type === 'crystallized'
                            ? 'bg-purple-500/20 text-purple-400'
                            : 'bg-accent/20 text-accent'
                            }`}>
                            {selectedSkill.type}
                        </span>
                        <p className="text-text-secondary mb-4">{selectedSkill.description}</p>
                        <div className="grid grid-cols-2 gap-4 text-sm">
                            <div>
                                <span className="text-text-tertiary">Versione:</span>
                                <span className="text-text-primary ml-2">{selectedSkill.version || 'N/A'}</span>
                            </div>
                            <div>
                                <span className="text-text-tertiary">Utilizzi:</span>
                                <span className="text-text-primary ml-2">{selectedSkill.usage_count}</span>
                            </div>
                            <div>
                                <span className="text-text-tertiary">Successi:</span>
                                <span className="text-text-primary ml-2">{selectedSkill.success_count}</span>
                            </div>
                            <div>
                                <span className="text-text-tertiary">Success Rate:</span>
                                <span className="text-text-primary ml-2">{Math.round((selectedSkill.success_rate || 0) * 100)}%</span>
                            </div>
                        </div>
                        <button
                            onClick={() => setSelectedSkill(null)}
                            className="btn-primary w-full mt-6"
                        >
                            Chiudi
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}

export default SkillsPanel;
