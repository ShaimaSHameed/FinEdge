'use client';

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  BarChart3,
  Bookmark,
  Building2,
  CandlestickChart,
  Circle,
  FileText,
  Loader2,
  Newspaper,
  Search,
} from 'lucide-react';
import { Button, Card, CardContent, Tag } from '@/components/ui';
import { TradingViewChart } from '@/components/charts/TradingViewChart';
import { TechnicalCandlesChart } from '@/components/charts';
import { useWatchlistStore, useAnalysisHistoryStore } from '@/stores';
import {
  FUNDAMENTAL_PROFILES,
  profileFromFundamentalResponse,
  type CoverageTicker,
  type FundamentalProfile,
} from '@/components/pages/fundamental/FundamentalAnalysisPage';
import { cn, fundamentalApi, handleApiError, sentimentApi, technicalApi } from '@/lib';
import type { FundamentalAnalysisResponse, SentimentalAnalysisResponse, TechnicalAnalysisResponse } from '@/types';

type AnalysisTab = 'overview' | 'fundamental' | 'technical' | 'sentiment';
type AnalysisStatus = 'idle' | 'loading' | 'success' | 'error';
type SignalTone = 'success' | 'warning' | 'danger' | 'neutral';

interface StockSnapshot {
  ticker: CoverageTicker;
  companyName: string;
  exchange: string;
  currency: string;
  marketStatus: string;
  price: number;
  change: number;
  changePercent: number;
  preMarket: number;
  marketCap: string;
  revenue: string;
  netIncome: string;
  eps: string;
  peRatio: string;
  forwardPe: string;
  volume: string;
  weekRange: string;
  beta: string;
  nextEarnings: string;
}

interface CombinedStockAnalysis {
  ticker: CoverageTicker;
  snapshot: StockSnapshot;
  profile: FundamentalProfile;
  fundamental: FundamentalAnalysisResponse | null;
  technical: TechnicalAnalysisResponse | null;
  sentiment: SentimentalAnalysisResponse | null;
  fundamentalError: string | null;
  technicalError: string | null;
  sentimentError: string | null;
}

const DEFAULT_TICKER: CoverageTicker = 'MSFT';
const COVERAGE_TICKERS = Object.keys(FUNDAMENTAL_PROFILES) as CoverageTicker[];

// Sourced directly from features.csv (snapshot 2025-06-30 / 2025-07-31)
// Used when the features API is unavailable — guarantees data always shows for covered tickers
const STATIC_FEATURES: Record<string, Record<string, number>> = {
  MSFT: {
    gross_margin: 0.6882, operating_margin: 0.4562, net_margin: 0.3615,
    roe: 0.2965, roa: 0.1645, roic: 0.2690,
    revenue_growth_yoy: 0.1493, earnings_growth_yoy: 0.1554, fcf_growth_yoy: -0.0332,
    pe_ratio: 35.84, pb_ratio: 10.63, ps_ratio: 12.96, ev_ebitda: 22.98,
    debt_to_equity: 0.1764, current_ratio: 1.3534,
    piotroski_score: 6, fcf_margin: 0.2542, fcf_yield: 0.0196,
    analyst_bull_score: 0.9180, short_interest_pct: 0.0091,
    cash: 78223000000, total_debt_raw: 60588000000, fcf_ttm: 68000000000,
    net_debt_ebitda: 0.50, interest_coverage: 80,
  },
  GOOGL: {
    gross_margin: 0.5894, operating_margin: 0.3268, net_margin: 0.3112,
    roe: 0.3185, roa: 0.2302, roic: 0.2926,
    revenue_growth_yoy: 0.1313, earnings_growth_yoy: 0.3185, fcf_growth_yoy: 0.0977,
    pe_ratio: 18.52, pb_ratio: 5.90, ps_ratio: 5.76, ev_ebitda: 13.66,
    debt_to_equity: 0.0980, current_ratio: 1.9037,
    piotroski_score: 5, fcf_margin: 0.1797, fcf_yield: 0.0312,
    analyst_bull_score: 0.8235, short_interest_pct: 0.0064,
    cash: 126840000000, total_debt_raw: 35559000000, fcf_ttm: 64430000000,
    net_debt_ebitda: -0.90, interest_coverage: 111,
  },
  TSLA: {
    gross_margin: 0.1748, operating_margin: 0.0606, net_margin: 0.0654,
    roe: 0.0784, roa: 0.0472, roic: 0.0570,
    revenue_growth_yoy: -0.0273, earnings_growth_yoy: -0.5179, fcf_growth_yoy: 2.2533,
    pe_ratio: 358.55, pb_ratio: 13.69, ps_ratio: 11.41, ev_ebitda: 76.63,
    debt_to_equity: 0.1699, current_ratio: 2.0372,
    piotroski_score: 6, fcf_margin: 0.0602, fcf_yield: 0.0053,
    analyst_bull_score: 0.4468, short_interest_pct: 0.0200,
    cash: 36560000000, total_debt_raw: 13134000000, fcf_ttm: 5800000000,
    net_debt_ebitda: -2.20, interest_coverage: 42,
  },
  AAPL: {
    gross_margin: 0.4668, operating_margin: 0.3187, net_margin: 0.2430,
    roe: 1.5081, roa: 0.2995, roic: 0.6840,
    revenue_growth_yoy: 0.0597, earnings_growth_yoy: -0.0262, fcf_growth_yoy: -0.0782,
    pe_ratio: 31.20, pb_ratio: 47.05, ps_ratio: 7.58, ev_ebitda: 22.43,
    debt_to_equity: 1.5449, current_ratio: 0.8680,
    piotroski_score: 6, fcf_margin: 0.2354, fcf_yield: 0.0311,
    analyst_bull_score: 0.5870, short_interest_pct: 0.0080,
    cash: 67150000000, total_debt_raw: 101698000000, fcf_ttm: 99000000000,
    net_debt_ebitda: 0.80, interest_coverage: 50,
  },
  NVDA: {
    gross_margin: 0.6985, operating_margin: 0.5809, net_margin: 0.5241,
    roe: 0.8648, roa: 0.6153, roic: 0.8240,
    revenue_growth_yoy: 0.7155, earnings_growth_yoy: 0.6337, fcf_growth_yoy: 0.5394,
    pe_ratio: 50.78, pb_ratio: 43.91, ps_ratio: 26.61, ev_ebitda: 42.60,
    debt_to_equity: 0.1058, current_ratio: 4.2140,
    piotroski_score: 4, fcf_margin: 0.4359, fcf_yield: 0.0164,
    analyst_bull_score: 0.8730, short_interest_pct: 0.0100,
    cash: 30000000000, total_debt_raw: 10598000000, fcf_ttm: 50000000000,
    net_debt_ebitda: -0.50, interest_coverage: 120,
  },
};

const COMPANY_ABOUT: Partial<Record<string, { description: string; segments: string[] }>> = {
  MSFT: {
    description: "Microsoft develops cloud computing, productivity software, and AI tools for individuals and enterprises. Azure is the world's second-largest cloud platform. Copilot AI is being embedded across all products, creating a new growth layer.",
    segments: ["Intelligent Cloud — Azure, SQL Server, GitHub", "Productivity & Business Processes — Microsoft 365, Teams, LinkedIn", "More Personal Computing — Windows, Xbox, Surface"],
  },
  GOOGL: {
    description: "Alphabet is Google's parent company. Google Search dominates global web traffic and digital advertising. YouTube is the world's largest video platform. Google Cloud is one of the fastest-growing enterprise cloud businesses.",
    segments: ["Google Services — Search, YouTube, Maps, Gmail", "Google Cloud — GCP, Workspace, AI infrastructure", "Other Bets — Waymo (autonomous driving), DeepMind"],
  },
  AAPL: {
    description: "Apple designs premium consumer electronics, software, and services. The iPhone is its core product, while the high-margin Services segment (App Store, Apple Pay, iCloud) is now its fastest-growing division.",
    segments: ["iPhone — primary revenue driver (~50% of sales)", "Services — App Store, Apple Music, iCloud, Apple Pay", "Mac, iPad, Wearables & Accessories"],
  },
  NVDA: {
    description: "NVIDIA designs GPUs and AI accelerator chips. Its H100 and Blackwell chips dominate AI model training, with virtually every major AI lab and cloud provider as a customer. The Data Center segment is now its primary revenue source.",
    segments: ["Data Center — AI training GPUs (H100, B200), networking", "Gaming — GeForce consumer GPUs", "Professional Visualization & Automotive"],
  },
  TSLA: {
    description: "Tesla designs and manufactures electric vehicles and energy storage systems. It leads the US EV market and is developing full self-driving capability. The Cybertruck, Semi, and next-gen affordable model are key growth catalysts.",
    segments: ["Automotive — Model 3/Y/S/X, Cybertruck, FSD software", "Energy Generation & Storage — Powerwall, Megapack", "Services — Supercharging, insurance, software updates"],
  },
};

