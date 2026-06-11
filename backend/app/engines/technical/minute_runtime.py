from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from app.config import settings
from app.schemas.technical import TechnicalCandle


MINUTE_MARKET_STATE_COLUMNS = [
    "rsi_14",
    "macd_histogram",
    "bb_position",
    "atr_14_pct",
    "price_momentum_5",
    "price_momentum_20",
    "vwap_20_dev",
    "obv_slope",
    "direction",
    "relative_volume",
]
PORTFOLIO_STATE = [1.0, 0.0, 1.0, 0.0]
ACTION_NEUTRAL_BAND = 0.10
DEFAULT_CRYPTO_SYMBOL = "BTC/USD"

FINAL_WEIGHT_PRIOR_BLEND = 1.0
FINAL_EXCLUDED_EXPERTS = {"v9_2"}
FINAL_AGGREGATION_WEIGHT_PRIOR = {
    "v8_5": 0.10,
    "v9_1": 0.10,
    "v9_5": 0.80,
}
FINAL_AGGREGATE_SHRINK = 0.70
FINAL_GUARD_LOOKBACK = 390
FINAL_SOFT_SWING_Q95_MULT = 1.35
FINAL_SOFT_SWING_ATR_MULT = 0.55
FINAL_SOFT_SWING_MIN_MOVE = 0.25
FINAL_SOFT_SWING_EXCESS_SCALE = 0.15
FINAL_SOFT_SWING_HARD_MULT = 1.10
FINAL_SOFT_SWING_EXTREME_SCALE = 0.01
FINAL_EMPIRICAL_Q95_MULT = 1.15
FINAL_EMPIRICAL_STEP_BASE_MULT = 1.0
FINAL_EMPIRICAL_ATR_MULT = 0.55
FINAL_EMPIRICAL_MIN_MOVE = 0.25
FINAL_EMPIRICAL_EXCESS_SCALE = 0.12
FINAL_EMPIRICAL_HARD_MULT = 1.08
FINAL_EMPIRICAL_EXTREME_SCALE = 0.01
FINAL_CANDLE_RANGE_Q97_MULT = 1.35
FINAL_CANDLE_RANGE_MIN_WICK = 0.35
FINAL_T1_TEMPORAL_Q95_MULT = 1.10
FINAL_T1_TEMPORAL_ATR_MULT = 0.45
FINAL_T1_TEMPORAL_MIN_MOVE = 0.22
FINAL_T1_TEMPORAL_EXCESS_SCALE = 0.10
FINAL_T1_TEMPORAL_HARD_MULT = 1.08
FINAL_T1_TEMPORAL_EXTREME_SCALE = 0.00
FINAL_T1_TEMPORAL_RECAP_EXCESS_SCALE = 0.08
FINAL_T1_TEMPORAL_RECAP_HARD_MULT = 1.06
FINAL_T1_TEMPORAL_RECAP_EXTREME_SCALE = 0.00
FINAL_T1_DIRECTION_VOTE_THRESHOLD = 0.35
FINAL_T1_DIRECTION_MOMENTUM_BARS = 3
FINAL_T1_DIRECTION_MOMENTUM_MIN_MOVE = 0.05
FINAL_T1_DIRECTION_MAX_ABS_DELTA_TO_OVERRIDE = 0.35
FINAL_T1_DIRECTION_MIN_OVERRIDE_MOVE = 0.10
FINAL_T1_DIRECTION_MAX_OVERRIDE_MOVE = 0.25
FINAL_T1_SHIFT_FADE_POWER = 2.0
FINAL_MAX_FORECAST_BARS = 15
FINAL_CANDLE_SIZE_SCALE = 0.70


@dataclass
class MinuteExpertBundle:
    name: str
    version: str
    lookback: int
    feature_mode: str
    architecture: str
    ensemble_size: int
    model: Any
    scaler: Dict[str, Any]
    feature_columns: List[str]
    inference_config: Dict[str, Any]
    retrieval_artifact: Optional[Dict[str, Any]]
    rag_config: Dict[str, Any]


@dataclass
class MinuteModelResult:
    history: List[TechnicalCandle]
    forecast: List[TechnicalCandle]
    latest_price: float
    source_model: str
    artifact_version: str
    artifact_path: str
    generated_at: datetime
    ensemble_weights: Dict[str, float]
    expert_versions: Dict[str, str]
    policy: Dict[str, float | str]
    regime: str
    data_source: str
    inference_input_bars: int
    required_input_bars: int


class MinuteTechnicalArtifactStore:
    def __init__(self, artifact_dir: str | None = None) -> None:
        self.artifact_dir = Path(artifact_dir or settings.TECHNICAL_INTRADAY_ARTIFACT_DIR)
        self._local_fallback_dir = Path(__file__).resolve().parents[4] / "Technical_Model" / "final_artifacts"

    @property
    def root(self) -> Path:
        if self.artifact_dir.exists():
            return self.artifact_dir
        return self._local_fallback_dir

    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    def load_manifest(self) -> Dict[str, Any]:
        manifest_path = self.manifest_path()
        if not manifest_path.exists():
            raise FileNotFoundError(f"One-minute technical model manifest is missing: {manifest_path}")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def status(self) -> Dict[str, Any]:
        root = self.root
        manifest_exists = self.manifest_path().exists()
        manifest: Dict[str, Any] = {}
        if manifest_exists:
            try:
                manifest = self.load_manifest()
            except Exception:
                manifest = {}

        expected_files = [
            root / "manifest.json",
            root / "ensemble" / "weights.json",
            root / "rl" / "policy.pt",
            root / "rl" / "state_schema.json",
        ]
        experts = list((manifest.get("forecast_models") or {}).keys())
        for expert in experts:
            expected_files.extend(
                [
                    root / "models" / expert / "model.pt",
                    root / "models" / expert / "scaler.npz",
                    root / "models" / expert / "feature_manifest.json",
                    root / "models" / expert / "inference_config.json",
                ]
            )
        missing = [str(path) for path in expected_files if not path.exists()]
        runtime = manifest.get("runtime", {})
        return {
            "artifact_dir": str(self.artifact_dir),
            "resolved_artifact_dir": str(root),
            "artifact_dir_exists": root.exists(),
            "manifest_exists": manifest_exists,
            "missing_files": missing,
            "using_real_model_artifacts": root.exists() and manifest_exists and bool(experts) and not missing,
            "model_symbol": runtime.get("symbol"),
            "timeframe": "1Min",
            "horizon": runtime.get("horizon"),
            "created_at_utc": runtime.get("created_at_utc"),
            "ready_for_live_inference": (
                root.exists()
                and manifest_exists
                and bool(experts)
                and not missing
                and bool(_alpaca_api_key() and _alpaca_secret_key())
            ),
        }


