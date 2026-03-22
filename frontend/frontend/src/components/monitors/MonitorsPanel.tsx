/**
 * Monitors Panel Component
 *
 * UI per gestione monitor proattivi (Phase 5).
 * Permette di visualizzare, creare, pausare e eliminare monitor.
 */

'use client';

import { useState, useEffect, useCallback } from 'react';
import { useMonitorNotifications } from '@/hooks/useMonitorNotifications';
import { API_CONFIG } from '@/lib/config';

// Types
interface MonitorConfig {
    ticker?: string;
    condition?: string;
    threshold?: number;
    goal?: string;
    min_confidence?: number;
    cron_expression?: string;
    task?: string;
}

interface EvaluationResult {
    monitor_id: string;
    evaluated_at: string;
    trigger: boolean;
    decision?: {
        recommendation: string;
        confidence: number;
        reasoning: string;
        key_factors: string[];
    };
    error?: string;
}

interface Monitor {
    id: string;
    user_id: string;
    type: 'PRICE_WATCH' | 'SIGNAL_WATCH' | 'AUTONOMOUS' | 'SCHEDULED' | 'EVENT_DRIVEN' | 'HEARTBEAT' | 'TASK_REMINDER' | 'INBOX_WATCH' | 'CALENDAR_WATCH' | 'FILE_WATCH';
    name: string;
    description?: string;
    config: MonitorConfig;
    interval_minutes: number;
    notify_channels: string[];
    state: 'ACTIVE' | 'PAUSED' | 'TRIGGERED' | 'COMPLETED' | 'ERROR';
    created_at: string;
    last_check?: string;
    next_check?: string;
    checks_count: number;
    triggers_count: number;
    history: EvaluationResult[];
}

interface MonitorListResponse {
    monitors: Monitor[];
    total: number;
    active_count: number;
    paused_count: number;
}

interface MonitorStatsResponse {
    total_monitors: number;
    active_monitors: number;
    total_checks: number;
    total_triggers: number;
    by_type: Record<string, number>;
}

// API Base URL
const API_BASE = API_CONFIG.gatewayUrl;

// API Helpers
const API_HEADERS = {
    'Content-Type': 'application/json',
    'x-user-id': 'default', // TODO: Get from auth context
};

async function fetchMonitors(): Promise<MonitorListResponse> {
    const res = await fetch(`${API_BASE}/api/monitors`, {
        headers: API_HEADERS,
    });
    if (!res.ok) throw new Error('Failed to fetch monitors');
    const data = await res.json();
    // Handle new Gateway response format
    return data.monitors ? data : { monitors: data, total: data.length, active_count: 0, paused_count: 0 };
}

// Calculate stats client-side (Gateway /stats endpoint not yet implemented)
function calculateStats(monitors: Monitor[]): MonitorStatsResponse {
    return {
        total_monitors: monitors.length,
        active_monitors: monitors.filter(m => m.state === 'ACTIVE').length,
        total_checks: monitors.reduce((sum, m) => sum + m.checks_count, 0),
        total_triggers: monitors.reduce((sum, m) => sum + m.triggers_count, 0),
        by_type: monitors.reduce((acc, m) => {
            acc[m.type] = (acc[m.type] || 0) + 1;
            return acc;
        }, {} as Record<string, number>),
    };
}

