from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx

from app.config import settings
from app.schemas.technical import TechnicalCandle


MODEL_REVISION = "recurrent_decoder_price_path_v2"
CORE_FEATURE_COLUMNS = [
    "rOpen",
    "rHigh",
    "rLow",
    "rClose",
    "logVolChange",
    "logTradeCountChange",
    "vwapDelta",
    "rangeFrac",
    "orderFlowProxy",
    "tickPressure",
]
REGIME_FEATURE_COLUMNS = [
    "atr_14",
    "atr_14_pct",
    "returns",
    "turbulence_60",
    "regime_indicator",
]
MARKET_STATE_COLUMNS = [
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


@dataclass
class ExpertBundle:
    name: str
    version: str
    lookback: int
    feature_mode: str
    model: Any
    scaler: Dict[str, Any]
    feature_columns: List[str]
    inference_config: Dict[str, Any]
    retrieval_artifact: Optional[Dict[str, Any]]
    rag_config: Dict[str, Any]


@dataclass
class TechnicalModelResult:
    history: List[TechnicalCandle]
    forecast: List[TechnicalCandle]
    latest_price: float
    model_version: str
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


class TechnicalArtifactStore:
    def __init__(self, artifact_dir: str | None = None) -> None:
        self.artifact_dir = Path(artifact_dir or settings.TECHNICAL_ARTIFACT_DIR)
        self._local_fallback_dir = (
            Path(__file__).resolve().parents[4] / "Technical_Model" / "final_1d_artifacts"
        )

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
            raise FileNotFoundError(f"Technical model manifest is missing: {manifest_path}")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    def status(self) -> Dict[str, Any]:
        root = self.root
        manifest_exists = self.manifest_path().exists()
        expected_files = [
            root / "manifest.json",
            root / "ensemble" / "weights.json",
            root / "rl" / "policy.pt",
            root / "rl" / "state_schema.json",
        ]
        for expert in ("v8_5", "v9_2", "v9_5"):
            expected_files.extend(
                [
                    root / "models" / expert / "model.pt",
                    root / "models" / expert / "scaler.npz",
                    root / "models" / expert / "feature_manifest.json",
                    root / "models" / expert / "inference_config.json",
                ]
            )
        missing = [str(path) for path in expected_files if not path.exists()]
        manifest: Dict[str, Any] = {}
        if manifest_exists:
            try:
                manifest = self.load_manifest()
            except Exception:
                manifest = {}
        runtime = manifest.get("runtime", {})
        return {
            "artifact_dir": str(self.artifact_dir),
            "resolved_artifact_dir": str(root),
            "artifact_dir_exists": root.exists(),
            "manifest_exists": manifest_exists,
            "missing_files": missing,
            "using_real_model_artifacts": root.exists() and manifest_exists and not missing,
            "model_symbol": runtime.get("symbol"),
            "timeframe": runtime.get("timeframe"),
            "horizon": runtime.get("horizon"),
            "created_at_utc": runtime.get("created_at_utc"),
            "require_model_artifact": settings.TECHNICAL_REQUIRE_MODEL_ARTIFACT,
            "require_alpaca_live_data": settings.TECHNICAL_REQUIRE_ALPACA_LIVE_DATA,
            "alpaca_credentials_configured": bool(settings.ALPACA_API_KEY and settings.ALPACA_SECRET_KEY),
            "ready_for_live_inference": (
                root.exists()
                and manifest_exists
                and not missing
                and (
                    not settings.TECHNICAL_REQUIRE_ALPACA_LIVE_DATA
                    or bool(settings.ALPACA_API_KEY and settings.ALPACA_SECRET_KEY)
                )
            ),
        }


class TechnicalModelRuntime:
    def __init__(self, artifact_store: TechnicalArtifactStore | None = None) -> None:
        self.artifact_store = artifact_store or TechnicalArtifactStore()
        self._bundles: Dict[str, ExpertBundle] | None = None
        self._policy: Any | None = None
        self._policy_state_dim: int | None = None

    async def predict(self, ticker: str, history_bars: int, forecast_bars: int) -> TechnicalModelResult:
        np, pd, torch, nn, F = self._deps()
        manifest = self.artifact_store.load_manifest()
        runtime = manifest.get("runtime", {})
        horizon = int(runtime.get("horizon", 7))
        forecast_count = max(1, min(int(forecast_bars), horizon))
        required_input_bars = self._required_input_bars(manifest)

        raw_bars, data_source = await self._fetch_daily_bars(ticker, required_input_bars)
        if len(raw_bars) < required_input_bars:
            raise ValueError(
                f"Not enough live daily bars available for {ticker}; "
                f"need {required_input_bars}, received {len(raw_bars)}"
            )

        feature_frame = self._build_feature_frame(raw_bars, pd, np)
        bundles = self._load_bundles()
        expected_experts = list(self._load_weights().keys())
        weights = self._normalize_weights(self._load_weights(), expected_experts)

        expert_paths: Dict[str, Any] = {}
        expert_versions: Dict[str, str] = {}
        expert_regimes: Dict[str, float] = {}
        anchor_prev_close = float(feature_frame["close"].iloc[-1])
        anchor_timestamp = feature_frame["timestamp"].iloc[-1]

        for expert_name in expected_experts:
            bundle = bundles[expert_name]
            model_input = self._build_latest_input(feature_frame, bundle, pd, np)
            path = self._generate_path(bundle, model_input, np, torch)
            expert_paths[expert_name] = path
            expert_versions[expert_name] = bundle.version
            if "regime_indicator" in model_input["context"].columns:
                expert_regimes[expert_name] = float(model_input["context"]["regime_indicator"].iloc[-1])

        aggregate_path = np.zeros_like(next(iter(expert_paths.values())), dtype=np.float32)
        aggregate_regime = 0.0
        for expert_name, path in expert_paths.items():
            weight = float(weights.get(expert_name, 0.0))
            aggregate_path += weight * path
            aggregate_regime += weight * float(expert_regimes.get(expert_name, 0.0))
        aggregate_path = self._enforce_candle_validity(aggregate_path, np)

        policy = self._run_policy(aggregate_path, feature_frame, aggregate_regime, np, torch)
        timestamps = self._future_business_days(anchor_timestamp, forecast_count)
        forecast = [
            TechnicalCandle(
                timestamp=timestamps[idx],
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
        history = raw_bars[-history_count:]
        root = self.artifact_store.root
        return TechnicalModelResult(
            history=history,
            forecast=forecast,
            latest_price=anchor_prev_close,
            model_version="final_1d",
            source_model="final_1d_ensemble_rl",
            artifact_version=str(runtime.get("created_at_utc") or "unknown"),
            artifact_path=str(root),
            generated_at=datetime.now(timezone.utc),
            ensemble_weights=weights,
            expert_versions=expert_versions,
            policy=policy,
            regime=self._regime_name(aggregate_regime),
            data_source=data_source,
            inference_input_bars=len(raw_bars),
            required_input_bars=required_input_bars,
        )

    async def _fetch_daily_bars(self, ticker: str, required_bars: int) -> Tuple[List[TechnicalCandle], str]:
        end = datetime.now(timezone.utc)
        calendar_days = max(365, math.ceil(required_bars * 8 / 5) + 90)
        start = end - timedelta(days=calendar_days)

        if settings.ALPACA_API_KEY and settings.ALPACA_SECRET_KEY:
            try:
                bars = await self._fetch_daily_bars_alpaca(ticker, start, end, required_bars)
                if bars:
                    return bars[-required_bars:], "alpaca-1d-live"
            except Exception as exc:
                if settings.TECHNICAL_REQUIRE_ALPACA_LIVE_DATA:
                    raise ValueError(f"Alpaca live daily-bar fetch failed for {ticker}: {exc}") from exc

        if settings.TECHNICAL_REQUIRE_ALPACA_LIVE_DATA:
            raise ValueError(
                "Alpaca API credentials are required for live technical inference. "
                "Set ALPACA_API_KEY and ALPACA_SECRET_KEY."
            )

        bars, data_source = await self._fetch_daily_bars_yahoo(ticker, required_bars)
        return bars[-required_bars:], data_source

    async def _fetch_daily_bars_alpaca(
        self,
        ticker: str,
        start: datetime,
        end: datetime,
        required_bars: int,
    ) -> List[TechnicalCandle]:
        url = f"{settings.ALPACA_DATA_URL.rstrip('/')}/v2/stocks/{ticker}/bars"
        params = {
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "adjustment": "raw",
            "feed": settings.ALPACA_STOCK_FEED,
            "sort": "asc",
            "limit": min(max(required_bars + 250, required_bars), 10000),
        }
        headers = {
            "APCA-API-KEY-ID": settings.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": settings.ALPACA_SECRET_KEY,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        return [
            TechnicalCandle(
                timestamp=datetime.fromisoformat(bar["t"].replace("Z", "+00:00")),
                open=float(bar["o"]),
                high=float(bar["h"]),
                low=float(bar["l"]),
                close=float(bar["c"]),
                volume=int(bar.get("v", 0)),
            )
            for bar in payload.get("bars", [])
        ]

    async def _fetch_daily_bars_yahoo(self, ticker: str, required_bars: int) -> Tuple[List[TechnicalCandle], str]:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {
            "interval": "1d",
            "range": "5y" if required_bars <= 1200 else "10y",
            "includePrePost": "false",
            "events": "div%2Csplit",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

        result = (payload.get("chart", {}).get("result") or [{}])[0]
        timestamps = result.get("timestamp") or []
        quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
        bars: List[TechnicalCandle] = []
        for idx, timestamp in enumerate(timestamps):
            open_price = self._get_index_value(quotes.get("open"), idx)
            high_price = self._get_index_value(quotes.get("high"), idx)
            low_price = self._get_index_value(quotes.get("low"), idx)
            close_price = self._get_index_value(quotes.get("close"), idx)
            volume = self._get_index_value(quotes.get("volume"), idx, default=0)
            if None in (open_price, high_price, low_price, close_price):
                continue
            bars.append(
                TechnicalCandle(
                    timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                    open=float(open_price),
                    high=float(high_price),
                    low=float(low_price),
                    close=float(close_price),
                    volume=int(volume or 0),
                )
            )
        if not bars:
            raise ValueError(f"No daily-bar data available for {ticker}")
        return bars, "yahoo-1d-fallback"

    def _required_input_bars(self, manifest: Dict[str, Any]) -> int:
        model_lookbacks = [
            int(model.get("lookback", 0))
            for model in manifest.get("forecast_models", {}).values()
        ]
        max_model_lookback = max(model_lookbacks or [128])
        indicator_warmup = max(int(settings.TECHNICAL_INFERENCE_WARMUP_BARS), 60)
        return max_model_lookback + indicator_warmup

    def _build_feature_frame(self, bars: List[TechnicalCandle], pd: Any, np: Any) -> Any:
        frame = pd.DataFrame(
            [
                {
                    "timestamp": candle.timestamp,
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
                for candle in bars
            ]
        ).sort_values("timestamp").reset_index(drop=True)

        frame["prev_close"] = frame["close"].shift(1).fillna(frame["open"])
        safe_prev = frame["prev_close"].replace(0, np.nan).ffill().bfill()
        frame["rOpen"] = np.log(frame["open"] / safe_prev)
        frame["rHigh"] = np.log(frame["high"] / safe_prev)
        frame["rLow"] = np.log(frame["low"] / safe_prev)
        frame["rClose"] = np.log(frame["close"] / safe_prev)
        frame["logVolChange"] = np.log1p(frame["volume"]).diff().replace([np.inf, -np.inf], np.nan).fillna(0.0)
        frame["logTradeCountChange"] = 0.0
        vwap_proxy = (frame["high"] + frame["low"] + frame["close"]) / 3.0
        frame["vwapDelta"] = np.log(vwap_proxy / frame["close"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
        frame["rangeFrac"] = ((frame["high"] - frame["low"]) / safe_prev).replace([np.inf, -np.inf], np.nan)
        price_range = (frame["high"] - frame["low"]).replace(0, np.nan)
        frame["orderFlowProxy"] = ((frame["close"] - frame["open"]) / price_range).replace([np.inf, -np.inf], np.nan)
        frame["tickPressure"] = (np.sign(frame["rClose"]) * frame["orderFlowProxy"].abs()).replace([np.inf, -np.inf], np.nan)
        frame["returns"] = frame["close"].pct_change().replace([np.inf, -np.inf], np.nan).fillna(0.0)

        self._add_technical_features(frame, pd, np)
        frame["row_imputed"] = frame[CORE_FEATURE_COLUMNS + REGIME_FEATURE_COLUMNS + MARKET_STATE_COLUMNS].isna().any(axis=1).astype(float)
        frame = frame.replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0)
        return frame

    def _add_technical_features(self, frame: Any, pd: Any, np: Any) -> None:
        close = frame["close"]
        high = frame["high"]
        low = frame["low"]
        volume = frame["volume"].replace(0, np.nan)

        frame["sma_5"] = close.rolling(5, min_periods=1).mean()
        frame["sma_10"] = close.rolling(10, min_periods=1).mean()
        frame["sma_20"] = close.rolling(20, min_periods=1).mean()
        frame["sma_50"] = close.rolling(50, min_periods=1).mean()
        frame["ema_12"] = close.ewm(span=12, adjust=False).mean()
        frame["ema_26"] = close.ewm(span=26, adjust=False).mean()
        frame["macd_line"] = frame["ema_12"] - frame["ema_26"]
        frame["macd_signal"] = frame["macd_line"].ewm(span=9, adjust=False).mean()
        frame["macd_histogram"] = frame["macd_line"] - frame["macd_signal"]
        frame["macd_momentum"] = frame["macd_histogram"].diff().fillna(0.0)

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
        loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
        rs = gain / loss.replace(0, np.nan)
        frame["rsi_14"] = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0) / 100.0
        frame["rsi_14_slope"] = frame["rsi_14"].diff().fillna(0.0)

        lowest_low = low.rolling(14, min_periods=1).min()
        highest_high = high.rolling(14, min_periods=1).max()
        frame["stoch_k"] = ((close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)).fillna(0.5)
        frame["stoch_d"] = frame["stoch_k"].rolling(3, min_periods=1).mean()
        rolling_std = close.rolling(20, min_periods=1).std().fillna(0.0)
        frame["bb_upper"] = frame["sma_20"] + 2.0 * rolling_std
        frame["bb_lower"] = frame["sma_20"] - 2.0 * rolling_std
        frame["bb_width"] = ((frame["bb_upper"] - frame["bb_lower"]) / close.replace(0, np.nan)).fillna(0.0)
        frame["bb_position"] = ((close - frame["bb_lower"]) / (frame["bb_upper"] - frame["bb_lower"]).replace(0, np.nan)).fillna(0.5)

        true_range = pd.concat(
            [
                (high - low).abs(),
                (high - frame["prev_close"]).abs(),
                (low - frame["prev_close"]).abs(),
            ],
            axis=1,
        ).max(axis=1)
        frame["atr_14"] = true_range.rolling(14, min_periods=1).mean()
        frame["atr_14_pct"] = (frame["atr_14"] / close.replace(0, np.nan)).fillna(0.0)
        direction = np.sign(close.diff().fillna(0.0))
        frame["obv"] = (direction * frame["volume"].fillna(0)).cumsum()
        frame["obv_slope"] = frame["obv"].diff(5).fillna(0.0) / volume.rolling(20, min_periods=1).mean().fillna(1.0)
        frame["vwap_20"] = (
            ((high + low + close) / 3.0 * frame["volume"]).rolling(20, min_periods=1).sum()
            / frame["volume"].rolling(20, min_periods=1).sum().replace(0, np.nan)
        ).fillna(close)
        frame["vwap_20_dev"] = ((close - frame["vwap_20"]) / close.replace(0, np.nan)).fillna(0.0)
        frame["price_momentum_5"] = close.pct_change(5).fillna(0.0)
        frame["price_momentum_10"] = close.pct_change(10).fillna(0.0)
        frame["price_momentum_20"] = close.pct_change(20).fillna(0.0)
        frame["body_size"] = (close - frame["open"]).abs()
        frame["body_pct"] = (frame["body_size"] / close.replace(0, np.nan)).fillna(0.0)
        frame["upper_shadow"] = (high - pd.concat([frame["open"], close], axis=1).max(axis=1)).clip(lower=0)
        frame["lower_shadow"] = (pd.concat([frame["open"], close], axis=1).min(axis=1) - low).clip(lower=0)
        frame["direction"] = direction.fillna(0.0)
        frame["relative_volume"] = (frame["volume"] / frame["volume"].rolling(20, min_periods=1).mean().replace(0, np.nan)).fillna(1.0)

        turbulence = frame["returns"].rolling(60, min_periods=2).std().fillna(0.0)
        frame["turbulence_60"] = turbulence
        atr_q75 = frame["atr_14_pct"].rolling(390, min_periods=20).quantile(0.75).fillna(frame["atr_14_pct"].expanding().quantile(0.75))
        turb_q75 = frame["turbulence_60"].rolling(390, min_periods=20).quantile(0.75).fillna(frame["turbulence_60"].expanding().quantile(0.75))
        frame["regime_indicator"] = ((frame["atr_14_pct"] >= atr_q75).astype(float) * 0.5) + (
            (frame["turbulence_60"] >= turb_q75).astype(float) * 0.5
        )

    def _load_bundles(self) -> Dict[str, ExpertBundle]:
        if self._bundles is not None:
            return self._bundles

        np, _, torch, nn, F = self._deps()
        root = self.artifact_store.root
        manifest = self.artifact_store.load_manifest()
        bundles: Dict[str, ExpertBundle] = {}

        for expert_name, artifact in manifest.get("forecast_models", {}).items():
            expert_dir = root / "models" / expert_name
            model_path = expert_dir / "model.pt"
            scaler_path = expert_dir / "scaler.npz"
            feature_manifest_path = expert_dir / "feature_manifest.json"
            inference_config_path = expert_dir / "inference_config.json"
            for path in [model_path, scaler_path, feature_manifest_path, inference_config_path]:
                if not path.exists():
                    raise FileNotFoundError(f"Missing technical model artifact: {path}")

            checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)
            model = self._build_model_from_checkpoint(checkpoint, torch, nn, F).eval()
            scaler_npz = np.load(scaler_path)
            retrieval_artifact = None
            rag_path = expert_dir / "rag_database.npz"
            rag_config_path = expert_dir / "rag_config.json"
            rag_config = {"k_retrieve": 5, "blend_weight": 0.25}
            if rag_path.exists():
                rag_npz = np.load(rag_path)
                retrieval_artifact = {
                    "embeddings": rag_npz["embeddings"].astype(np.float32),
                    "future_returns": rag_npz["future_returns"].astype(np.float32),
                }
            if rag_config_path.exists():
                rag_config = json.loads(rag_config_path.read_text(encoding="utf-8"))
            feature_manifest = json.loads(feature_manifest_path.read_text(encoding="utf-8"))
            inference_config = json.loads(inference_config_path.read_text(encoding="utf-8"))

            bundles[expert_name] = ExpertBundle(
                name=expert_name,
                version=str(artifact.get("version", expert_name)),
                lookback=int(artifact.get("lookback", inference_config.get("lookback", 128))),
                feature_mode=str(artifact.get("feature_mode", "core")),
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
        if checkpoint.get("model_revision") != MODEL_REVISION:
            raise RuntimeError(
                f"Technical model revision {checkpoint.get('model_revision')!r} is incompatible with {MODEL_REVISION!r}"
            )
        spec = checkpoint["spec"]
        if spec["architecture"] not in {"gru", "gru_rag"}:
            raise ValueError(f"Unsupported technical architecture: {spec['architecture']}")
        model = _seq2seq_model_class(torch, nn, F)(
            int(checkpoint["input_dim"]),
            int(checkpoint["training_defaults"]["hidden_size"]),
            int(checkpoint["training_defaults"]["num_layers"]),
            float(checkpoint["training_defaults"]["dropout"]),
            int(self.artifact_store.load_manifest().get("runtime", {}).get("horizon", 7)),
        )
        model.load_state_dict(checkpoint["state_dict"])
        return model

    def _build_latest_input(self, feature_frame: Any, bundle: ExpertBundle, pd: Any, np: Any) -> Dict[str, Any]:
        if len(feature_frame) < bundle.lookback:
            raise RuntimeError(f"Not enough rows to build latest input for {bundle.name}")
        context = feature_frame.iloc[len(feature_frame) - bundle.lookback : len(feature_frame)].copy()
        feature_block = context.loc[:, bundle.feature_columns].to_numpy(dtype=np.float32)
        impute_frac = float(context["row_imputed"].mean())
        feature_block = np.concatenate(
            [feature_block, np.full((bundle.lookback, 1), impute_frac, dtype=np.float32)],
            axis=1,
        )
        scaled = ((feature_block[None, ...] - bundle.scaler["mean"]) / bundle.scaler["std"]).astype(np.float32)[0]
        return {
            "scaled_input": scaled,
            "anchor_prev_close": float(context["close"].iloc[-1]),
            "context": context,
            "target_scale": self._estimate_target_scale(context, np),
        }

    def _generate_path(self, bundle: ExpertBundle, model_input: Dict[str, Any], np: Any, torch: Any) -> Any:
        x_tensor = torch.from_numpy(model_input["scaled_input"][None, ...]).float()
        with torch.inference_mode():
            mu, _log_sigma = bundle.model(x_tensor, y=None, teacher_forcing_ratio=0.0)
        mean_returns = (mu.squeeze(0).detach().cpu().numpy().astype(np.float32) * float(model_input["target_scale"])).astype(np.float32)
        if bundle.retrieval_artifact is not None and float(bundle.rag_config.get("blend_weight", 0.0)) > 0.0:
            retrieved = self._retrieve_future_returns(bundle, model_input["scaled_input"], np, torch)
            if retrieved is not None:
                blend_weight = float(bundle.rag_config.get("blend_weight", 0.25))
                mean_returns = ((1.0 - blend_weight) * mean_returns + blend_weight * retrieved).astype(np.float32)
        return self._returns_to_prices(float(model_input["anchor_prev_close"]), mean_returns, np)

    def _retrieve_future_returns(self, bundle: ExpertBundle, x_scaled_single: Any, np: Any, torch: Any) -> Any | None:
        artifact = bundle.retrieval_artifact
        if artifact is None or len(artifact["embeddings"]) == 0:
            return None
        with torch.inference_mode():
            query = torch.from_numpy(x_scaled_single[None, ...]).float()
            query_embedding = bundle.model.encode_context(query).detach().cpu().numpy()[0].astype(np.float32)
        query_embedding /= np.linalg.norm(query_embedding).clip(min=1e-8)
        similarities = artifact["embeddings"] @ query_embedding
        k_retrieve = int(bundle.rag_config.get("k_retrieve", 5))
        top_idx = np.argsort(similarities)[-k_retrieve:][::-1]
        top_scores = similarities[top_idx]
        top_weights = np.exp(top_scores - top_scores.max())
        top_weights /= top_weights.sum().clip(min=1e-8)
        return np.tensordot(top_weights, artifact["future_returns"][top_idx], axes=(0, 0)).astype(np.float32)

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
        market_state = latest_market.loc[MARKET_STATE_COLUMNS].to_numpy(dtype=np.float32)
        policy_state = np.concatenate(
            [
                aggregate_path.reshape(-1).astype(np.float32),
                market_state,
                np.asarray(PORTFOLIO_STATE, dtype=np.float32),
                np.asarray([aggregate_regime], dtype=np.float32),
            ]
        ).astype(np.float32)
        if self._policy_state_dim and policy_state.shape[0] != self._policy_state_dim:
            raise ValueError(f"Technical policy state dimension mismatch: expected {self._policy_state_dim}, got {policy_state.shape[0]}")
        with torch.inference_mode():
            mean_action, action_std, value_estimate = self._policy(torch.from_numpy(policy_state).float().unsqueeze(0))
        raw_action = float(mean_action.item())
        policy_std = float(action_std.item())
        regime_scale = self._regime_scale(aggregate_regime)
        adjusted_action = raw_action * regime_scale
        return {
            "raw_action": raw_action,
            "policy_std": policy_std,
            "confidence_score": float(1.0 / (1.0 + policy_std)),
            "critic_value_estimate": float(value_estimate.item()),
            "regime_scale": regime_scale,
            "recommended_position_pct": adjusted_action,
            "stance": self._stance_from_action(adjusted_action),
        }

    def _load_weights(self) -> Dict[str, float]:
        path = self.artifact_store.root / "ensemble" / "weights.json"
        if not path.exists():
            raise FileNotFoundError(f"Technical ensemble weights are missing: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): float(value) for key, value in payload.items()}

    @staticmethod
    def _normalize_weights(weights: Dict[str, float], experts: Sequence[str]) -> Dict[str, float]:
        filtered = {expert: max(0.0, float(weights.get(expert, 0.0))) for expert in experts}
        total = sum(filtered.values())
        if total <= 0:
            uniform = 1.0 / max(len(experts), 1)
            return {expert: uniform for expert in experts}
        return {expert: value / total for expert, value in filtered.items()}

    @staticmethod
    def _estimate_target_scale(context: Any, np: Any) -> float:
        candidates = []
        if "atr_14_pct" in context.columns:
            candidates.append(float(context["atr_14_pct"].replace([np.inf, -np.inf], np.nan).ffill().iloc[-1]))
        if "rClose" in context.columns:
            candidates.append(float(context["rClose"].tail(20).std()) * 2.0)
        finite = [value for value in candidates if np.isfinite(value) and value > 0.0]
        if not finite:
            return float(settings.TECHNICAL_TARGET_SCALE_FLOOR)
        return float(np.clip(max(finite), settings.TECHNICAL_TARGET_SCALE_FLOOR, settings.TECHNICAL_TARGET_SCALE_CEILING))

    @staticmethod
    def _returns_to_prices(anchor_prev_close: float, return_seq: Any, np: Any) -> Any:
        prices = np.zeros_like(return_seq, dtype=np.float32)
        prev_close = float(anchor_prev_close)
        for step in range(return_seq.shape[0]):
            prices[step] = np.exp(return_seq[step]) * prev_close
            prev_close = float(prices[step, 3])
        return TechnicalModelRuntime._enforce_candle_validity(prices, np)

    @staticmethod
    def _enforce_candle_validity(path: Any, np: Any) -> Any:
        repaired = np.asarray(path, dtype=np.float32).copy()
        repaired[:, 1] = np.maximum(repaired[:, 1], np.maximum(repaired[:, 0], repaired[:, 3]))
        repaired[:, 2] = np.minimum(repaired[:, 2], np.minimum(repaired[:, 0], repaired[:, 3]))
        repaired = np.maximum(repaired, 0.01)
        return repaired

    @staticmethod
    def _future_business_days(anchor_timestamp: Any, count: int) -> List[datetime]:
        if hasattr(anchor_timestamp, "to_pydatetime"):
            current = anchor_timestamp.to_pydatetime()
        else:
            current = anchor_timestamp
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        days: List[datetime] = []
        next_day = current + timedelta(days=1)
        while len(days) < count:
            if next_day.weekday() < 5:
                days.append(datetime.combine(next_day.date(), time(21, 0), tzinfo=timezone.utc))
            next_day += timedelta(days=1)
        return days

    @staticmethod
    def _get_index_value(values: list | None, index: int, default: float | None = None):
        if values is None or index >= len(values):
            return default
        value = values[index]
        return default if value is None else value

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
                "The real technical model requires numpy, pandas, and torch. "
                "Install backend requirements or rebuild the Docker image."
            ) from exc
        return np, pd, torch, nn, F


def _seq2seq_model_class(torch: Any, nn: Any, F: Any) -> Any:
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

    class Seq2SeqAttnGRU(nn.Module):
        def __init__(self, input_dim: int, hidden_size: int, num_layers: int, dropout: float, horizon: int) -> None:
            super().__init__()
            self.horizon = horizon
            self.hidden_size = hidden_size
            self.encoder = nn.GRU(
                input_size=input_dim,
                hidden_size=hidden_size,
                num_layers=num_layers,
                dropout=dropout if num_layers > 1 else 0.0,
                batch_first=True,
            )
            self.attention = AdditiveAttention(hidden_size)
            self.context_head = nn.Sequential(
                nn.Linear(hidden_size * 3, hidden_size),
                nn.GELU(),
                nn.LayerNorm(hidden_size),
                nn.Dropout(dropout),
            )
            self.step_embedding = nn.Embedding(horizon, hidden_size)
            self.decoder_cell = nn.GRUCell(hidden_size + 4, hidden_size)
            self.decoder_norm = nn.LayerNorm(hidden_size)
            self.mu_step_head = nn.Linear(hidden_size * 2, 4)
            self.log_sigma_step_head = nn.Linear(hidden_size * 2, 4)

        def encode_sequence(self, x: Any) -> Tuple[Any, Any]:
            enc_out, enc_hidden = self.encoder(x)
            return enc_out, enc_hidden[-1]

        def encode_context(self, x: Any) -> Any:
            enc_out, enc_hidden = self.encode_sequence(x)
            pooled = enc_out.mean(dim=1)
            return F.normalize(torch.cat([pooled, enc_hidden], dim=-1), dim=-1)

        def _teacher_mix(self, predicted: Any, actual: Optional[Any], ratio: float) -> Any:
            if actual is None or ratio <= 0.0 or not self.training:
                return predicted.detach()
            if ratio >= 1.0:
                return actual.detach()
            mask = (torch.rand(predicted.size(0), 1, device=predicted.device) < float(ratio)).to(predicted.dtype)
            return (mask * actual + (1.0 - mask) * predicted).detach()

        def forward(self, x: Any, y: Optional[Any] = None, teacher_forcing_ratio: float = 0.0) -> Tuple[Any, Any]:
            encoder_memory, encoder_hidden = self.encode_sequence(x)
            context, _ = self.attention(encoder_hidden, encoder_memory)
            pooled = encoder_memory.mean(dim=1)
            decoder_state = self.context_head(torch.cat([encoder_hidden, context, pooled], dim=-1))
            prev_return = torch.zeros(x.size(0), 4, device=x.device, dtype=x.dtype)
            mu_steps: List[Any] = []
            log_sigma_steps: List[Any] = []

            for step in range(self.horizon):
                step_ids = torch.full((x.size(0),), step, device=x.device, dtype=torch.long)
                decoder_input = torch.cat([prev_return, self.step_embedding(step_ids)], dim=-1)
                decoder_state = self.decoder_norm(self.decoder_cell(decoder_input, decoder_state))
                step_features = torch.cat([decoder_state, context], dim=-1)
                mu_step = self.mu_step_head(step_features)
                log_sigma_step = torch.clamp(self.log_sigma_step_head(step_features), min=-5.0, max=3.0)
                mu_steps.append(mu_step)
                log_sigma_steps.append(log_sigma_step)
                if step + 1 < self.horizon:
                    teacher_value = y[:, step, :] if y is not None else None
                    prev_return = self._teacher_mix(mu_step, teacher_value, teacher_forcing_ratio)

            return torch.stack(mu_steps, dim=1), torch.stack(log_sigma_steps, dim=1)

    return Seq2SeqAttnGRU


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