class MinuteTechnicalModelRuntime:
    def __init__(self, artifact_store: MinuteTechnicalArtifactStore | None = None) -> None:
        self.artifact_store = artifact_store or MinuteTechnicalArtifactStore()
        self._bundles: Dict[str, MinuteExpertBundle] | None = None
        self._policy: Any | None = None
        self._policy_state_dim: int | None = None

    async def predict(self, ticker: str, history_bars: int, forecast_bars: int) -> MinuteModelResult:
        np, pd, torch, nn, F = self._deps()
        manifest = self.artifact_store.load_manifest()
        runtime = manifest.get("runtime", {})
        horizon = int(runtime.get("horizon", 50))
        forecast_count = max(1, min(int(forecast_bars), horizon, FINAL_MAX_FORECAST_BARS))
        required_input_bars = self._required_input_bars(manifest)

        raw_bars, data_source = await self._fetch_minute_bars(ticker, required_input_bars)
        if len(raw_bars) < required_input_bars:
            raise ValueError(
                f"Not enough 1-minute bars available for {ticker}; need {required_input_bars}, received {len(raw_bars)}"
            )

        feature_frames = self._build_feature_frames(raw_bars, pd, np)
        bundles = self._load_bundles()
        expected_experts = self._active_experts(manifest)
        weights = self._build_final_inference_weights(self._load_weights(), expected_experts)

        expert_paths: Dict[str, Any] = {}
        previous_expert_paths: Dict[str, Any] = {}
        expert_versions: Dict[str, str] = {}
        expert_regimes: Dict[str, float] = {}
        aggregate_anchor_prev_close: Optional[float] = None
        previous_aggregate_anchor_prev_close: Optional[float] = None
        anchor_timestamp = feature_frames["core"]["timestamp"].iloc[-1]

        for expert_name in expected_experts:
            bundle = bundles[expert_name]
            feature_frame = feature_frames[bundle.feature_mode]
            model_input = self._build_latest_input(feature_frame, bundle, pd, np)
            if aggregate_anchor_prev_close is None:
                aggregate_anchor_prev_close = float(model_input["anchor_prev_close"])
            regime_name, regime_multiplier, regime_indicator = self._detect_regime_multiplier(model_input["context"], np)
            temperature = float(bundle.inference_config.get("sampling_temperature", 1.5))
            temperature *= self._intraday_temperature(model_input["anchor_timestamp"], pd) / 1.5
            path = self._generate_sampled_path(bundle, model_input, temperature, regime_multiplier, np, torch)
            expert_paths[expert_name] = path
            expert_versions[expert_name] = bundle.version
            expert_regimes[expert_name] = regime_indicator

            if len(feature_frame) >= bundle.lookback + 2:
                previous_model_input = self._build_anchor_input(feature_frame, bundle, len(feature_frame) - 2, pd, np)
                if previous_aggregate_anchor_prev_close is None:
                    previous_aggregate_anchor_prev_close = float(previous_model_input["anchor_prev_close"])
                previous_regime_multiplier = 1.0
                if bundle.feature_mode == "regime":
                    previous_history = feature_frame.iloc[max(0, len(feature_frame) - 1 - 390) : len(feature_frame) - 1].copy()
                    _, previous_regime_multiplier, _ = self._detect_regime_multiplier(previous_history, np)
                previous_temperature = float(bundle.inference_config.get("sampling_temperature", 1.5))
                previous_temperature *= self._intraday_temperature(previous_model_input["anchor_timestamp"], pd) / 1.5
                previous_expert_paths[expert_name] = self._generate_sampled_path(
                    bundle,
                    previous_model_input,
                    previous_temperature,
                    previous_regime_multiplier,
                    np,
                    torch,
                )

        if aggregate_anchor_prev_close is None:
            raise ValueError("No one-minute expert paths were generated.")

        aggregate_path = np.zeros_like(next(iter(expert_paths.values())), dtype=np.float32)
        aggregate_regime = 0.0
        for expert_name, path in expert_paths.items():
            weight = float(weights.get(expert_name, 0.0))
            aggregate_path += weight * path
            aggregate_regime += weight * float(expert_regimes.get(expert_name, 0.0))
        aggregate_guard_history = self._guard_history(feature_frames["technical"], len(feature_frames["technical"]) - 1)
        aggregate_path = self._postprocess_aggregate_path(
            aggregate_path,
            aggregate_anchor_prev_close,
            aggregate_guard_history,
            np,
        )

        previous_aggregate_next_close: Optional[float] = None
        if len(previous_expert_paths) == len(expected_experts) and previous_aggregate_anchor_prev_close is not None:
            previous_aggregate_path = np.zeros_like(next(iter(previous_expert_paths.values())), dtype=np.float32)
            for expert_name, path in previous_expert_paths.items():
                previous_aggregate_path += float(weights.get(expert_name, 0.0)) * path
            previous_guard_history = self._guard_history(feature_frames["technical"], len(feature_frames["technical"]) - 2)
            previous_aggregate_path = self._postprocess_aggregate_path(
                previous_aggregate_path,
                previous_aggregate_anchor_prev_close,
                previous_guard_history,
                np,
            )
            previous_aggregate_next_close = float(previous_aggregate_path[0, 3])

        aggregate_path = self._apply_t1_temporal_direction_guard(
            aggregate_path,
            aggregate_anchor_prev_close,
            aggregate_guard_history,
            expert_paths,
            weights,
            previous_aggregate_next_close,
            np,
        )
        aggregate_path = self._scale_candle_sizes(aggregate_path, FINAL_CANDLE_SIZE_SCALE, np)

        policy = self._run_policy(aggregate_path, feature_frames["technical"], aggregate_regime, np, torch)
        timestamps = self._future_minutes(anchor_timestamp, forecast_count, pd)
        forecast = [
            TechnicalCandle(
                timestamp=timestamps[idx].to_pydatetime() if hasattr(timestamps[idx], "to_pydatetime") else timestamps[idx],
                open=round(float(row[0]), 4),
                high=round(float(row[1]), 4),
                low=round(float(row[2]), 4),
                close=round(float(row[3]), 4),
                volume=0,
                is_prediction=True,
            )
            for idx, row in enumerate(aggregate_path[:forecast_count])
        ]

        history_count = max(1, min(int(history_bars), len(raw_bars)))
        return MinuteModelResult(
            history=raw_bars[-history_count:],
            forecast=forecast,
            latest_price=float(feature_frames["core"]["close"].iloc[-1]),
            source_model="final_1min_ensemble_rl",
            artifact_version=str(runtime.get("created_at_utc") or "unknown"),
            artifact_path=str(self.artifact_store.root),
            generated_at=datetime.now(timezone.utc),
            ensemble_weights=weights,
            expert_versions=expert_versions,
            policy=policy,
            regime=self._regime_name(aggregate_regime),
            data_source=data_source,
            inference_input_bars=len(raw_bars),
            required_input_bars=required_input_bars,
        )

    async def _fetch_minute_bars(self, ticker: str, required_bars: int) -> Tuple[List[TechnicalCandle], str]:
        if not _alpaca_api_key() or not _alpaca_secret_key():
            raise ValueError("Alpaca API credentials are required for one-minute technical inference.")

        normalized = self._normalize_symbol(ticker)
        lookback_days = max(3, math.ceil(required_bars / 390) + 3)
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        start = end - timedelta(days=lookback_days)

        if "/" in normalized:
            bars = await self._fetch_crypto_minute_bars(normalized, start, end)
            return bars[-required_bars:], "alpaca-crypto-1min-live"

        bars = await self._fetch_stock_minute_bars(normalized, start, end, required_bars)
        return bars[-required_bars:], "alpaca-stock-1min-live"

    async def _fetch_stock_minute_bars(
        self,
        ticker: str,
        start: datetime,
        end: datetime,
        required_bars: int,
    ) -> List[TechnicalCandle]:
        url = f"{settings.ALPACA_DATA_URL.rstrip('/')}/v2/stocks/{ticker}/bars"
        params = {
            "timeframe": "1Min",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "adjustment": "raw",
            "feed": settings.ALPACA_STOCK_FEED,
            "sort": "asc",
            "limit": min(max(required_bars + 500, required_bars), 10000),
        }
        payload = await self._alpaca_get(url, params)
        return [self._bar_from_payload(bar) for bar in payload.get("bars", [])]

    async def _fetch_crypto_minute_bars(self, symbol: str, start: datetime, end: datetime) -> List[TechnicalCandle]:
        url = f"{settings.ALPACA_DATA_URL.rstrip('/')}/v1beta3/crypto/us/bars"
        params = {
            "symbols": symbol,
            "timeframe": "1Min",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "sort": "asc",
            "limit": 10000,
        }
        payload = await self._alpaca_get(url, params)
        bars_by_symbol = payload.get("bars") or {}
        return [self._bar_from_payload(bar) for bar in bars_by_symbol.get(symbol, [])]

    async def _alpaca_get(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        headers = {
            "APCA-API-KEY-ID": _alpaca_api_key(),
            "APCA-API-SECRET-KEY": _alpaca_secret_key(),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _bar_from_payload(bar: Dict[str, Any]) -> TechnicalCandle:
        return TechnicalCandle(
            timestamp=datetime.fromisoformat(str(bar["t"]).replace("Z", "+00:00")),
            open=float(bar["o"]),
            high=float(bar["h"]),
            low=float(bar["l"]),
            close=float(bar["c"]),
            volume=int(float(bar.get("v", 0) or 0)),
        )

    def _build_feature_frames(self, bars: List[TechnicalCandle], pd: Any, np: Any) -> Dict[str, Any]:
        base = pd.DataFrame(
            [
                {
                    "timestamp": candle.timestamp,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                    "trade_count": 0.0,
                    "vwap": (candle.high + candle.low + candle.close) / 3.0,
                    "row_imputed": False,
                }
                for candle in bars
            ]
        ).sort_values("timestamp").reset_index(drop=True)
        base["session_date"] = pd.to_datetime(base["timestamp"], utc=True).dt.date.astype(str)
        core = self._build_feature_frame_for_mode(base, "core", pd, np)
        technical = self._build_feature_frame_for_mode(base, "technical", pd, np)
        regime = self._build_feature_frame_for_mode(base, "regime", pd, np)
        return {"core": core, "technical": technical, "regime": regime}

    def _build_feature_frame_for_mode(self, bars: Any, mode: str, pd: Any, np: Any) -> Any:
        core = bars.copy().sort_values("timestamp").reset_index(drop=True)
        core["prev_close"] = core["close"].shift(1)
        session_change = core["session_date"] != core["session_date"].shift(1)
        core.loc[session_change, "prev_close"] = core.loc[session_change, "open"]
        core["prev_close"] = core["prev_close"].fillna(core["open"])
        safe_prev = core["prev_close"].replace(0.0, np.nan).ffill().bfill()

        prev_volume = core["volume"].shift(1).fillna(core["volume"].median())
        prev_trade_count = core["trade_count"].shift(1).fillna(core["trade_count"].median())
        core["rOpen"] = np.log((core["open"] / safe_prev).clip(lower=1e-8))
        core["rHigh"] = np.log((core["high"] / safe_prev).clip(lower=1e-8))
        core["rLow"] = np.log((core["low"] / safe_prev).clip(lower=1e-8))
        core["rClose"] = np.log((core["close"] / safe_prev).clip(lower=1e-8))
        core["returns"] = core["rClose"]
        core["logVolChange"] = np.log1p(core["volume"]) - np.log1p(prev_volume)
        core["logTradeCountChange"] = np.log1p(core["trade_count"]) - np.log1p(prev_trade_count)
        core["vwapDelta"] = ((core["vwap"] - safe_prev) / safe_prev).replace([np.inf, -np.inf], np.nan)
        core["rangeFrac"] = ((core["high"] - core["low"]) / safe_prev).clip(lower=0.0)
        candle_span = (core["high"] - core["low"]).replace(0.0, np.nan)
        core["orderFlowProxy"] = ((core["close"] - core["open"]) / candle_span).fillna(0.0) * np.log1p(core["volume"])
        core["tickPressure"] = (((core["close"] - core["low"]) - (core["high"] - core["close"])) / candle_span).fillna(0.0)

        technical = self._calculate_technical_features(core, pd, np)
        if mode == "technical":
            features = pd.concat([core, technical], axis=1)
        elif mode == "regime":
            features = core.copy()
            features["atr_14"] = technical["atr_14"]
            features["atr_14_pct"] = technical["atr_14_pct"]
            features["turbulence_60"] = self._compute_turbulence(features["returns"], pd, np)
            features["regime_indicator"] = self._build_dynamic_regime_indicator(features["atr_14_pct"], features["turbulence_60"], np)
        elif mode == "core":
            features = core.copy()
        else:
            raise ValueError(f"Unsupported one-minute feature mode: {mode}")

        if "turbulence_60" not in features.columns:
            features["turbulence_60"] = self._compute_turbulence(features["returns"], pd, np)
        if "atr_14" not in features.columns:
            features["atr_14"] = technical["atr_14"]
        if "atr_14_pct" not in features.columns:
            features["atr_14_pct"] = technical["atr_14_pct"]
        if "regime_indicator" not in features.columns:
            features["regime_indicator"] = self._build_dynamic_regime_indicator(features["atr_14_pct"], features["turbulence_60"], np)
        features["relative_volume"] = (
            features["volume"] / features["volume"].rolling(20, min_periods=5).mean().replace(0.0, np.nan)
        )
        return features.replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)

    def _calculate_technical_features(self, core: Any, pd: Any, np: Any) -> Any:
        out = pd.DataFrame(index=core.index)
        close = core["close"]
        high = core["high"]
        low = core["low"]
        volume = core["volume"]
        out["sma_5"] = close.rolling(5, min_periods=1).mean()
        out["sma_10"] = close.rolling(10, min_periods=1).mean()
        out["sma_20"] = close.rolling(20, min_periods=1).mean()
        out["sma_50"] = close.rolling(50, min_periods=1).mean()
        out["ema_12"] = close.ewm(span=12, adjust=False).mean()
        out["ema_26"] = close.ewm(span=26, adjust=False).mean()
        out["macd_line"] = out["ema_12"] - out["ema_26"]
        out["macd_signal"] = out["macd_line"].ewm(span=9, adjust=False).mean()
        out["macd_histogram"] = out["macd_line"] - out["macd_signal"]
        out["macd_momentum"] = out["macd_histogram"].diff()
        delta = close.diff()
        gain = delta.clip(lower=0.0).ewm(alpha=1 / 14, adjust=False).mean()
        loss = (-delta.clip(upper=0.0)).ewm(alpha=1 / 14, adjust=False).mean()
        out["rsi_14"] = 100.0 - (100.0 / (1.0 + (gain / loss.replace(0.0, np.nan))))
        out["rsi_14_slope"] = out["rsi_14"].diff()
        rolling_low = low.rolling(14, min_periods=1).min()
        rolling_high = high.rolling(14, min_periods=1).max()
        out["stoch_k"] = 100.0 * (close - rolling_low) / (rolling_high - rolling_low).replace(0.0, np.nan)
        out["stoch_d"] = out["stoch_k"].rolling(3, min_periods=1).mean()
        mid = close.rolling(20, min_periods=1).mean()
        std = close.rolling(20, min_periods=1).std().fillna(0.0)
        out["bb_upper"] = mid + (2.0 * std)
        out["bb_lower"] = mid - (2.0 * std)
        out["bb_width"] = (out["bb_upper"] - out["bb_lower"]) / mid.replace(0.0, np.nan)
        out["bb_position"] = (close - out["bb_lower"]) / (out["bb_upper"] - out["bb_lower"]).replace(0.0, np.nan)
        prev_close = close.shift(1)
        true_range = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        out["atr_14"] = true_range.ewm(alpha=1 / 14, adjust=False).mean()
        out["atr_14_pct"] = out["atr_14"] / close.replace(0.0, np.nan)
        direction = np.sign(close.diff().fillna(0.0))
        out["obv"] = (direction * volume.fillna(0.0)).cumsum()
        out["obv_slope"] = out["obv"].diff(5) / 5.0
        out["vwap_20"] = core["vwap"].rolling(20, min_periods=1).mean()
        out["vwap_20_dev"] = (core["close"] - out["vwap_20"]) / out["vwap_20"].replace(0.0, np.nan)
        out["price_momentum_5"] = close.pct_change(5)
        out["price_momentum_10"] = close.pct_change(10)
        out["price_momentum_20"] = close.pct_change(20)
        body = core["close"] - core["open"]
        full_range = (core["high"] - core["low"]).replace(0.0, np.nan)
        out["body_size"] = body
        out["body_pct"] = body / full_range
        out["upper_shadow"] = core["high"] - core[["open", "close"]].max(axis=1)
        out["lower_shadow"] = core[["open", "close"]].min(axis=1) - core["low"]
        out["direction"] = np.sign(body)
        return out.replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)

    @staticmethod
    def _compute_turbulence(returns: Any, pd: Any, np: Any) -> Any:
        rolling_mean = returns.rolling(60, min_periods=2).mean()
        rolling_std = returns.rolling(60, min_periods=2).std().replace(0.0, np.nan)
        return ((returns - rolling_mean) / rolling_std).abs().replace([np.inf, -np.inf], np.nan).fillna(0.0)

    @staticmethod
    def _build_dynamic_regime_indicator(atr_pct: Any, turbulence: Any, np: Any) -> Any:
        atr_q75 = atr_pct.rolling(390, min_periods=60).quantile(0.75).shift(1)
        atr_q90 = atr_pct.rolling(390, min_periods=60).quantile(0.90).shift(1)
        turb_q75 = turbulence.rolling(390, min_periods=60).quantile(0.75).shift(1)
        turb_q90 = turbulence.rolling(390, min_periods=60).quantile(0.90).shift(1)
        crisis = (atr_pct >= atr_q90.fillna(np.inf)) & (turbulence >= turb_q90.fillna(np.inf))
        elevated = (atr_pct >= atr_q75.fillna(np.inf)) | (turbulence >= turb_q75.fillna(np.inf))
        regime = atr_pct.copy()
        regime.loc[:] = 0.0
        regime.loc[elevated] = 0.5
        regime.loc[crisis] = 1.0
        return regime

    def _load_bundles(self) -> Dict[str, MinuteExpertBundle]:
        if self._bundles is not None:
            return self._bundles

        np, _, torch, nn, F = self._deps()
        root = self.artifact_store.root
        manifest = self.artifact_store.load_manifest()
        bundles: Dict[str, MinuteExpertBundle] = {}
        for expert_name, artifact in manifest.get("forecast_models", {}).items():
            expert_dir = root / "models" / expert_name
            checkpoint = torch.load(expert_dir / "model.pt", map_location="cpu", weights_only=False)
            model = self._build_model_from_checkpoint(checkpoint, torch, nn, F).eval()
            scaler_npz = np.load(expert_dir / "scaler.npz")
            feature_manifest = json.loads((expert_dir / "feature_manifest.json").read_text(encoding="utf-8"))
            inference_config = json.loads((expert_dir / "inference_config.json").read_text(encoding="utf-8"))
            retrieval_artifact = None
            rag_config = {"k_retrieve": 5, "blend_weight": 0.25}
            rag_path = expert_dir / "rag_database.npz"
            rag_config_path = expert_dir / "rag_config.json"
            if rag_path.exists():
                rag_npz = np.load(rag_path)
                retrieval_artifact = {
                    "embeddings": rag_npz["embeddings"].astype(np.float32),
                    "future_returns": rag_npz["future_returns"].astype(np.float32),
                }
            if rag_config_path.exists():
                rag_config = json.loads(rag_config_path.read_text(encoding="utf-8"))
            bundles[expert_name] = MinuteExpertBundle(
                name=expert_name,
                version=str(artifact.get("version", expert_name)),
                lookback=int(artifact.get("lookback", inference_config.get("lookback", 256))),
                feature_mode=str(artifact.get("feature_mode", "core")),
                architecture=str(artifact.get("architecture", "gru")),
                ensemble_size=max(1, int(inference_config.get("ensemble_size", 1))),
                model=model,
                scaler={"mean": scaler_npz["mean"].astype(np.float32), "std": scaler_npz["std"].astype(np.float32)},
                feature_columns=list(feature_manifest["feature_columns"]),
                inference_config=inference_config,
                retrieval_artifact=retrieval_artifact,
                rag_config=rag_config,
            )
        self._bundles = bundles
        return bundles

    def _build_model_from_checkpoint(self, checkpoint: Dict[str, Any], torch: Any, nn: Any, F: Any) -> Any:
        spec = checkpoint["spec"]
        architecture = spec["architecture"]
        input_dim = int(checkpoint["input_dim"])
        hidden_size = int(checkpoint["training_defaults"]["hidden_size"])
        num_layers = int(checkpoint["training_defaults"]["num_layers"])
        dropout = float(checkpoint["training_defaults"]["dropout"])
        horizon = int(self.artifact_store.load_manifest().get("runtime", {}).get("horizon", 50))
        if architecture in {"gru", "gru_rag"}:
            model = _minute_seq2seq_class(torch, nn, F)(input_dim, hidden_size, num_layers, dropout, horizon)
        elif architecture == "hybrid_itransformer_gru":
            model = _minute_hybrid_model_class(torch, nn, F)(
                input_dim=input_dim,
                lookback=int(spec["lookback"]),
                hidden_size=hidden_size,
                num_layers=num_layers,
                dropout=dropout,
                horizon=horizon,
                d_model=int(spec.get("d_model", 128)),
                n_heads=int(spec.get("n_heads", 8)),
                n_layers=int(spec.get("n_layers", 2)),
            )
        else:
            raise ValueError(f"Unsupported one-minute technical architecture: {architecture}")
        model.load_state_dict(checkpoint["state_dict"])
        return model

    def _build_latest_input(self, feature_frame: Any, bundle: MinuteExpertBundle, pd: Any, np: Any) -> Dict[str, Any]:
        if len(feature_frame) < bundle.lookback + 1:
            raise RuntimeError(f"Not enough rows to build latest input for {bundle.name}")
        return self._build_anchor_input(feature_frame, bundle, len(feature_frame) - 1, pd, np)

    def _build_anchor_input(self, feature_frame: Any, bundle: MinuteExpertBundle, anchor_index: int, pd: Any, np: Any) -> Dict[str, Any]:
        if anchor_index < bundle.lookback:
            raise RuntimeError(f"Not enough rows to build input for {bundle.name} at anchor {anchor_index}")
        if anchor_index >= len(feature_frame):
            raise RuntimeError(f"Anchor index {anchor_index} is outside feature frame for {bundle.name}")
        context = feature_frame.iloc[anchor_index - bundle.lookback : anchor_index].copy()
        feature_block = context.loc[:, bundle.feature_columns].to_numpy(dtype=np.float32)
        impute_frac = float(context["row_imputed"].mean())
        feature_block = np.concatenate(
            [feature_block, np.full((bundle.lookback, 1), impute_frac, dtype=np.float32)],
            axis=1,
        )
        scaled = ((feature_block[None, ...] - bundle.scaler["mean"]) / bundle.scaler["std"]).astype(np.float32)[0]
        return {
            "scaled_input": scaled,
            "anchor_prev_close": float(feature_frame["prev_close"].iloc[anchor_index]),
            "anchor_timestamp": pd.Timestamp(feature_frame["timestamp"].iloc[anchor_index]),
            "historical_closes": context["close"].to_numpy(dtype=np.float32),
            "context": context,
        }

    @staticmethod
    def _guard_history(feature_frame: Any, anchor_index: int) -> Any:
        end = max(0, int(anchor_index))
        start = max(0, end - int(FINAL_GUARD_LOOKBACK))
        if end <= start:
            return feature_frame.iloc[max(0, end - 1) : end].copy()
        return feature_frame.iloc[start:end].copy()

    def _generate_sampled_path(
        self,
        bundle: MinuteExpertBundle,
        model_input: Dict[str, Any],
        temperature: float,
        regime_multiplier: float,
        np: Any,
        torch: Any,
    ) -> Any:
        x_tensor = torch.from_numpy(model_input["scaled_input"][None, ...]).float()
        with torch.inference_mode():
            encoder_memory, decoder_hidden_init = bundle.model.encode_sequence(x_tensor)
        decoder_input_init = x_tensor[:, -1, :4]
        candidate_paths = []
        retrieved_future = self._retrieve_future_returns(bundle, model_input["scaled_input"], np, torch)
        for seed_offset in range(bundle.ensemble_size):
            torch.manual_seed(137 + seed_offset)
            decoder_hidden = decoder_hidden_init.clone()
            decoder_input = decoder_input_init.clone()
            sampled_steps = []
            for _ in range(int(self.artifact_store.load_manifest().get("runtime", {}).get("horizon", 50))):
                with torch.inference_mode():
                    mu, log_sigma, decoder_hidden = bundle.model.decode_step(decoder_input, decoder_hidden, encoder_memory)
                    sigma = torch.exp(log_sigma).clamp(min=float(bundle.inference_config.get("min_predicted_vol", 0.0001)))
                    sample = mu + torch.randn_like(mu) * sigma * temperature * regime_multiplier
                sampled_steps.append(sample.squeeze(0).detach().cpu().numpy().astype(np.float32))
                decoder_input = sample
            sampled_returns = np.stack(sampled_steps).astype(np.float32)
            if retrieved_future is not None:
                blend_weight = float(bundle.rag_config.get("blend_weight", 0.25))
                sampled_returns = ((1.0 - blend_weight) * sampled_returns + blend_weight * retrieved_future).astype(np.float32)
            candidate_paths.append(self._returns_to_prices(float(model_input["anchor_prev_close"]), sampled_returns, np))
        candidate_paths = np.stack(candidate_paths).astype(np.float32)
        return self._select_best_path_by_trend(
            model_input["historical_closes"],
            candidate_paths,
            int(bundle.inference_config.get("trend_lookback_bars", 20)),
            float(bundle.inference_config.get("strong_trend_threshold", 0.002)),
            np,
        )

    def _retrieve_future_returns(self, bundle: MinuteExpertBundle, x_scaled_single: Any, np: Any, torch: Any) -> Any | None:
        if bundle.retrieval_artifact is None or len(bundle.retrieval_artifact["embeddings"]) == 0:
            return None
        with torch.inference_mode():
            query = torch.from_numpy(x_scaled_single[None, ...]).float()
            query_embedding = bundle.model.encode_context(query).detach().cpu().numpy()[0].astype(np.float32)
        query_embedding /= np.linalg.norm(query_embedding).clip(min=1e-8)
        similarities = bundle.retrieval_artifact["embeddings"] @ query_embedding
        k_retrieve = int(bundle.rag_config.get("k_retrieve", 5))
        top_idx = np.argsort(similarities)[-k_retrieve:][::-1]
        top_scores = similarities[top_idx]
        top_weights = np.exp(top_scores - top_scores.max())
        top_weights /= top_weights.sum().clip(min=1e-8)
        return np.tensordot(top_weights, bundle.retrieval_artifact["future_returns"][top_idx], axes=(0, 0)).astype(np.float32)

    def _run_policy(self, aggregate_path: Any, feature_frame: Any, aggregate_regime: float, np: Any, torch: Any) -> Dict[str, float | str]:
        policy_path = self.artifact_store.root / "rl" / "policy.pt"
        if not policy_path.exists():
            return {}
        if self._policy is None:
            checkpoint = torch.load(policy_path, map_location="cpu", weights_only=False)
            state_dim = int(checkpoint["state_dim"])
            policy = _actor_critic_class(torch)(state_dim)
            policy.load_state_dict(checkpoint["state_dict"])
            self._policy = policy.eval()
            self._policy_state_dim = state_dim

        latest_market = feature_frame.iloc[-1]
        market_state = latest_market.loc[MINUTE_MARKET_STATE_COLUMNS].to_numpy(dtype=np.float32)
        policy_state = np.concatenate(
            [
                aggregate_path.reshape(-1).astype(np.float32),
                market_state,
                np.asarray(PORTFOLIO_STATE, dtype=np.float32),
                np.asarray([aggregate_regime], dtype=np.float32),
            ]
        ).astype(np.float32)
        if self._policy_state_dim and policy_state.shape[0] != self._policy_state_dim:
            raise ValueError(f"One-minute policy state dimension mismatch: expected {self._policy_state_dim}, got {policy_state.shape[0]}")
        with torch.inference_mode():
            mean_action, action_std, value_estimate = self._policy(torch.from_numpy(policy_state).float().unsqueeze(0))
        raw_action = float(mean_action.item())
        policy_std = float(action_std.item())
        adjusted_action = raw_action * self._regime_scale(aggregate_regime)
        return {
            "raw_action": raw_action,
            "policy_std": policy_std,
            "confidence_score": float(1.0 / (1.0 + policy_std)),
            "critic_value_estimate": float(value_estimate.item()),
            "regime_scale": self._regime_scale(aggregate_regime),
            "recommended_position_pct": adjusted_action,
            "stance": self._stance_from_action(adjusted_action),
        }

    def _load_weights(self) -> Dict[str, float]:
        path = self.artifact_store.root / "ensemble" / "weights.json"
        if not path.exists():
            raise FileNotFoundError(f"One-minute technical ensemble weights are missing: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): float(value) for key, value in payload.items()}

    @staticmethod
    def _active_experts(manifest: Dict[str, Any]) -> List[str]:
        experts = [
            str(expert_name)
            for expert_name in manifest.get("forecast_models", {}).keys()
            if str(expert_name) not in FINAL_EXCLUDED_EXPERTS
        ]
        if not experts:
            raise ValueError("No active one-minute forecast experts are available after exclusions.")
        return experts

    def _required_input_bars(self, manifest: Dict[str, Any]) -> int:
        max_lookback = max(int(model.get("lookback", 0)) for model in manifest.get("forecast_models", {}).values())
        warmup = max(int(settings.TECHNICAL_INTRADAY_WARMUP_BARS), 390)
        return max_lookback + warmup

    @staticmethod
    def _normalize_symbol(ticker: str) -> str:
        cleaned = ticker.upper().strip()
        if cleaned in {"BTC", "BTCUSD", "XBTUSD"}:
            return DEFAULT_CRYPTO_SYMBOL
        return cleaned

    @staticmethod
    def _normalize_weights(weights: Dict[str, float], experts: Sequence[str]) -> Dict[str, float]:
        filtered = {expert: max(0.0, float(weights.get(expert, 0.0))) for expert in experts}
        total = sum(filtered.values())
        if total <= 0:
            uniform = 1.0 / max(len(experts), 1)
            return {expert: uniform for expert in experts}
        return {expert: value / total for expert, value in filtered.items()}

    def _build_final_inference_weights(self, saved_weights: Dict[str, float], experts: Sequence[str]) -> Dict[str, float]:
        saved_norm = self._normalize_weights(saved_weights, experts)
        prior_raw = {
            expert: float(FINAL_AGGREGATION_WEIGHT_PRIOR.get(expert, saved_norm.get(expert, 0.0)))
            for expert in experts
        }
        prior_norm = self._normalize_weights(prior_raw, experts)
        blended = {
            expert: (1.0 - FINAL_WEIGHT_PRIOR_BLEND) * saved_norm[expert] + FINAL_WEIGHT_PRIOR_BLEND * prior_norm[expert]
            for expert in experts
        }
        return self._normalize_weights(blended, experts)

    @staticmethod
    def _returns_to_prices(anchor_prev_close: float, return_seq: Any, np: Any) -> Any:
        prices = np.zeros_like(return_seq, dtype=np.float32)
        prev_close = float(anchor_prev_close)
        for step in range(return_seq.shape[0]):
            prices[step] = np.exp(return_seq[step]) * prev_close
            prev_close = float(prices[step, 3])
        return MinuteTechnicalModelRuntime._enforce_candle_validity(prices, np)

    @staticmethod
    def _enforce_candle_validity(path: Any, np: Any) -> Any:
        repaired = np.asarray(path, dtype=np.float32).copy()
        repaired[:, 1] = np.maximum(repaired[:, 1], np.maximum(repaired[:, 0], repaired[:, 3]))
        repaired[:, 2] = np.minimum(repaired[:, 2], np.minimum(repaired[:, 0], repaired[:, 3]))
        repaired = np.maximum(repaired, 0.01)
        return repaired

    def _postprocess_aggregate_path(self, path: Any, anchor_prev_close: float, history_slice: Any, np: Any) -> Any:
        processed = self._shrink_path_to_anchor(path, anchor_prev_close, FINAL_AGGREGATE_SHRINK, np)
        step_cap = self._compute_soft_swing_guard_cap(history_slice, np)
        processed = self._soft_cap_step_swings(processed, anchor_prev_close, step_cap, np)
        horizon_caps = self._compute_empirical_horizon_caps(history_slice, len(processed), step_cap, np)
        processed = self._empirical_anchor_envelope_cap_path(processed, anchor_prev_close, horizon_caps, np)
        processed = self._soft_cap_step_swings(processed, anchor_prev_close, step_cap, np)
        processed = self._cap_candle_ranges(processed, history_slice, np)
        return self._enforce_candle_validity(processed, np)

    def _shrink_path_to_anchor(self, path: Any, anchor_prev_close: float, shrink: float, np: Any) -> Any:
        anchor = float(anchor_prev_close)
        shrunk = anchor + float(shrink) * (np.asarray(path, dtype=np.float32) - anchor)
        return self._enforce_candle_validity(shrunk.astype(np.float32), np)

    @staticmethod
    def _finite_values(values: Any, np: Any) -> Any:
        array = np.asarray(values, dtype=np.float32)
        return array[np.isfinite(array)]

    def _compute_soft_swing_guard_cap(self, history_slice: Any, np: Any) -> float:
        if history_slice is None or history_slice.empty:
            return float(FINAL_SOFT_SWING_MIN_MOVE)

        if "prev_close" in history_slice.columns:
            prev_close = history_slice["prev_close"].astype(float).copy()
        else:
            prev_close = history_slice["close"].shift(1).astype(float)
            if len(prev_close) > 0:
                fallback = float(history_slice["open"].iloc[0]) if "open" in history_slice.columns else float(history_slice["close"].iloc[0])
                prev_close.iloc[0] = fallback

        close_moves = self._finite_values((history_slice["close"].astype(float) - prev_close).abs().to_numpy(dtype=np.float32), np)
        q95_cap = float(np.percentile(close_moves, 95) * FINAL_SOFT_SWING_Q95_MULT) if close_moves.size else 0.0

        atr_cap = self._latest_atr_value(history_slice, np) * FINAL_SOFT_SWING_ATR_MULT

        return max(float(FINAL_SOFT_SWING_MIN_MOVE), q95_cap, atr_cap)

    def _latest_atr_value(self, history_slice: Any, np: Any) -> float:
        if history_slice is None or history_slice.empty:
            return 0.0
        if "atr_14" in history_slice.columns:
            atr_values = self._finite_values(history_slice["atr_14"].to_numpy(dtype=np.float32), np)
            if atr_values.size:
                return float(atr_values[-1])
        if not {"high", "low", "close"}.issubset(history_slice.columns):
            return 0.0
        if "prev_close" in history_slice.columns:
            prev_close = history_slice["prev_close"].astype(float).copy()
        else:
            prev_close = history_slice["close"].shift(1).astype(float)
            if len(prev_close) > 0:
                fallback = float(history_slice["open"].iloc[0]) if "open" in history_slice.columns else float(history_slice["close"].iloc[0])
                prev_close.iloc[0] = fallback
        true_range = np.maximum.reduce(
            [
                (history_slice["high"].astype(float) - history_slice["low"].astype(float)).abs().to_numpy(dtype=np.float32),
                (history_slice["high"].astype(float) - prev_close).abs().to_numpy(dtype=np.float32),
                (history_slice["low"].astype(float) - prev_close).abs().to_numpy(dtype=np.float32),
            ]
        )
        finite = self._finite_values(true_range, np)
        if finite.size == 0:
            return 0.0
        return float(finite[-14:].mean())

    @staticmethod
    def _compress_abs_move(abs_move: float, cap: float, excess_scale: float, hard_mult: float, extreme_scale: float) -> float:
        if abs_move <= cap:
            return float(abs_move)
        hard_cap = cap * float(hard_mult)
        soft_ceiling = cap + float(excess_scale) * (hard_cap - cap)
        if abs_move <= hard_cap:
            return float(cap + float(excess_scale) * (abs_move - cap))
        return float(soft_ceiling + float(extreme_scale) * (abs_move - hard_cap))

    @staticmethod
    def _shift_candle_close(candle: Any, new_close: float, np: Any) -> Any:
        shifted = np.asarray(candle, dtype=np.float32).copy()
        old_close = float(shifted[3])
        delta = abs(float(new_close) - old_close)
        old_range = max(abs(float(shifted[0]) - old_close), abs(float(shifted[1]) - old_close), abs(float(shifted[2]) - old_close), 1e-9)
        scale = max(0.0, 1.0 - delta / old_range) if old_range > 1e-9 else 1.0
        scale = max(scale, 0.15)
        shifted[0] = float(new_close) + scale * (float(shifted[0]) - old_close)
        shifted[1] = float(new_close) + scale * (float(shifted[1]) - old_close)
        shifted[2] = float(new_close) + scale * (float(shifted[2]) - old_close)
        shifted[3] = float(new_close)
        shifted[1] = max(float(shifted[1]), float(shifted[0]), float(shifted[3]))
        shifted[2] = min(float(shifted[2]), float(shifted[0]), float(shifted[3]))
        return shifted.astype(np.float32)

    def _soft_cap_step_swings(self, path: Any, anchor_prev_close: float, step_move_cap: float, np: Any) -> Any:
        guarded = np.asarray(path, dtype=np.float32).copy()
        previous_close = float(anchor_prev_close)
        cap = float(step_move_cap)
        if cap <= 0.0:
            return self._enforce_candle_validity(guarded, np)

        for idx in range(len(guarded)):
            candle = guarded[idx].copy()
            close_delta = float(candle[3] - previous_close)
            abs_delta = abs(close_delta)
            if abs_delta > cap:
                compressed_delta = math.copysign(
                    self._compress_abs_move(
                        abs_delta,
                        cap,
                        FINAL_SOFT_SWING_EXCESS_SCALE,
                        FINAL_SOFT_SWING_HARD_MULT,
                        FINAL_SOFT_SWING_EXTREME_SCALE,
                    ),
                    close_delta,
                )
                candle = self._shift_candle_close(candle, previous_close + compressed_delta, np)
            guarded[idx] = candle
            previous_close = float(guarded[idx, 3])

        return self._enforce_candle_validity(guarded, np)

    def _compute_empirical_horizon_caps(self, history_slice: Any, horizon: int, base_step_cap: float, np: Any) -> Any:
        if history_slice is None or history_slice.empty:
            return np.full(horizon, float(FINAL_EMPIRICAL_MIN_MOVE), dtype=np.float32)

        closes = self._finite_values(history_slice["close"].to_numpy(dtype=np.float32), np)
        atr_value = self._latest_atr_value(history_slice, np)

        caps = []
        for step in range(1, int(horizon) + 1):
            empirical_cap = 0.0
            if closes.size > step:
                moves = np.abs(closes[step:] - closes[:-step])
                finite_moves = self._finite_values(moves, np)
                if finite_moves.size:
                    empirical_cap = float(np.percentile(finite_moves, 95) * FINAL_EMPIRICAL_Q95_MULT)
            step_root = math.sqrt(float(step))
            step_cap = float(base_step_cap) * FINAL_EMPIRICAL_STEP_BASE_MULT * step_root
            atr_horizon_cap = atr_value * FINAL_EMPIRICAL_ATR_MULT * step_root
            caps.append(max(float(FINAL_EMPIRICAL_MIN_MOVE) * step_root, empirical_cap, step_cap, atr_horizon_cap))
        return np.asarray(caps, dtype=np.float32)

    def _empirical_anchor_envelope_cap_path(self, path: Any, anchor_prev_close: float, horizon_caps: Any, np: Any) -> Any:
        guarded = np.asarray(path, dtype=np.float32).copy()
        anchor = float(anchor_prev_close)
        caps = np.asarray(horizon_caps, dtype=np.float32)
        if caps.size == 0:
            return self._enforce_candle_validity(guarded, np)

        for idx in range(len(guarded)):
            candle = guarded[idx].copy()
            cap = float(caps[min(idx, len(caps) - 1)])
            close_delta = float(candle[3] - anchor)
            abs_delta = abs(close_delta)
            if abs_delta > cap:
                compressed_delta = math.copysign(
                    self._compress_abs_move(
                        abs_delta,
                        cap,
                        FINAL_EMPIRICAL_EXCESS_SCALE,
                        FINAL_EMPIRICAL_HARD_MULT,
                        FINAL_EMPIRICAL_EXTREME_SCALE,
                    ),
                    close_delta,
                )
                candle = self._shift_candle_close(candle, anchor + compressed_delta, np)
            guarded[idx] = candle

        return self._enforce_candle_validity(guarded, np)

    def _cap_candle_ranges(self, path: Any, history_slice: Any, np: Any) -> Any:
        guarded = np.asarray(path, dtype=np.float32).copy()
        if history_slice is None or history_slice.empty or not {"high", "low"}.issubset(history_slice.columns):
            return self._enforce_candle_validity(guarded, np)

        recent_range = self._finite_values((history_slice["high"] - history_slice["low"]).to_numpy(dtype=np.float32), np)
        if recent_range.size == 0:
            return self._enforce_candle_validity(guarded, np)

        range_cap = max(
            float(FINAL_CANDLE_RANGE_MIN_WICK),
            float(np.percentile(recent_range, 97) * FINAL_CANDLE_RANGE_Q97_MULT),
        )
        for idx in range(len(guarded)):
            candle = guarded[idx].copy()
            body_high = max(float(candle[0]), float(candle[3]))
            body_low = min(float(candle[0]), float(candle[3]))
            candle[1] = min(float(candle[1]), body_high + range_cap)
            candle[2] = max(float(candle[2]), body_low - range_cap)
            candle[1] = max(float(candle[1]), float(candle[0]), float(candle[3]))
            candle[2] = min(float(candle[2]), float(candle[0]), float(candle[3]))
            guarded[idx] = candle

        return self._enforce_candle_validity(guarded, np)

    def _scale_candle_sizes(self, path: Any, scale: float, np: Any) -> Any:
        """Shrink forecast candle bodies and wicks while preserving close predictions."""
        scaled = np.asarray(path, dtype=np.float32).copy()
        factor = max(0.0, float(scale))
        for idx in range(len(scaled)):
            close = float(scaled[idx, 3])
            scaled[idx, 0] = close + factor * (float(scaled[idx, 0]) - close)
            scaled[idx, 1] = close + factor * (float(scaled[idx, 1]) - close)
            scaled[idx, 2] = close + factor * (float(scaled[idx, 2]) - close)
        return self._enforce_candle_validity(scaled, np)

    def _compute_t1_temporal_cap(self, history_slice: Any, np: Any) -> float:
        if history_slice is None or history_slice.empty:
            return float(FINAL_T1_TEMPORAL_MIN_MOVE)

        if "prev_close" in history_slice.columns:
            prev_close = history_slice["prev_close"].astype(float).copy()
        else:
            prev_close = history_slice["close"].shift(1).astype(float)
            if len(prev_close) > 0:
                fallback = float(history_slice["open"].iloc[0]) if "open" in history_slice.columns else float(history_slice["close"].iloc[0])
                prev_close.iloc[0] = fallback

        close_moves = self._finite_values((history_slice["close"].astype(float) - prev_close).abs().to_numpy(dtype=np.float32), np)
        q95_move = float(np.percentile(close_moves, 95)) if close_moves.size else 0.0
        atr_value = self._latest_atr_value(history_slice, np)
        return max(
            float(FINAL_T1_TEMPORAL_MIN_MOVE),
            float(FINAL_T1_TEMPORAL_Q95_MULT) * q95_move,
            float(FINAL_T1_TEMPORAL_ATR_MULT) * atr_value,
        )

    @staticmethod
    def _recent_momentum_sign(history_slice: Any, bars: int, min_move: float) -> float:
        if history_slice is None or history_slice.empty or "close" not in history_slice.columns:
            return 0.0
        closes = history_slice["close"].astype(float).replace([math.inf, -math.inf], float("nan")).dropna()
        if len(closes) <= int(bars):
            return 0.0
        delta = float(closes.iloc[-1] - closes.iloc[-1 - int(bars)])
        if abs(delta) < float(min_move):
            return 0.0
        return 1.0 if delta > 0.0 else -1.0

    @staticmethod
    def _direction_vote_from_expert_paths(expert_paths: Dict[str, Any], anchor_prev_close: float, weight_map: Dict[str, float], np: Any) -> float:
        vote_score = 0.0
        anchor = float(anchor_prev_close)
        for expert_name, expert_path in expert_paths.items():
            weight = float(weight_map.get(expert_name, 0.0))
            if weight <= 0.0:
                continue
            delta = float(np.asarray(expert_path, dtype=np.float32)[0, 3] - anchor)
            vote_score += weight * float(np.sign(delta))
        return float(vote_score)

    def _shift_path_from_first_close(self, path: Any, target_first_close: float, np: Any) -> Any:
        shifted = np.asarray(path, dtype=np.float32).copy()
        if len(shifted) == 0:
            return shifted
        close_shift = float(target_first_close) - float(shifted[0, 3])
        if abs(close_shift) <= 1e-12:
            return self._enforce_candle_validity(shifted.astype(np.float32), np)
        fade = np.linspace(1.0, 0.0, len(shifted), dtype=np.float32) ** float(FINAL_T1_SHIFT_FADE_POWER)
        shifted = shifted + close_shift * fade[:, None]
        return self._enforce_candle_validity(shifted.astype(np.float32), np)

    def _apply_t1_temporal_direction_guard(
        self,
        path: Any,
        anchor_prev_close: float,
        history_slice: Any,
        expert_paths: Dict[str, Any],
        weight_map: Dict[str, float],
        previous_next_close: Optional[float],
        np: Any,
    ) -> Any:
        guarded = np.asarray(path, dtype=np.float32).copy()
        target_first_close = float(guarded[0, 3])
        temporal_cap = self._compute_t1_temporal_cap(history_slice, np)

        if previous_next_close is not None:
            delta_from_prev = float(target_first_close) - float(previous_next_close)
            compressed = self._compress_abs_move(
                abs(delta_from_prev),
                temporal_cap,
                FINAL_T1_TEMPORAL_EXCESS_SCALE,
                FINAL_T1_TEMPORAL_HARD_MULT,
                FINAL_T1_TEMPORAL_EXTREME_SCALE,
            )
            target_first_close = float(previous_next_close) + math.copysign(compressed, delta_from_prev)

        direction_vote = self._direction_vote_from_expert_paths(expert_paths, anchor_prev_close, weight_map, np)
        vote_sign = float(np.sign(direction_vote))
        current_delta = float(target_first_close) - float(anchor_prev_close)
        momentum_sign = self._recent_momentum_sign(
            history_slice,
            FINAL_T1_DIRECTION_MOMENTUM_BARS,
            FINAL_T1_DIRECTION_MOMENTUM_MIN_MOVE,
        )
        if (
            abs(direction_vote) >= float(FINAL_T1_DIRECTION_VOTE_THRESHOLD)
            and vote_sign != 0.0
            and np.sign(current_delta) != vote_sign
            and abs(current_delta) <= float(FINAL_T1_DIRECTION_MAX_ABS_DELTA_TO_OVERRIDE)
            and momentum_sign == vote_sign
        ):
            override_abs = min(
                max(abs(current_delta) * 0.5, float(FINAL_T1_DIRECTION_MIN_OVERRIDE_MOVE)),
                float(FINAL_T1_DIRECTION_MAX_OVERRIDE_MOVE),
            )
            target_first_close = float(anchor_prev_close) + vote_sign * float(override_abs)

        if previous_next_close is not None:
            delta_from_prev = float(target_first_close) - float(previous_next_close)
            compressed = self._compress_abs_move(
                abs(delta_from_prev),
                temporal_cap,
                FINAL_T1_TEMPORAL_RECAP_EXCESS_SCALE,
                FINAL_T1_TEMPORAL_RECAP_HARD_MULT,
                FINAL_T1_TEMPORAL_RECAP_EXTREME_SCALE,
            )
            target_first_close = float(previous_next_close) + math.copysign(compressed, delta_from_prev)

        return self._shift_path_from_first_close(guarded, target_first_close, np)

    @staticmethod
    def _select_best_path_by_trend(historical_closes: Any, candidate_paths: Any, bars: int, threshold: float, np: Any) -> Any:
        def slope(close_seq: Any) -> float:
            if len(close_seq) < 2:
                return 0.0
            x_axis = np.arange(len(close_seq), dtype=np.float32)
            value, _ = np.polyfit(x_axis, close_seq.astype(np.float32), 1)
            return float(value / max(abs(close_seq[-1]), 1e-6))

        historical_slope = slope(historical_closes[-bars:])
        candidate_slopes = np.asarray([slope(path[:, 3]) for path in candidate_paths], dtype=np.float32)
        if abs(historical_slope) >= threshold:
            same_sign = np.sign(candidate_slopes) == np.sign(historical_slope)
            filtered_idx = np.where(same_sign)[0]
            if len(filtered_idx) > 0:
                candidate_paths = candidate_paths[filtered_idx]
                candidate_slopes = candidate_slopes[filtered_idx]
        return candidate_paths[int(np.argmin(np.abs(candidate_slopes - historical_slope)))]

    @staticmethod
    def _detect_regime_multiplier(history_slice: Any, np: Any) -> Tuple[str, float, float]:
        turbulence = float(history_slice["turbulence_60"].iloc[-1])
        atr_pct = float(history_slice["atr_14_pct"].iloc[-1])
        turb_q75 = float(history_slice["turbulence_60"].quantile(0.75))
        turb_q90 = float(history_slice["turbulence_60"].quantile(0.90))
        atr_q75 = float(history_slice["atr_14_pct"].quantile(0.75))
        atr_q90 = float(history_slice["atr_14_pct"].quantile(0.90))
        if turbulence >= turb_q90 and atr_pct >= atr_q90:
            return "CRISIS", 1.8, 1.0
        if turbulence >= turb_q75 or atr_pct >= atr_q75:
            return "ELEVATED", 1.3, 0.5
        return "NORMAL", 1.0, 0.0

    @staticmethod
    def _intraday_temperature(anchor_ts: Any, pd: Any) -> float:
        local_ts = pd.Timestamp(anchor_ts).tz_convert("America/New_York")
        hhmm = local_ts.hour * 100 + local_ts.minute
        if hhmm < 1015:
            return 1.25
        if hhmm < 1400:
            return 1.45
        return 1.60

    @staticmethod
    def _future_minutes(anchor_timestamp: Any, count: int, pd: Any) -> List[Any]:
        current = pd.Timestamp(anchor_timestamp)
        if current.tzinfo is None:
            current = current.tz_localize("UTC")
        return [current + pd.Timedelta(minutes=idx + 1) for idx in range(count)]

    @staticmethod
    def _regime_name(value: float) -> str:
        if value >= 1.0:
            return "CRISIS"
        if value >= 0.5:
            return "ELEVATED"
        return "NORMAL"

    @staticmethod
    def _regime_scale(value: float) -> float:
        if value >= 1.0:
            return 0.3
        if value >= 0.5:
            return 0.7
        return 1.0

    @staticmethod
    def _stance_from_action(action: float) -> str:
        if action > ACTION_NEUTRAL_BAND:
            return "LONG"
        if action < -ACTION_NEUTRAL_BAND:
            return "SHORT"
        return "NEUTRAL"

    @staticmethod
    def _deps() -> Tuple[Any, Any, Any, Any, Any]:
        try:
            import numpy as np
            import pandas as pd
            import torch
            import torch.nn as nn
            import torch.nn.functional as F
        except ImportError as exc:
            raise RuntimeError(
                "The one-minute technical model requires numpy, pandas, and torch. "
                "Install backend requirements or rebuild the Docker image."
            ) from exc
        return np, pd, torch, nn, F


def _alpaca_api_key() -> str | None:
    return settings.ALPACA_API_KEY or settings.APCA_API_KEY_ID


def _alpaca_secret_key() -> str | None:
    return settings.ALPACA_SECRET_KEY or settings.ALPACA_API_SECRET or settings.APCA_API_SECRET_KEY


def _additive_attention_class(torch: Any, nn: Any) -> Any:
    class AdditiveAttention(nn.Module):
        def __init__(self, hidden_size: int) -> None:
            super().__init__()
            self.query = nn.Linear(hidden_size, hidden_size)
            self.key = nn.Linear(hidden_size, hidden_size)
            self.energy = nn.Linear(hidden_size, 1, bias=False)

        def forward(self, query: Any, memory: Any) -> Tuple[Any, Any]:
            projected_query = self.query(query).unsqueeze(1)
            projected_memory = self.key(memory)
            scores = self.energy(torch.tanh(projected_query + projected_memory)).squeeze(-1)
            attn = torch.softmax(scores, dim=1)
            context = torch.bmm(attn.unsqueeze(1), memory).squeeze(1)
            return context, attn

    return AdditiveAttention


def _minute_seq2seq_class(torch: Any, nn: Any, F: Any) -> Any:
    AdditiveAttention = _additive_attention_class(torch, nn)

    class Seq2SeqAttnGRU(nn.Module):
        def __init__(self, input_dim: int, hidden_size: int, num_layers: int, dropout: float, horizon: int) -> None:
            super().__init__()
            self.horizon = horizon
            self.encoder = nn.GRU(
                input_size=input_dim,
                hidden_size=hidden_size,
                num_layers=num_layers,
                dropout=dropout if num_layers > 1 else 0.0,
                batch_first=True,
            )
            self.attention = AdditiveAttention(hidden_size)
            self.decoder = nn.GRUCell(4 + hidden_size, hidden_size)
            self.mu_head = nn.Linear(hidden_size * 2, 4)
            self.log_sigma_head = nn.Linear(hidden_size * 2, 4)

        def encode_sequence(self, x: Any) -> Tuple[Any, Any]:
            enc_out, enc_hidden = self.encoder(x)
            return enc_out, enc_hidden[-1]

        def encode_context(self, x: Any) -> Any:
            enc_out, enc_hidden = self.encode_sequence(x)
            pooled = enc_out.mean(dim=1)
            return F.normalize(torch.cat([pooled, enc_hidden], dim=-1), dim=-1)

        def decode_step(self, decoder_input: Any, decoder_hidden: Any, encoder_memory: Any) -> Tuple[Any, Any, Any]:
            context, _ = self.attention(decoder_hidden, encoder_memory)
            decoder_hidden = self.decoder(torch.cat([decoder_input, context], dim=-1), decoder_hidden)
            fused = torch.cat([decoder_hidden, context], dim=-1)
            mu = self.mu_head(fused)
            log_sigma = torch.clamp(self.log_sigma_head(fused), min=-5.0, max=3.0)
            return mu, log_sigma, decoder_hidden

    return Seq2SeqAttnGRU


def _minute_hybrid_model_class(torch: Any, nn: Any, F: Any) -> Any:
    AdditiveAttention = _additive_attention_class(torch, nn)

    class SinusoidalPositionalEncoding(nn.Module):
        def __init__(self, d_model: int, max_len: int = 512) -> None:
            super().__init__()
            position = torch.arange(max_len).unsqueeze(1)
            div_term = torch.exp(torch.arange(0, d_model, 2) * (-math.log(10000.0) / d_model))
            pe = torch.zeros(max_len, d_model)
            pe[:, 0::2] = torch.sin(position * div_term)
            pe[:, 1::2] = torch.cos(position * div_term)
            self.register_buffer("pe", pe.unsqueeze(0))

        def forward(self, x: Any) -> Any:
            return x + self.pe[:, : x.size(1)]

    class ITransformerEncoderLayer(nn.Module):
        def __init__(self, d_model: int, n_heads: int, dropout: float) -> None:
            super().__init__()
            self.attn = nn.MultiheadAttention(d_model, n_heads, dropout=dropout, batch_first=True)
            self.ffn = nn.Sequential(
                nn.Linear(d_model, d_model * 4),
                nn.GELU(),
                nn.Dropout(dropout),
                nn.Linear(d_model * 4, d_model),
            )
            self.norm_1 = nn.LayerNorm(d_model)
            self.norm_2 = nn.LayerNorm(d_model)
            self.dropout = nn.Dropout(dropout)

        def forward(self, x: Any) -> Any:
            attn_out, _ = self.attn(x, x, x, need_weights=False)
            x = self.norm_1(x + self.dropout(attn_out))
            return self.norm_2(x + self.dropout(self.ffn(x)))

    class ITransformerEncoder(nn.Module):
        def __init__(self, input_dim: int, lookback: int, d_model: int, n_heads: int, n_layers: int, dropout: float) -> None:
            super().__init__()
            self.token_projection = nn.Linear(lookback, d_model)
            self.positional = SinusoidalPositionalEncoding(d_model, max_len=input_dim + 8)
            self.layers = nn.ModuleList([ITransformerEncoderLayer(d_model, n_heads, dropout) for _ in range(n_layers)])
            self.norm = nn.LayerNorm(d_model)

        def forward(self, x: Any) -> Any:
            tokens = self.token_projection(x.transpose(1, 2))
            tokens = self.positional(tokens)
            for layer in self.layers:
                tokens = layer(tokens)
            return self.norm(tokens).flatten(start_dim=1)

    class HybridSeq2SeqForecaster(nn.Module):
        def __init__(
            self,
            input_dim: int,
            lookback: int,
            hidden_size: int,
            num_layers: int,
            dropout: float,
            horizon: int,
            d_model: int,
            n_heads: int,
            n_layers: int,
        ) -> None:
            super().__init__()
            self.horizon = horizon
            self.gru = nn.GRU(
                input_size=input_dim,
                hidden_size=hidden_size,
                num_layers=num_layers,
                dropout=dropout if num_layers > 1 else 0.0,
                batch_first=True,
            )
            self.itransformer = ITransformerEncoder(input_dim, lookback, d_model, n_heads, n_layers, dropout)
            self.fusion = nn.Sequential(
                nn.Linear((input_dim * d_model) + hidden_size, hidden_size),
                nn.GELU(),
                nn.LayerNorm(hidden_size),
            )
            self.attention = AdditiveAttention(hidden_size)
            self.decoder = nn.GRUCell(4 + hidden_size, hidden_size)
            self.mu_head = nn.Linear(hidden_size * 2, 4)
            self.log_sigma_head = nn.Linear(hidden_size * 2, 4)

        def encode_sequence(self, x: Any) -> Tuple[Any, Any]:
            gru_out, gru_hidden = self.gru(x)
            transformer_flat = self.itransformer(x)
            fused = self.fusion(torch.cat([transformer_flat, gru_hidden[-1]], dim=-1))
            return gru_out, fused

        def encode_context(self, x: Any) -> Any:
            gru_out, fused = self.encode_sequence(x)
            return F.normalize(torch.cat([gru_out.mean(dim=1), fused], dim=-1), dim=-1)

        def decode_step(self, decoder_input: Any, decoder_hidden: Any, encoder_memory: Any) -> Tuple[Any, Any, Any]:
            context, _ = self.attention(decoder_hidden, encoder_memory)
            decoder_hidden = self.decoder(torch.cat([decoder_input, context], dim=-1), decoder_hidden)
            fused = torch.cat([decoder_hidden, context], dim=-1)
            mu = self.mu_head(fused)
            log_sigma = torch.clamp(self.log_sigma_head(fused), min=-5.0, max=3.0)
            return mu, log_sigma, decoder_hidden

    return HybridSeq2SeqForecaster


def _actor_critic_class(torch: Any) -> Any:
    import torch.nn as nn

    class ActorCritic(nn.Module):
        def __init__(self, state_dim: int, hidden_dim: int = 256) -> None:
            super().__init__()
            self.shared = nn.Sequential(
                nn.Linear(state_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.Tanh(),
                nn.Linear(hidden_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.Tanh(),
            )
            self.actor_mean = nn.Linear(hidden_dim, 1)
            self.actor_log_std = nn.Parameter(torch.zeros(1))
            self.critic = nn.Linear(hidden_dim, 1)

        def forward(self, x: Any) -> Tuple[Any, Any, Any]:
            shared = self.shared(x)
            mean = torch.tanh(self.actor_mean(shared))
            std = torch.exp(self.actor_log_std).expand_as(mean)
            value = self.critic(shared)
            return mean, std, value

    return ActorCritic
