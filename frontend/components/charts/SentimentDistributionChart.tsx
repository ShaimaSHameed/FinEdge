'use client';

import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, Cell } from 'recharts';

/**
 * Sentiment distribution data
 */
export interface SentimentDistributionData {
  name: string;
  value: number;
  color: string;
}

/**
 * SentimentDistributionChart Component
 * 
 * Bar chart displaying sentiment breakdown (Positive, Negative, Neutral).
 */
interface SentimentDistributionChartProps {
  data: SentimentDistributionData[];
  width?: number;
  height?: number;
}

export function SentimentDistributionChart({
  data,
  width = 400,
  height = 300,
}: SentimentDistributionChartProps) {
  return (
    <ResponsiveContainer width={width} height={height}>
      <BarChart data={data} layout="vertical">
        <XAxis type="number" hide />
        <YAxis 
          type="category" 
          dataKey="name" 
          tick={{ fill: '#64748B', fontSize: 12 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1E293B',
            border: 'none',
            borderRadius: '8px',
            padding: '12px',
            color: '#F8FAFC',
          }}
          formatter={(value: number) => `${value} articles`}
        />
        <Bar dataKey="value" radius={[0, 8, 8, 0]}>
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
