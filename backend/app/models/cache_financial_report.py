from datetime import datetime
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, String, Text

from app.database import Base


class CacheFinancialReport(Base):
    __tablename__ = "cache_financial_reports"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid4()))
    ticker = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False, index=True)
    report_type = Column(String(50), nullable=False, default="fundamentals")
    report_period = Column(String(50), nullable=False, default="latest")
    content = Column(Text, nullable=False)
    source = Column(String(50), nullable=False, default="eodhd")
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index("idx_cache_financial_reports_lookup", "ticker", "market", "report_type"),
        Index("idx_cache_financial_reports_expires_at", "expires_at"),
    )
