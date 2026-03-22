/**
 * Evaluator Service - Monitor evaluation logic
 * 
 * Valuta i monitor proattivi chiamando Me4BrAIn per dati e decisioni.
 * Pattern SOTA 2026: Parallel execution, timeout handling, structured logging, DI for testability.
 * 
 * NOTE: Refactored in Phase 4.2 with Dependency Injection
 */

import { Monitor, EvaluationResult, Decision } from '@persan/shared';
import { Me4BrAInClient } from '@persan/me4brain-client';
import { ConfigService } from '../../config/config.service.js';
import { monitorManager } from './monitor-manager.service.js';
import { IMe4BrAInClient } from './interfaces/me4brain-client.interface.js';
import { getNotificationService } from './notification-service.instance.js';
import type { MonitorAlert } from './notification.service.js';
import pino from 'pino';

const logger = pino({ name: 'evaluator-service' });

export class EvaluatorService {
    private readonly me4brainClient: IMe4BrAInClient;

    /**
     * Constructor with dependency injection
     * @param me4brainClient - Optional Me4BrAIn client (for testing). Defaults to production client.
     */
    constructor(me4brainClient?: IMe4BrAInClient) {
        // Use injected client or create default production client
        if (me4brainClient) {
            this.me4brainClient = me4brainClient;
        } else {
            const me4brainUrl = ConfigService.getInstance().get('ME4BRAIN_URL') as string;
            this.me4brainClient = new Me4BrAInClient({ baseUrl: me4brainUrl });
        }
    }
    /**
     * Evaluate a monitor by ID
     */
    async evaluate(monitorId: string): Promise<EvaluationResult> {
        const monitor = await monitorManager.getMonitor(monitorId);
        if (!monitor) {
            throw new Error(`Monitor ${monitorId} not found`);
        }

        logger.info({ monitorId, type: monitor.type }, 'Evaluating monitor');

        try {
            // Dispatch to type-specific evaluator
            let result: EvaluationResult;

            switch (monitor.type) {
                case 'PRICE_WATCH':
                    result = await this.evaluatePriceWatch(monitor);
                    break;
                case 'SIGNAL_WATCH':
                    result = await this.evaluateSignalWatch(monitor);
                    break;
                case 'AUTONOMOUS':
                    result = await this.evaluateAutonomous(monitor);
                    break;
                case 'HEARTBEAT':
                    result = await this.evaluateHeartbeat(monitor);
                    break;
                case 'TASK_REMINDER':
                    result = await this.evaluateTaskReminder(monitor);
                    break;
                case 'INBOX_WATCH':
                    result = await this.evaluateInboxWatch(monitor);
                    break;
                case 'CALENDAR_WATCH':
                    result = await this.evaluateCalendarWatch(monitor);
                    break;
                case 'SCHEDULED':
                    result = await this.evaluateScheduled(monitor);
                    break;
                case 'EVENT_DRIVEN':
                    result = await this.evaluateEventDriven(monitor);
                    break;
                case 'FILE_WATCH':
                    result = await this.evaluateFileWatch(monitor);
                    break;
                default:
                    throw new Error(`Unknown monitor type: ${monitor.type}`);
            }

            // Store result in monitor history
            await monitorManager.addEvaluationResult(monitorId, result);

            // Send notification if triggered
            if (result.trigger) {
                await this.sendNotification(monitor, result);
            }

            return result;
        } catch (error) {
            logger.error({ monitorId, error }, 'Evaluation failed');

            const errorResult: EvaluationResult = {
                timestamp: new Date().toISOString(),
                trigger: false,
                error: error instanceof Error ? error.message : 'Unknown error',
            };

            await monitorManager.addEvaluationResult(monitorId, errorResult);

            return errorResult;
        }
    }

    // =========================================================================
    // Me4BrAIn Integration Helpers
    // =========================================================================

