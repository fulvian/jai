'use client';

import { create } from 'zustand';
import { CanvasBlockData } from '@/components/canvas/CanvasBlock';

interface CanvasState {
    blocks: CanvasBlockData[];

    // Actions
    pushBlock: (block: CanvasBlockData) => void;
    updateBlock: (id: string, data: Partial<CanvasBlockData>) => void;
    removeBlock: (id: string) => void;
    reorderBlocks: (activeId: string, overId: string) => void;
    clearCanvas: () => void;
}

export const useCanvasStore = create<CanvasState>((set) => ({
    blocks: [],

    pushBlock: (block) => set((state) => {
        // Se esiste già un blocco con lo stesso ID, lo aggiorna, altrimenti lo aggiunge
        const exists = state.blocks.find(b => b.id === block.id);
        if (exists) {
            return {
                blocks: state.blocks.map(b => b.id === block.id ? { ...b, ...block } : b)
            };
        }
        return { blocks: [...state.blocks, block] };
    }),

    updateBlock: (id, data) => set((state) => ({
        blocks: state.blocks.map(b => b.id === id ? { ...b, ...data } : b)
    })),

    removeBlock: (id) => set((state) => ({
        blocks: state.blocks.filter(b => b.id !== id)
    })),

    reorderBlocks: (activeId, overId) => set((state) => {
        const oldIndex = state.blocks.findIndex(b => b.id === activeId);
        const newIndex = state.blocks.findIndex(b => b.id === overId);

        if (oldIndex === -1 || newIndex === -1) return state;

        const newBlocks = [...state.blocks];
        const [removed] = newBlocks.splice(oldIndex, 1);
        newBlocks.splice(newIndex, 0, removed);

        return { blocks: newBlocks };
    }),

    clearCanvas: () => set({ blocks: [] }),
}));

