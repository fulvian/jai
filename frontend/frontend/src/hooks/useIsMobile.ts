'use client';

import { useState, useEffect } from 'react';

/**
 * Robust hook to detect mobile viewports via matchMedia.
 * Returns null until determined on client to prevent hydration mismatches.
 * @param breakpoint Breakpoint in pixels (default: 768)
 */
export function useIsMobile(breakpoint = 768): boolean | null {
    const [isMobile, setIsMobile] = useState<boolean | null>(null);

    useEffect(() => {
        const mq = window.matchMedia(`(max-width: ${breakpoint - 1}px)`);

        // Initial check
        setIsMobile(mq.matches);

        const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);

        // Modern browsers
        if (mq.addEventListener) {
            mq.addEventListener('change', handler);
        } else {
            // Old browsers fallback
            // @ts-ignore
            mq.addListener(handler);
        }

        return () => {
            if (mq.removeEventListener) {
                mq.removeEventListener('change', handler);
            } else {
                // @ts-ignore
                mq.removeListener(handler);
            }
        };
    }, [breakpoint]);

    return isMobile;
}
