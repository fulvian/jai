'use client';

interface TableBlockProps {
    data: any;
}

const mockTable = {
    headers: ['Asset', 'Price', 'Change 24h', 'Volume'],
    rows: [
        ['Bitcoin (BTC)', '$65,432', '+2.4%', '$32B'],
        ['Ethereum (ETH)', '$3,456', '-1.2%', '$18B'],
        ['Solana (SOL)', '$145', '+5.1%', '$4B'],
        ['Apple (AAPL)', '$189.45', '+0.8%', '56M'],
        ['Tesla (TSLA)', '$176.20', '-2.3%', '94M'],
    ]
};

export function TableBlock({ data }: TableBlockProps) {
    const displayData = data && data.headers ? data : mockTable;

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
                <thead>
                    <tr className="border-b border-[var(--glass-border)]">
                        {displayData.headers.map((header: string, i: number) => (
                            <th key={i} className="py-2 px-3 font-semibold text-[var(--text-tertiary)] uppercase tracking-wider">
                                {header}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody className="divide-y divide-[var(--glass-border)]">
                    {displayData.rows.map((row: any[], i: number) => (
                        <tr key={i} className="hover:bg-white/[0.02] transition-colors">
                            {row.map((cell: any, j: number) => (
                                <td key={j} className="py-3 px-3 text-[var(--text-secondary)] whitespace-nowrap">
                                    {cell}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
