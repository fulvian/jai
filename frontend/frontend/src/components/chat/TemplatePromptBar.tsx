/**
 * TemplatePromptBar - Barra di chip/pill scrollabile per prompt template.
 *
 * Mostrata sopra il chat input per sessioni di tipo 'template'.
 * Click su un chip → inietta il prompt nella textarea.
 * ⌘+Click → invia direttamente il prompt.
 */

'use client';

import { useCallback, useState } from 'react';
import type { TemplatePrompt } from '@/types/chat';

interface TemplatePromptBarProps {
    prompts: TemplatePrompt[];
    onPromptSelect: (prompt: TemplatePrompt) => void;
    onPromptDirectSend?: (prompt: TemplatePrompt) => void;
    onManagePrompts: () => void;
}

export default function TemplatePromptBar({
    prompts,
    onPromptSelect,
    onPromptDirectSend,
    onManagePrompts,
}: TemplatePromptBarProps) {
    const [hoveredId, setHoveredId] = useState<string | null>(null);

    const enabledPrompts = prompts.filter((p) => p.enabled);

    const handleClick = useCallback(
        (prompt: TemplatePrompt, e: React.MouseEvent) => {
            if (e.metaKey || e.ctrlKey) {
                onPromptDirectSend?.(prompt);
            } else {
                onPromptSelect(prompt);
            }
        },
        [onPromptSelect, onPromptDirectSend]
    );

    if (enabledPrompts.length === 0) return null;

    return (
        <div className="template-prompt-bar">
            <div className="prompt-bar-label">
                <span className="prompt-bar-icon">⚡</span>
                <span>Template</span>
            </div>
            <div className="prompt-chips-scroll">
                {enabledPrompts.map((prompt) => (
                    <button
                        key={prompt.id}
                        className={`prompt-chip-btn ${hoveredId === prompt.id ? 'hovered' : ''}`}
                        onClick={(e) => handleClick(prompt, e)}
                        onMouseEnter={() => setHoveredId(prompt.id)}
                        onMouseLeave={() => setHoveredId(null)}
                        title={`Click: inserisci • ⌘+Click: invia\n${prompt.content.slice(0, 100)}${prompt.content.length > 100 ? '...' : ''}`}
                    >
                        <span className="chip-label">{prompt.label}</span>
                    </button>
                ))}
            </div>
            <button
                className="manage-prompts-btn"
                onClick={onManagePrompts}
                title="Gestisci prompt template"
            >
                ⚙️
            </button>
        </div>
    );
}
