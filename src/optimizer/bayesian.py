"""Bayesian optimization search with the same contract as random_search."""

from typing import Callable, Dict, Iterable, Mapping, Sequence

import pandas as pd

from backtest import BacktestConfig, BacktestParams
from backtest.strategy import CallableStrategy

from .random_search import (
    DEFAULT_SPACE,
    RandomSearchReport,
    TrialResult,
    WindowSearchResult,
    _build_report,
    _run_backtest,
    _slice_data,
    _windows_from_data,
    default_objective,
)
from .window import DateRange, WalkForwardWindow


def bayesian_search(
    space: Mapping[str, Sequence[float]] | None,
    hist_data: Dict[str, pd.DataFrame],
    strategy: CallableStrategy,
    n_trials: int = 40,
    windows: Iterable[WalkForwardWindow] | None = None,
    seed: int = 42,
    config: BacktestConfig | None = None,
    objective_fn: Callable[[Dict], float] | None = None,
    min_profitable_ratio: float = 0.50,
    n_initial_points: int = 10,
) -> RandomSearchReport:
    """Run Bayesian train selection, then evaluate best params out of sample."""
    if n_trials <= 0:
        raise ValueError("n_trials must be positive")
    if n_initial_points <= 0:
        raise ValueError("n_initial_points must be positive")
    if n_initial_points > n_trials:
        raise ValueError("n_initial_points cannot exceed n_trials")
    if not hist_data:
        raise ValueError("hist_data cannot be empty")

    try:
        from skopt import gp_minimize
        from skopt.space import Categorical, Real
    except ImportError as exc:
        raise ImportError(
            "bayesian_search requires scikit-optimize. Install dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    resolved_space = space or DEFAULT_SPACE
    dimensions, names = _build_dimensions(resolved_space, Real, Categorical)
    search_windows = list(windows) if windows is not None else _windows_from_data(hist_data)
    objective = objective_fn or default_objective
    results: list[WindowSearchResult] = []

    for window_index, window in enumerate(search_windows):
        train_data = _slice_data(hist_data, window.train)
        validation_data = _slice_data(hist_data, DateRange(window.train.start, window.validation.end))
        evaluations: list[TrialResult] = []

        def minimize_objective(values):
            params = _params_from_values(names, values)
            result = _run_backtest(train_data, strategy, params, config, window.train)
            score = objective(result.metrics)
            evaluations.append(TrialResult(params=params, score=score, metrics=result.metrics))
            return -score

        gp_minimize(
            minimize_objective,
            dimensions,
            n_calls=n_trials,
            n_initial_points=n_initial_points,
            random_state=seed + window_index,
        )

        best_train = max(evaluations, key=lambda trial: trial.score)
        validation = _run_backtest(validation_data, strategy, best_train.params, config, window.validation)
        results.append(WindowSearchResult(window, best_train, validation))

    return _build_report(results, min_profitable_ratio)


def _build_dimensions(space, real_cls, categorical_cls):
    dimensions = []
    names = []
    for name, bounds in space.items():
        names.append(name)
        if len(bounds) == 2 and all(isinstance(item, (int, float)) for item in bounds):
            dimensions.append(real_cls(float(bounds[0]), float(bounds[1]), name=name))
        else:
            dimensions.append(categorical_cls(list(bounds), name=name))
    return dimensions, names


def _params_from_values(names, values) -> BacktestParams:
    raw = dict(zip(names, values))
    allowed = {
        "risk_per_trade": raw.get("risk_per_trade", BacktestParams().risk_per_trade),
        "max_concentration": raw.get("max_concentration", BacktestParams().max_concentration),
        "stop_loss_multiplier": raw.get("stop_loss_multiplier", BacktestParams().stop_loss_multiplier),
        "take_profit_pct": raw.get("take_profit_pct", BacktestParams().take_profit_pct),
        "min_confidence": raw.get("min_confidence", BacktestParams().min_confidence),
    }
    return BacktestParams(**allowed)
