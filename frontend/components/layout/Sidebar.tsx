'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BarChart3,
  Building2,
  CandlestickChart,
  Grid2X2,
  Menu,
  MessageSquareText,
  Search,
  TrendingUp,
  X,
  Wifi,
  WifiOff,
  Bookmark,
  Trash2,
  Circle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWatchlistStore } from '@/stores';

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
}

const navItems: NavItem[] = [
  { label: 'Dashboard', href: '/dashboard', icon: <Grid2X2 size={15} /> },
  { label: 'Analyse Stock', href: '/analyze', icon: <Search size={15} /> },
  { label: 'Fundamental', href: '/fundamental', icon: <Building2 size={15} /> },
  { label: 'Technical', href: '/technical', icon: <CandlestickChart size={15} /> },
  { label: 'Sentiment', href: '/sentiment', icon: <MessageSquareText size={15} /> },
  { label: 'Results', href: '/results', icon: <BarChart3 size={15} /> },
];

type ConnectionStatus = 'checking' | 'connected' | 'disconnected';

interface MarketStatus {
  status: 'open' | 'pre' | 'after' | 'closed';
  label: string;
  color: string;
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
    return { status: 'closed', label: `NYSE Closed · Opens in ${fmt(minsToNextOpen())} · ${uaeTime}`, color: 'bg-rose-400' };
  }
  // Pre-market 4:00–9:30 AM ET
  if (et >= 240 && et < 570) {
    return { status: 'pre', label: `Pre-Market · Opens in ${fmt(570 - et)} · ${uaeTime}`, color: 'bg-amber-400' };
  }
  // Market open 9:30 AM–4:00 PM ET
  if (et >= 570 && et < 960) {
    return { status: 'open', label: `NYSE Open · Closes in ${fmt(960 - et)} · ${uaeTime}`, color: 'bg-emerald-500' };
  }
  // After hours 4:00–8:00 PM ET
  if (et >= 960 && et < 1200) {
    return { status: 'after', label: `After Hours · ${uaeTime}`, color: 'bg-slate-400' };
  }
  // Overnight closed
  return { status: 'closed', label: `NYSE Closed · Opens in ${fmt(minsToNextOpen())} · ${uaeTime}`, color: 'bg-rose-400' };
}

