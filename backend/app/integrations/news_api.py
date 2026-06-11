from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from eventregistry import ArticleInfoFlags, EventRegistry, QueryArticlesIter, ReturnInfo

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NewsAPIClient:
    _instance: Optional['NewsAPIClient'] = None
    _er: Optional[EventRegistry] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._er is None:
            self._er = EventRegistry(apiKey=settings.NEWS_API_KEY)

    async def fetch_news(
        self,
        company_name: str,
        ticker: str,
        days: int = 7,
        max_articles: int = 10
    ) -> List[Dict[str, Any]]:
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        try:
            query = QueryArticlesIter(
                keywords=f"{company_name} {ticker}",
                lang='eng',
                dateStart=start_date_str,
                dateEnd=end_date_str
            )

            articles = []
            seen_urls = set()
            return_info = ReturnInfo(articleInfo=ArticleInfoFlags(body=True))

            for article in query.execQuery(self._er, maxItems=max_articles, returnInfo=return_info):
                url = article.get('url')
                if url and url in seen_urls:
                    continue
                if url:
                    seen_urls.add(url)

                published_at = article.get('dateTime') or article.get('dateTimePub') or article.get('date')
                articles.append({
                    'ticker': ticker,
                    'company': company_name,
                    'title': article.get('title'),
                    'body': article.get('body', ''),
                    'url': url,
                    'source': article.get('source', {}).get('title') if article.get('source') else None,
                    'published_at': published_at,
                    'published_date': str(published_at or start_date_str)[:10]
                })

            logger.info(f"Fetched {len(articles)} articles for {ticker}")
            return articles

        except Exception as e:
            logger.error(f"Error fetching news for {ticker}: {str(e)}")
            return []

    async def fetch_multiple_news(
        self,
        companies: Dict[str, str],
        days: int = 7,
        max_articles_per_company: int = 10
    ) -> Dict[str, List[Dict[str, Any]]]:
        results = {}

        for ticker, company_name in companies.items():
            articles = await self.fetch_news(
                company_name=company_name,
                ticker=ticker,
                days=days,
                max_articles=max_articles_per_company
            )
            results[ticker] = articles

        return results
