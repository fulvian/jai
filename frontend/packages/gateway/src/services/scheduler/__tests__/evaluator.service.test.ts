/**
 * Evaluator Service - Comprehensive Unit Tests
 * 
 * Tests all 10 monitor types with Me4BrAIn mocking, error scenarios, and edge cases.
 * Refactored to use Dependency Injection pattern.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { Monitor } from '@persan/shared';
import type { IMe4BrAInClient } from '../interfaces/me4brain-client.interface.js';

// Mock ConfigService to prevent environment validation errors
vi.mock('../../../config/config.service.js', () => ({
    ConfigService: {
        getInstance: vi.fn(() => ({
            get: vi.fn((key: string) => {
                if (key === 'ME4BRAIN_URL') return 'http://localhost:8000';
                return undefined;
            }),
        })),
    },
}));

// Mock MonitorManager
vi.mock('../monitor-manager.service.js');

// Import after mocks
import { EvaluatorService } from '../evaluator.service.js';
import { monitorManager } from '../monitor-manager.service.js';

describe('EvaluatorService', () => {
    let evaluatorService: EvaluatorService;
    let mockGetMonitor: ReturnType<typeof vi.fn>;
    let mockAddEvaluationResult: ReturnType<typeof vi.fn>;
    let mockMe4BrAInClient: IMe4BrAInClient;
    let mockQuery: ReturnType<typeof vi.fn>;

    beforeEach(() => {
        // Clear mocks first
        vi.clearAllMocks();

        // Setup mocks
        mockGetMonitor = vi.fn();
        mockAddEvaluationResult = vi.fn();
        mockQuery = vi.fn();

        vi.mocked(monitorManager).getMonitor = mockGetMonitor;
        vi.mocked(monitorManager).addEvaluationResult = mockAddEvaluationResult;

        // Create mock Me4BrAIn client
        mockMe4BrAInClient = {
            engine: {
                query: mockQuery,
            },
        };

        // Instantiate service with mock client (DEPENDENCY INJECTION!)
        evaluatorService = new EvaluatorService(mockMe4BrAInClient);
    });

    // =========================================================================
    // Core Dispatcher Tests
    // =========================================================================

    describe('evaluate() - Core Dispatcher', () => {
        it('should dispatch to PRICE_WATCH evaluator', async () => {
            const monitor = {
                id: 'test-1',
                user_id: 'user-1',
                name: 'Test Price Watch',
                type: 'PRICE_WATCH',
                config: { ticker: 'AAPL', condition: 'below', threshold: '150' },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);
            mockQuery.mockResolvedValue({
                query: 'Get stock price for AAPL',
                answer: JSON.stringify({ price: 140, change: -2.5, volume: 1000000 }),
                toolsCalled: [],
                totalLatencyMs: 100,
            });

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(true);
            expect(result.decision?.recommendation).toBe('WAIT');
            expect(mockAddEvaluationResult).toHaveBeenCalledWith('test-1', expect.any(Object));
        });

        it('should handle unknown monitor types', async () => {
            const monitor = {
                id: 'test-1',
                type: 'UNKNOWN_TYPE',
                config: {},
            } as any;

            mockGetMonitor.mockResolvedValue(monitor);

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(false);
            expect(result.error).toContain('Unknown monitor type');
        });

        it('should handle monitor not found', async () => {
            mockGetMonitor.mockResolvedValue(null);

            await expect(evaluatorService.evaluate('non-existent')).rejects.toThrow('Monitor non-existent not found');
        });
    });

    // =========================================================================
    // Finance Monitors Tests
    // =========================================================================

    describe('PRICE_WATCH Evaluator', () => {
        it('should trigger when price is below threshold', async () => {
            const monitor = {
                id: 'test-1',
                type: 'PRICE_WATCH',
                config: { ticker: 'AAPL', condition: 'below', threshold: '150' },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);
            mockQuery.mockResolvedValue({
                query: 'Get stock price for AAPL',
                answer: JSON.stringify({ price: 140, change: -2.5, volume: 1000000 }),
                toolsCalled: [],
                totalLatencyMs: 100,
            });

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(true);
            expect(result.decision?.confidence).toBe(100);
            expect(result.data).toMatchObject({ price: 140, threshold: 150, ticker: 'AAPL' });
        });

        it('should not trigger when condition is not met', async () => {
            const monitor = {
                id: 'test-1',
                type: 'PRICE_WATCH',
                config: { ticker: 'AAPL', condition: 'below', threshold: '150' },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);
            mockQuery.mockResolvedValue({
                query: 'Get stock price for AAPL',
                answer: JSON.stringify({ price: 160, change: 2.5, volume: 1000000 }),
                toolsCalled: [],
                totalLatencyMs: 100,
            });

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(false);
            expect(result.decision?.confidence).toBe(50);
        });

        it('should handle Me4BrAIn API failure', async () => {
            const monitor = {
                id: 'test-1',
                type: 'PRICE_WATCH',
                config: { ticker: 'AAPL', condition: 'below', threshold: '150' },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);
            mockQuery.mockRejectedValue(new Error('API Error'));

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(false);
            expect(result.error).toContain('Failed to evaluate PRICE_WATCH');
        });
    });

    describe('SIGNAL_WATCH Evaluator', () => {
        it('should trigger when RSI is below threshold', async () => {
            const monitor = {
                id: 'test-1',
                type: 'SIGNAL_WATCH',
                config: { ticker: 'AAPL', indicator: 'rsi', condition: 'below', threshold: '30' },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);
            mockQuery.mockResolvedValue({
                query: 'Get RSI for AAPL',
                answer: JSON.stringify({ value: 25 }),
                toolsCalled: [],
                totalLatencyMs: 100,
            });

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(true);
            expect(result.decision?.confidence).toBe(100);
        });
    });

    describe('AUTONOMOUS Evaluator', () => {
        it('should trigger on high-confidence BUY recommendation', async () => {
            const monitor = {
                id: 'test-1',
                type: 'AUTONOMOUS',
                config: { ticker: 'AAPL', goal: 'Find buy opportunities', min_confidence: '70' },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);

            mockQuery
                .mockResolvedValueOnce({
                    query: 'price',
                    answer: JSON.stringify({ price: 150, change: 2.5, volume: 1000000 }),
                    toolsCalled: [],
                    totalLatencyMs: 100,
                })
                .mockResolvedValueOnce({
                    query: 'news',
                    answer: JSON.stringify({ headlines: ['Positive news'] }),
                    toolsCalled: [],
                    totalLatencyMs: 100,
                })
                .mockResolvedValueOnce({
                    query: 'rsi',
                    answer: JSON.stringify({ value: 45 }),
                    toolsCalled: [],
                    totalLatencyMs: 100,
                })
                .mockResolvedValueOnce({
                    query: 'analyze',
                    answer: JSON.stringify({
                        recommendation: 'BUY',
                        confidence: 85,
                        reasoning: 'Strong buy signal',
                        key_factors: ['Factor 1']
                    }),
                    toolsCalled: [],
                    totalLatencyMs: 100,
                });

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(true);
            expect(result.decision?.recommendation).toBe('BUY');
            expect(result.decision?.confidence).toBe(85);
        });

        it('should not trigger on low-confidence recommendations', async () => {
            const monitor = {
                id: 'test-1',
                type: 'AUTONOMOUS',
                config: { ticker: 'AAPL', goal: 'Monitor', min_confidence: '70' },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);

            mockQuery
                .mockResolvedValueOnce({
                    query: 'price',
                    answer: JSON.stringify({ price: 150, change: 0, volume: 1000000 }),
                    toolsCalled: [],
                    totalLatencyMs: 100,
                })
                .mockResolvedValueOnce({
                    query: 'news',
                    answer: JSON.stringify({ headlines: [] }),
                    toolsCalled: [],
                    totalLatencyMs: 100,
                })
                .mockResolvedValueOnce({
                    query: 'rsi',
                    answer: JSON.stringify({ value: 50 }),
                    toolsCalled: [],
                    totalLatencyMs: 100,
                })
                .mockResolvedValueOnce({
                    query: 'analyze',
                    answer: JSON.stringify({
                        recommendation: 'HOLD',
                        confidence: 50,
                        reasoning: 'Neutral signal',
                        key_factors: []
                    }),
                    toolsCalled: [],
                    totalLatencyMs: 100,
                });

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(false);
        });
    });

    // =========================================================================
    // Generic Monitors Tests
    // =========================================================================

    describe('HEARTBEAT Evaluator', () => {
        it('should trigger on high-confidence proactive suggestions', async () => {
            const monitor = {
                id: 'test-1',
                type: 'HEARTBEAT',
                config: { goal: 'Proactive assistance' },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);

            mockQuery
                .mockResolvedValueOnce({
                    query: 'calendar',
                    answer: JSON.stringify({ events: [{ start: '2026-02-28T20:00:00Z', title: 'Meeting' }] }),
                    toolsCalled: [],
                    totalLatencyMs: 100,
                })
                .mockResolvedValueOnce({
                    query: 'memory',
                    answer: JSON.stringify({ recent_items: [] }),
                    toolsCalled: [],
                    totalLatencyMs: 100,
                })
                .mockResolvedValueOnce({
                    query: 'analyze',
                    answer: JSON.stringify({
                        recommendation: 'WAIT',
                        confidence: 85,
                        reasoning: 'Prepare for meeting',
                        suggested_action: 'Review agenda'
                    }),
                    toolsCalled: [],
                    totalLatencyMs: 100,
                });

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(true);
            expect(result.decision?.confidence).toBeGreaterThanOrEqual(70);
        });
    });

    describe('TASK_REMINDER Evaluator', () => {
        it('should trigger when task is due within reminder window', async () => {
            const dueDate = new Date(Date.now() + 30 * 60 * 1000);

            const monitor = {
                id: 'test-1',
                type: 'TASK_REMINDER',
                config: {
                    task_name: 'Complete report',
                    due_date: dueDate.toISOString(),
                    reminder_minutes: '60'
                },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(true);
            expect(result.decision?.confidence).toBe(100);
        });

        it('should not trigger when task is not due yet', async () => {
            const dueDate = new Date(Date.now() + 120 * 60 * 1000);

            const monitor = {
                id: 'test-1',
                type: 'TASK_REMINDER',
                config: {
                    task_name: 'Complete report',
                    due_date: dueDate.toISOString(),
                    reminder_minutes: '60'
                },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(false);
        });
    });

    describe('INBOX_WATCH Evaluator', () => {
        it('should trigger when new emails match criteria', async () => {
            const monitor = {
                id: 'test-1',
                type: 'INBOX_WATCH',
                config: { keywords: ['urgent'], sender: null },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);
            mockQuery.mockResolvedValue({
                query: 'inbox',
                answer: JSON.stringify({
                    emails: [{ from: 'boss@company.com', subject: 'Urgent', timestamp: new Date().toISOString() }]
                }),
                toolsCalled: [],
                totalLatencyMs: 100,
            });

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(true);
        });
    });

    describe('CALENDAR_WATCH Evaluator', () => {
        it('should trigger when events in look-ahead window', async () => {
            const eventStart = new Date(Date.now() + 15 * 60 * 1000);

            const monitor = {
                id: 'test-1',
                type: 'CALENDAR_WATCH',
                config: { look_ahead_minutes: '30' },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);
            mockQuery.mockResolvedValue({
                query: 'calendar',
                answer: JSON.stringify({
                    events: [{ start: eventStart.toISOString(), title: 'Meeting' }]
                }),
                toolsCalled: [],
                totalLatencyMs: 100,
            });

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(true);
        });
    });

    // =========================================================================
    // System Monitors Tests
    // =========================================================================

    describe('SCHEDULED Evaluator', () => {
        it('should always trigger', async () => {
            const monitor = {
                id: 'test-1',
                type: 'SCHEDULED',
                config: { task: 'backup' },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(true);
            expect(result.decision?.confidence).toBe(100);
        });
    });

    describe('EVENT_DRIVEN Evaluator', () => {
        it('should always trigger', async () => {
            const monitor = {
                id: 'test-1',
                type: 'EVENT_DRIVEN',
                config: {},
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(true);
        });
    });

    describe('FILE_WATCH Evaluator', () => {
        it('should return stub response', async () => {
            const monitor = {
                id: 'test-1',
                type: 'FILE_WATCH',
                config: { path: '/data/logs' },
            } as Partial<Monitor>;

            mockGetMonitor.mockResolvedValue(monitor);

            const result = await evaluatorService.evaluate('test-1');

            expect(result.trigger).toBe(false);
            expect(result.decision?.reasoning).toContain('not fully implemented');
        });
    });
});
