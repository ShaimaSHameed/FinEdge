/**
 * Type definitions for Sentiment Analysis API
 * Matches backend Pydantic schemas
 */

// Sentiment Analysis Request
export interface SentimentalAnalysisRequest {
  ticker: string;
  market: 'US' | 'IN';
}

// News Article
export interface NewsArticle {
  ticker: string;
  company: string;
  title: string;
  body: string;
  url: string;
  source?: string;
  published_at?: string;
}

// News Sentiment Breakdown
export interface NewsSentimentBreakdown {
  ticker: string;
  article_count: number;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  average_score: number;
  top_positive_articles: TopArticle[];
  top_negative_articles: TopArticle[];
}

// Top Article (positive or negative)
export interface TopArticle {
  title: string;
  score: number;
  verdict: 'BUY' | 'SELL' | 'HOLD';
  source?: string;
}

// Influential Article
export interface InfluentialArticle {
  title: string;
  sentiment: number;
  verdict: 'BUY' | 'SELL' | 'HOLD';
  reasoning: string;
  source?: string;
  url?: string | null;
  event_type?: string;
  materiality?: number;
  horizon?: string;
}

// Sentiment Analysis Response
export interface SentimentalAnalysisResponse {
  ticker: string;
  market: string;
  overall_sentiment: 'Positive' | 'Negative' | 'Neutral';
  score: number; // -1 to 1
  news_breakdown: NewsSentimentBreakdown;
  trend: 'Improving' | 'Declining' | 'Stable';
  confidence: number; // 0 to 1
  analysis_summary: string;
  influential_articles: InfluentialArticle[];
  cached: boolean;
  analyzed_at: string; // ISO 8601 datetime
  source?: 'model_artifact' | 'live_fallback';
  source_model?: string | null;
  source_model_id?: string | null;
  model_signal?: number | null;
  artifact_version?: string | null;
  artifact_path?: string | null;
}

// Analysis History Item
export interface AnalysisHistory {
  id: string;
  user_id: string;
  ticker: string;
  market: string;
  analysis_types: string[];
  results: any;
  created_at: string;
}

// Trend Data Point
export interface TrendDataPoint {
  date: string;
  score: number;
  article_count?: number;
}

// Sentiment Verdict
export type SentimentVerdict = 'BUY' | 'SELL' | 'HOLD';

// Overall Sentiment
export type OverallSentiment = 'Positive' | 'Negative' | 'Neutral';

// Trend
export type Trend = 'Improving' | 'Declining' | 'Stable';

// Market
export type Market = 'US' | 'IN';
