from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, JSON, String

from app.database import Base


class CacheFundamentalAnalysis(Base):
    __tablename__ = "cache_fundamental_analysis"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid4()))
    ticker = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False, index=True)
    source_signal_date = Column(String(20), nullable=True)
    result = Column(JSON, nullable=False)
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index("idx_cache_fundamental_analysis_lookup", "ticker", "market"),
        Index("idx_cache_fundamental_analysis_expires_at", "expires_at"),
    )
