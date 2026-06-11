'use client';

import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import {
  ArrowUpRight,
  BarChart3,
  CircleAlert,
  FileText,
  Landmark,
  Search,
  ShieldCheck,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react';
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Tag } from '@/components/ui';
import { cn, fundamentalApi, handleApiError } from '@/lib';
import type { FundamentalAnalysisResponse } from '@/types';

const DEFAULT_TICKER = 'MSFT';
const COVERAGE_TICKERS = ['MSFT', 'GOOGL', 'AAPL', 'NVDA'] as const;

export type CoverageTicker = typeof COVERAGE_TICKERS[number];
type AnalysisLens = 'blend' | 'quality' | 'value';
type AnalysisStatus = 'idle' | 'loading' | 'success' | 'error';
type AccentTone = 'default' | 'success' | 'warning' | 'danger' | 'info';
type TagTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info';

interface LensNote {
  title: string;
  summary: string;
  question: string;
  tone: TagTone;
}

interface ScoreBand {
  label: string;
  score: number;
  summary: string;
  tone: AccentTone;
}

interface Scenario {
  label: 'Bull' | 'Base' | 'Bear';
  price: number;
  probability: number;
  summary: string;
  tone: AccentTone;
}

interface ContextSignal {
  label: string;
  detail: string;
}

interface SegmentMix {
  name: string;
  share: number;
  growth: string;
  margin: string;
  note: string;
}

interface FinancialSnapshot {
  period: string;
  revenue: number;
  operatingMargin: number;
  freeCashFlow: number;
  eps: number;
  roic: number;
}

interface RatioCheck {
  label: string;
  value: string;
  benchmark: string;
  summary: string;
  tone: AccentTone;
}

interface PeerRow {
  ticker: string;
  company: string;
  revenueGrowth: string;
  operatingMargin: string;
  freeCashFlowMargin: string;
  forwardPe: string;
  note: string;
}

interface FilingCheckpoint {
  title: string;
  cadence: string;
  summary: string;
  status: 'Reviewed' | 'Monitor' | 'Priority';
}

interface SpotlightMetric {
  label: string;
  value: string;
}

export interface FundamentalProfile {
  ticker: string;
  companyName: string;
  sector: string;
  headline: string;
  thesis: string;
  marketCap: string;
  price: number;
  fairValueBase: number;
  fairValueLow: number;
  fairValueHigh: number;
  qualityScore: number;
  qualityLabel: string;
  shareholderYield: string;
  balanceSheetLabel: string;
  spotlightMetrics: SpotlightMetric[];
  lensNotes: Record<AnalysisLens, LensNote>;
  scoreBands: ScoreBand[];
  scenarios: Scenario[];
  contextSignals: ContextSignal[];
  segments: SegmentMix[];
  financials: FinancialSnapshot[];
  valuationChecks: RatioCheck[];
  healthChecks: RatioCheck[];
  peers: PeerRow[];
  strengths: string[];
  risks: string[];
  catalysts: string[];
  filingChecklist: FilingCheckpoint[];
}

const LENS_OPTIONS: Array<{
  value: AnalysisLens;
  label: string;
  summary: string;
}> = [
  {
    value: 'blend',
    label: 'Balanced Lens',
    summary: 'Weights quality, growth, and valuation evenly.',
  },
  {
    value: 'quality',
    label: 'Quality Lens',
    summary: 'Emphasizes moat, cash generation, and financial resilience.',
  },
  {
    value: 'value',
    label: 'Value Lens',
    summary: 'Pushes harder on downside cover and fair-value spread.',
  },
];

const TONE_STYLES: Record<
  AccentTone,
  {
    card: string;
    badge: TagTone;
    bar: string;
    fill: string;
    icon: string;
  }
> = {
  default: {
    card: 'border-slate-200 bg-slate-50/90 text-slate-800',
    badge: 'neutral',
    bar: 'bg-slate-700',
    fill: 'bg-slate-900',
    icon: 'bg-slate-900',
  },
  success: {
    card: 'border-emerald-200 bg-emerald-50/85 text-emerald-950',
    badge: 'success',
    bar: 'bg-emerald-500',
    fill: 'bg-emerald-600',
    icon: 'bg-emerald-600',
  },
  warning: {
    card: 'border-amber-200 bg-amber-50/90 text-amber-950',
    badge: 'warning',
    bar: 'bg-amber-500',
    fill: 'bg-amber-500',
    icon: 'bg-amber-500',
  },
  danger: {
    card: 'border-rose-200 bg-rose-50/85 text-rose-950',
    badge: 'danger',
    bar: 'bg-rose-500',
    fill: 'bg-rose-600',
    icon: 'bg-rose-600',
  },
  info: {
    card: 'border-blue-200 bg-blue-50/90 text-blue-950',
    badge: 'info',
    bar: 'bg-blue-500',
    fill: 'bg-blue-600',
    icon: 'bg-blue-600',
  },
};

