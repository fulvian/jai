import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { IntelDeck } from '@/components/layout/IntelDeck';
import { Sidebar } from '@/components/layout/Sidebar';
import { ChatErrorBoundary, MonitorsErrorBoundary } from '@/components/ErrorBoundary';

export default function Home() {
    return (
        <DashboardLayout
            sidebar={<Sidebar />}
            intelDeck={
                <MonitorsErrorBoundary>
                    <IntelDeck />
                </MonitorsErrorBoundary>
            }
        >
            <ChatErrorBoundary>
                <ChatPanel />
            </ChatErrorBoundary>
        </DashboardLayout>
    );
}

