from sqlalchemy import Column, String, DateTime, Text, Index, Integer, Float, JSON
from datetime import datetime
from uuid import uuid4

from app.database import Base


class AnalysisHistory(Base):
    __tablename__ = "analysis_history"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid4()))
    user_id = Column(String, nullable=False, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False)
    analysis_types = Column(JSON, nullable=False)
    results = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_analysis_history_user_id', 'user_id'),
        Index('idx_analysis_history_ticker_market', 'ticker', 'market'),
        Index('idx_analysis_history_created_at', 'created_at'),
    )
