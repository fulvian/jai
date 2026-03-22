/**
 * Voice Service
 * 
 * Gestisce TTS (Text-to-Speech) per PersAn.
 * Usa Web Speech API nel browser come soluzione semplice e universale.
 * 
 * Il gateway NON fa sintesi vocale - segnala al client di usare Web Speech API.
 */

export interface VoiceConfig {
    // Configurazione opzionale per future estensioni
    enabled?: boolean;
}

export interface SynthesizeResult {
    useWebSpeech: true;
    text: string;
}

export class VoiceService {
    private isReady: boolean = true;

    constructor(_config: VoiceConfig = {}) {
        // Config opzionale per future estensioni
    }

    /**
     * Inizializza il servizio
     */
    async initialize(): Promise<void> {
        console.log('🔊 VoiceService: Using Web Speech API (browser-side)');
        this.isReady = true;
    }

    /**
     * Segnala al client di usare Web Speech API
     * 
     * @param text Testo da sintetizzare
     * @returns Segnale per usare Web Speech nel browser
     */
    synthesize(text: string): SynthesizeResult {
        if (!text.trim()) {
            throw new Error('Text cannot be empty');
        }

        // Segnala al client di usare Web Speech API
        return {
            useWebSpeech: true,
            text: text,
        };
    }

    /**
     * Controlla se il servizio è pronto
     */
    get ready(): boolean {
        return this.isReady;
    }

    /**
     * Health check
     */
    async healthCheck(): Promise<{
        ready: boolean;
        provider: string;
    }> {
        return {
            ready: this.isReady,
            provider: 'web-speech',
        };
    }
}

// Singleton per uso globale
let voiceServiceInstance: VoiceService | null = null;

export function getVoiceService(): VoiceService {
    if (!voiceServiceInstance) {
        voiceServiceInstance = new VoiceService();
    }
    return voiceServiceInstance;
}

export async function initializeVoiceService(config?: VoiceConfig): Promise<VoiceService> {
    voiceServiceInstance = new VoiceService(config);
    await voiceServiceInstance.initialize();
    return voiceServiceInstance;
}