    private async fetchStockData(ticker: string): Promise<{ price: number; change: number; volume: number }> {
        try {
            const prompt = `Get current stock price for ${ticker}. Return JSON with: price (number), change (number), volume (number).`;
            const response = await this.me4brainClient.engine.query(prompt, {
                timeoutSeconds: 10,
            });

            // Parse response
            const data = typeof response.answer === 'string' ? JSON.parse(response.answer) : response.answer;
            return {
                price: parseFloat(data.price || '0'),
                change: parseFloat(data.change || '0'),
                volume: parseInt(data.volume || '0', 10),
            };
        } catch (error) {
            logger.error({ ticker, error: error instanceof Error ? error.message : 'Unknown' }, 'fetch_stock_data_error');
            throw new Error(`Failed to fetch stock data for ${ticker}`);
        }
    }

    private async fetchTechnicalIndicator(ticker: string, indicator: string): Promise<{ value: number }> {
        try {
            const prompt = `Get ${indicator.toUpperCase()} technical indicator for ${ticker}. Return JSON with: value (number).`;
            const response = await this.me4brainClient.engine.query(prompt, {
                timeoutSeconds: 10,
            });

            const data = typeof response.answer === 'string' ? JSON.parse(response.answer) : response.answer;
            return {
                value: parseFloat(data.value || '50'),
            };
        } catch (error) {
            logger.error({ ticker, indicator, error: error instanceof Error ? error.message : 'Unknown' }, 'fetch_technical_indicator_error');
            throw new Error(`Failed to fetch ${indicator} for ${ticker}`);
        }
    }

    private async fetchNewsData(ticker: string): Promise<{ headlines: string[] }> {
        try {
            const prompt = `Get latest news headlines for ${ticker}. Return JSON with: headlines (array of strings, max 5).`;
            const response = await this.me4brainClient.engine.query(prompt, {
                timeoutSeconds: 10,
            });

            const data = typeof response.answer === 'string' ? JSON.parse(response.answer) : response.answer;
            return {
                headlines: Array.isArray(data.headlines) ? data.headlines : [],
            };
        } catch (error) {
            logger.error({ ticker, error: error instanceof Error ? error.message : 'Unknown' }, 'fetch_news_data_error');
            // Non-critical, return empty array
            return { headlines: [] };
        }
    }

    private async llmEvaluate(context: any, goal: string): Promise<Decision> {
        try {
            const prompt = `
You are a financial analyst AI. Analyze the following market data and provide a trading recommendation.

Goal: ${goal}

Market Data:
- Ticker: ${context.ticker}
- Current Price: $${context.price}
- Price Change: ${context.change}%
- Volume: ${context.volume}
- RSI: ${context.rsi}
- Recent News: ${context.news.join(', ') || 'None'}

Provide your analysis in JSON format with:
- recommendation: "BUY" | "SELL" | "HOLD" | "WAIT"
- confidence: number (0-100)
- reasoning: string (brief explanation)
- key_factors: array of strings (3-5 key factors)
- suggested_action: string (optional specific action)
`;

            const response = await this.me4brainClient.engine.query(prompt, {
                timeoutSeconds: 20,
            });

            const data = typeof response.answer === 'string' ? JSON.parse(response.answer) : response.answer;

            return {
                recommendation: data.recommendation || 'WAIT',
                confidence: parseInt(data.confidence || '50', 10),
                reasoning: data.reasoning || 'No reasoning provided',
                key_factors: Array.isArray(data.key_factors) ? data.key_factors : [],
                suggested_action: data.suggested_action,
            };
        } catch (error) {
            logger.error({ context, error: error instanceof Error ? error.message : 'Unknown' }, 'llm_evaluate_error');
            // Return safe default
            return {
                recommendation: 'WAIT',
                confidence: 0,
                reasoning: 'LLM evaluation failed',
                key_factors: ['Error during evaluation'],
            };
        }
    }

    // =========================================================================
    // Type-Specific Evaluators (Implementation)
    // =========================================================================

