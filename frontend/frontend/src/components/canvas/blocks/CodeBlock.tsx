'use client';

import { Highlight, themes } from 'prism-react-renderer';
import { Copy, Check } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';

interface CodeBlockProps {
    data: {
        code: string;
        language: string;
    };
}

const mockCode = {
    code: `async function analyzeMarket(ticker) {
  const data = await me4brain.finance.getQuotes(ticker);
  const signal = data.change > 0 ? "BUY" : "SELL";
  
  return {
    ticker,
    signal,
    timestamp: new Date()
  };
}`,
    language: 'javascript'
};

export function CodeBlock({ data }: CodeBlockProps) {
    const [copied, setCopied] = useState(false);
    const copyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const displayData = data && data.code ? data : mockCode;

    // Cleanup timer on unmount
    useEffect(() => {
        return () => {
            if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
        };
    }, []);

    const copyToClipboard = () => {
        navigator.clipboard.writeText(displayData.code);
        setCopied(true);
        if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
        copyTimerRef.current = setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="relative group">
            <button
                onClick={copyToClipboard}
                className="absolute top-2 right-2 p-1.5 rounded-lg bg-white/5 border border-white/10 text-white/50 opacity-0 group-hover:opacity-100 transition-all hover:bg-white/10 hover:text-white"
                title="Copia codice"
            >
                {copied ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
            </button>
            <Highlight
                theme={themes.vsDark}
                code={displayData.code.trim()}
                language={displayData.language}
            >
                {({ className, style, tokens, getLineProps, getTokenProps }) => (
                    <pre className="text-xs font-mono p-2 overflow-x-auto custom-scrollbar" style={{ background: 'transparent' }}>
                        {tokens.map((line, i) => (
                            <div key={i} {...getLineProps({ line, key: i })}>
                                <span className="inline-block w-4 text-white/20 select-none mr-2">{i + 1}</span>
                                {line.map((token, key) => (
                                    <span key={key} {...getTokenProps({ token, key })} />
                                ))}
                            </div>
                        ))}
                    </pre>
                )}
            </Highlight>
        </div>
    );
}
