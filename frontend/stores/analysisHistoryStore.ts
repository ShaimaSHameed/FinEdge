import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface AnalysisHistoryEntry {
  id: string;
  ticker: string;
  companyName: string;
  analyzedAt: string;
  overallRecommendation: 'BUY' | 'SELL' | 'HOLD' | 'STRONG BUY';
  confidence: number;
  price?: number;
  fundamentalSignal?: string;
  fundamentalGap?: string;
  technicalSignal?: string;
  technicalMove?: string;
  sentimentSignal?: string;
  sentimentScore?: number;
}

interface AnalysisHistoryStore {
  history: AnalysisHistoryEntry[];
  addToHistory: (entry: AnalysisHistoryEntry) => void;
  clearHistory: () => void;
}

export const useAnalysisHistoryStore = create<AnalysisHistoryStore>()(
  persist(
    (set) => ({
      history: [],
      addToHistory: (entry: AnalysisHistoryEntry) => {
        set((state) => ({
          history: [entry, ...state.history].slice(0, 50),
        }));
      },
      clearHistory: () => set({ history: [] }),
    }),
    {
      name: 'finedge-analysis-history',
      storage: createJSONStorage(() => localStorage),
    }
  )
);
