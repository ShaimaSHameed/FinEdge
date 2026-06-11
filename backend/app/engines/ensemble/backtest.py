from __future__ import annotations

import csv
import math
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from app.schemas.ensemble import (
    EnsembleBacktestMetrics,
    EnsembleBacktestRequest,
    EnsembleBacktestResponse,
    EnsembleDecision,
    EnsembleEquityPoint,
    EnsembleModelSignal,
    EnsembleTrade,
    TradeAction,
)


SENTIMENT_TEXT_ROW = re.compile(
    r"^\s*(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<signal>[+-]?\d+(?:\.\d+)?)\s+"
    r"(?P<target>[+-]?\d+(?:\.\d+)?)\s+"
    r"(?P<actual>[+-]?\d+(?:\.\d+)?)\u2192(?P<new>[+-]?\d+(?:\.\d+)?)\s+"
    r"(?P<action>BUY|SELL|HOLD)\b"
)


@dataclass(frozen=True)
class PricePoint:
    date: date
    close: float


@dataclass(frozen=True)
class SignalRow:
    date: date
    ticker: str
    model: str
    raw_signal: str
    normalized_score: float
    confidence: float
    signal_label: str | None
    source: str


class EnsembleBacktestEngine:
    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parents[4]
        self.use_env_artifacts = repo_root is None

    async def backtest(self, request: EnsembleBacktestRequest) -> EnsembleBacktestResponse:
        ticker = request.ticker.upper().strip()
        warnings: list[str] = []
        signals = self.load_model_signals(ticker, request, warnings)

        if not signals:
            raise ValueError(
                f"No historical model signals are available for {ticker}. "
                "Add sentimental, fundamental, or technical backtest artifacts first."
            )

        signal_start = min(row.date for row in signals)
        signal_end = max(row.date for row in signals)
        start = request.start_date or signal_start
        end = request.end_date or signal_end
        signals = [row for row in signals if start <= row.date <= end]
        if not signals:
            raise ValueError(f"No model signals for {ticker} fall within {start} to {end}.")

        prices = await self.fetch_price_history(ticker, start, end)
        if not prices:
            raise ValueError(f"No historical daily prices are available for {ticker} between {start} and {end}.")

        if request.allow_technical_proxy and not any(row.model == "technical" for row in signals):
            decision_dates = sorted({row.date for row in signals if row.model != "technical"})
            proxy = self.build_technical_proxy_signals(ticker, prices, decision_dates)
            if proxy:
                signals.extend(proxy)
                warnings.append(
                    "No technical backtest signal artifact was found; used a deterministic price-momentum "
                    "technical proxy for historical alignment."
                )

        decisions = self.aggregate_decisions(signals, prices, request)
        if not decisions:
            raise ValueError(
                f"Model signals for {ticker} did not align with available daily prices. "
                "Check artifact dates and ticker coverage."
            )

        equity_curve, trades = self.simulate_portfolio(decisions, prices, request)
        if not equity_curve:
            raise ValueError("Backtest produced no equity curve points.")

        metrics = self.build_metrics(
            equity_curve=equity_curve,
            trades=trades,
            decisions=decisions,
            signals=signals,
            initial_capital=request.initial_capital,
        )
        output_signals = [
            EnsembleModelSignal(
                date=row.date,
                ticker=row.ticker,
                model=row.model,  # type: ignore[arg-type]
                raw_signal=row.raw_signal,
                normalized_score=round(row.normalized_score, 6),
                confidence=round(row.confidence, 6),
                signal_label=row.signal_label,
                source=row.source,
            )
            for row in sorted(signals, key=lambda item: (item.date, item.model))
        ]

        return EnsembleBacktestResponse(
            ticker=ticker,
            market=request.market,
            start_date=equity_curve[0].date,
            end_date=equity_curve[-1].date,
            metrics=metrics,
            decisions=decisions,
            trades=trades,
            equity_curve=equity_curve,
            model_signals=output_signals,
            source_files=sorted({row.source for row in signals}),
            warnings=warnings,
            generated_at=datetime.now(timezone.utc),
        )

    def health(self) -> dict[str, Any]:
        sentimental_sources = self._sentimental_sources("GOOGL")
        fundamental_sources = self._fundamental_candidates()
        technical_sources = self._technical_sources()
        return {
            "status": "healthy" if sentimental_sources or fundamental_sources or technical_sources else "degraded",
            "service": "ensemble",
            "available_sources": {
                "sentimental": [str(path) for path in sentimental_sources],
                "fundamental": [str(path) for path in fundamental_sources],
                "technical": [str(path) for path in technical_sources],
            },
            "supports_technical_proxy": True,
        }

    def load_model_signals(
        self,
        ticker: str,
        request: EnsembleBacktestRequest,
        warnings: list[str],
    ) -> list[SignalRow]:
        signals: list[SignalRow] = []
        signals.extend(self.load_sentimental_signals(ticker, request.sentiment_max_exposure, warnings))
        signals.extend(self.load_fundamental_signals(ticker, warnings))
        signals.extend(self.load_technical_signals(ticker, warnings))
        return signals

    def load_sentimental_signals(
        self,
        ticker: str,
        max_exposure: float,
        warnings: list[str],
    ) -> list[SignalRow]:
        csv_rows: list[SignalRow] = []
        for path in self._sentimental_csv_sources(ticker):
            csv_rows.extend(self._read_sentimental_csv(path, ticker, max_exposure))
        if csv_rows:
            return csv_rows

        rows: list[SignalRow] = []
        text_sources = self._sentimental_text_sources()
        if not text_sources:
            warnings.append("Sentimental trade log not found.")
            return []

        for text_path in text_sources:
            for line in text_path.read_text(encoding="utf-8").splitlines():
                match = SENTIMENT_TEXT_ROW.match(line)
                if not match:
                    continue
                target = self._safe_float(match.group("target"))
                signal = self._safe_float(match.group("signal"))
                if target is None:
                    continue
                rows.append(
                    SignalRow(
                        date=date.fromisoformat(match.group("date")),
                        ticker=ticker,
                        model="sentimental",
                        raw_signal=f"{signal:.6f}" if signal is not None else match.group("signal"),
                        normalized_score=self._score_from_exposure(target, max_exposure),
                        confidence=1.0,
                        signal_label=match.group("action"),
                        source=str(text_path),
                    )
                )
        if not rows:
            warnings.append(f"Sentimental trade log had no parseable rows: {', '.join(str(path) for path in text_sources)}")
        return rows

    def load_fundamental_signals(self, ticker: str, warnings: list[str]) -> list[SignalRow]:
        rows: list[SignalRow] = []
        for path in self._fundamental_candidates():
            try:
                with path.open("r", newline="", encoding="utf-8-sig") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        row_ticker = str(row.get("ticker") or row.get("symbol") or "").upper()
                        if row_ticker and row_ticker != ticker:
                            continue
                        signal_date = self._date_from_row_or_file(row, path)
                        if signal_date is None:
                            continue
                        label = str(row.get("signal") or row.get("rating") or row.get("recommendation") or "").upper()
                        score = self._first_float(row, ["model_score", "score", "universe_percentile", "percentile"])
                        normalized = self._normalize_fundamental_score(score, label)
                        if normalized is None:
                            continue
                        rows.append(
                            SignalRow(
                                date=signal_date,
                                ticker=ticker,
                                model="fundamental",
                                raw_signal=label or (f"{score:.6f}" if score is not None else ""),
                                normalized_score=normalized,
                                confidence=1.0,
                                signal_label=label or self._label_from_score(normalized),
                                source=str(path),
                            )
                        )
            except Exception as exc:
                warnings.append(f"Failed to read fundamental signal artifact {path}: {exc}")
        if not rows:
            warnings.append("No fundamental historical signal rows were found for this ticker.")
        return rows

    def load_technical_signals(self, ticker: str, warnings: list[str]) -> list[SignalRow]:
        rows: list[SignalRow] = []
        sources = self._technical_sources()
        for path in sources:
            try:
                with path.open("r", newline="", encoding="utf-8-sig") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        row_ticker = str(row.get("ticker") or row.get("symbol") or ticker).upper()
                        if row_ticker != ticker:
                            continue
                        signal_date = self._parse_date(row.get("date") or row.get("as_of") or row.get("timestamp"))
                        if signal_date is None:
                            continue
                        normalized = self._technical_score_from_row(row)
                        if normalized is None:
                            continue
                        label = str(row.get("stance") or row.get("signal") or row.get("action") or "").upper() or None
                        rows.append(
                            SignalRow(
                                date=signal_date,
                                ticker=ticker,
                                model="technical",
                                raw_signal=self._raw_technical_signal(row),
                                normalized_score=normalized,
                                confidence=self._bounded(self._first_float(row, ["confidence", "confidence_score"]), 0.0, 1.0, 1.0),
                                signal_label=label or self._label_from_score(normalized),
                                source=str(path),
                            )
                        )
            except Exception as exc:
                warnings.append(f"Failed to read technical signal artifact {path}: {exc}")
        if not rows:
            warnings.append("No technical backtest signal CSV was found for this ticker.")
        return rows

    def build_technical_proxy_signals(
        self,
        ticker: str,
        prices: dict[date, PricePoint],
        decision_dates: list[date],
    ) -> list[SignalRow]:
        sorted_prices = sorted(prices.values(), key=lambda item: item.date)
        by_date = {point.date: idx for idx, point in enumerate(sorted_prices)}
        rows: list[SignalRow] = []
        for decision_date in decision_dates:
            idx = by_date.get(decision_date)
            if idx is None or idx < 20:
                continue
            close = sorted_prices[idx].close
            close_5 = sorted_prices[idx - 5].close
            close_20 = sorted_prices[idx - 20].close
            momentum_5 = (close / close_5) - 1.0
            momentum_20 = (close / close_20) - 1.0
            raw_score = (0.65 * momentum_5) + (0.35 * momentum_20)
            normalized = math.tanh(raw_score / 0.05)
            rows.append(
                SignalRow(
                    date=decision_date,
                    ticker=ticker,
                    model="technical",
                    raw_signal=f"{raw_score:.6f}",
                    normalized_score=self._clip_score(normalized),
                    confidence=0.5,
                    signal_label=self._label_from_score(normalized),
                    source="technical_proxy_price_momentum",
                )
            )
        return rows

    def aggregate_decisions(
        self,
        signals: list[SignalRow],
        prices: dict[date, PricePoint],
        request: EnsembleBacktestRequest,
    ) -> list[EnsembleDecision]:
        grouped: dict[date, dict[str, SignalRow]] = {}
        for row in signals:
            if row.date not in prices:
                continue
            grouped.setdefault(row.date, {})[row.model] = row

        decisions: list[EnsembleDecision] = []
        for signal_date, model_rows in sorted(grouped.items()):
            if len(model_rows) < request.min_model_count:
                continue
            sentiment_row = model_rows.get("sentimental")
            if request.require_sentiment_signal and sentiment_row is None:
                continue
            model_scores = {model: row.normalized_score for model, row in sorted(model_rows.items())}
            action = self._sentiment_led_action(sentiment_row, request)
            technical_adjustment = self._support_adjustment(model_rows.get("technical"), request.technical_exposure_weight)
            fundamental_adjustment = self._support_adjustment(model_rows.get("fundamental"), request.fundamental_exposure_weight)
            support_score = self._clip_score(technical_adjustment + fundamental_adjustment)
            sentiment_score = sentiment_row.normalized_score if sentiment_row is not None else 0.0
            average_score = self._clip_score(sentiment_score + support_score)
            target_exposure = None
            if action == "BUY":
                target_exposure = self._bounded(
                    request.base_long_exposure + technical_adjustment + fundamental_adjustment,
                    0.0,
                    request.target_long_exposure,
                    request.base_long_exposure,
                )
            elif action == "SELL":
                target_exposure = 0.0
            decisions.append(
                EnsembleDecision(
                    date=signal_date,
                    close=prices[signal_date].close,
                    action=action,
                    average_score=round(self._clip_score(average_score), 6),
                    target_exposure=round(target_exposure, 6) if target_exposure is not None else None,
                    model_count=len(model_scores),
                    model_scores={model: round(score, 6) for model, score in model_scores.items()},
                    sentiment_action=action,
                    support_score=round(support_score, 6),
                    technical_adjustment=round(technical_adjustment, 6),
                    fundamental_adjustment=round(fundamental_adjustment, 6),
                )
            )
        return decisions

    def simulate_portfolio(
        self,
        decisions: list[EnsembleDecision],
        prices: dict[date, PricePoint],
        request: EnsembleBacktestRequest,
    ) -> tuple[list[EnsembleEquityPoint], list[EnsembleTrade]]:
        decision_by_date = {decision.date: decision for decision in decisions}
        start = decisions[0].date
        end = decisions[-1].date
        price_points = [point for point in sorted(prices.values(), key=lambda item: item.date) if start <= point.date <= end]

        cash = request.initial_capital
        shares = 0.0
        previous_value = request.initial_capital
        equity_curve: list[EnsembleEquityPoint] = []
        trades: list[EnsembleTrade] = []

        for point in price_points:
            portfolio_value = cash + (shares * point.close)
            current_position_value = shares * point.close
            exposure_before = self._safe_div(current_position_value, portfolio_value)
            decision = decision_by_date.get(point.date)

            if decision and decision.action != "HOLD" and decision.target_exposure is not None:
                target_position_value = decision.target_exposure * portfolio_value
                trade_value = target_position_value - current_position_value
                if abs(trade_value) >= request.min_trade_value:
                    transaction_cost = abs(trade_value) * request.transaction_cost_pct
                    shares += trade_value / point.close
                    cash -= trade_value + transaction_cost
                    portfolio_value = cash + (shares * point.close)
                    exposure_after = self._safe_div(shares * point.close, portfolio_value)
                    trades.append(
                        EnsembleTrade(
                            date=point.date,
                            action=decision.action,
                            price=round(point.close, 4),
                            exposure_before=round(exposure_before, 6),
                            exposure_after=round(exposure_after, 6),
                            trade_value=round(trade_value, 4),
                            transaction_cost=round(transaction_cost, 4),
                            shares_after=round(shares, 8),
                            cash_after=round(cash, 4),
                            portfolio_value=round(portfolio_value, 4),
                        )
                    )

            daily_return = 0.0 if not equity_curve else self._safe_div(portfolio_value - previous_value, previous_value)
            previous_value = portfolio_value
            exposure = self._safe_div(shares * point.close, portfolio_value)
            equity_curve.append(
                EnsembleEquityPoint(
                    date=point.date,
                    close=round(point.close, 4),
                    shares=round(shares, 8),
                    cash=round(cash, 4),
                    exposure=round(exposure, 6),
                    portfolio_value=round(portfolio_value, 4),
                    daily_return=round(daily_return, 8),
                )
            )

        return equity_curve, trades

    def build_metrics(
        self,
        equity_curve: list[EnsembleEquityPoint],
        trades: list[EnsembleTrade],
        decisions: list[EnsembleDecision],
        signals: list[SignalRow],
        initial_capital: float,
    ) -> EnsembleBacktestMetrics:
        values = [point.portfolio_value for point in equity_curve]
        returns = [point.daily_return for point in equity_curve[1:]]
        final_value = values[-1]
        total_return = (final_value / initial_capital) - 1.0
        sharpe = self._annualized_sharpe(returns)
        max_drawdown = self._max_drawdown(values)
        win_rate = self._win_rate(returns)
        coverage = {
            model: sum(1 for row in signals if row.model == model)
            for model in ("fundamental", "sentimental", "technical")
        }
        average_model_count = sum(decision.model_count for decision in decisions) / len(decisions)
        return EnsembleBacktestMetrics(
            initial_capital=round(initial_capital, 4),
            final_value=round(final_value, 4),
            total_return_pct=round(total_return * 100.0, 4),
            sharpe_ratio=round(sharpe, 4),
            max_drawdown_pct=round(max_drawdown * 100.0, 4),
            win_rate_pct=round(win_rate * 100.0, 4),
            trade_count=len(trades),
            decision_count=len(decisions),
            average_model_count=round(average_model_count, 4),
            coverage_by_model=coverage,
        )

    async def fetch_price_history(self, ticker: str, start: date, end: date) -> dict[date, PricePoint]:
        local_prices = self.load_local_price_history(ticker, start, end)
        if local_prices:
            return local_prices

        import httpx

        period1 = int(datetime.combine(start - timedelta(days=35), time.min, tzinfo=timezone.utc).timestamp())
        period2 = int(datetime.combine(end + timedelta(days=2), time.min, tzinfo=timezone.utc).timestamp())
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {
            "interval": "1d",
            "period1": period1,
            "period2": period2,
            "events": "div%2Csplit",
            "includePrePost": "false",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

        result = (payload.get("chart", {}).get("result") or [{}])[0]
        timestamps = result.get("timestamp") or []
        quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quotes.get("close") or []
        prices: dict[date, PricePoint] = {}
        for idx, timestamp in enumerate(timestamps):
            close = closes[idx] if idx < len(closes) else None
            if close is None:
                continue
            point_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
            if start <= point_date <= end:
                prices[point_date] = PricePoint(date=point_date, close=float(close))
        return prices

    def load_local_price_history(self, ticker: str, start: date, end: date) -> dict[date, PricePoint]:
        for root in self._price_history_roots():
            path = root / f"{ticker}.csv"
            if not path.exists():
                continue
            prices: dict[date, PricePoint] = {}
            try:
                with path.open("r", newline="", encoding="utf-8-sig") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        point_date = self._parse_date(row.get("Date") or row.get("date") or row.get("timestamp"))
                        close = self._first_float(row, ["Close", "close", "adj_close", "Adj Close"])
                        if point_date is None or close is None or not start <= point_date <= end:
                            continue
                        prices[point_date] = PricePoint(date=point_date, close=close)
            except Exception:
                continue
            if prices:
                return prices
        return {}

    def _price_history_roots(self) -> list[Path]:
        roots: list[Path] = []
        if self.use_env_artifacts:
            roots.append(Path(os.getenv("PRICE_HISTORY_DIR", "/artifacts/prices")))
        roots.append(self.repo_root / "fundamental_model" / "data" / "raw" / "prices")
        return [root for root in roots if root.exists()]

    def _sentimental_sources(self, ticker: str) -> list[Path]:
        sources = self._sentimental_csv_sources(ticker)
        sources.extend(self._sentimental_text_sources())
        return sorted(dict.fromkeys(sources))

    def _sentimental_csv_sources(self, ticker: str) -> list[Path]:
        roots: list[Path] = []
        if self.use_env_artifacts:
            roots.append(Path(os.getenv("SENTIMENTAL_BACKTEST_DIR", "/artifacts/sentimental")))
        roots.append(self.repo_root / "Sentimental_Model" / "data")
        sources: list[Path] = []
        for data_dir in roots:
            if not data_dir.exists():
                continue
            exact = data_dir / f"test_trades_ctx1y_allocator_{ticker}.csv"
            if exact.exists():
                sources.append(exact)
            sources.extend(path for path in data_dir.glob(f"*trades*{ticker}*.csv") if path.exists() and path not in sources)
        return sorted(sources)

    def _sentimental_text_sources(self) -> list[Path]:
        sources: list[Path] = []
        if self.use_env_artifacts:
            sources.append(Path(os.getenv("SENTIMENTAL_TRADE_LOG", "/artifacts/sentimental/sentimental_trades.txt")))
        sources.append(self.repo_root / "Sentimental_Model" / "sentimental_trades.txt")
        return [path for path in dict.fromkeys(sources) if path.exists()]

    def _read_sentimental_csv(self, path: Path, ticker: str, max_exposure: float) -> list[SignalRow]:
        rows: list[SignalRow] = []
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_ticker = str(row.get("ticker") or row.get("symbol") or ticker).upper()
                if row_ticker != ticker:
                    continue
                signal_date = self._parse_date(row.get("date") or row.get("timestamp"))
                exposure = self._first_float(row, ["chosen_exp", "chosen_exposure", "target", "target_exposure", "raw_target_exp"])
                if signal_date is None or exposure is None:
                    continue
                raw_signal = self._first_float(row, ["signal", "model_signal", "predicted_edge"])
                rows.append(
                    SignalRow(
                        date=signal_date,
                        ticker=ticker,
                        model="sentimental",
                        raw_signal=f"{raw_signal:.6f}" if raw_signal is not None else str(exposure),
                        normalized_score=self._score_from_exposure(exposure, max_exposure),
                        confidence=1.0,
                        signal_label=str(row.get("direction") or row.get("action") or "").upper() or None,
                        source=str(path),
                    )
                )
        return rows

    def _fundamental_candidates(self) -> list[Path]:
        roots: list[Path] = []
        if self.use_env_artifacts:
            roots.append(Path(os.getenv("FUNDAMENTAL_ARTIFACT_DIR", "/app/artifacts/fundamental")))
        roots.extend(
            [
                self.repo_root / "fundamental_model" / "outputs",
                self.repo_root / "fundamental_model" / "outputs" / "signals",
            ]
        )
        candidates: list[Path] = []
        for root in roots:
            if not root.exists():
                continue
            search_roots = [root]
            if (root / "signals").exists():
                search_roots.append(root / "signals")
            for search_root in search_roots:
                for pattern in ("latest_signals.csv", "signals_*.csv", "top7_buys_*.csv"):
                    candidates.extend(search_root.glob(pattern))
        unique = list(dict.fromkeys(path.resolve() for path in candidates if path.is_file()))
        return sorted(unique, key=lambda path: (self._date_from_filename(path) or date.min, path.stat().st_mtime))

    def _technical_sources(self) -> list[Path]:
        roots: list[Path] = []
        if self.use_env_artifacts:
            roots.append(Path(os.getenv("TECHNICAL_ARTIFACT_DIR", "/artifacts/technical/final_1d_artifacts")))
        roots.append(self.repo_root / "Technical_Model" / "final_1d_artifacts")
        names = ("backtest_signals.csv", "technical_backtest_signals.csv", "rolling_backtest_signals.csv")
        sources: list[Path] = []
        for root in roots:
            if not root.exists():
                continue
            for name in names:
                for candidate in (root / name, root / "ensemble" / name):
                    if candidate.exists() and candidate.is_file():
                        sources.append(candidate.resolve())
        return sorted(dict.fromkeys(sources))

    def _date_from_row_or_file(self, row: dict[str, Any], path: Path) -> date | None:
        for key in ("date", "as_of", "signal_date", "source_signal_date", "created_at"):
            parsed = self._parse_date(row.get(key))
            if parsed is not None:
                return parsed
        return self._date_from_filename(path)

    @staticmethod
    def _date_from_filename(path: Path) -> date | None:
        match = re.search(r"(\d{8})", path.name)
        if not match:
            return None
        raw = match.group(1)
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            pass
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except ValueError:
            return None

    def _technical_score_from_row(self, row: dict[str, Any]) -> float | None:
        normalized = self._first_float(row, ["normalized_score", "score"])
        if normalized is not None:
            return self._clip_score(normalized)
        action_value = self._first_float(row, ["policy_action", "recommended_position_pct", "raw_action"])
        if action_value is not None:
            return self._clip_score(action_value)
        predicted_return = self._first_float(row, ["predicted_return", "forecast_return", "next_return"])
        if predicted_return is not None:
            return self._clip_score(math.tanh(predicted_return / 0.05))
        stance = str(row.get("stance") or row.get("signal") or row.get("action") or "").upper()
        if stance in {"LONG", "BUY"}:
            return 1.0
        if stance in {"SHORT", "SELL"}:
            return -1.0
        if stance in {"NEUTRAL", "HOLD"}:
            return 0.0
        return None

    def _raw_technical_signal(self, row: dict[str, Any]) -> str:
        for key in ("raw_signal", "policy_action", "recommended_position_pct", "predicted_return", "stance", "signal"):
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    @staticmethod
    def _first_float(row: dict[str, Any], keys: Iterable[str]) -> float | None:
        for key in keys:
            value = EnsembleBacktestEngine._safe_float(row.get(key))
            if value is not None:
                return value
        return None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value in (None, "", "NA", "None", "nan"):
                return None
            parsed = float(str(value).replace("$", "").replace(",", "").strip())
            return parsed if math.isfinite(parsed) else None
        except (TypeError, ValueError):
            return None

    def _normalize_fundamental_score(self, score: float | None, label: str) -> float | None:
        if score is not None:
            if 0.0 <= score <= 1.0:
                return self._clip_score((score * 2.0) - 1.0)
            if 0.0 <= score <= 10.0:
                return self._clip_score(((score / 10.0) * 2.0) - 1.0)
        if "BUY" in label:
            return 1.0
        if "SELL" in label or "AVOID" in label:
            return -1.0
        if "HOLD" in label or "NEUTRAL" in label:
            return 0.0
        return None

    def _score_from_exposure(self, exposure: float, max_exposure: float) -> float:
        return self._clip_score(((exposure / max_exposure) * 2.0) - 1.0)

    def _sentiment_led_action(self, sentiment_row: SignalRow | None, request: EnsembleBacktestRequest) -> TradeAction:
        if sentiment_row is None:
            return "HOLD"
        label = (sentiment_row.signal_label or sentiment_row.raw_signal or "").upper()
        if "BUY" in label:
            return "BUY"
        if "SELL" in label:
            return "SELL"
        if "HOLD" in label or "NEUTRAL" in label:
            return "HOLD"
        return self._action_from_score(sentiment_row.normalized_score, request.buy_threshold, request.sell_threshold)

    def _support_adjustment(self, row: SignalRow | None, exposure_weight: float) -> float:
        if row is None:
            return 0.0
        return self._clip_score(row.normalized_score) * exposure_weight

    @staticmethod
    def _action_from_score(score: float, buy_threshold: float, sell_threshold: float) -> TradeAction:
        if score >= buy_threshold:
            return "BUY"
        if score <= sell_threshold:
            return "SELL"
        return "HOLD"

    @staticmethod
    def _label_from_score(score: float) -> str:
        if score >= 0.15:
            return "BUY"
        if score <= -0.15:
            return "SELL"
        return "HOLD"

    @staticmethod
    def _clip_score(value: float) -> float:
        return max(-1.0, min(1.0, float(value)))

    @staticmethod
    def _bounded(value: float | None, minimum: float, maximum: float, default: float) -> float:
        if value is None:
            return default
        return max(minimum, min(maximum, float(value)))

    @staticmethod
    def _safe_div(numerator: float, denominator: float) -> float:
        if abs(denominator) < 1e-12:
            return 0.0
        return numerator / denominator

    @staticmethod
    def _annualized_sharpe(returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0
        mean_return = sum(returns) / len(returns)
        variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
        std_dev = math.sqrt(variance)
        if std_dev <= 1e-12:
            return 0.0
        return (mean_return / std_dev) * math.sqrt(252.0)

    @staticmethod
    def _max_drawdown(values: list[float]) -> float:
        peak = values[0]
        worst = 0.0
        for value in values:
            peak = max(peak, value)
            drawdown = (value / peak) - 1.0 if peak > 0 else 0.0
            worst = min(worst, drawdown)
        return worst

    @staticmethod
    def _win_rate(returns: list[float]) -> float:
        if not returns:
            return 0.0
        return sum(1 for value in returns if value > 0.0) / len(returns)
