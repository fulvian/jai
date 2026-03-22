'use client';

import React from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

// ── Types ─────────────────────────────────────────────────────────────

interface ErrorBoundaryProps {
    children: React.ReactNode;
    fallback?: React.ReactNode;
    /** Custom error handler */
    onError?: (error: Error, errorInfo: React.ErrorInfo) => void;
    /** Custom reset handler */
    onReset?: () => void;
    /** Error boundary name for logging */
    name?: string;
}

interface ErrorBoundaryState {
    hasError: boolean;
    error: Error | null;
    errorInfo: React.ErrorInfo | null;
}

// ── Generic ErrorBoundary ─────────────────────────────────────────────

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ErrorBoundaryProps) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
        this.setState({ errorInfo });
        console.error(`[ErrorBoundary${this.props.name ? `:${this.props.name}` : ''}]`, error, errorInfo);
        this.props.onError?.(error, errorInfo);
    }

    handleRetry = (): void => {
        this.props.onReset?.();
        this.setState({ hasError: false, error: null, errorInfo: null });
    };

    render(): React.ReactNode {
        if (this.state.hasError) {
            if (this.props.fallback) {
                return this.props.fallback;
            }

            return (
                <div className="flex flex-col items-center justify-center min-h-[200px] p-8 rounded-xl bg-red-500/10 border border-red-500/20">
                    <AlertTriangle className="w-12 h-12 text-red-400 mb-4" />
                    <h2 className="text-lg font-semibold text-white mb-2">
                        Qualcosa è andato storto
                    </h2>
                    <p className="text-sm text-white/60 mb-4 text-center max-w-md">
                        {this.state.error?.message || 'Si è verificato un errore imprevisto'}
                    </p>
                    {process.env.NODE_ENV === 'development' && this.state.errorInfo && (
                        <details className="mb-4 text-xs text-white/40 max-w-full overflow-auto">
                            <summary className="cursor-pointer hover:text-white/60">
                                Dettagli errore
                            </summary>
                            <pre className="mt-2 p-2 bg-black/20 rounded text-left whitespace-pre-wrap">
                                {this.state.error?.stack}
                            </pre>
                        </details>
                    )}
                    <button
                        onClick={this.handleRetry}
                        className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-colors"
                    >
                        <RefreshCw className="w-4 h-4" />
                        Riprova
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}

// ── ChatErrorBoundary ─────────────────────────────────────────────────

interface ChatErrorBoundaryProps {
    children: React.ReactNode;
    onReset?: () => void;
}

export class ChatErrorBoundary extends React.Component<ChatErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: ChatErrorBoundaryProps) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
        this.setState({ errorInfo });
        console.error('[ChatErrorBoundary]', error, errorInfo);
    }

    handleRetry = (): void => {
        this.props.onReset?.();
        this.setState({ hasError: false, error: null, errorInfo: null });
    };

    render(): React.ReactNode {
        if (this.state.hasError) {
            return (
                <div className="flex flex-col items-center justify-center h-full p-8">
                    <div className="flex flex-col items-center max-w-md text-center">
                        <div className="w-16 h-16 rounded-full bg-red-500/20 flex items-center justify-center mb-4">
                            <AlertTriangle className="w-8 h-8 text-red-400" />
                        </div>
                        <h2 className="text-xl font-semibold text-white mb-2">
                            Errore nella Chat
                        </h2>
                        <p className="text-sm text-white/60 mb-6">
                            Si è verificato un errore durante il caricamento della chat.
                            {this.state.error?.message && (
                                <span className="block mt-2 text-red-400/80">
                                    {this.state.error.message}
                                </span>
                            )}
                        </p>
                        <div className="flex gap-3">
                            <button
                                onClick={this.handleRetry}
                                className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-colors"
                            >
                                <RefreshCw className="w-4 h-4" />
                                Riprova
                            </button>
                            <button
                                onClick={() => window.location.reload()}
                                className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 rounded-lg text-white/70 hover:text-white transition-colors"
                            >
                                <Home className="w-4 h-4" />
                                Ricarica Pagina
                            </button>
                        </div>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}

// ── MonitorsErrorBoundary ─────────────────────────────────────────────

interface MonitorsErrorBoundaryProps {
    children: React.ReactNode;
}

export class MonitorsErrorBoundary extends React.Component<MonitorsErrorBoundaryProps, ErrorBoundaryState> {
    constructor(props: MonitorsErrorBoundaryProps) {
        super(props);
        this.state = { hasError: false, error: null, errorInfo: null };
    }

    static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
        this.setState({ errorInfo });
        console.error('[MonitorsErrorBoundary]', error, errorInfo);
    }

    handleRetry = (): void => {
        this.setState({ hasError: false, error: null, errorInfo: null });
    };

    render(): React.ReactNode {
        if (this.state.hasError) {
            return (
                <div className="flex flex-col items-center justify-center h-full p-6">
                    <div className="text-center">
                        <AlertTriangle className="w-10 h-10 text-yellow-400 mx-auto mb-3" />
                        <p className="text-sm text-white/60 mb-3">
                            Errore nel pannello monitor
                        </p>
                        <button
                            onClick={this.handleRetry}
                            className="text-xs text-white/40 hover:text-white/60 transition-colors underline"
                        >
                            Riprova
                        </button>
                    </div>
                </div>
            );
        }

        return this.props.children;
    }
}

// ── Hook for functional components ────────────────────────────────────

/**
 * Hook to programmatically trigger an error boundary.
 * Useful for catching async errors in event handlers.
 */
export function useErrorBoundary() {
    const [, setError] = React.useState<Error | null>(null);

    const showBoundary = React.useCallback((error: Error) => {
        setError(() => {
            throw error;
        });
    }, []);

    return { showBoundary };
}

export default ErrorBoundary;
