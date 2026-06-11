'use client';

import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from 'recharts';
import { format } from 'date-fns';

/**
 * Trend data point
 */
export interface TrendDataPoint {
  date: string;
  score: number;
  article_count?: number;
}

/**
 * TrendLineChart Component
 * 
 * Line chart showing sentiment over time (last 7 days).
 * Color-coded trend line (green for positive, red for negative).
 */
interface TrendLineChartProps {
  data: TrendDataPoint[];
  width?: number;
  height?: number;
  color?: string;
}

export function TrendLineChart({
  data,
  width = 600,
  height = 300,
  color,
}: TrendLineChartProps) {
  // Determine if overall trend is positive or negative
  const lastScore = data[data.length - 1]?.score || 0;
  const lineColor = color ?? (lastScore >= 0 ? '#10B981' : '#EF4444');

  return (
    <ResponsiveContainer width={width} height={height}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
        <XAxis
          dataKey="date"
          tickFormatter={(value: string) => format(new Date(value), 'MMM dd')}
          tick={{ fill: '#64748B', fontSize: 12 }}
          axisLine={{ stroke: '#E2E8F0' }}
          tickLine={{ stroke: '#E2E8F0' }}
        />
        <YAxis
          domain={[-1, 1]}
          tickFormatter={(value: number) => value.toFixed(2)}
          tick={{ fill: '#64748B', fontSize: 12 }}
          axisLine={{ stroke: '#E2E8F0' }}
          tickLine={{ stroke: '#E2E8F0' }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: '#1E293B',
            border: 'none',
            borderRadius: '8px',
            padding: '12px',
            color: '#F8FAFC',
          }}
          labelFormatter={(value: string) => format(new Date(value), 'MMM dd, yyyy')}
          formatter={(value: unknown, _name: string, props: { payload?: TrendDataPoint }) => {
            const numericValue = typeof value === 'number' ? value : Number(value);
            const articleCount = props.payload?.article_count;
            return [
              <div key="score">
                <div className="font-semibold">Score: {numericValue.toFixed(3)}</div>
                {articleCount && <div className="text-sm text-gray-400">Articles: {articleCount}</div>}
              </div>
            ];
          }}
        />
        <Line
          type="monotone"
          dataKey="score"
          stroke={lineColor}
          strokeWidth={2}
          dot={{ fill: lineColor, strokeWidth: 2, r: 4 }}
          activeDot={{ r: 6 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
