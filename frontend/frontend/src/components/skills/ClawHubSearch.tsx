/**
 * ClawHubSearch - Componente per ricerca skills su ClawHub.ai
 */

'use client';

import { useState, useCallback } from 'react';
import { Search, Download, ExternalLink, Star, Tag } from 'lucide-react';

export interface ClawHubSkill {
    slug: string;
    name: string;
    description: string;
    author?: string;
    stars: number;
    tags: string[];
}

interface ClawHubSearchProps {
    onInstall: (skill: ClawHubSkill) => Promise<void>;
}

export function ClawHubSearch({ onInstall }: ClawHubSearchProps) {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<ClawHubSkill[]>([]);
    const [isSearching, setIsSearching] = useState(false);
    const [installingSlug, setInstallingSlug] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const handleSearch = useCallback(async () => {
        if (!query.trim()) return;

        setIsSearching(true);
        setError(null);

        try {
            const response = await fetch(`/api/skills/search/clawhub?q=${encodeURIComponent(query)}`);
            if (!response.ok) throw new Error('Search failed');

            const data = await response.json();
            setResults(data.results || []);

            if (data.results?.length === 0) {
                setError('Nessun risultato trovato. ClawHub API potrebbe non essere disponibile.');
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Search error');
        } finally {
            setIsSearching(false);
        }
    }, [query]);

    const handleInstall = async (skill: ClawHubSkill) => {
        setInstallingSlug(skill.slug);
        try {
            await onInstall(skill);
        } finally {
            setInstallingSlug(null);
        }
    };

    return (
        <div>
            {/* Search Bar */}
            <div className="flex gap-2 mb-4">
                <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary" />
                    <input
                        type="text"
                        placeholder="Cerca su ClawHub.ai..."
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                        className="w-full pl-10 pr-4 py-2 bg-bg-tertiary border border-border rounded-lg text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent/50"
                    />
                </div>
                <button
                    onClick={handleSearch}
                    disabled={isSearching || !query.trim()}
                    className="btn-primary px-4 py-2 flex items-center gap-2"
                >
                    {isSearching ? (
                        <span className="animate-spin">⌛</span>
                    ) : (
                        <Search className="w-4 h-4" />
                    )}
                    Cerca
                </button>
            </div>

            {/* Info Banner */}
            <div className="glass-panel-light p-3 rounded-lg mb-4 text-xs text-text-secondary">
                <p>
                    <ExternalLink className="w-3 h-3 inline mr-1" />
                    Sfoglia le 700+ skills su{' '}
                    <a
                        href="https://clawhub.ai/skills"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent hover:underline"
                    >
                        clawhub.ai/skills
                    </a>
                </p>
            </div>

            {/* Error */}
            {error && (
                <div className="text-center text-yellow-400 py-4 text-sm">
                    {error}
                </div>
            )}

            {/* Results */}
            {results.length > 0 && (
                <div className="space-y-3">
                    {results.map((skill) => (
                        <div
                            key={skill.slug}
                            className="glass-panel p-4 rounded-xl"
                        >
                            <div className="flex items-start justify-between mb-2">
                                <div>
                                    <h3 className="font-medium text-text-primary">{skill.name}</h3>
                                    {skill.author && (
                                        <span className="text-xs text-text-tertiary">@{skill.author}</span>
                                    )}
                                </div>
                                <div className="flex items-center gap-1 text-xs text-text-tertiary">
                                    <Star className="w-3 h-3" />
                                    <span>{skill.stars}</span>
                                </div>
                            </div>

                            <p className="text-sm text-text-secondary mb-3 line-clamp-2">
                                {skill.description}
                            </p>

                            {/* Tags */}
                            {skill.tags.length > 0 && (
                                <div className="flex flex-wrap gap-1 mb-3">
                                    {skill.tags.slice(0, 3).map((tag) => (
                                        <span
                                            key={tag}
                                            className="inline-flex items-center gap-0.5 px-2 py-0.5 bg-bg-tertiary rounded text-xs text-text-tertiary"
                                        >
                                            <Tag className="w-2.5 h-2.5" />
                                            {tag}
                                        </span>
                                    ))}
                                </div>
                            )}

                            {/* Actions */}
                            <div className="flex gap-2">
                                <button
                                    onClick={() => handleInstall(skill)}
                                    disabled={installingSlug === skill.slug}
                                    className="btn-primary flex-1 flex items-center justify-center gap-2 py-2 text-sm"
                                >
                                    {installingSlug === skill.slug ? (
                                        <>
                                            <span className="animate-spin">⌛</span>
                                            Installing...
                                        </>
                                    ) : (
                                        <>
                                            <Download className="w-4 h-4" />
                                            Install
                                        </>
                                    )}
                                </button>
                                <a
                                    href={`https://clawhub.ai/skills/${skill.slug}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="btn-icon px-3"
                                >
                                    <ExternalLink className="w-4 h-4" />
                                </a>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Empty State */}
            {!isSearching && results.length === 0 && !error && (
                <div className="text-center text-text-tertiary py-8">
                    <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p>Cerca skills su ClawHub.ai</p>
                    <p className="text-xs mt-1">Es: "weather", "finance", "calendar"</p>
                </div>
            )}
        </div>
    );
}

export default ClawHubSearch;