async function createMonitor(data: {
    type: string;
    name: string;
    config: MonitorConfig;
    interval_minutes?: number;
}): Promise<Monitor> {
    const res = await fetch(`${API_BASE}/api/monitors`, {
        method: 'POST',
        headers: API_HEADERS,
        body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to create monitor');
    const result = await res.json();
    // Handle new Gateway response format
    return result.monitor || result;
}

async function pauseMonitor(id: string): Promise<void> {
    const res = await fetch(`${API_BASE}/api/monitors/${id}/pause`, {
        method: 'POST',
        headers: API_HEADERS,
    });
    if (!res.ok) throw new Error('Failed to pause monitor');
}

async function resumeMonitor(id: string): Promise<void> {
    const res = await fetch(`${API_BASE}/api/monitors/${id}/resume`, {
        method: 'POST',
        headers: API_HEADERS,
    });
    if (!res.ok) throw new Error('Failed to resume monitor');
}

async function deleteMonitor(id: string): Promise<void> {
    const res = await fetch(`${API_BASE}/api/monitors/${id}`, {
        method: 'DELETE',
        headers: API_HEADERS,
    });
    if (!res.ok) throw new Error('Failed to delete monitor');
}

async function triggerMonitor(id: string): Promise<void> {
    const res = await fetch(`${API_BASE}/api/monitors/${id}/trigger`, {
        method: 'POST',
        headers: API_HEADERS,
    });
    if (!res.ok) throw new Error('Failed to trigger monitor');
}

// Monitor Type Config (Updated to match Gateway enums)
const MONITOR_TYPES: Record<string, { icon: string; label: string; color: string }> = {
    PRICE_WATCH: { icon: '💰', label: 'Price Watch', color: 'var(--color-gold)' },
    SIGNAL_WATCH: { icon: '📊', label: 'Signal Watch', color: 'var(--color-blue)' },
    AUTONOMOUS: { icon: '🤖', label: 'Autonomous', color: 'var(--color-purple)' },
    SCHEDULED: { icon: '📅', label: 'Scheduled', color: 'var(--color-green)' },
    EVENT_DRIVEN: { icon: '⚡', label: 'Event Driven', color: 'var(--color-orange)' },
    HEARTBEAT: { icon: '💓', label: 'Heartbeat', color: 'var(--color-pink)' },
    TASK_REMINDER: { icon: '📝', label: 'Task Reminder', color: 'var(--color-cyan)' },
    INBOX_WATCH: { icon: '📧', label: 'Inbox Watch', color: 'var(--color-blue)' },
    CALENDAR_WATCH: { icon: '📅', label: 'Calendar Watch', color: 'var(--color-green)' },
    FILE_WATCH: { icon: '📁', label: 'File Watch', color: 'var(--color-orange)' },
};

const STATE_BADGES: Record<string, { icon: string; label: string; color: string }> = {
    ACTIVE: { icon: '▶️', label: 'Active', color: 'var(--color-green)' },
    PAUSED: { icon: '⏸️', label: 'Paused', color: 'var(--color-yellow)' },
    TRIGGERED: { icon: '🔔', label: 'Triggered', color: 'var(--color-red)' },
    COMPLETED: { icon: '✅', label: 'Completed', color: 'var(--color-blue)' },
    ERROR: { icon: '❌', label: 'Error', color: 'var(--color-red)' },
};

// Main Component
export default function MonitorsPanel() {
    const [monitors, setMonitors] = useState<Monitor[]>([]);
    const [stats, setStats] = useState<MonitorStatsResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [selectedMonitor, setSelectedMonitor] = useState<Monitor | null>(null);
    const [realtimeAlert, setRealtimeAlert] = useState<{
        monitorId: string;
        title: string;
        message: string;
    } | null>(null);

    // WebSocket notifications hook
    const { connected: wsConnected, alerts: recentAlerts, clearAlerts } = useMonitorNotifications({
        onAlert: (alert) => {
            // Show toast and refresh data quando arriva un alert
            setRealtimeAlert({
                monitorId: alert.monitorId,
                title: alert.title,
                message: alert.message,
            });
            loadData(); // Refresh monitor list
            setTimeout(() => setRealtimeAlert(null), 5000); // Auto-hide after 5s
        },
        onUpdate: () => {
            // Refresh monitor list on any update
            loadData();
        },
    });

    // Load data
    const loadData = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const monitorsData = await fetchMonitors();
            const monitors = monitorsData.monitors || [];
            setMonitors(monitors);
            // Calculate stats client-side
            setStats(calculateStats(monitors));
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadData();
        // Refresh every 30 seconds
        const interval = setInterval(loadData, 30000);
        return () => clearInterval(interval);
    }, [loadData]);

    // Actions
    const handlePause = async (id: string) => {
        try {
            await pauseMonitor(id);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to pause');
        }
    };

    const handleResume = async (id: string) => {
        try {
            await resumeMonitor(id);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to resume');
        }
    };

    const handleDelete = async (id: string) => {
        if (!confirm('Sei sicuro di voler eliminare questo monitor?')) return;
        try {
            await deleteMonitor(id);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to delete');
        }
    };

    const handleTrigger = async (id: string) => {
        try {
            await triggerMonitor(id);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to trigger');
        }
    };

    const handleCreate = async (data: {
        type: string;
        name: string;
        config: MonitorConfig;
        interval_minutes: number;
    }) => {
        try {
            await createMonitor(data);
            setShowCreateModal(false);
            await loadData();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create');
        }
    };

    return (
        <div className="monitors-panel">
            {/* Header */}
            <div className="monitors-header">
                <div className="monitors-title">
                    <span className="monitors-icon">🔔</span>
                    <h2>Proactive Monitors</h2>
                </div>
                <div className="monitors-actions">
                    <button
                        className="btn-icon"
                        onClick={loadData}
                        title="Refresh"
                    >
                        🔄
                    </button>
                    <button
                        className="btn-primary"
                        onClick={() => setShowCreateModal(true)}
                    >
                        + New Monitor
                    </button>
                </div>
            </div>

            {/* Stats Bar */}
            {stats && (
                <div className="monitors-stats">
                    <div className="stat-item">
                        <span className="stat-value">{stats.total_monitors}</span>
                        <span className="stat-label">Total</span>
                    </div>
                    <div className="stat-item">
                        <span className="stat-value">{stats.active_monitors}</span>
                        <span className="stat-label">Active</span>
                    </div>
                    <div className="stat-item">
                        <span className="stat-value">{stats.total_checks}</span>
                        <span className="stat-label">Checks</span>
                    </div>
                    <div className="stat-item">
                        <span className="stat-value">{stats.total_triggers}</span>
                        <span className="stat-label">Triggers</span>
                    </div>
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="monitors-error">
                    ⚠️ {error}
                    <button onClick={() => setError(null)}>×</button>
                </div>
            )}

            {/* Loading */}
            {loading && monitors.length === 0 && (
                <div className="monitors-loading">
                    <div className="spinner" />
                    Caricamento monitor...
                </div>
            )}

            {/* Empty State */}
            {!loading && monitors.length === 0 && (
                <div className="monitors-empty">
                    <div className="empty-icon">🔔</div>
                    <h3>Nessun monitor attivo</h3>
                    <p>
                        Crea un monitor per ricevere notifiche automatiche
                        quando vengono soddisfatte determinate condizioni.
                    </p>
                    <button
                        className="btn-primary"
                        onClick={() => setShowCreateModal(true)}
                    >
                        + Crea il tuo primo monitor
                    </button>
                </div>
            )}

            {/* Monitor List */}
            <div className="monitors-list">
                {monitors.map((monitor) => (
                    <MonitorCard
                        key={monitor.id}
                        monitor={monitor}
                        onPause={() => handlePause(monitor.id)}
                        onResume={() => handleResume(monitor.id)}
                        onDelete={() => handleDelete(monitor.id)}
                        onTrigger={() => handleTrigger(monitor.id)}
                        onSelect={() => setSelectedMonitor(monitor)}
                    />
                ))}
            </div>

            {/* Create Modal */}
            {showCreateModal && (
                <CreateMonitorModal
                    onClose={() => setShowCreateModal(false)}
                    onCreate={handleCreate}
                />
            )}

            {/* Detail Modal */}
            {selectedMonitor && (
                <MonitorDetailModal
                    monitor={selectedMonitor}
                    onClose={() => setSelectedMonitor(null)}
                />
            )}

            <style jsx>{`
                .monitors-panel {
                    background: var(--glass-bg, rgba(28, 28, 30, 0.85));
                    backdrop-filter: blur(20px);
                    border-radius: 16px;
                    border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.08));
                    padding: 20px;
                    color: var(--text-primary, #fff);
                }

                .monitors-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 16px;
                }

                .monitors-title {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }

                .monitors-icon {
                    font-size: 24px;
                }

                .monitors-title h2 {
                    font-size: 18px;
                    font-weight: 600;
                    margin: 0;
                }

                .monitors-actions {
                    display: flex;
                    gap: 8px;
                }

                .btn-icon {
                    background: transparent;
                    border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.1));
                    border-radius: 8px;
                    padding: 8px;
                    cursor: pointer;
                    font-size: 16px;
                    transition: all 0.2s;
                }

                .btn-icon:hover {
                    background: rgba(255, 255, 255, 0.1);
                }

                .btn-primary {
                    background: var(--accent-blue, #007aff);
                    border: none;
                    border-radius: 8px;
                    padding: 8px 16px;
                    color: white;
                    font-weight: 500;
                    cursor: pointer;
                    transition: all 0.2s;
                }

                .btn-primary:hover {
                    background: var(--accent-blue-hover, #0066cc);
                }

                .monitors-stats {
                    display: grid;
                    grid-template-columns: repeat(4, 1fr);
                    gap: 12px;
                    margin-bottom: 16px;
                    padding: 12px;
                    background: rgba(0, 0, 0, 0.2);
                    border-radius: 12px;
                }

                .stat-item {
                    text-align: center;
                }

                .stat-value {
                    display: block;
                    font-size: 24px;
                    font-weight: 700;
                    color: var(--accent-blue, #007aff);
                }

                .stat-label {
                    font-size: 12px;
                    color: var(--text-secondary, rgba(255, 255, 255, 0.6));
                }

                .monitors-error {
                    background: rgba(255, 59, 48, 0.2);
                    border: 1px solid rgba(255, 59, 48, 0.4);
                    border-radius: 8px;
                    padding: 12px;
                    margin-bottom: 16px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }

                .monitors-error button {
                    background: none;
                    border: none;
                    color: white;
                    font-size: 18px;
                    cursor: pointer;
                }

                .monitors-loading {
                    text-align: center;
                    padding: 40px;
                    color: var(--text-secondary);
                }

                .spinner {
                    width: 32px;
                    height: 32px;
                    border: 3px solid rgba(255, 255, 255, 0.1);
                    border-top-color: var(--accent-blue);
                    border-radius: 50%;
                    margin: 0 auto 16px;
                    animation: spin 1s linear infinite;
                }

                @keyframes spin {
                    to {
                        transform: rotate(360deg);
                    }
                }

                .monitors-empty {
                    text-align: center;
                    padding: 40px 20px;
                }

                .empty-icon {
                    font-size: 48px;
                    margin-bottom: 16px;
                }

                .monitors-empty h3 {
                    font-size: 18px;
                    margin: 0 0 8px;
                }

                .monitors-empty p {
                    font-size: 14px;
                    color: var(--text-secondary);
                    margin: 0 0 20px;
                }

                .monitors-list {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }
            `}</style>
        </div>
    );
}

