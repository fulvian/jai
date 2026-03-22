'use client';

import { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { Maximize2, X, GripVertical, Settings2 } from 'lucide-react';
import { clsx } from 'clsx';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

export type BlockType = 'chart' | 'table' | 'code' | 'text' | 'image' | 'custom';

export interface CanvasBlockData {
    id: string;
    type: BlockType;
    title: string;
    data: any;
    size?: 'sm' | 'md' | 'lg' | 'full';
}

interface CanvasBlockProps {
    block: CanvasBlockData;
    children: ReactNode;
    onRemove?: (id: string) => void;
    onExpand?: (id: string) => void;
}

export function CanvasBlock({ block, children, onRemove, onExpand }: CanvasBlockProps) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging,
    } = useSortable({ id: block.id });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        zIndex: isDragging ? 1000 : 1,
    };

    return (
        <motion.div
            ref={setNodeRef}
            style={style}
            layout
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className={clsx(
                'glass-panel-floating flex flex-col overflow-hidden hover-lift',
                isDragging && 'glow-border-animated elevation-5',
                block.size === 'full' ? 'col-span-2 row-span-2' :
                    block.size === 'lg' ? 'col-span-2' : 'col-span-1'
            )}
        >
            {/* Block Header - Glass */}
            <div className="px-3 py-2 flex items-center justify-between border-b border-[var(--glass-border-subtle)]" style={{ background: 'var(--glass-tint-light)' }}>
                <div className="flex items-center gap-2 overflow-hidden">
                    {/* Drag Handle */}
                    <span
                        {...attributes}
                        {...listeners}
                        className="cursor-grab active:cursor-grabbing transition-colors" style={{ color: 'var(--text-quaternary)' }}
                    >
                        <GripVertical size={14} />
                    </span>
                    <h3 className="text-[11px] font-bold uppercase tracking-wider truncate" style={{ color: 'var(--text-secondary)' }}>
                        {block.title}
                    </h3>
                </div>

                <div className="flex items-center gap-1">
                    <button
                        onClick={() => onExpand?.(block.id)}
                        className="w-6 h-6 rounded flex items-center justify-center hover:bg-[var(--glass-tint-medium)] transition-colors"
                        style={{ color: 'var(--text-tertiary)' }}
                        title="Espandi"
                    >
                        <Maximize2 size={12} />
                    </button>
                    <button
                        onClick={() => onRemove?.(block.id)}
                        className="w-6 h-6 rounded flex items-center justify-center hover:bg-[var(--tahoe-red)]/20 hover:text-[var(--tahoe-red)] transition-colors"
                        style={{ color: 'var(--text-tertiary)' }}
                        title="Rimuovi"
                    >
                        <X size={12} />
                    </button>
                </div>
            </div>

            {/* Block Content */}
            <div className="flex-1 overflow-auto p-4 custom-scrollbar bg-transparent">
                {children}
            </div>
        </motion.div>
    );
}

