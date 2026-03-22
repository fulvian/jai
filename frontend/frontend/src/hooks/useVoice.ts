/**
 * useVoice Hook
 * 
 * Hook React per gestire Speech-to-Text e Text-to-Speech.
 * 
 * STT: Web Speech API (default) o Whisper WASM (alta qualità)
 * TTS: Piper TTS via gateway, fallback a Web Speech Synthesis
 */

'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { initWhisper, transcribeWithWhisper, isWhisperReady, recordAudioForWhisper } from '@/lib/whisper';
import { API_CONFIG } from '@/lib/config';

// Types
interface SpeechRecognitionEvent {
    results: SpeechRecognitionResultList;
    resultIndex: number;
}

interface SpeechRecognitionErrorEvent {
    error: string;
    message?: string;
}

interface SpeechRecognition extends EventTarget {
    continuous: boolean;
    interimResults: boolean;
    lang: string;
    start: () => void;
    stop: () => void;
    abort: () => void;
    onresult: (event: SpeechRecognitionEvent) => void;
    onerror: (event: SpeechRecognitionErrorEvent) => void;
    onend: () => void;
    onstart: () => void;
}

declare global {
    interface Window {
        SpeechRecognition?: new () => SpeechRecognition;
        webkitSpeechRecognition?: new () => SpeechRecognition;
    }
}

export interface UseVoiceConfig {
    /** Lingua per STT (default: it-IT) */
    lang?: string;
    /** URL gateway per TTS */
    gatewayUrl?: string;
    /** Abilita risultati parziali STT */
    interimResults?: boolean;
    /** Provider STT: 'webspeech' (default) o 'whisper' (alta qualità) */
    sttProvider?: 'webspeech' | 'whisper';
    /** Callback progresso download modello Whisper */
    onWhisperProgress?: (progress: number) => void;
    /** Callback quando viene rilevato speech */
    onTranscript?: (text: string, isFinal: boolean) => void;
    /** Callback per errori */
    onError?: (error: string) => void;
}

export interface UseVoiceReturn {
    // State
    isListening: boolean;
    isSpeaking: boolean;
    isSupported: boolean;
    isWhisperReady: boolean;
    isWhisperLoading: boolean;
    whisperProgress: number;
    transcript: string;
    interimTranscript: string;
    sttProvider: 'webspeech' | 'whisper';

    // Actions
    startListening: () => void;
    stopListening: () => void;
    speak: (text: string) => Promise<void>;
    stopSpeaking: () => void;
    initializeWhisper: () => Promise<void>;
    setSttProvider: (provider: 'webspeech' | 'whisper') => void;

    // Toggle
    toggleListening: () => void;
}