// Monitor Card Component
function MonitorCard({
    monitor,
    onPause,
    onResume,
    onDelete,
    onTrigger,
    onSelect,
}: {
    monitor: Monitor;
    onPause: () => void;
    onResume: () => void;
    onDelete: () => void;
    onTrigger: () => void;
    onSelect: () => void;
}) {
    const typeConfig = MONITOR_TYPES[monitor.type];
    const stateConfig = STATE_BADGES[monitor.state];

    const formatDate = (dateStr?: string) => {
        if (!dateStr) return '—';
        return new Date(dateStr).toLocaleString('it-IT', {
            hour: '2-digit',
            minute: '2-digit',
            day: '2-digit',
            month: 'short',
        });
    };

    return (
        <div className="monitor-card" onClick={onSelect}>
            <div className="monitor-info">
                <div className="monitor-type" style={{ color: typeConfig.color }}>
                    {typeConfig.icon}
                </div>
                <div className="monitor-details">
                    <div className="monitor-name">{monitor.name}</div>
                    <div className="monitor-meta">
                        {monitor.config.ticker && <span>{monitor.config.ticker}</span>}
                        <span>ogni {monitor.interval_minutes} min</span>
                    </div>
                </div>
            </div>

            <div className="monitor-status">
                <div className="state-badge" style={{ background: stateConfig.color }}>
                    {stateConfig.icon} {stateConfig.label}
                </div>
                <div className="monitor-counts">
                    <span title="Checks">{monitor.checks_count} 🔍</span>
                    <span title="Triggers">{monitor.triggers_count} 🔔</span>
                </div>
                {monitor.next_check && (
                    <div className="next-check">
                        Next: {formatDate(monitor.next_check)}
                    </div>
                )}
            </div>

            <div className="monitor-actions" onClick={(e) => e.stopPropagation()}>
                {monitor.state === 'ACTIVE' ? (
                    <button onClick={onPause} title="Pause">
                        ⏸️
                    </button>
                ) : monitor.state === 'PAUSED' ? (
                    <button onClick={onResume} title="Resume">
                        ▶️
                    </button>
                ) : null}
                <button onClick={onTrigger} title="Trigger Now">
                    ⚡
                </button>
                <button onClick={onDelete} title="Delete" className="delete-btn">
                    🗑️
                </button>
            </div>

            <style jsx>{`
                .monitor-card {
                    display: flex;
                    align-items: center;
                    gap: 16px;
                    background: rgba(0, 0, 0, 0.2);
                    border-radius: 12px;
                    padding: 16px;
                    cursor: pointer;
                    transition: all 0.2s;
                }

                .monitor-card:hover {
                    background: rgba(0, 0, 0, 0.3);
                }

                .monitor-info {
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    flex: 1;
                }

                .monitor-type {
                    font-size: 24px;
                }

                .monitor-details {
                    flex: 1;
                }

                .monitor-name {
                    font-weight: 600;
                    font-size: 15px;
                }

                .monitor-meta {
                    font-size: 12px;
                    color: var(--text-secondary);
                    display: flex;
                    gap: 8px;
                }

                .monitor-status {
                    display: flex;
                    flex-direction: column;
                    align-items: flex-end;
                    gap: 4px;
                }

                .state-badge {
                    font-size: 11px;
                    padding: 4px 8px;
                    border-radius: 12px;
                    color: white;
                }

                .monitor-counts {
                    font-size: 12px;
                    color: var(--text-secondary);
                    display: flex;
                    gap: 8px;
                }

                .next-check {
                    font-size: 11px;
                    color: var(--text-secondary);
                }

                .monitor-actions {
                    display: flex;
                    gap: 8px;
                }

                .monitor-actions button {
                    background: rgba(255, 255, 255, 0.1);
                    border: none;
                    border-radius: 8px;
                    padding: 8px;
                    cursor: pointer;
                    font-size: 14px;
                    transition: all 0.2s;
                }

                .monitor-actions button:hover {
                    background: rgba(255, 255, 255, 0.2);
                }

                .delete-btn:hover {
                    background: rgba(255, 59, 48, 0.3) !important;
                }
            `}</style>
        </div>
    );
}

