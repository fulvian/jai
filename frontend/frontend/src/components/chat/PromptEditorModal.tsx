/**
 * PromptEditorModal - Editor CRUD completo per prompt template.
 *
 * Features:
 * - Lista prompt con toggle enable/disable
 * - Editing inline di label e content
 * - Drag & drop per riordinamento (via data attributes)
 * - Delete on hover
 * - Aggiunta di nuovi prompt
 */

'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import type { TemplatePrompt } from '@/types/chat';

interface PromptEditorModalProps {
    isOpen: boolean;
    prompts: TemplatePrompt[];
    onClose: () => void;
    onSave: (prompts: TemplatePrompt[]) => void;
}

function generatePromptId(): string {
    return `prompt-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export default function PromptEditorModal({
    isOpen,
    prompts: initialPrompts,
    onClose,
    onSave,
}: PromptEditorModalProps) {
    const [editablePrompts, setEditablePrompts] = useState<TemplatePrompt[]>([]);
    const [editingId, setEditingId] = useState<string | null>(null);
    const [newLabel, setNewLabel] = useState('');
    const [newContent, setNewContent] = useState('');
    const [draggedId, setDraggedId] = useState<string | null>(null);

    const dialogRef = useRef<HTMLDialogElement>(null);

    useEffect(() => {
        if (isOpen) {
            setEditablePrompts([...initialPrompts]);
            dialogRef.current?.showModal();
        } else {
            dialogRef.current?.close();
        }
    }, [isOpen, initialPrompts]);

    const handleToggle = useCallback((promptId: string) => {
        setEditablePrompts((prev) =>
            prev.map((p) => (p.id === promptId ? { ...p, enabled: !p.enabled } : p))
        );
    }, []);

    const handleDelete = useCallback((promptId: string) => {
        setEditablePrompts((prev) => prev.filter((p) => p.id !== promptId));
    }, []);

    const handleEdit = useCallback(
        (promptId: string, field: 'label' | 'content', value: string) => {
            setEditablePrompts((prev) =>
                prev.map((p) =>
                    p.id === promptId
                        ? { ...p, [field]: value, updatedAt: new Date().toISOString() }
                        : p
                )
            );
        },
        []
    );

    const handleAdd = useCallback(() => {
        if (!newLabel.trim() || !newContent.trim()) return;
        const now = new Date().toISOString();
        const prompt: TemplatePrompt = {
            id: generatePromptId(),
            label: newLabel.trim(),
            content: newContent.trim(),
            enabled: true,
            createdAt: now,
            updatedAt: now,
        };
        setEditablePrompts((prev) => [...prev, prompt]);
        setNewLabel('');
        setNewContent('');
    }, [newLabel, newContent]);

    const handleDragStart = useCallback((promptId: string) => {
        setDraggedId(promptId);
    }, []);

    const handleDragOver = useCallback(
        (e: React.DragEvent, targetId: string) => {
            e.preventDefault();
            if (!draggedId || draggedId === targetId) return;

            setEditablePrompts((prev) => {
                const fromIdx = prev.findIndex((p) => p.id === draggedId);
                const toIdx = prev.findIndex((p) => p.id === targetId);
                if (fromIdx === -1 || toIdx === -1) return prev;

                const reordered = [...prev];
                const [moved] = reordered.splice(fromIdx, 1);
                reordered.splice(toIdx, 0, moved);
                return reordered;
            });
        },
        [draggedId]
    );

    const handleDragEnd = useCallback(() => {
        setDraggedId(null);
    }, []);

    const handleSave = useCallback(() => {
        onSave(editablePrompts);
        onClose();
    }, [editablePrompts, onSave, onClose]);

    if (!isOpen) return null;

    return (
        <dialog
            ref={dialogRef}
            className="prompt-editor-modal"
            onClick={(e) => {
                if (e.target === dialogRef.current) onClose();
            }}
        >
            <div className="editor-content">
                {/* Header */}
                <div className="editor-header">
                    <h2>⚡ Gestisci Prompt Template</h2>
                    <button className="close-btn" onClick={onClose} aria-label="Chiudi">
                        ✕
                    </button>
                </div>

                {/* Prompt List */}
                <div className="editor-body">
                    {editablePrompts.length === 0 && (
                        <div className="empty-state">
                            <span className="empty-icon">📝</span>
                            <p>Nessun prompt template. Aggiungine uno qui sotto.</p>
                        </div>
                    )}

                    <div className="prompts-grid">
                        {editablePrompts.map((prompt) => (
                            <div
                                key={prompt.id}
                                className={`prompt-row ${draggedId === prompt.id ? 'dragging' : ''} ${!prompt.enabled ? 'disabled' : ''
                                    }`}
                                draggable
                                onDragStart={() => handleDragStart(prompt.id)}
                                onDragOver={(e) => handleDragOver(e, prompt.id)}
                                onDragEnd={handleDragEnd}
                            >
                                {/* Drag handle */}
                                <span className="drag-handle" title="Trascina per riordinare">
                                    ⠿
                                </span>

                                {/* Toggle */}
                                <button
                                    className={`toggle-btn ${prompt.enabled ? 'on' : 'off'}`}
                                    onClick={() => handleToggle(prompt.id)}
                                    title={prompt.enabled ? 'Disabilita' : 'Abilita'}
                                >
                                    <span className="toggle-knob" />
                                </button>

                                {/* Label & Content */}
                                <div
                                    className="prompt-details"
                                    onClick={() => setEditingId(editingId === prompt.id ? null : prompt.id)}
                                >
                                    {editingId === prompt.id ? (
                                        <>
                                            <input
                                                className="edit-label-input"
                                                value={prompt.label}
                                                onChange={(e) =>
                                                    handleEdit(prompt.id, 'label', e.target.value)
                                                }
                                                onClick={(e) => e.stopPropagation()}
                                                autoFocus
                                            />
                                            <textarea
                                                className="edit-content-textarea"
                                                value={prompt.content}
                                                onChange={(e) =>
                                                    handleEdit(prompt.id, 'content', e.target.value)
                                                }
                                                onClick={(e) => e.stopPropagation()}
                                                rows={3}
                                            />
                                        </>
                                    ) : (
                                        <>
                                            <span className="prompt-label-text">{prompt.label}</span>
                                            <span className="prompt-content-preview">
                                                {prompt.content.length > 80
                                                    ? `${prompt.content.slice(0, 80)}...`
                                                    : prompt.content}
                                            </span>
                                        </>
                                    )}
                                </div>

                                {/* Delete */}
                                <button
                                    className="delete-btn"
                                    onClick={() => handleDelete(prompt.id)}
                                    title="Elimina"
                                >
                                    🗑️
                                </button>
                            </div>
                        ))}
                    </div>

                    {/* Add New */}
                    <div className="add-prompt-section">
                        <h3>Aggiungi Nuovo Prompt</h3>
                        <input
                            type="text"
                            className="add-input"
                            placeholder="Nome prompt..."
                            value={newLabel}
                            onChange={(e) => setNewLabel(e.target.value)}
                        />
                        <textarea
                            className="add-textarea"
                            placeholder="Contenuto del prompt..."
                            value={newContent}
                            onChange={(e) => setNewContent(e.target.value)}
                            rows={3}
                        />
                        <button
                            className="add-btn"
                            onClick={handleAdd}
                            disabled={!newLabel.trim() || !newContent.trim()}
                        >
                            + Aggiungi Prompt
                        </button>
                    </div>
                </div>

                {/* Footer */}
                <div className="editor-footer">
                    <span className="prompt-count">
                        {editablePrompts.length} prompt{editablePrompts.length !== 1 ? 's' : ''}
                    </span>
                    <div className="footer-actions">
                        <button className="cancel-btn" onClick={onClose}>
                            Annulla
                        </button>
                        <button className="save-btn" onClick={handleSave}>
                            Salva Modifiche
                        </button>
                    </div>
                </div>
            </div>
        </dialog>
    );
}
