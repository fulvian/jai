/**
 * Upload route - File upload with OCR processing.
 * 
 * Proxies to Python backend until Me4BrAIn SDK has ingestion API.
 */

import { FastifyPluginAsync } from 'fastify';
import { MultipartFile } from '@fastify/multipart';
import { createWriteStream, promises as fs } from 'fs';
import { pipeline } from 'stream/promises';
import { tmpdir } from 'os';
import { join } from 'path';
import { randomUUID } from 'crypto';

const ALLOWED_EXTENSIONS = new Set(['.pdf', '.jpg', '.jpeg', '.png', '.bmp']);
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

interface UploadResponse {
    filename: string;
    content: string;
    method: string;
    model?: string;
    pages: number;
}

interface ErrorResponse {
    error: string;
    details?: string;
}

export const uploadRoutes: FastifyPluginAsync = async (fastify) => {
    fastify.post<{ Reply: UploadResponse | ErrorResponse }>('/api/upload', async (request, reply) => {
        const data = await request.file();

        if (!data) {
            return reply.code(400).send({ error: 'No file provided' });
        }

        const file = data as MultipartFile;

        // Validate filename
        if (!file.filename) {
            return reply.code(400).send({ error: 'No filename provided' });
        }

        // Validate extension
        const ext = file.filename.substring(file.filename.lastIndexOf('.')).toLowerCase();
        if (!ALLOWED_EXTENSIONS.has(ext)) {
            return reply.code(400).send({
                error: `File type not supported. Allowed: ${Array.from(ALLOWED_EXTENSIONS).join(', ')}`
            });
        }

        // Create temp file
        const tmpPath = join(tmpdir(), `upload-${randomUUID()}${ext}`);

        try {
            // Save uploaded file to temp location
            await pipeline(file.file, createWriteStream(tmpPath));


            // Check file size
            const stats = await fs.stat(tmpPath);
            if (stats.size > MAX_FILE_SIZE) {
                await fs.unlink(tmpPath);
                return reply.code(400).send({
                    error: `File too large. Maximum size: ${MAX_FILE_SIZE / 1024 / 1024}MB`
                });
            }

            // Call Me4BrAIn ingestion API directly
            const ME4BRAIN_URL = process.env.ME4BRAIN_URL || 'http://localhost:8000';

            const formData = new FormData();
            const fileBuffer = await fs.readFile(tmpPath);
            const blob = new Blob([fileBuffer], { type: file.mimetype });
            formData.append('file', blob, file.filename);

            const response = await fetch(`${ME4BRAIN_URL}/v1/ingestion/upload`, {
                method: 'POST',
                body: formData,
            });

            if (!response.ok) {
                throw new Error(`Me4BrAIn ingestion failed: ${response.status}`);
            }

            const result = await response.json() as UploadResponse;

            return {
                filename: file.filename,
                content: result.content || '',
                method: result.method || 'unknown',
                model: result.model,
                pages: result.pages || 0,
            };

        } catch (error) {
            fastify.log.error({ error, filename: file.filename }, 'Upload processing failed');
            return reply.code(500).send({
                error: 'Failed to process file',
                details: error instanceof Error ? error.message : 'Unknown error'
            });
        } finally {
            // Cleanup temp file
            try {
                await fs.unlink(tmpPath);
            } catch {
                // Ignore cleanup errors
            }
        }
    });
};
