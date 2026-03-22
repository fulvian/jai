/**
 * Approval Dialog Component
 * 
 * Mostra richieste di approvazione HITL dall'agent.
 * Permette all'utente di approvare o negare azioni critiche.
 */

'use client';

import { useState, useEffect } from 'react';
import styles from './ApprovalDialog.module.css';

interface ApprovalRequest {
    id: string;
    tool: string;
    message: string;
    urgency: 'low' | 'medium' | 'high';
    expiresAt: string;
    args?: Record<string, unknown>;
}

interface ApprovalDialogProps {
    request: ApprovalRequest;
    onApprove: (requestId: string) => void;
    onDeny: (requestId: string) => void;
    onClose: () => void;
}

export function ApprovalDialog({ request, onApprove, onDeny, onClose }: ApprovalDialogProps) {
    const [timeLeft, setTimeLeft] = useState<number>(0);
    const [isLoading, setIsLoading] = useState(false);

    // Countdown timer
    useEffect(() => {
        const expires = new Date(request.expiresAt).getTime();

        const updateTimer = () => {
            const now = Date.now();
            const remaining = Math.max(0, expires - now);
            setTimeLeft(Math.floor(remaining / 1000));

            if (remaining <= 0) {
                onClose();
            }
        };

        updateTimer();
        const interval = setInterval(updateTimer, 1000);
        return () => clearInterval(interval);
    }, [request.expiresAt, onClose]);

    const handleApprove = async () => {
        setIsLoading(true);
        onApprove(request.id);
    };

    const handleDeny = async () => {
        setIsLoading(true);
        onDeny(request.id);
    };

    const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const urgencyIcon = {
        low: '🔵',
        medium: '🟡',
        high: '🔴',
    }[request.urgency];

    return (
        <div className={styles.overlay}>
            <div className={`${styles.dialog} ${styles[request.urgency]}`}>
                <div className={styles.header}>
                    <span className={styles.urgencyBadge}>
                        {urgencyIcon} {request.urgency.toUpperCase()}
                    </span>
                    <span className={styles.timer}>
                        Scade in {formatTime(timeLeft)}
                    </span>
                </div>

                <div className={styles.content}>
                    <h3 className={styles.title}>Conferma Azione</h3>

                    <div className={styles.toolBadge}>
                        🛠️ {request.tool}
                    </div>

                    <p className={styles.message}>{request.message}</p>

                    {request.args && Object.keys(request.args).length > 0 && (
                        <details className={styles.details}>
                            <summary>Dettagli</summary>
                            <pre>{JSON.stringify(request.args, null, 2)}</pre>
                        </details>
                    )}
                </div>

                <div className={styles.actions}>
                    <button
                        className={styles.denyButton}
                        onClick={handleDeny}
                        disabled={isLoading}
                    >
                        ✕ Nega
                    </button>
                    <button
                        className={styles.approveButton}
                        onClick={handleApprove}
                        disabled={isLoading}
                    >
                        ✓ Approva
                    </button>
                </div>
            </div>
        </div>
    );
}

export default ApprovalDialog;
