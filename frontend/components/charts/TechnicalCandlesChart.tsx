'use client';

import { format } from 'date-fns';
import type { TechnicalCandle } from '@/types';

interface TechnicalCandlesChartProps {
  ticker: string;
  modelVersion: 'final_1d' | 'final_1min' | 'v1.1' | 'v1.2';
  history: TechnicalCandle[];
  forecast: TechnicalCandle[];
  dataSource: string;
  timeframe: '1Min' | '1D';
}

const VIEWBOX_WIDTH = 1100;
const VIEWBOX_HEIGHT = 460;
const MARGIN = { top: 22, right: 20, bottom: 42, left: 64 };

export function TechnicalCandlesChart({
  ticker,
  modelVersion,
  history,
  forecast,
  dataSource,
  timeframe,
}: TechnicalCandlesChartProps) {
  const candles = [...history, ...forecast];
  const forecastStartIndex = history.length;
  const plotWidth = VIEWBOX_WIDTH - MARGIN.left - MARGIN.right;
  const plotHeight = VIEWBOX_HEIGHT - MARGIN.top - MARGIN.bottom;
  const candleStep = candles.length > 1 ? plotWidth / candles.length : plotWidth;
  const bodyWidth = Math.max(4, Math.min(9, candleStep * 0.58));

  const highs = candles.map((candle) => candle.high);
  const lows = candles.map((candle) => candle.low);
  const maxPrice = Math.max(...highs);
  const minPrice = Math.min(...lows);
  const padding = (maxPrice - minPrice || 1) * 0.12;
  const domainMax = maxPrice + padding;
  const domainMin = minPrice - padding;
  const priceRange = domainMax - domainMin || 1;

  const priceToY = (price: number) =>
    MARGIN.top + ((domainMax - price) / priceRange) * plotHeight;

  const xForIndex = (index: number) => MARGIN.left + candleStep * index + candleStep / 2;
  const forecastStartX = xForIndex(Math.max(forecastStartIndex, 0)) - candleStep / 2;
  const gridTicks = Array.from({ length: 5 }, (_, index) => domainMin + (priceRange / 4) * index).reverse();
  const labelEvery = timeframe === '1Min' ? 12 : candles.length > 90 ? 10 : 8;
  const labelFormat = timeframe === '1Min' ? 'HH:mm' : 'MMM d';

  return (
    <div className="rounded-2xl border border-slate-800 bg-[#05070c] p-4 shadow-2xl">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="text-xl font-semibold text-white">{ticker} {timeframe} Technical Analysis</h3>
          <p className="text-sm text-slate-400">
            Model {modelVersion} / {history.length} real bars + {forecast.length} forecast bars / Source: {dataSource}
          </p>
        </div>

        <div className="flex flex-wrap gap-3 text-xs text-slate-300">
          <LegendSwatch color="#22c55e" label="History (bull)" />
          <LegendSwatch color="#ef4444" label="History (bear)" />
          <LegendSwatch color="rgba(34,197,94,0.5)" label="Forecast (bull)" />
          <LegendSwatch color="rgba(239,68,68,0.45)" label="Forecast (bear)" />
        </div>
      </div>

      <div className="mt-4 h-[440px] w-full">
        <svg viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`} className="h-full w-full">
          <rect x="0" y="0" width={VIEWBOX_WIDTH} height={VIEWBOX_HEIGHT} rx="16" fill="#05070c" />
          <rect
            x={forecastStartX}
            y={MARGIN.top}
            width={VIEWBOX_WIDTH - forecastStartX - MARGIN.right}
            height={plotHeight}
            fill="rgba(30, 41, 59, 0.18)"
          />

          {gridTicks.map((tick) => {
            const y = priceToY(tick);
            return (
              <g key={tick}>
                <line x1={MARGIN.left} x2={VIEWBOX_WIDTH - MARGIN.right} y1={y} y2={y} stroke="rgba(255,255,255,0.08)" />
                <text x={MARGIN.left - 10} y={y + 4} fill="#94a3b8" fontSize="12" textAnchor="end">
                  {tick.toFixed(2)}
                </text>
              </g>
            );
          })}

          {candles.map((candle, index) => {
            const x = xForIndex(index);
            const isBull = candle.close >= candle.open;
            const isPrediction = candle.is_prediction;
            const color = isBull
              ? isPrediction
                ? 'rgba(34,197,94,0.50)'
                : '#22c55e'
              : isPrediction
                ? 'rgba(239,68,68,0.45)'
                : '#ef4444';
            const wickColor = isPrediction ? 'rgba(255,255,255,0.28)' : 'rgba(255,255,255,0.72)';
            const openY = priceToY(candle.open);
            const closeY = priceToY(candle.close);
            const highY = priceToY(candle.high);
            const lowY = priceToY(candle.low);
            const bodyY = Math.min(openY, closeY);
            const bodyHeight = Math.max(Math.abs(closeY - openY), 1.6);

            return (
              <g key={`${candle.timestamp}-${index}`}>
                <line x1={x} x2={x} y1={highY} y2={lowY} stroke={wickColor} strokeWidth={1.2} />
                <rect
                  x={x - bodyWidth / 2}
                  y={bodyY}
                  width={bodyWidth}
                  height={bodyHeight}
                  rx={1.4}
                  fill={color}
                />
              </g>
            );
          })}

          <line
            x1={forecastStartX}
            x2={forecastStartX}
            y1={MARGIN.top}
            y2={MARGIN.top + plotHeight}
            stroke="rgba(255,255,255,0.55)"
            strokeDasharray="6 6"
          />

          <text
            x={forecastStartX + 8}
            y={MARGIN.top + 16}
            fill="#cbd5e1"
            fontSize="12"
          >
            Forecast starts
          </text>

          {candles.map((candle, index) => {
            if (index % labelEvery !== 0 && index !== candles.length - 1) {
              return null;
            }
            const x = xForIndex(index);
            return (
              <g key={`label-${candle.timestamp}-${index}`}>
                <line
                  x1={x}
                  x2={x}
                  y1={MARGIN.top}
                  y2={MARGIN.top + plotHeight}
                  stroke="rgba(255,255,255,0.05)"
                />
                <text
                  x={x}
                  y={VIEWBOX_HEIGHT - 14}
                  fill="#94a3b8"
                  fontSize="12"
                  textAnchor="middle"
                >
                  {format(new Date(candle.timestamp), labelFormat)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-2 rounded-full border border-slate-700/70 bg-slate-900/70 px-3 py-1.5">
      <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: color }} />
      <span>{label}</span>
    </div>
  );
}
