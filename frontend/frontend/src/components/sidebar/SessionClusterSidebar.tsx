'use client';

/**
 * SessionClusterSidebar — Cluster tematici delle sessioni.
 *
 * Mostra le sessioni organizzate in cluster semantici dal Knowledge Graph.
 * Fallback alla lista piatta cronologica se il grafo non è disponibile.
 */

import { useState, useMemo, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';
import {
    Network,
    ChevronDown,
    ChevronRight,
    Search,
    MessageSquare,
    Sparkles,
} from 'lucide-react';
import { useSessionClusters, useSessionSearch, type SessionCluster, type SessionSearchResult } from '@/hooks/useSessionGraph';
import { useLayout } from '@/components/layout/DashboardLayout';

interface Props {
    onSelectSession: (sessionId: string) => void;
    activeSessionId?: string | null;
}

export default function SessionClusterSidebar({ onSelectSession, activeSessionId }: Props) {
    const { isMobile, closeAll } = useLayout();
    const { data: clusters, loading } = useSessionClusters();
    const { results: searchResults, loading: searching, search, clear } = useSessionSearch();
    const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());
    const [searchQuery, setSearchQuery] = useState('');

    const toggleCluster = (id: string) => {
        setExpandedClusters((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            return next;
        });
    };

    const handleSearch = (q: string) => {
        setSearchQuery(q);
        if (q.length >= 3) {
            search(q);
        } else {
            clear();
        }
    };

    const isSearching = searchQuery.length >= 3;

    const hasAutoExpanded = useRef(false);

    // Expand all clusters initially - Safe useEffect with Ref guard
    useEffect(() => {
        const clusterData = clusters ?? [];
        if (!isSearching && clusterData.length > 0 && !hasAutoExpanded.current) {
            hasAutoExpanded.current = true;
            setExpandedClusters(new Set(clusterData.map((c: SessionCluster) => c.id)));
        }
    }, [clusters, isSearching]); // Removed expandedClusters.size to prevent loop

    return (
        <div className="session-cluster-sidebar">
            {/* Search bar */}
            <div className="cluster-search">
                <Search size={14} className="cluster-search-icon" />
                <input
                    type="text"
                    placeholder="Cerca nelle sessioni..."
                    value={searchQuery}
                    onChange={(e) => handleSearch(e.target.value)}
                    className="cluster-search-input"
                />
            </div>

            {/* Search Results */}
            {isSearching && (
                <div className="cluster-search-results">
                    <div className="cluster-search-header">
                        <Sparkles size={12} />
                        <span>Risultati semantici</span>
                    </div>
                    {searching ? (
                        <div className="cluster-loading">Ricerca in corso...</div>
                    ) : searchResults.length === 0 ? (
                        <div className="cluster-empty">Nessun risultato</div>
                    ) : (
                        searchResults.map((r) => (
                            <SearchResultItem
                                key={r.sessionId}
                                result={r}
                                isActive={r.sessionId === activeSessionId}
                                onSelect={() => {
                                    onSelectSession(r.sessionId);
                                    if (isMobile) closeAll();
                                }}
                            />
                        ))
                    )}
                </div>
            )}

            {/* Cluster tree */}
            {!isSearching && (
                <div className="cluster-tree">
                    {loading ? (
                        <div className="cluster-loading">
                            <Network size={16} className="cluster-loading-icon" />
                            Caricamento cluster...
                        </div>
                    ) : (clusters ?? []).length === 0 ? (
                        <div className="cluster-empty">
                            <Network size={20} className="cluster-empty-icon" />
                            <span>Nessun cluster ancora. Le sessioni verranno organizzate automaticamente.</span>
                        </div>
                    ) : (
                        <AnimatePresence>
                            {(clusters ?? []).map((cluster: SessionCluster) => (
                                <motion.div
                                    key={cluster.id}
                                    initial={{ opacity: 0, y: 6 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0 }}
                                    className="cluster-group"
                                >
                                    {/* Cluster header */}
                                    <button
                                        onClick={() => toggleCluster(cluster.id)}
                                        className="cluster-header"
                                    >
                                        <span className="cluster-toggle">
                                            {expandedClusters.has(cluster.id)
                                                ? <ChevronDown size={14} />
                                                : <ChevronRight size={14} />}
                                        </span>
                                        <Network size={13} className="cluster-icon" />
                                        <span className="cluster-name">{cluster.name}</span>
                                        <span className="cluster-count">{cluster.sessionCount}</span>
                                    </button>

                                    {/* Topic tags */}
                                    {expandedClusters.has(cluster.id) && (cluster.topics?.length ?? 0) > 0 && (
                                        <div className="cluster-topics">
                                            {(cluster.topics || []).slice(0, 4).map((t) => (
                                                <span key={t} className="cluster-topic-tag">{t}</span>
                                            ))}
                                        </div>
                                    )}

                                    {/* Sessions in cluster */}
                                    <AnimatePresence>
                                        {expandedClusters.has(cluster.id) && (
                                            <motion.div
                                                initial={{ height: 0, opacity: 0 }}
                                                animate={{ height: 'auto', opacity: 1 }}
                                                exit={{ height: 0, opacity: 0 }}
                                                transition={{ duration: 0.2 }}
                                                className="cluster-sessions"
                                            >
                                                {(cluster.sessionIds || []).map((sid) => (
                                                    <button
                                                        key={sid}
                                                        onClick={() => {
                                                            if (sid) onSelectSession(sid);
                                                            if (isMobile) closeAll();
                                                        }}
                                                        className={clsx('cluster-session-item', {
                                                            'cluster-session-active': sid === activeSessionId,
                                                        })}
                                                    >
                                                        <MessageSquare size={12} />
                                                        <span className="cluster-session-id">
                                                            {typeof sid === 'string' ? sid.slice(0, 8) : 'Session'}...
                                                        </span>
                                                    </button>
                                                ))}
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                    )}
                </div>
            )}
        </div>
    );
}

// ── Sub-components ───────────────────────────────────────────────────

function SearchResultItem({
    result,
    isActive,
    onSelect,
}: {
    result: SessionSearchResult;
    isActive: boolean;
    onSelect: () => void;
}) {
    return (
        <button
            onClick={() => onSelect()}
            className={clsx('search-result-item', { 'search-result-active': isActive })}
        >
            <div className="search-result-header">
                <span className="search-result-title">{result.title}</span>
                <span className="search-result-score">
                    {Math.round((result.score || 0) * 100)}%
                </span>
            </div>
            {result.topics && result.topics.length > 0 && (
                <div className="search-result-topics">
                    {result.topics.slice(0, 3).map((t) => (
                        <span key={t} className="search-result-tag">{t}</span>
                    ))}
                </div>
            )}
            <div className="search-result-meta">
                <span>{result.turnCount || 0} messaggi</span>
                {result.clusterName && <span>• {result.clusterName}</span>}
            </div>
        </button>
    );
}
