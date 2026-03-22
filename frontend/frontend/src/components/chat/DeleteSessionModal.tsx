'use client';

import React from 'react';
import { Trash2, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from '@/lib/utils';

interface DeleteSessionModalProps {
    isOpen: boolean;
    onClose: () => void;
    onConfirm: () => void;
    sessionTitle?: string;
}

export function DeleteSessionModal({ isOpen, onClose, onConfirm, sessionTitle }: DeleteSessionModalProps) {
    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-[100]"
                    />

                    {/* Modal Content */}
                    <div className="fixed inset-0 flex items-center justify-center pointer-events-none z-[101] p-4">
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95, y: 20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.95, y: 20 }}
                            className="pointer-events-auto w-full max-w-sm overflow-hidden rounded-2xl bg-[#1c1c1e] border border-white/10 shadow-2xl"
                        >
                            <div className="p-6">
                                <div className="flex items-center justify-center w-12 h-12 rounded-full bg-red-500/10 text-red-500 mx-auto mb-4">
                                    <Trash2 size={24} />
                                </div>

                                <h3 className="text-lg font-semibold text-white text-center mb-2">
                                    Elimina conversazione
                                </h3>

                                <p className="text-sm text-white/60 text-center mb-6">
                                    Sei sicuro di voler eliminare {sessionTitle ? <strong>"{sessionTitle}"</strong> : "questa conversazione"}?
                                    L'azione è irreversibile.
                                </p>

                                <div className="flex flex-col gap-2">
                                    <button
                                        onClick={onConfirm}
                                        className="w-full py-3 px-4 bg-red-500 hover:bg-red-600 text-white font-medium rounded-xl transition-colors"
                                    >
                                        Elimina
                                    </button>
                                    <button
                                        onClick={onClose}
                                        className="w-full py-3 px-4 bg-white/5 hover:bg-white/10 text-white font-medium rounded-xl transition-colors"
                                    >
                                        Annulla
                                    </button>
                                </div>
                            </div>
                        </motion.div>
                    </div>
                </>
            )}
        </AnimatePresence>
    );
}
