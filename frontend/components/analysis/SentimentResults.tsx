'use client';

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui';
import { SentimentPill, Tag } from '@/components/ui';
import { SentimentScoreCard } from '@/components/analysis';
import { NewsBreakdownCard } from '@/components/analysis';
import { InfluentialArticleCard } from '@/components/analysis';
import type { SentimentalAnalysisResponse } from '@/types';

interface SentimentResultsProps {
  analysis: SentimentalAnalysisResponse;
}

export function SentimentResults({ analysis }: SentimentResultsProps) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <SentimentScoreCard
          score={analysis.score}
          overallSentiment={analysis.overall_sentiment}
          confidence={analysis.confidence}
          trend={analysis.trend}
          cached={analysis.cached}
          analyzedAt={analysis.analyzed_at}
        />

        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Analysis Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap items-center gap-2 mb-4">
              <Tag size="sm">{analysis.ticker}</Tag>
              <Tag size="sm" variant="info">
                {analysis.market}
              </Tag>
              <SentimentPill sentiment={analysis.overall_sentiment} />
              {analysis.source === 'model_artifact' && (
                <Tag size="sm" variant="success">
                  Model artifact
                </Tag>
              )}
            </div>

            <p className="text-text-secondary leading-relaxed">
              {analysis.analysis_summary}
            </p>

            <div className="mt-4 space-y-1 text-sm text-text-secondary">
              {analysis.source_model && (
                <div>
                  <span className="font-medium text-text-primary">Model:</span>{' '}
                  {analysis.source_model}
                  {analysis.artifact_version ? ` (${analysis.artifact_version})` : ''}
                </div>
              )}
              {typeof analysis.model_signal === 'number' && (
                <div>
                  <span className="font-medium text-text-primary">Model signal:</span>{' '}
                  {analysis.model_signal.toFixed(3)}
                </div>
              )}
              <span className="font-medium text-text-primary">Analyzed:</span>{' '}
              {new Date(analysis.analyzed_at).toLocaleString()}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <NewsBreakdownCard breakdown={analysis.news_breakdown} />
        <InfluentialArticleCard articles={analysis.influential_articles} />
      </div>
    </div>
  );
}
