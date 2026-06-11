'use client';

import { TrendingUp, TrendingDown } from 'lucide-react';
import { Card, CardContent, Button } from '@/components/ui';
import { ExchangeTag, SentimentPill } from '@/components/ui';
import { SparklineChart } from '@/components/charts';

/**
 * Stock Tile Component
 * 
 * Card displaying stock information with sparkline chart and sentiment indicators.
 */
interface StockTileProps {
  ticker: string;
  exchange: string;
  price: number;
  change: number;
  changePercent: number;
  volume: string;
  peRatio?: string;
  sentiment?: 'Positive' | 'Negative' | 'Neutral';
  technicalSignal?: 'BUY' | 'SELL' | 'HOLD' | 'NEUTRAL';
  sparklineData?: Array<{ value: number; index?: number }>;
  onReAnalyze?: () => void;
  onPaperTrade?: () => void;
}

export function StockTile({
  ticker,
  exchange,
  price,
  change,
  changePercent,
  volume,
  peRatio,
  sentiment,
  technicalSignal,
  sparklineData = [],
  onReAnalyze,
  onPaperTrade,
}: StockTileProps) {
  const isPositive = change >= 0;
  const changeColor = isPositive ? 'text-success-900' : 'text-danger-900';
  const changeIcon = isPositive ? <TrendingUp size={16} /> : <TrendingDown size={16} />;

  return (
    <Card className="hover:shadow-card-hover transition-shadow duration-200">
      <CardContent>
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="text-2xl font-bold text-text-primary">{ticker}</h3>
            <ExchangeTag exchange={exchange} />
          </div>
        </div>

        {/* Price Section */}
        <div className="flex items-baseline gap-3 mb-4">
          <span className="text-3xl font-bold text-text-primary">
            ${price.toFixed(2)}
          </span>
          <span className={`flex items-center gap-1 text-lg font-semibold ${changeColor}`}>
            {changeIcon}
            {isPositive ? '+' : ''}
            {changePercent.toFixed(2)}%
          </span>
        </div>

        {/* Sparkline Chart */}
        {sparklineData.length > 0 && (
          <div className="mb-4">
            <SparklineChart 
              data={sparklineData} 
              width={280} 
              height={60}
              color={isPositive ? '#10B981' : '#EF4444'}
            />
          </div>
        )}

        {/* Data Grid */}
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <p className="text-sm text-text-secondary">Volume</p>
            <p className="text-lg font-bold text-text-primary">{volume}</p>
          </div>
          {peRatio && (
            <div>
              <p className="text-sm text-text-secondary">P/E Ratio</p>
              <p className="text-lg font-bold text-text-primary">{peRatio}</p>
            </div>
          )}
        </div>

        {/* Indicators */}
        <div className="flex flex-wrap gap-2 mb-4">
          {sentiment && <SentimentPill sentiment={sentiment} />}
          {technicalSignal && (
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${
              technicalSignal === 'BUY' 
                ? 'bg-success-500 text-white' 
                : technicalSignal === 'SELL' 
                  ? 'bg-danger-500 text-white' 
                  : 'bg-slate-500 text-white'
            }`}>
              {technicalSignal}
            </span>
          )}
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <Button 
            variant="primary" 
            onClick={onReAnalyze}
            className="flex-1"
          >
            Re-analyze
          </Button>
          <Button 
            variant="secondary" 
            onClick={onPaperTrade}
            className="flex-1"
          >
            Paper Trade
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
