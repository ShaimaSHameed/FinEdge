from fastapi import APIRouter, HTTPException

from app.engines.ensemble import EnsembleBacktestEngine
from app.schemas.ensemble import EnsembleBacktestRequest, EnsembleBacktestResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/analyze", tags=["ensemble"])
ensemble_engine = EnsembleBacktestEngine()


@router.get("/ensemble/health")
async def ensemble_health() -> dict:
    return ensemble_engine.health()


@router.post("/ensemble/backtest", response_model=EnsembleBacktestResponse)
async def backtest_ensemble(request: EnsembleBacktestRequest) -> EnsembleBacktestResponse:
    try:
        logger.info("Received ensemble backtest request for %s", request.ticker)
        return await ensemble_engine.backtest(request)
    except ValueError as exc:
        logger.error(f"Ensemble backtest validation error: {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error(f"Ensemble backtest failed: {exc}")
        raise HTTPException(status_code=500, detail="Failed to perform ensemble backtest") from exc
