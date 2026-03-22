/**
 * Me4BrAIn Client Interface
 * 
 * Abstraction for Me4BrAIn client to enable dependency injection and testing.
 * Defines the contract for AI engine interactions.
 */

export interface ToolCallInfo {
    toolName: string;
    arguments: Record<string, unknown>;
    success: boolean;
    latencyMs: number;
    error?: string;
}

export interface IMe4BrAInClient {
    engine: {
        /**
         * Execute a natural language query
         * @param prompt - The query prompt
         * @param options - Optional configuration (timeout, etc.)
         * @returns Query response with answer and metadata
         */
        query(
            prompt: string,
            options?: { timeoutSeconds?: number }
        ): Promise<{
            query: string;
            answer: string;
            toolsCalled: ToolCallInfo[];
            totalLatencyMs: number;
            rawResults?: unknown[];
        }>;
    };
}