export function Sidebar() {
  const pathname = usePathname();
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('checking');
  const [marketStatus, setMarketStatus] = useState<MarketStatus>(getMarketStatus());
  const { items: watchlistItems, removeFromWatchlist } = useWatchlistStore();

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/api/health`,
          { signal: AbortSignal.timeout(4000) }
        );
        setConnectionStatus(res.ok ? 'connected' : 'disconnected');
      } catch {
        setConnectionStatus('disconnected');
      }
    };
    void check();
    const iv = setInterval(() => void check(), 30000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    const iv = setInterval(() => setMarketStatus(getMarketStatus()), 30000);
    return () => clearInterval(iv);
  }, []);

  const isActive = (href: string, label: string) => {
    if (label === 'Sentiment') return pathname === '/sentiment';
    if (href === '/dashboard') return pathname === '/' || pathname.startsWith('/dashboard');
    return pathname.startsWith(href);
  };

  return (
    <>
      <button
        onClick={() => setIsMobileOpen(!isMobileOpen)}
        className="fixed left-4 top-4 z-50 rounded-full border border-slate-200 bg-white p-2 shadow-sm lg:hidden"
        aria-label="Toggle navigation"
      >
        {isMobileOpen ? <X size={22} /> : <Menu size={22} />}
      </button>

      {isMobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-950/30 backdrop-blur-sm lg:hidden"
          onClick={() => setIsMobileOpen(false)}
        />
      )}

      <aside
        className={cn(
          'fixed left-0 top-0 z-50 flex h-full w-[224px] flex-col border-r border-slate-200 bg-white transition-transform duration-300',
          'lg:translate-x-0',
          isMobileOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Logo */}
        <div className="flex h-[64px] items-center justify-between border-b border-slate-200 px-4">
          <Link href="/dashboard" className="flex items-center gap-2.5" onClick={() => setIsMobileOpen(false)}>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-600 text-white shadow-md">
              <TrendingUp size={16} strokeWidth={2.8} />
            </div>
            <span className="text-base font-extrabold tracking-tight text-slate-950">FinEdge</span>
          </Link>
          {/* Market status dot */}
          <div className="flex items-center gap-1.5">
            <span className={cn('h-2 w-2 rounded-full', marketStatus.color, marketStatus.status === 'open' && 'animate-pulse')} />
            <span className="text-[10px] font-bold text-slate-500">NYSE</span>
          </div>
        </div>

        {/* Market status bar */}
        <div className={cn(
          'flex items-center gap-2 px-4 py-1.5 text-[11px] font-semibold',
          marketStatus.status === 'open' ? 'bg-emerald-50 text-emerald-700' :
          marketStatus.status === 'pre' ? 'bg-amber-50 text-amber-700' :
          'bg-slate-50 text-slate-500'
        )}>
          <Circle size={6} fill="currentColor" />
          <span>{marketStatus.label}</span>
        </div>



        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-3 py-3">
          <ul className="space-y-0.5">
            {navItems.map((item) => {
              const active = isActive(item.href, item.label);
              return (
                <li key={`${item.label}-${item.href}`}>
                  <Link
                    href={item.href}
                    className={cn(
                      'flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-bold transition-all duration-200',
                      active ? 'bg-emerald-50 text-emerald-700' : 'text-slate-500 hover:bg-slate-50 hover:text-slate-950'
                    )}
                    onClick={() => setIsMobileOpen(false)}
                  >
                    <span className={cn(active ? 'text-emerald-600' : 'text-slate-400')}>{item.icon}</span>
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>

          {/* Watchlist */}
          <div className="mt-5 border-t border-slate-200 pt-4">
            <div className="mb-2 flex items-center justify-between px-3">
              <div className="flex items-center gap-2">
                <Bookmark size={13} className="text-amber-500" />
                <span className="text-[11px] font-extrabold uppercase tracking-[0.12em] text-slate-500">Watchlist</span>
              </div>
              {watchlistItems.length > 0 && (
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500">
                  {watchlistItems.length}
                </span>
              )}
            </div>

            {watchlistItems.length === 0 ? (
              <p className="px-3 text-[11px] text-slate-400">Add stocks to track them here.</p>
            ) : (
              <ul className="space-y-0.5">
                {watchlistItems.map((item) => (
                  <li key={item.ticker}>
                    <div className="flex items-center justify-between rounded-xl px-3 py-2 hover:bg-slate-50 group">
                      <Link
                        href={`/analyze?ticker=${item.ticker}`}
                        className="flex-1"
                        onClick={() => setIsMobileOpen(false)}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-[13px] font-bold text-slate-800">{item.ticker}</span>
                          {item.lastSignal && (
                            <span className={cn(
                              'rounded-full px-2 py-0.5 text-[10px] font-bold',
                              item.lastSignal === 'BUY' ? 'bg-emerald-100 text-emerald-700' :
                              item.lastSignal === 'SELL' ? 'bg-rose-100 text-rose-700' :
                              'bg-slate-100 text-slate-600'
                            )}>
                              {item.lastSignal}
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] text-slate-400 truncate">{item.companyName}</p>
                      </Link>
                      <button
                        onClick={() => removeFromWatchlist(item.ticker)}
                        className="ml-2 opacity-0 group-hover:opacity-100 transition-opacity text-slate-400 hover:text-rose-500"
                      >
                        <Trash2 size={11} />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </nav>

        <div className="border-t border-slate-200 px-4 py-3 text-[10px] text-slate-400">
          <p className="font-semibold">© 2026 FinEdge · AUS Senior Design</p>
        </div>
      </aside>
    </>
  );
}
