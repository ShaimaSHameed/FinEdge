from __future__ import annotations

import sys
import tempfile
import types
import unittest
import importlib.util
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


for package_name in ("app", "app.schemas", "app.engines", "app.engines.ensemble"):
    package = sys.modules.setdefault(package_name, types.ModuleType(package_name))
    package.__path__ = []  # type: ignore[attr-defined]


class SimpleBaseModel:
    def __init__(self, **kwargs):
        annotations = {}
        for cls in reversed(type(self).__mro__):
            annotations.update(getattr(cls, "__annotations__", {}))
        for name in annotations:
            if name in kwargs:
                value = kwargs[name]
            elif hasattr(type(self), name):
                value = getattr(type(self), name)
                if value is Ellipsis:
                    continue
            else:
                continue
            setattr(self, name, value)


def field(default=Ellipsis, **_kwargs):
    return default


def model_validator(**_kwargs):
    def decorator(func):
        return func

    return decorator


sys.modules.setdefault(
    "pydantic",
    types.SimpleNamespace(BaseModel=SimpleBaseModel, Field=field, model_validator=model_validator),
)

ensemble_schema = load_module("app.schemas.ensemble", BACKEND_ROOT / "app" / "schemas" / "ensemble.py")
backtest_module = load_module(
    "app.engines.ensemble.backtest",
    BACKEND_ROOT / "app" / "engines" / "ensemble" / "backtest.py",
)

EnsembleBacktestRequest = ensemble_schema.EnsembleBacktestRequest
EnsembleBacktestEngine = backtest_module.EnsembleBacktestEngine
PricePoint = backtest_module.PricePoint
SignalRow = backtest_module.SignalRow


