'use client';

import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts';

/**
 * Data point for sparkline chart
 */
export interface SparklineDataPoint {
  value: number;
  index?: number;
}

/**
 * SparklineChart Component
 * 
 * Minimal line chart for displaying trends in stock tiles.
 * Green line for positive trend, smooth curve styling.
 */
interface SparklineChartProps {
  data: SparklineDataPoint[];
  color?: string;
  width?: number;
  height?: number;
  showTooltip?: boolean;
}

export function SparklineChart({
  data,
  color = '#10B981',
  width = 100,
  height = 40,
  showTooltip = false,
}: SparklineChartProps) {
  // Format data for Recharts
  const chartData = data.map((point, index) => ({
    value: point.value,
    index: point.index ?? index,
  }));

  return (
    <ResponsiveContainer width={width} height={height}>
      <LineChart data={chartData}>
        {showTooltip && (
          <Tooltip
            contentStyle={{
              backgroundColor: '#1E293B',
              border: 'none',
              borderRadius: '8px',
              padding: '8px',
              color: '#F8FAFC',
            }}
            formatter={(value: number) => value.toFixed(2)}
          />
        )}
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          dot={false}
          activeDot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
