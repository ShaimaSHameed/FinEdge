'use client';

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui';
import { SentimentDistributionChart } from '@/components/charts';
import type { NewsSentimentBreakdown } from '@/types';

/**
 * NewsBreakdownCard Component
 * 
 * Displays news sentiment breakdown with statistics and article lists.
 */
interface NewsBreakdownCardProps {
  breakdown: NewsSentimentBreakdown;
}

export function NewsBreakdownCard({ breakdown }: NewsBreakdownCardProps) {
  const { article_count, positive_count, negative_count, neutral_count, average_score, top_positive_articles, top_negative_articles } = breakdown;

  // Prepare chart data
  const chartData = [
    { name: 'Positive', value: positive_count, color: '#10B981' },
    { name: 'Negative', value: negative_count, color: '#EF4444' },
    { name: 'Neutral', value: neutral_count, color: '#94A3B8' },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>News Breakdown</CardTitle>
      </CardHeader>
      <CardContent>
        {/* Statistics */}
        <div className="mb-6">
          <p className="text-lg font-semibold text-text-primary mb-4">
            Total Articles: {article_count}
          </p>

          {/* Sentiment Distribution Chart */}
          <div className="mb-4">
            <SentimentDistributionChart data={chartData} width={500} height={200} />
          </div>

          <div className="flex justify-between items-center text-sm text-text-secondary">
            <span>Positive: {positive_count}</span>
            <span>Negative: {negative_count}</span>
            <span>Neutral: {neutral_count}</span>
          </div>
        </div>

        {/* Average Score */}
        <div className="mb-6 p-4 bg-slate-50 rounded-lg">
          <p className="text-sm text-text-secondary mb-1">Average Score</p>
          <p className={`text-3xl font-bold ${average_score > 0 ? 'text-success-900' : average_score < 0 ? 'text-danger-900' : 'text-text-primary'}`}>
            {average_score.toFixed(3)}
          </p>
        </div>

        {/* Top Positive Articles */}
        {top_positive_articles.length > 0 && (
          <div className="mb-6">
            <h4 className="text-lg font-semibold text-success-900 mb-3">
              Top Positive Articles
            </h4>
            <div className="space-y-3">
              {top_positive_articles.map((article, index) => (
                <div key={`pos-${index}`} className="p-4 bg-success-50 rounded-lg border border-success-200">
                  <div className="flex items-start justify-between mb-2">
                    <h5 className="font-semibold text-text-primary flex-1">
                      {article.title}
                    </h5>
                    <span className={`text-sm font-bold px-2 py-1 rounded ${
                      article.verdict === 'BUY' ? 'bg-success-500 text-white' : 'bg-slate-500 text-white'
                    }`}>
                      {article.verdict}
                    </span>
                  </div>
                  <div className="text-sm text-text-secondary space-y-1">
                    <p>Score: {article.score.toFixed(3)}</p>
                    <p>Source: {article.source}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Top Negative Articles */}
        {top_negative_articles.length > 0 && (
          <div>
            <h4 className="text-lg font-semibold text-danger-900 mb-3">
              Top Negative Articles
            </h4>
            <div className="space-y-3">
              {top_negative_articles.map((article, index) => (
                <div key={`neg-${index}`} className="p-4 bg-danger-50 rounded-lg border border-danger-200">
                  <div className="flex items-start justify-between mb-2">
                    <h5 className="font-semibold text-text-primary flex-1">
                      {article.title}
                    </h5>
                    <span className={`text-sm font-bold px-2 py-1 rounded ${
                      article.verdict === 'SELL' ? 'bg-danger-500 text-white' : 'bg-slate-500 text-white'
                    }`}>
                      {article.verdict}
                    </span>
                  </div>
                  <div className="text-sm text-text-secondary space-y-1">
                    <p>Score: {article.score.toFixed(3)}</p>
                    <p>Source: {article.source}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
