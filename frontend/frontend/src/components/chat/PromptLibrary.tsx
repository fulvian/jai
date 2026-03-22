'use client';

/**
 * PromptLibrary — Libreria prompt navigabile.
 *
 * Mostra i prompt template con ricerca semantica e CRUD.
 * Si integra con il Session Knowledge Graph per suggerimenti contestuali.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { clsx } from 'clsx';
import {
    BookOpen,
    Search,
    Plus,
    Edit3,
    Copy,
    Trash2,
    X,
    Tag,
    Sparkles,
    Loader2,
    Check,
} from 'lucide-react';
import { usePromptLibrary, type PromptTemplate } from '@/hooks/useSessionGraph';

interface Props {
    isOpen: boolean;
    onClose: () => void;
    onUsePrompt: (content: string) => void;
    currentSessionId?: string | null;
}

export default function PromptLibrary({ isOpen, onClose, onUsePrompt, currentSessionId }: Props) {
    const { prompts, loading, fetchPrompts, savePrompt, searchPrompts } = usePromptLibrary();
    const [searchQuery, setSearchQuery] = useState('');
    const [showEditor, setShowEditor] = useState(false);
    const [editingPrompt, setEditingPrompt] = useState<Partial<PromptTemplate> | null>(null);
    const [copiedId, setCopiedId] = useState<string | null>(null);
    const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Cleanup timer on unmount
    useEffect(() => {
        return () => {
            if (copyTimerRef.current) {
                clearTimeout(copyTimerRef.current);
            }
        };
    }, []);

    const handleSearch = useCallback((q: string) => {
        setSearchQuery(q);
        if (q.length >= 2) {
            searchPrompts(q);
        } else {
            fetchPrompts();
        }
    }, [searchPrompts, fetchPrompts]);

    const handleUsePrompt = (prompt: PromptTemplate) => {
        let content = prompt.content;
        // Replace variables with placeholders
        if (prompt.variables?.length) {
            prompt.variables.forEach((v) => {
                content = content.replaceAll(`{{${v}}}`, `[inserisci ${v}]`);
            });
        }
        onUsePrompt(content);
    };

    const handleCopy = async (prompt: PromptTemplate) => {
        await navigator.clipboard.writeText(prompt.content);
        setCopiedId(prompt.id);
        if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
        copyTimerRef.current = setTimeout(() => setCopiedId(null), 1500);
    };

    const handleSave = async () => {
        if (!editingPrompt?.label || !editingPrompt?.content) return;
        await savePrompt({
            id: editingPrompt.id ?? '',
            label: editingPrompt.label,
            content: editingPrompt.content,
            category: editingPrompt.category ?? 'general',
            topics: editingPrompt.topics ?? [],
            variables: editingPrompt.variables ?? [],
        });
        setShowEditor(false);
        setEditingPrompt(null);
    };

    if (!isOpen) return null;

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="prompt-library-overlay"
            onClick={(e) => {
                if (e.target === e.currentTarget) onClose();
            }}
        >
            <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 20 }}
                transition={{ duration: 0.2 }}
                className="prompt-library"
            >
                {/* Header */}
                <div className="prompt-library-header">
                    <div className="prompt-library-title">
                        <BookOpen size={18} />
                        <h2>Libreria Prompt</h2>
                    </div>
                    <div className="prompt-library-actions">
                        <button
                            onClick={() => {
                                setEditingPrompt({ category: 'general', variables: [], topics: [] });
                                setShowEditor(true);
                            }}
                            className="prompt-btn prompt-btn-primary"
                        >
                            <Plus size={14} />
                            <span>Nuovo</span>
                        </button>
                        <button onClick={onClose} className="prompt-btn prompt-btn-ghost">
                            <X size={16} />
                        </button>
                    </div>
                </div>

                {/* Search */}
                <div className="prompt-search">
                    <Search size={14} className="prompt-search-icon" />
                    <input
                        type="text"
                        placeholder="Cerca prompt..."
                        value={searchQuery}
                        onChange={(e) => handleSearch(e.target.value)}
                        className="prompt-search-input"
                    />
                    {loading && <Loader2 size={14} className="prompt-search-spinner" />}
                </div>

                {/* Prompt list */}
                <div className="prompt-list">
                    {prompts.length === 0 ? (
                        <div className="prompt-empty">
                            <BookOpen size={32} className="prompt-empty-icon" />
                            <p>Nessun prompt salvato.</p>
                            <p className="prompt-empty-hint">
                                Crea il tuo primo prompt template per riutilizzarlo nelle sessioni.
                            </p>
                        </div>
                    ) : (
                        <AnimatePresence>
                            {prompts.map((prompt, i) => (
                                <motion.div
                                    key={prompt.id}
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0 }}
                                    transition={{ delay: i * 0.03 }}
                                    className="prompt-card"
                                >
                                    <div className="prompt-card-header">
                                        <h3 className="prompt-card-label">{prompt.label}</h3>
                                        <div className="prompt-card-actions">
                                            <button
                                                onClick={() => handleUsePrompt(prompt)}
                                                className="prompt-action-btn prompt-action-use"
                                                title="Usa questo prompt"
                                            >
                                                <Sparkles size={12} />
                                                <span>Usa</span>
                                            </button>
                                            <button
                                                onClick={() => handleCopy(prompt)}
                                                className="prompt-action-btn"
                                                title="Copia"
                                            >
                                                {copiedId === prompt.id
                                                    ? <Check size={12} className="prompt-copied" />
                                                    : <Copy size={12} />}
                                            </button>
                                            <button
                                                onClick={() => {
                                                    setEditingPrompt(prompt);
                                                    setShowEditor(true);
                                                }}
                                                className="prompt-action-btn"
                                                title="Modifica"
                                            >
                                                <Edit3 size={12} />
                                            </button>
                                        </div>
                                    </div>

                                    <p className="prompt-card-content">
                                        {prompt.content.length > 120
                                            ? prompt.content.slice(0, 120) + '...'
                                            : prompt.content}
                                    </p>

                                    <div className="prompt-card-footer">
                                        <span className="prompt-category">{prompt.category}</span>
                                        {prompt.variables?.length > 0 && (
                                            <span className="prompt-vars">
                                                {prompt.variables.length} variabili
                                            </span>
                                        )}
                                        {prompt.topics.slice(0, 2).map((t) => (
                                            <span key={t} className="prompt-topic">{t}</span>
                                        ))}
                                        <span className="prompt-usage">
                                            Usato {prompt.usageCount}x
                                        </span>
                                    </div>
                                </motion.div>
                            ))}
                        </AnimatePresence>
                    )}
                </div>

                {/* Editor modal */}
                <AnimatePresence>
                    {showEditor && editingPrompt && (
                        <PromptEditor
                            prompt={editingPrompt}
                            onChange={setEditingPrompt}
                            onSave={handleSave}
                            onCancel={() => { setShowEditor(false); setEditingPrompt(null); }}
                        />
                    )}
                </AnimatePresence>
            </motion.div>
        </motion.div>
    );
}