const STOCK_SNAPSHOTS: Record<CoverageTicker, StockSnapshot> = {
  MSFT: {
    ticker: 'MSFT',
    companyName: 'Microsoft Corp.',
    exchange: 'NASDAQ',
    currency: 'USD',
    marketStatus: 'Market Closed · opens in 1d 15h',
    price: 428.15,
    change: 5.22,
    changePercent: 1.24,
    preMarket: 429.05,
    marketCap: '$3.2T',
    revenue: '$245.1B',
    netIncome: '$88.1B',
    eps: '11.82',
    peRatio: '36.2',
    forwardPe: '31.4',
    volume: '26.4M',
    weekRange: '309.45 - 430.82',
    beta: '0.91',
    nextEarnings: 'Jul 24, 2026',
  },
  AAPL: {
    ticker: 'AAPL',
    companyName: 'Apple Inc.',
    exchange: 'NASDAQ',
    currency: 'USD',
    marketStatus: 'Market Closed · opens in 1d 15h',
    price: 214.6,
    change: -1.38,
    changePercent: -0.64,
    preMarket: 215.1,
    marketCap: '$3.05T',
    revenue: '$385.6B',
    netIncome: '$97.0B',
    eps: '6.42',
    peRatio: '30.9',
    forwardPe: '28.5',
    volume: '54.2M',
    weekRange: '164.08 - 237.49',
    beta: '1.24',
    nextEarnings: 'Jul 31, 2026',
  },
  NVDA: {
    ticker: 'NVDA',
    companyName: 'NVIDIA Corp.',
    exchange: 'NASDAQ',
    currency: 'USD',
    marketStatus: 'Market Closed · opens in 1d 15h',
    price: 142.8,
    change: 3.14,
    changePercent: 2.25,
    preMarket: 143.35,
    marketCap: '$3.5T',
    revenue: '$130.5B',
    netIncome: '$72.9B',
    eps: '2.94',
    peRatio: '48.6',
    forwardPe: '34.8',
    volume: '48.9M',
    weekRange: '75.61 - 153.13',
    beta: '1.69',
    nextEarnings: 'Aug 27, 2026',
  },
  GOOGL: {
    ticker: 'GOOGL',
    companyName: 'Alphabet Inc.',
    exchange: 'NASDAQ',
    currency: 'USD',
    marketStatus: 'Market Closed',
    price: 173.50,
    change: 2.14,
    changePercent: 1.25,
    preMarket: 174.20,
    marketCap: '$2.1T',
    revenue: '$350.0B',
    netIncome: '$94.3B',
    eps: '7.65',
    peRatio: '22.7',
    forwardPe: '20.4',
    volume: '24.8M',
    weekRange: '140.53 - 207.05',
    beta: '1.06',
    nextEarnings: 'Jul 29, 2026',
  },
};

const TAB_OPTIONS: Array<{ value: AnalysisTab; label: string }> = [
  { value: 'overview', label: 'Overview' },
  { value: 'fundamental', label: 'Fundamental' },
  { value: 'technical', label: 'Technical' },
  { value: 'sentiment', label: 'Sentiment' },
];

function normalizeCoverageTicker(value: string | null): CoverageTicker | null {
  const normalized = value?.trim().toUpperCase();
  if (!normalized) return null;
  // Accept coverage tickers for full profile data
  return COVERAGE_TICKERS.includes(normalized as CoverageTicker) ? (normalized as CoverageTicker) : null;
}

function normalizeAnyTicker(value: string | null): string | null {
  const normalized = value?.trim().toUpperCase();
  return normalized || null;
}

function formatMoney(value: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value);
}

