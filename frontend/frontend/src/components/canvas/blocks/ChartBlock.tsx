'use client';

import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';

interface ChartBlockProps {
    data: any;
    type?: 'line' | 'bar';
}

const mockData = [
    { name: 'Lun', val: 400 },
    { name: 'Mar', val: 300 },
    { name: 'Mer', val: 200 },
    { name: 'Gio', val: 278 },
    { name: 'Ven', val: 189 },
    { name: 'Sab', val: 239 },
    { name: 'Dom', val: 349 },
];

export function ChartBlock({ data, type = 'line' }: ChartBlockProps) {
    // Fallback to mock data if empty
    const displayData = data && Object.keys(data).length > 0 ? data : mockData;

    return (
        <div className="w-full h-48 lg:h-64 pt-2">
            <ResponsiveContainer width="100%" height="100%">
                {type === 'line' ? (
                    <LineChart data={displayData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                        <XAxis
                            dataKey="name"
                            stroke="rgba(255,255,255,0.3)"
                            fontSize={10}
                            tickLine={false}
                            axisLine={false}
                        />
                        <YAxis
                            stroke="rgba(255,255,255,0.3)"
                            fontSize={10}
                            tickLine={false}
                            axisLine={false}
                            tickFormatter={(v) => `$${v}`}
                        />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: 'var(--bg-secondary)',
                                border: '1px solid var(--glass-border)',
                                borderRadius: '8px',
                                fontSize: '12px'
                            }}
                        />
                        <Line
                            type="monotone"
                            dataKey="val"
                            stroke="var(--accent-primary)"
                            strokeWidth={2}
                            dot={{ fill: 'var(--accent-primary)', strokeWidth: 2, r: 4 }}
                            activeDot={{ r: 6, strokeWidth: 0 }}
                        />
                    </LineChart>
                ) : (
                    <BarChart data={displayData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                        <XAxis dataKey="name" stroke="rgba(255,255,255,0.3)" fontSize={10} />
                        <YAxis stroke="rgba(255,255,255,0.3)" fontSize={10} />
                        <Tooltip />
                        <Bar dataKey="val" fill="var(--accent-primary)" radius={[4, 4, 0, 0]} />
                    </BarChart>
                )}
            </ResponsiveContainer>
        </div>
    );
}
