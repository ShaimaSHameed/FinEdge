import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { SentimentalAnalysisResponse, AnalysisHistory } from '@/types';
import { sentimentApi } from '@/lib/api';

/**
 * Sentiment Analysis Store
 * Manages sentiment analysis state and results
 */
type AnalysisStatus = 'idle' | 'loading' | 'success' | 'error';

interface SentimentStore {
  // Current Analysis State
  analysisStatus: AnalysisStatus;
  currentAnalysis: SentimentalAnalysisResponse | null;
  analysisError: string | null;
  
  // History State
  analysisHistory: AnalysisHistory[];
  historyLoading: boolean;
  historyError: string | null;
  
  // Actions
  analyzeSentiment: (ticker: string, market: 'US' | 'IN') => Promise<void>;
  setCurrentAnalysis: (analysis: SentimentalAnalysisResponse | null) => void;
  setAnalysisStatus: (status: AnalysisStatus) => void;
  setAnalysisError: (error: string | null) => void;
  clearAnalysis: () => void;
  
  // History Actions
  loadHistory: () => Promise<void>;
  deleteHistoryItem: (id: string) => Promise<void>;
  setHistory: (history: AnalysisHistory[]) => void;
  setHistoryLoading: (loading: boolean) => void;
  setHistoryError: (error: string | null) => void;
  clearHistoryError: () => void;
}

export const useSentimentStore = create<SentimentStore>()(
  persist(
    (set) => ({
      // Initial State
      analysisStatus: 'idle',
      currentAnalysis: null,
      analysisError: null,
      analysisHistory: [],
      historyLoading: false,
      historyError: null,

      // Actions
      analyzeSentiment: async (ticker: string, market: 'US' | 'IN') => {
        set({ analysisStatus: 'loading', analysisError: null });
        try {
          const analysis = await sentimentApi.analyze({ ticker, market });
          set({
            analysisStatus: 'success',
            currentAnalysis: analysis,
            analysisError: null,
          });
        } catch (error: any) {
          const errorMessage =
            error.response?.data?.detail ||
            error.message ||
            'Failed to analyze sentiment';
          set({
            analysisStatus: 'error',
            analysisError: errorMessage,
          });
          throw error;
        }
      },

      setCurrentAnalysis: (analysis: SentimentalAnalysisResponse | null) => {
        set({ currentAnalysis: analysis });
      },

      setAnalysisStatus: (status: AnalysisStatus) => {
        set({ analysisStatus: status });
      },

      setAnalysisError: (error: string | null) => {
        set({ analysisError: error });
      },

      clearAnalysis: () => {
        set({
          analysisStatus: 'idle',
          currentAnalysis: null,
          analysisError: null,
        });
      },

      loadHistory: async () => {
        set({ historyLoading: true, historyError: null });
        try {
          const history = await sentimentApi.getHistory();
          set({
            analysisHistory: history,
            historyLoading: false,
            historyError: null,
          });
        } catch (error: any) {
          const errorMessage =
            error.response?.data?.detail ||
            error.message ||
            'Failed to load history';
          set({
            historyLoading: false,
            historyError: errorMessage,
          });
          throw error;
        }
      },

      deleteHistoryItem: async (id: string) => {
        set({ historyLoading: true, historyError: null });
        try {
          await sentimentApi.deleteHistoryItem(id);
          set((state) => ({
            analysisHistory: state.analysisHistory.filter((item) => item.id !== id),
            historyLoading: false,
            historyError: null,
          }));
        } catch (error: any) {
          const errorMessage =
            error.response?.data?.detail ||
            error.message ||
            'Failed to delete history item';
          set({
            historyLoading: false,
            historyError: errorMessage,
          });
          throw error;
        }
      },

      setHistory: (history: AnalysisHistory[]) => {
        set({ analysisHistory: history });
      },

      setHistoryLoading: (loading: boolean) => {
        set({ historyLoading: loading });
      },

      setHistoryError: (error: string | null) => {
        set({ historyError: error });
      },

      clearHistoryError: () => {
        set({ historyError: null });
      },
    }),
    {
      name: 'sentiment-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
);

/**
 * Helper function to get the store instance (for use outside React components)
 */
export const getSentimentStore = () => useSentimentStore.getState();
