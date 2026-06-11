from typing import Dict, Any, List, Optional, Literal
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
import json

from app.config import settings
from app.engines.sentimental.artifacts import SentimentalArtifactStore
from app.engines.sentimental.llm_analyzer import LLMAnalyzer
from app.integrations.news_api import NewsAPIClient
from app.services.cache_manager import CacheManager
from app.schemas.sentimental import (
    SentimentalAnalysisResponse,
    NewsSentimentBreakdown
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SentimentalEngine:
    def __init__(self):
        self.artifact_store = SentimentalArtifactStore()
        self.llm_analyzer: Optional[LLMAnalyzer] = None
        self.news_client: Optional[NewsAPIClient] = None
        self.cache_manager = CacheManager()

    async def analyze(
        self,
        ticker: str,
        market: str,
        db: AsyncSession,
        days: int = 7,
        max_articles: int = 10
    ) -> SentimentalAnalysisResponse:
        ticker = ticker.upper()
        market = market.upper()
        logger.info(f"Starting sentimental analysis for {ticker} ({market})")

        artifact_error: Optional[ValueError] = None
        try:
            artifact = self.artifact_store.load_latest(ticker, market)
        except ValueError as exc:
            artifact = None
            artifact_error = exc
            if not settings.SENTIMENTAL_ALLOW_LIVE_FALLBACK:
                raise
            logger.warning(f"Sentimental artifact unavailable for {ticker}; falling back to live analysis: {exc}")

        if artifact:
            logger.info(f"Using sentimental model artifact for {ticker}")
            return self._build_artifact_response(artifact)

        if settings.SENTIMENTAL_REQUIRE_MODEL_ARTIFACT and not settings.SENTIMENTAL_ALLOW_LIVE_FALLBACK:
            artifact_status = self.artifact_status()
            covered_tickers = artifact_status.get("covered_tickers") or []
            raise ValueError(
                f"No sentimental model artifact is available for {ticker}. "
                f"Docker is configured to require real sentimental model artifacts; "
                f"covered tickers: {covered_tickers or 'none'}."
            )

        if not settings.SENTIMENTAL_ALLOW_LIVE_FALLBACK:
            raise ValueError(
                f"No sentimental model artifact is available for {ticker}, and live fallback is disabled."
            )

        if artifact_error is None:
            logger.info(f"No sentimental artifact for {ticker}; using live News API/OpenRouter analysis")
        articles = await self._fetch_articles(ticker, market, days, max_articles)

        if not articles:
            logger.warning(f"No articles found for {ticker}")
            return self._empty_response(ticker, market)

        analyzed_articles = await self.llm_analyzer.analyze_news_batch(articles)

        return self._build_response(analyzed_articles, ticker, market, cached=False)

    def artifact_status(self) -> Dict[str, Any]:
        return self.artifact_store.artifact_status()

    async def _fetch_articles(
        self,
        ticker: str,
        market: str,
        days: int,
        max_articles: int
    ) -> List[Dict[str, Any]]:
        company_names = {
            'AAPL': 'Apple Inc',
            'MSFT': 'Microsoft Corporation',
            'NVDA': 'NVIDIA Corporation',
            'GOOGL': 'Alphabet Inc',
            'AMZN': 'Amazon.com Inc',
            'META': 'Meta Platforms Inc',
            'TSLA': 'Tesla Inc',
            'RELIANCE.NS': 'Reliance Industries',
            'TCS.NS': 'Tata Consultancy Services',
            'INFY.NS': 'Infosys Ltd',
            'HDFCBANK.NS': 'HDFC Bank Ltd',
            'ICICIBANK.NS': 'ICICI Bank Ltd'
        }

        company_name = company_names.get(ticker, ticker)

        if self.news_client is None:
            self.news_client = NewsAPIClient()

        articles = await self.news_client.fetch_news(
            company_name=company_name,
            ticker=ticker,
            days=days,
            max_articles=max_articles
        )

        return articles

    @property
    def llm_analyzer(self) -> LLMAnalyzer:
        if self._llm_analyzer is None:
            self._llm_analyzer = LLMAnalyzer()
        return self._llm_analyzer

    @llm_analyzer.setter
    def llm_analyzer(self, value: Optional[LLMAnalyzer]) -> None:
        self._llm_analyzer = value

    async def _cache_articles(
        self,
        db: AsyncSession,
        ticker: str,
        market: str,
        articles: List[Dict[str, Any]]
    ) -> None:
        content = json.dumps(articles)
        await self.cache_manager.save_cached_news(db, ticker, market, content)

    def _build_response(
        self,
        articles: List[Dict[str, Any]],
        ticker: str,
        market: str,
        cached: bool
    ) -> SentimentalAnalysisResponse:
        breakdown = self._calculate_breakdown(articles)

        if breakdown.article_count == 0:
            return self._empty_response(ticker, market)

        overall_score = breakdown.average_score
        overall_sentiment: Literal["Positive", "Negative", "Neutral"] = self._score_to_sentiment(overall_score)
        trend: Literal["Improving", "Declining", "Stable"] = self._calculate_trend(articles)
        confidence = self._calculate_confidence(breakdown)

        top_articles = sorted(
            articles,
            key=lambda x: (
                abs(self._safe_float(x.get('sentiment_score', 0)))
                * max(self._safe_float(x.get('confidence', 0.0)), 0.25)
                * max(self._safe_float(x.get('materiality', x.get('relevance', 0.5))), 0.25)
            ),
            reverse=True
        )[:5]

        influential_articles = [
            {
                'title': a.get('title'),
                'sentiment': a.get('sentiment_score'),
                'verdict': a.get('verdict'),
                'reasoning': a.get('reasoning'),
                'source': a.get('source'),
                'url': a.get('url'),
                'event_type': a.get('event_type'),
                'materiality': a.get('materiality') or a.get('relevance'),
                'horizon': a.get('horizon')
            }
            for a in top_articles
        ]

        news_breakdown = breakdown.model_dump()
        news_breakdown["provenance"] = {
            "source": "live_fallback",
            "article_source": "eventregistry",
            "source_model": "openrouter",
            "source_model_id": settings.LLM_MODEL,
            "requested_articles": len(articles),
        }

        return SentimentalAnalysisResponse(
            ticker=ticker,
            market=market,
            overall_sentiment=overall_sentiment,
            score=round(overall_score, 3),
            news_breakdown=news_breakdown,
            trend=trend,
            confidence=round(confidence, 2),
            analysis_summary=self._generate_summary(breakdown, overall_sentiment, trend),
            influential_articles=influential_articles,
            cached=cached,
            analyzed_at=datetime.now(timezone.utc),
            source="live_fallback",
            source_model="openrouter",
            source_model_id=settings.LLM_MODEL,
        )

    def _build_artifact_response(self, artifact: Dict[str, Any]) -> SentimentalAnalysisResponse:
        provenance = artifact.get("provenance") or {}
        analyzed_at = self._parse_artifact_datetime(
            artifact.get("as_of") or provenance.get("generated_at")
        )

        news_breakdown = dict(artifact.get("news_breakdown") or {})
        news_breakdown["provenance"] = {
            "source": "model_artifact",
            "source_model": artifact.get("source_model"),
            "source_model_id": artifact.get("source_model_id"),
            "strategy": artifact.get("strategy"),
            **provenance,
        }

        return SentimentalAnalysisResponse(
            ticker=str(artifact.get("ticker", "")).upper(),
            market=str(artifact.get("market", "US")).upper(),
            overall_sentiment=artifact.get("overall_sentiment", "Neutral"),
            score=round(max(-1.0, min(self._safe_float(artifact.get("score")), 1.0)), 3),
            news_breakdown=news_breakdown,
            trend=artifact.get("trend", "Stable"),
            confidence=round(max(0.0, min(self._safe_float(artifact.get("confidence")), 1.0)), 2),
            analysis_summary=artifact.get("analysis_summary", ""),
            influential_articles=artifact.get("influential_articles") or [],
            cached=True,
            analyzed_at=analyzed_at,
            source="model_artifact",
            source_model=artifact.get("source_model"),
            source_model_id=artifact.get("source_model_id"),
            model_signal=self._safe_float(artifact.get("model_signal")) if artifact.get("model_signal") is not None else None,
            artifact_version=provenance.get("artifact_version"),
            artifact_path=artifact.get("_artifact_path"),
        )

    def _parse_cached_response(
        self,
        cached_content: str,
        ticker: str,
        market: str
    ) -> SentimentalAnalysisResponse:
        articles = json.loads(cached_content)
        return self._build_response(articles, ticker, market, cached=True)

    def _empty_response(self, ticker: str, market: str) -> SentimentalAnalysisResponse:
        return SentimentalAnalysisResponse(
            ticker=ticker,
            market=market,
            overall_sentiment="Neutral",
            score=0.0,
            news_breakdown={
                'ticker': ticker,
                'article_count': 0,
                'positive_count': 0,
                'negative_count': 0,
                'neutral_count': 0,
                'average_score': 0.0,
                'top_positive_articles': [],
                'top_negative_articles': []
            },
            trend="Stable",
            confidence=0.0,
            analysis_summary=f"No news data available for {ticker}",
            influential_articles=[],
            cached=False,
            analyzed_at=datetime.now(timezone.utc),
            source="live_fallback"
        )

    def _calculate_breakdown(self, articles: List[Dict[str, Any]]) -> NewsSentimentBreakdown:
        if not articles:
            return NewsSentimentBreakdown(
                ticker='',
                article_count=0,
                positive_count=0,
                negative_count=0,
                neutral_count=0,
                average_score=0.0,
                top_positive_articles=[],
                top_negative_articles=[]
            )

        scores = [a.get('sentiment_score', 0) for a in articles]
        average_score = sum(scores) / len(scores) if scores else 0

        positive = [a for a in articles if a.get('sentiment_score', 0) > 0.05]
        negative = [a for a in articles if a.get('sentiment_score', 0) < -0.05]
        neutral = [a for a in articles if -0.05 <= a.get('sentiment_score', 0) <= 0.05]

        top_positive = sorted(
            positive,
            key=lambda x: x.get('sentiment_score', 0),
            reverse=True
        )[:3]

        top_negative = sorted(
            negative,
            key=lambda x: x.get('sentiment_score', 0)
        )[:3]

        return NewsSentimentBreakdown(
            ticker=articles[0].get('ticker', ''),
            article_count=len(articles),
            positive_count=len(positive),
            negative_count=len(negative),
            neutral_count=len(neutral),
            average_score=average_score,
            top_positive_articles=[
                {
                    'title': a.get('title'),
                    'score': a.get('sentiment_score'),
                    'verdict': a.get('verdict'),
                    'source': a.get('source')
                }
                for a in top_positive
            ],
            top_negative_articles=[
                {
                    'title': a.get('title'),
                    'score': a.get('sentiment_score'),
                    'verdict': a.get('verdict'),
                    'source': a.get('source')
                }
                for a in top_negative
            ]
        )

    def _score_to_sentiment(self, score: float) -> str:
        if score > 0.05:
            return "Positive"
        elif score < -0.05:
            return "Negative"
        return "Neutral"

    def _calculate_trend(self, articles: List[Dict[str, Any]]) -> str:
        if len(articles) < 3:
            return "Stable"

        scores = [a.get('sentiment_score', 0) for a in articles[:3]]
        recent_avg = sum(scores) / len(scores)

        if len(articles) >= 6:
            recent_scores = [a.get('sentiment_score', 0) for a in articles[3:6]]
            previous_avg = sum(recent_scores) / len(recent_scores)
            change = recent_avg - previous_avg

            if change > 0.1:
                return "Improving"
            elif change < -0.1:
                return "Declining"

        if recent_avg > 0.1:
            return "Improving"
        elif recent_avg < -0.1:
            return "Declining"

        return "Stable"

    def _calculate_confidence(self, breakdown: NewsSentimentBreakdown) -> float:
        if breakdown.article_count == 0:
            return 0.0

        total_articles = breakdown.article_count
        article_count_factor = min(total_articles / 10, 1.0)

        verdict_distribution = [
            breakdown.positive_count,
            breakdown.negative_count,
            breakdown.neutral_count
        ]
        max_verdict_count = max(verdict_distribution)
        consensus_factor = max_verdict_count / total_articles

        return (article_count_factor * 0.5) + (consensus_factor * 0.5)

    def _generate_summary(
        self,
        breakdown: NewsSentimentBreakdown,
        sentiment: str,
        trend: str
    ) -> str:
        return (f"Based on {breakdown.article_count} news articles, "
                f"sentiment is {sentiment} with an average score of {breakdown.average_score:.3f}. "
                f"{breakdown.positive_count} positive, {breakdown.negative_count} negative, "
                f"{breakdown.neutral_count} neutral articles. Trend: {trend}.")

    @staticmethod
    def _parse_artifact_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
