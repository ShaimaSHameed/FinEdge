export interface TechnicalCandle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  is_prediction: boolean;
}

export interface TechnicalAnalysisRequest {
  ticker: string;
  model_version: 'final_1d' | 'final_1min' | 'v1.1' | 'v1.2';
  history_bars?: number;
  forecast_bars?: number;
}

export interface TechnicalAnalysisResponse {
  ticker: string;
  timeframe: '1Min' | '1D';
  model_version: 'final_1d' | 'final_1min' | 'v1.1' | 'v1.2';
  source: 'model_artifact' | 'synthetic_fallback';
  source_model?: string | null;
  artifact_version?: string | null;
  artifact_path?: string | null;
  data_source: string;
  inference_input_bars: number;
  required_input_bars: number;
  latest_price: number;
  history_bars: TechnicalCandle[];
  forecast_bars: TechnicalCandle[];
  generated_at: string;
  ensemble_weights: Record<string, number>;
  expert_versions: Record<string, string>;
  policy: Record<string, number | string>;
  regime?: string | null;
}
