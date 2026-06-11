'use client';

import { useEffect, useState } from 'react';
import { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { Circle } from 'lucide-react';

interface MarketStatus {
  status: 'open' | 'pre' | 'after' | 'closed';
  label: string;
}

function getMarketStatus(): MarketStatus {
  const now = new Date();
  const etNow = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const uaeNow = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Dubai' }));

  const day = etNow.getDay(); // 0=Sun, 1=Mon, ..., 6=Sat
  const et = etNow.getHours() * 60 + etNow.getMinutes();

  const uaeH = uaeNow.getHours();
  const uaeM = uaeNow.getMinutes();
  const uaeTime = `${uaeH % 12 === 0 ? 12 : uaeH % 12}:${String(uaeM).padStart(2, '0')} ${uaeH >= 12 ? 'PM' : 'AM'} UAE`;

  const fmt = (mins: number) => {
    if (mins >= 1440) return `${Math.floor(mins / 1440)}d ${Math.floor((mins % 1440) / 60)}h`;
    return `${Math.floor(mins / 60)}h ${mins % 60}m`;
  };

  // Minutes until next weekday 9:30 AM ET (570 mins)
  const minsToNextOpen = (): number => {
    // mins remaining today until midnight
    const tillMidnight = 1440 - et;
    if (day === 6) { // Saturday → Monday = 2 days
      return tillMidnight + 1440 + 570;
    }
    if (day === 0) { // Sunday → Monday = 1 day
      return tillMidnight + 570;
    }
    // Weekday but market not open yet or already past
    if (et < 570) return 570 - et;
    // Weekday after close → next day (skip weekend if Friday)
    if (day === 5) return tillMidnight + 1440 + 1440 + 570; // Friday → Monday
    return tillMidnight + 570;
  };

  // Weekend
  if (day === 0 || day === 6) {
    return { status: 'closed', label: `NYSE Closed · Opens in ${fmt(minsToNextOpen())} · ${uaeTime}` };
  }
  // Pre-market 4:00–9:30 AM ET
  if (et >= 240 && et < 570) {
    return { status: 'pre', label: `Pre-Market · Opens in ${fmt(570 - et)} · ${uaeTime}` };
  }
  // Market open 9:30 AM–4:00 PM ET
  if (et >= 570 && et < 960) {
    return { status: 'open', label: `NYSE Open · Closes in ${fmt(960 - et)} · ${uaeTime}` };
  }
  // After hours 4:00–8:00 PM ET
  if (et >= 960 && et < 1200) {
    return { status: 'after', label: `After Hours · ${uaeTime}` };
  }
  // Overnight closed
  return { status: 'closed', label: `NYSE Closed · Opens in ${fmt(minsToNextOpen())} · ${uaeTime}` };
}

export interface MainContentProps {
  children: ReactNode;
  className?: string;
}

export function MainContent({ children, className = '' }: MainContentProps) {
  const [marketStatus, setMarketStatus] = useState<MarketStatus>(getMarketStatus());

  useEffect(() => {
    const iv = setInterval(() => setMarketStatus(getMarketStatus()), 30000);
    return () => clearInterval(iv);
  }, []);

  return (
    <main className={`finedge-shell flex-1 min-h-screen overflow-y-auto custom-scrollbar lg:ml-[224px] ${className}`}>
      {/* Market status banner */}
      <div className={cn(
        'flex items-center gap-2 px-4 py-2 text-xs font-semibold lg:px-10',
        marketStatus.status === 'open' ? 'bg-emerald-50 text-emerald-700 border-b border-emerald-100' :
        marketStatus.status === 'pre' ? 'bg-amber-50 text-amber-700 border-b border-amber-100' :
        'bg-slate-50 text-slate-500 border-b border-slate-100'
      )}>
        <Circle
          size={7}
          fill="currentColor"
          className={marketStatus.status === 'open' ? 'animate-pulse' : ''}
        />
        <span>{marketStatus.label}</span>
      </div>

      <div className="mx-auto w-full max-w-[1420px] px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
        {children}
      </div>
    </main>
  );
}
