'use client';

/**
 * RelatedSessions — Pannello sessioni correlate.
 *
 * Mostra sessioni semanticamente simili alla sessione corrente.
 * Appare come card compatta nella chat area.
 */

import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';
import {
    Link2,
    MessageSquare,
    ChevronRight,
    Loader2,
} from 'lucide-react';
import { useRelatedSessions, type SessionSearchResult } from '@/hooks/useSessionGraph';

interface Props {
    sessionId: string | null;
    onSelectSession: (sessionId: string) => void;
}

export default function RelatedSessions({ sessionId, onSelectSession }: Props) {
    const { data: related, loading } = useRelatedSessions(sessionId);

    if (!sessionId || ((related ?? []).length === 0 && !loading)) return null;

    return (
        <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="related-sessions"
        >
            <div className="related-header">
                <Link2 size={14} />
                <span>Sessioni correlate</span>
                {loading && <Loader2 size={12} className="related-spinner" />}
            </div>

            <AnimatePresence>
                {(related ?? []).map((r: SessionSearchResult, i: number) => (
                    <motion.button
                        key={r.sessionId}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: i * 0.05 }}
                        onClick={() => onSelectSession(r.sessionId)}
                        className="related-item"
                    >
                        <div className="related-item-left">
                            <MessageSquare size={12} className="related-item-icon" />
                            <div className="related-item-info">
                                <span className="related-item-title">{r.title}</span>
                                <div className="related-item-meta">
                                    {r.topics.slice(0, 2).map((t) => (
                                        <span key={t} className="related-topic-tag">{t}</span>
                                    ))}
                                    <span className="related-item-turns">
                                        {r.turnCount} msg
                                    </span>
                                </div>
                            </div>
                        </div>
                        <div className="related-item-right">
                            <div
                                className="related-score-bar"
                                title={`Similarità: ${Math.round(r.score * 100)}%`}
                            >
                                <div
                                    className="related-score-fill"
                                    style={{ width: `${Math.round(r.score * 100)}%` }}
                                />
                            </div>
                            <ChevronRight size={12} className="related-chevron" />
                        </div>
                    </motion.button>
                ))}
            </AnimatePresence>
        </motion.div>
    );
}
