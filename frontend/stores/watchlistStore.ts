import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface WatchlistEntry {
  ticker: string;
  companyName: string;
  addedAt: string;
  lastSignal?: 'BUY' | 'SELL' | 'HOLD';
  lastPrice?: number;
  lastChangePercent?: number;
  lastAnalyzedAt?: string;
  fundamentalSignal?: string;
  technicalSignal?: string;
  sentimentSignal?: string;
  sentimentScore?: number;
}

interface WatchlistStore {
  items: WatchlistEntry[];
  addToWatchlist: (entry: WatchlistEntry) => void;
  removeFromWatchlist: (ticker: string) => void;
  isInWatchlist: (ticker: string) => boolean;
  updateEntry: (ticker: string, data: Partial<WatchlistEntry>) => void;
  clearWatchlist: () => void;
}

export const useWatchlistStore = create<WatchlistStore>()(
  persist(
    (set, get) => ({
      items: [],

      addToWatchlist: (entry: WatchlistEntry) => {
        if (!get().items.find((i) => i.ticker === entry.ticker)) {
          set((state) => ({ items: [...state.items, entry] }));
        }
      },

      removeFromWatchlist: (ticker: string) => {
        set((state) => ({ items: state.items.filter((i) => i.ticker !== ticker) }));
      },

      isInWatchlist: (ticker: string) => get().items.some((i) => i.ticker === ticker),

      updateEntry: (ticker: string, data: Partial<WatchlistEntry>) => {
        set((state) => ({
          items: state.items.map((i) => (i.ticker === ticker ? { ...i, ...data } : i)),
        }));
      },

      clearWatchlist: () => set({ items: [] }),
    }),
    {
      name: 'finedge-watchlist',
      storage: createJSONStorage(() => localStorage),
    }
  )
);
