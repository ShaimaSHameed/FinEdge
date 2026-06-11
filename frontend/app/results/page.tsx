'use client';

import { useAnalysisHistoryStore } from '@/stores';
import { cn } from '@/lib/utils';
import { BarChart3, Clock, TrendingUp, TrendingDown, Minus, Trash2, Search } from 'lucide-react';
import Link from 'next/link';

function SignalBadge({ signal }: { signal?: string }) {
  if (!signal) return <span className="text-slate-400 text-xs">—</span>;
  const s = signal.toUpperCase();
  return (
    <span className={cn(
      'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold',
      s === 'BUY' || s === 'STRONG BUY' || s === 'POSITIVE' ? 'bg-emerald-100 text-emerald-700' :
      s === 'SELL' || s === 'NEGATIVE' ? 'bg-rose-100 text-rose-700' :
      'bg-slate-100 text-slate-600'
    )}>
      {s}
    </span>
  );
}

function RecommendationIcon({ rec }: { rec: string }) {
  const r = rec.toUpperCase();
  if (r === 'BUY' || r === 'STRONG BUY') return <TrendingUp size={18} className="text-emerald-600" />;
  if (r === 'SELL') return <TrendingDown size={18} className="text-rose-600" />;
  return <Minus size={18} className="text-slate-400" />;
}

export default function ResultsPage() {
  const { history, clearHistory } = useAnalysisHistoryStore();

  if (history.length === 0) {
    return (
      <div className="mx-auto max-w-2xl pt-10 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-3xl bg-slate-100 text-slate-400">
          <BarChart3 size={28} />
        </div>
        <h1 className="mt-5 text-2xl font-extrabold text-slate-950">No analyses yet</h1>
        <p className="mt-2 text-sm text-slate-500">
          Every stock you analyse will appear here with its full signal breakdown.
        </p>
        <Link
          href="/analyze"
          className="mt-6 inline-flex items-center gap-2 rounded-full bg-primary-600 px-5 py-2.5 text-sm font-bold text-white shadow-md hover:bg-primary-700 transition-colors"
        >
          <Search size={15} />
          Analyse a stock
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-950">Analysis History</h1>
          <p className="mt-1 text-sm text-slate-500">{history.length} analyses · saved in your browser</p>
        </div>
        <button
          onClick={clearHistory}
          className="flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-bold text-slate-500 hover:border-rose-200 hover:text-rose-600 transition-colors"
        >
          <Trash2 size={13} />
          Clear history
        </button>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-100 text-sm">
          <thead className="bg-slate-50">
            <tr className="text-left text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
              <th className="px-6 py-4">Stock</th>
              <th className="px-6 py-4">Overall</th>
              <th className="px-6 py-4">Fundamental</th>
              <th className="px-6 py-4">Technical</th>
              <th className="px-6 py-4">Sentiment</th>
              <th className="px-6 py-4">Confidence</th>
              <th className="px-6 py-4">Analysed</th>
              <th className="px-6 py-4" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {history.map((entry) => (
              <tr key={entry.id} className="hover:bg-slate-50/60 transition-colors">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-600">
                      <RecommendationIcon rec={entry.overallRecommendation} />
                    </div>
                    <div>
                      <p className="font-extrabold text-slate-950">{entry.ticker}</p>
                      <p className="text-xs text-slate-500 truncate max-w-[120px]">{entry.companyName}</p>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <SignalBadge signal={entry.overallRecommendation} />
                </td>
                <td className="px-6 py-4">
                  <div>
                    <SignalBadge signal={entry.fundamentalSignal} />
                    {entry.fundamentalGap && (
                      <p className="mt-1 text-[10px] text-slate-400">{entry.fundamentalGap}</p>
                    )}
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div>
                    <SignalBadge signal={entry.technicalSignal} />
                    {entry.technicalMove && (
                      <p className="mt-1 text-[10px] text-slate-400">{entry.technicalMove}</p>
                    )}
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div>
                    <SignalBadge signal={entry.sentimentSignal} />
                    {entry.sentimentScore !== undefined && (
                      <p className="mt-1 text-[10px] text-slate-400">Score: {entry.sentimentScore.toFixed(2)}</p>
                    )}
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-16 rounded-full bg-slate-100">
                      <div
                        className={cn('h-full rounded-full', entry.confidence >= 70 ? 'bg-emerald-500' : entry.confidence >= 50 ? 'bg-amber-400' : 'bg-slate-400')}
                        style={{ width: `${Math.min(100, entry.confidence)}%` }}
                      />
                    </div>
                    <span className="text-xs font-bold text-slate-600">{entry.confidence}%</span>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-1.5 text-slate-400">
                    <Clock size={11} />
                    <span className="text-xs">{new Date(entry.analyzedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <Link
                    href={`/analyze?ticker=${entry.ticker}`}
                    className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 hover:border-primary-200 hover:text-primary-700 transition-colors"
                  >
                    Re-analyse
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
