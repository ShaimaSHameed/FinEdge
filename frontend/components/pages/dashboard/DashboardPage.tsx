'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Search, TrendingUp, TrendingDown, ArrowRight,
  Bookmark, Trash2, BarChart3, Newspaper, Flame,
  RefreshCw, ExternalLink,
} from 'lucide-react';
import { SparklineChart } from '@/components/charts';
import { cn } from '@/lib/utils';
import { marketApi } from '@/lib';
import { useWatchlistStore } from '@/stores';
import { FUNDAMENTAL_PROFILES, type CoverageTicker } from '@/components/pages/fundamental/FundamentalAnalysisPage';

// ─── Types ────────────────────────────────────────────────────────────────────
interface IndexData  { label: string; value: string; change: string; positive: boolean }
interface MoverData  { ticker: string; name: string; price: string; change: string; positive: boolean }
interface NewsItem   { headline: string; url: string; source: string; time: string }
interface PriceData  { price: number; change: number; changePercent: number }

interface MarketData {
  indexes: IndexData[];
  prices: Record<string, PriceData>;
  gainers: MoverData[];
  losers: MoverData[];
  news: NewsItem[];
}

// ─── Static sparkline seeds (shape only, price overridden by live data) ──────
const SPARKLINE_SEEDS: Record<string, Array<{value: number; index: number}>> = {
  MSFT:  [412,415,417,418,421,423,425,428].map((v,i) => ({value: v, index: i})),
  GOOGL: [165,167,168,169,170,171,172,173].map((v,i) => ({value: v, index: i})),
  AAPL:  [219,218,217,216,215,216,215,214].map((v,i) => ({value: v, index: i})),
  NVDA:  [132,134,135,137,138,139,141,143].map((v,i) => ({value: v, index: i})),
};

const FEATURED_TICKERS = ['MSFT', 'GOOGL', 'AAPL', 'NVDA'] as CoverageTicker[];
const TRENDING = ['NVDA', 'MSFT', 'GOOGL', 'AAPL', 'META', 'TSLA', 'AMD'];

