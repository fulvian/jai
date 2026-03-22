/**
 * Voice Routes
 * 
 * API endpoints per voice processing:
 * - POST /voice/synthesize - Segnala al client di usare Web Speech API
 * - GET /voice/health - Health check
 */

import { FastifyPluginAsync } from 'fastify';
import { getVoiceService } from '../voice/index.js';

interface SynthesizeBody {
    text: string;
}

export const voiceRoutes: FastifyPluginAsync = async (fastify) => {
    /**
     * POST /voice/synthesize
     * 
     * Segnala al client di usare Web Speech API per la sintesi.
     * Il gateway NON fa sintesi vocale server-side.
     */
    fastify.post<{ Body: SynthesizeBody }>('/voice/synthesize', {
        schema: {
            body: {
                type: 'object',
                required: ['text'],
                properties: {
                    text: { type: 'string', minLength: 1, maxLength: 5000 },
                },
            },
        },
    }, async (request, reply) => {
        const { text } = request.body;

        try {
            const voiceService = getVoiceService();
            const result = voiceService.synthesize(text);

            // Segnala al client di usare Web Speech API
            return reply.status(200).send({
                action: 'use_web_speech',
                text: result.text,
                provider: 'web-speech',
                message: 'Use Web Speech API in browser for synthesis',
            });
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Unknown error';
            request.log.error({ error }, 'Voice synthesis failed');
            return reply.status(500).send({
                error: 'SYNTHESIS_FAILED',
                message,
            });
        }
    });

    /**
     * GET /voice/health
     * 
     * Health check per voice service
     */
    fastify.get('/voice/health', async (_request, reply) => {
        const voiceService = getVoiceService();
        const health = await voiceService.healthCheck();

        return reply.send({
            status: health.ready ? 'healthy' : 'degraded',
            provider: health.provider,
            note: 'TTS uses Web Speech API in browser (client-side)',
        });
    });
};