// Create Monitor Modal
function CreateMonitorModal({
    onClose,
    onCreate,
}: {
    onClose: () => void;
    onCreate: (data: {
        type: string;
        name: string;
        config: MonitorConfig;
        interval_minutes: number;
    }) => void;
}) {
    const [type, setType] = useState<string>('PRICE_WATCH');
    const [name, setName] = useState('');
    const [ticker, setTicker] = useState('');
    const [threshold, setThreshold] = useState('');
    const [condition, setCondition] = useState('below');
    const [interval, setInterval] = useState('15');

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        onCreate({
            type,
            name,
            config: {
                ticker,
                condition,
                threshold: parseFloat(threshold),
            },
            interval_minutes: parseInt(interval),
        });
    };

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                <h3>Nuovo Monitor</h3>
                <form onSubmit={handleSubmit}>
                    <div className="form-group">
                        <label>Tipo</label>
                        <select value={type} onChange={(e) => setType(e.target.value)}>
                            {Object.entries(MONITOR_TYPES).map(([key, config]) => (
                                <option key={key} value={key}>
                                    {config.icon} {config.label}
                                </option>
                            ))}
                        </select>
                    </div>

                    <div className="form-group">
                        <label>Nome</label>
                        <input
                            type="text"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="Es: AAPL Price Alert"
                            required
                        />
                    </div>

                    <div className="form-group">
                        <label>Ticker</label>
                        <input
                            type="text"
                            value={ticker}
                            onChange={(e) => setTicker(e.target.value.toUpperCase())}
                            placeholder="Es: AAPL, TSLA, GOOGL"
                            required
                        />
                    </div>

                    <div className="form-row">
                        <div className="form-group">
                            <label>Condizione</label>
                            <select
                                value={condition}
                                onChange={(e) => setCondition(e.target.value)}
                            >
                                <option value="below">Sotto</option>
                                <option value="above">Sopra</option>
                            </select>
                        </div>
                        <div className="form-group">
                            <label>Soglia ($)</label>
                            <input
                                type="number"
                                value={threshold}
                                onChange={(e) => setThreshold(e.target.value)}
                                placeholder="180"
                                step="0.01"
                            />
                        </div>
                    </div>

                    <div className="form-group">
                        <label>Intervallo (minuti)</label>
                        <select value={interval} onChange={(e) => setInterval(e.target.value)}>
                            <option value="5">5 min</option>
                            <option value="15">15 min</option>
                            <option value="30">30 min</option>
                            <option value="60">1 ora</option>
                        </select>
                    </div>

                    <div className="modal-actions">
                        <button type="button" onClick={onClose} className="btn-cancel">
                            Annulla
                        </button>
                        <button type="submit" className="btn-primary">
                            Crea Monitor
                        </button>
                    </div>
                </form>

                <style jsx>{`
                    .modal-overlay {
                        position: fixed;
                        inset: 0;
                        background: rgba(0, 0, 0, 0.7);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        z-index: 1000;
                    }

                    .modal-content {
                        background: var(--glass-bg, rgba(28, 28, 30, 0.95));
                        backdrop-filter: blur(20px);
                        border-radius: 16px;
                        border: 1px solid var(--glass-border);
                        padding: 24px;
                        width: 400px;
                        max-width: 90vw;
                    }

                    h3 {
                        margin: 0 0 20px;
                        font-size: 18px;
                    }

                    .form-group {
                        margin-bottom: 16px;
                    }

                    .form-row {
                        display: grid;
                        grid-template-columns: 1fr 1fr;
                        gap: 12px;
                    }

                    label {
                        display: block;
                        font-size: 13px;
                        color: var(--text-secondary);
                        margin-bottom: 6px;
                    }

                    input,
                    select {
                        width: 100%;
                        background: rgba(0, 0, 0, 0.3);
                        border: 1px solid var(--glass-border);
                        border-radius: 8px;
                        padding: 10px 12px;
                        color: white;
                        font-size: 14px;
                    }

                    input:focus,
                    select:focus {
                        outline: none;
                        border-color: var(--accent-blue);
                    }

                    .modal-actions {
                        display: flex;
                        gap: 12px;
                        margin-top: 24px;
                    }

                    .btn-cancel {
                        flex: 1;
                        background: rgba(255, 255, 255, 0.1);
                        border: none;
                        border-radius: 8px;
                        padding: 12px;
                        color: white;
                        cursor: pointer;
                    }

                    .btn-primary {
                        flex: 1;
                        background: var(--accent-blue);
                        border: none;
                        border-radius: 8px;
                        padding: 12px;
                        color: white;
                        cursor: pointer;
                        font-weight: 500;
                    }
                `}</style>
            </div>
        </div>
    );
}

