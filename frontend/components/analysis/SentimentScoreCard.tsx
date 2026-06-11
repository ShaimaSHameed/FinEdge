'use client';

import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Card, CardContent } from '@/components/ui';
import { VerdictBadge } from '@/components/ui';

/**
 * SentimentScoreCard Component
 * 
 * Displays overall sentiment score with verdict badge and confidence level.
 */
interface SentimentScoreCardProps {
  score: number;
  overallSentiment: 'Positive' | 'Negative' | 'Neutral';
  confidence: number;
  trend: 'Improving' | 'Declining' | 'Stable';
  cached?: boolean;
  analyzedAt?: string;
}

export function SentimentScoreCard({
  score,
  overallSentiment: _overallSentiment,
  confidence,
  trend,
  cached = false,
  analyzedAt,
}: SentimentScoreCardProps) {
  // Determine verdict based on score
  const getVerdict = (): 'BUY' | 'SELL' | 'HOLD' => {
    if (score > 0.2) return 'BUY';
    if (score < -0.2) return 'SELL';
    return 'HOLD';
  };

  // Get trend icon
  const getTrendIcon = () => {
    switch (trend) {
      case 'Improving':
        return <TrendingUp className="text-success-900" size={20} />;
      case 'Declining':
        return <TrendingDown className="text-danger-900" size={20} />;
      case 'Stable':
        return <Minus className="text-text-secondary" size={20} />;
    }
  };

  // Get score background color
  const getScoreBackgroundColor = () => {
    if (score > 0.2) return 'bg-success-100';
    if (score < -0.2) return 'bg-danger-100';
    return 'bg-slate-100';
  };

  return (
    <Card>
      <CardContent>
        <div className="text-center">
          {/* Score Display */}
          <div className={`inline-block px-8 py-4 rounded-2xl ${getScoreBackgroundColor()} mb-6`}>
            <div className="text-5xl font-bold text-text-primary">
              {score.toFixed(3)}
            </div>
          </div>

          {/* Verdict Badge */}
          <div className="mb-4">
            <VerdictBadge verdict={getVerdict()} />
          </div>

          {/* Trend Indicator */}
          <div className="flex items-center justify-center gap-2 mb-4">
            {getTrendIcon()}
            <span className="text-lg font-semibold text-text-primary">
              {trend}
            </span>
          </div>

          {/* Confidence Score */}
          <div className="mb-6">
            <p className="text-sm text-text-secondary mb-2">Confidence</p>
            <div className="w-full bg-slate-200 rounded-full h-3 overflow-hidden">
              <div
                className="h-full bg-primary-600 transition-all duration-500"
                style={{ width: `${confidence * 100}%` }}
              />
            </div>
            <p className="text-sm text-text-secondary mt-1">
              {Math.round(confidence * 100)}%
            </p>
          </div>

          {/* Cached Indicator */}
          {cached && (
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-amber-100 text-amber-900 rounded-lg mb-4">
              <span className="text-sm font-medium">Results from cache</span>
            </div>
          )}

          {/* Analyzed At */}
          {analyzedAt && (
            <p className="text-xs text-text-secondary">
              Analyzed at {new Date(analyzedAt).toLocaleString()}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
