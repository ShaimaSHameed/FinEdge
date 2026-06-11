'use client';

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

type Timeframe = '1D' | '5D' | '1M' | '6M' | 'YTD' | '1Y';

const INTERVAL_MAP: Record<Timeframe, string> = {
  '1D': '5',
  '5D': '15',
  '1M': '60',
  '6M': 'D',
  'YTD': 'D',
  '1Y': 'W',
};

const RANGE_MAP: Record<Timeframe, string> = {
  '1D': '1D',
  '5D': '5D',
  '1M': '1M',
  '6M': '6M',
  'YTD': 'YTD',
  '1Y': '12M',
};

const EXCHANGE_MAP: Record<string, string> = {
  MSFT: 'NASDAQ',
  GOOGL: 'NASDAQ',
  AAPL: 'NASDAQ',
  NVDA: 'NASDAQ',
  META: 'NASDAQ',
  AMZN: 'NASDAQ',
};

declare global {
  interface Window {
    TradingView: { widget: new (config: Record<string, unknown>) => void };
  }
}

interface Props {
  ticker: string;
  height?: number;
  defaultTimeframe?: Timeframe;
}

export function TradingViewChart({ ticker, height = 440, defaultTimeframe = '1D' }: Props) {
  const [activeTimeframe, setActiveTimeframe] = useState<Timeframe>(defaultTimeframe);
  const containerRef = useRef<HTMLDivElement>(null);
  const idRef = useRef(`tv_${ticker}_${Math.random().toString(36).substr(2, 6)}`);
  const TIMEFRAMES: Timeframe[] = ['1D', '5D', '1M', '6M', 'YTD', '1Y'];

  useEffect(() => {
    const id = idRef.current;

    const buildWidget = () => {
      if (!containerRef.current || !window.TradingView) return;
      containerRef.current.innerHTML = `<div id="${id}" style="height:${height}px"></div>`;

      new window.TradingView.widget({
        container_id: id,
        autosize: true,
        symbol: `${EXCHANGE_MAP[ticker] ?? 'NASDAQ'}:${ticker}`,
        interval: INTERVAL_MAP[activeTimeframe],
        range: RANGE_MAP[activeTimeframe],
        timezone: 'America/New_York',
        theme: 'light',
        style: '1',
        locale: 'en',
        toolbar_bg: '#ffffff',
        enable_publishing: false,
        allow_symbol_change: false,
        hide_side_toolbar: true,
        withdateranges: false,
        details: false,
        hotlist: false,
        calendar: false,
        show_popup_button: false,
      });
    };

    if (window.TradingView) {
      buildWidget();
    } else {
      const script = document.createElement('script');
      script.src = 'https://s3.tradingview.com/tv.js';
      script.async = true;
      script.onload = buildWidget;
      document.head.appendChild(script);
    }

    return () => {
      if (containerRef.current) containerRef.current.innerHTML = '';
    };
  }, [ticker, activeTimeframe, height]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1 rounded-xl bg-slate-100/80 p-1 w-fit">
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            type="button"
            onClick={() => setActiveTimeframe(tf)}
            className={cn(
              'rounded-lg px-3 py-1.5 text-xs font-bold transition-all duration-150',
              activeTimeframe === tf
                ? 'bg-white text-slate-950 shadow-sm'
                : 'text-slate-500 hover:text-slate-800'
            )}
          >
            {tf}
          </button>
        ))}
      </div>
      <div
        ref={containerRef}
        style={{ height: `${height}px` }}
        className="w-full overflow-hidden rounded-2xl border border-slate-200 bg-slate-50"
      />
    </div>
  );
}
