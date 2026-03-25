/**
 * Whisper STT Module
 * 
 * Stub implementation for Whisper WASM speech-to-text.
 * This provides high-quality transcription when Whisper WASM is loaded.
 * Falls back to Web Speech API when not available.
 */

export interface WhisperState {
    isReady: boolean;
    isLoading: boolean;
    progress: number;
}

export async function initWhisper(
    onProgress?: (progress: number) => void
): Promise<boolean> {
    // Stub: Whisper not available in this environment
    console.warn('[Whisper] WASM module not loaded - using Web Speech API fallback');
    onProgress?.(100);
    return true;
}

export function isWhisperReady(): boolean {
    return false;
}

export async function transcribeWithWhisper(
    audioBlob: Blob
): Promise<string> {
    throw new Error('Whisper not available');
}

export async function recordAudioForWhisper(): Promise<Blob> {
    throw new Error('Whisper not available');
}

export function stopWhisperRecording(): void {
    // No-op stub
}
