/**
 * Notification Service Unit Tests
 * 
 * Tests for NotificationService with mocked Redis and WebSocket connections.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { NotificationService, MonitorAlert } from '../notification.service.js';
import type { Redis } from 'ioredis';
import { connectionRegistry } from '../../../websocket/registry.js';

// Mock connectionRegistry
vi.mock('../../../websocket/registry.js', () => ({
    connectionRegistry: {
        sendMonitorAlert: vi.fn(),
    },
}));

describe('NotificationService', () => {
    let notificationService: NotificationService;
    let mockRedis: Redis;

    beforeEach(() => {
        // Create mock Redis
        mockRedis = {
            lpush: vi.fn().mockResolvedValue(1),
            ltrim: vi.fn().mockResolvedValue('OK'),
            lrange: vi.fn().mockResolvedValue([]),
        } as unknown as Redis;

        notificationService = new NotificationService(mockRedis);

        // Reset mocks
        vi.clearAllMocks();
    });

    describe('sendMonitorAlert', () => {
        const mockAlert: MonitorAlert = {
            monitorId: 'mon-123',
            monitorName: 'Test Monitor',
            monitorType: 'PRICE_WATCH',
            trigger: true,
            decision: {
                recommendation: 'BUY',
                confidence: 85,
                reasoning: 'Price below threshold',
            },
            data: { price: 150, threshold: 160 },
            timestamp: '2026-02-28T20:00:00Z',
        };

        it('should send alert via WebSocket when user connected', async () => {
            vi.mocked(connectionRegistry.sendMonitorAlert).mockReturnValue(1);

            await notificationService.sendMonitorAlert('user-123', mockAlert);

            expect(connectionRegistry.sendMonitorAlert).toHaveBeenCalledWith(
                'user-123',
                expect.objectContaining({
                    monitorId: 'mon-123',
                    monitorName: 'Test Monitor',
                    monitorType: 'PRICE_WATCH',
                    message: 'Price below threshold',
                    severity: 'critical',
                    timestamp: '2026-02-28T20:00:00Z',
                })
            );
        });

        it('should log warning when user not connected', async () => {
            vi.mocked(connectionRegistry.sendMonitorAlert).mockReturnValue(0);

            await notificationService.sendMonitorAlert('user-123', mockAlert);

            expect(connectionRegistry.sendMonitorAlert).toHaveBeenCalled();
            // Warning logged (checked via logger mock if needed)
        });

        it('should store notification in Redis', async () => {
            vi.mocked(connectionRegistry.sendMonitorAlert).mockReturnValue(1);

            await notificationService.sendMonitorAlert('user-123', mockAlert);

            expect(mockRedis.lpush).toHaveBeenCalledWith(
                'notifications:user:user-123',
                JSON.stringify(mockAlert)
            );
            expect(mockRedis.ltrim).toHaveBeenCalledWith(
                'notifications:user:user-123',
                0,
                49
            );
        });
    });

    describe('getNotificationHistory', () => {
        it('should return notification history from Redis', async () => {
            const mockAlerts: MonitorAlert[] = [
                {
                    monitorId: 'mon-1',
                    monitorName: 'Alert 1',
                    monitorType: 'PRICE_WATCH',
                    trigger: true,
                    decision: { recommendation: 'BUY', confidence: 80, reasoning: 'Test' },
                    data: {},
                    timestamp: '2026-02-28T20:00:00Z',
                },
                {
                    monitorId: 'mon-2',
                    monitorName: 'Alert 2',
                    monitorType: 'SIGNAL_WATCH',
                    trigger: true,
                    decision: { recommendation: 'SELL', confidence: 75, reasoning: 'Test' },
                    data: {},
                    timestamp: '2026-02-28T19:00:00Z',
                },
            ];

            vi.mocked(mockRedis.lrange).mockResolvedValue(
                mockAlerts.map(a => JSON.stringify(a))
            );

            const result = await notificationService.getNotificationHistory('user-123', 10);

            expect(mockRedis.lrange).toHaveBeenCalledWith('notifications:user:user-123', 0, 9);
            expect(result).toHaveLength(2);
            expect(result[0].monitorId).toBe('mon-1');
            expect(result[1].monitorId).toBe('mon-2');
        });

        it('should return empty array if no history', async () => {
            vi.mocked(mockRedis.lrange).mockResolvedValue([]);

            const result = await notificationService.getNotificationHistory('user-123');

            expect(result).toEqual([]);
        });

        it('should handle Redis errors gracefully', async () => {
            vi.mocked(mockRedis.lrange).mockRejectedValue(new Error('Redis error'));

            const result = await notificationService.getNotificationHistory('user-123');

            expect(result).toEqual([]);
        });
    });

    describe('replayNotifications', () => {
        it('should replay notifications since timestamp', async () => {
            const mockAlerts: MonitorAlert[] = [
                {
                    monitorId: 'mon-1',
                    monitorName: 'Recent Alert',
                    monitorType: 'PRICE_WATCH',
                    trigger: true,
                    decision: { recommendation: 'BUY', confidence: 80, reasoning: 'Test' },
                    data: {},
                    timestamp: '2026-02-28T20:00:00Z',
                },
                {
                    monitorId: 'mon-2',
                    monitorName: 'Old Alert',
                    monitorType: 'SIGNAL_WATCH',
                    trigger: true,
                    decision: { recommendation: 'SELL', confidence: 75, reasoning: 'Test' },
                    data: {},
                    timestamp: '2026-02-28T18:00:00Z',
                },
            ];

            vi.mocked(mockRedis.lrange).mockResolvedValue(
                mockAlerts.map(a => JSON.stringify(a))
            );
            vi.mocked(connectionRegistry.sendMonitorAlert).mockReturnValue(1);

            const since = new Date('2026-02-28T19:00:00Z');
            await notificationService.replayNotifications('user-123', since);

            // Should only replay the recent alert (after 19:00)
            expect(connectionRegistry.sendMonitorAlert).toHaveBeenCalledTimes(1);
            expect(connectionRegistry.sendMonitorAlert).toHaveBeenCalledWith(
                'user-123',
                expect.objectContaining({
                    monitorId: 'mon-1',
                })
            );
        });

        it('should handle no notifications case', async () => {
            vi.mocked(mockRedis.lrange).mockResolvedValue([]);

            await notificationService.replayNotifications('user-123');

            expect(connectionRegistry.sendMonitorAlert).not.toHaveBeenCalled();
        });

        it('should replay all notifications if no since timestamp', async () => {
            const mockAlerts: MonitorAlert[] = [
                {
                    monitorId: 'mon-1',
                    monitorName: 'Alert 1',
                    monitorType: 'PRICE_WATCH',
                    trigger: true,
                    decision: { recommendation: 'BUY', confidence: 80, reasoning: 'Test' },
                    data: {},
                    timestamp: '2026-02-28T20:00:00Z',
                },
                {
                    monitorId: 'mon-2',
                    monitorName: 'Alert 2',
                    monitorType: 'SIGNAL_WATCH',
                    trigger: true,
                    decision: { recommendation: 'SELL', confidence: 75, reasoning: 'Test' },
                    data: {},
                    timestamp: '2026-02-28T19:00:00Z',
                },
            ];

            vi.mocked(mockRedis.lrange).mockResolvedValue(
                mockAlerts.map(a => JSON.stringify(a))
            );
            vi.mocked(connectionRegistry.sendMonitorAlert).mockReturnValue(1);

            await notificationService.replayNotifications('user-123');

            expect(connectionRegistry.sendMonitorAlert).toHaveBeenCalledTimes(2);
        });
    });

    describe('getSeverity', () => {
        it('should return critical for high confidence (>= 80)', async () => {
            const alert: MonitorAlert = {
                monitorId: 'mon-1',
                monitorName: 'Test',
                monitorType: 'PRICE_WATCH',
                trigger: true,
                decision: { recommendation: 'BUY', confidence: 85, reasoning: 'Test' },
                data: {},
                timestamp: '2026-02-28T20:00:00Z',
            };

            vi.mocked(connectionRegistry.sendMonitorAlert).mockReturnValue(1);
            await notificationService.sendMonitorAlert('user-123', alert);

            expect(connectionRegistry.sendMonitorAlert).toHaveBeenCalledWith(
                'user-123',
                expect.objectContaining({ severity: 'critical' })
            );
        });

        it('should return warning for medium confidence (60-79)', async () => {
            const alert: MonitorAlert = {
                monitorId: 'mon-1',
                monitorName: 'Test',
                monitorType: 'PRICE_WATCH',
                trigger: true,
                decision: { recommendation: 'BUY', confidence: 70, reasoning: 'Test' },
                data: {},
                timestamp: '2026-02-28T20:00:00Z',
            };

            vi.mocked(connectionRegistry.sendMonitorAlert).mockReturnValue(1);
            await notificationService.sendMonitorAlert('user-123', alert);

            expect(connectionRegistry.sendMonitorAlert).toHaveBeenCalledWith(
                'user-123',
                expect.objectContaining({ severity: 'warning' })
            );
        });

        it('should return info for low confidence (< 60)', async () => {
            const alert: MonitorAlert = {
                monitorId: 'mon-1',
                monitorName: 'Test',
                monitorType: 'PRICE_WATCH',
                trigger: true,
                decision: { recommendation: 'BUY', confidence: 50, reasoning: 'Test' },
                data: {},
                timestamp: '2026-02-28T20:00:00Z',
            };

            vi.mocked(connectionRegistry.sendMonitorAlert).mockReturnValue(1);
            await notificationService.sendMonitorAlert('user-123', alert);

            expect(connectionRegistry.sendMonitorAlert).toHaveBeenCalledWith(
                'user-123',
                expect.objectContaining({ severity: 'info' })
            );
        });
    });
});
