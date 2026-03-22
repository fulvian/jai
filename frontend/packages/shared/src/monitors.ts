/**
 * Monitors Types - Proactive System
 * 
 * Tipi Zod per il sistema di monitoring proattivo.
 * Sostituisce i modelli Pydantic in backend/proactive/monitors.py
 */

import { z } from 'zod';

// ============================================================================
// Enums
// ============================================================================

export const MonitorTypeSchema = z.enum([
    'PRICE_WATCH',
    'SIGNAL_WATCH',
    'AUTONOMOUS',
    'SCHEDULED',
    'EVENT_DRIVEN',
    'HEARTBEAT',
    'TASK_REMINDER',
    'INBOX_WATCH',
    'CALENDAR_WATCH',
    'FILE_WATCH',
]);

export type MonitorType = z.infer<typeof MonitorTypeSchema>;

export const MonitorStateSchema = z.enum([
    'ACTIVE',
    'PAUSED',
    'TRIGGERED',
    'COMPLETED',
    'ERROR',
]);

export type MonitorState = z.infer<typeof MonitorStateSchema>;

// ============================================================================
// Decision
// ============================================================================

export const DecisionSchema = z.object({
    recommendation: z.enum(['BUY', 'SELL', 'HOLD', 'WAIT']),
    confidence: z.number().min(0).max(100),
    reasoning: z.string(),
    key_factors: z.array(z.string()),
    suggested_action: z.string().optional(),
    position_size: z.number().optional(),
    stop_loss: z.number().optional(),
    take_profit: z.number().optional(),
});

export type Decision = z.infer<typeof DecisionSchema>;

// ============================================================================
// Evaluation Result
// ============================================================================

export const EvaluationResultSchema = z.object({
    timestamp: z.string(),
    trigger: z.boolean(),
    decision: DecisionSchema.optional(),
    data: z.record(z.unknown()).optional(),
    error: z.string().optional(),
});

export type EvaluationResult = z.infer<typeof EvaluationResultSchema>;

// ============================================================================
// Monitor
// ============================================================================

export const MonitorSchema = z.object({
    id: z.string().uuid(),
    user_id: z.string(),
    type: MonitorTypeSchema,
    name: z.string().min(1).max(200),
    description: z.string().optional(),
    config: z.record(z.unknown()),
    state: MonitorStateSchema.default('ACTIVE'),
    interval_minutes: z.number().int().min(1).default(60),
    notify_channels: z.array(z.enum(['telegram', 'slack', 'email', 'push'])).default(['push']),
    created_at: z.string(),
    updated_at: z.string(),
    last_check: z.string().optional(),
    next_check: z.string().optional(),
    checks_count: z.number().int().default(0),
    triggers_count: z.number().int().default(0),
    history: z.array(EvaluationResultSchema).default([]),
});

export type Monitor = z.infer<typeof MonitorSchema>;

// ============================================================================
// Create Monitor Request
// ============================================================================

export const CreateMonitorRequestSchema = z.object({
    type: MonitorTypeSchema,
    name: z.string().min(1).max(200),
    description: z.string().optional(),
    config: z.record(z.unknown()),
    interval_minutes: z.number().int().min(1).default(60),
    notify_channels: z.array(z.enum(['telegram', 'slack', 'email', 'push'])).default(['push']),
});

export type CreateMonitorRequest = z.infer<typeof CreateMonitorRequestSchema>;

// ============================================================================
// Monitor List Response
// ============================================================================

export const MonitorListResponseSchema = z.object({
    monitors: z.array(MonitorSchema),
    total: z.number().int(),
    active_count: z.number().int(),
    paused_count: z.number().int(),
});

export type MonitorListResponse = z.infer<typeof MonitorListResponseSchema>;

// ============================================================================
// Monitor Stats Response
// ============================================================================

export const MonitorStatsResponseSchema = z.object({
    total_monitors: z.number().int(),
    active_monitors: z.number().int(),
    total_checks: z.number().int(),
    total_triggers: z.number().int(),
    by_type: z.record(z.number().int()),
});

export type MonitorStatsResponse = z.infer<typeof MonitorStatsResponseSchema>;

// ============================================================================
// Config Schemas per Monitor Type
// ============================================================================

export const PriceWatchConfigSchema = z.object({
    ticker: z.string(),
    condition: z.enum(['above', 'below']),
    threshold: z.number(),
});

export const SignalWatchConfigSchema = z.object({
    ticker: z.string(),
    indicator: z.string(),
    condition: z.enum(['above', 'below', 'cross_above', 'cross_below']),
    threshold: z.number().optional(),
});

export const AutonomousConfigSchema = z.object({
    ticker: z.string(),
    goal: z.enum(['buy', 'sell', 'monitor']),
    min_confidence: z.number().min(0).max(100).default(70),
});

export const ScheduledConfigSchema = z.object({
    cron_expression: z.string(),
    task: z.string(),
});

export const HeartbeatConfigSchema = z.object({
    goal: z.string(),
    min_urgency: z.enum(['low', 'medium', 'high']).default('medium'),
});

export const TaskReminderConfigSchema = z.object({
    task: z.string(),
    due_date: z.string().optional(),
});

export const InboxWatchConfigSchema = z.object({
    filters: z.object({
        from: z.string().optional(),
        subject_contains: z.string().optional(),
        unread_only: z.boolean().default(true),
    }),
});

export const CalendarWatchConfigSchema = z.object({
    lookahead_minutes: z.number().int().min(1).default(15),
});

export const FileWatchConfigSchema = z.object({
    path: z.string(),
    pattern: z.string().optional(),
    event_types: z.array(z.enum(['created', 'modified', 'deleted'])).default(['modified']),
});
