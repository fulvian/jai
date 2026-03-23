/**
 * GraphExplorer — Dropdown di esplorazione nodi connessi nel Knowledge Graph.
 *
 * Per ogni sessione mostra i top-3 nodi (topic, sessioni 2-hop, cluster)
 * più connessi, permettendo esplorazione esterna dal contesto corrente.
 *
 * Design: macOS Tahoe Liquid Glass, interazioni animate con framer-motion.
 */

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useConnectedNodes, ConnectedNode } from '../../hooks/useSessionGraph';

// ── Icone per tipo nodo ──────────────────────────────────────────────

const NODE_TYPE_CONFIG: Record<string, { icon: string; color: string; label: string }> = {
    topic: { icon: '🏷️', color: '#a78bfa', label: 'Topic' },
    session: { icon: '💬', color: '#60a5fa', label: 'Sessione' },
    cluster: { icon: '🧩', color: '#34d399', label: 'Cluster' },
};

// ── Props ────────────────────────────────────────────────────────────

interface GraphExplorerProps {
    sessionId: string | null;
    onNodeClick?: (node: ConnectedNode) => void;
    className?: string;
}

// ── Component ────────────────────────────────────────────────────────

export function GraphExplorer({ sessionId, onNodeClick, className = '' }: GraphExplorerProps) {
    const { data: nodes, loading } = useConnectedNodes(sessionId);
    const [isOpen, setIsOpen] = useState(false);

    if (!sessionId || ((nodes ?? []).length === 0 && !loading)) return null;

    const toggleOpen = () => setIsOpen(!isOpen);

    return (
        <div className={`graph-explorer ${className}`}>
            {/* Toggle button */}
            <button
                className="graph-explorer__toggle"
                onClick={toggleOpen}
                aria-expanded={isOpen}
                aria-label="Esplora nodi connessi nel grafo"
            >
                <span className="graph-explorer__toggle-icon">
                    🔗
                </span>
                <span className="graph-explorer__toggle-text">
                    Esplora Grafo
                </span>
                {(nodes ?? []).length > 0 && (
                    <span className="graph-explorer__badge">{(nodes ?? []).length}</span>
                )}
                <motion.span
                    className="graph-explorer__chevron"
                    animate={{ rotate: isOpen ? 180 : 0 }}
                    transition={{ duration: 0.2 }}
                >
                    ▾
                </motion.span>
            </button>

            {/* Dropdown panel */}
            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        className="graph-explorer__dropdown"
                        initial={{ opacity: 0, height: 0, y: -8 }}
                        animate={{ opacity: 1, height: 'auto', y: 0 }}
                        exit={{ opacity: 0, height: 0, y: -8 }}
                        transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
                    >
                        {loading ? (
                            <div className="graph-explorer__loading">
                                <div className="graph-explorer__spinner" />
                                <span>Analisi grafo...</span>
                            </div>
                        ) : nodes.length === 0 ? (
                            <div className="graph-explorer__empty">
                                Nessun collegamento trovato
                            </div>
                        ) : (
                            <ul className="graph-explorer__list">
                                {nodes.map((node, index) => {
                                    const config = NODE_TYPE_CONFIG[node.nodeType] ?? NODE_TYPE_CONFIG.topic;
                                    return (
                                        <motion.li
                                            key={node.id}
                                            className="graph-explorer__item"
                                            initial={{ opacity: 0, x: -16 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            transition={{ delay: index * 0.08 }}
                                            onClick={() => onNodeClick?.(node)}
                                        >
                                            <div className="graph-explorer__item-header">
                                                <span
                                                    className="graph-explorer__item-icon"
                                                    style={{ '--node-color': config.color } as React.CSSProperties}
                                                >
                                                    {config.icon}
                                                </span>
                                                <div className="graph-explorer__item-info">
                                                    <span className="graph-explorer__item-name">
                                                        {node.name}
                                                    </span>
                                                    <span className="graph-explorer__item-type">
                                                        {config.label} · {node.relationType}
                                                    </span>
                                                </div>
                                                <div className="graph-explorer__item-score">
                                                    <span className="graph-explorer__score-value">
                                                        {node.sharedSessions}
                                                    </span>
                                                    <span className="graph-explorer__score-label">
                                                        connessioni
                                                    </span>
                                                </div>
                                            </div>
                                            <p className="graph-explorer__item-desc">
                                                {node.description}
                                            </p>

                                            {/* Score bar */}
                                            <div className="graph-explorer__score-bar">
                                                <motion.div
                                                    className="graph-explorer__score-fill"
                                                    style={{
                                                        '--node-color': config.color,
                                                    } as React.CSSProperties}
                                                    initial={{ width: 0 }}
                                                    animate={{
                                                        width: `${Math.min(
                                                            (node.connectionScore / (nodes[0]?.connectionScore || 1)) * 100,
                                                            100
                                                        )}%`,
                                                    }}
                                                    transition={{ duration: 0.5, delay: index * 0.1 }}
                                                />
                                            </div>
                                        </motion.li>
                                    );
                                })}
                            </ul>
                        )}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

export default GraphExplorer;
