/**
 * useMonitorNotifications Hook
 *
 * Gestisce connessione WebSocket per ricevere notifiche real-time
 * su trigger e aggiornamenti monitor.
 */

'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { API_CONFIG } from '@/lib/config';

// Gateway WebSocket URL from centralized config
const WS_URL = API_CONFIG.websocketUrl;

export interface MonitorAlert {
    monitorId: string;
    monitorName: string;
    type: string;
    title: string;
    message: string;
    recommendation?: string;
    confidence?: number;
    ticker?: string;
    triggeredAt: number;
}

export interface MonitorUpdate {
    monitorId: string;
    state: string;
    lastCheck?: string;
    nextCheck?: string;
}

interface WSMessage<T = unknown> {
    type: string;
    data: T;
    timestamp: number;
}

interface UseMonitorNotificationsOptions {
    onAlert?: (alert: MonitorAlert) => void;
    onUpdate?: (update: MonitorUpdate) => void;
    autoReconnect?: boolean;
    reconnectDelay?: number;
}

interface UseMonitorNotificationsResult {
    connected: boolean;
    alerts: MonitorAlert[];
    clearAlerts: () => void;
}

export function useMonitorNotifications(
    options: UseMonitorNotificationsOptions = {}
): UseMonitorNotificationsResult {
    const {
        onAlert,
        onUpdate,
        autoReconnect = true,
        reconnectDelay = 3000,
    } = options;

    const [connected, setConnected] = useState(false);
    const [alerts, setAlerts] = useState<MonitorAlert[]>([]);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

    const clearAlerts = useCallback(() => {
        setAlerts([]);
    }, []);

    const connect = useCallback(() => {
        if (wsRef.current?.readyState === WebSocket.OPEN) return;

        try {
            const ws = new WebSocket(WS_URL);

            ws.onopen = () => {
                console.log('[WS] Connected to Gateway');
                setConnected(true);

                // Invia messaggio di auth/session init
                ws.send(
                    JSON.stringify({
                        type: 'auth',
                        data: { userId: 'default' },
                    })
                );
            };

            ws.onmessage = (event) => {
                try {
                    const msg: WSMessage = JSON.parse(event.data);

                    if (msg.type === 'monitor:alert') {
                        const alert = msg.data as MonitorAlert;
                        console.log('[WS] Monitor alert received:', alert);

                        setAlerts((prev) => [alert, ...prev].slice(0, 50)); // Keep last 50

                        if (onAlert) {
                            onAlert(alert);
                        }

                        // Show browser notification if permitted
                        showBrowserNotification(alert);
                    }

                    if (msg.type === 'monitor:update') {
                        const update = msg.data as MonitorUpdate;
                        console.log('[WS] Monitor update received:', update);

                        if (onUpdate) {
                            onUpdate(update);
                        }
                    }
                } catch (e) {
                    console.error('[WS] Failed to parse message:', e);
                }
            };

            ws.onclose = (event) => {
                console.log('[WS] Disconnected:', event.code, event.reason);
                setConnected(false);
                wsRef.current = null;

                // Auto-reconnect
                if (autoReconnect && event.code !== 1000) {
                    reconnectTimeoutRef.current = setTimeout(() => {
                        console.log('[WS] Attempting reconnect...');
                        connect();
                    }, reconnectDelay);
                }
            };

            ws.onerror = (error) => {
                console.error('[WS] Error:', error);
            };

            wsRef.current = ws;
        } catch (error) {
            console.error('[WS] Failed to connect:', error);
        }
    }, [autoReconnect, reconnectDelay, onAlert, onUpdate]);

    // Connect on mount
    useEffect(() => {
        connect();

        return () => {
            if (reconnectTimeoutRef.current) {
                clearTimeout(reconnectTimeoutRef.current);
            }
            if (wsRef.current) {
                wsRef.current.close(1000, 'Component unmount');
            }
        };
    }, [connect]);

    return { connected, alerts, clearAlerts };
}

// Browser notifications
async function showBrowserNotification(alert: MonitorAlert): Promise<void> {
    if (!('Notification' in window)) return;

    if (Notification.permission === 'default') {
        await Notification.requestPermission();
    }

    if (Notification.permission === 'granted') {
        new Notification(alert.title, {
            body: alert.message,
            icon: '/favicon.ico',
            tag: alert.monitorId,
        });
    }
}

export default useMonitorNotifications;
