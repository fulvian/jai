'use client';

import { Layers, LayoutGrid, PanelRightClose } from 'lucide-react';
import { CanvasBlock, CanvasBlockData } from './CanvasBlock';
import { useCanvasStore } from '@/stores/useCanvasStore';
import { motion, AnimatePresence } from 'framer-motion';
import {
    DndContext,
    DragEndEvent,
    closestCenter,
    KeyboardSensor,
    PointerSensor,
    useSensor,
    useSensors,
} from '@dnd-kit/core';
import {
    SortableContext,
    sortableKeyboardCoordinates,
    rectSortingStrategy,
} from '@dnd-kit/sortable';

// Import block components
import { ChartBlock } from './blocks/ChartBlock';
import { TableBlock } from './blocks/TableBlock';
import { CodeBlock } from './blocks/CodeBlock';
import { TextBlock } from './blocks/TextBlock';

interface CanvasProps {
    onClose?: () => void;
}

export function Canvas({ onClose }: CanvasProps) {
    const { blocks, removeBlock, reorderBlocks } = useCanvasStore();

    // DnD Sensors
    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: {
                distance: 8, // Prevenire drag accidentale su click
            },
        }),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    );

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (over && active.id !== over.id) {
            reorderBlocks(String(active.id), String(over.id));
        }
    };

    const renderBlockContent = (block: CanvasBlockData) => {
        switch (block.type) {
            case 'chart': return <ChartBlock data={block.data} />;
            case 'table': return <TableBlock data={block.data} />;
            case 'code': return <CodeBlock data={block.data} />;
            case 'text': return <TextBlock data={block.data} />;
            default: return <div className="text-xs text-gray-500">Tipo blocco non supportato: {block.type}</div>;
        }
    };

    return (
        <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--tahoe-gray-6)' }}>
            {/* Canvas Header - Glass */}
            <div className="h-12 flex items-center justify-between px-4 glass-topbar">
                <div className="flex items-center gap-2">
                    <Layers size={18} className="text-[var(--tahoe-blue)]" />
                    <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>Canvas A2UI</span>
                </div>

                <div className="flex items-center gap-2">
                    <button className="glass-button-ghost p-2 rounded-lg" title="Griglia">
                        <LayoutGrid size={18} />
                    </button>
                    <button onClick={onClose} className="glass-button-ghost p-2 rounded-lg" title="Chiudi Canvas">
                        <PanelRightClose size={18} />
                    </button>
                </div>
            </div>

            {/* Dashboard Area */}
            <div className="flex-1 overflow-y-auto p-4 md:p-6 custom-scrollbar" style={{ background: 'rgba(28, 28, 30, 0.5)' }}>
                {blocks.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center max-w-sm mx-auto animate-fade-in-up">
                        <div className="w-16 h-16 rounded-2xl glass-panel-floating flex items-center justify-center mb-4 glow-border">
                            <Layers size={32} className="text-[var(--tahoe-blue)]" />
                        </div>
                        <h3 className="text-lg font-medium mb-1" style={{ color: 'var(--text-primary)' }}>Canvas Vuoto</h3>
                        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                            L'agente aggiungerà grafici e tabelle qui durante la conversazione.
                        </p>
                    </div>
                ) : (
                    <DndContext
                        sensors={sensors}
                        collisionDetection={closestCenter}
                        onDragEnd={handleDragEnd}
                    >
                        <SortableContext
                            items={blocks.map(b => b.id)}
                            strategy={rectSortingStrategy}
                        >
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 auto-rows-fr">
                                <AnimatePresence>
                                    {blocks.map((block) => (
                                        <CanvasBlock
                                            key={block.id}
                                            block={block}
                                            onRemove={removeBlock}
                                        >
                                            {renderBlockContent(block)}
                                        </CanvasBlock>
                                    ))}
                                </AnimatePresence>
                            </div>
                        </SortableContext>
                    </DndContext>
                )}
            </div>
        </div>
    );
}