export const FUNDAMENTAL_PROFILES: Record<CoverageTicker, FundamentalProfile> = {
  MSFT: {
    ticker: 'MSFT',
    companyName: 'Microsoft',
    sector: 'Software & Cloud',
    headline: 'Large-cap compounder with durable enterprise pricing power and AI-driven margin optionality.',
    thesis:
      'Recurring software revenue, Azure mix shift, and disciplined capital returns support a premium multiple that still looks reasonable against cash generation.',
    marketCap: '$3.2T',
    price: 428.15,
    fairValueBase: 458,
    fairValueLow: 418,
    fairValueHigh: 492,
    qualityScore: 9.3,
    qualityLabel: 'Wide margin profile with strong reinvestment capacity',
    shareholderYield: '1.6%',
    balanceSheetLabel: 'Net cash balance sheet with room for elevated AI capex',
    spotlightMetrics: [
      { label: 'Market cap', value: '$3.2T' },
      { label: 'Revenue growth', value: '+14%' },
      { label: 'FCF margin', value: '31%' },
    ],
    lensNotes: {
      blend: {
        title: 'Balanced compounding view',
        summary:
          'Quality remains the anchor, but valuation still leaves room if cloud mix and Copilot monetization continue to improve.',
        question: 'Is AI monetization converting into durable revenue per seat faster than capital intensity rises?',
        tone: 'info',
      },
      quality: {
        title: 'Quality-led underwriting',
        summary:
          'The case is built on recurring enterprise revenue, pricing power, and a balance sheet that can absorb aggressive infrastructure spend.',
        question: 'Does the company keep expanding returns on capital while scaling datacenter investment?',
        tone: 'success',
      },
      value: {
        title: 'Value discipline',
        summary:
          'This is not a cheap stock, but the premium is still defendable because free cash flow and downside resilience remain above peer averages.',
        question: 'Would the valuation still clear the hurdle rate if Azure growth cooled into the mid-teens?',
        tone: 'warning',
      },
    },
    scoreBands: [
      {
        label: 'Valuation',
        score: 7.3,
        summary: 'Premium to software peers, but still supported by free-cash-flow yield and fair value spread.',
        tone: 'info',
      },
      {
        label: 'Growth durability',
        score: 8.8,
        summary: 'Azure, security, and productivity bundles provide multiple engines of expansion.',
        tone: 'success',
      },
      {
        label: 'Profitability',
        score: 9.4,
        summary: 'High gross margins and expanding operating leverage keep earnings quality elevated.',
        tone: 'success',
      },
      {
        label: 'Balance sheet',
        score: 9.1,
        summary: 'Net cash and strong coverage ratios keep strategic optionality high.',
        tone: 'success',
      },
      {
        label: 'Capital allocation',
        score: 8.5,
        summary: 'Buybacks and dividend remain additive without constraining the investment cycle.',
        tone: 'info',
      },
    ],
    scenarios: [
      {
        label: 'Bull',
        price: 506,
        probability: 25,
        summary: 'Copilot monetization scales quickly and Azure margin stays resilient.',
        tone: 'success',
      },
      {
        label: 'Base',
        price: 458,
        probability: 50,
        summary: 'Cloud growth remains healthy, with steady expansion in productivity and security.',
        tone: 'info',
      },
      {
        label: 'Bear',
        price: 398,
        probability: 25,
        summary: 'Enterprise seat growth cools while AI infrastructure costs rise faster than expected.',
        tone: 'danger',
      },
    ],
    contextSignals: [
      {
        label: 'Industry setup',
        detail: 'Enterprise budgets are consolidating toward platform vendors that can bundle security, productivity, and AI workflows.',
      },
      {
        label: 'Demand driver',
        detail: 'Azure optimization headwinds have moderated, while premium AI seats create another monetization layer.',
      },
      {
        label: 'Macro sensitivity',
        detail: 'Mission-critical software spending is resilient, but seat growth can soften if enterprise hiring slows.',
      },
    ],
    segments: [
      {
        name: 'Cloud & AI',
        share: 43,
        growth: '+25%',
        margin: 'High 40s',
        note: 'Azure and AI services remain the largest source of incremental growth and valuation support.',
      },
      {
        name: 'Productivity & Business Processes',
        share: 34,
        growth: '+12%',
        margin: 'Mid 50s',
        note: 'Office, LinkedIn, and Teams subscriptions create sticky cash flow and strong renewals.',
      },
      {
        name: 'More Personal Computing',
        share: 23,
        growth: '+6%',
        margin: 'Mid 20s',
        note: 'Windows, gaming, and devices add cycle exposure but diversify the overall revenue mix.',
      },
    ],
    financials: [
      { period: 'FY22', revenue: 198.3, operatingMargin: 41.6, freeCashFlow: 65.1, eps: 9.65, roic: 28.0 },
      { period: 'FY23', revenue: 211.9, operatingMargin: 41.8, freeCashFlow: 59.5, eps: 9.68, roic: 27.3 },
      { period: 'FY24', revenue: 236.6, operatingMargin: 46.2, freeCashFlow: 74.1, eps: 11.86, roic: 31.5 },
      { period: 'LTM', revenue: 252.4, operatingMargin: 46.0, freeCashFlow: 79.8, eps: 13.05, roic: 33.2 },
    ],
    valuationChecks: [
      {
        label: 'Forward P/E',
        value: '31.2x',
        benchmark: 'Peer median 28.4x',
        summary: 'Premium multiple matches a higher-quality growth mix.',
        tone: 'info',
      },
      {
        label: 'PEG',
        value: '2.0x',
        benchmark: 'Peer median 2.1x',
        summary: 'Growth-adjusted valuation remains reasonable for the category.',
        tone: 'success',
      },
      {
        label: 'EV / EBITDA',
        value: '23.5x',
        benchmark: 'Peer median 20.8x',
        summary: 'Still rich on traditional multiples, so execution matters.',
        tone: 'warning',
      },
      {
        label: 'Free-cash-flow yield',
        value: '3.6%',
        benchmark: 'Peer median 3.1%',
        summary: 'Cash earnings support the premium better than headline earnings alone.',
        tone: 'success',
      },
      {
        label: 'Price / Sales',
        value: '13.2x',
        benchmark: 'Peer median 11.8x',
        summary: 'Expensive on revenue, but justified by margin depth and durability.',
        tone: 'warning',
      },
    ],
    healthChecks: [
      {
        label: 'Net cash',
        value: '$58B',
        benchmark: 'Above software peer set',
        summary: 'Infrastructure buildout can step up without stressing the balance sheet.',
        tone: 'success',
      },
      {
        label: 'Debt / Equity',
        value: '0.19x',
        benchmark: 'Peer median 0.38x',
        summary: 'Conservative leverage profile relative to other mega-cap software names.',
        tone: 'success',
      },
      {
        label: 'Current ratio',
        value: '1.32x',
        benchmark: 'Comfortably funded',
        summary: 'Short-term liquidity remains solid even through heavier capex periods.',
        tone: 'info',
      },
      {
        label: 'FCF conversion',
        value: '118%',
        benchmark: 'Top-tier for software',
        summary: 'Earnings quality is reinforced by strong cash conversion.',
        tone: 'success',
      },
      {
        label: 'ROIC',
        value: '33.2%',
        benchmark: 'Peer median 18.9%',
        summary: 'Returns on capital remain well above cost-of-capital assumptions.',
        tone: 'success',
      },
      {
        label: 'Shareholder yield',
        value: '1.6%',
        benchmark: 'Dividend + buybacks',
        summary: 'Capital return is supportive without overwhelming reinvestment priorities.',
        tone: 'info',
      },
    ],
    peers: [
      {
        ticker: 'MSFT',
        company: 'Microsoft',
        revenueGrowth: '+14%',
        operatingMargin: '46%',
        freeCashFlowMargin: '31%',
        forwardPe: '31.2x',
        note: 'Best balance of margin depth, recurring revenue, and valuation discipline in the mega-cap set.',
      },
      {
        ticker: 'AAPL',
        company: 'Apple',
        revenueGrowth: '+5%',
        operatingMargin: '31%',
        freeCashFlowMargin: '26%',
        forwardPe: '29.0x',
        note: 'Consumer ecosystem premium with heavier hardware-cycle dependence.',
      },
      {
        ticker: 'NVDA',
        company: 'NVIDIA',
        revenueGrowth: '+53%',
        operatingMargin: '58%',
        freeCashFlowMargin: '49%',
        forwardPe: '36.5x',
        note: 'Extraordinary growth profile, but meaningfully higher cyclicality and concentration.',
      },
      {
        ticker: 'GOOGL',
        company: 'Alphabet',
        revenueGrowth: '+11%',
        operatingMargin: '33%',
        freeCashFlowMargin: '25%',
        forwardPe: '22.4x',
        note: 'Cheaper multiple, but weaker enterprise monetization breadth.',
      },
      {
        ticker: 'ORCL',
        company: 'Oracle',
        revenueGrowth: '+8%',
        operatingMargin: '39%',
        freeCashFlowMargin: '28%',
        forwardPe: '23.1x',
        note: 'Strong backlog and cloud momentum, though with narrower platform reach.',
      },
    ],
    strengths: [
      'Broad platform bundle increases customer stickiness across productivity, security, and cloud.',
      'High recurring revenue base gives management room to invest heavily without destabilizing margins.',
      'Strong balance sheet and disciplined buybacks support both optionality and downside protection.',
    ],
    risks: [
      'AI datacenter spend could rise faster than monetization if enterprise adoption lags expectations.',
      'Regulatory scrutiny around bundling and antitrust remains a medium-term overhang.',
      'Commercial seat growth can soften if corporate hiring and IT budgets turn cautious.',
    ],
    catalysts: [
      'Copilot attach rates and pricing stability across enterprise seat cohorts.',
      'Azure mix shift toward higher-margin AI and platform services.',
      'Operating leverage once the heaviest AI infrastructure build cycle normalizes.',
    ],
    filingChecklist: [
      {
        title: 'Business and segment disclosures',
        cadence: 'Annual / quarterly',
        summary: 'Confirm Azure mix, commercial RPO, and Copilot attach assumptions still support the base case.',
        status: 'Priority',
      },
      {
        title: 'Management discussion and analysis',
        cadence: 'Quarterly',
        summary: 'Watch margin commentary for signs that AI revenue is covering the capex step-up.',
        status: 'Reviewed',
      },
      {
        title: 'Cash flow statement',
        cadence: 'Quarterly',
        summary: 'Track capex intensity versus free-cash-flow conversion to maintain valuation support.',
        status: 'Reviewed',
      },
      {
        title: 'Risk factors',
        cadence: 'Annual',
        summary: 'Focus on regulation, competition in cloud AI, and customer optimization trends.',
        status: 'Monitor',
      },
      {
        title: 'Capital allocation',
        cadence: 'Quarterly',
        summary: 'Verify dividends and buybacks remain balanced against infrastructure investment needs.',
        status: 'Reviewed',
      },
    ],
  },
  AAPL: {
    ticker: 'AAPL',
    companyName: 'Apple',
    sector: 'Consumer Technology',
    headline: 'Elite ecosystem business with exceptional cash efficiency, but a valuation that already prices in plenty of execution.',
    thesis:
      'Services mix, customer retention, and capital return are still world-class, yet upside depends on proving the next device and software cycle can reaccelerate growth.',
    marketCap: '$3.1T',
    price: 214.6,
    fairValueBase: 205,
    fairValueLow: 185,
    fairValueHigh: 228,
    qualityScore: 8.7,
    qualityLabel: 'Elite ecosystem economics with unusually strong capital return',
    shareholderYield: '3.7%',
    balanceSheetLabel: 'Highly efficient, though leverage-assisted, capital structure',
    spotlightMetrics: [
      { label: 'Services mix', value: '27%' },
      { label: 'Gross margin', value: '46%' },
      { label: 'Shareholder yield', value: '3.7%' },
    ],
    lensNotes: {
      blend: {
        title: 'Balanced stewardship view',
        summary:
          'A premium quality business is offset by a fuller multiple, making execution on services and the product refresh cycle essential.',
        question: 'Can services and AI-led device upgrades lift growth enough to justify today’s premium?',
        tone: 'info',
      },
      quality: {
        title: 'Quality-led underwriting',
        summary:
          'The durability story remains compelling because retention, monetization per user, and cash returns are still exceptional.',
        question: 'Does the ecosystem keep deepening even if hardware units stay flattish?',
        tone: 'success',
      },
      value: {
        title: 'Value discipline',
        summary:
          'The valuation already assumes clean execution, so downside cover is thinner than the brand strength might imply.',
        question: 'Would the stock still screen attractively if services growth slowed or China risk intensified?',
        tone: 'warning',
      },
    },
    scoreBands: [
      {
        label: 'Valuation',
        score: 5.8,
        summary: 'Premium to peers on most metrics with limited upside to base fair value.',
        tone: 'warning',
      },
      {
        label: 'Growth durability',
        score: 7.2,
        summary: 'Services help smooth the cycle, but hardware refresh timing still matters.',
        tone: 'info',
      },
      {
        label: 'Profitability',
        score: 9.0,
        summary: 'Brand strength and vertical integration preserve best-in-class margins.',
        tone: 'success',
      },
      {
        label: 'Balance sheet',
        score: 7.4,
        summary: 'Still healthy, though leverage is more intentional because of capital returns.',
        tone: 'info',
      },
      {
        label: 'Capital allocation',
        score: 9.3,
        summary: 'Repurchases and dividends remain among the strongest in large-cap equities.',
        tone: 'success',
      },
    ],
    scenarios: [
      {
        label: 'Bull',
        price: 231,
        probability: 20,
        summary: 'AI-enabled device upgrades and services growth reaccelerate together.',
        tone: 'success',
      },
      {
        label: 'Base',
        price: 205,
        probability: 50,
        summary: 'Services stay strong, but hardware growth remains measured and valuation stays elevated.',
        tone: 'info',
      },
      {
        label: 'Bear',
        price: 176,
        probability: 30,
        summary: 'China exposure and a slower upgrade cycle compress the multiple and growth outlook.',
        tone: 'danger',
      },
    ],
    contextSignals: [
      {
        label: 'Industry setup',
        detail: 'Premium smartphone and device categories are mature, shifting the emphasis toward ecosystem monetization and retention.',
      },
      {
        label: 'Demand driver',
        detail: 'Services ARPU, silicon differentiation, and new device features matter more than simple unit growth.',
      },
      {
        label: 'Macro sensitivity',
        detail: 'Consumer spending and FX matter more here than in enterprise software, especially for international hardware sales.',
      },
    ],
    segments: [
      {
        name: 'iPhone',
        share: 52,
        growth: '+4%',
        margin: 'High 30s',
        note: 'The installed base remains a moat, but the growth profile is tied to upgrade cadence.',
      },
      {
        name: 'Services',
        share: 27,
        growth: '+14%',
        margin: 'High 70s',
        note: 'The highest-quality earnings stream in the mix, supporting blended margin expansion.',
      },
      {
        name: 'Mac, iPad, Wearables',
        share: 21,
        growth: '+3%',
        margin: 'Low 30s',
        note: 'Hardware adjacency expands the ecosystem, though it is less important to valuation than services.',
      },
    ],
    financials: [
      { period: 'FY22', revenue: 394.3, operatingMargin: 30.3, freeCashFlow: 111.4, eps: 6.11, roic: 46.7 },
      { period: 'FY23', revenue: 383.3, operatingMargin: 29.8, freeCashFlow: 99.6, eps: 6.13, roic: 44.5 },
      { period: 'FY24', revenue: 391.8, operatingMargin: 31.1, freeCashFlow: 104.5, eps: 6.46, roic: 46.9 },
      { period: 'LTM', revenue: 407.2, operatingMargin: 31.2, freeCashFlow: 108.1, eps: 6.72, roic: 49.0 },
    ],
    valuationChecks: [
      {
        label: 'Forward P/E',
        value: '29.0x',
        benchmark: 'Peer median 25.8x',
        summary: 'The stock trades at a clear premium to large-cap consumer tech peers.',
        tone: 'warning',
      },
      {
        label: 'PEG',
        value: '2.5x',
        benchmark: 'Peer median 2.0x',
        summary: 'Growth-adjusted valuation asks for a cleaner acceleration path.',
        tone: 'danger',
      },
      {
        label: 'EV / EBITDA',
        value: '21.1x',
        benchmark: 'Peer median 18.6x',
        summary: 'Still rich, even after accounting for balance-sheet quality.',
        tone: 'warning',
      },
      {
        label: 'Free-cash-flow yield',
        value: '3.5%',
        benchmark: 'Peer median 4.2%',
        summary: 'Cash generation is elite, but the yield is not especially generous.',
        tone: 'danger',
      },
      {
        label: 'Price / Sales',
        value: '7.7x',
        benchmark: 'Peer median 6.4x',
        summary: 'Supported by margin quality, but difficult to call cheap.',
        tone: 'warning',
      },
    ],
    healthChecks: [
      {
        label: 'Net cash',
        value: '$12B',
        benchmark: 'Positive but slimmer buffer',
        summary: 'Still healthy, though less of a balance-sheet differentiator than before.',
        tone: 'info',
      },
      {
        label: 'Debt / Equity',
        value: '1.47x',
        benchmark: 'Above peer median',
        summary: 'Leverage is intentional and tied to an aggressive capital-return program.',
        tone: 'warning',
      },
      {
        label: 'Current ratio',
        value: '1.08x',
        benchmark: 'Adequate liquidity',
        summary: 'Working-capital management remains efficient, if lean.',
        tone: 'info',
      },
      {
        label: 'FCF conversion',
        value: '99%',
        benchmark: 'Very strong for hardware',
        summary: 'Earnings quality remains solid despite hardware-cycle variability.',
        tone: 'success',
      },
      {
        label: 'ROIC',
        value: '49.0%',
        benchmark: 'Exceptional',
        summary: 'Returns on capital remain among the strongest in global large caps.',
        tone: 'success',
      },
      {
        label: 'Shareholder yield',
        value: '3.7%',
        benchmark: 'Dividend + buybacks',
        summary: 'Capital returns are a material part of the equity case.',
        tone: 'success',
      },
    ],
    peers: [
      {
        ticker: 'AAPL',
        company: 'Apple',
        revenueGrowth: '+5%',
        operatingMargin: '31%',
        freeCashFlowMargin: '26%',
        forwardPe: '29.0x',
        note: 'Best-in-class ecosystem and buybacks, but valuation leaves less margin for error.',
      },
      {
        ticker: 'MSFT',
        company: 'Microsoft',
        revenueGrowth: '+14%',
        operatingMargin: '46%',
        freeCashFlowMargin: '31%',
        forwardPe: '31.2x',
        note: 'Similar quality premium, with stronger enterprise growth and net-cash flexibility.',
      },
      {
        ticker: 'GOOGL',
        company: 'Alphabet',
        revenueGrowth: '+11%',
        operatingMargin: '33%',
        freeCashFlowMargin: '25%',
        forwardPe: '22.4x',
        note: 'Lower multiple with strong cash generation, but less consumer-hardware lock-in.',
      },
      {
        ticker: 'AMZN',
        company: 'Amazon',
        revenueGrowth: '+12%',
        operatingMargin: '11%',
        freeCashFlowMargin: '9%',
        forwardPe: '34.7x',
        note: 'Higher reinvestment intensity and lower margin quality keep comparability imperfect.',
      },
      {
        ticker: 'COST',
        company: 'Costco',
        revenueGrowth: '+8%',
        operatingMargin: '3%',
        freeCashFlowMargin: '3%',
        forwardPe: '47.0x',
        note: 'Another premium consumer loyalty model, though with far lower margin leverage.',
      },
    ],
    strengths: [
      'Installed base and ecosystem depth keep switching costs unusually high.',
      'Services and silicon integration continue to improve blended profitability and customer lock-in.',
      'Capital return remains powerful, supporting earnings-per-share compounding even in modest growth periods.',
    ],
    risks: [
      'China exposure creates both demand and supply-chain risk that can affect growth and sentiment quickly.',
      'Regulatory pressure on app-store economics could challenge one of the highest-margin businesses in the mix.',
      'A slower device replacement cycle can make the premium multiple harder to defend.',
    ],
    catalysts: [
      'Higher-value services monetization across the installed base.',
      'An AI-enabled product cycle that improves replacement demand and pricing mix.',
      'Continued buybacks that enhance per-share growth even in a moderate revenue environment.',
    ],
    filingChecklist: [
      {
        title: 'Business and segment disclosures',
        cadence: 'Annual / quarterly',
        summary: 'Monitor the revenue mix between iPhone, services, and the broader device ecosystem.',
        status: 'Priority',
      },
      {
        title: 'Management discussion and analysis',
        cadence: 'Quarterly',
        summary: 'Watch margin language for mix, FX, and product-cycle commentary.',
        status: 'Reviewed',
      },
      {
        title: 'Cash flow statement',
        cadence: 'Quarterly',
        summary: 'Confirm working-capital swings are not obscuring weaker underlying demand.',
        status: 'Reviewed',
      },
      {
        title: 'Risk factors',
        cadence: 'Annual',
        summary: 'Focus on China exposure, regulatory pressure, and supply-chain concentration.',
        status: 'Monitor',
      },
      {
        title: 'Capital allocation',
        cadence: 'Quarterly',
        summary: 'Keep buyback pace and net-cash trajectory in view because they matter for fair value support.',
        status: 'Reviewed',
      },
    ],
  },
  NVDA: {
    ticker: 'NVDA',
    companyName: 'NVIDIA',
    sector: 'Semiconductors & AI Infrastructure',
    headline: 'Exceptional unit economics and growth leadership, with valuation support hinging on how durable the AI demand cycle proves to be.',
    thesis:
      'The full-stack compute franchise, software moat, and networking attach create rare earnings power, but concentration and cycle risk still need a larger discount rate than the quality of the business alone would suggest.',
    marketCap: '$3.5T',
    price: 142.8,
    fairValueBase: 154,
    fairValueLow: 118,
    fairValueHigh: 175,
    qualityScore: 8.9,
    qualityLabel: 'Extraordinary economics with concentrated end-market exposure',
    shareholderYield: '0.1%',
    balanceSheetLabel: 'Net cash balance sheet with ample operating flexibility',
    spotlightMetrics: [
      { label: 'Data-center mix', value: '88%' },
      { label: 'Revenue growth', value: '+53%' },
      { label: 'Operating margin', value: '58%' },
    ],
    lensNotes: {
      blend: {
        title: 'Balanced infrastructure view',
        summary:
          'A powerful growth-and-profitability profile still supports premium valuation, provided inference demand broadens beyond the initial training wave.',
        question: 'How much of today’s demand is durable platform adoption versus a front-loaded infrastructure build cycle?',
        tone: 'info',
      },
      quality: {
        title: 'Quality-led underwriting',
        summary:
          'Few businesses combine software lock-in, hardware leadership, and operating leverage this efficiently, even if customer concentration remains elevated.',
        question: 'Does the ecosystem stay sticky enough to preserve pricing power as competition rises?',
        tone: 'success',
      },
      value: {
        title: 'Value discipline',
        summary:
          'The stock is not optically cheap, but PEG and free-cash-flow support are better than the headline price-to-sales multiple suggests.',
        question: 'Would the valuation still clear the hurdle rate if hyperscaler capex normalized faster than expected?',
        tone: 'warning',
      },
    },
    scoreBands: [
      {
        label: 'Valuation',
        score: 6.9,
        summary: 'Premium multiple remains justified only if the growth curve stays steep.',
        tone: 'warning',
      },
      {
        label: 'Growth durability',
        score: 9.5,
        summary: 'AI compute, networking, and software create unusually strong expansion optionality.',
        tone: 'success',
      },
      {
        label: 'Profitability',
        score: 9.8,
        summary: 'Unit economics and pricing power are among the strongest in public markets.',
        tone: 'success',
      },
      {
        label: 'Balance sheet',
        score: 8.8,
        summary: 'Net cash and a light leverage profile reduce execution risk.',
        tone: 'success',
      },
      {
        label: 'Capital allocation',
        score: 7.0,
        summary: 'Most of the value comes from reinvestment rather than direct shareholder payout.',
        tone: 'info',
      },
    ],
    scenarios: [
      {
        label: 'Bull',
        price: 178,
        probability: 25,
        summary: 'Blackwell ramps smoothly and inference demand broadens across enterprise workloads.',
        tone: 'success',
      },
      {
        label: 'Base',
        price: 154,
        probability: 50,
        summary: 'AI infrastructure demand remains strong, though growth naturally normalizes from peak levels.',
        tone: 'info',
      },
      {
        label: 'Bear',
        price: 120,
        probability: 25,
        summary: 'Customer digestion, export restrictions, or custom silicon pressure compress the multiple.',
        tone: 'danger',
      },
    ],
    contextSignals: [
      {
        label: 'Industry setup',
        detail: 'AI infrastructure remains supply-led, but the next phase of demand depends on inference monetization and broader enterprise adoption.',
      },
      {
        label: 'Demand driver',
        detail: 'Datacenter GPUs, networking, and CUDA software remain tightly linked in customer purchasing decisions.',
      },
      {
        label: 'Macro sensitivity',
        detail: 'This is less tied to consumer demand and more exposed to cloud capex digestion, policy, and export dynamics.',
      },
    ],
    segments: [
      {
        name: 'Data Center',
        share: 88,
        growth: '+73%',
        margin: 'Low 60s',
        note: 'The core earnings engine, powered by GPU systems, networking, and software lock-in.',
      },
      {
        name: 'Gaming',
        share: 8,
        growth: '+12%',
        margin: 'High 20s',
        note: 'Smaller in the mix, but still useful for brand reach and channel breadth.',
      },
      {
        name: 'Auto & Edge',
        share: 4,
        growth: '+22%',
        margin: 'Mid 20s',
        note: 'Early-stage optionality rather than the current driver of fair value.',
      },
    ],
    financials: [
      { period: 'FY23', revenue: 26.9, operatingMargin: 26.7, freeCashFlow: 3.8, eps: 0.17, roic: 12.3 },
      { period: 'FY24', revenue: 60.9, operatingMargin: 54.1, freeCashFlow: 27.0, eps: 1.19, roic: 44.5 },
      { period: 'FY25', revenue: 121.6, operatingMargin: 58.0, freeCashFlow: 56.8, eps: 2.56, roic: 78.4 },
      { period: 'LTM', revenue: 139.4, operatingMargin: 58.1, freeCashFlow: 64.5, eps: 2.89, roic: 82.1 },
    ],
    valuationChecks: [
      {
        label: 'Forward P/E',
        value: '36.5x',
        benchmark: 'Peer median 34.1x',
        summary: 'Still expensive, though not extreme relative to the growth profile.',
        tone: 'warning',
      },
      {
        label: 'PEG',
        value: '1.1x',
        benchmark: 'Peer median 1.6x',
        summary: 'Growth-adjusted valuation is more supportive than the headline multiple implies.',
        tone: 'success',
      },
      {
        label: 'EV / EBITDA',
        value: '27.8x',
        benchmark: 'Peer median 23.5x',
        summary: 'A premium remains necessary because profitability is far above the group.',
        tone: 'warning',
      },
      {
        label: 'Free-cash-flow yield',
        value: '2.8%',
        benchmark: 'Peer median 2.4%',
        summary: 'Cash generation helps defend the current valuation better than sales multiples do.',
        tone: 'success',
      },
      {
        label: 'Price / Sales',
        value: '25.0x',
        benchmark: 'Peer median 13.4x',
        summary: 'The most aggressive metric in the stack, underscoring how much growth is already expected.',
        tone: 'danger',
      },
    ],
    healthChecks: [
      {
        label: 'Net cash',
        value: '$23B',
        benchmark: 'Strong liquidity',
        summary: 'The balance sheet can handle volatility and still fund aggressive product cycles.',
        tone: 'success',
      },
      {
        label: 'Debt / Equity',
        value: '0.22x',
        benchmark: 'Below semiconductor peers',
        summary: 'Leverage is low for a company with this scale of earnings power.',
        tone: 'success',
      },
      {
        label: 'Current ratio',
        value: '3.52x',
        benchmark: 'Very strong',
        summary: 'Short-term financial flexibility is comfortably above peer averages.',
        tone: 'success',
      },
      {
        label: 'FCF conversion',
        value: '121%',
        benchmark: 'Best-in-class',
        summary: 'Cash generation materially exceeds already-strong accounting earnings.',
        tone: 'success',
      },
      {
        label: 'ROIC',
        value: '82.1%',
        benchmark: 'Exceptional',
        summary: 'Returns on capital are extraordinary even after the recent scale-up.',
        tone: 'success',
      },
      {
        label: 'Shareholder yield',
        value: '0.1%',
        benchmark: 'Reinvestment-led',
        summary: 'The equity case is driven by growth compounding, not cash payout.',
        tone: 'info',
      },
    ],
    peers: [
      {
        ticker: 'NVDA',
        company: 'NVIDIA',
        revenueGrowth: '+53%',
        operatingMargin: '58%',
        freeCashFlowMargin: '49%',
        forwardPe: '36.5x',
        note: 'Dominant full-stack AI platform with peer-leading unit economics.',
      },
      {
        ticker: 'AMD',
        company: 'AMD',
        revenueGrowth: '+18%',
        operatingMargin: '24%',
        freeCashFlowMargin: '18%',
        forwardPe: '31.8x',
        note: 'Solid accelerator progress, though with less ecosystem lock-in.',
      },
      {
        ticker: 'AVGO',
        company: 'Broadcom',
        revenueGrowth: '+16%',
        operatingMargin: '46%',
        freeCashFlowMargin: '41%',
        forwardPe: '29.7x',
        note: 'High-quality infrastructure exposure with a different product and M&A mix.',
      },
      {
        ticker: 'TSM',
        company: 'TSMC',
        revenueGrowth: '+21%',
        operatingMargin: '41%',
        freeCashFlowMargin: '31%',
        forwardPe: '25.2x',
        note: 'Manufacturing leader and critical supplier, but with a different margin and risk profile.',
      },
      {
        ticker: 'MSFT',
        company: 'Microsoft',
        revenueGrowth: '+14%',
        operatingMargin: '46%',
        freeCashFlowMargin: '31%',
        forwardPe: '31.2x',
        note: 'Alternative AI beneficiary with lower cyclicality and broader enterprise revenue diversity.',
      },
    ],
    strengths: [
      'CUDA, networking, and systems integration create a software-and-hardware moat that is hard to replicate.',
      'Operating leverage is unusually powerful because pricing remains strong at very high gross margins.',
      'Net cash and rapid cash conversion keep strategic flexibility high despite a volatile end market.',
    ],
    risks: [
      'Hyperscaler spending could pause after an intense build phase, creating tougher comparisons.',
      'Custom silicon and competitor roadmaps can pressure pricing or share at the margin.',
      'Export restrictions remain a material policy risk for both demand and product mix.',
    ],
    catalysts: [
      'Blackwell and networking attach rates as the next wave of system upgrades begins.',
      'Broader enterprise inference demand beyond the largest cloud platforms.',
      'Evidence that software and platform lock-in are preserving pricing power even as competition rises.',
    ],
    filingChecklist: [
      {
        title: 'Business and segment disclosures',
        cadence: 'Annual / quarterly',
        summary: 'Track datacenter concentration, networking attach, and the mix between training and inference demand.',
        status: 'Priority',
      },
      {
        title: 'Management discussion and analysis',
        cadence: 'Quarterly',
        summary: 'Watch commentary on supply, lead times, customer digestion, and competitive dynamics.',
        status: 'Reviewed',
      },
      {
        title: 'Cash flow statement',
        cadence: 'Quarterly',
        summary: 'Validate that cash conversion remains strong as revenue scale normalizes.',
        status: 'Reviewed',
      },
      {
        title: 'Risk factors',
        cadence: 'Annual',
        summary: 'Focus on export controls, concentration, and reliance on a small number of critical suppliers.',
        status: 'Monitor',
      },
      {
        title: 'Capital allocation',
        cadence: 'Quarterly',
        summary: 'Reinvestment pace matters more than payout, so keep an eye on how management funds the next cycle.',
        status: 'Reviewed',
      },
    ],
  },
  GOOGL: {
    ticker: 'GOOGL',
    companyName: 'Alphabet',
    sector: 'Search, Cloud & AI',
    headline: 'Dominant search franchise with accelerating cloud growth and undervalued AI optionality at a meaningful discount to mega-cap peers.',
    thesis: 'Google Search retains durable pricing power while Google Cloud approaches profitability inflection. The combination of ad resilience, cloud scale-up, and AI-native products supports a re-rating. At a forward P/E well below MSFT and AAPL, the quality discount looks too wide.',
    marketCap: '$2.1T',
    price: 173.50,
    fairValueBase: 198,
    fairValueLow: 162,
    fairValueHigh: 225,
    qualityScore: 8.8,
    qualityLabel: 'Elite cash generation with growing cloud optionality',
    shareholderYield: '0.5%',
    balanceSheetLabel: 'Deep net cash — $95B with disciplined buyback program',
    spotlightMetrics: [
      { label: 'Market cap', value: '$2.1T' },
      { label: 'Cloud growth', value: '+28%' },
      { label: 'FCF margin', value: '25%' },
    ],
    lensNotes: {
      blend: { title: 'Balanced compounding view', summary: 'The search moat funds the cloud investment cycle, and AI integration creates underappreciated earnings optionality at a lower multiple than peers.', question: 'Can Google Cloud sustain its growth while Search monetization holds through AI-driven query shifts?', tone: 'info' },
      quality: { title: 'Quality-led underwriting', summary: 'First-party data at scale, advertising network effects, and a growing cloud ecosystem create unusually high barriers to disruption.', question: 'Do the moat dynamics in Search hold as AI assistants absorb more informational queries?', tone: 'success' },
      value: { title: 'Value discipline', summary: 'At a meaningfully lower multiple than MSFT and AAPL, Alphabet offers a similar quality profile with more upside if the cloud trajectory holds.', question: 'Does the relative discount to mega-cap peers narrow as Cloud margins continue to improve?', tone: 'success' },
    },
    scoreBands: [
      { label: 'Valuation', score: 8.2, summary: 'Discounted to mega-cap peers on most multiples, with FCF yield supporting the case.', tone: 'success' },
      { label: 'Growth durability', score: 8.4, summary: 'Search remains resilient while Cloud provides a second high-growth engine.', tone: 'success' },
      { label: 'Profitability', score: 8.9, summary: 'Expanding margins across both segments with strong reinvestment capacity.', tone: 'success' },
      { label: 'Balance sheet', score: 9.2, summary: 'One of the largest net cash positions in global large caps at $95B.', tone: 'success' },
      { label: 'Capital allocation', score: 7.8, summary: 'Buybacks are accelerating and now represent a material shareholder return.', tone: 'info' },
    ],
    scenarios: [
      { label: 'Bull', price: 225, probability: 25, summary: 'Cloud margin expansion accelerates and AI monetization in Search remains intact.', tone: 'success' },
      { label: 'Base', price: 198, probability: 50, summary: 'Cloud sustains growth, Search holds pricing, and the discount to peers narrows gradually.', tone: 'info' },
      { label: 'Bear', price: 152, probability: 25, summary: 'AI disruption to Search queries and a slower cloud ramp compress the multiple.', tone: 'danger' },
    ],
    contextSignals: [
      { label: 'Industry setup', detail: 'AI is both a risk and a driver for Alphabet — it pressures legacy search but creates new cloud demand and AI-native products.' },
      { label: 'Demand driver', detail: 'Advertiser ROI on Google Search remains strong, while Cloud growth is broadening beyond AI-specific workloads.' },
      { label: 'Macro sensitivity', detail: 'Advertising is more cyclical than enterprise software, but Search has historically proven resilient in moderate downturns.' },
    ],
    segments: [
      { name: 'Google Search & Other', share: 57, growth: '+10%', margin: 'High 30s', note: 'The cash engine of the business, funding all reinvestment with durable pricing power.' },
      { name: 'Google Cloud', share: 12, growth: '+28%', margin: 'Mid teens and expanding', note: 'The fastest-growing segment, now meaningfully profitable with AI-driven enterprise demand.' },
      { name: 'YouTube Ads', share: 11, growth: '+13%', margin: 'Mid 20s', note: 'Strong Connected TV momentum adding a more durable revenue stream to the ad mix.' },
      { name: 'Network & Other Bets', share: 20, growth: '+5%', margin: 'Mixed', note: 'Network ads and subscriptions round out the mix, with Other Bets holding long-term optionality.' },
    ],
    financials: [
      { period: 'FY22', revenue: 282.8, operatingMargin: 26.5, freeCashFlow: 60.0, eps: 5.11, roic: 18.2 },
      { period: 'FY23', revenue: 307.4, operatingMargin: 27.4, freeCashFlow: 69.5, eps: 5.80, roic: 20.1 },
      { period: 'FY24', revenue: 350.0, operatingMargin: 31.6, freeCashFlow: 87.8, eps: 7.65, roic: 26.4 },
      { period: 'LTM', revenue: 370.2, operatingMargin: 32.1, freeCashFlow: 93.2, eps: 8.04, roic: 28.0 },
    ],
    valuationChecks: [
      { label: 'Forward P/E', value: '20.4x', benchmark: 'Peer median 28.4x', summary: 'Significant discount to mega-cap software and consumer tech peers.', tone: 'success' },
      { label: 'PEG', value: '1.5x', benchmark: 'Peer median 2.1x', summary: 'Growth-adjusted valuation is among the most attractive in the large-cap set.', tone: 'success' },
      { label: 'EV / EBITDA', value: '16.4x', benchmark: 'Peer median 20.8x', summary: 'Cheaper than peers even before accounting for the net cash buffer.', tone: 'success' },
      { label: 'Free-cash-flow yield', value: '4.2%', benchmark: 'Peer median 3.1%', summary: 'One of the strongest FCF yields in mega-cap tech.', tone: 'success' },
      { label: 'Price / Sales', value: '6.0x', benchmark: 'Peer median 11.8x', summary: 'Meaningfully cheaper on revenue, with margins improving toward software-like levels.', tone: 'success' },
    ],
    healthChecks: [
      { label: 'Net cash', value: '$95B', benchmark: 'Largest in mega-cap tech', summary: 'Deep cash reserves fund the AI investment cycle without balance-sheet stress.', tone: 'success' },
      { label: 'Debt / Equity', value: '0.06x', benchmark: 'Far below peer median', summary: 'Essentially an unlevered balance sheet, maximum strategic flexibility.', tone: 'success' },
      { label: 'Current ratio', value: '2.14x', benchmark: 'Strong liquidity', summary: 'Comfortable working capital position even in a heavy AI investment cycle.', tone: 'success' },
      { label: 'FCF conversion', value: '109%', benchmark: 'Top-tier for internet', summary: 'Strong conversion demonstrates the quality of accounting earnings.', tone: 'success' },
      { label: 'ROIC', value: '28.0%', benchmark: 'Peer median 18.9%', summary: 'Returns on capital are well above cost-of-capital and improving year over year.', tone: 'success' },
      { label: 'Shareholder yield', value: '0.5%', benchmark: 'Buyback-led return', summary: 'Buyback pace has accelerated and is now a more meaningful return component.', tone: 'info' },
    ],
    peers: [
      { ticker: 'GOOGL', company: 'Alphabet', revenueGrowth: '+10%', operatingMargin: '32%', freeCashFlowMargin: '25%', forwardPe: '20.4x', note: 'Best value in mega-cap tech — search moat plus cloud growth at a discount.' },
      { ticker: 'MSFT', company: 'Microsoft', revenueGrowth: '+14%', operatingMargin: '46%', freeCashFlowMargin: '31%', forwardPe: '31.2x', note: 'Higher multiple reflects enterprise software premium and deeper AI monetization.' },
      { ticker: 'META', company: 'Meta', revenueGrowth: '+16%', operatingMargin: '41%', freeCashFlowMargin: '33%', forwardPe: '23.1x', note: 'Similar advertising exposure with more concentrated social media risk.' },
      { ticker: 'AMZN', company: 'Amazon', revenueGrowth: '+12%', operatingMargin: '11%', freeCashFlowMargin: '9%', forwardPe: '34.7x', note: 'Cloud competitor with a very different margin and reinvestment profile.' },
      { ticker: 'NVDA', company: 'NVIDIA', revenueGrowth: '+53%', operatingMargin: '58%', freeCashFlowMargin: '49%', forwardPe: '36.5x', note: 'AI infrastructure leader — a key Alphabet supplier and cloud workload driver.' },
    ],
    strengths: [
      'Search moat backed by first-party data, advertiser loyalty, and a network effect that has resisted disruption for over two decades.',
      'Google Cloud is now meaningfully profitable and growing faster than AWS, with AI demand broadening the customer base.',
      'One of the deepest balance sheets in global equities, with $95B net cash supporting buybacks and the AI investment cycle.',
    ],
    risks: [
      'AI-driven shifts in search behavior remain the primary structural risk to the core revenue engine.',
      'Regulatory pressure across Europe and the US creates ongoing compliance costs and potential remedies.',
      'Advertising cyclicality makes revenue more macro-sensitive than enterprise SaaS peers.',
    ],
    catalysts: [
      'Google Cloud reaching double-digit operating margins, establishing it as a third major cloud player.',
      'AI Overview and Gemini integration maintaining Search monetization while improving query relevance.',
      'Accelerating buyback pace as the balance sheet continues to generate strong free cash flow.',
    ],
    filingChecklist: [
      { title: 'Business and segment disclosures', cadence: 'Annual / quarterly', summary: 'Monitor Cloud growth rate, Search query volume, and YouTube revenue trajectory.', status: 'Priority' },
      { title: 'Management discussion and analysis', cadence: 'Quarterly', summary: 'Watch commentary on AI impact to Search and Cloud margin progression.', status: 'Reviewed' },
      { title: 'Cash flow statement', cadence: 'Quarterly', summary: 'Track buyback pace and capex commitment to confirm disciplined capital allocation.', status: 'Reviewed' },
      { title: 'Risk factors', cadence: 'Annual', summary: 'Focus on AI disruption to Search, antitrust remedies, and advertising cycle sensitivity.', status: 'Monitor' },
      { title: 'Capital allocation', cadence: 'Quarterly', summary: 'Confirm buyback acceleration is sustainable given the AI investment cycle.', status: 'Reviewed' },
    ],
  },
};

