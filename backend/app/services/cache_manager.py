from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cache_news import CacheNews
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CacheManager:
    NEWS_CACHE_TTL = timedelta(hours=24)

    @staticmethod
    async def get_cached_news(
        db: AsyncSession,
        ticker: str,
        market: str
    ) -> Optional[CacheNews]:
        cache_key = f"{ticker}_{market}"
        expiry_time = datetime.utcnow() - CacheManager.NEWS_CACHE_TTL

        try:
            stmt = (
                select(CacheNews)
                .where(CacheNews.ticker == ticker)
                .where(CacheNews.market == market)
                .where(CacheNews.cached_at > expiry_time)
                .order_by(CacheNews.cached_at.desc())
                .limit(1)
            )

            result = await db.execute(stmt)
            return result.scalar_one_or_none()

        except Exception as e:
            logger.error(f"Error checking cache for {ticker}: {str(e)}")
            return None

    @staticmethod
    async def save_cached_news(
        db: AsyncSession,
        ticker: str,
        market: str,
        content: str
    ) -> CacheNews:
        expiry_time = datetime.utcnow() + CacheManager.NEWS_CACHE_TTL

        cached_news = CacheNews(
            ticker=ticker,
            market=market,
            content=content,
            source='event_registry',
            published_at=datetime.utcnow(),
            cached_at=datetime.utcnow(),
            expires_at=expiry_time
        )

        db.add(cached_news)
        await db.commit()
        await db.refresh(cached_news)

        logger.info(f"Cached news for {ticker} (expires: {expiry_time})")
        return cached_news

    @staticmethod
    async def invalidate_cache(
        db: AsyncSession,
        ticker: str,
        market: str
    ) -> None:
        try:
            stmt = (
                select(CacheNews)
                .where(CacheNews.ticker == ticker)
                .where(CacheNews.market == market)
            )

            result = await db.execute(stmt)
            cached_items = result.scalars().all()

            for item in cached_items:
                await db.delete(item)

            await db.commit()
            logger.info(f"Invalidated cache for {ticker}")

        except Exception as e:
            logger.error(f"Error invalidating cache for {ticker}: {str(e)}")
            await db.rollback()