    private async evaluatePriceWatch(monitor: Monitor): Promise<EvaluationResult> {
        const config = monitor.config as any;
        const ticker = config.ticker || '';
        const condition = config.condition || 'below';
        const threshold = parseFloat(config.threshold || '0');

        try {
            // Fetch current price from Me4BrAIn
            const data = await this.fetchStockData(ticker);
            const currentPrice = data.price || 0;

            // Check condition
            let trigger = false;
            if (condition === 'below' && currentPrice < threshold) {
                trigger = true;
            } else if (condition === 'above' && currentPrice > threshold) {
                trigger = true;
            }

            return {
                timestamp: new Date().toISOString(),
                trigger,
                decision: {
                    recommendation: trigger ? 'WAIT' : 'HOLD',
                    confidence: trigger ? 100 : 50,
                    reasoning: `Price ${ticker}: $${currentPrice.toFixed(2)} vs threshold $${threshold.toFixed(2)}`,
                    key_factors: [
                        `Condition: ${condition}`,
                        `Current: $${currentPrice.toFixed(2)}`,
                        `Threshold: $${threshold.toFixed(2)}`,
                    ],
                },
                data: { price: currentPrice, threshold, ticker },
            };
        } catch (error) {
            throw new Error(`Failed to evaluate PRICE_WATCH: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

    private async evaluateSignalWatch(monitor: Monitor): Promise<EvaluationResult> {
        const config = monitor.config as any;
        const ticker = config.ticker || '';
        const indicator = config.indicator || 'rsi';
        const condition = config.condition || 'below';
        const threshold = parseFloat(config.threshold || '30');

        try {
            // Fetch technical indicator from Me4BrAIn
            const data = await this.fetchTechnicalIndicator(ticker, indicator);
            const currentValue = data.value || 50;

            // Check condition
            let trigger = false;
            if (condition === 'below' && currentValue < threshold) {
                trigger = true;
            } else if (condition === 'above' && currentValue > threshold) {
                trigger = true;
            }

            return {
                timestamp: new Date().toISOString(),
                trigger,
                decision: {
                    recommendation: trigger ? 'WAIT' : 'HOLD',
                    confidence: trigger ? 100 : 50,
                    reasoning: `${indicator.toUpperCase()} ${ticker}: ${currentValue.toFixed(2)} vs threshold ${threshold.toFixed(2)}`,
                    key_factors: [
                        `Indicator: ${indicator}`,
                        `Value: ${currentValue.toFixed(2)}`,
                        `Threshold: ${threshold.toFixed(2)}`,
                    ],
                },
                data: { indicator, value: currentValue, threshold, ticker },
            };
        } catch (error) {
            throw new Error(`Failed to evaluate SIGNAL_WATCH: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

    private async evaluateAutonomous(monitor: Monitor): Promise<EvaluationResult> {
        const config = monitor.config as any;
        const ticker = config.ticker || '';
        const goal = config.goal || monitor.description || 'Analyze market conditions';
        const minConfidence = parseFloat(config.min_confidence || '70');

        try {
            // Parallel data collection using Promise.allSettled (SOTA 2026 pattern)
            const [priceResult, newsResult, technicalResult] = await Promise.allSettled([
                this.fetchStockData(ticker),
                this.fetchNewsData(ticker),
                this.fetchTechnicalIndicator(ticker, 'rsi'),
            ]);

            // Extract data from settled promises
            const priceData = priceResult.status === 'fulfilled' ? priceResult.value : null;
            const newsData = newsResult.status === 'fulfilled' ? newsResult.value : null;
            const technicalData = technicalResult.status === 'fulfilled' ? technicalResult.value : null;

            // Build context for LLM evaluation
            const context = {
                ticker,
                price: priceData?.price || 0,
                change: priceData?.change || 0,
                volume: priceData?.volume || 0,
                rsi: technicalData?.value || 50,
                news: newsData?.headlines || [],
                goal,
            };

            // LLM evaluation via Me4BrAIn
            const decision = await this.llmEvaluate(context, goal);

            // Trigger if confidence meets threshold and recommendation is actionable
            const trigger =
                decision.confidence >= minConfidence &&
                (decision.recommendation === 'BUY' || decision.recommendation === 'SELL');

            return {
                timestamp: new Date().toISOString(),
                trigger,
                decision,
                data: context,
            };
        } catch (error) {
            throw new Error(`Failed to evaluate AUTONOMOUS: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

    private async evaluateHeartbeat(monitor: Monitor): Promise<EvaluationResult> {
        const config = monitor.config as any;
        const goal = config.goal || monitor.description || 'Periodic reasoning check';

        try {
            // Fetch context from calendar and memory
            const [calendarResult, memoryResult] = await Promise.allSettled([
                this.fetchCalendarContext(),
                this.fetchMemoryContext(),
            ]);

            const calendarData = calendarResult.status === 'fulfilled' ? calendarResult.value : null;
            const memoryData = memoryResult.status === 'fulfilled' ? memoryResult.value : null;

            // Build context for LLM
            const context = {
                goal,
                calendar: calendarData?.events || [],
                memory: memoryData?.recent_items || [],
                timestamp: new Date().toISOString(),
            };

            // LLM reasoning
            const prompt = `
You are a proactive AI assistant performing a periodic check-in.

Goal: ${goal}

Context:
- Upcoming Calendar Events: ${JSON.stringify(context.calendar)}
- Recent Memory Items: ${JSON.stringify(context.memory)}
- Current Time: ${context.timestamp}

Analyze the context and determine if any proactive action is needed. Return JSON with:
- recommendation: "WAIT" | "HOLD"
- confidence: number (0-100)
- reasoning: string
- key_factors: array of strings
- suggested_action: string (optional)
`;

            const response = await this.me4brainClient.engine.query(prompt, { timeoutSeconds: 15 });
            const data = typeof response.answer === 'string' ? JSON.parse(response.answer) : response.answer;

            const decision: Decision = {
                recommendation: data.recommendation || 'WAIT',
                confidence: parseInt(data.confidence || '50', 10),
                reasoning: data.reasoning || 'Periodic check completed',
                key_factors: Array.isArray(data.key_factors) ? data.key_factors : [],
                suggested_action: data.suggested_action,
            };

            // Trigger if confidence is high and action suggested
            const trigger = decision.confidence >= 70 && !!decision.suggested_action;

            return {
                timestamp: new Date().toISOString(),
                trigger,
                decision,
                data: context,
            };
        } catch (error) {
            throw new Error(`Failed to evaluate HEARTBEAT: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

    private async evaluateTaskReminder(monitor: Monitor): Promise<EvaluationResult> {
        const config = monitor.config as any;
        const taskName = config.task_name || monitor.name;
        const dueDate = config.due_date ? new Date(config.due_date) : null;
        const reminderMinutes = parseInt(config.reminder_minutes || '60', 10);

        try {
            const now = new Date();
            let trigger = false;
            let reasoning = '';

            if (dueDate) {
                const minutesUntilDue = (dueDate.getTime() - now.getTime()) / (1000 * 60);

                if (minutesUntilDue <= reminderMinutes && minutesUntilDue > 0) {
                    trigger = true;
                    reasoning = `Task "${taskName}" is due in ${Math.round(minutesUntilDue)} minutes`;
                } else if (minutesUntilDue <= 0) {
                    trigger = true;
                    reasoning = `Task "${taskName}" is overdue by ${Math.abs(Math.round(minutesUntilDue))} minutes`;
                } else {
                    reasoning = `Task "${taskName}" is due in ${Math.round(minutesUntilDue)} minutes (reminder threshold: ${reminderMinutes} min)`;
                }
            } else {
                reasoning = `No due date set for task "${taskName}"`;
            }

            return {
                timestamp: new Date().toISOString(),
                trigger,
                decision: {
                    recommendation: trigger ? 'WAIT' : 'HOLD',
                    confidence: trigger ? 100 : 50,
                    reasoning,
                    key_factors: [
                        `Task: ${taskName}`,
                        `Due: ${dueDate?.toISOString() || 'Not set'}`,
                        `Reminder threshold: ${reminderMinutes} min`,
                    ],
                },
                data: { task_name: taskName, due_date: dueDate?.toISOString(), reminder_minutes: reminderMinutes },
            };
        } catch (error) {
            throw new Error(`Failed to evaluate TASK_REMINDER: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

    private async evaluateInboxWatch(monitor: Monitor): Promise<EvaluationResult> {
        const config = monitor.config as any;
        const keywords = config.keywords || [];
        const sender = config.sender || null;

        try {
            // Fetch inbox context from Me4BrAIn
            const inboxData = await this.fetchInboxContext(keywords, sender);
            const newEmails = inboxData.emails || [];

            const trigger = newEmails.length > 0;

            return {
                timestamp: new Date().toISOString(),
                trigger,
                decision: {
                    recommendation: trigger ? 'WAIT' : 'HOLD',
                    confidence: trigger ? 100 : 50,
                    reasoning: trigger
                        ? `Found ${newEmails.length} new email(s) matching criteria`
                        : 'No new emails matching criteria',
                    key_factors: [
                        `Keywords: ${keywords.join(', ') || 'None'}`,
                        `Sender filter: ${sender || 'None'}`,
                        `New emails: ${newEmails.length}`,
                    ],
                },
                data: { emails: newEmails, keywords, sender },
            };
        } catch (error) {
            throw new Error(`Failed to evaluate INBOX_WATCH: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

    private async evaluateCalendarWatch(monitor: Monitor): Promise<EvaluationResult> {
        const config = monitor.config as any;
        const lookAheadMinutes = parseInt(config.look_ahead_minutes || '30', 10);

        try {
            // Fetch calendar context
            const calendarData = await this.fetchCalendarContext();
            const events = calendarData.events || [];

            // Filter events within look-ahead window
            const now = new Date();
            const lookAheadTime = new Date(now.getTime() + lookAheadMinutes * 60 * 1000);

            const upcomingEvents = events.filter((event: any) => {
                const eventStart = new Date(event.start);
                return eventStart >= now && eventStart <= lookAheadTime;
            });

            const trigger = upcomingEvents.length > 0;

            return {
                timestamp: new Date().toISOString(),
                trigger,
                decision: {
                    recommendation: trigger ? 'WAIT' : 'HOLD',
                    confidence: trigger ? 100 : 50,
                    reasoning: trigger
                        ? `Found ${upcomingEvents.length} event(s) starting in the next ${lookAheadMinutes} minutes`
                        : `No events in the next ${lookAheadMinutes} minutes`,
                    key_factors: [
                        `Look-ahead window: ${lookAheadMinutes} min`,
                        `Upcoming events: ${upcomingEvents.length}`,
                    ],
                },
                data: { events: upcomingEvents, look_ahead_minutes: lookAheadMinutes },
            };
        } catch (error) {
            throw new Error(`Failed to evaluate CALENDAR_WATCH: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }


    private async evaluateScheduled(monitor: Monitor): Promise<EvaluationResult> {
        const config = monitor.config as any;
        const task = config.task || 'scheduled_task';
        const params = config.params || {};

        // Scheduled tasks always trigger (they are executed on schedule)
        return {
            timestamp: new Date().toISOString(),
            trigger: true,
            decision: {
                recommendation: 'WAIT',
                confidence: 100,
                reasoning: `Scheduled task: ${task}`,
                key_factors: Object.keys(params),
                suggested_action: task,
            },
            data: { task, params },
        };
    }

    private async evaluateEventDriven(_monitor: Monitor): Promise<EvaluationResult> {
        // Event-driven monitors are triggered externally (e.g., webhook)
        // This evaluator just logs and confirms the trigger
        return {
            timestamp: new Date().toISOString(),
            trigger: true,
            decision: {
                recommendation: 'WAIT',
                confidence: 100,
                reasoning: 'Event-driven monitor triggered externally',
                key_factors: ['External event received'],
            },
            data: { event_type: 'external_trigger' },
        };
    }

    private async evaluateFileWatch(monitor: Monitor): Promise<EvaluationResult> {
        const config = monitor.config as any;
        const path = config.path || '';
        const events = config.events || ['modified'];

        // File watch would require filesystem access
        // For now, return a stub that indicates the feature is not fully implemented
        return {
            timestamp: new Date().toISOString(),
            trigger: false,
            decision: {
                recommendation: 'WAIT',
                confidence: 0,
                reasoning: `FILE_WATCH not fully implemented for path: ${path}`,
                key_factors: [`Path: ${path}`, `Events: ${events.join(', ')}`],
            },
            data: { path, events, note: 'Filesystem monitoring requires additional implementation' },
        };
    }

    // =========================================================================
    // Additional Helper Methods
    // =========================================================================

    private async fetchCalendarContext(): Promise<{ events: any[] }> {
        try {
            const prompt = 'Get upcoming calendar events for the next 24 hours. Return JSON with: events (array of objects with start, title, description).';
            const response = await this.me4brainClient.engine.query(prompt, { timeoutSeconds: 10 });
            const data = typeof response.answer === 'string' ? JSON.parse(response.answer) : response.answer;
            return {
                events: Array.isArray(data.events) ? data.events : [],
            };
        } catch (error) {
            logger.error({ error: error instanceof Error ? error.message : 'Unknown' }, 'fetch_calendar_context_error');
            return { events: [] };
        }
    }

    private async fetchMemoryContext(): Promise<{ recent_items: any[] }> {
        try {
            const prompt = 'Get recent memory items from working memory. Return JSON with: recent_items (array of objects with timestamp, content, type).';
            const response = await this.me4brainClient.engine.query(prompt, { timeoutSeconds: 10 });
            const data = typeof response.answer === 'string' ? JSON.parse(response.answer) : response.answer;
            return {
                recent_items: Array.isArray(data.recent_items) ? data.recent_items : [],
            };
        } catch (error) {
            logger.error({ error: error instanceof Error ? error.message : 'Unknown' }, 'fetch_memory_context_error');
            return { recent_items: [] };
        }
    }

    private async fetchInboxContext(keywords: string[], sender: string | null): Promise<{ emails: any[] }> {
        try {
            const keywordFilter = keywords.length > 0 ? `with keywords: ${keywords.join(', ')}` : '';
            const senderFilter = sender ? `from sender: ${sender}` : '';
            const filters = [keywordFilter, senderFilter].filter(Boolean).join(' and ');

            const prompt = `Get new emails ${filters || 'from inbox'}. Return JSON with: emails (array of objects with from, subject, timestamp).`;
            const response = await this.me4brainClient.engine.query(prompt, { timeoutSeconds: 10 });
            const data = typeof response.answer === 'string' ? JSON.parse(response.answer) : response.answer;
            return {
                emails: Array.isArray(data.emails) ? data.emails : [],
            };
        } catch (error) {
            logger.error({ keywords, sender, error: error instanceof Error ? error.message : 'Unknown' }, 'fetch_inbox_context_error');
            return { emails: [] };
        }
    }

    // =========================================================================
    // Helpers
    // =========================================================================

    private async sendNotification(monitor: Monitor, result: EvaluationResult): Promise<void> {
        try {
            const notificationService = getNotificationService();

            // Format alert from evaluation result
            const alert: MonitorAlert = {
                monitorId: monitor.id,
                monitorName: monitor.name,
                monitorType: monitor.type,
                trigger: result.trigger,
                decision: result.decision || {
                    recommendation: 'UNKNOWN',
                    confidence: 0,
                    reasoning: 'No decision available',
                },
                data: result.data || {},
                timestamp: result.timestamp,
            };

            // Send via NotificationService
            await notificationService.sendMonitorAlert(monitor.user_id, alert);

            logger.info(
                { monitorId: monitor.id, userId: monitor.user_id, monitorType: monitor.type },
                'Notification sent successfully'
            );
        } catch (error) {
            logger.error(
                { monitorId: monitor.id, userId: monitor.user_id, error },
                'Failed to send notification'
            );
            // Don't throw - notification failure shouldn't break evaluation
        }
    }

    /**
     * Timeout helper for Promise.race
     */
    protected timeout<T>(ms: number, message: string): Promise<T> {
        return new Promise((_, reject) =>
            setTimeout(() => reject(new Error(message)), ms)
        );
    }
}

// Singleton instance
let evaluatorServiceInstance: EvaluatorService | null = null;

export function getEvaluatorService(): EvaluatorService {
    if (!evaluatorServiceInstance) {
        evaluatorServiceInstance = new EvaluatorService();
    }
    return evaluatorServiceInstance;
}

export const evaluatorService = getEvaluatorService();