export function isCoverageTicker(ticker: string): ticker is CoverageTicker {
  return ticker in FUNDAMENTAL_PROFILES;
}

function resolveCoverageTicker(ticker?: string): string {
  const normalizedTicker = ticker?.trim().toUpperCase();
  return normalizedTicker || DEFAULT_TICKER;
}

function formatDollars(value: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  }).format(value);
}

function formatBillions(value: number) {
  return `$${value.toFixed(1)}B`;
}

function formatPercentage(value: number) {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
}

function formatMetricPercent(value: number | null | undefined) {
  return value === null || value === undefined ? 'N/A' : `${(value * 100).toFixed(1)}%`;
}

function formatMetricNumber(value: number | null | undefined, suffix = '') {
  return value === null || value === undefined ? 'N/A' : `${value.toFixed(2)}${suffix}`;
}

function toneFromRating(rating: FundamentalAnalysisResponse['rating']): AccentTone {
  if (rating === 'BUY') {
    return 'success';
  }
  if (rating === 'SELL') {
    return 'danger';
  }
  return 'warning';
}

export function profileFromFundamentalResponse(response: FundamentalAnalysisResponse): FundamentalProfile {
  const fallback = isCoverageTicker(response.ticker)
    ? FUNDAMENTAL_PROFILES[response.ticker]
    : FUNDAMENTAL_PROFILES[DEFAULT_TICKER];
  const keyMetrics = response.key_metrics;
  const ratingTone = toneFromRating(response.rating);
  const percentile = response.universe_percentile;
  const percentileText = percentile === null || percentile === undefined ? 'N/A' : `${(percentile * 100).toFixed(0)}th pct`;
  const rankText = response.relative_rank ? `#${response.relative_rank}` : 'N/A';
  const modelScoreText = response.model_score === null || response.model_score === undefined
    ? 'N/A'
    : response.model_score.toFixed(3);

  return {
    ...fallback,
    ticker: response.ticker,
    companyName: response.company_name,
    sector: response.sector ?? fallback.sector,
    headline: `${response.rating} fundamental read from the latest FinEdge model artifact.`,
    thesis: response.analysis_summary,
    qualityScore: response.score,
    qualityLabel: `${response.signal} signal with ${percentileText} universe standing`,
    shareholderYield: percentileText,
    balanceSheetLabel: `Source: ${response.data_source}${response.cached ? ' (cached/artifact-backed)' : ''}`,
    spotlightMetrics: [
      { label: 'Model score', value: modelScoreText },
      { label: 'Universe rank', value: rankText },
      { label: 'Signal date', value: response.source_signal_date ?? 'Latest' },
    ],
    lensNotes: {
      blend: {
        title: 'Model-backed fundamental read',
        summary: response.analysis_summary,
        question: 'Do the next filings confirm the model signal and the current peer ranking?',
        tone: ratingTone === 'danger' ? 'danger' : ratingTone === 'success' ? 'success' : 'warning',
      },
      quality: {
        title: 'Quality and financial health',
        summary: `${formatMetricPercent(keyMetrics.roe)} ROE, ${formatMetricPercent(
          keyMetrics.free_cash_flow_margin
        )} free-cash-flow margin, and ${response.trends.cash_flow.toLowerCase()} cash-flow trend.`,
        question: 'Is profitability being converted into durable free cash flow?',
        tone: keyMetrics.roe !== null && keyMetrics.roe !== undefined && keyMetrics.roe > 0.15 ? 'success' : 'info',
      },
      value: {
        title: 'Valuation discipline',
        summary: `P/E is ${formatMetricNumber(keyMetrics.pe_ratio)} while the model score is ${response.score.toFixed(1)} / 10.`,
        question: 'Does the current valuation leave enough margin for the fundamental signal?',
        tone: keyMetrics.pe_ratio !== null && keyMetrics.pe_ratio !== undefined && keyMetrics.pe_ratio > 35 ? 'warning' : 'info',
      },
    },
    scoreBands: [
      {
        label: 'Model signal',
        score: response.score,
        summary: `${response.signal} from the latest available fundamental model artifact.`,
        tone: ratingTone,
      },
      {
        label: 'Peer rank',
        score: percentile === null || percentile === undefined ? 5 : percentile * 10,
        summary: `${percentileText} across the model universe.`,
        tone: percentile !== null && percentile !== undefined && percentile >= 0.7 ? 'success' : 'info',
      },
      {
        label: 'Profitability',
        score: keyMetrics.roe === null || keyMetrics.roe === undefined ? 5 : Math.min(Math.max(keyMetrics.roe * 20, 0), 10),
        summary: `ROE: ${formatMetricPercent(keyMetrics.roe)}. Free-cash-flow margin: ${formatMetricPercent(
          keyMetrics.free_cash_flow_margin
        )}.`,
        tone: 'success',
      },
      {
        label: 'Growth trend',
        score:
          keyMetrics.revenue_growth_yoy === null || keyMetrics.revenue_growth_yoy === undefined
            ? 5
            : Math.min(Math.max((keyMetrics.revenue_growth_yoy + 0.2) * 25, 0), 10),
        summary: `Revenue growth: ${formatMetricPercent(keyMetrics.revenue_growth_yoy)}. Earnings growth: ${formatMetricPercent(
          keyMetrics.earnings_growth_yoy
        )}.`,
        tone: keyMetrics.revenue_growth_yoy !== null && keyMetrics.revenue_growth_yoy !== undefined && keyMetrics.revenue_growth_yoy < 0 ? 'warning' : 'info',
      },
    ],
    contextSignals: [
      { label: 'Rating', detail: response.rating },
      { label: 'Model signal', detail: response.signal },
      { label: 'Data source', detail: response.data_source },
    ],
    valuationChecks: [
      {
        label: 'P/E ratio',
        value: formatMetricNumber(keyMetrics.pe_ratio),
        benchmark: 'Lower is generally cheaper',
        summary: 'Direct valuation ratio from EODHD highlights when available.',
        tone: keyMetrics.pe_ratio !== null && keyMetrics.pe_ratio !== undefined && keyMetrics.pe_ratio > 35 ? 'warning' : 'info',
      },
      {
        label: 'Universe percentile',
        value: percentileText,
        benchmark: 'Model peer universe',
        summary: 'Cross-sectional model standing from the latest signal artifact.',
        tone: percentile !== null && percentile !== undefined && percentile >= 0.7 ? 'success' : 'info',
      },
      {
        label: 'Model score',
        value: `${response.score.toFixed(1)} / 10`,
        benchmark: 'FinEdge fundamental model',
        summary: response.analysis_summary,
        tone: ratingTone,
      },
    ],
    healthChecks: [
      {
        label: 'ROE',
        value: formatMetricPercent(keyMetrics.roe),
        benchmark: 'Profitability quality',
        summary: `Earnings trend is ${response.trends.earnings.toLowerCase()}.`,
        tone: keyMetrics.roe !== null && keyMetrics.roe !== undefined && keyMetrics.roe > 0.15 ? 'success' : 'info',
      },
      {
        label: 'Debt to equity',
        value: formatMetricNumber(keyMetrics.debt_to_equity),
        benchmark: 'Balance-sheet leverage',
        summary: 'Used as a quick financial risk checkpoint.',
        tone: keyMetrics.debt_to_equity !== null && keyMetrics.debt_to_equity !== undefined && keyMetrics.debt_to_equity > 2 ? 'warning' : 'success',
      },
      {
        label: 'FCF margin',
        value: formatMetricPercent(keyMetrics.free_cash_flow_margin),
        benchmark: 'Cash conversion',
        summary: `Cash-flow trend is ${response.trends.cash_flow.toLowerCase()}.`,
        tone:
          keyMetrics.free_cash_flow_margin !== null &&
          keyMetrics.free_cash_flow_margin !== undefined &&
          keyMetrics.free_cash_flow_margin > 0.15
            ? 'success'
            : 'info',
      },
    ],
    strengths: response.strengths.length ? response.strengths : fallback.strengths,
    risks: response.concerns.length ? response.concerns : fallback.risks,
    catalysts: [
      `Next model artifact refresh for ${response.ticker}`,
      'Upcoming quarterly filing updates',
      ...fallback.catalysts.slice(0, 1),
    ],
    filingChecklist: [
      {
        title: 'Latest model artifact',
        cadence: response.source_signal_date ?? 'Latest',
        summary: `${response.signal} signal, ${rankText} rank, ${percentileText} universe percentile.`,
        status: 'Reviewed',
      },
      {
        title: 'Financial statements',
        cadence: 'Quarterly',
        summary: 'Refresh EODHD fundamentals when new filings are published.',
        status: response.data_source.includes('eodhd') ? 'Reviewed' : 'Monitor',
      },
      ...fallback.filingChecklist.slice(0, 3),
    ],
  };
}