// ── Prompt Editor ────────────────────────────────────────────────────

function PromptEditor({
    prompt,
    onChange,
    onSave,
    onCancel,
}: {
    prompt: Partial<PromptTemplate>;
    onChange: (p: Partial<PromptTemplate>) => void;
    onSave: () => void;
    onCancel: () => void;
}) {
    const [newVar, setNewVar] = useState('');
    const [newTopic, setNewTopic] = useState('');

    const addVariable = () => {
        if (!newVar.trim()) return;
        onChange({ ...prompt, variables: [...(prompt.variables ?? []), newVar.trim()] });
        setNewVar('');
    };

    const addTopic = () => {
        if (!newTopic.trim()) return;
        onChange({ ...prompt, topics: [...(prompt.topics ?? []), newTopic.trim()] });
        setNewTopic('');
    };

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="prompt-editor-overlay"
        >
            <motion.div
                initial={{ scale: 0.95 }}
                animate={{ scale: 1 }}
                className="prompt-editor"
            >
                <h3 className="prompt-editor-title">
                    {prompt.id ? 'Modifica Prompt' : 'Nuovo Prompt'}
                </h3>

                <div className="prompt-editor-field">
                    <label>Nome</label>
                    <input
                        type="text"
                        value={prompt.label ?? ''}
                        onChange={(e) => onChange({ ...prompt, label: e.target.value })}
                        placeholder="Es: Analisi di mercato"
                    />
                </div>

                <div className="prompt-editor-field">
                    <label>Categoria</label>
                    <select
                        value={prompt.category ?? 'general'}
                        onChange={(e) => onChange({ ...prompt, category: e.target.value })}
                    >
                        <option value="general">Generale</option>
                        <option value="research">Ricerca</option>
                        <option value="analysis">Analisi</option>
                        <option value="writing">Scrittura</option>
                        <option value="coding">Codice</option>
                        <option value="creative">Creativo</option>
                    </select>
                </div>

                <div className="prompt-editor-field">
                    <label>Contenuto</label>
                    <textarea
                        value={prompt.content ?? ''}
                        onChange={(e) => onChange({ ...prompt, content: e.target.value })}
                        placeholder="Scrivi il tuo prompt. Usa {{variabile}} per parti dinamiche."
                        rows={6}
                    />
                </div>

                {/* Variables */}
                <div className="prompt-editor-field">
                    <label>Variabili</label>
                    <div className="prompt-editor-tags">
                        {(prompt.variables ?? []).map((v) => (
                            <span key={v} className="prompt-editor-tag">
                                {`{{${v}}}`}
                                <button
                                    onClick={() =>
                                        onChange({
                                            ...prompt,
                                            variables: (prompt.variables ?? []).filter((x) => x !== v),
                                        })
                                    }
                                >
                                    <X size={10} />
                                </button>
                            </span>
                        ))}
                        <div className="prompt-editor-tag-input">
                            <input
                                type="text"
                                value={newVar}
                                onChange={(e) => setNewVar(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && addVariable()}
                                placeholder="Nuova variabile..."
                            />
                            <button onClick={addVariable}>
                                <Plus size={12} />
                            </button>
                        </div>
                    </div>
                </div>

                {/* Topics */}
                <div className="prompt-editor-field">
                    <label>Topic</label>
                    <div className="prompt-editor-tags">
                        {(prompt.topics ?? []).map((t) => (
                            <span key={t} className="prompt-editor-tag prompt-editor-tag-topic">
                                <Tag size={10} />
                                {t}
                                <button
                                    onClick={() =>
                                        onChange({
                                            ...prompt,
                                            topics: (prompt.topics ?? []).filter((x) => x !== t),
                                        })
                                    }
                                >
                                    <X size={10} />
                                </button>
                            </span>
                        ))}
                        <div className="prompt-editor-tag-input">
                            <input
                                type="text"
                                value={newTopic}
                                onChange={(e) => setNewTopic(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && addTopic()}
                                placeholder="Nuovo topic..."
                            />
                            <button onClick={addTopic}>
                                <Plus size={12} />
                            </button>
                        </div>
                    </div>
                </div>

                <div className="prompt-editor-actions">
                    <button onClick={onCancel} className="prompt-btn prompt-btn-ghost">
                        Annulla
                    </button>
                    <button
                        onClick={onSave}
                        disabled={!prompt.label || !prompt.content}
                        className="prompt-btn prompt-btn-primary"
                    >
                        Salva
                    </button>
                </div>
            </motion.div>
        </motion.div>
    );
}
