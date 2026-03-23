'use client';

import { Layers, LayoutGrid, PanelRightClose } from 'lucide-react';
import { CanvasBlock, CanvasBlockData } from './CanvasBlock';
import { useCanvasStore } from '@/stores/useCanvasStore';
import { motion, AnimatePresence } from 'framer-motion';
import {
    DndContext,
    DragEndEvent,
    DragOverEvent,
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
import { useRef, useCallback } from 'react';

// Import block components
import { ChartBlock } from './blocks/ChartBlock';
import { TableBlock } from './blocks/TableBlock';
import { CodeBlock } from './blocks/CodeBlock';
import { TextBlock } from './blocks/TextBlock';

interface CanvasProps {
    onClose?: () => void;
}

export function Canvas({ onClose }: CanvasProps) {
    const { blocks, removeBlock } = useCanvasStore();

    // Snapshot for optimistic update rollback
    const snapshotRef = useRef<CanvasBlockData[] | null>(null);

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

    // Handle drag start - save snapshot for rollback
    const handleDragStart = useCallback(() => {
        // Save snapshot for potential rollback on error
        snapshotRef.current = JSON.parse(JSON.stringify(blocks));
    }, [blocks]);

    // Handle drag over - real-time visual update during drag
    const handleDragOver = useCallback((event: DragOverEvent) => {
        const { active, over } = event;
        if (over && active.id !== over.id && snapshotRef.current) {
            // Apply optimistic reorder during drag
            const activeId = String(active.id);
            const overId = String(over.id);

            // Reorder with snapshot as base
            const oldIndex = snapshotRef.current.findIndex(b => b.id === activeId);
            const newIndex = snapshotRef.current.findIndex(b => b.id === overId);

            if (oldIndex !== -1 && newIndex !== -1) {
                const newBlocks = [...snapshotRef.current];
                const [removed] = newBlocks.splice(oldIndex, 1);
                newBlocks.splice(newIndex, 0, removed);

                // Update store with optimistic reorder
                useCanvasStore.setState({ blocks: newBlocks });
            }
        }
    }, []);

    // Handle drag end - persist to backend
    const handleDragEnd = useCallback(async (event: DragEndEvent) => {
        const { active, over } = event;

        // Reset snapshot
        snapshotRef.current = null;

        if (!over || active.id === over.id) {
            return;
        }

        const activeId = String(active.id);
        const overId = String(over.id);

        try {
            // Persist reorder to backend
            // TODO: Call API to persist block order
            // await api.canvas.reorderBlocks(activeId, overId);

            console.info('[Canvas] Block reordered:', activeId, '->', overId);
        } catch (error) {
            // Rollback on error
            if (snapshotRef.current) {
                useCanvasStore.setState({ blocks: snapshotRef.current });
            }

            console.error('[Canvas] Failed to reorder blocks, rolled back:', error);
        }
    }, []);

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
                        onDragStart={handleDragStart}
                        onDragOver={handleDragOver}
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

