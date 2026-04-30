"""Compare current DB params against optimized guarded params on OOS windows."""

from dataclasses import asdict, dataclass
from typing import Dict

import pandas as pd

from backtest import BacktestConfig, BacktestParams
from backtest.strategy import CallableStrategy
from optimizer.random_search import (
    RandomSearchReport,
    _build_report,
    _run_backtest,
    _slice_data,
)
from optimizer.window import DateRange, WalkForwardWindow


@dataclass(frozen=True)
class FixedWindowResult:
    window: WalkForwardWindow
    validation_metrics: Dict


@dataclass(frozen=True)
class FixedParamReport:
    params: BacktestParams
    windows: list[FixedWindowResult]
    profitable_windows: int
    avg_oos_sharpe: float
    avg_oos_return_pct: float
    avg_max_drawdown_pct: float
    total_windows: int


@dataclass(frozen=True)
class ParamComparisonReport:
    current: FixedParamReport
    optimized: FixedParamReport
    delta: Dict
    save_recommended: bool
    reason: str

    def to_text(self) -> str:
        return (
            "=== Current vs Optimized Parameter Report ===\n"
            "[Current DB Params]\n"
            f"Windows: {self.current.profitable_windows} / {self.current.total_windows} profitable\n"
            f"Avg OOS Sharpe: {self.current.avg_oos_sharpe:.2f}\n"
            f"Avg OOS Return: {self.current.avg_oos_return_pct:.2f}%\n"
            f"Avg Max Drawdown: {self.current.avg_max_drawdown_pct:.2f}%\n\n"
            "[Optimized Guarded Params]\n"
            f"Windows: {self.optimized.profitable_windows} / {self.optimized.total_windows} profitable\n"
            f"Avg OOS Sharpe: {self.optimized.avg_oos_sharpe:.2f}\n"
            f"Avg OOS Return: {self.optimized.avg_oos_return_pct:.2f}%\n"
            f"Avg Max Drawdown: {self.optimized.avg_max_drawdown_pct:.2f}%\n\n"
            "[Delta]\n"
            f"Sharpe: {self.delta['avg_oos_sharpe']:+.2f}\n"
            f"Return: {self.delta['avg_oos_return_pct']:+.2f}%\n"
            f"Max Drawdown: {self.delta['avg_max_drawdown_pct']:+.2f}%\n"
            f"Profitable windows: {self.delta['profitable_windows']:+d}\n\n"
            f"Save recommended: {self.save_recommended}\n"
            f"Reason: {self.reason}"
        )


def compare_current_vs_optimized(
    hist_data: Dict[str, pd.DataFrame],
    strategy: CallableStrategy,
    windows: list[WalkForwardWindow],
    current_params: BacktestParams,
    optimized_params: BacktestParams,
    config: BacktestConfig,
    min_sharpe_delta: float = 0.10,
    min_return_delta: float = 0.05,
) -> ParamComparisonReport:
    current = evaluate_fixed_params(hist_data, strategy, windows, current_params, config)
    optimized = evaluate_fixed_params(hist_data, strategy, windows, optimized_params, config)
    delta = {
        "avg_oos_sharpe": round(optimized.avg_oos_sharpe - current.avg_oos_sharpe, 4),
        "avg_oos_return_pct": round(optimized.avg_oos_return_pct - current.avg_oos_return_pct, 4),
        "avg_max_drawdown_pct": round(optimized.avg_max_drawdown_pct - current.avg_max_drawdown_pct, 4),
        "profitable_windows": optimized.profitable_windows - current.profitable_windows,
    }
    failures = []
    if delta["avg_oos_sharpe"] < min_sharpe_delta:
        failures.append(f"Sharpe delta {delta['avg_oos_sharpe']:.2f} below {min_sharpe_delta:.2f}")
    if delta["avg_oos_return_pct"] < min_return_delta:
        failures.append(f"return delta {delta['avg_oos_return_pct']:.2f}% below {min_return_delta:.2f}%")
    if optimized.avg_oos_return_pct <= 0:
        failures.append("optimized OOS return is not positive")

    return ParamComparisonReport(
        current=current,
        optimized=optimized,
        delta=delta,
        save_recommended=not failures,
        reason="; ".join(failures) if failures else "optimized params improve current DB params",
    )


def evaluate_fixed_params(
    hist_data: Dict[str, pd.DataFrame],
    strategy: CallableStrategy,
    windows: list[WalkForwardWindow],
    params: BacktestParams,
    config: BacktestConfig,
) -> FixedParamReport:
    results = []
    for window in windows:
        validation_data = _slice_data(hist_data, DateRange(window.train.start, window.validation.end))
        validation = _run_backtest(validation_data, strategy, params, config, window.validation)
        results.append(FixedWindowResult(window, validation.metrics))
    random_like = _fixed_results_to_random_report(results)
    return FixedParamReport(
        params=params,
        windows=results,
        profitable_windows=random_like.profitable_windows,
        avg_oos_sharpe=random_like.avg_oos_sharpe,
        avg_oos_return_pct=random_like.avg_oos_return_pct,
        avg_max_drawdown_pct=random_like.avg_max_drawdown_pct,
        total_windows=random_like.total_windows,
    )


def current_settings_to_params(settings: Dict) -> BacktestParams:
    defaults = asdict(BacktestParams())
    return BacktestParams(**{name: float(settings.get(name, value)) for name, value in defaults.items()})


def dict_to_params(values: Dict) -> BacktestParams:
    defaults = asdict(BacktestParams())
    return BacktestParams(**{name: float(values.get(name, value)) for name, value in defaults.items()})


def report_to_jsonable(report: ParamComparisonReport) -> Dict:
    return {
        "save_recommended": report.save_recommended,
        "reason": report.reason,
        "delta": report.delta,
        "current": _fixed_report_to_jsonable(report.current),
        "optimized": _fixed_report_to_jsonable(report.optimized),
    }


def _fixed_report_to_jsonable(report: FixedParamReport) -> Dict:
    return {
        "params": asdict(report.params),
        "profitable_windows": report.profitable_windows,
        "total_windows": report.total_windows,
        "avg_oos_sharpe": report.avg_oos_sharpe,
        "avg_oos_return_pct": report.avg_oos_return_pct,
        "avg_max_drawdown_pct": report.avg_max_drawdown_pct,
        "windows": [
            {
                "train": {
                    "start": item.window.train.start.isoformat(),
                    "end": item.window.train.end.isoformat(),
                },
                "validation": {
                    "start": item.window.validation.start.isoformat(),
                    "end": item.window.validation.end.isoformat(),
                },
                "metrics": item.validation_metrics,
            }
            for item in report.windows
        ],
    }


def _fixed_results_to_random_report(results):
    class _Validation:
        def __init__(self, metrics):
            self.metrics = metrics

    class _Result:
        def __init__(self, metrics):
            self.validation = _Validation(metrics)

    return _build_report([_Result(item.validation_metrics) for item in results], min_profitable_ratio=0.5)
