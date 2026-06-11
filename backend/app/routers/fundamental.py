from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engines.fundamental import FundamentalAnalysisEngine
from app.models.analysis_history import AnalysisHistory
from app.schemas.fundamental import FundamentalAnalysisRequest, FundamentalAnalysisResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/analyze", tags=["fundamental"])
fundamental_engine = FundamentalAnalysisEngine()


@router.post("/fundamental", response_model=FundamentalAnalysisResponse)
async def analyze_fundamental(
    request: FundamentalAnalysisRequest,
    db: AsyncSession = Depends(get_db),
) -> FundamentalAnalysisResponse:
    try:
        logger.info(f"Received fundamental analysis request for {request.ticker}")
        response = await fundamental_engine.analyze(request, db)
        await _save_history(db, request, response)
        return response
    except ValueError as exc:
        logger.error(f"Fundamental analysis validation error: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Fundamental analysis failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to perform fundamental analysis") from exc


@router.get("/fundamental/health")
async def health_check():
    artifact_status = fundamental_engine.artifact_status()
    has_required_artifacts = (
        artifact_status["signal_file_count"] > 0
        and artifact_status["latest_signal_rows"] > 0
        and artifact_status["model_files"]["final_model"]
    )
    return {
        "status": "healthy" if has_required_artifacts else "degraded",
        "service": "fundamental",
        "using_real_model_artifacts": has_required_artifacts,
        **artifact_status,
    }


async def _save_history(
    db: AsyncSession,
    request: FundamentalAnalysisRequest,
    response: FundamentalAnalysisResponse,
) -> None:
    try:
        record = AnalysisHistory(
            user_id="anonymous",
            ticker=request.ticker.upper(),
            market=request.market,
            analysis_types=["fundamental"],
            results=response.model_dump(mode="json"),
        )
        db.add(record)
        await db.commit()
    except Exception as exc:
        logger.warning(f"Failed to save fundamental analysis history: {exc}")
        await db.rollback()
