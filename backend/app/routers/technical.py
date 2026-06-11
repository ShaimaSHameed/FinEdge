from fastapi import APIRouter, HTTPException

from app.engines.technical import TechnicalAnalysisEngine
from app.schemas.technical import TechnicalAnalysisRequest, TechnicalAnalysisResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/analyze", tags=["technical"])
technical_engine = TechnicalAnalysisEngine()


@router.get("/technical/health")
async def technical_health() -> dict:
    status = technical_engine.artifact_status()
    return {
        "status": "healthy" if status["ready_for_live_inference"] else "degraded",
        **status,
    }


@router.post("/technical", response_model=TechnicalAnalysisResponse)
async def analyze_technical(request: TechnicalAnalysisRequest) -> TechnicalAnalysisResponse:
    try:
        logger.info(
            "Received technical analysis request for %s using model %s",
            request.ticker,
            request.model_version,
        )
        return await technical_engine.analyze(request)
    except ValueError as exc:
        logger.error(f"Technical analysis validation error: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Technical analysis failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to perform technical analysis") from exc
