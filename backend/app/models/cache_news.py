from sqlalchemy import Column, String, DateTime, Text, Index, Float
from datetime import datetime
import json
from uuid import uuid4

from app.database import Base


class CacheNews(Base):
    __tablename__ = "cache_news"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid4()))
    ticker = Column(String(20), nullable=False, index=True)
    market = Column(String(10), nullable=False, index=True)
    content = Column(Text, nullable=False)
    source = Column(String(50), nullable=False)
    published_at = Column(DateTime, nullable=False)
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index('idx_cache_news_ticker_market', 'ticker', 'market'),
        Index('idx_cache_news_expires_at', 'expires_at'),
    )

    def to_dict(self):
        return {
            'ticker': self.ticker,
            'market': self.market,
            'content': json.loads(self.content) if self.content else None,
            'source': self.source,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'cached_at': self.cached_at.isoformat() if self.cached_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }
