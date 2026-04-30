"""Random-search baseline for walk-forward parameter evaluation."""

from dataclasses import asdict, dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Sequence

import numpy as np
import pandas as pd

from backtest import BacktestConfig, BacktestEngine, BacktestParams, BacktestResult
from backtest.strategy import CallableStrategy

from .window import DateRange, WalkForwardWindow, generate_walk_forward_windows


DEFAULT_SPACE = {
    "risk_per_trade": (0.005, 0.03),
    "max_concentration": (0.05, 0.20),
    "stop_loss_multiplier": (1.0, 4.0),
    "take_profit_pct": (0.02, 0.15),
    "min_confidence": (0.20, 0.70),
}


@dataclass(frozen=True)
class TrialResult:
    params: BacktestParams
    score: float
    metrics: Dict


@dataclass(frozen=True)
class WindowSearchResult:
    window: WalkForwardWindow
    best_train: TrialResult
    validation: BacktestResult


@dataclass(frozen=True)
class RandomSearchReport:
    windows: List[WindowSearchResult]
    profitable_windows: int
    avg_oos_sharpe: float
    avg_oos_return_pct: float
    avg_max_drawdown_pct: float
    total_windows: int
    decision: str
    reason: str

    def to_text(self) -> str:
        icon = "PROCEED" if self.decision == "proceed" else "STOP"
        return (
            "=== Random Search Baseline Report ===\n"
            f"Total windows: {self.total_windows}\n"
            f"Profitable windows: {self.profitable_windows} / {self.total_windows}\n"
            f"Avg out-of-sample Sharpe: {self.avg_oos_sharpe:.2f}\n"
            f"Avg OOS return: {self.avg_oos_return_pct:.2f}%\n"
            f"Avg max drawdown: {self.avg_max_drawdown_pct:.2f}%\n\n"
            f"{icon}: {self.reason}"
        )


def random_search(
    space: Mapping[str, Sequence[float]] | None,
    hist_data: Dict[str, pd.DataFrame],
    strategy: CallableStrategy,
    n_trials: int = 50,
    windows: Iterable[WalkForwardWindow] | None = None,
    seed: int = 42,
    config: BacktestConfig | None = None,
    objective_fn: Callable[[Dict], float] | None = None,
    min_profitable_ratio: float = 0.50,
) -> RandomSearchReport:
    """Run train-selected random search and report validation performance."""
    if n_trials <= 0:
        raise ValueError("n_trials must be positive")
    if not hist_data:
        raise ValueError("hist_data cannot be empty")

    resolved_space = space or DEFAULT_SPACE
    rng = np.random.default_rng(seed)
    search_windows = list(windows) if windows is not None else _windows_from_data(hist_data)
    objective = objective_fn or default_objective
    results: List[WindowSearchResult] = []

    for window in search_windows:
        train_data = _slice_data(hist_data, window.train)
        validation_data = _slice_data(
            hist_data,
            DateRange(window.train.start, window.validation.end),
        )
        trials = [
            _evaluate(
                train_data,
                strategy,
                _sample_params(resolved_space, rng),
                config,
                window.train,
                objective,
            )
            for _ in range(n_trials)
        ]
        best_train = max(trials, key=lambda trial: trial.score)
        validation = _run_backtest(
            validation_data,
            strategy,
            best_train.params,
            config,
            window.validation,
        )
        results.append(WindowSearchResult(window, best_train, validation))

    return _build_report(results, min_profitable_ratio)


def default_objective(metrics: Dict) -> float:
    total_return = float(metrics.get("total_return_pct", 0.0))
    drawdown = abs(float(metrics.get("max_drawdown_pct", 0.0)))
    sharpe = float(metrics.get("sharpe_ratio", 0.0))
    trades = int(metrics.get("total_trades", 0))
    trade_penalty = 5.0 if trades < 2 else 0.0
    return total_return + sharpe - (0.5 * drawdown) - trade_penalty


def _evaluate(
    data: Dict[str, pd.DataFrame],
    strategy: CallableStrategy,
    params: BacktestParams,
    config: BacktestConfig | None,
    date_range: DateRange,
    objective_fn: Callable[[Dict], float],
) -> TrialResult:
    result = _run_backtest(data, strategy, params, config, date_range)
    return TrialResult(params=params, score=objective_fn(result.metrics), metrics=result.metrics)


def _run_backtest(
    data: Dict[str, pd.DataFrame],
    strategy: CallableStrategy,
    params: BacktestParams,
    config: BacktestConfig | None,
    date_range: DateRange,
) -> BacktestResult:
    engine = BacktestEngine(data, strategy, params, config or BacktestConfig())
    return engine.run(start=date_range.start.isoformat(), end=date_range.end.isoformat())


def _sample_params(space: Mapping[str, Sequence[float]], rng: np.random.Generator) -> BacktestParams:
    values = {}
    for name, bounds in space.items():
        if len(bounds) == 2 and all(isinstance(item, (int, float)) for item in bounds):
            lo, hi = float(bounds[0]), float(bounds[1])
            values[name] = float(rng.uniform(lo, hi))
        else:
            values[name] = rng.choice(list(bounds)).item()
    allowed = {field: values[field] for field in asdict(BacktestParams()) if field in values}
    return BacktestParams(**allowed)


def _slice_data(hist_data: Dict[str, pd.DataFrame], date_range: DateRange) -> Dict[str, pd.DataFrame]:
    start = pd.Timestamp(date_range.start)
    end = pd.Timestamp(date_range.end)
    return {
        symbol: frame.loc[(frame.index >= start) & (frame.index <= end)].copy()
        for symbol, frame in hist_data.items()
    }


def _windows_from_data(hist_data: Dict[str, pd.DataFrame]) -> List[WalkForwardWindow]:
    starts = [pd.Timestamp(frame.index.min()).normalize() for frame in hist_data.values() if len(frame)]
    ends = [pd.Timestamp(frame.index.max()).normalize() for frame in hist_data.values() if len(frame)]
    if not starts or not ends:
        return []
    return generate_walk_forward_windows(min(starts), max(ends))


def _build_report(
    results: List[WindowSearchResult],
    min_profitable_ratio: float,
) -> RandomSearchReport:
    total = len(results)
    if total == 0:
        return RandomSearchReport([], 0, 0.0, 0.0, 0.0, 0, "stop", "No walk-forward windows available.")

    returns = [float(item.validation.metrics.get("total_return_pct", 0.0)) for item in results]
    sharpes = [float(item.validation.metrics.get("sharpe_ratio", 0.0)) for item in results]
    drawdowns = [float(item.validation.metrics.get("max_drawdown_pct", 0.0)) for item in results]
    profitable = sum(1 for value in returns if value > 0)
    avg_return = float(np.mean(returns))
    avg_sharpe = float(np.mean(sharpes))
    avg_drawdown = float(np.mean(drawdowns))
    ratio = profitable / total

    if ratio >= min_profitable_ratio and avg_return > 0 and avg_sharpe > 0:
        decision = "proceed"
        reason = "Marginal alpha detected; proceed to Bayesian A/B only if it improves OOS metrics."
    else:
        decision = "stop"
        reason = "Random search cannot find robust OOS profitability; revisit signal generation before Bayesian."

    return RandomSearchReport(
        windows=results,
        profitable_windows=profitable,
        avg_oos_sharpe=round(avg_sharpe, 4),
        avg_oos_return_pct=round(avg_return, 4),
        avg_max_drawdown_pct=round(avg_drawdown, 4),
        total_windows=total,
        decision=decision,
        reason=reason,
    )
