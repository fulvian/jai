/**
 * FileUpload component for chat attachments.
 * 
 * Supports: PDF, images (JPEG, PNG, BMP)
 * Uses Me4BrAIn HybridOCR (native + Vision LLM fallback)
 */

'use client';

import { useCallback, useState, useRef } from 'react';
import { Paperclip, X, FileText, Image as ImageIcon, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { API_CONFIG } from '@/lib/config';

interface FileUploadProps {
    onFileProcessed: (extractedText: string, fileName: string) => void;
    disabled?: boolean;
}

interface UploadedFile {
    name: string;
    type: string;
    size: number;
    extractedText?: string;
    processing: boolean;
    error?: string;
}

const ACCEPTED_TYPES = [
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/bmp',
];

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

const API_URL = API_CONFIG.gatewayUrl;

export function FileUpload({ onFileProcessed, disabled }: FileUploadProps) {
    const [files, setFiles] = useState<UploadedFile[]>([]);
    const inputRef = useRef<HTMLInputElement>(null);

    const processFile = useCallback(async (file: File) => {
        // Validate file type
        if (!ACCEPTED_TYPES.includes(file.type)) {
            setFiles(prev => [...prev, {
                name: file.name,
                type: file.type,
                size: file.size,
                processing: false,
                error: 'Tipo file non supportato. Usa PDF, JPEG, PNG o BMP.',
            }]);
            return;
        }

        // Validate file size
        if (file.size > MAX_FILE_SIZE) {
            setFiles(prev => [...prev, {
                name: file.name,
                type: file.type,
                size: file.size,
                processing: false,
                error: 'File troppo grande. Max 10MB.',
            }]);
            return;
        }

        // Add file with processing state
        setFiles(prev => [...prev, {
            name: file.name,
            type: file.type,
            size: file.size,
            processing: true,
        }]);

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(`${API_URL}/api/upload`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`Upload failed: ${response.status}`);
            }

            const result = await response.json();

            // Update file with extracted text
            setFiles(prev => prev.map(f =>
                f.name === file.name
                    ? { ...f, processing: false, extractedText: result.content }
                    : f
            ));

            // Callback con testo estratto
            if (result.content) {
                onFileProcessed(result.content, file.name);
            }

        } catch (error) {
            setFiles(prev => prev.map(f =>
                f.name === file.name
                    ? { ...f, processing: false, error: (error as Error).message }
                    : f
            ));
        }
    }, [onFileProcessed]);

    const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFiles = e.target.files;
        if (!selectedFiles) return;

        Array.from(selectedFiles).forEach(processFile);

        // Reset input
        if (inputRef.current) {
            inputRef.current.value = '';
        }
    }, [processFile]);

    const removeFile = useCallback((fileName: string) => {
        setFiles(prev => prev.filter(f => f.name !== fileName));
    }, []);

    const getFileIcon = (type: string) => {
        if (type === 'application/pdf') return <FileText className="w-4 h-4" />;
        if (type.startsWith('image/')) return <ImageIcon className="w-4 h-4" />;
        return <FileText className="w-4 h-4" />;
    };

    return (
        <div className="space-y-2">
            {/* File chips */}
            {files.length > 0 && (
                <div className="flex flex-wrap gap-2">
                    {files.map((file) => (
                        <div
                            key={file.name}
                            className={cn(
                                'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs',
                                file.error
                                    ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                                    : file.processing
                                        ? 'bg-primary/20 text-primary border border-primary/30'
                                        : 'bg-muted text-muted-foreground border border-border'
                            )}
                        >
                            {file.processing ? (
                                <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                                getFileIcon(file.type)
                            )}
                            <span className="max-w-[100px] truncate">{file.name}</span>
                            {!file.processing && (
                                <button
                                    onClick={() => removeFile(file.name)}
                                    className="hover:text-foreground"
                                >
                                    <X className="w-3 h-3" />
                                </button>
                            )}
                        </div>
                    ))}
                </div>
            )}

            {/* Upload button */}
            <div>
                <input
                    ref={inputRef}
                    type="file"
                    accept={ACCEPTED_TYPES.join(',')}
                    onChange={handleFileChange}
                    className="hidden"
                    disabled={disabled}
                    multiple
                />
                <button
                    type="button"
                    onClick={() => inputRef.current?.click()}
                    disabled={disabled}
                    className={cn(
                        'flex items-center gap-2 px-3 py-2 rounded-lg text-sm',
                        'bg-muted/50 hover:bg-muted text-muted-foreground',
                        'border border-border hover:border-primary/50',
                        'transition-colors duration-200',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                    )}
                >
                    <Paperclip className="w-4 h-4" />
                    Allega file
                </button>
            </div>
        </div>
    );
}