function formatSignedPercent(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function signalFromFundamental(response: FundamentalAnalysisResponse | null) {
  return response?.rating ?? 'HOLD';
}

function signalFromTechnical(analysis: TechnicalAnalysisResponse | null) {
  if (!analysis) return 'HOLD';
  // Use RL policy stance as primary signal (from the actual model)
  const stance = String(analysis.policy?.stance ?? "").toUpperCase();
  if (stance === 'LONG') return 'BUY';
  if (stance === 'SHORT') return 'SELL';
  if (stance === 'FLAT') return 'HOLD';
  // Fallback: use forecast price movement
  if (!analysis.forecast_bars?.length) return 'HOLD';
  const last = analysis.forecast_bars[analysis.forecast_bars.length - 1];
  const movePct = analysis.latest_price > 0 ? ((last.close - analysis.latest_price) / analysis.latest_price) * 100 : 0;
  if (movePct > 0.35) return 'BUY';
  if (movePct < -0.35) return 'SELL';
  return 'HOLD';
}

function signalFromSentiment(analysis: SentimentalAnalysisResponse | null) {
  if (!analysis) {
    return 'NEUTRAL';
  }
  return analysis.overall_sentiment.toUpperCase();
}

function toneFromSignal(signal: string): SignalTone {
  if (['BUY', 'STRONG BUY', 'POSITIVE', 'UP'].includes(signal)) {
    return 'success';
  }
  if (['SELL', 'STRONG SELL', 'NEGATIVE', 'DOWN'].includes(signal)) {
    return 'danger';
  }
  if (['HOLD', 'NEUTRAL'].includes(signal)) {
    return 'warning';
  }
  return 'neutral';
}

function combinedRecommendation(result: CombinedStockAnalysis | null) {
  if (!result) {
    return { label: 'ANALYSE', confidence: 0, tone: 'neutral' as SignalTone, availableModels: 0 };
  }

  const entries: Array<{score: number; weight: number}> = [];

  // Fundamental: our trained ML model — give it meaningful weight
  if (result.fundamental) {
    const sig = signalFromFundamental(result.fundamental);
    const score = sig === 'BUY' ? 1 : sig === 'SELL' ? -1 : 0;
    const weight = Math.max(0.4, result.fundamental.model_score ?? 0.5);
    entries.push({ score, weight });
  }

  // Technical: GRU ensemble policy
  if (result.technical) {
    const sig = signalFromTechnical(result.technical);
    const score = sig === 'BUY' ? 1 : sig === 'SELL' ? -1 : 0;
    const weight = (result.technical.policy?.confidence_score as number) ?? 0.6;
    entries.push({ score, weight });
  }

  // Sentiment: news AI score
  if (result.sentiment) {
    const sent = result.sentiment.overall_sentiment;
    const score = sent === 'Positive' ? 1 : sent === 'Negative' ? -1 : 0;
    const weight = result.sentiment.confidence ?? 0.6;
    entries.push({ score, weight });
  }

  if (entries.length === 0) {
    return { label: 'PENDING', confidence: 0, tone: 'neutral' as SignalTone, availableModels: 0 };
  }

  const totalWeight = entries.reduce((s, e) => s + e.weight, 0);
  const weightedScore = entries.reduce((s, e) => s + e.score * e.weight, 0) / (totalWeight || 1);

  // STRONG BUY/SELL requires at least 2 models in agreement
  const buyVotes  = entries.filter(e => e.score > 0).length;
  const sellVotes = entries.filter(e => e.score < 0).length;
  const strongBuyOk  = entries.length >= 2 && buyVotes  >= 2;
  const strongSellOk = entries.length >= 2 && sellVotes >= 2;

  // If our fundamental ML model says SELL, cap the combined signal at HOLD
  // (strong technical/sentiment should not override a clear SELL from our model)
  const fundamentalSig = result.fundamental ? signalFromFundamental(result.fundamental) : null;
  if (fundamentalSig === 'SELL') {
    const conf = Math.round(Math.min(75, (0.5 + Math.abs(weightedScore) * 0.25) * 100));
    return { label: 'HOLD', confidence: conf, tone: 'warning' as SignalTone, availableModels: entries.length };
  }

  const avgModelConf = totalWeight / entries.length;
  const confidence = Math.round(Math.min(99, (0.5 + Math.abs(weightedScore) * 0.35 + avgModelConf * 0.15) * 100));

  if (strongBuyOk  && weightedScore >  0.4) return { label: 'STRONG BUY', confidence, tone: 'success' as SignalTone, availableModels: entries.length };
  if (weightedScore >  0.1) return { label: 'BUY',    confidence, tone: 'success' as SignalTone, availableModels: entries.length };
  if (strongSellOk && weightedScore < -0.4) return { label: 'SELL',       confidence, tone: 'danger'  as SignalTone, availableModels: entries.length };
  if (weightedScore < -0.1) return { label: 'REDUCE',  confidence, tone: 'danger'  as SignalTone, availableModels: entries.length };
  return { label: 'HOLD', confidence, tone: 'warning' as SignalTone, availableModels: entries.length };
}

export default function StockAnalysisPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { addToWatchlist, removeFromWatchlist, isInWatchlist, updateEntry } = useWatchlistStore();
  const { addToHistory } = useAnalysisHistoryStore();
  const rawQueryTicker = normalizeAnyTicker(searchParams.get('ticker'));
  const queryTicker = normalizeCoverageTicker(searchParams.get('ticker'));
  const initialTicker = rawQueryTicker ?? DEFAULT_TICKER;
  const [tickerInput, setTickerInput] = useState<string>(initialTicker);
  const [activeTab, setActiveTab] = useState<AnalysisTab>('overview');
  const [status, setStatus] = useState<AnalysisStatus>(rawQueryTicker ? 'loading' : 'idle');
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<CombinedStockAnalysis | null>(null);
  const [livePrice, setLivePrice] = useState<{price: number; change: number; changePercent: number} | null>(null);

  const runAnalysis = useCallback(async (ticker: CoverageTicker) => {
    setStatus('loading');
    setError(null);
    setAnalysis(null); // clear stale data so previous ticker's charts don't show
    setTickerInput(ticker);

    const [fundamentalResult, technicalResult, sentimentResult] = await Promise.allSettled([
      fundamentalApi.analyze({
        ticker,
        market: 'US',
        include_peer_context: true,
      }),
      technicalApi.analyze({
        ticker,
        model_version: 'final_1d',
        history_bars: 90,
        forecast_bars: 7,
      }),
      sentimentApi.analyze({
        ticker,
        market: 'US',
      }),
    ]);

    const fallbackProfile = FUNDAMENTAL_PROFILES[ticker];
    const nextAnalysis: CombinedStockAnalysis = {
      ticker,
      snapshot: STOCK_SNAPSHOTS[ticker as CoverageTicker] ?? { ticker, companyName: ticker, exchange: "NASDAQ", currency: "USD", marketStatus: "—", price: 0, change: 0, changePercent: 0, preMarket: 0, marketCap: "—", revenue: "—", netIncome: "—", eps: "—", peRatio: "—", forwardPe: "—", volume: "—", weekRange: "—", beta: "—", nextEarnings: "—" },
      profile:
        fundamentalResult.status === 'fulfilled'
          ? profileFromFundamentalResponse(fundamentalResult.value)
          : fallbackProfile,
      fundamental: fundamentalResult.status === 'fulfilled' ? fundamentalResult.value : null,
      technical: technicalResult.status === 'fulfilled' ? technicalResult.value : null,
      sentiment: sentimentResult.status === 'fulfilled' ? sentimentResult.value : null,
      fundamentalError: fundamentalResult.status === 'rejected' ? handleApiError(fundamentalResult.reason) : null,
      technicalError: technicalResult.status === 'rejected' ? handleApiError(technicalResult.reason) : null,
      sentimentError: sentimentResult.status === 'rejected' ? handleApiError(sentimentResult.reason) : null,
    };

    setAnalysis(nextAnalysis);
    const succeeded = fundamentalResult.status === 'fulfilled' || nextAnalysis.technical || nextAnalysis.sentiment;
    setStatus(succeeded ? 'success' : 'error');

    // Use the same combinedRecommendation logic as the UI so watchlist stays in sync
    const rec = combinedRecommendation(nextAnalysis);
    const watchlistSignal: 'BUY' | 'SELL' | 'HOLD' =
      rec.label === 'STRONG BUY' || rec.label === 'BUY' ? 'BUY' :
      rec.label === 'SELL' || rec.label === 'REDUCE' ? 'SELL' : 'HOLD';

    const fundamentalSig = nextAnalysis.fundamental?.rating ?? 'HOLD';
    const technicalSig = (() => {
      if (!nextAnalysis.technical?.forecast_bars?.length) return 'HOLD';
      const last = nextAnalysis.technical.forecast_bars[nextAnalysis.technical.forecast_bars.length - 1];
      const move = nextAnalysis.technical.latest_price > 0 ? ((last.close - nextAnalysis.technical.latest_price) / nextAnalysis.technical.latest_price) * 100 : 0;
      return move > 0.35 ? 'BUY' : move < -0.35 ? 'SELL' : 'HOLD';
    })();
    const sentimentSig = nextAnalysis.sentiment?.overall_sentiment?.toUpperCase() ?? 'NEUTRAL';
    const snap = STOCK_SNAPSHOTS[ticker as CoverageTicker] ?? null;

    addToHistory({
      id: `${ticker}_${Date.now()}`,
      ticker,
      companyName: snap?.companyName ?? ticker,
      analyzedAt: new Date().toISOString(),
      overallRecommendation: (rec.label === 'STRONG BUY' ? 'STRONG BUY' : watchlistSignal) as 'BUY' | 'SELL' | 'HOLD' | 'STRONG BUY',
      confidence: rec.confidence,
      price: snap?.price,
      fundamentalSignal: fundamentalSig,
      technicalSignal: technicalSig,
      sentimentSignal: sentimentSig,
      sentimentScore: nextAnalysis.sentiment?.score,
      technicalMove: nextAnalysis.technical ? `${((nextAnalysis.technical.forecast_bars[nextAnalysis.technical.forecast_bars.length-1]?.close ?? nextAnalysis.technical.latest_price) - nextAnalysis.technical.latest_price >= 0 ? '+' : '')}${(((nextAnalysis.technical.forecast_bars[nextAnalysis.technical.forecast_bars.length-1]?.close ?? nextAnalysis.technical.latest_price) - nextAnalysis.technical.latest_price) / nextAnalysis.technical.latest_price * 100).toFixed(2)}%` : undefined,
    });

    // Update watchlist using the same signal as the Combined Signal display
    if (isInWatchlist(ticker)) {
      updateEntry(ticker, {
        lastSignal: watchlistSignal,
        lastPrice: snap?.price,
        lastChangePercent: snap?.changePercent,
        lastAnalyzedAt: new Date().toISOString(),
        fundamentalSignal: fundamentalSig,
        technicalSignal: technicalSig,
        sentimentSignal: sentimentSig,
      });
    }
  }, [addToHistory, isInWatchlist, updateEntry]);

  // Fetch live price for any ticker
  useEffect(() => {
    const ticker = rawQueryTicker;
    if (!ticker) return;
    const fetchPrice = async () => {
      try {
        const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
        const res = await fetch(`${API_URL}/api/market/price/${ticker}`);
        if (res.ok) {
          const data = await res.json();
          if (data.price) setLivePrice(data);
        }
      } catch {}
    };
    void fetchPrice();
    const iv = setInterval(() => void fetchPrice(), 30000);
    return () => clearInterval(iv);
  }, [rawQueryTicker]);

  useEffect(() => {
    if (rawQueryTicker) {
      void runAnalysis(rawQueryTicker as CoverageTicker);
    }
  }, [queryTicker, runAnalysis]);

  const submitTicker = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const raw = normalizeAnyTicker(tickerInput);
    if (!raw) {
      setError('Please enter a ticker symbol.');
      return;
    }
    setError(null);
    router.push(`/analyze?ticker=${raw}`);
  };

  const currentTicker = (rawQueryTicker ?? normalizeCoverageTicker(tickerInput) ?? DEFAULT_TICKER) as CoverageTicker;
  const baseSnapshot = analysis?.snapshot ?? STOCK_SNAPSHOTS[currentTicker as CoverageTicker] ?? { ticker: currentTicker, companyName: currentTicker, exchange: "NASDAQ", currency: "USD", marketStatus: "—", price: 0, change: 0, changePercent: 0, preMarket: 0, marketCap: "—", revenue: "—", netIncome: "—", eps: "—", peRatio: "—", forwardPe: "—", volume: "—", weekRange: "—", beta: "—", nextEarnings: "—" };
  const snapshot = livePrice ? { ...baseSnapshot, price: livePrice.price, change: livePrice.change, changePercent: livePrice.changePercent } : baseSnapshot;
  const profile = analysis?.profile ?? FUNDAMENTAL_PROFILES[currentTicker];
  const recommendation = combinedRecommendation(analysis);
  const priceTone = snapshot.change >= 0 ? 'text-emerald-600' : 'text-rose-600';
  const hasTicker = Boolean(rawQueryTicker);

  if (!hasTicker) {
    return (
      <div className="mx-auto max-w-5xl space-y-8">
        <EmptyAnalyzeState />
        <AnalyzeSearchCard
          tickerInput={tickerInput}
          setTickerInput={setTickerInput}
          submitTicker={submitTicker}
          currentTicker={currentTicker}
          status={status}
          error={error}
          routerPush={(ticker) => router.push(`/analyze?ticker=${ticker}`)}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <StockHeader
        snapshot={snapshot}
        profile={profile}
        recommendation={recommendation}
        status={status}
        priceTone={priceTone}
      />

      <div className="rounded-2xl bg-slate-100/70 p-2">
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {TAB_OPTIONS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              onClick={() => setActiveTab(tab.value)}
              className={cn(
                'rounded-xl px-4 py-3 text-sm font-extrabold text-slate-500 transition-all',
                activeTab === tab.value ? 'bg-white text-slate-950 shadow-card' : 'hover:bg-white/60 hover:text-slate-800'
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {status === 'loading' && (
        <Card className="border border-slate-200 bg-white" variant="bordered" padding="none">
          <CardContent className="p-8">
            <div className="flex items-center gap-4">
              <Loader2 className="animate-spin text-primary-600" size={26} />
              <div>
                <p className="text-lg font-extrabold text-slate-950">
                  Analysing {currentTicker} across Fundamental, Technical & Sentiment models...
                </p>
                <p className="mt-1 text-sm text-slate-500">The full stock view will appear as each model response is assembled.</p>
              </div>
            </div>
            <div className="mt-6 h-2 rounded-full bg-slate-100 progress-indeterminate" />
          </CardContent>
        </Card>
      )}

      {status !== 'loading' && (
        <div>
          {activeTab === 'overview' && (
            <OverviewTab
              result={analysis}
              snapshot={snapshot}
              recommendation={recommendation}
            />
          )}
          {activeTab === 'fundamental' && (
            <FundamentalTab
              result={analysis}
              profile={profile}
            />
          )}
          {activeTab === 'technical' && (
            <TechnicalTab
              analysis={analysis?.technical ?? null}
              error={analysis?.technicalError ?? null}
            />
          )}
          {activeTab === 'sentiment' && (
            <SentimentTab
              analysis={analysis?.sentiment ?? null}
              error={analysis?.sentimentError ?? null}
            />
          )}
        </div>
      )}
    </div>
  );
}

function StockHeader({
  snapshot,
  profile,
  recommendation,
  status,
  priceTone,
}: {
  snapshot: StockSnapshot;
  profile: FundamentalProfile;
  recommendation: { label: string; confidence: number; tone: SignalTone };
  status: AnalysisStatus;
  priceTone: string;
}) {
  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-4xl font-extrabold tracking-[-0.04em] text-slate-950 md:text-5xl">
              {snapshot.companyName}
            </h1>
            <span className="text-2xl font-extrabold text-slate-400">{snapshot.ticker}</span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <SignalPill label={status === 'loading' ? 'ANALYSING' : recommendation.label} tone={recommendation.tone} />
          </div>
        </div>
        <WatchlistButton
          ticker={snapshot.ticker}
          companyName={snapshot.companyName}
          signal={status === 'success' ? recommendation.label : undefined}
          price={snapshot.price}
          changePercent={snapshot.changePercent}
        />
      </div>

      <div>
        <div className="flex flex-wrap items-end gap-3">
          <p className="text-5xl font-extrabold tracking-[-0.04em] text-slate-950">{formatMoney(snapshot.price)}</p>
          <p className={cn('pb-2 text-xl font-extrabold', priceTone)}>
            {snapshot.change >= 0 ? '+' : ''}{snapshot.change.toFixed(2)} ({formatSignedPercent(snapshot.changePercent)})
          </p>
        </div>
      </div>
    </section>
  );
}

function AnalyzeSearchCard({
  tickerInput,
  setTickerInput,
  submitTicker,
  currentTicker,
  status,
  error,
  routerPush,
}: {
  tickerInput: string;
  setTickerInput: (value: string) => void;
  submitTicker: (event: FormEvent<HTMLFormElement>) => void;
  currentTicker: CoverageTicker;
  status: AnalysisStatus;
  error: string | null;
  routerPush: (ticker: CoverageTicker) => void;
}) {
  return (
    <Card className="border border-slate-200" variant="bordered" padding="none">
      <CardContent className="p-4 sm:p-5">
        <form onSubmit={submitTicker} className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="flex flex-1 items-center gap-3 rounded-full border border-slate-200 bg-white px-4 py-3">
            <Search size={18} className="shrink-0 text-slate-400" />
            <input
              value={tickerInput}
              onChange={(event) => setTickerInput(event.target.value.toUpperCase())}
              placeholder="Enter ticker"
              className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-slate-900 outline-none placeholder:text-slate-400"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {COVERAGE_TICKERS.map((ticker) => (
              <button
                key={ticker}
                type="button"
                onClick={() => routerPush(ticker)}
                className={cn(
                  'rounded-full border px-3 py-2 text-xs font-extrabold transition-all',
                  ticker === currentTicker
                    ? 'border-primary-600 bg-primary-600 text-white'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-primary-200 hover:text-primary-700'
                )}
              >
                {ticker}
              </button>
            ))}
          </div>
          <Button type="submit" isLoading={status === 'loading'} className="md:min-w-[160px]">
            Analyse
          </Button>
        </form>
        {error && <p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">{error}</p>}
      </CardContent>
    </Card>
  );
}

