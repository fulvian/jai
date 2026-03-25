/**
 * SessionManager Singleton Instance
 * 
 * Exports a singleton instance of SessionManager configured with Me4BrAIn Working Memory API.
 * This instance is used across all Gateway routes for unified session management.
 */

import { Me4BrAInClient } from '@persan/me4brain-client';
import { SessionManager } from './session_manager.js';

// Initialize Me4BrAIn client
// Note: Me4BrAInClient auto-appends /v1 if missing, so .env should NOT include /v1
// Note: Backend canonical port is 8000 (changed from legacy 8089)
const me4brainUrl = process.env.ME4BRAIN_URL || 'http://localhost:8000';
const me4brainClient = new Me4BrAInClient({ baseUrl: me4brainUrl });

// Use the memory namespace from the client (no need to duplicate)
const memoryNamespace = me4brainClient.memory;

// Create SessionManager singleton
export const sessionManager = new SessionManager(memoryNamespace);

// Export types for convenience
export type { ChatSession, ChatTurn, SessionConfig, CacheMetrics } from '@persan/shared';
