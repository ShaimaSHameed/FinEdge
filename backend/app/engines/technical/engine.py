from __future__ import annotations

from app.config import settings
from app.engines.technical.minute_runtime import MinuteTechnicalArtifactStore, MinuteTechnicalModelRuntime
from app.engines.technical.model_runtime import TechnicalArtifactStore, TechnicalModelRuntime
from app.schemas.technical import TechnicalAnalysisRequest, TechnicalAnalysisResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TechnicalAnalysisEngine:
    def __init__(self) -> None:
        self.artifact_store = TechnicalArtifactStore()
        self.model_runtime = TechnicalModelRuntime(self.artifact_store)
        self.minute_artifact_store = MinuteTechnicalArtifactStore()
        self.minute_model_runtime = MinuteTechnicalModelRuntime(self.minute_artifact_store)

    async def analyze(self, request: TechnicalAnalysisRequest) -> TechnicalAnalysisResponse:
        ticker = request.ticker.upper()
        if request.model_version == "final_1min":
            return await self._analyze_one_minute(request, ticker)

        status = self.artifact_status()
        one_day_status = status["final_1d"]
        if settings.TECHNICAL_REQUIRE_MODEL_ARTIFACT and not one_day_status["using_real_model_artifacts"]:
            missing = ", ".join(one_day_status.get("missing_files") or [])
            raise ValueError(
                "Real technical model artifacts are not ready. "
                f"Resolved artifact dir: {one_day_status['resolved_artifact_dir']}. "
                f"Missing: {missing or 'unknown'}"
            )

        if request.model_version != "final_1d":
            logger.info(
                "Technical request asked for deprecated %s; using real final_1d artifact model",
                request.model_version,
            )

        result = await self.model_runtime.predict(
            ticker=ticker,
            history_bars=request.history_bars,
            forecast_bars=request.forecast_bars,
        )

        return TechnicalAnalysisResponse(
            ticker=ticker,
            timeframe="1D",
            model_version="final_1d",
            source="model_artifact",
            source_model=result.source_model,
            artifact_version=result.artifact_version,
            artifact_path=result.artifact_path,
            data_source=result.data_source,
            inference_input_bars=result.inference_input_bars,
            required_input_bars=result.required_input_bars,
            latest_price=result.latest_price,
            history_bars=result.history,
            forecast_bars=result.forecast,
            generated_at=result.generated_at,
            ensemble_weights=result.ensemble_weights,
            expert_versions=result.expert_versions,
            policy=result.policy,
            regime=result.regime,
        )

    async def _analyze_one_minute(self, request: TechnicalAnalysisRequest, ticker: str) -> TechnicalAnalysisResponse:
        status = self.minute_artifact_store.status()
        if settings.TECHNICAL_REQUIRE_MODEL_ARTIFACT and not status["using_real_model_artifacts"]:
            missing = ", ".join(status.get("missing_files") or [])
            raise ValueError(
                "Real one-minute technical model artifacts are not ready. "
                f"Resolved artifact dir: {status['resolved_artifact_dir']}. "
                f"Missing: {missing or 'unknown'}"
            )

        result = await self.minute_model_runtime.predict(
            ticker=ticker,
            history_bars=request.history_bars,
            forecast_bars=request.forecast_bars,
        )

        return TechnicalAnalysisResponse(
            ticker=ticker,
            timeframe="1Min",
            model_version="final_1min",
            source="model_artifact",
            source_model=result.source_model,
            artifact_version=result.artifact_version,
            artifact_path=result.artifact_path,
            data_source=result.data_source,
            inference_input_bars=result.inference_input_bars,
            required_input_bars=result.required_input_bars,
            latest_price=result.latest_price,
            history_bars=result.history,
            forecast_bars=result.forecast,
            generated_at=result.generated_at,
            ensemble_weights=result.ensemble_weights,
            expert_versions=result.expert_versions,
            policy=result.policy,
            regime=result.regime,
        )

    def artifact_status(self) -> dict:
        one_day = self.artifact_store.status()
        one_minute = self.minute_artifact_store.status()
        return {
            **one_day,
            "final_1d": one_day,
            "final_1min": one_minute,
            "ready_for_live_inference": one_day["ready_for_live_inference"] or one_minute["ready_for_live_inference"],
        }
