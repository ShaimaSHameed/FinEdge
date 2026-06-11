from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.sentimental import (
    SentimentalAnalysisRequest,
    SentimentalAnalysisResponse
)
from app.engines.sentimental.engine import SentimentalEngine
from app.models.analysis_history import AnalysisHistory
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/analyze", tags=["sentimental"])
sentimental_engine = SentimentalEngine()


@router.post("/sentimental", response_model=SentimentalAnalysisResponse)
async def analyze_sentiment(
    request: SentimentalAnalysisRequest,
    db: AsyncSession = Depends(get_db)
) -> SentimentalAnalysisResponse:
    try:
        logger.info(f"Received sentimental analysis request for {request.ticker}")

        response = await sentimental_engine.analyze(
            ticker=request.ticker.upper(),
            market=request.market,
            db=db,
            days=7,
            max_articles=10
        )

        await _save_history(db, request, response)
        return response

    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error(f"Error during sentimental analysis: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to perform sentimental analysis")


@router.get("/sentimental/health")
async def health_check():
    artifact_status = sentimental_engine.artifact_status()
    return {
        "status": "healthy" if artifact_status["using_real_model_artifacts"] else "degraded",
        "service": "sentimental",
        **artifact_status,
    }


async def _save_history(
    db: AsyncSession,
    request: SentimentalAnalysisRequest,
    response: SentimentalAnalysisResponse
) -> None:
    try:
        record = AnalysisHistory(
            user_id="anonymous",
            ticker=request.ticker.upper(),
            market=request.market,
            analysis_types=["sentimental"],
            results=response.model_dump(mode="json")
        )
        db.add(record)
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to save analysis history: {str(e)}")
        await db.rollback()
