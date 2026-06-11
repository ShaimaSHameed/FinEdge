from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FundamentalAnalysisRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20, description="Stock ticker symbol")
    market: Literal["US", "IN"] = Field("US", description="Market: US or India")
    include_peer_context: bool = Field(True, description="Include ranking/peer context when available")


class FundamentalPeerContext(BaseModel):
    sector_percentile: Optional[float] = Field(None, ge=0.0, le=1.0)
    universe_percentile: Optional[float] = Field(None, ge=0.0, le=1.0)
    relative_rank: Optional[int] = Field(None, ge=1)
    source: str


class FundamentalAnalysisResponse(BaseModel):
    ticker: str
    market: str
    company_name: str
    sector: Optional[str] = None
    rating: Literal["BUY", "HOLD", "SELL"]
    signal: str
    score: float = Field(..., ge=0.0, le=10.0)
    model_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    universe_percentile: Optional[float] = Field(None, ge=0.0, le=1.0)
    relative_rank: Optional[int] = Field(None, ge=1)
    key_metrics: Dict[str, Optional[float]]
    trends: Dict[str, str]
    peer_context: Optional[FundamentalPeerContext] = None
    strengths: List[str]
    concerns: List[str]
    analysis_summary: str
    data_source: str
    cached: bool
    source_signal_date: Optional[str] = None
    generated_at: datetime
