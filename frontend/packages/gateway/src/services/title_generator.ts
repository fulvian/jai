/**
 * Title Generator - Auto-naming for chat sessions.
 *
 * Chiama l'endpoint Me4BrAIn per generare titoli descrittivi
 * per le sessioni chat basati sulla query iniziale dell'utente.
 */

// Always use port 8089 for title generation - backend runs on this port
const ME4BRAIN_URL = 'http://localhost:8089';
const TITLE_GENERATION_TIMEOUT = 5000; // 5 secondi

export interface GenerateTitleResponse {
    title: string;
}

/**
 * Genera un titolo per la sessione chat chiamando l'endpoint LLM.
 *
 * @param prompt - Il primo messaggio dell'utente
 * @param _signal - AbortSignal opzionale per cancellation (non utilizzato per ora)
 * @returns Il titolo generato, o throw in caso di errore
 */
export async function generateSessionTitle(
    prompt: string,
    _signal?: AbortSignal,
): Promise<string> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), TITLE_GENERATION_TIMEOUT);

    try {
        const response = await fetch(`${ME4BRAIN_URL}/v1/sessions/generate-title`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ prompt }),
            signal: controller.signal,
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = (await response.json()) as GenerateTitleResponse;
        return data.title;
    } finally {
        clearTimeout(timeout);
    }
}

/**
 * Genera un titolo con fallback automatico.
 * Se la generazione fallisce, restituisce una versione troncata del prompt.
 *
 * @param prompt - Il primo messaggio dell'utente
 * @param signal - AbortSignal opzionale per cancellation
 * @returns Il titolo generato o il fallback
 */
export async function generateSessionTitleWithFallback(
    prompt: string,
    signal?: AbortSignal,
): Promise<string> {
    try {
        // Crea un AbortController che combina timeout interno e signal esterno
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), TITLE_GENERATION_TIMEOUT);

        // Se arriva un signal esterno, lo ascoltiamo
        if (signal) {
            signal.addEventListener('abort', () => controller.abort());
        }

        const response = await fetch(`${ME4BRAIN_URL}/v1/sessions/generate-title`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ prompt }),
            signal: controller.signal,
        });

        clearTimeout(timeout);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = (await response.json()) as GenerateTitleResponse;
        return data.title;
    } catch (error) {
        // Fallback: tronca il prompt a 50 caratteri
        const truncated = prompt.slice(0, 50);
        return truncated.length < prompt.length ? `${truncated}...` : truncated;
    }
}
