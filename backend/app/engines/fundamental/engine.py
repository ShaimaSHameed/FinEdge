from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations.eodhd_api import EODHDClient
from app.models.cache_financial_report import CacheFinancialReport
from app.schemas.fundamental import (
    FundamentalAnalysisRequest,
    FundamentalAnalysisResponse,
    FundamentalPeerContext,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SignalRecord:
    ticker: str
    score: Optional[float]
    signal: str
    relative_rank: Optional[int]
    universe_percentile: Optional[float]
    source_file: str
    source_signal_date: Optional[str]


class FundamentalAnalysisEngine:
    def __init__(self) -> None:
        self.eodhd_client = EODHDClient()

    async def analyze(
        self,
        request: FundamentalAnalysisRequest,
        db: AsyncSession,
    ) -> FundamentalAnalysisResponse:
        ticker = request.ticker.upper().strip()
        market = request.market.upper()

        if market != "US":
            raise ValueError("Fundamental analysis currently supports US market data only")

        signal = self._find_latest_signal(ticker)
        if settings.FUNDAMENTAL_REQUIRE_MODEL_SIGNAL and signal is None:
            artifact_status = self.artifact_status()
            latest_file = artifact_status.get("latest_signal_file") or "none"
            raise ValueError(
                f"No fundamental model signal is available for {ticker}. "
                f"Docker is configured to require real model artifacts; latest signal file: {latest_file}."
            )

        report_data, report_cached = await self._get_financial_report(ticker, market, db)

        if signal is None and report_data is None:
            raise ValueError(
                f"No fundamental model output is available for {ticker}. "
                "Refresh the fundamental model artifacts or choose a covered ticker."
            )

        return self._build_response(
            ticker=ticker,
            market=market,
            signal=signal,
            report_data=report_data,
            report_cached=report_cached,
            include_peer_context=request.include_peer_context,
        )

    def _find_latest_signal(self, ticker: str) -> SignalRecord | None:
        for csv_path in self._signal_candidates():
            try:
                with csv_path.open("r", newline="", encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        if (row.get("ticker") or "").upper() != ticker:
                            continue
                        return SignalRecord(
                            ticker=ticker,
                            score=self._safe_float(row.get("score")),
                            signal=self._normalize_signal_text(row.get("signal")),
                            relative_rank=self._safe_int(row.get("relative_rank") or row.get("rank")),
                            universe_percentile=self._safe_float(row.get("universe_percentile")),
                            source_file=str(csv_path),
                            source_signal_date=self._signal_date_from_name(csv_path.name),
                        )
            except Exception as exc:
                logger.warning(f"Failed to read fundamental signal artifact {csv_path}: {exc}")
        return None

    def _signal_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        for root in self._artifact_roots():
            if not root.exists():
                continue
            search_roots = [root]
            if (root / "signals").exists():
                search_roots.append(root / "signals")
            for search_root in search_roots:
                for pattern in ("latest_signals.csv", "signals_*.csv", "top7_buys_*.csv"):
                    candidates.extend(search_root.glob(pattern))

        unique_candidates = list(dict.fromkeys(path.resolve() for path in candidates if path.is_file()))
        return sorted(unique_candidates, key=self._artifact_sort_key, reverse=True)

    def artifact_status(self) -> Dict[str, Any]:
        signal_files = self._signal_candidates()
        latest_signal = signal_files[0] if signal_files else None
        configured_root = Path(settings.FUNDAMENTAL_ARTIFACT_DIR)
        roots = [root for root in self._artifact_roots()]

        return {
            "artifact_dir": str(configured_root),
            "artifact_dir_exists": configured_root.exists(),
            "require_model_signal": settings.FUNDAMENTAL_REQUIRE_MODEL_SIGNAL,
            "signal_file_count": len(signal_files),
            "latest_signal_file": str(latest_signal) if latest_signal else None,
            "latest_signal_date": self._signal_date_from_name(latest_signal.name) if latest_signal else None,
            "latest_signal_rows": self._count_signal_rows(latest_signal) if latest_signal else 0,
            "model_files": {
                "final_model": any((root / "models" / "final_model.pkl").exists() for root in roots),
                "lgbm_model": any((root / "models" / "lgbm_model.pkl").exists() for root in roots),
                "sector_models": any((root / "models" / "sector_models").exists() for root in roots),
            },
        }

    def _artifact_roots(self) -> Iterable[Path]:
        configured = Path(settings.FUNDAMENTAL_ARTIFACT_DIR)
        yield configured

        repo_root = Path(__file__).resolve().parents[4]
        model_outputs = repo_root / "fundamental_model" / "outputs"
        yield model_outputs
        yield model_outputs / "signals"

    def _artifact_sort_key(self, path: Path) -> tuple[str, float]:
        signal_date = "99999999" if path.name == "latest_signals.csv" else self._signal_date_from_name(path.name) or ""
        try:
            modified = path.stat().st_mtime
        except OSError:
            modified = 0.0
        return signal_date, modified

    def _count_signal_rows(self, csv_path: Path) -> int:
        try:
            with csv_path.open("r", newline="", encoding="utf-8") as handle:
                return sum(1 for _ in csv.DictReader(handle))
        except Exception as exc:
            logger.warning(f"Failed to count fundamental signal artifact rows {csv_path}: {exc}")
            return 0

    async def _get_financial_report(
        self,
        ticker: str,
        market: str,
        db: AsyncSession,
    ) -> tuple[Dict[str, Any] | None, bool]:
        cached = await self._get_cached_report(ticker, market, db)
        if cached is not None:
            return cached, True

        data = await self.eodhd_client.fetch_fundamentals(ticker, market)
        if data is None:
            return None, False

        await self._save_cached_report(ticker, market, data, db)
        return data, False

    async def _get_cached_report(
        self,
        ticker: str,
        market: str,
        db: AsyncSession,
    ) -> Dict[str, Any] | None:
        try:
            stmt = (
                select(CacheFinancialReport)
                .where(CacheFinancialReport.ticker == ticker)
                .where(CacheFinancialReport.market == market)
                .where(CacheFinancialReport.report_type == "fundamentals")
                .where(CacheFinancialReport.expires_at > datetime.utcnow())
                .order_by(CacheFinancialReport.cached_at.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            cached = result.scalar_one_or_none()
            if cached is None:
                return None
            return json.loads(cached.content)
        except Exception as exc:
            logger.warning(f"Failed to read cached financial report for {ticker}: {exc}")
            return None

    async def _save_cached_report(
        self,
        ticker: str,
        market: str,
        data: Dict[str, Any],
        db: AsyncSession,
    ) -> None:
        try:
            cached_report = CacheFinancialReport(
                ticker=ticker,
                market=market,
                report_type="fundamentals",
                report_period="latest",
                content=json.dumps(data),
                source="eodhd",
                cached_at=datetime.utcnow(),
                expires_at=datetime.utcnow() + timedelta(days=settings.FUNDAMENTAL_REPORT_CACHE_DAYS),
            )
            db.add(cached_report)
            await db.commit()
        except Exception as exc:
            logger.warning(f"Failed to cache financial report for {ticker}: {exc}")
            await db.rollback()

    def _build_response(
        self,
        ticker: str,
        market: str,
        signal: SignalRecord | None,
        report_data: Dict[str, Any] | None,
        report_cached: bool,
        include_peer_context: bool,
    ) -> FundamentalAnalysisResponse:
        general = (report_data or {}).get("General", {})
        metrics = self._extract_key_metrics(report_data)
        trends = self._extract_trends(report_data)
        rating = self._rating_from_signal(signal.signal if signal else None)
        model_score = signal.score if signal else None
        score = self._score_to_ten(model_score, rating)
        strengths, concerns = self._build_takeaways(metrics, rating, signal)
        company_name = general.get("Name") or ticker
        sector = general.get("Sector")
        peer_context = None

        if include_peer_context and signal is not None:
            peer_context = FundamentalPeerContext(
                sector_percentile=None,
                universe_percentile=signal.universe_percentile,
                relative_rank=signal.relative_rank,
                source=Path(signal.source_file).name,
            )

        data_sources = ["model-artifact"] if signal else []
        if report_data:
            data_sources.append("eodhd")

        return FundamentalAnalysisResponse(
            ticker=ticker,
            market=market,
            company_name=company_name,
            sector=sector,
            rating=rating,
            signal=signal.signal if signal else rating,
            score=score,
            model_score=model_score,
            universe_percentile=signal.universe_percentile if signal else None,
            relative_rank=signal.relative_rank if signal else None,
            key_metrics=metrics,
            trends=trends,
            peer_context=peer_context,
            strengths=strengths,
            concerns=concerns,
            analysis_summary=self._build_summary(ticker, rating, score, signal, strengths, concerns),
            data_source="+".join(data_sources) or "unavailable",
            cached=bool(signal) or report_cached,
            source_signal_date=signal.source_signal_date if signal else None,
            generated_at=datetime.now(timezone.utc),
        )

    def _extract_key_metrics(self, report_data: Dict[str, Any] | None) -> Dict[str, Optional[float]]:
        if not report_data:
            return {
                "pe_ratio": None,
                "roe": None,
                "debt_to_equity": None,
                "free_cash_flow_margin": None,
                "revenue_growth_yoy": None,
                "earnings_growth_yoy": None,
            }

        highlights = report_data.get("Highlights", {})
        latest_income = self._latest_statement(report_data, "Income_Statement")
        year_ago_income = self._statement_offset(report_data, "Income_Statement", 4)
        latest_cash_flow = self._latest_statement(report_data, "Cash_Flow")
        latest_balance = self._latest_statement(report_data, "Balance_Sheet")

        revenue = self._safe_float(latest_income.get("totalRevenue"))
        year_ago_revenue = self._safe_float(year_ago_income.get("totalRevenue"))
        net_income = self._safe_float(latest_income.get("netIncome"))
        year_ago_net_income = self._safe_float(year_ago_income.get("netIncome"))
        free_cash_flow = self._safe_float(latest_cash_flow.get("freeCashFlow"))
        debt = self._safe_float(latest_balance.get("shortLongTermDebtTotal")) or self._safe_float(
            latest_balance.get("longTermDebt")
        )
        equity = self._safe_float(latest_balance.get("totalStockholderEquity"))

        return {
            "pe_ratio": self._safe_float(highlights.get("PERatio")),
            "roe": self._safe_float(highlights.get("ReturnOnEquityTTM")),
            "debt_to_equity": self._safe_float(highlights.get("DebtToEquity"))
            or self._safe_div(debt, equity),
            "free_cash_flow_margin": self._safe_div(free_cash_flow, revenue),
            "revenue_growth_yoy": self._growth_rate(revenue, year_ago_revenue),
            "earnings_growth_yoy": self._growth_rate(net_income, year_ago_net_income),
        }

    def _extract_trends(self, report_data: Dict[str, Any] | None) -> Dict[str, str]:
        if not report_data:
            return {"revenue": "Unknown", "earnings": "Unknown", "cash_flow": "Unknown"}

        return {
            "revenue": self._trend_from_statement(report_data, "Income_Statement", "totalRevenue"),
            "earnings": self._trend_from_statement(report_data, "Income_Statement", "netIncome"),
            "cash_flow": self._trend_from_statement(report_data, "Cash_Flow", "freeCashFlow"),
        }

    def _trend_from_statement(self, report_data: Dict[str, Any], statement: str, key: str) -> str:
        rows = self._quarterly_rows(report_data, statement)
        if len(rows) < 2:
            return "Unknown"
        latest = self._safe_float(rows[0].get(key))
        previous = self._safe_float(rows[1].get(key))
        growth = self._growth_rate(latest, previous)
        if growth is None:
            return "Unknown"
        if growth > 0.05:
            return "Improving"
        if growth < -0.05:
            return "Declining"
        return "Stable"

    def _latest_statement(self, report_data: Dict[str, Any], statement: str) -> Dict[str, Any]:
        return self._statement_offset(report_data, statement, 0)

    def _statement_offset(self, report_data: Dict[str, Any], statement: str, offset: int) -> Dict[str, Any]:
        rows = self._quarterly_rows(report_data, statement)
        if offset >= len(rows):
            return {}
        return rows[offset]

    def _quarterly_rows(self, report_data: Dict[str, Any], statement: str) -> list[Dict[str, Any]]:
        quarterly = (
            report_data.get("Financials", {})
            .get(statement, {})
            .get("quarterly", {})
        )
        if not isinstance(quarterly, dict):
            return []
        return [
            row
            for _, row in sorted(
                quarterly.items(),
                key=lambda item: item[0],
                reverse=True,
            )
            if isinstance(row, dict)
        ]

    def _build_takeaways(
        self,
        metrics: Dict[str, Optional[float]],
        rating: str,
        signal: SignalRecord | None,
    ) -> tuple[list[str], list[str]]:
        strengths: list[str] = []
        concerns: list[str] = []

        if signal and signal.universe_percentile is not None:
            if signal.universe_percentile >= 0.7:
                strengths.append("Ranks in the upper tier of the model universe")
            elif signal.universe_percentile <= 0.35:
                concerns.append("Ranks in the lower tier of the model universe")

        revenue_growth = metrics.get("revenue_growth_yoy")
        if revenue_growth is not None:
            if revenue_growth > 0.1:
                strengths.append("Revenue growth is running ahead of a normal mature-company pace")
            elif revenue_growth < 0:
                concerns.append("Revenue has declined versus the year-ago quarter")

        fcf_margin = metrics.get("free_cash_flow_margin")
        if fcf_margin is not None:
            if fcf_margin > 0.2:
                strengths.append("Free cash flow conversion is strong")
            elif fcf_margin < 0.05:
                concerns.append("Free cash flow conversion is thin")

        debt_to_equity = metrics.get("debt_to_equity")
        if debt_to_equity is not None and debt_to_equity > 2:
            concerns.append("Leverage is elevated relative to equity")

        if not strengths and rating == "BUY":
            strengths.append("The latest model signal is constructive")
        if not concerns and rating == "SELL":
            concerns.append("The latest model signal is cautious")
        if not strengths:
            strengths.append("Fundamental data is available for review")
        if not concerns:
            concerns.append("Monitor upcoming filings for confirmation")

        return strengths[:4], concerns[:4]

    def _build_summary(
        self,
        ticker: str,
        rating: str,
        score: float,
        signal: SignalRecord | None,
        strengths: list[str],
        concerns: list[str],
    ) -> str:
        rank_text = ""
        if signal and signal.relative_rank:
            rank_text = f" with model rank {signal.relative_rank}"
        source_text = "latest fundamental model artifact" if signal else "available financial report data"
        return (
            f"{ticker} receives a {rating} fundamental rating ({score:.1f}/10){rank_text} "
            f"based on the {source_text}. Key support: {strengths[0]}. "
            f"Key watch item: {concerns[0]}."
        )

    @staticmethod
    def _rating_from_signal(signal: str | None) -> str:
        if not signal:
            return "HOLD"
        normalized = signal.upper()
        if "BUY" in normalized:
            return "BUY"
        if "SELL" in normalized or "AVOID" in normalized:
            return "SELL"
        return "HOLD"

    @staticmethod
    def _score_to_ten(model_score: Optional[float], rating: str) -> float:
        if model_score is not None:
            return round(max(0.0, min(model_score * 10, 10.0)), 1)
        return {"BUY": 7.0, "HOLD": 5.0, "SELL": 3.0}[rating]

    @staticmethod
    def _normalize_signal_text(signal: str | None) -> str:
        normalized = (signal or "HOLD").strip().upper()
        if normalized == "AVOID":
            return "SELL"
        return normalized

    @staticmethod
    def _signal_date_from_name(file_name: str) -> str | None:
        match = re.search(r"(\d{8})", file_name)
        return match.group(1) if match else None

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value in (None, "", "NA", "None", "nan"):
                return None
            result = float(value)
            return result if result == result else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            if value in (None, "", "NA", "None", "nan"):
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_div(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
        if numerator is None or denominator is None or abs(denominator) < 1e-9:
            return None
        return numerator / denominator

    def _growth_rate(self, current: Optional[float], previous: Optional[float]) -> Optional[float]:
        if current is None or previous is None or abs(previous) < 1e-9:
            return None
        return (current - previous) / abs(previous)
