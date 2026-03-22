'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface TextBlockProps {
    data: {
        content: string;
    };
}

const mockText = {
    content: `### Analisi di Mercato: Apple Inc (AAPL)

Sulla base dei dati analizzati oggi, Apple presenta una struttura tecnica rialzista nel breve termine.

**Punti di Forza:**
- Innovazione continua nel settore servizi
- Solidità finanziaria (Cash on hand)
- Buyback aggressivi

**Rischi:**
- Rallentamento vendite in Cina
- Pressioni regolatorie EU

Il target price per il prossimo trimestre è stimato tra **$210** e **$220**.`
};

export function TextBlock({ data }: TextBlockProps) {
    const displayData = data && data.content ? data : mockText;

    return (
        <div className="prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed prose-li:my-0">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {displayData.content}
            </ReactMarkdown>
        </div>
    );
}
