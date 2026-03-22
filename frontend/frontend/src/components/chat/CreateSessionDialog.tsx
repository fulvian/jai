/**
 * CreateSessionDialog - Dialog modale per creare una nuova sessione categorizzata.
 *
 * Supporta tre tipi di sessione:
 * - Free: conversazione libera (default)
 * - Topic: sessione focalizzata su un argomento con tags
 * - Template: sessione con prompt predefiniti riutilizzabili
 */

'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import type { SessionType, SessionConfig, TemplatePrompt } from '@/types/chat';
import { useChatStore } from '@/stores/useChatStore';

interface CreateSessionDialogProps {
    isOpen: boolean;
    onClose: () => void;
    onSessionCreated?: (sessionId: string) => void;
}

interface SessionTypeCard {
    type: SessionType;
    icon: string;
    label: string;
    description: string;
    gradient: string;
}

const SESSION_TYPES: SessionTypeCard[] = [
    {
        type: 'free',
        icon: '💬',
        label: 'Chat Libera',
        description: 'Conversazione senza vincoli su qualsiasi argomento',
        gradient: 'linear-gradient(135deg, rgba(0,122,255,0.15), rgba(88,86,214,0.1))',
    },
    {
        type: 'topic',
        icon: '🎯',
        label: 'Per Argomento',
        description: 'Sessione focalizzata su un tema specifico di ricerca',
        gradient: 'linear-gradient(135deg, rgba(52,199,89,0.15), rgba(0,199,190,0.1))',
    },
    {
        type: 'template',
        icon: '⚡',
        label: 'Da Template',
        description: 'Prompt predefiniti riutilizzabili per task ricorrenti',
        gradient: 'linear-gradient(135deg, rgba(175,82,222,0.15), rgba(255,55,95,0.1))',
    },
];

