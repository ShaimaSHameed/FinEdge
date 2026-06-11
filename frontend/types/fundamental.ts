export type FundamentalRating = 'BUY' | 'HOLD' | 'SELL';

export interface FundamentalAnalysisRequest {
  ticker: string;
  market?: 'US' | 'IN';
  include_peer_context?: boolean;
}

export interface FundamentalPeerContext {
  sector_percentile: number | null;
  universe_percentile: number | null;
  relative_rank: number | null;
  source: string;
}

export interface FundamentalAnalysisResponse {
  ticker: string;
  market: string;
  company_name: string;
  sector: string | null;
  rating: FundamentalRating;
  signal: string;
  score: number;
  model_score: number | null;
  universe_percentile: number | null;
  relative_rank: number | null;
  key_metrics: {
    pe_ratio: number | null;
    roe: number | null;
    debt_to_equity: number | null;
    free_cash_flow_margin: number | null;
    revenue_growth_yoy: number | null;
    earnings_growth_yoy: number | null;
    [key: string]: number | null;
  };
  trends: Record<string, string>;
  peer_context: FundamentalPeerContext | null;
  strengths: string[];
  concerns: string[];
  analysis_summary: string;
  data_source: string;
  cached: boolean;
  source_signal_date: string | null;
  generated_at: string;
}
