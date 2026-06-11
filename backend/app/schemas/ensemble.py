from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


TradeAction = Literal["BUY", "HOLD", "SELL"]
SignalModel = Literal["fundamental", "sentimental", "technical"]


class EnsembleBacktestRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20, description="Stock ticker symbol")
    market: Literal["US", "IN"] = Field("US", description="Market: US or India")
    start_date: Optional[date] = Field(None, description="Inclusive backtest start date")
    end_date: Optional[date] = Field(None, description="Inclusive backtest end date")
    initial_capital: float = Field(10000.0, gt=0.0)
    transaction_cost_pct: float = Field(0.001, ge=0.0, le=0.05)
    buy_threshold: float = Field(0.15, ge=-1.0, le=1.0)
    sell_threshold: float = Field(-0.15, ge=-1.0, le=1.0)
    target_long_exposure: float = Field(1.0, ge=0.0, le=2.5)
    base_long_exposure: float = Field(0.6, ge=0.0, le=2.5)
    technical_exposure_weight: float = Field(0.25, ge=0.0, le=2.5)
    fundamental_exposure_weight: float = Field(0.15, ge=0.0, le=2.5)
    sentiment_max_exposure: float = Field(2.5, gt=0.0, le=10.0)
    min_trade_value: float = Field(1.0, ge=0.0)
    min_model_count: int = Field(1, ge=1, le=3)
    require_sentiment_signal: bool = Field(
        True,
        description="Require a sentimental signal before creating a sentiment-led aggregate decision.",
    )
    allow_technical_proxy: bool = Field(
        True,
        description="Use deterministic price-momentum technical proxy if no technical backtest artifact is available.",
    )

    @model_validator(mode="after")
    def validate_thresholds(self) -> "EnsembleBacktestRequest":
        if self.sell_threshold >= self.buy_threshold:
            raise ValueError("sell_threshold must be lower than buy_threshold")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be on or before end_date")
        if self.base_long_exposure > self.target_long_exposure:
            raise ValueError("base_long_exposure must be less than or equal to target_long_exposure")
        return self


class EnsembleModelSignal(BaseModel):
    date: date
    ticker: str
    model: SignalModel
    raw_signal: str
    normalized_score: float = Field(..., ge=-1.0, le=1.0)
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    signal_label: Optional[str] = None
    source: str


class EnsembleDecision(BaseModel):
    date: date
    close: float = Field(..., gt=0.0)
    action: TradeAction
    average_score: float = Field(..., ge=-1.0, le=1.0)
    target_exposure: Optional[float] = Field(None, ge=0.0, le=2.5)
    model_count: int = Field(..., ge=1, le=3)
    model_scores: Dict[str, float]
    sentiment_action: Optional[TradeAction] = None
    support_score: float = Field(0.0, ge=-1.0, le=1.0)
    technical_adjustment: float = Field(0.0, ge=-2.5, le=2.5)
    fundamental_adjustment: float = Field(0.0, ge=-2.5, le=2.5)


class EnsembleTrade(BaseModel):
    date: date
    action: TradeAction
    price: float = Field(..., gt=0.0)
    exposure_before: float
    exposure_after: float
    trade_value: float
    transaction_cost: float
    shares_after: float
    cash_after: float
    portfolio_value: float


class EnsembleEquityPoint(BaseModel):
    date: date
    close: float = Field(..., gt=0.0)
    shares: float
    cash: float
    exposure: float
    portfolio_value: float
    daily_return: float


class EnsembleBacktestMetrics(BaseModel):
    initial_capital: float
    final_value: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    trade_count: int
    decision_count: int
    average_model_count: float
    coverage_by_model: Dict[str, int]


class EnsembleBacktestResponse(BaseModel):
    ticker: str
    market: str
    start_date: date
    end_date: date
    metrics: EnsembleBacktestMetrics
    decisions: List[EnsembleDecision]
    trades: List[EnsembleTrade]
    equity_curve: List[EnsembleEquityPoint]
    model_signals: List[EnsembleModelSignal]
    source_files: List[str]
    warnings: List[str]
    generated_at: datetime