function generatePromptId(): string {
    return `prompt-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export default function CreateSessionDialog({
    isOpen,
    onClose,
    onSessionCreated,
}: CreateSessionDialogProps) {
    const createNewSession = useChatStore((s) => s.createNewSession);

    const [selectedType, setSelectedType] = useState<SessionType>('free');
    const [topicName, setTopicName] = useState('');
    const [tagInput, setTagInput] = useState('');
    const [tags, setTags] = useState<string[]>([]);
    const [prompts, setPrompts] = useState<TemplatePrompt[]>([]);
    const [newPromptLabel, setNewPromptLabel] = useState('');
    const [newPromptContent, setNewPromptContent] = useState('');
    const [isCreating, setIsCreating] = useState(false);

    const dialogRef = useRef<HTMLDialogElement>(null);

    useEffect(() => {
        if (isOpen) {
            dialogRef.current?.showModal();
        } else {
            dialogRef.current?.close();
        }
    }, [isOpen]);

    const resetForm = useCallback(() => {
        setSelectedType('free');
        setTopicName('');
        setTagInput('');
        setTags([]);
        setPrompts([]);
        setNewPromptLabel('');
        setNewPromptContent('');
    }, []);

    const handleClose = useCallback(() => {
        resetForm();
        onClose();
    }, [onClose, resetForm]);

    const handleAddTag = useCallback(() => {
        const trimmed = tagInput.trim();
        if (trimmed && !tags.includes(trimmed) && tags.length < 10) {
            setTags((prev) => [...prev, trimmed]);
            setTagInput('');
        }
    }, [tagInput, tags]);

    const handleRemoveTag = useCallback((tag: string) => {
        setTags((prev) => prev.filter((t) => t !== tag));
    }, []);

    const handleAddPrompt = useCallback(() => {
        if (!newPromptLabel.trim() || !newPromptContent.trim()) return;
        const now = new Date().toISOString();
        const prompt: TemplatePrompt = {
            id: generatePromptId(),
            label: newPromptLabel.trim(),
            content: newPromptContent.trim(),
            enabled: true,
            createdAt: now,
            updatedAt: now,
        };
        setPrompts((prev) => [...prev, prompt]);
        setNewPromptLabel('');
        setNewPromptContent('');
    }, [newPromptLabel, newPromptContent]);

    const handleRemovePrompt = useCallback((promptId: string) => {
        setPrompts((prev) => prev.filter((p) => p.id !== promptId));
    }, []);

    const handleCreate = useCallback(async () => {
        setIsCreating(true);
        try {
            const config: SessionConfig = { type: selectedType };

            if (selectedType === 'topic') {
                if (topicName.trim()) config.topic = topicName.trim();
                if (tags.length > 0) config.tags = tags;
            } else if (selectedType === 'template') {
                if (prompts.length > 0) config.prompts = prompts;
            }

            const sessionId = await createNewSession(
                selectedType === 'free' ? undefined : config
            );

            if (sessionId) {
                onSessionCreated?.(sessionId);
                handleClose();
            }
        } finally {
            setIsCreating(false);
        }
    }, [selectedType, topicName, tags, prompts, createNewSession, onSessionCreated, handleClose]);

    const handleKeyDown = useCallback(
        (e: React.KeyboardEvent) => {
            if (e.key === 'Escape') {
                handleClose();
            }
        },
        [handleClose]
    );

    if (!isOpen) return null;

    return (
        <dialog
            ref={dialogRef}
            className="create-session-dialog"
            onKeyDown={handleKeyDown}
            onClick={(e) => {
                if (e.target === dialogRef.current) handleClose();
            }}
        >
            <div className="dialog-content">
                {/* Header */}
                <div className="dialog-header">
                    <h2>Nuova Sessione</h2>
                    <button
                        className="close-btn"
                        onClick={handleClose}
                        aria-label="Chiudi"
                    >
                        ✕
                    </button>
                </div>

                {/* Session Type Cards */}
                <div className="type-cards">
                    {SESSION_TYPES.map((st) => (
                        <button
                            key={st.type}
                            className={`type-card ${selectedType === st.type ? 'selected' : ''}`}
                            onClick={() => setSelectedType(st.type)}
                            style={{ '--card-gradient': st.gradient } as React.CSSProperties}
                        >
                            <span className="type-icon">{st.icon}</span>
                            <span className="type-label">{st.label}</span>
                            <span className="type-desc">{st.description}</span>
                        </button>
                    ))}
                </div>

                {/* Topic Config */}
                {selectedType === 'topic' && (
                    <div className="config-section topic-config">
                        <label className="config-label">Argomento</label>
                        <input
                            type="text"
                            className="config-input"
                            placeholder="Es. Machine Learning, React Architecture..."
                            value={topicName}
                            onChange={(e) => setTopicName(e.target.value)}
                            autoFocus
                        />

                        <label className="config-label">Tags</label>
                        <div className="tags-input-row">
                            <input
                                type="text"
                                className="config-input tags-input"
                                placeholder="Aggiungi tag..."
                                value={tagInput}
                                onChange={(e) => setTagInput(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') {
                                        e.preventDefault();
                                        handleAddTag();
                                    }
                                }}
                            />
                            <button
                                className="add-tag-btn"
                                onClick={handleAddTag}
                                disabled={!tagInput.trim()}
                            >
                                +
                            </button>
                        </div>
                        {tags.length > 0 && (
                            <div className="tags-list">
                                {tags.map((tag) => (
                                    <span key={tag} className="tag-chip">
                                        {tag}
                                        <button
                                            onClick={() => handleRemoveTag(tag)}
                                            className="tag-remove"
                                        >
                                            ✕
                                        </button>
                                    </span>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* Template Config */}
                {selectedType === 'template' && (
                    <div className="config-section template-config">
                        <label className="config-label">Prompt Template</label>

                        {/* Existing prompts */}
                        {prompts.length > 0 && (
                            <div className="prompts-list">
                                {prompts.map((p) => (
                                    <div key={p.id} className="prompt-chip">
                                        <span className="prompt-chip-label">{p.label}</span>
                                        <button
                                            onClick={() => handleRemovePrompt(p.id)}
                                            className="prompt-chip-remove"
                                        >
                                            ✕
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Add new prompt */}
                        <div className="add-prompt-form">
                            <input
                                type="text"
                                className="config-input"
                                placeholder="Nome prompt..."
                                value={newPromptLabel}
                                onChange={(e) => setNewPromptLabel(e.target.value)}
                            />
                            <textarea
                                className="config-textarea"
                                placeholder="Contenuto prompt..."
                                value={newPromptContent}
                                onChange={(e) => setNewPromptContent(e.target.value)}
                                rows={3}
                            />
                            <button
                                className="add-prompt-btn"
                                onClick={handleAddPrompt}
                                disabled={!newPromptLabel.trim() || !newPromptContent.trim()}
                            >
                                + Aggiungi Prompt
                            </button>
                        </div>
                    </div>
                )}

                {/* Footer */}
                <div className="dialog-footer">
                    <button className="cancel-btn" onClick={handleClose}>
                        Annulla
                    </button>
                    <button
                        className="create-btn"
                        onClick={handleCreate}
                        disabled={isCreating}
                    >
                        {isCreating ? 'Creando...' : 'Crea Sessione'}
                    </button>
                </div>
            </div>
        </dialog>
    );
}
