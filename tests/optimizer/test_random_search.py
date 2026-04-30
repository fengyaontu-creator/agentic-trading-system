import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from backtest import BacktestConfig, BacktestParams
from backtest.fills import FillConfig
from backtest.strategy import CallableStrategy, Signal
from optimizer.random_search import random_search
from optimizer.window import DateRange, WalkForwardWindow


def trending_ohlc(start="2025-01-01", periods=90, step=0.25):
    base = 100 + step * pd.Series(range(periods), dtype=float)
    frame = pd.DataFrame({
        "open": base,
        "high": base + 0.5,
        "low": base,
        "close": base + 0.5,
    })
    frame.index = pd.date_range(start, periods=periods, freq="D")
    return frame.copy()


def declining_ohlc(start="2025-01-01", periods=90):
    return trending_ohlc(start=start, periods=periods, step=-0.25)


def buy_with_history(context, symbol):
    history = context.history(symbol)
    if len(history) >= 3:
        return Signal(symbol, "BUY", 1.0, "history-ready buy")
    return None


def always_buy(context, symbol):
    return Signal(symbol, "BUY", 1.0, "always buy")


def _config():
    return BacktestConfig(
        initial_capital=10_000,
        warmup_bars=1,
        fill=FillConfig(slippage_bps=0, sec_fee_per_million=0, taf_per_share=0),
    )


def _windows():
    return [
        WalkForwardWindow(
            train=DateRange(pd.Timestamp("2025-01-01").date(), pd.Timestamp("2025-01-31").date()),
            validation=DateRange(pd.Timestamp("2025-02-01").date(), pd.Timestamp("2025-02-28").date()),
        ),
        WalkForwardWindow(
            train=DateRange(pd.Timestamp("2025-02-01").date(), pd.Timestamp("2025-02-28").date()),
            validation=DateRange(pd.Timestamp("2025-03-01").date(), pd.Timestamp("2025-03-31").date()),
        ),
    ]


def test_random_search_returns_window_results_and_in_range_params():
    space = {
        "risk_per_trade": (0.01, 0.02),
        "max_concentration": (0.10, 0.15),
        "stop_loss_multiplier": (1.0, 2.0),
        "take_profit_pct": (0.03, 0.05),
        "min_confidence": (0.2, 0.4),
    }

    report = random_search(
        space,
        {"UP": trending_ohlc()},
        CallableStrategy(always_buy),
        n_trials=5,
        windows=_windows(),
        seed=1,
        config=_config(),
    )

    assert report.total_windows == 2
    for window in report.windows:
        params = window.best_train.params
        assert 0.01 <= params.risk_per_trade <= 0.02
        assert 0.10 <= params.max_concentration <= 0.15
        assert 1.0 <= params.stop_loss_multiplier <= 2.0
        assert 0.03 <= params.take_profit_pct <= 0.05
        assert 0.2 <= params.min_confidence <= 0.4


def test_random_search_proceeds_when_oos_windows_are_profitable():
    report = random_search(
        {"risk_per_trade": [0.02], "max_concentration": [0.5], "take_profit_pct": [0.20]},
        {"UP": trending_ohlc(step=0.5)},
        CallableStrategy(always_buy),
        n_trials=3,
        windows=_windows(),
        seed=2,
        config=_config(),
    )

    assert report.decision == "proceed"
    assert report.profitable_windows == report.total_windows
    assert "PROCEED" in report.to_text()


def test_random_search_stops_when_oos_windows_are_not_profitable():
    report = random_search(
        {"risk_per_trade": [0.02], "max_concentration": [0.5], "take_profit_pct": [0.20]},
        {"DOWN": declining_ohlc()},
        CallableStrategy(always_buy),
        n_trials=3,
        windows=_windows(),
        seed=3,
        config=_config(),
    )

    assert report.decision == "stop"
    assert report.profitable_windows == 0
    assert "STOP" in report.to_text()


def test_validation_can_use_train_history_without_seeing_future():
    report = random_search(
        {"risk_per_trade": [0.02], "max_concentration": [0.5], "take_profit_pct": [0.20]},
        {"UP": trending_ohlc()},
        CallableStrategy(buy_with_history),
        n_trials=2,
        windows=[_windows()[0]],
        seed=4,
        config=_config(),
    )

    validation_trades = report.windows[0].validation.trades
    assert validation_trades
    assert validation_trades[0]["date"] == "2025-02-02"


def test_random_search_rejects_invalid_trial_count():
    try:
        random_search({}, {"UP": trending_ohlc()}, CallableStrategy(always_buy), n_trials=0)
    except ValueError as exc:
        assert "n_trials" in str(exc)
    else:
        raise AssertionError("expected ValueError")
