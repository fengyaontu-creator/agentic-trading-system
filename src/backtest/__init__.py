"""Event-driven backtesting package used by optimizer workflows."""

from .engine import BacktestConfig, BacktestEngine, BacktestParams, BacktestResult
from .strategy import Signal, StrategyContext

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestParams",
    "BacktestResult",
    "Signal",
    "StrategyContext",
]
