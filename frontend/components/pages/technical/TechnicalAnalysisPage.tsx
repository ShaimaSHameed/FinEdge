'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Activity,
  CandlestickChart,
  Clock3,
  Database,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { TechnicalCandlesChart } from '@/components/charts';
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Tag } from '@/components/ui';
import { cn, handleApiError, technicalApi } from '@/lib';
import type { TechnicalAnalysisResponse } from '@/types';

const DEFAULT_TICKER = 'MSFT';
const DEFAULT_MODEL = 'final_1d';

type ModelVersion = 'final_1d' | 'final_1min';
type AnalysisStatus = 'idle' | 'loading' | 'success' | 'error';

const MODEL_OPTIONS: Array<{
  value: ModelVersion;
  label: string;
  summary: string;
  defaultTicker: string;
  historyBars: number;
  forecastBars: number;
  timeframeLabel: string;
  helperText: string;
}> = [
  {
    value: 'final_1d',
    label: 'Final 1D Ensemble',
    summary: 'Real GRU ensemble with RL policy overlay from the mounted technical artifacts.',
    defaultTicker: 'MSFT',
    historyBars: 90,
    forecastBars: 7,
    timeframeLabel: '1D',
    helperText: 'Uses daily US equity candles for the final 1D technical model.',
  },
  {
    value: 'final_1min',
    label: 'Final 1Min Ensemble',
    summary: 'One-minute artifact bundle for near-term candles, using Alpaca minute data.',
    defaultTicker: 'BTC/USD',
    historyBars: 120,
    forecastBars: 15,
    timeframeLabel: '1Min',
    helperText: 'Uses Alpaca one-minute candles. BTC/USD routes through Alpaca crypto data.',
  },
];

