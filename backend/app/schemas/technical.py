from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class TechnicalAnalysisRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20, description="Stock or crypto symbol")
    model_version: Literal["final_1d", "final_1min", "v1.1", "v1.2"] = Field("final_1d", description="Technical model selector")
    history_bars: int = Field(90, ge=30, le=500, description="Number of historical candles")
    forecast_bars: int = Field(7, ge=1, le=50, description="Number of future candles")


class TechnicalCandle(BaseModel):
    timestamp: datetime
    open: float = Field(..., gt=0)
    high: float = Field(..., gt=0)
    low: float = Field(..., gt=0)
    close: float = Field(..., gt=0)
    volume: int = Field(..., ge=0)
    is_prediction: bool = False


class TechnicalAnalysisResponse(BaseModel):
    ticker: str
    timeframe: Literal["1Min", "1D"] = "1D"
    model_version: Literal["final_1d", "final_1min", "v1.1", "v1.2"]
    source: Literal["model_artifact", "synthetic_fallback"] = "model_artifact"
    source_model: Optional[str] = None
    artifact_version: Optional[str] = None
    artifact_path: Optional[str] = None
    data_source: str
    inference_input_bars: int = Field(..., ge=1)
    required_input_bars: int = Field(..., ge=1)
    latest_price: float = Field(..., gt=0)
    history_bars: List[TechnicalCandle]
    forecast_bars: List[TechnicalCandle]
    generated_at: datetime
    ensemble_weights: Dict[str, float] = Field(default_factory=dict)
    expert_versions: Dict[str, str] = Field(default_factory=dict)
    policy: Dict[str, float | str] = Field(default_factory=dict)
    regime: Optional[str] = None
