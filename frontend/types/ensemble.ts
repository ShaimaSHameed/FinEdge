export type EnsembleTradeAction = 'BUY' | 'HOLD' | 'SELL';
export type EnsembleSignalModel = 'fundamental' | 'sentimental' | 'technical';

export interface EnsembleBacktestRequest {
  ticker: string;
  market?: 'US' | 'IN';
  start_date?: string | null;
  end_date?: string | null;
  initial_capital?: number;
  transaction_cost_pct?: number;
  buy_threshold?: number;
  sell_threshold?: number;
  target_long_exposure?: number;
  base_long_exposure?: number;
  technical_exposure_weight?: number;
  fundamental_exposure_weight?: number;
  sentiment_max_exposure?: number;
  min_trade_value?: number;
  min_model_count?: number;
  require_sentiment_signal?: boolean;
  allow_technical_proxy?: boolean;
}

export interface EnsembleModelSignal {
  date: string;
  ticker: string;
  model: EnsembleSignalModel;
  raw_signal: string;
  normalized_score: number;
  confidence: number;
  signal_label?: string | null;
  source: string;
}

export interface EnsembleDecision {
  date: string;
  close: number;
  action: EnsembleTradeAction;
  average_score: number;
  target_exposure?: number | null;
  model_count: number;
  model_scores: Record<string, number>;
  sentiment_action?: EnsembleTradeAction | null;
  support_score: number;
  technical_adjustment: number;
  fundamental_adjustment: number;
}

export interface EnsembleTrade {
  date: string;
  action: EnsembleTradeAction;
  price: number;
  exposure_before: number;
  exposure_after: number;
  trade_value: number;
  transaction_cost: number;
  shares_after: number;
  cash_after: number;
  portfolio_value: number;
}

export interface EnsembleEquityPoint {
  date: string;
  close: number;
  shares: number;
  cash: number;
  exposure: number;
  portfolio_value: number;
  daily_return: number;
}

export interface EnsembleBacktestMetrics {
  initial_capital: number;
  final_value: number;
  total_return_pct: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  trade_count: number;
  decision_count: number;
  average_model_count: number;
  coverage_by_model: Record<string, number>;
}

export interface EnsembleBacktestResponse {
  ticker: string;
  market: string;
  start_date: string;
  end_date: string;
  metrics: EnsembleBacktestMetrics;
  decisions: EnsembleDecision[];
  trades: EnsembleTrade[];
  equity_curve: EnsembleEquityPoint[];
  model_signals: EnsembleModelSignal[];
  source_files: string[];
  warnings: string[];
  generated_at: string;
}
