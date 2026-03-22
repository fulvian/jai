/**
 * SkillCard - Card per visualizzare una skill
 */

'use client';

import { useState } from 'react';
import { Zap, ToggleLeft, ToggleRight, Trash2, Eye, Star } from 'lucide-react';

export interface Skill {
    id: string;
    name: string;
    description: string;
    type: 'explicit' | 'crystallized';
    enabled: boolean;
    usage_count: number;
    success_count: number;
    success_rate: number;
    confidence: number;
    version?: string;
}

interface SkillCardProps {
    skill: Skill;
    onToggle: (id: string, enabled: boolean) => void;
    onDelete: (id: string) => void;
    onViewDetails: (skill: Skill) => void;
}

export function SkillCard({ skill, onToggle, onDelete, onViewDetails }: SkillCardProps) {
    const [isToggling, setIsToggling] = useState(false);

    const handleToggle = async () => {
        setIsToggling(true);
        try {
            await onToggle(skill.id, !skill.enabled);
        } finally {
            setIsToggling(false);
        }
    };

    const successRatePercent = Math.round((skill.success_rate || 0) * 100);
    const confidencePercent = Math.round((skill.confidence || 0) * 100);

    return (
        <div className={`glass-panel p-4 rounded-xl transition-all duration-200 ${skill.enabled ? 'border-accent/30' : 'opacity-60'
            }`}>
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                    <div className={`p-2 rounded-lg ${skill.type === 'crystallized'
                        ? 'bg-purple-500/20 text-purple-400'
                        : 'bg-accent/20 text-accent'
                        }`}>
                        <Zap className="w-4 h-4" />
                    </div>
                    <div>
                        <h3 className="font-medium text-text-primary">{skill.name}</h3>
                        <span className={`text-xs px-2 py-0.5 rounded-full ${skill.type === 'crystallized'
                            ? 'bg-purple-500/20 text-purple-400'
                            : 'bg-accent/20 text-accent'
                            }`}>
                            {skill.type}
                        </span>
                    </div>
                </div>

                <button
                    onClick={handleToggle}
                    disabled={isToggling}
                    className="btn-icon"
                    title={skill.enabled ? 'Disabilita' : 'Abilita'}
                >
                    {skill.enabled ? (
                        <ToggleRight className="w-5 h-5 text-accent" />
                    ) : (
                        <ToggleLeft className="w-5 h-5 text-text-tertiary" />
                    )}
                </button>
            </div>

            {/* Description */}
            <p className="text-sm text-text-secondary mb-3 line-clamp-2">
                {skill.description}
            </p>

            {/* Stats */}
            <div className="flex items-center gap-4 text-xs text-text-tertiary mb-3">
                <div className="flex items-center gap-1">
                    <Star className="w-3 h-3" />
                    <span>{skill.usage_count} uses</span>
                </div>
                <div className="flex items-center gap-1">
                    <span className={successRatePercent >= 70 ? 'text-green-400' : successRatePercent >= 40 ? 'text-yellow-400' : 'text-red-400'}>
                        {successRatePercent}% success
                    </span>
                </div>
                <div className="flex items-center gap-1">
                    <span>{confidencePercent}% confidence</span>
                </div>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2">
                <button
                    onClick={() => onViewDetails(skill)}
                    className="btn-icon flex-1 flex items-center justify-center gap-1 text-xs"
                >
                    <Eye className="w-3 h-3" />
                    Dettagli
                </button>
                <button
                    onClick={() => onDelete(skill.id)}
                    className="btn-icon text-red-400 hover:text-red-300"
                    title="Elimina skill"
                >
                    <Trash2 className="w-4 h-4" />
                </button>
            </div>
        </div>
    );
}

export default SkillCard;