class EnsembleBacktestTests(unittest.TestCase):
    def test_parses_sentimental_text_trade_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            log_dir = repo_root / "Sentimental_Model"
            log_dir.mkdir(parents=True)
            (log_dir / "sentimental_trades.txt").write_text(
                "      Date            Signal  Target     Actual\u2192New Action     Trade$   Portfolio\n"
                "      2025-04-21      +4.064    1.25      0.00\u21921.25    BUY $ +524.77 $   999.48\n"
                "      2025-04-22      -2.000    0.00      1.25\u21920.00   SELL $ -524.77 $  1000.00\n",
                encoding="utf-8",
            )

            engine = EnsembleBacktestEngine(repo_root=repo_root)
            warnings: list[str] = []
            rows = engine.load_sentimental_signals("GOOGL", 2.5, warnings)

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0].date, date(2025, 4, 21))
            self.assertEqual(rows[0].signal_label, "BUY")
            self.assertAlmostEqual(rows[0].normalized_score, 0.0)
            self.assertAlmostEqual(rows[1].normalized_score, -1.0)
            self.assertEqual(warnings, [])

    def test_parses_fundamental_signal_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            signal_dir = repo_root / "fundamental_model" / "outputs"
            signal_dir.mkdir(parents=True)
            (signal_dir / "signals_20250102.csv").write_text(
                "ticker,score,signal\nGOOGL,0.8,BUY\nMSFT,0.2,SELL\n",
                encoding="utf-8",
            )

            engine = EnsembleBacktestEngine(repo_root=repo_root)
            warnings: list[str] = []
            rows = engine.load_fundamental_signals("GOOGL", warnings)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].date, date(2025, 1, 2))
            self.assertEqual(rows[0].signal_label, "BUY")
            self.assertAlmostEqual(rows[0].normalized_score, 0.6)

    def test_sentiment_buy_scales_with_support_then_sell_exits(self) -> None:
        engine = EnsembleBacktestEngine(repo_root=Path("/unused"))
        request = EnsembleBacktestRequest(
            ticker="GOOGL",
            initial_capital=1000.0,
            transaction_cost_pct=0.0,
            buy_threshold=0.15,
            sell_threshold=-0.15,
        )
        prices = {
            date(2025, 1, 2): PricePoint(date(2025, 1, 2), 100.0),
            date(2025, 1, 3): PricePoint(date(2025, 1, 3), 110.0),
        }
        signals = [
            SignalRow(date(2025, 1, 2), "GOOGL", "fundamental", "BUY", 1.0, 1.0, "BUY", "test"),
            SignalRow(date(2025, 1, 2), "GOOGL", "sentimental", "0.5", 0.5, 1.0, "BUY", "test"),
            SignalRow(date(2025, 1, 2), "GOOGL", "technical", "1.0", 1.0, 1.0, "BUY", "test"),
            SignalRow(date(2025, 1, 3), "GOOGL", "fundamental", "BUY", 1.0, 1.0, "BUY", "test"),
            SignalRow(date(2025, 1, 3), "GOOGL", "sentimental", "-1.0", -1.0, 1.0, "SELL", "test"),
            SignalRow(date(2025, 1, 3), "GOOGL", "technical", "1.0", 1.0, 1.0, "BUY", "test"),
        ]

        decisions = engine.aggregate_decisions(signals, prices, request)
        equity_curve, trades = engine.simulate_portfolio(decisions, prices, request)
        metrics = engine.build_metrics(equity_curve, trades, decisions, signals, request.initial_capital)

        self.assertEqual([decision.action for decision in decisions], ["BUY", "SELL"])
        self.assertAlmostEqual(decisions[0].target_exposure, 1.0)
        self.assertAlmostEqual(decisions[0].technical_adjustment, 0.25)
        self.assertAlmostEqual(decisions[0].fundamental_adjustment, 0.15)
        self.assertAlmostEqual(decisions[1].target_exposure, 0.0)
        self.assertEqual(len(trades), 2)
        self.assertAlmostEqual(trades[0].shares_after, 10.0)
        self.assertAlmostEqual(metrics.final_value, 1100.0)
        self.assertAlmostEqual(metrics.total_return_pct, 10.0)

    def test_sentiment_buy_negative_support_reduces_exposure(self) -> None:
        engine = EnsembleBacktestEngine(repo_root=Path("/unused"))
        request = EnsembleBacktestRequest(ticker="GOOGL")
        prices = {
            date(2025, 1, 2): PricePoint(date(2025, 1, 2), 100.0),
        }
        signals = [
            SignalRow(date(2025, 1, 2), "GOOGL", "fundamental", "SELL", -1.0, 1.0, "SELL", "test"),
            SignalRow(date(2025, 1, 2), "GOOGL", "sentimental", "BUY", 0.8, 1.0, "BUY", "test"),
            SignalRow(date(2025, 1, 2), "GOOGL", "technical", "SELL", -1.0, 1.0, "SELL", "test"),
        ]

        decisions = engine.aggregate_decisions(signals, prices, request)

        self.assertEqual(decisions[0].action, "BUY")
        self.assertAlmostEqual(decisions[0].target_exposure, 0.2)
        self.assertAlmostEqual(decisions[0].support_score, -0.4)

    def test_sentiment_hold_does_not_trade(self) -> None:
        engine = EnsembleBacktestEngine(repo_root=Path("/unused"))
        request = EnsembleBacktestRequest(ticker="GOOGL")
        prices = {
            date(2025, 1, 2): PricePoint(date(2025, 1, 2), 100.0),
        }
        signals = [
            SignalRow(date(2025, 1, 2), "GOOGL", "fundamental", "BUY", 1.0, 1.0, "BUY", "test"),
            SignalRow(date(2025, 1, 2), "GOOGL", "sentimental", "HOLD", 0.0, 1.0, "HOLD", "test"),
            SignalRow(date(2025, 1, 2), "GOOGL", "technical", "BUY", 1.0, 1.0, "BUY", "test"),
        ]

        decisions = engine.aggregate_decisions(signals, prices, request)
        equity_curve, trades = engine.simulate_portfolio(decisions, prices, request)

        self.assertEqual(decisions[0].action, "HOLD")
        self.assertIsNone(decisions[0].target_exposure)
        self.assertEqual(trades, [])
        self.assertAlmostEqual(equity_curve[0].portfolio_value, request.initial_capital)


if __name__ == "__main__":
    unittest.main()
