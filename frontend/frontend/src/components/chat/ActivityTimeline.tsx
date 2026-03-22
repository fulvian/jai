/**
 * ActivityTimeline - Real-time progress display during streaming.
 *
 * Shows a vertical timeline of activity steps while the system is working:
 * thinking → plan → step_start/complete → synthesizing → content
 *
 * Inspired by Perplexity's search progress + ChatGPT's tool indicators.
 */

'use client';

import { useChatStore, type ActivityStep } from '@/stores/useChatStore';
import { cn } from '@/lib/utils';

function StepCard({ step }: { step: ActivityStep }) {
    const isActive = step.status === 'active';
    const isDone = step.status === 'done';
    const isError = step.status === 'error';

    return (
        <div
            className={cn(
                'flex items-start gap-3 px-4 py-3 rounded-xl transition-all duration-300',
                'backdrop-blur-sm border',
                isActive && 'bg-[var(--tahoe-blue)]/5 border-[var(--tahoe-blue)]/20 animate-ai-pulse',
                isDone && 'bg-[var(--tahoe-green)]/5 border-[var(--tahoe-green)]/15',
                isError && 'bg-[var(--tahoe-red)]/5 border-[var(--tahoe-red)]/20',
            )}
        >
            {/* Status indicator */}
            <div className="flex-shrink-0 mt-0.5">
                {isActive ? (
                    <div className="w-5 h-5 rounded-full border-2 border-[var(--tahoe-blue)] border-t-transparent animate-spin" />
                ) : (
                    <span className="text-base leading-5">{step.icon}</span>
                )}
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
                <p className={cn(
                    'text-sm font-medium',
                    isActive && 'text-[var(--tahoe-blue)]',
                    isDone && 'text-[var(--text-secondary)]',
                    isError && 'text-[var(--tahoe-red)]',
                )}>
                    {step.message}
                </p>

                {/* Plan areas */}
                {step.type === 'plan' && step.areas && step.areas.length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {step.areas.map((area) => (
                            <span
                                key={area}
                                className="px-2 py-0.5 text-xs rounded-full
                                    bg-[var(--glass-surface)] border border-[var(--glass-border-subtle)]
                                    text-[var(--text-tertiary)]"
                            >
                                {area}
                            </span>
                        ))}
                    </div>
                )}

                {/* 🎯 NEW: Tools being used */}
                {step.tools && step.tools.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                        {step.tools.map((tool) => (
                            <span
                                key={tool}
                                className="px-2 py-0.5 text-xs rounded-full bg-[var(--tahoe-blue)]/10 text-[var(--tahoe-blue)]"
                            >
                                🔧 {tool}
                            </span>
                        ))}
                    </div>
                )}

                {/* 🎯 NEW: Details section */}
                {step.details && (
                    <p className="text-xs text-[var(--text-tertiary)] mt-1">
                        {step.details}
                    </p>
                )}

                {/* 🎯 NEW: Progress bar */}
                {step.total && step.total > 1 && step.step && (
                    <div className="flex items-center gap-2 mt-1.5">
                        <div className="flex-1 h-1 bg-gray-200 rounded-full">
                            <div
                                className="h-1 bg-blue-500 rounded-full transition-all"
                                style={{ width: `${(step.step / step.total) * 100}%` }}
                            />
                        </div>
                        <span className="text-xs text-gray-500">
                            {step.step}/{step.total}
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
}

export function ActivityTimeline() {
    const currentSession = useChatStore((s) => s.getCurrentSession());
    const { activitySteps = [], isStreaming, pendingMessage = '', isThinking, pendingThinking } = currentSession;

    // Show timeline only during streaming and when we have activity steps
    // Keep timeline visible during entire streaming, not just before content
    if (activitySteps.length === 0 && !isThinking) return null;

    // Only hide timeline when streaming is COMPLETE (not just when content arrives)
    // This ensures thinking and activity steps remain visible during the entire response
    const shouldHide = !isStreaming && !isThinking && activitySteps.length === 0;

    if (shouldHide) return null;

    // Collapse regular activity steps when content arrives, but KEEP thinking visible
    const shouldCollapseActivity = !isThinking && pendingMessage.length > 0;

    return (
        <div className="flex flex-col gap-2 py-2 px-1">
            {/* Activity steps - can collapse when content arrives */}
            <div className={cn(
                'flex flex-col gap-2 transition-all duration-500',
                shouldCollapseActivity && 'max-h-0 overflow-hidden opacity-0',
                !shouldCollapseActivity && 'max-h-[2000px] opacity-100',
            )}>
                {activitySteps.map((step, i) => (
                    <StepCard key={`${step.type}-${i}`} step={step} />
                ))}
            </div>

            {/* 🎯 Real-time Thinking Process - ALWAYS VISIBLE during thinking */}
            {/* This remains visible even when content starts arriving */}
            {isThinking && pendingThinking && (
                <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-[var(--glass-surface)] border border-[var(--tahoe-blue)]/20 animate-ai-pulse">
                    <div className="flex-shrink-0 mt-0.5">
                        <div className="w-5 h-5 rounded-full border-2 border-[var(--tahoe-blue)] border-t-transparent animate-spin" />
                    </div>
                    <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-[var(--tahoe-blue)] italic whitespace-pre-wrap break-words leading-relaxed">
                            {pendingThinking}
                            <span className="inline-block w-1.5 h-4 ml-1 bg-[var(--tahoe-blue)] animate-blink" />
                        </p>
                    </div>
                </div>
            )}
        </div>
    );
}
