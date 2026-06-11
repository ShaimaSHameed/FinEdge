from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime


class SentimentScore(BaseModel):
    score: float = Field(..., ge=-1.0, le=1.0, description="Sentiment score from -1 to 1")
    verdict: Literal["BUY", "SELL", "HOLD"] = Field(..., description="Trading verdict")
    reasoning: str = Field(..., description="AI reasoning for the verdict")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score if available")


class NewsArticle(BaseModel):
    ticker: str
    company: str
    title: str
    body: str
    url: str
    source: Optional[str]
    published_at: Optional[str]


class SentimentalAnalysisRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20, description="Stock ticker symbol")
    market: Literal["US", "IN"] = Field("US", description="Market: US or India")


class SentimentalAnalysisResponse(BaseModel):
    ticker: str
    market: str
    overall_sentiment: Literal["Positive", "Negative", "Neutral"]
    score: float = Field(..., ge=-1.0, le=1.0)
    news_breakdown: Dict[str, Any]
    trend: Literal["Improving", "Declining", "Stable"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    analysis_summary: str
    influential_articles: List[Dict[str, Any]]
    cached: bool
    analyzed_at: datetime
    source: Literal["model_artifact", "live_fallback"] = "model_artifact"
    source_model: Optional[str] = None
    source_model_id: Optional[str] = None
    model_signal: Optional[float] = None
    artifact_version: Optional[str] = None
    artifact_path: Optional[str] = None


class NewsSentimentBreakdown(BaseModel):
    ticker: str
    article_count: int
    positive_count: int
    negative_count: int
    neutral_count: int
    average_score: float
    top_positive_articles: List[Dict[str, Any]]
    top_negative_articles: List[Dict[str, Any]]