// Monitor Detail Modal
function MonitorDetailModal({
    monitor,
    onClose,
}: {
    monitor: Monitor;
    onClose: () => void;
}) {
    const typeConfig = MONITOR_TYPES[monitor.type];

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                <div className="detail-header">
                    <span className="type-icon" style={{ color: typeConfig.color }}>
                        {typeConfig.icon}
                    </span>
                    <h3>{monitor.name}</h3>
                    <button className="close-btn" onClick={onClose}>
                        ×
                    </button>
                </div>

                <div className="detail-section">
                    <h4>Configurazione</h4>
                    <pre>{JSON.stringify(monitor.config, null, 2)}</pre>
                </div>

                <div className="detail-section">
                    <h4>Statistiche</h4>
                    <div className="stats-grid">
                        <div>
                            <span className="stat-value">{monitor.checks_count}</span>
                            <span className="stat-label">Checks</span>
                        </div>
                        <div>
                            <span className="stat-value">{monitor.triggers_count}</span>
                            <span className="stat-label">Triggers</span>
                        </div>
                        <div>
                            <span className="stat-value">{monitor.interval_minutes}m</span>
                            <span className="stat-label">Intervallo</span>
                        </div>
                    </div>
                </div>

                {monitor.history.length > 0 && (
                    <div className="detail-section">
                        <h4>Ultime Valutazioni</h4>
                        <div className="history-list">
                            {monitor.history.slice(0, 5).map((result, i) => (
                                <div key={i} className="history-item">
                                    <span className={result.trigger ? 'trigger' : ''}>
                                        {result.trigger ? '🔔' : '✓'}
                                    </span>
                                    <span>{new Date(result.evaluated_at).toLocaleString()}</span>
                                    {result.decision && (
                                        <span className="decision">
                                            {result.decision.recommendation} (
                                            {result.decision.confidence}%)
                                        </span>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                <style jsx>{`
                    .modal-overlay {
                        position: fixed;
                        inset: 0;
                        background: rgba(0, 0, 0, 0.7);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        z-index: 1000;
                    }

                    .modal-content {
                        background: var(--glass-bg, rgba(28, 28, 30, 0.95));
                        backdrop-filter: blur(20px);
                        border-radius: 16px;
                        border: 1px solid var(--glass-border);
                        padding: 24px;
                        width: 500px;
                        max-width: 90vw;
                        max-height: 80vh;
                        overflow-y: auto;
                    }

                    .detail-header {
                        display: flex;
                        align-items: center;
                        gap: 12px;
                        margin-bottom: 20px;
                    }

                    .type-icon {
                        font-size: 28px;
                    }

                    h3 {
                        flex: 1;
                        margin: 0;
                        font-size: 18px;
                    }

                    .close-btn {
                        background: none;
                        border: none;
                        font-size: 24px;
                        color: var(--text-secondary);
                        cursor: pointer;
                    }

                    .detail-section {
                        margin-bottom: 20px;
                    }

                    h4 {
                        font-size: 14px;
                        color: var(--text-secondary);
                        margin: 0 0 8px;
                    }

                    pre {
                        background: rgba(0, 0, 0, 0.3);
                        padding: 12px;
                        border-radius: 8px;
                        font-size: 12px;
                        overflow-x: auto;
                        margin: 0;
                    }

                    .stats-grid {
                        display: grid;
                        grid-template-columns: repeat(3, 1fr);
                        gap: 12px;
                        text-align: center;
                    }

                    .stat-value {
                        display: block;
                        font-size: 24px;
                        font-weight: 700;
                        color: var(--accent-blue);
                    }

                    .stat-label {
                        font-size: 12px;
                        color: var(--text-secondary);
                    }

                    .history-list {
                        background: rgba(0, 0, 0, 0.2);
                        border-radius: 8px;
                        padding: 8px;
                    }

                    .history-item {
                        display: flex;
                        gap: 12px;
                        padding: 8px;
                        font-size: 13px;
                        border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                    }

                    .history-item:last-child {
                        border-bottom: none;
                    }

                    .trigger {
                        color: var(--color-red, #ff3b30);
                    }

                    .decision {
                        color: var(--text-secondary);
                        margin-left: auto;
                    }
                `}</style>
            </div>
        </div>
    );
}