function statusVariant(status: FilingCheckpoint['status']): TagTone {
  if (status === 'Priority') {
    return 'warning';
  }

  if (status === 'Monitor') {
    return 'danger';
  }

  return 'success';
}

export interface FundamentalAnalysisPageProps {
  initialTicker?: string;
  showHero?: boolean;
  showControls?: boolean;
}

export default function FundamentalPage({
  initialTicker = DEFAULT_TICKER,
  showHero = true,
  showControls = true,
}: FundamentalAnalysisPageProps) {
  const resolvedInitialTicker = resolveCoverageTicker(initialTicker);
  const [ticker, setTicker] = useState<string>(resolvedInitialTicker);
  const [lens, setLens] = useState<AnalysisLens>('blend');
  const [status, setStatus] = useState<AnalysisStatus>(showHero ? 'idle' : 'loading');
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<FundamentalProfile>(
    isCoverageTicker(resolvedInitialTicker) ? FUNDAMENTAL_PROFILES[resolvedInitialTicker] : FUNDAMENTAL_PROFILES[DEFAULT_TICKER]
  );
  const [lastSubmittedTicker, setLastSubmittedTicker] = useState(resolvedInitialTicker);

  const runAnalysis = useCallback(async (nextTickerInput: string) => {
    const normalizedTicker = nextTickerInput.trim().toUpperCase();

    if (!normalizedTicker) {
      setStatus('error');
      setError('Enter a ticker to run fundamental analysis.');
      return;
    }

    setStatus('loading');
    setError(null);
    setLastSubmittedTicker(normalizedTicker);

    try {
      const response = await fundamentalApi.analyze({
        ticker: normalizedTicker,
        market: 'US',
        include_peer_context: true,
      });
      setProfile(profileFromFundamentalResponse(response));
      setStatus('success');
    } catch (apiError) {
      setStatus('error');
      setError(handleApiError(apiError));
    }
  }, []);

  useEffect(() => {
    const nextTicker = resolveCoverageTicker(initialTicker);
    setTicker(nextTicker);
    // Only auto-run when embedded (no hero), e.g. inside Dashboard modal
    if (!showHero) {
      void runAnalysis(nextTicker);
    }
  }, [initialTicker, runAnalysis, showHero]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    runAnalysis(ticker);
  };

  const onPresetSelect = (nextTicker: CoverageTicker) => {
    setTicker(nextTicker);
    runAnalysis(nextTicker);
  };

  const selectedLens = LENS_OPTIONS.find((option) => option.value === lens) ?? LENS_OPTIONS[0];
  const activeLensNote = profile.lensNotes[lens];
  const activeCoverageTicker = status === 'loading' ? lastSubmittedTicker : profile.ticker;

  const valuationDelta = useMemo(() => profile.fairValueBase - profile.price, [profile.fairValueBase, profile.price]);
  const valuationDeltaPct = useMemo(
    () => ((profile.fairValueBase - profile.price) / profile.price) * 100,
    [profile.fairValueBase, profile.price]
  );

  const valuationTone: AccentTone = valuationDelta >= 0 ? 'success' : 'danger';
  const shouldShowResults = status === 'success';
  const showIdleHero = status === 'idle' && showHero;

  return (
    <div className="space-y-6">
      {showHero && (
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-100">
            <Landmark size={20} className="text-blue-600" />
          </div>
          <div>
            <h1 className="text-2xl font-extrabold text-slate-950">Fundamental Analysis</h1>
            <p className="text-sm text-slate-500">ML model signals, financial health, and valuation</p>
          </div>
        </div>
      )}

      {showControls && (
        <Card className="border border-slate-200/90" variant="bordered" padding="none">
          <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5">
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div>
                <CardTitle className="text-2xl">Run Fundamental Analysis</CardTitle>
                <p className="mt-1 text-sm text-text-secondary">
                  Compare intrinsic value, cash generation, business quality, and filing-driven risk.
                </p>
              </div>
              <Tag variant="neutral" className="self-start md:self-auto">
                US large-cap coverage
              </Tag>
            </div>
          </CardHeader>
          <CardContent className="space-y-6 p-6">
            <form onSubmit={onSubmit} className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)_220px] xl:items-end">
              <div className="space-y-3">
                <Input
                  label="Ticker"
                  value={ticker}
                  onChange={(event) => setTicker(event.target.value.toUpperCase())}
                  placeholder="AAPL, MSFT, GOOGL, TSLA"
                  helperText="Requires the latest backend model artifact, with EODHD metrics when configured."
                  leftIcon={<Search size={18} />}
                />
                <div className="flex flex-wrap gap-2">
                  {COVERAGE_TICKERS.map((coverageTicker) => {
                    const isSelected = coverageTicker === activeCoverageTicker;
                    return (
                      <button
                        key={coverageTicker}
                        type="button"
                        onClick={() => onPresetSelect(coverageTicker)}
                        className={cn(
                          'rounded-full border px-3 py-1.5 text-sm font-medium transition-colors duration-200',
                          isSelected
                            ? 'border-primary-500 bg-blue-50 text-primary-700'
                            : 'border-slate-200 bg-white text-text-secondary hover:border-slate-300 hover:text-text-primary'
                        )}
                      >
                        {coverageTicker}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="grid gap-3">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-text-primary">Analysis Lens</label>
                  <span className="text-xs text-text-secondary">Prioritize what matters most</span>
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  {LENS_OPTIONS.map((option) => {
                    const isSelected = option.value === lens;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => setLens(option.value)}
                        className={cn(
                          'rounded-2xl border px-4 py-3 text-left transition-all duration-200',
                          isSelected
                            ? 'border-primary-500 bg-blue-50 shadow-[0_12px_28px_rgba(37,99,235,0.12)]'
                            : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                        )}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-base font-semibold text-text-primary">{option.label}</span>
                          <span
                            className={cn(
                              'h-3 w-3 rounded-full border',
                              isSelected ? 'border-primary-600 bg-primary-600' : 'border-slate-300 bg-white'
                            )}
                          />
                        </div>
                        <p className="mt-2 text-sm leading-5 text-text-secondary">{option.summary}</p>
                      </button>
                    );
                  })}
                </div>
              </div>

              <Button type="submit" size="lg" fullWidth isLoading={status === 'loading'} className="h-[52px] text-base">
                Analyze Fundamentals
              </Button>
            </form>

            {status === 'loading' && (
              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50/80">
                <div className="border-b border-slate-200 px-4 py-3">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-sm font-medium text-text-primary">
                      Building the fundamental stack for {lastSubmittedTicker}
                    </p>
                    <span className="text-xs text-text-secondary">
                      Statement review, ratio stack, and scenario valuation
                    </span>
                  </div>
                </div>
                <div className="px-4 py-4">
                  <div className="h-2 rounded-full bg-slate-200 progress-indeterminate" />
                  <div className="mt-3 grid gap-3 text-xs text-text-secondary md:grid-cols-3">
                    <ProgressStep label="1. Filing digest" description="Refreshing the business, risk, and management narrative." />
                    <ProgressStep label="2. Ratio stack" description="Updating valuation, profitability, and balance-sheet checkpoints." />
                    <ProgressStep label="3. Scenario view" description={`Applying the ${selectedLens.label.toLowerCase()} to intrinsic value.`} />
                  </div>
                </div>
              </div>
            )}

            {error && (
              <div className="rounded-2xl border border-danger-200 bg-danger-50 px-4 py-3 text-danger-900">
                {error}
                <p className="mt-2 text-sm">
                  The results area will stay hidden until the backend returns a model-backed signal.
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {shouldShowResults && (
        <>
          {/* Coverage summary — shown after analysis runs */}
          {showHero && (
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white px-5 py-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-1">Current Coverage</p>
                <p className="text-xl font-extrabold text-slate-950">
                  {profile.ticker} <span className="text-slate-500 font-normal">{profile.companyName}</span>
                </p>
              </div>
              <div className="flex gap-4 flex-wrap">
                {profile.spotlightMetrics.map((metric) => (
                  <div key={metric.label} className="text-right">
                    <p className="text-xs text-slate-400">{metric.label}</p>
                    <p className="text-sm font-extrabold text-slate-950">{metric.value}</p>
                  </div>
                ))}
                {profile.sector && <span className="self-center rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-bold text-slate-600">{profile.sector}</span>}
              </div>
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <MetricCard
              icon={<Wallet size={18} />}
              label="Market Price"
              value={formatDollars(profile.price)}
              detail={`${profile.marketCap} market cap`}
            />
            <MetricCard
              icon={<Landmark size={18} />}
              label="Base Fair Value"
              value={formatDollars(profile.fairValueBase)}
              detail={`${formatDollars(profile.fairValueLow)} to ${formatDollars(profile.fairValueHigh)} scenario range`}
              accent="info"
            />
            <MetricCard
              icon={valuationDelta >= 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
              label="Valuation Gap"
              value={formatPercentage(valuationDeltaPct)}
              detail={`${valuationDelta >= 0 ? '+' : '-'}${formatDollars(Math.abs(valuationDelta))} versus base case`}
              accent={valuationTone}
            />
            <MetricCard
              icon={<ShieldCheck size={18} />}
              label="Quality Score"
              value={`${profile.qualityScore.toFixed(1)} / 10`}
              detail={profile.qualityLabel}
              accent="success"
            />
            <MetricCard
              icon={<Sparkles size={18} />}
              label="Shareholder Yield"
              value={profile.shareholderYield}
              detail={profile.balanceSheetLabel}
            />
          </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
        <Card className="border border-slate-200/90" variant="bordered" padding="none">
          <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div>
                <CardTitle className="text-xl">Investment Brief</CardTitle>
                <p className="mt-1 text-sm text-text-secondary">{profile.headline}</p>
              </div>
              <Tag variant={activeLensNote.tone}>{selectedLens.label}</Tag>
            </div>
          </CardHeader>
          <CardContent className="space-y-6 p-6">
            <div className="rounded-3xl border border-slate-200 bg-slate-50/80 p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-text-secondary">Core Thesis</p>
              <p className="mt-3 text-base leading-7 text-text-primary">{profile.thesis}</p>
              <div className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-text-primary">{activeLensNote.title}</p>
                    <p className="mt-1 text-sm leading-6 text-text-secondary">{activeLensNote.summary}</p>
                  </div>
                  <Tag variant={activeLensNote.tone} size="sm">
                    {profile.ticker}
                  </Tag>
                </div>
                <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.15em] text-text-secondary">Question in focus</p>
                  <p className="mt-2 text-sm text-text-primary">{activeLensNote.question}</p>
                </div>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              {profile.scenarios.map((scenario) => (
                <ScenarioCard key={scenario.label} scenario={scenario} />
              ))}
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              {profile.contextSignals.map((signal) => (
                <ContextCard key={signal.label} label={signal.label} detail={signal.detail} />
              ))}
            </div>
          </CardContent>
        </Card>

        <Card className="border border-slate-200/90" variant="bordered" padding="none">
          <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5">
            <div>
              <CardTitle className="text-xl">Business Mix</CardTitle>
              <p className="mt-1 text-sm text-text-secondary">
                The segment structure that drives durability, operating leverage, and downside cover.
              </p>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 p-6">
            {profile.segments.map((segment) => (
              <SegmentCard key={segment.name} segment={segment} />
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <Card className="border border-slate-200/90" variant="bordered" padding="none">
          <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5">
            <div>
              <CardTitle className="text-xl">Financial Trajectory</CardTitle>
              <p className="mt-1 text-sm text-text-secondary">
                Multi-period trend review across growth, earnings power, cash generation, and returns on capital.
              </p>
            </div>
          </CardHeader>
          <CardContent className="grid gap-4 p-6 md:grid-cols-2">
            <TrendPanel
              title="Revenue"
              caption="Top-line scale"
              entries={profile.financials}
              valueAccessor={(entry) => entry.revenue}
              formatter={(value) => formatBillions(value)}
              tone="info"
            />
            <TrendPanel
              title="Free Cash Flow"
              caption="Cash earnings"
              entries={profile.financials}
              valueAccessor={(entry) => entry.freeCashFlow}
              formatter={(value) => formatBillions(value)}
              tone="success"
            />
            <TrendPanel
              title="Operating Margin"
              caption="Profitability"
              entries={profile.financials}
              valueAccessor={(entry) => entry.operatingMargin}
              formatter={(value) => `${value.toFixed(1)}%`}
              tone="default"
            />
            <TrendPanel
              title="ROIC"
              caption="Capital efficiency"
              entries={profile.financials}
              valueAccessor={(entry) => entry.roic}
              formatter={(value) => `${value.toFixed(1)}%`}
              tone="success"
            />
          </CardContent>
        </Card>

        <Card className="border border-slate-200/90" variant="bordered" padding="none">
          <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5">
            <div>
              <CardTitle className="text-xl">Fundamental Scorecard</CardTitle>
              <p className="mt-1 text-sm text-text-secondary">
                A clean view of what is driving conviction and what still needs a discount.
              </p>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 p-6">
            {profile.scoreBands.map((scoreBand) => (
              <ScoreRow key={scoreBand.label} scoreBand={scoreBand} />
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        {/* Quality Lens puts Health first; Value Lens puts Valuation first; Balanced is alphabetical */}
        {(lens === 'quality' ? [
          { title: 'Financial Health', subtitle: 'Quality metrics: profitability, cash conversion, and balance sheet strength.', checks: profile.healthChecks, isFirst: true },
          { title: 'Relative Valuation', subtitle: 'Benchmark headline multiples against growth and cash conversion.', checks: profile.valuationChecks, isFirst: false },
        ] : lens === 'value' ? [
          { title: 'Relative Valuation', subtitle: 'Value Lens: focus on multiples, earnings yield, and margin of safety.', checks: profile.valuationChecks, isFirst: true },
          { title: 'Financial Health', subtitle: 'Test resilience through leverage, liquidity, and capital allocation.', checks: profile.healthChecks, isFirst: false },
        ] : [
          { title: 'Relative Valuation', subtitle: 'Benchmark headline multiples against growth, cash conversion, and the peer stack.', checks: profile.valuationChecks, isFirst: true },
          { title: 'Financial Health', subtitle: 'Test resilience through leverage, liquidity, cash conversion, and capital allocation.', checks: profile.healthChecks, isFirst: false },
        ]).map(({ title, subtitle, checks }) => (
          <Card key={title} className="border border-slate-200/90" variant="bordered" padding="none">
            <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5">
              <div>
                <CardTitle className="text-xl">{title}</CardTitle>
                <p className="mt-1 text-sm text-text-secondary">{subtitle}</p>
              </div>
            </CardHeader>
            <CardContent className="grid gap-4 p-6 md:grid-cols-2">
              {checks.map((check) => (
                <RatioCard key={check.label} check={check} />
              ))}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="border border-slate-200/90" variant="bordered" padding="none">
        <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <CardTitle className="text-xl">Peer Comparison</CardTitle>
              <p className="mt-1 text-sm text-text-secondary">
                Compare growth, margin quality, cash generation, and valuation against the closest public alternatives.
              </p>
            </div>
            <Tag variant="neutral">{profile.ticker} in focus</Tag>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-left">
              <thead className="bg-slate-50 text-xs uppercase tracking-[0.18em] text-text-secondary">
                <tr>
                  <th className="px-6 py-4 font-semibold">Company</th>
                  <th className="px-6 py-4 font-semibold">Revenue Growth</th>
                  <th className="px-6 py-4 font-semibold">Op Margin</th>
                  <th className="px-6 py-4 font-semibold">FCF Margin</th>
                  <th className="px-6 py-4 font-semibold">Forward P/E</th>
                  <th className="px-6 py-4 font-semibold">Takeaway</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white text-sm text-text-primary">
                {profile.peers.map((peer) => {
                  const isCurrent = peer.ticker === profile.ticker;
                  return (
                    <tr key={peer.ticker} className={cn(isCurrent && 'bg-blue-50/55')}>
                      <td className="px-6 py-4 align-top">
                        <div className="flex items-center gap-3">
                          <div
                            className={cn(
                              'flex h-10 w-10 items-center justify-center rounded-2xl text-sm font-semibold',
                              isCurrent ? 'bg-primary-600 text-white' : 'bg-slate-100 text-slate-700'
                            )}
                          >
                            {peer.ticker}
                          </div>
                          <div>
                            <p className="font-semibold text-text-primary">{peer.company}</p>
                            <p className="text-xs text-text-secondary">{peer.ticker}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 align-top">{peer.revenueGrowth}</td>
                      <td className="px-6 py-4 align-top">{peer.operatingMargin}</td>
                      <td className="px-6 py-4 align-top">{peer.freeCashFlowMargin}</td>
                      <td className="px-6 py-4 align-top">{peer.forwardPe}</td>
                      <td className="px-6 py-4 align-top text-text-secondary">{peer.note}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(320px,0.9fr)]">
        <Card className="border border-slate-200/90" variant="bordered" padding="none">
          <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5">
            <div>
              <CardTitle className="text-xl">Quality, Risk, and Catalysts</CardTitle>
              <p className="mt-1 text-sm text-text-secondary">
                Blend the quantitative stack with business quality, management execution, and scenario triggers.
              </p>
            </div>
          </CardHeader>
          <CardContent className="grid gap-4 p-6 lg:grid-cols-3">
            <InsightColumn
              title="Strengths"
              icon={<ShieldCheck size={18} />}
              tone="success"
              items={profile.strengths}
            />
            <InsightColumn
              title="Risks"
              icon={<CircleAlert size={18} />}
              tone="danger"
              items={profile.risks}
            />
            <InsightColumn
              title="Catalysts"
              icon={<ArrowUpRight size={18} />}
              tone="info"
              items={profile.catalysts}
            />
          </CardContent>
        </Card>

        <Card className="border border-slate-200/90" variant="bordered" padding="none">
          <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5">
            <div>
              <CardTitle className="text-xl">Filing Checklist</CardTitle>
              <p className="mt-1 text-sm text-text-secondary">
                The annual and quarterly checkpoints that should validate or challenge the thesis.
              </p>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 p-6">
            {profile.filingChecklist.map((checkpoint) => (
              <div key={checkpoint.title} className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="flex items-start gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-900 text-white">
                      <FileText size={18} />
                    </div>
                    <div>
                      <p className="font-semibold text-text-primary">{checkpoint.title}</p>
                      <p className="mt-1 text-sm text-text-secondary">{checkpoint.summary}</p>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <Tag variant="neutral" size="sm">
                      {checkpoint.cadence}
                    </Tag>
                    <Tag variant={statusVariant(checkpoint.status)} size="sm">
                      {checkpoint.status}
                    </Tag>
                  </div>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
        </>
      )}
    </div>
  );
}

function HeroPill({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 shadow-card">
      {icon}
      <span>{text}</span>
    </div>
  );
}

function ProgressStep({ label, description }: { label: string; description: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-3 py-3">
      <p className="font-medium text-text-primary">{label}</p>
      <p className="mt-1 leading-5">{description}</p>
    </div>
  );
}

function MetricCard({
  icon,
  label,
  value,
  detail,
  accent = 'default',
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
  accent?: AccentTone;
}) {
  const tone = TONE_STYLES[accent];

  return (
    <Card className={cn('border', tone.card)} variant="bordered" padding="none">
      <CardContent className="flex items-start gap-4 p-5">
        <div className={cn('flex h-11 w-11 items-center justify-center rounded-2xl text-white', tone.icon)}>
          {icon}
        </div>
        <div>
          <p className="text-sm text-text-secondary">{label}</p>
          <p className="mt-1 text-2xl font-semibold text-text-primary">{value}</p>
          <p className="mt-1 text-sm text-text-secondary">{detail}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function ScenarioCard({ scenario }: { scenario: Scenario }) {
  const tone = TONE_STYLES[scenario.tone];

  return (
    <div className={cn('rounded-2xl border p-4', tone.card)}>
      <div className="flex items-center justify-between gap-3">
        <Tag variant={tone.badge} size="sm">
          {scenario.label}
        </Tag>
        <span className="text-xs font-semibold uppercase tracking-[0.18em]">{scenario.probability}%</span>
      </div>
      <p className="mt-4 text-2xl font-semibold">{formatDollars(scenario.price)}</p>
      <p className="mt-2 text-sm leading-6">{scenario.summary}</p>
    </div>
  );
}

function ContextCard({ label, detail }: ContextSignal) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-text-secondary">{label}</p>
      <p className="mt-2 text-sm leading-6 text-text-primary">{detail}</p>
    </div>
  );
}

function SegmentCard({ segment }: { segment: SegmentMix }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <p className="font-semibold text-text-primary">{segment.name}</p>
            <Tag variant="neutral" size="sm">
              {segment.share}% mix
            </Tag>
          </div>
          <p className="mt-2 text-sm leading-6 text-text-secondary">{segment.note}</p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Tag variant="success" size="sm">
            Growth {segment.growth}
          </Tag>
          <Tag variant="info" size="sm">
            Margin {segment.margin}
          </Tag>
        </div>
      </div>
      <div className="mt-4 h-2 rounded-full bg-slate-200">
        <div className="h-full rounded-full bg-gradient-to-r from-primary-500 to-primary-600" style={{ width: `${segment.share}%` }} />
      </div>
    </div>
  );
}

function TrendPanel({
  title,
  caption,
  entries,
  valueAccessor,
  formatter,
  tone,
}: {
  title: string;
  caption: string;
  entries: FinancialSnapshot[];
  valueAccessor: (entry: FinancialSnapshot) => number;
  formatter: (value: number) => string;
  tone: AccentTone;
}) {
  const maxValue = Math.max(...entries.map((entry) => valueAccessor(entry)));
  const toneStyles = TONE_STYLES[tone];
  const latestValue = valueAccessor(entries[entries.length - 1]);

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-text-primary">{title}</p>
          <p className="text-xs text-text-secondary">{caption}</p>
        </div>
        <Tag variant={toneStyles.badge} size="sm">
          {formatter(latestValue)} latest
        </Tag>
      </div>
      <div className="mt-4 space-y-3">
        {entries.map((entry) => {
          const value = valueAccessor(entry);
          const width = maxValue === 0 ? 0 : Math.max((value / maxValue) * 100, 8);

          return (
            <div key={`${title}-${entry.period}`}>
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="font-medium text-text-primary">{entry.period}</span>
                <span className="text-text-secondary">{formatter(value)}</span>
              </div>
              <div className="mt-1 h-2 rounded-full bg-slate-200">
                <div className={cn('h-full rounded-full', toneStyles.bar)} style={{ width: `${width}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ScoreRow({ scoreBand }: { scoreBand: ScoreBand }) {
  const tone = TONE_STYLES[scoreBand.tone];

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-semibold text-text-primary">{scoreBand.label}</p>
          <p className="mt-1 text-sm text-text-secondary">{scoreBand.summary}</p>
        </div>
        <Tag variant={tone.badge}>{scoreBand.score.toFixed(1)} / 10</Tag>
      </div>
      <div className="mt-4 h-2 rounded-full bg-slate-200">
        <div className={cn('h-full rounded-full', tone.bar)} style={{ width: `${scoreBand.score * 10}%` }} />
      </div>
    </div>
  );
}

function RatioCard({ check }: { check: RatioCheck }) {
  const tone = TONE_STYLES[check.tone];

  return (
    <div className={cn('rounded-2xl border p-4', tone.card)}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold">{check.label}</p>
        <Tag variant={tone.badge} size="sm">
          {check.benchmark}
        </Tag>
      </div>
      <p className="mt-4 text-2xl font-semibold">{check.value}</p>
      <p className="mt-2 text-sm leading-6">{check.summary}</p>
    </div>
  );
}

function InsightColumn({
  title,
  icon,
  tone,
  items,
}: {
  title: string;
  icon: ReactNode;
  tone: AccentTone;
  items: string[];
}) {
  const toneStyles = TONE_STYLES[tone];

  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
      <div className="flex items-center gap-3">
        <div className={cn('flex h-10 w-10 items-center justify-center rounded-2xl text-white', toneStyles.icon)}>
          {icon}
        </div>
        <div>
          <p className="font-semibold text-text-primary">{title}</p>
          <Tag variant={toneStyles.badge} size="sm" className="mt-1">
            {items.length} items
          </Tag>
        </div>
      </div>
      <div className="mt-4 space-y-3">
        {items.map((item) => (
          <div key={item} className="rounded-2xl border border-slate-200 bg-white px-3 py-3 text-sm leading-6 text-text-primary">
            {item}
          </div>
        ))}
      </div>
    </div>
  );
}