// ─── Skeleton ─────────────────────────────────────────────────────────────────
function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded bg-slate-100', className)} />;
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const router = useRouter();
  const [searchInput, setSearchInput] = useState('');
  const [market, setMarket] = useState<MarketData | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string>('');
  const { items: watchlistItems, removeFromWatchlist } = useWatchlistStore();

  const fetchMarket = useCallback(async () => {
    try {
      const data = await marketApi.overview();
      setMarket(data);
      setLastUpdated(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
    } catch {
      // keep previous data if refresh fails
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchMarket();
    const iv = setInterval(() => void fetchMarket(), 60000); // refresh every 60s
    return () => clearInterval(iv);
  }, [fetchMarket]);

  const handleSearch = (ticker?: string) => {
    const t = (ticker ?? searchInput).trim().toUpperCase();
    if (t) router.push(`/analyze?ticker=${t}`);
  };

  // Merge watchlist items with live prices
  const displayTickers = watchlistItems.length > 0
    ? watchlistItems.map(w => w.ticker as CoverageTicker)
    : FEATURED_TICKERS;

  return (
    <div className="space-y-7">

      {/* ── Index Bar ── */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {loading
          ? Array.from({length: 4}).map((_, i) => (
              <div key={i} className="rounded-2xl border border-slate-200 bg-white px-4 py-3.5 space-y-2">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-6 w-24" />
                <Skeleton className="h-3 w-12" />
              </div>
            ))
          : (market?.indexes ?? []).map((idx) => (
              <div key={idx.label} className="rounded-2xl border border-slate-200 bg-white px-4 py-3.5">
                <p className="text-xs font-semibold text-slate-500">{idx.label}</p>
                <p className="mt-1 text-xl font-extrabold tracking-tight text-slate-950">{idx.value}</p>
                <p className={cn('mt-0.5 text-sm font-bold', idx.positive ? 'text-emerald-600' : 'text-rose-600')}>
                  {idx.change}
                </p>
              </div>
            ))
        }
      </div>

      {/* ── Hero Search ── */}
      <div className="rounded-3xl border border-slate-200 bg-gradient-to-b from-slate-50 to-white px-6 py-10 text-center">
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-950 md:text-4xl">
          Search any stock to start your analysis
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Fundamental · Technical · Sentiment — three models, one recommendation.
        </p>

        <div className="mx-auto mt-6 flex max-w-xl items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2.5 shadow-sm focus-within:border-primary-400 focus-within:ring-2 focus-within:ring-primary-100 transition-all">
          <Search size={18} className="shrink-0 text-slate-400" />
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Company or stock symbol..."
            className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-slate-900 outline-none placeholder:font-normal placeholder:text-slate-400"
          />
          <button
            onClick={() => handleSearch()}
            className="shrink-0 rounded-full bg-primary-600 px-4 py-1.5 text-sm font-bold text-white hover:bg-primary-700 transition-colors"
          >
            Analyse
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
          <span className="flex items-center gap-1 text-xs text-slate-400">
            <Flame size={12} /> Trending:
          </span>
          {TRENDING.map((t) => (
            <button
              key={t}
              onClick={() => handleSearch(t)}
              className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-bold text-slate-600 hover:border-primary-300 hover:text-primary-700 transition-colors"
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* ── Watchlist / Featured ── */}
      <section>
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bookmark size={16} className="text-amber-500" />
            <h2 className="text-lg font-extrabold tracking-tight text-slate-950">
              {watchlistItems.length > 0 ? 'Your Watchlist' : 'Featured Stocks'}
            </h2>
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-bold text-slate-500">
              {displayTickers.length}
            </span>
          </div>
          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="text-xs text-slate-400 flex items-center gap-1">
                <RefreshCw size={10} /> {lastUpdated}
              </span>
            )}
            <button
              onClick={() => router.push('/analyze')}
              className="flex items-center gap-1 text-xs font-bold text-primary-600 hover:text-primary-700"
            >
              Analyse all <ArrowRight size={13} />
            </button>
          </div>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
          <table className="min-w-full divide-y divide-slate-100 text-sm">
            <thead className="bg-slate-50">
              <tr className="text-left text-[11px] font-extrabold uppercase tracking-[0.14em] text-slate-500">
                <th className="px-5 py-3">Stock</th>
                <th className="px-5 py-3">Price</th>
                <th className="px-5 py-3 hidden md:table-cell">7D</th>
                <th className="px-5 py-3">Change</th>
                <th className="px-5 py-3 hidden lg:table-cell">About</th>
                <th className="px-5 py-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {displayTickers.map((ticker) => {
                const livePrice = market?.prices?.[ticker];
                const profile = FUNDAMENTAL_PROFILES[ticker as CoverageTicker];
                const isUp = (livePrice?.changePercent ?? 0) >= 0;
                const inWatchlist = watchlistItems.find(w => w.ticker === ticker);

                return (
                  <tr key={ticker} className="hover:bg-slate-50/60 transition-colors">
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100 text-xs font-extrabold text-slate-700">
                          {ticker.slice(0, 2)}
                        </div>
                        <div>
                          <p className="font-extrabold text-slate-950">{ticker}</p>
                          <p className="text-xs text-slate-400">{profile?.companyName ?? ticker}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      {loading || !livePrice
                        ? <Skeleton className="h-4 w-16" />
                        : <p className="font-bold text-slate-950">${livePrice.price.toFixed(2)}</p>
                      }
                    </td>
                    <td className="hidden px-5 py-3.5 md:table-cell">
                      <SparklineChart data={SPARKLINE_SEEDS[ticker] ?? []} height={32} width={80} />
                    </td>
                    <td className="px-5 py-3.5">
                      {loading || !livePrice
                        ? <Skeleton className="h-5 w-14 rounded-full" />
                        : (
                          <span className={cn(
                            'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-bold',
                            isUp ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'
                          )}>
                            {isUp ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
                            {isUp ? '+' : ''}{livePrice.changePercent.toFixed(2)}%
                          </span>
                        )
                      }
                    </td>
                    <td className="hidden px-5 py-3.5 lg:table-cell max-w-[240px]">
                      <p className="truncate text-xs text-slate-500">{profile?.headline?.slice(0, 80)}...</p>
                    </td>
                    <td className="px-5 py-3.5 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => router.push(`/analyze?ticker=${ticker}`)}
                          className="rounded-full bg-primary-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-primary-700 transition-colors"
                        >
                          Analyse
                        </button>
                        {inWatchlist && (
                          <button
                            onClick={() => removeFromWatchlist(ticker)}
                            className="text-slate-300 hover:text-rose-500 transition-colors"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── Market Movers + News ── */}
      <div className="grid gap-5 lg:grid-cols-[1fr_1fr_1.5fr]">

        {/* Top Gainers */}
        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
          <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
            <TrendingUp size={14} className="text-emerald-500" />
            <h3 className="text-sm font-extrabold text-slate-950">Top Gainers</h3>
            <span className="ml-auto text-[10px] text-slate-400">Today · NYSE</span>
          </div>
          <div className="divide-y divide-slate-100">
            {loading
              ? Array.from({length: 5}).map((_, i) => (
                  <div key={i} className="flex items-center justify-between px-4 py-2.5">
                    <Skeleton className="h-8 w-24" />
                    <Skeleton className="h-8 w-16" />
                  </div>
                ))
              : (market?.gainers ?? []).map((s) => (
                  <button
                    key={s.ticker}
                    onClick={() => router.push(`/analyze?ticker=${s.ticker}`)}
                    className="flex w-full items-center justify-between px-4 py-2.5 hover:bg-slate-50 transition-colors text-left"
                  >
                    <div>
                      <p className="text-sm font-bold text-slate-950">{s.ticker}</p>
                      <p className="text-xs text-slate-400 truncate max-w-[110px]">{s.name}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-bold text-slate-950">{s.price}</p>
                      <p className="text-xs font-bold text-emerald-600">{s.change}</p>
                    </div>
                  </button>
                ))
            }
          </div>
        </div>

        {/* Top Losers */}
        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
          <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
            <TrendingDown size={14} className="text-rose-500" />
            <h3 className="text-sm font-extrabold text-slate-950">Top Losers</h3>
            <span className="ml-auto text-[10px] text-slate-400">Today · NYSE</span>
          </div>
          <div className="divide-y divide-slate-100">
            {loading
              ? Array.from({length: 5}).map((_, i) => (
                  <div key={i} className="flex items-center justify-between px-4 py-2.5">
                    <Skeleton className="h-8 w-24" />
                    <Skeleton className="h-8 w-16" />
                  </div>
                ))
              : (market?.losers ?? []).map((s) => (
                  <button
                    key={s.ticker}
                    onClick={() => router.push(`/analyze?ticker=${s.ticker}`)}
                    className="flex w-full items-center justify-between px-4 py-2.5 hover:bg-slate-50 transition-colors text-left"
                  >
                    <div>
                      <p className="text-sm font-bold text-slate-950">{s.ticker}</p>
                      <p className="text-xs text-slate-400 truncate max-w-[110px]">{s.name}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-bold text-slate-950">{s.price}</p>
                      <p className="text-xs font-bold text-rose-600">{s.change}</p>
                    </div>
                  </button>
                ))
            }
          </div>
        </div>

        {/* Live Market News */}
        <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
          <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
            <Newspaper size={14} className="text-primary-500" />
            <h3 className="text-sm font-extrabold text-slate-950">Market News</h3>
            <span className="ml-auto text-[10px] text-slate-400">Live</span>
          </div>
          <div className="divide-y divide-slate-100">
            {loading
              ? Array.from({length: 6}).map((_, i) => (
                  <div key={i} className="px-4 py-3 space-y-1.5">
                    <Skeleton className="h-3 w-20" />
                    <Skeleton className="h-4 w-full" />
                    <Skeleton className="h-4 w-3/4" />
                  </div>
                ))
              : (market?.news ?? []).map((n, i) => (
                  <a
                    key={i}
                    href={n.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block px-4 py-3 hover:bg-slate-50 transition-colors group"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-bold text-primary-600 uppercase">{n.source}</span>
                      <ExternalLink size={10} className="text-slate-300 group-hover:text-slate-500 transition-colors" />
                    </div>
                    <p className="text-xs leading-5 text-slate-700 line-clamp-2 group-hover:text-slate-950 transition-colors">
                      {n.headline}
                    </p>
                  </a>
                ))
            }
          </div>
        </div>
      </div>

      {/* ── Quick Links ── */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { label: 'Fundamental', sub: 'Valuation & financials', href: '/fundamental', icon: <BarChart3 size={18} /> },
          { label: 'Technical', sub: 'Price forecasting', href: '/technical', icon: <TrendingUp size={18} /> },
          { label: 'Sentiment', sub: 'News & market tone', href: '/sentiment', icon: <Newspaper size={18} /> },
          { label: 'History', sub: 'Past analyses', href: '/results', icon: <Search size={18} /> },
        ].map((link) => (
          <button
            key={link.href}
            onClick={() => router.push(link.href)}
            className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-white p-4 text-left hover:border-primary-200 hover:shadow-sm transition-all"
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
              {link.icon}
            </div>
            <div>
              <p className="text-sm font-bold text-slate-950">{link.label}</p>
              <p className="text-xs text-slate-400">{link.sub}</p>
            </div>
          </button>
        ))}
      </div>

    </div>
  );
}
