import type { Metadata, Viewport } from 'next';
import Script from 'next/script';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import './globals.css';

export const viewport: Viewport = {
    width: 'device-width',
    initialScale: 1,
    maximumScale: 1,
    userScalable: false,
};

export const metadata: Metadata = {
    title: 'jAI',
    description: 'jAI — AI Assistant universale powered by Me4BrAIn',
};

// Suppress noisy browser extension warnings (MetaMask, etc.)
const SUPPRESS_EXTENSIONS_SCRIPT = `
(function(){
  var p=['MetaMask','inpage.js','nkbihfbeogaeaoehlefnkodbefgpgknn','chrome-extension://'];
  function s(a){return Array.from(a).some(function(x){
    var t=typeof x==='string'?x:x instanceof Error?(x.message||'')+(x.stack||''):'';
    return t&&p.some(function(k){return t.indexOf(k)!==-1});
  })}
  var oe=console.error,ow=console.warn,ol=console.log,oi=console.info;
  console.error=function(){if(!s(arguments))oe.apply(console,arguments)};
  console.warn=function(){if(!s(arguments))ow.apply(console,arguments)};
  console.log=function(){if(!s(arguments))ol.apply(console,arguments)};
  console.info=function(){if(!s(arguments))oi.apply(console,arguments)};
})();
`;

export default function RootLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    return (
        <html lang="it" className="dark">
            <body suppressHydrationWarning>
                <Script
                    id="suppress-extension-warnings"
                    strategy="afterInteractive"
                    dangerouslySetInnerHTML={{ __html: SUPPRESS_EXTENSIONS_SCRIPT }}
                />
                <ErrorBoundary name="Root">
                    {children}
                </ErrorBoundary>
            </body>
        </html>
    );
}
