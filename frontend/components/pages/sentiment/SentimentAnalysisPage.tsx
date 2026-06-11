'use client';

import { useState } from 'react';
import { ExternalLink, Newspaper, Search, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { Button, Card, CardContent, Input } from '@/components/ui';
import { useSentimentStore } from '@/stores';
import { cn } from '@/lib';
import type { SentimentalAnalysisResponse, InfluentialArticle } from '@/types';

type FilterTab = 'All' | 'Positive' | 'Negative' | 'Neutral';

function SignalBadge({ verdict }: { verdict: 'BUY' | 'SELL' | 'HOLD' }) {
  const styles = {
    BUY:  'bg-emerald-50 text-emerald-700 border-emerald-200',
    SELL: 'bg-rose-50 text-rose-700 border-rose-200',
    HOLD: 'bg-amber-50 text-amber-700 border-amber-200',
  };
  return (
    <span className={cn('inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-bold', styles[verdict])}>
      {verdict}
    </span>
  );
}

function ArticleCard({ article }: { article: InfluentialArticle }) {
  const scoreColor = article.sentiment > 0.1 ? 'text-emerald-600' : article.sentiment < -0.1 ? 'text-rose-600' : 'text-amber-600';
  return (
    <div className="flex items-start gap-4 border-b border-slate-100 py-4 last:border-0 px-1">
      <div className={cn(
        'flex-shrink-0 w-12 h-12 rounded-xl flex items-center justify-center text-xs font-extrabold',
        article.sentiment > 0.1 ? 'bg-emerald-50' : article.sentiment < -0.1 ? 'bg-rose-50' : 'bg-amber-50',
        scoreColor,
      )}>
        {article.sentiment > 0 ? '+' : ''}{article.sentiment.toFixed(2)}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1">
            {article.url ? (
              <a href={article.url} target="_blank" rel="noopener noreferrer"
                className="font-bold text-slate-950 hover:text-blue-600 transition-colors leading-snug block text-sm">
                {article.title}
                <ExternalLink size={11} className="inline-block ml-1 opacity-40" />
              </a>
            ) : (
              <p className="font-bold text-slate-950 leading-snug text-sm">{article.title}</p>
            )}
            {article.source && <p className="text-xs text-slate-400 mt-0.5">{article.source}</p>}
          </div>
          <SignalBadge verdict={article.verdict} />
        </div>
        <p className="text-sm text-slate-500 mt-2 leading-relaxed">{article.reasoning}</p>
      </div>
    </div>
  );
}

function ResultsView({ analysis }: { analysis: SentimentalAnalysisResponse }) {
  const [filter, setFilter] = useState<FilterTab>('All');
  const b = analysis.news_breakdown;
  const filteredArticles = analysis.influential_articles.filter(a => {
    if (filter === 'All') return true;
    if (filter === 'Positive') return a.sentiment > 0.05;
    if (filter === 'Negative') return a.sentiment < -0.05;
    return Math.abs(a.sentiment) <= 0.05;
  });
  const positivePct = b.article_count > 0 ? Math.round((b.positive_count / b.article_count) * 100) : 0;
  const negativePct = b.article_count > 0 ? Math.round((b.negative_count / b.article_count) * 100) : 0;
  const neutralPct  = b.article_count > 0 ? Math.round((b.neutral_count  / b.article_count) * 100) : 0;
  const sentimentColor = analysis.overall_sentiment === 'Positive' ? 'text-emerald-600'
    : analysis.overall_sentiment === 'Negative' ? 'text-rose-600' : 'text-amber-600';
  const TrendIcon = analysis.trend === 'Improving' ? TrendingUp : analysis.trend === 'Declining' ? TrendingDown : Minus;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <Card className="border border-slate-200">
        <CardContent className="p-0">
          <div className="flex gap-0 border-b border-slate-100 px-4 pt-4">
            {(['All', 'Positive', 'Negative', 'Neutral'] as FilterTab[]).map(tab => (
              <button key={tab} onClick={() => setFilter(tab)}
                className={cn('px-4 py-2 text-sm font-semibold border-b-2 transition-colors',
                  filter === tab ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700'
                )}>
                {tab}
                <span className="ml-1.5 text-xs opacity-60">
                  {tab === 'All' ? b.article_count : tab === 'Positive' ? b.positive_count : tab === 'Negative' ? b.negative_count : b.neutral_count}
                </span>
              </button>
            ))}
          </div>
          <div className="px-4 py-2">
            {filteredArticles.length === 0
              ? <p className="text-center text-slate-400 text-sm py-8">No articles in this category</p>
              : filteredArticles.map((a, i) => <ArticleCard key={i} article={a} />)
            }
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card className="border border-slate-200">
          <CardContent className="p-5">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">{analysis.ticker} · Signal</p>
            <div className="flex items-center gap-2 mb-4">
              <p className={cn('text-2xl font-extrabold', sentimentColor)}>{analysis.overall_sentiment}</p>
              <TrendIcon size={18} className={sentimentColor} />
            </div>
            {[
              ['Score', `${analysis.score >= 0 ? '+' : ''}${analysis.score.toFixed(3)}`],
              ['Confidence', `${Math.round(analysis.confidence * 100)}%`],
              ['Trend', analysis.trend],
              ['Articles', String(b.article_count)],
            ].map(([label, val]) => (
              <div key={label} className="flex justify-between text-sm py-1.5 border-b border-slate-50 last:border-0">
                <span className="text-slate-500">{label}</span>
                <span className="font-bold text-slate-950">{val}</span>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="border border-slate-200">
          <CardContent className="p-5">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">Breakdown</p>
            <div className="flex h-2.5 rounded-full overflow-hidden mb-3">
              {positivePct > 0 && <div className="bg-emerald-500" style={{ width: `${positivePct}%` }} />}
              {neutralPct  > 0 && <div className="bg-amber-400"  style={{ width: `${neutralPct}%` }} />}
              {negativePct > 0 && <div className="bg-rose-500"   style={{ width: `${negativePct}%` }} />}
            </div>
            {[
              ['bg-emerald-500', 'Positive', b.positive_count, positivePct, 'text-emerald-700'],
              ['bg-amber-400',  'Neutral',  b.neutral_count,  neutralPct,  'text-amber-700'],
              ['bg-rose-500',   'Negative', b.negative_count, negativePct, 'text-rose-700'],
            ].map(([dot, label, count, pct, color]) => (
              <div key={String(label)} className="flex justify-between items-center text-sm py-1">
                <span className="flex items-center gap-1.5 text-slate-600">
                  <span className={cn('h-2 w-2 rounded-full inline-block', String(dot))} />{String(label)}
                </span>
                <span className={cn('font-bold', String(color))}>{String(count)} ({String(pct)}%)</span>
              </div>
            ))}
          </CardContent>
        </Card>

        {analysis.analysis_summary && (
          <Card className="border border-slate-200">
            <CardContent className="p-5">
              <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">AI Summary</p>
              <p className="text-sm text-slate-600 leading-relaxed">{analysis.analysis_summary}</p>
            </CardContent>
          </Card>
        )}
        <p className="text-xs text-slate-400 text-center">
          FinEdge Sentiment Model · NewsAPI · {analysis.source_model ?? 'AI'}
        </p>
      </div>
    </div>
  );
}

export default function SentimentAnalysisPage() {
  const [ticker, setTicker] = useState('');
  const [market, setMarket] = useState<'US' | 'IN'>('US');
  const [formError, setFormError] = useState<string | null>(null);
  const { analyzeSentiment, analysisStatus, analysisError, currentAnalysis, clearAnalysis } = useSentimentStore();

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const t = ticker.trim().toUpperCase();
    if (!t) { setFormError('Enter a ticker.'); return; }
    setFormError(null);
    try { await analyzeSentiment(t, market); } catch {}
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100">
          <Newspaper size={20} className="text-blue-600" />
        </div>
        <div>
          <h1 className="text-2xl font-extrabold text-slate-950">News Sentiment</h1>
          <p className="text-sm text-slate-500">AI-scored news — real market tone for any ticker</p>
        </div>
        {currentAnalysis && (
          <button onClick={clearAnalysis} className="ml-auto text-xs text-slate-400 hover:text-slate-600 underline">
            Clear
          </button>
        )}
      </div>

      <Card className="border border-slate-200">
        <CardContent className="p-4">
          <form onSubmit={onSubmit} className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[160px]">
              <Input label="Ticker" placeholder="MSFT, AAPL, NVDA..."
                value={ticker} onChange={e => setTicker(e.target.value)}
                leftIcon={<Search size={16} />} error={formError || undefined} />
            </div>
            <div className="w-28">
              <label className="block text-sm font-medium text-slate-700 mb-1">Market</label>
              <select value={market} onChange={e => setMarket(e.target.value as 'US' | 'IN')}
                className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="US">US</option>
                <option value="IN">India</option>
              </select>
            </div>
            <Button type="submit" variant="primary" size="lg" isLoading={analysisStatus === 'loading'}>
              Analyze
            </Button>
          </form>
          {analysisStatus === 'loading' && (
            <div className="mt-4 rounded-xl bg-slate-50 px-4 py-3">
              <div className="flex justify-between mb-1.5">
                <p className="text-sm text-slate-600">Fetching and scoring articles...</p>
                <span className="text-xs text-slate-400">~60s</span>
              </div>
              <div className="h-1 rounded-full bg-slate-200 overflow-hidden">
                <div className="h-full bg-blue-500 animate-pulse rounded-full w-2/3" />
              </div>
            </div>
          )}
          {analysisError && (
            <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{analysisError}</div>
          )}
        </CardContent>
      </Card>

      {currentAnalysis && <ResultsView analysis={currentAnalysis} />}
      {!currentAnalysis && analysisStatus !== 'loading' && (
        <div className="text-center py-20 text-slate-300">
          <Newspaper size={48} className="mx-auto mb-3" />
          <p className="text-sm text-slate-400">Enter a ticker to see AI-scored news sentiment</p>
        </div>
      )}
    </div>
  );
}