export function useVoice(config: UseVoiceConfig = {}): UseVoiceReturn {
    const {
        lang = 'it-IT',
        gatewayUrl = API_CONFIG.gatewayUrl,
        interimResults = true,
        sttProvider: initialProvider = 'webspeech',
        onWhisperProgress,
        onTranscript,
        onError,
    } = config;

    // State
    const [isListening, setIsListening] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);
    const [transcript, setTranscript] = useState('');
    const [interimTranscript, setInterimTranscript] = useState('');
    const [sttProvider, setSttProvider] = useState<'webspeech' | 'whisper'>(initialProvider);
    const [whisperReady, setWhisperReady] = useState(false);
    const [whisperLoading, setWhisperLoading] = useState(false);
    const [whisperProgress, setWhisperProgress] = useState(0);

    // Refs
    const recognitionRef = useRef<SpeechRecognition | null>(null);
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const synthRef = useRef<SpeechSynthesisUtterance | null>(null);
    const whisperRecordingRef = useRef<boolean>(false);

    // Check browser support
    const isSupported = typeof window !== 'undefined' &&
        !!(window.SpeechRecognition || window.webkitSpeechRecognition);

    // Initialize Speech Recognition
    useEffect(() => {
        if (typeof window === 'undefined') return;

        const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognitionAPI) return;

        const recognition = new SpeechRecognitionAPI();
        recognition.continuous = true;
        recognition.interimResults = interimResults;
        recognition.lang = lang;

        recognition.onresult = (event: SpeechRecognitionEvent) => {
            let interim = '';
            let final = '';

            for (let i = event.resultIndex; i < event.results.length; i++) {
                const result = event.results[i];
                if (result.isFinal) {
                    final += result[0].transcript;
                } else {
                    interim += result[0].transcript;
                }
            }

            if (final) {
                setTranscript(prev => prev + final);
                setInterimTranscript('');
                onTranscript?.(final, true);
            } else {
                setInterimTranscript(interim);
                onTranscript?.(interim, false);
            }
        };

        recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
            // Ignora errori normali del flusso di riconoscimento vocale
            const ignorableErrors = ['aborted', 'no-speech'];
            if (ignorableErrors.includes(event.error)) {
                setIsListening(false);
                return;
            }
            console.error('Speech recognition error:', event.error);
            onError?.(event.error);
            setIsListening(false);
        };

        recognition.onend = () => {
            setIsListening(false);
        };

        recognition.onstart = () => {
            setIsListening(true);
        };

        recognitionRef.current = recognition;

        return () => {
            recognition.abort();
        };
    }, [lang, interimResults, onTranscript, onError]);

    // Initialize Whisper WASM
    const initializeWhisper = useCallback(async (): Promise<void> => {
        if (whisperReady || whisperLoading) return;

        setWhisperLoading(true);
        try {
            await initWhisper({
                model: 'whisper-small',
                language: lang.split('-')[0], // 'it-IT' -> 'it'
                onProgress: (progress) => {
                    setWhisperProgress(progress);
                    onWhisperProgress?.(progress);
                },
                onReady: () => {
                    setWhisperReady(true);
                    setWhisperLoading(false);
                    console.log('✅ Whisper WASM ready');
                },
            });
        } catch (error) {
            console.error('Failed to initialize Whisper:', error);
            setWhisperLoading(false);
            onError?.('Failed to initialize Whisper');
        }
    }, [lang, onWhisperProgress, onError, whisperReady, whisperLoading]);

    // Start listening with Whisper
    const startListeningWhisper = useCallback(async () => {
        if (!whisperReady) {
            onError?.('Whisper not initialized. Call initializeWhisper first.');
            return;
        }

        if (whisperRecordingRef.current) return;
        whisperRecordingRef.current = true;

        setIsListening(true);
        setTranscript('');
        setInterimTranscript('Recording...');

        try {
            // Record for 5 seconds (can be made configurable)
            const audio = await recordAudioForWhisper(5000);
            if (!audio) {
                onError?.('Whisper recording failed');
                return;
            }
            setInterimTranscript('Transcribing...');

            const result = await transcribeWithWhisper(audio, lang.split('-')[0]);
            if (!result) {
                onError?.('Whisper transcription failed');
                return;
            }

            setTranscript(result.text);
            setInterimTranscript('');
            onTranscript?.(result.text, true);
        } catch (error) {
            console.error('Whisper transcription error:', error);
            onError?.('Whisper transcription failed');
        } finally {
            whisperRecordingRef.current = false;
            setIsListening(false);
        }
    }, [whisperReady, lang, onTranscript, onError]);

    // Start listening (dispatcher based on provider)
    const startListening = useCallback(() => {
        if (sttProvider === 'whisper') {
            startListeningWhisper();
            return;
        }

        // Web Speech API
        if (!recognitionRef.current) {
            onError?.('Speech recognition not supported');
            return;
        }

        // Stop any ongoing speech
        if (isSpeaking) {
            stopSpeaking();
        }

        setTranscript('');
        setInterimTranscript('');

        try {
            recognitionRef.current.start();
        } catch (e) {
            // Already started
            console.warn('Recognition already started');
        }
    }, [sttProvider, startListeningWhisper, isSpeaking, onError]);

    // Stop listening
    const stopListening = useCallback(() => {
        if (recognitionRef.current) {
            recognitionRef.current.stop();
        }
        setIsListening(false);
    }, []);

    // Toggle listening
    const toggleListening = useCallback(() => {
        if (isListening) {
            stopListening();
        } else {
            startListening();
        }
    }, [isListening, startListening, stopListening]);

    // Speak text (TTS)
    const speak = useCallback(async (text: string): Promise<void> => {
        if (!text.trim()) return;

        // Stop listening while speaking
        if (isListening) {
            stopListening();
        }

        setIsSpeaking(true);

        try {
            // Try Piper TTS via gateway
            const response = await fetch(`${gatewayUrl}/voice/synthesize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text }),
            });

            if (response.ok) {
                const audioBlob = await response.blob();
                const audioUrl = URL.createObjectURL(audioBlob);

                const audio = new Audio(audioUrl);
                audioRef.current = audio;

                return new Promise((resolve, reject) => {
                    audio.onended = () => {
                        setIsSpeaking(false);
                        URL.revokeObjectURL(audioUrl);
                        resolve();
                    };
                    audio.onerror = () => {
                        setIsSpeaking(false);
                        URL.revokeObjectURL(audioUrl);
                        reject(new Error('Audio playback failed'));
                    };
                    audio.play();
                });
            }

            // Fallback: Web Speech Synthesis
            console.log('Using Web Speech Synthesis fallback');
            return speakWithWebSpeech(text);

        } catch (error) {
            console.warn('Piper TTS failed, using Web Speech fallback:', error);
            return speakWithWebSpeech(text);
        }
    }, [gatewayUrl, isListening, stopListening]);

    // Web Speech Synthesis fallback
    const speakWithWebSpeech = useCallback((text: string): Promise<void> => {
        return new Promise((resolve, reject) => {
            if (!window.speechSynthesis) {
                setIsSpeaking(false);
                reject(new Error('Speech synthesis not supported'));
                return;
            }

            // Cancel any ongoing speech
            window.speechSynthesis.cancel();

            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = lang;
            utterance.rate = 1.0;
            utterance.pitch = 1.0;

            // Find Italian voice if available
            const voices = window.speechSynthesis.getVoices();
            const italianVoice = voices.find(v => v.lang.startsWith('it'));
            if (italianVoice) {
                utterance.voice = italianVoice;
            }

            synthRef.current = utterance;

            utterance.onend = () => {
                setIsSpeaking(false);
                resolve();
            };

            utterance.onerror = (event) => {
                setIsSpeaking(false);
                reject(new Error(event.error));
            };

            window.speechSynthesis.speak(utterance);
        });
    }, [lang]);

    // Stop speaking
    const stopSpeaking = useCallback(() => {
        if (audioRef.current) {
            audioRef.current.pause();
            audioRef.current = null;
        }
        if (window.speechSynthesis) {
            window.speechSynthesis.cancel();
        }
        setIsSpeaking(false);
    }, []);

    return {
        isListening,
        isSpeaking,
        isSupported,
        isWhisperReady: whisperReady,
        isWhisperLoading: whisperLoading,
        whisperProgress,
        transcript,
        interimTranscript,
        sttProvider,
        startListening,
        stopListening,
        speak,
        stopSpeaking,
        initializeWhisper,
        setSttProvider,
        toggleListening,
    };
}