export default function TechnicalPage() {
  const [ticker, setTicker] = useState(DEFAULT_TICKER);
  const [modelVersion, setModelVersion] = useState<ModelVersion>(DEFAULT_MODEL);
  const [status, setStatus] = useState<AnalysisStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<TechnicalAnalysisResponse | null>(null);
  const [lastSubmittedTicker, setLastSubmittedTicker] = useState(DEFAULT_TICKER);
  const initialRequestStarted = useRef(false);

  const runAnalysis = useCallback(async (nextTicker: string, nextModel: ModelVersion) => {
    const normalizedTicker = nextTicker.trim().toUpperCase();
    const modelConfig = MODEL_OPTIONS.find((option) => option.value === nextModel) ?? MODEL_OPTIONS[0];

    if (!normalizedTicker) {
      setError('Enter a valid ticker or crypto symbol.');
      setStatus('error');
      return;
    }

    setStatus('loading');
    setError(null);
    setLastSubmittedTicker(normalizedTicker);

    try {
      const response = await technicalApi.analyze({
        ticker: normalizedTicker,
        model_version: nextModel,
        history_bars: modelConfig.historyBars,
        forecast_bars: modelConfig.forecastBars,
      });
      setAnalysis(response);
      setStatus('success');
    } catch (analysisError) {
      setStatus('error');
      setError(handleApiError(analysisError));
    }
  }, []);

  useEffect(() => {
    if (initialRequestStarted.current) {
      return;
    }
    initialRequestStarted.current = true;
    void runAnalysis(DEFAULT_TICKER, DEFAULT_MODEL);
  }, [runAnalysis]);

  const onSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await runAnalysis(ticker, modelVersion);
  };

  const forecastStats = useMemo(() => {
    if (!analysis) {
      return null;
    }

    const lastForecast = analysis.forecast_bars[analysis.forecast_bars.length - 1];
    const projectedMove = lastForecast.close - analysis.latest_price;
    const projectedMovePct = analysis.latest_price > 0
      ? (projectedMove / analysis.latest_price) * 100
      : 0;

    return {
      lastForecast,
      projectedMove,
      projectedMovePct,
      direction: projectedMove >= 0 ? 'up' : 'down',
    };
  }, [analysis]);

  const selectedModel = MODEL_OPTIONS.find((option) => option.value === modelVersion) ?? MODEL_OPTIONS[0];
  const selectModel = (nextModel: ModelVersion) => {
    const option = MODEL_OPTIONS.find((item) => item.value === nextModel) ?? MODEL_OPTIONS[0];
    setModelVersion(nextModel);
    if (ticker.trim().toUpperCase() === selectedModel.defaultTicker) {
      setTicker(option.defaultTicker);
    }
  };

  return (
    <div className="space-y-6">
      <div className="mx-auto max-w-5xl text-center">
        <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-extrabold uppercase tracking-[0.18em] text-slate-500 shadow-card">
          <CandlestickChart size={14} className="text-primary-600" />
          Multi-Timeframe Forecasting
        </div>
        <div className="mt-6 space-y-3">
          <h1 className="text-4xl font-extrabold tracking-[-0.04em] text-slate-950 md:text-6xl">Technical Analysis</h1>
          <p className="mx-auto max-w-3xl text-sm leading-6 text-slate-500 md:text-base">
            Choose the daily or one-minute artifact model, fetch the matching candle feed, and project
            the next candles with the ensemble and RL policy.
          </p>
        </div>
        <div className="mt-5 flex flex-wrap justify-center gap-2 text-xs font-bold text-slate-600">
          <HeroPill icon={<Clock3 size={14} />} text="1D and 1Min modes" />
          <HeroPill icon={<CandlestickChart size={14} />} text="Separate candle requirements" />
          <HeroPill icon={<Sparkles size={14} />} text="Real model artifacts" />
        </div>
      </div>

      <Card className="border border-slate-200/90" variant="bordered">
        <CardHeader className="mb-0 border-b border-slate-200 px-6 py-5">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <CardTitle className="text-2xl">Run Technical Analysis</CardTitle>
              <p className="mt-1 text-sm text-text-secondary">
                Pick the model timeframe, then run the matching artifact-backed price-path projection.
              </p>
            </div>
            <Tag variant="neutral" className="self-start md:self-auto">
              1D equities / 1Min BTC or equities
            </Tag>
          </div>
        </CardHeader>
        <CardContent className="p-6">
          <form onSubmit={onSubmit} className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)_220px] xl:items-end">
            <Input
              label="Ticker"
              value={ticker}
              onChange={(event) => setTicker(event.target.value.toUpperCase())}
              placeholder={selectedModel.value === 'final_1min' ? 'BTC/USD, MSFT' : 'MSFT, AAPL, NVDA'}
              helperText={selectedModel.helperText}
            />

            <div className="grid gap-3">
              <div className="flex items-center justify-between">
                <label className="text-sm font-medium text-text-primary">Model Version</label>
                <span className="text-xs text-text-secondary">Docker-mounted artifact bundle</span>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                {MODEL_OPTIONS.map((option) => {
                  const selected = option.value === modelVersion;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => selectModel(option.value)}
                      className={cn(
                        'rounded-2xl border px-4 py-3 text-left transition-all duration-200',
                        selected
                          ? 'border-primary-500 bg-blue-50 shadow-[0_12px_28px_rgba(37,99,235,0.12)]'
                          : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                      )}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-base font-semibold text-text-primary">{option.label}</span>
                        <span
                          className={cn(
                            'h-3 w-3 rounded-full border',
                            selected ? 'border-primary-600 bg-primary-600' : 'border-slate-300 bg-white'
                          )}
                        />
                      </div>
                      <p className="mt-2 text-sm leading-5 text-text-secondary">{option.summary}</p>
                      <p className="mt-2 text-xs font-medium text-primary-700">
                        {option.historyBars} history candles / {option.forecastBars} forecast candles / {option.timeframeLabel}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            <Button type="submit" size="lg" fullWidth isLoading={status === 'loading'} className="h-[52px]">
              Analyze {selectedModel.timeframeLabel} Chart
            </Button>
          </form>

          {status === 'loading' && (
            <div className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50/80">
              <div className="border-b border-slate-200 px-4 py-3">
                <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                  <p className="text-sm font-medium text-text-primary">
                    Generating outlook for {lastSubmittedTicker}
                  </p>
                  <span className="text-xs text-text-secondary">
                    Fetching {selectedModel.timeframeLabel} bars and producing {selectedModel.forecastBars} projected candles
                  </span>
                </div>
              </div>
              <div className="px-4 py-4">
                <div className="h-2 rounded-full bg-slate-200 progress-indeterminate" />
                <div className="mt-3 grid gap-3 text-xs text-text-secondary md:grid-cols-3">
                  <ProgressStep label="1. Market data" description={`Pulling the latest ${selectedModel.timeframeLabel} candles.`} />
                  <ProgressStep label="2. Model inference" description={`Running ${selectedModel.label}.`} />
                  <ProgressStep label="3. Chart overlay" description={`Projecting ${selectedModel.forecastBars} forward candles on the chart.`} />
                </div>
              </div>
            </div>
          )}

          {error && (
            <div className="mt-6 rounded-2xl border border-danger-200 bg-danger-50 px-4 py-3 text-danger-900">
              {error}
            </div>
          )}
        </CardContent>
      </Card>

      {analysis && forecastStats && (
        <div className="space-y-5">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              icon={<Activity size={18} />}
              label="Latest Price"
              value={`$${analysis.latest_price.toFixed(2)}`}
              detail={`Updated ${new Date(analysis.generated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`}
            />
            <MetricCard
              icon={<CandlestickChart size={18} />}
              label="Forecast End"
              value={`$${forecastStats.lastForecast.close.toFixed(2)}`}
              detail={`${analysis.forecast_bars.length} candles ahead`}
            />
            <MetricCard
              icon={forecastStats.direction === 'up' ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
              label="Projected Move"
              value={`${forecastStats.projectedMove >= 0 ? '+' : ''}${forecastStats.projectedMovePct.toFixed(2)}%`}
              detail={`${forecastStats.projectedMove >= 0 ? '+' : ''}$${forecastStats.projectedMove.toFixed(2)} vs latest close`}
              accent={forecastStats.direction === 'up' ? 'success' : 'danger'}
            />
            <MetricCard
              icon={<Database size={18} />}
              label="Data Feed"
              value={analysis.data_source.includes('alpaca') ? 'Alpaca' : 'Fallback feed'}
              detail={`${analysis.inference_input_bars} Alpaca bars / ${analysis.regime ?? 'NORMAL'}`}
            />
          </div>

          <TechnicalCandlesChart
            ticker={analysis.ticker}
            modelVersion={analysis.model_version}
            history={analysis.history_bars}
            forecast={analysis.forecast_bars}
            dataSource={analysis.data_source}
            timeframe={analysis.timeframe}
          />
        </div>
      )}
    </div>
  );
}

function HeroPill({ icon, text }: { icon: React.ReactNode; text: string }) {
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
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
  accent?: 'default' | 'success' | 'danger';
}) {
  return (
    <Card
      className={cn(
        'border border-slate-200/90',
        accent === 'success' && 'border-emerald-200 bg-emerald-50/55',
        accent === 'danger' && 'border-rose-200 bg-rose-50/60'
      )}
      variant="bordered"
    >
      <CardContent className="flex items-start gap-4 p-5">
        <div
          className={cn(
            'flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-900 text-white',
            accent === 'success' && 'bg-emerald-600',
            accent === 'danger' && 'bg-rose-600'
          )}
        >
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