function OverviewTab({
  result,
  snapshot,
  recommendation,
}: {
  result: CombinedStockAnalysis | null;
  snapshot: StockSnapshot;
  recommendation: { label: string; confidence: number; tone: SignalTone };
}) {
  // Build plain-English reasons for each model signal
  const fundamentalSignal = signalFromFundamental(result?.fundamental ?? null);
  const technicalSignal = signalFromTechnical(result?.technical ?? null);
  const sentimentSignal = signalFromSentiment(result?.sentiment ?? null);

  const fundamentalReason = result?.fundamental
    ? result.fundamental.analysis_summary?.slice(0, 120) + '...'
    : result?.fundamentalError
    ? 'Model artifact not available — showing profile data.'
    : 'Run analysis to get the fundamental signal.';

  const technicalReason = result?.technical
    ? (() => {
        const last = result.technical.forecast_bars[result.technical.forecast_bars.length - 1];
        const move = last ? ((last.close - result.technical.latest_price) / result.technical.latest_price * 100) : 0;
        return `Model projects a ${move >= 0 ? '+' : ''}${move.toFixed(2)}% move over ${result.technical.forecast_bars.length} bars using the GRU ensemble.`;
      })()
    : result?.technicalError
    ? 'Live price data unavailable — Alpaca API key required.'
    : 'Run analysis to get the technical signal.';

  const sentimentReason = result?.sentiment
    ? result.sentiment.analysis_summary?.slice(0, 120) + '...'
    : result?.sentimentError
    ? 'News data unavailable for this ticker.'
    : 'Run analysis to get the sentiment signal.';

  const recColors = {
    success: 'bg-emerald-500',
    warning: 'bg-amber-400',
    danger: 'bg-rose-500',
    neutral: 'bg-slate-400',
  };

  return (
    <div className="space-y-5">
      {/* Live Chart - Full Width */}
      <Card className="border border-slate-200" variant="bordered" padding="none">
        <CardContent className="p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-extrabold text-slate-950">Price Chart</h2>
            <span className="text-xs text-slate-400">Real-time · TradingView</span>
          </div>
          <TradingViewChart ticker={snapshot.ticker} height={380} />
        </CardContent>
      </Card>

      {/* Combined Recommendation */}
      <div className="grid gap-5 lg:grid-cols-[1.2fr_0.8fr]">
        {/* 3 Model Signals with reasons */}
        <Card className="border border-slate-200" variant="bordered" padding="none">
          <CardContent className="p-6">
            <h2 className="text-lg font-extrabold text-slate-950">FinEdge Analysis</h2>
            <p className="mt-1 text-xs text-slate-500">Three independent models, one combined recommendation.</p>
            <div className="mt-5 space-y-4">
              {/* Fundamental */}
              <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-100">
                      <Building2 size={13} className="text-blue-600" />
                    </div>
                    <span className="text-sm font-bold text-slate-950">Fundamental</span>
                  </div>
                  <SignalPill label={fundamentalSignal} tone={toneFromSignal(fundamentalSignal)} />
                </div>
                <p className="text-xs leading-5 text-slate-500">{fundamentalReason}</p>
              </div>

              {/* Technical */}
              <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-violet-100">
                      <CandlestickChart size={13} className="text-violet-600" />
                    </div>
                    <span className="text-sm font-bold text-slate-950">Technical</span>
                  </div>
                  <SignalPill label={technicalSignal} tone={toneFromSignal(technicalSignal)} />
                </div>
                <p className="text-xs leading-5 text-slate-500">{technicalReason}</p>
              </div>

              {/* Sentiment */}
              <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-100">
                      <Newspaper size={13} className="text-amber-600" />
                    </div>
                    <span className="text-sm font-bold text-slate-950">Sentiment</span>
                  </div>
                  <SignalPill label={sentimentSignal} tone={toneFromSignal(sentimentSignal)} />
                </div>
                <p className="text-xs leading-5 text-slate-500">{sentimentReason}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Combined verdict + market data */}
        <div className="space-y-5">
          {/* Verdict card */}
          <Card className="border border-slate-200" variant="bordered" padding="none">
            <CardContent className="p-6">
              <p className="text-xs font-bold uppercase tracking-widest text-slate-500">Combined Signal</p>
              <div className="mt-3 flex items-end justify-between">
                <div>
                  <p className={cn(
                    'text-4xl font-extrabold tracking-tight',
                    recommendation.tone === 'success' ? 'text-emerald-600' :
                    recommendation.tone === 'danger' ? 'text-rose-600' :
                    recommendation.tone === 'warning' ? 'text-amber-600' : 'text-slate-600'
                  )}>
                    {recommendation.label}
                  </p>
                  <p className="mt-1 text-sm text-slate-500">{recommendation.confidence}% confidence</p>
                </div>
                <div className="text-right">
                  <p className="text-3xl font-extrabold text-slate-950">${snapshot.price > 0 ? snapshot.price.toFixed(2) : '—'}</p>
                  <p className={cn('text-sm font-bold', snapshot.changePercent >= 0 ? 'text-emerald-600' : 'text-rose-600')}>
                    {snapshot.changePercent >= 0 ? '+' : ''}{snapshot.changePercent.toFixed(2)}%
                  </p>
                </div>
              </div>
              <div className="mt-4 h-2 rounded-full bg-slate-100">
                <div
                  className={cn('h-full rounded-full transition-all', recColors[recommendation.tone])}
                  style={{ width: `${recommendation.confidence}%` }}
                />
              </div>
            </CardContent>
          </Card>

          {/* Key stats */}
          <Card className="border border-slate-200" variant="bordered" padding="none">
            <CardContent className="p-5">
              <p className="text-xs font-bold uppercase tracking-widest text-slate-500 mb-3">Key Data</p>
              <div className="divide-y divide-slate-100">
                <DataRow label="Market Cap" value={snapshot.marketCap} />
                <DataRow label="P/E Ratio" value={snapshot.peRatio} />
                <DataRow label="Forward P/E" value={snapshot.forwardPe} />
                <DataRow label="52-Week Range" value={snapshot.weekRange} />
                <DataRow label="Volume" value={snapshot.volume} />
                <DataRow label="Next Earnings" value={snapshot.nextEarnings} />
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* About the Company — for covered tickers */}
      {COMPANY_ABOUT[snapshot.ticker] && (
        <Card className="border border-slate-200" variant="bordered" padding="none">
          <CardContent className="p-5">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">About {snapshot.companyName}</p>
            <p className="text-sm leading-6 text-slate-600 mb-4">{COMPANY_ABOUT[snapshot.ticker]!.description}</p>
            <div className="grid gap-2 sm:grid-cols-3">
              {COMPANY_ABOUT[snapshot.ticker]!.segments.map((seg, i) => (
                <div key={i} className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5">
                  <p className="text-xs font-semibold text-slate-700 leading-5">{seg}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

interface YFStats {
  market_cap?: string; pe_ratio?: number; forward_pe?: number; peg_ratio?: number;
  ps_ratio?: number; pb_ratio?: number; ev_ebitda?: number;
  roe?: number; roa?: number; gross_margin?: number; operating_margin?: number;
  net_margin?: number; revenue_growth?: number; earnings_growth?: number;
  debt_to_equity?: number; current_ratio?: number; quick_ratio?: number;
  beta?: number; week_52_high?: number; week_52_low?: number; avg_volume?: number;
  shares_outstanding?: string; dividend_yield?: number; forward_eps?: number;
  total_cash?: string; total_debt?: string; free_cashflow?: string;
  revenue?: string; net_income?: string; analyst_target?: number;
  analyst_rating?: string; sector?: string; industry?: string;
}

function FundamentalTab({ result, profile }: { result: CombinedStockAnalysis | null; profile: FundamentalProfile }) {
  const f = result?.fundamental ?? null;
  const snap = result?.snapshot;
  const error = result?.fundamentalError;
  const ticker = result?.snapshot?.ticker ?? profile.ticker;

  const [stats, setStats] = useState<YFStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [features, setFeatures] = useState<Record<string, number | string | null> | null>(null);

  useEffect(() => {
    if (!ticker) return;
    setStatsLoading(true);
    const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
    Promise.all([
      fetch(`${API_URL}/api/market/stats/${ticker}`).then(r => r.ok ? r.json() : null),
      fetch(`${API_URL}/api/market/fundamentals-features/${ticker}`).then(r => r.ok ? r.json() : null),
    ]).then(([statsData, featuresData]) => {
      if (statsData && !statsData.error) setStats(statsData);
      if (featuresData && !featuresData.error) setFeatures(featuresData);
    }).catch(() => {}).finally(() => setStatsLoading(false));
  }, [ticker]);

  // Prioritise: model key_metrics → yfinance stats → snapshot
  const n = (v: number | null | undefined, decimals = 2) =>
    v != null ? v.toFixed(decimals) : null;
  const pct = (v: number | null | undefined, alreadyPct = false) =>
    v != null ? `${alreadyPct ? v.toFixed(1) : (v * 100).toFixed(1)}%` : null;

  // features.csv is our ML training dataset — use it as primary source for all ratios
  // Priority: live API features → static snapshot from features.csv → yfinance → hardcoded snapshot
  const staticData = STATIC_FEATURES[ticker] ?? null;

  const fromFeat = (key: string, isPercent = false): string | null => {
    // Check live API first, then static fallback
    const v = features?.[key] ?? staticData?.[key] ?? null;
    if (v == null) return null;
    const num = Number(v);
    if (isNaN(num) || !isFinite(num)) return null;
    if (isPercent) return `${(num * 100).toFixed(1)}%`;
    if (Math.abs(num) > 100) return num.toFixed(1);
    if (Math.abs(num) > 10) return num.toFixed(2);
    return num.toFixed(2);
  };

  const fmtLargeNum = (v: number | null | undefined): string | null => {
    if (v == null || isNaN(Number(v))) return null;
    const n2 = Number(v);
    if (Math.abs(n2) >= 1e12) return `$${(n2/1e12).toFixed(2)}T`;
    if (Math.abs(n2) >= 1e9)  return `$${(n2/1e9).toFixed(2)}B`;
    if (Math.abs(n2) >= 1e6)  return `$${(n2/1e6).toFixed(2)}M`;
    return `$${n2.toLocaleString()}`;
  };

  // Priority: features.csv → model key_metrics → yfinance stats → snapshot hardcoded
  const pe    = fromFeat('pe_ratio') ?? n(f?.key_metrics?.pe_ratio) ?? n(stats?.pe_ratio) ?? snap?.peRatio ?? '—';
  const fwdPe = n(stats?.forward_pe) ?? snap?.forwardPe ?? '—';
  const roe   = fromFeat('roe', true) ?? pct(f?.key_metrics?.roe) ?? (stats?.roe != null ? `${stats.roe}%` : null) ?? '—';
  const roa   = fromFeat('roa', true) ?? (stats?.roa != null ? `${stats.roa}%` : null) ?? '—';
  const roic  = fromFeat('roic', true) ?? '—';
  const de    = fromFeat('debt_to_equity') ?? n(f?.key_metrics?.debt_to_equity) ?? n(stats?.debt_to_equity) ?? '—';
  const fcfM  = fromFeat('fcf_margin', true) ?? pct(f?.key_metrics?.free_cash_flow_margin) ?? '—';
  const revG  = fromFeat('revenue_growth_yoy', true) ?? pct(f?.key_metrics?.revenue_growth_yoy) ?? (stats?.revenue_growth != null ? `${stats.revenue_growth}%` : null) ?? '—';
  const earnG = fromFeat('earnings_growth_yoy', true) ?? pct(f?.key_metrics?.earnings_growth_yoy) ?? (stats?.earnings_growth != null ? `${stats.earnings_growth}%` : null) ?? '—';
  const fcfG  = fromFeat('fcf_growth_yoy', true) ?? '—';
  const mktCap = stats?.market_cap ?? snap?.marketCap ?? '—';
  const beta   = n(stats?.beta) ?? snap?.beta ?? '—';
  const gm     = fromFeat('gross_margin', true) ?? (stats?.gross_margin != null ? `${stats.gross_margin}%` : null) ?? '—';
  const opM    = fromFeat('operating_margin', true) ?? (stats?.operating_margin != null ? `${stats.operating_margin}%` : null) ?? '—';
  const netM   = fromFeat('net_margin', true) ?? (stats?.net_margin != null ? `${stats.net_margin}%` : null) ?? '—';
  const curr   = fromFeat('current_ratio') ?? n(stats?.current_ratio) ?? '—';
  const divY   = stats?.dividend_yield != null ? `${stats.dividend_yield}%` : '—';
  const ps     = fromFeat('ps_ratio') ?? n(stats?.ps_ratio) ?? '—';
  const pb     = fromFeat('pb_ratio') ?? n(stats?.pb_ratio) ?? '—';
  const evEb   = fromFeat('ev_ebitda') ?? n(stats?.ev_ebitda) ?? '—';
  const peg    = n(stats?.peg_ratio) ?? '—';
  const fcfYld = fromFeat('fcf_yield', true) ?? '—';
  const intCov = fromFeat('interest_coverage') ?? '—';
  const netDe  = fromFeat('net_debt_ebitda') ?? '—';
  // Balance sheet $ values: features.csv has raw dollar amounts
  const totalCash = stats?.total_cash
    ?? fmtLargeNum(features?.cash != null ? Number(features.cash) : staticData?.cash)
    ?? '—';
  const totalDebt = stats?.total_debt
    ?? fmtLargeNum(features?.total_debt_raw != null ? Number(features.total_debt_raw) : staticData?.total_debt_raw)
    ?? '—';
  const freeCF = stats?.free_cashflow
    ?? fmtLargeNum(features?.fcf_ttm != null ? Number(features.fcf_ttm) : staticData?.fcf_ttm)
    ?? '—';

  // User-friendly model rank text — only show when rank is genuinely impressive
  const rankText = (() => {
    if (!f?.universe_percentile) return null;
    const pctVal = Math.round(f.universe_percentile * 100);
    const rank = f?.relative_rank;
    if (pctVal >= 95) return `Our model's top-rated stock — beats ${pctVal}% of everything we track`;
    if (pctVal >= 80) return `Highly ranked — better than ${pctVal}% of stocks our model covers`;
    if (pctVal >= 60) return `Above average among the stocks our model tracks`;
    if (pctVal >= 40) return `Mid-tier — roughly average among tracked stocks`;
    if (rank != null && rank <= 3) return `Top ${rank} stock in our current model coverage`;
    return null; // don't show for low-ranked stocks — it's confusing
  })();

  const signalDate = (() => {
    const d = f?.source_signal_date;
    if (!d || d.length !== 8) return d ?? null;
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[parseInt(d.slice(4,6))-1]} ${parseInt(d.slice(6,8))}, ${d.slice(0,4)}`;
  })();

  const trendColor = (trend: string) => {
    if (trend === 'Improving') return 'text-emerald-600';
    if (trend === 'Declining') return 'text-rose-600';
    return 'text-slate-500';
  };

  const trendPlain = (trend: string) => {
    if (trend === 'Improving') return '↑ Growing';
    if (trend === 'Declining') return '↓ Shrinking';
    if (trend === 'Stable') return '→ Stable';
    return null; // Unknown = don't show
  };

  return (
    <div className="space-y-5">
      {/* Model Signal Banner */}
      {f ? (
        <Card className="border border-slate-200 bg-gradient-to-r from-blue-50 to-slate-50" variant="bordered" padding="none">
          <CardContent className="p-5">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-3">FinEdge Model Verdict</p>
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <SignalPill label={f.signal} tone={toneFromSignal(f.signal)} />
                  <p className="text-2xl font-extrabold text-slate-950">
                    {f.score.toFixed(1)}<span className="text-sm font-semibold text-slate-400">/10</span>
                  </p>
                  <p className="text-xs text-slate-400">model quality score</p>
                </div>
                {rankText && (
                  <p className="text-sm font-semibold text-blue-700 mb-2">{rankText}</p>
                )}
              </div>
              {f.relative_rank != null && (
                <div className="text-right space-y-1 text-sm">
                  <p className="text-xs text-slate-400 uppercase tracking-wide">Model Rank</p>
                  <p className="text-xl font-extrabold text-slate-900">#{f.relative_rank}</p>
                  <p className="text-xs text-slate-400">out of stocks we track</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
          {error ?? 'This stock isn\'t covered by our fundamental model yet.'}
        </div>
      )}

      {/* Top stat tiles — live from Yahoo Finance */}
      <div className="grid gap-3 grid-cols-2 md:grid-cols-4">
        <StatTile label="Market Cap" value={mktCap} />
        <StatTile label="P/E Ratio" value={String(pe)} />
        <StatTile label="Revenue Growth" value={revG} />
        <StatTile label="Return on Equity" value={roe} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Valuation */}
        <Card className="border border-slate-200" variant="bordered" padding="none">
          <CardContent className="p-5">
            <SectionTitle title="Valuation" subtitle="How the market is pricing this stock" />
            <div className="mt-4 divide-y divide-slate-100">
              {([
                ['Price / Earnings (P/E)', pe, 'Lower = cheaper relative to profits'],
                ['Forward P/E', fwdPe, 'Based on next year\'s expected earnings'],
                ['Price / Sales', ps, 'How much you pay per $1 of revenue'],
                ['Price / Book', pb, 'Stock price vs company\'s net assets'],
                ['EV / EBITDA', evEb, 'Enterprise value vs operating profit'],
                ['PEG Ratio', peg, 'P/E adjusted for growth — under 1 is cheap'],
                ['FCF Yield', fcfYld, 'Free cash flow per share ÷ price — higher is better'],
              ] as [string,string,string][]).map(([label, val, hint]) => (
                <div key={label} className="flex items-center justify-between py-2.5 group">
                  <div>
                    <span className="text-sm text-slate-700">{label}</span>
                    <p className="text-xs text-slate-400 hidden group-hover:block">{hint}</p>
                  </div>
                  <span className="text-sm font-bold text-slate-950">{val}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Profitability */}
        <Card className="border border-slate-200" variant="bordered" padding="none">
          <CardContent className="p-5">
            <SectionTitle title="Profitability" subtitle="How much of revenue becomes profit" />
            <div className="mt-4 divide-y divide-slate-100">
              {([
                ['Gross Margin', gm, 'Revenue left after cost of goods'],
                ['Operating Margin', opM, 'Profit from core business operations'],
                ['Net Margin', netM, 'Final take-home profit %'],
                ['Return on Equity (ROE)', roe, 'How well the company uses shareholder money'],
                ['Return on Assets (ROA)', roa, 'Profit per dollar of assets'],
                ['Return on Invested Capital', roic, 'Efficiency of capital allocation'],
                ['Revenue Growth (YoY)', revG, 'Revenue vs same period last year'],
                ['Earnings Growth (YoY)', earnG, 'Earnings vs same period last year'],
                ['FCF Growth (YoY)', fcfG, 'Free cash flow growth year over year'],
              ] as [string,string,string][]).map(([label, val, hint]) => (
                <div key={label} className="flex items-center justify-between py-2.5 group">
                  <div>
                    <span className="text-sm text-slate-700">{label}</span>
                    <p className="text-xs text-slate-400 hidden group-hover:block">{hint}</p>
                  </div>
                  <span className="text-sm font-bold text-slate-950">{val}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Financial Health */}
        <Card className="border border-slate-200" variant="bordered" padding="none">
          <CardContent className="p-5">
            <SectionTitle title="Financial Health" subtitle="Balance sheet strength" />
            <div className="mt-4 divide-y divide-slate-100">
              {([
                ['Total Cash', totalCash, 'Cash and equivalents on hand'],
                ['Total Debt', totalDebt, 'All borrowings'],
                ['Free Cash Flow (TTM)', freeCF, 'Cash generated after capex'],
                ['FCF Margin', fcfM, 'Free cash flow as % of revenue'],
                ['Debt / Equity', de, 'Under 1 = more equity than debt (healthy)'],
                ['Current Ratio', curr, 'Over 1 = can cover short-term debts'],
                ['Net Debt / EBITDA', netDe, 'Negative = net cash (very healthy)'],
                ['Interest Coverage', intCov, 'How many times earnings cover interest'],
                ['Dividend Yield', divY, 'Annual dividend as % of stock price'],
              ] as [string,string,string][]).map(([label, val, hint]) => (
                <div key={label} className="flex items-center justify-between py-2.5 group">
                  <div>
                    <span className="text-sm text-slate-700">{label}</span>
                    <p className="text-xs text-slate-400 hidden group-hover:block">{hint}</p>
                  </div>
                  <span className="text-sm font-bold text-slate-950">{val}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Model Trends + Stock Stats */}
        <Card className="border border-slate-200" variant="bordered" padding="none">
          <CardContent className="p-5">
            {f?.trends && Object.entries(f.trends).some(([,t]) => trendPlain(t) !== null) ? (
              <>
                <SectionTitle title="Model Trend Assessment" subtitle="Is this company growing or shrinking?" />
                <div className="mt-4 space-y-3">
                  {Object.entries(f.trends).map(([key, trend]) => {
                    const label = trendPlain(trend);
                    if (!label) return null;
                    return (
                      <div key={key} className="flex items-center justify-between rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5">
                        <span className="text-sm text-slate-700 capitalize">{key.replace(/_/g, ' ')}</span>
                        <span className={`text-sm font-bold ${trendColor(trend)}`}>{label}</span>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : (
              <>
                <SectionTitle title="Stock Statistics" subtitle="Price and trading info" />
                <div className="mt-4 divide-y divide-slate-100">
                  {([
                    ['Beta', String(beta), 'Over 1 = more volatile than the market'],
                    ['52-Week High', stats?.week_52_high != null ? `$${stats.week_52_high.toFixed(2)}` : (snap?.weekRange ?? '—'), ''],
                    ['52-Week Low', stats?.week_52_low != null ? `$${stats.week_52_low.toFixed(2)}` : '—', ''],
                    ['Avg Volume', stats?.avg_volume != null ? stats.avg_volume.toLocaleString() : '—', 'Average daily shares traded'],
                    ['Forward EPS', stats?.forward_eps != null ? `$${stats.forward_eps.toFixed(2)}` : '—', 'Expected earnings per share'],
                  ] as [string,string,string][]).map(([label, val]) => (
                    <div key={label} className="flex items-center justify-between py-2.5">
                      <span className="text-sm text-slate-700">{label}</span>
                      <span className="text-sm font-bold text-slate-950">{val}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Model Strengths & Concerns */}
      {f && (f.strengths?.length > 0 || f.concerns?.length > 0) && (
        <div className="grid gap-5 lg:grid-cols-2">
          {f.strengths?.length > 0 && (
            <Card className="border border-emerald-200 bg-emerald-50/40" variant="bordered" padding="none">
              <CardContent className="p-5">
                <SectionTitle title="Why the model likes it" subtitle="Positive signals detected" />
                <ul className="mt-4 space-y-2">
                  {f.strengths.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                      <span className="mt-0.5 text-emerald-500 font-bold">✓</span>{s}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
          {f.concerns?.length > 0 && (
            <Card className="border border-amber-200 bg-amber-50/40" variant="bordered" padding="none">
              <CardContent className="p-5">
                <SectionTitle title="Things to watch" subtitle="Risks flagged by the model" />
                <ul className="mt-4 space-y-2">
                  {f.concerns.map((c, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-slate-700">
                      <span className="mt-0.5 text-amber-500 font-bold">!</span>{c}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
        {statsLoading ? 'Loading live data...' : (
          <>
            {f && <><span className="font-bold text-slate-700">FinEdge ML model</span> signal · </>}
            <span className="font-bold text-slate-700">Yahoo Finance</span> live financials
            {stats?.sector && ` · ${stats.sector}`}{stats?.industry && ` · ${stats.industry}`}
          </>
        )}
      </div>

      {/* ML Model Feature Scores — from features.csv */}
      {(features || staticData) && (
        <Card className="border border-blue-100 bg-blue-50/30" variant="bordered" padding="none">
          <CardContent className="p-5">
            <p className="text-xs font-bold uppercase tracking-widest text-blue-600 mb-4">ML Model Feature Scores</p>
            <p className="text-xs text-slate-500 mb-4">These are the actual features our fundamental model was trained on — from the features.csv training dataset.</p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: 'Piotroski F-Score', key: 'piotroski_score', max: 9, unit: '/9', hint: '≥7 = financially healthy', isPercent: false },
                { label: 'Analyst Bull %', key: 'analyst_bull_score', max: 1, unit: '%', hint: 'Analysts with Buy ratings', isPercent: true },
                { label: 'Short Interest', key: 'short_interest_pct', max: 0.3, unit: '%', hint: 'Lower = less bearish pressure', isPercent: true, reverse: true },
                { label: 'FCF Yield', key: 'fcf_yield', max: 0.1, unit: '%', hint: 'Free cash flow ÷ market cap', isPercent: true },
              ].map(({ label, key, max, unit, hint, isPercent, reverse }) => {
                const rawVal = features?.[key] ?? staticData?.[key];
                if (rawVal == null) return null;
                const numVal = Number(rawVal);
                const displayVal = isPercent ? numVal * 100 : numVal;
                const barPct = Math.min(100, Math.max(0, (numVal / max) * 100));
                const isGood = reverse ? numVal / max <= 0.4 : numVal / max >= 0.6;
                return (
                  <div key={label} className="rounded-xl border border-blue-100 bg-white p-3">
                    <p className="text-xs font-semibold text-slate-700">{label}</p>
                    <p className="text-lg font-extrabold text-slate-950 mt-1">{displayVal.toFixed(1)}{unit}</p>
                    <div className="mt-2 h-1.5 rounded-full bg-slate-100 overflow-hidden">
                      <div className={`h-full rounded-full ${isGood ? 'bg-emerald-500' : 'bg-amber-400'}`} style={{ width: `${barPct}%` }} />
                    </div>
                    <p className="text-xs text-slate-400 mt-1">{hint}</p>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-slate-400 mt-3">
              {features?.snapshot_date ? `Live data snapshot: ${String(features.snapshot_date)}` : 'Snapshot: Jun 2025 features dataset'}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function TechnicalTab({ analysis, error }: { analysis: TechnicalAnalysisResponse | null; error: string | null }) {
  const lastForecast = analysis?.forecast_bars[analysis.forecast_bars.length - 1];
  const movePct = analysis && lastForecast ? ((lastForecast.close - analysis.latest_price) / analysis.latest_price) * 100 : 0;
  const direction = movePct >= 0 ? 'UP' : 'DOWN';

  if (!analysis) {
    return (
      <div className="space-y-4">
        <ErrorCard message={error ?? 'Technical analysis is unavailable for this stock.'} />
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
          The GRU ensemble model currently has a trained artifact for <span className="font-bold text-slate-700">MSFT</span>. Other tickers will show this error until artifacts are generated. The technical signal for MSFT returns a real LONG/FLAT/SHORT stance with 7-bar forecast.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* GRU Forecast Chart — primary output, shown first */}
      <Card className="border border-slate-200" variant="bordered" padding="none">
        <CardContent className="p-6">
          <div className="flex items-center justify-between mb-1">
            <SectionTitle title="GRU Ensemble Forecast" subtitle="Historical price + 7-bar model projection" />
            <SignalPill label={direction} tone={direction === 'UP' ? 'success' : 'danger'} />
          </div>
          <MiniForecastChart technical={analysis} tall />
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="border border-slate-200" variant="bordered" padding="none">
          <CardContent className="p-6">
            <p className="text-sm font-semibold text-slate-500">Price Direction Prediction</p>
            <div className="mt-4 flex items-center gap-4">
              <SignalPill label={direction} tone={direction === 'UP' ? 'success' : 'danger'} />
              <p className="text-4xl font-extrabold text-slate-950">{Math.abs(movePct).toFixed(2)}%</p>
              <p className="font-bold text-slate-500">projected move</p>
            </div>
          </CardContent>
        </Card>

        <Card className="border border-slate-200" variant="bordered" padding="none">
          <CardContent className="p-6">
            <p className="text-sm font-semibold text-slate-500">Policy Overlay</p>
            <div className="mt-4 flex items-end justify-between gap-4">
              <div>
                <p className="text-2xl font-extrabold text-slate-950">{String(analysis.policy.stance ?? 'MODEL')}</p>
                <p className="text-sm font-semibold text-slate-500">{analysis.data_source}</p>
              </div>
              <p className="text-2xl font-extrabold text-slate-950">
                {typeof analysis.policy.recommended_position_pct === 'number'
                  ? `${(analysis.policy.recommended_position_pct * 100).toFixed(0)}%`
                  : 'N/A'}
              </p>
            </div>
            <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-emerald-500"
                style={{ width: `${Math.max(8, Math.min(100, Number(analysis.policy.recommended_position_pct ?? 0) * 100))}%` }}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="border border-slate-200" variant="bordered" padding="none">
        <CardContent className="p-6">
          <SectionTitle title="Model Ensemble Breakdown" subtitle="Individual model weights before policy overlay" />
          <div className="mt-5 divide-y divide-slate-100">
            {Object.entries(analysis.ensemble_weights).map(([model, weight]) => (
              <DataRow key={model} label={analysis.expert_versions[model] ?? model} value={`${(weight * 100).toFixed(1)}%`} />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function SentimentTab({ analysis, error }: { analysis: SentimentalAnalysisResponse | null; error: string | null }) {
  if (!analysis) {
    return <ErrorCard message={error ?? 'Sentiment analysis is unavailable for this stock.'} />;
  }

  const b = analysis.news_breakdown;
  const positivePct = b.article_count > 0 ? Math.round((b.positive_count / b.article_count) * 100) : 0;
  const negativePct = b.article_count > 0 ? Math.round((b.negative_count / b.article_count) * 100) : 0;
  const neutralPct  = b.article_count > 0 ? Math.round((b.neutral_count  / b.article_count) * 100) : 0;

  const sentimentColor = analysis.overall_sentiment === 'Positive' ? 'text-emerald-600'
    : analysis.overall_sentiment === 'Negative' ? 'text-rose-600' : 'text-amber-600';

  return (
    <div className="space-y-5">
      {/* Top summary row */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card className="border border-slate-200" variant="bordered" padding="none">
          <CardContent className="p-5 text-center">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Overall Sentiment</p>
            <p className={`text-3xl font-extrabold ${sentimentColor}`}>{analysis.overall_sentiment}</p>
            <p className="mt-1 text-xs text-slate-400">based on {b.article_count} articles</p>
          </CardContent>
        </Card>
        <Card className="border border-slate-200" variant="bordered" padding="none">
          <CardContent className="p-5 text-center">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Sentiment Score</p>
            <p className={`text-3xl font-extrabold ${sentimentColor}`}>{analysis.score.toFixed(2)}</p>
            <p className="mt-1 text-xs text-slate-400">-1 (very negative) to +1 (very positive)</p>
          </CardContent>
        </Card>
        <Card className="border border-slate-200" variant="bordered" padding="none">
          <CardContent className="p-5 text-center">
            <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-2">Model Confidence</p>
            <p className="text-3xl font-extrabold text-slate-950">{Math.round(analysis.confidence * 100)}%</p>
            <p className="mt-1 text-xs text-slate-400">trend: {analysis.trend}</p>
          </CardContent>
        </Card>
      </div>

      {/* Article breakdown bar */}
      <Card className="border border-slate-200" variant="bordered" padding="none">
        <CardContent className="p-5">
          <p className="text-sm font-bold text-slate-700 mb-3">News Breakdown — {b.article_count} articles analyzed</p>
          <div className="flex h-4 rounded-full overflow-hidden mb-3">
            {positivePct > 0 && <div className="bg-emerald-500 transition-all" style={{ width: `${positivePct}%` }} />}
            {neutralPct  > 0 && <div className="bg-amber-400 transition-all"  style={{ width: `${neutralPct}%` }} />}
            {negativePct > 0 && <div className="bg-rose-500 transition-all"   style={{ width: `${negativePct}%` }} />}
          </div>
          <div className="flex gap-5 text-sm">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-emerald-500 inline-block" /><span className="font-bold text-emerald-700">{b.positive_count}</span> positive ({positivePct}%)</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-amber-400 inline-block" /><span className="font-bold text-amber-700">{b.neutral_count}</span> neutral ({neutralPct}%)</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-rose-500 inline-block" /><span className="font-bold text-rose-700">{b.negative_count}</span> negative ({negativePct}%)</span>
          </div>
        </CardContent>
      </Card>

      {/* Article list — stockanalysis.com style */}
      <Card className="border border-slate-200" variant="bordered" padding="none">
        <CardContent className="p-0">
          <div className="px-5 py-4 border-b border-slate-100">
            <p className="font-extrabold text-slate-950">News Articles</p>
            <p className="text-xs text-slate-400 mt-0.5">AI-scored articles driving the sentiment signal</p>
          </div>
          <div className="divide-y divide-slate-100">
            {analysis.influential_articles.map((article, i) => (
              <div key={i} className="px-5 py-4 hover:bg-slate-50/60 transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    {article.url ? (
                      <a href={article.url} target="_blank" rel="noopener noreferrer"
                        className="font-bold text-slate-950 hover:text-blue-600 transition-colors leading-snug block">
                        {article.title}
                      </a>
                    ) : (
                      <p className="font-bold text-slate-950 leading-snug">{article.title}</p>
                    )}
                    {article.source && (
                      <p className="text-xs text-slate-400 mt-1">{article.source}</p>
                    )}
                    <p className="text-sm text-slate-500 mt-2 leading-relaxed">{article.reasoning}</p>
                  </div>
                  <div className="flex-shrink-0">
                    <SignalPill label={article.verdict} tone={toneFromSignal(article.verdict)} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {analysis.analysis_summary && (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500 leading-5">
          {analysis.analysis_summary}
        </div>
      )}
    </div>
  );
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <p className="font-semibold text-slate-500">{label}</p>
      <p className="text-right font-extrabold text-slate-950">{value}</p>
    </div>
  );
}

function RecommendationRow({ label, value }: { label: string; value: string }) {
  const tone = toneFromSignal(value);
  return (
    <div className="flex items-center justify-between gap-4">
      <p className="font-semibold text-slate-500">{label}</p>
      <SignalPill label={value} tone={tone} />
    </div>
  );
}

function SignalPill({ label, tone }: { label: string; tone: SignalTone }) {
  const styles: Record<SignalTone, string> = {
    success: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    warning: 'border-amber-200 bg-amber-50 text-amber-700',
    danger: 'border-rose-200 bg-rose-50 text-rose-700',
    neutral: 'border-slate-200 bg-slate-100 text-slate-700',
  };

  return (
    <span className={cn('inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-extrabold', styles[tone])}>
      <Circle size={7} fill="currentColor" />
      {label}
    </span>
  );
}

function SectionTitle({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div>
      <h2 className="text-xl font-extrabold text-slate-950">{title}</h2>
      <p className="mt-1 text-sm leading-6 text-slate-500">{subtitle}</p>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5">
      <p className="text-sm font-semibold text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-extrabold text-slate-950">{value}</p>
    </div>
  );
}

function MetricBar({ label, value, percent, status }: { label: string; value: string; percent: number; status: string }) {
  return (
    <div className="grid gap-3 py-3 md:grid-cols-[1fr_110px_1.2fr_120px] md:items-center">
      <p className="font-semibold text-slate-600">{label}</p>
      <p className="font-extrabold text-slate-950">{value}</p>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.max(8, Math.min(100, percent))}%` }} />
      </div>
      <p className="text-sm font-bold text-emerald-600">{status}</p>
    </div>
  );
}

function HealthRow({ label, detail, value, badge }: { label: string; detail: string; value: string; badge: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-extrabold text-slate-950">{label}</p>
          <p className="mt-1 text-sm text-slate-500">{detail}</p>
        </div>
        <div className="text-right">
          <p className="text-xl font-extrabold text-slate-950">{value}</p>
          <Tag variant="neutral" size="sm">{badge}</Tag>
        </div>
      </div>
    </div>
  );
}

function ValuationTile({ label, value, status }: { label: string; value: string; status: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
      <p className="text-sm font-semibold text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-extrabold text-slate-950">{value}</p>
      <p className="mt-1 text-sm font-bold text-slate-500">{status}</p>
    </div>
  );
}

function SentimentCount({ value, label, tone }: { value: number; label: string; tone: SignalTone }) {
  const color = tone === 'success' ? 'text-emerald-600 bg-emerald-50' : tone === 'danger' ? 'text-rose-600 bg-rose-50' : 'text-amber-600 bg-amber-50';
  return (
    <div className={cn('rounded-2xl p-5 text-center', color)}>
      <p className="text-4xl font-extrabold">{value}</p>
      <p className="mt-1 text-sm font-bold">{label}</p>
    </div>
  );
}

function MiniForecastChart({ technical, tall = false, ticker }: { technical: TechnicalAnalysisResponse | null; tall?: boolean; ticker?: string }) {
  // In Overview tab (ticker passed) — show TradingView real-time chart
  if (ticker && !technical) {
    return (
      <div className="mt-5">
        <TradingViewChart ticker={ticker} height={tall ? 400 : 320} />
      </div>
    );
  }
  if (!technical) {
    return (
      <div className="mt-5 flex h-52 items-center justify-center rounded-2xl bg-slate-50 text-sm font-semibold text-slate-400">
        Run analysis to generate the price forecast.
      </div>
    );
  }
  // In Technical tab — show actual GRU model forecast candles
  return (
    <div className="mt-5">
      <TechnicalCandlesChart
        ticker={technical.ticker}
        modelVersion={technical.model_version as 'final_1d' | 'final_1min' | 'v1.1' | 'v1.2'}
        history={technical.history_bars.slice(-Math.min(60, technical.history_bars.length))}
        forecast={technical.forecast_bars}
        dataSource={technical.data_source}
        timeframe={technical.timeframe as '1Min' | '1D'}
      />
    </div>
  );
}


function WatchlistButton({
  ticker,
  companyName,
  signal,
  price,
  changePercent,
}: {
  ticker: string;
  companyName: string;
  signal?: string;
  price?: number;
  changePercent?: number;
}) {
  const { addToWatchlist, removeFromWatchlist, isInWatchlist } = useWatchlistStore();
  const inList = isInWatchlist(ticker);

  const handleClick = () => {
    if (inList) {
      removeFromWatchlist(ticker);
    } else {
      addToWatchlist({
        ticker,
        companyName,
        addedAt: new Date().toISOString(),
        lastSignal: signal as 'BUY' | 'SELL' | 'HOLD' | undefined,
        lastPrice: price,
        lastChangePercent: changePercent,
      });
    }
  };

  return (
    <Button
      type="button"
      variant={inList ? 'primary' : 'secondary'}
      className="gap-2"
      onClick={handleClick}
    >
      <Bookmark size={17} fill={inList ? 'currentColor' : 'none'} />
      {inList ? 'In Watchlist' : 'Add to Watchlist'}
    </Button>
  );
}

function ErrorCard({ message }: { message: string }) {
  return (
    <Card className="border border-amber-200 bg-amber-50" variant="bordered" padding="none">
      <CardContent className="p-6">
        <div className="flex items-start gap-3">
          <FileText size={20} className="mt-0.5 text-amber-700" />
          <p className="text-sm leading-6 text-amber-950">{message}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export function EmptyAnalyzeState() {
  return (
    <div className="mx-auto max-w-4xl text-center">
      <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-extrabold uppercase tracking-[0.18em] text-slate-500 shadow-card">
        <BarChart3 size={14} className="text-primary-600" />
        Three models. One recommendation.
      </div>
      <h1 className="mt-6 text-4xl font-extrabold tracking-[-0.04em] text-slate-950 md:text-6xl">Analyse any stock.</h1>
      <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-slate-500 md:text-base">
        Search a supported ticker to open the full stock-level analysis workspace.
      </p>
      <div className="mt-8 grid gap-4 md:grid-cols-3">
        <FeatureCard icon={<Building2 size={20} />} title="Fundamental" text="Financial health, profitability, and valuation vs peers" />
        <FeatureCard icon={<CandlestickChart size={20} />} title="Technical" text="Price momentum and model forecast signals" />
        <FeatureCard icon={<Newspaper size={20} />} title="Sentiment" text="News tone, article mix, and language-model confidence" />
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return (
    <Card className="border border-slate-200" variant="bordered" padding="none">
      <CardContent className="p-6 text-left">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-50 text-primary-600">
          {icon}
        </div>
        <h3 className="mt-4 text-lg font-extrabold text-slate-950">{title}</h3>
        <p className="mt-2 text-sm leading-6 text-slate-500">{text}</p>
      </CardContent>
    </Card>
  );
}
