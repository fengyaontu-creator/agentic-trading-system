import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from backtest import BacktestConfig, BacktestEngine, BacktestParams
from backtest.fills import FillConfig
from backtest.strategy import CallableStrategy, LookaheadError, Signal

from .fixtures import next_open_entry_ohlc, random_walk_ohlc


def legal_history_strategy(context, symbol):
    history = context.history(symbol)
    assert history.index.max() <= context.as_of
    if context.as_of == pd.Timestamp("2025-01-01"):
        return Signal(symbol, "BUY", 1.0, "legal")
    return None


def leaky_strategy(context, symbol):
    context.history(symbol, end=context.as_of + pd.Timedelta(days=1))
    return None


def random_one_bar_strategy(seed=3):
    rng = __import__("numpy").random.default_rng(seed)
    open_side = {"RND": None}

    def _strategy(context, symbol):
        if open_side[symbol] == "BUY":
            open_side[symbol] = None
            return Signal(symbol, "SELL", 1.0, "random close long")
        if open_side[symbol] == "SELL":
            open_side[symbol] = None
            return Signal(symbol, "BUY", 1.0, "random close short")

        side = "BUY" if rng.random() < 0.5 else "SELL"
        open_side[symbol] = side
        return Signal(symbol, side, 1.0, "random one-bar")

    return _strategy


def test_strategy_context_only_exposes_history_through_as_of():
    config = BacktestConfig(
        initial_capital=10_000,
        warmup_bars=1,
        fill=FillConfig(slippage_bps=0, sec_fee_per_million=0, taf_per_share=0),
    )
    params = BacktestParams(risk_per_trade=1.0, max_concentration=1.0)
    engine = BacktestEngine({"AAPL": next_open_entry_ohlc()}, CallableStrategy(legal_history_strategy), params, config)

    result = engine.run()

    assert result.trades[0]["date"] == "2025-01-02"


def test_future_data_request_is_rejected():
    config = BacktestConfig(
        initial_capital=10_000,
        warmup_bars=1,
        fill=FillConfig(slippage_bps=0, sec_fee_per_million=0, taf_per_share=0),
    )
    engine = BacktestEngine(
        {"AAPL": next_open_entry_ohlc()},
        CallableStrategy(leaky_strategy),
        BacktestParams(),
        config,
    )

    with pytest.raises(LookaheadError):
        engine.run()


def test_random_walk_random_signals_do_not_create_alpha():
    config = BacktestConfig(
        initial_capital=100_000,
        warmup_bars=2,
        allow_shorts=True,
        fill=FillConfig(slippage_bps=0, sec_fee_per_million=0, taf_per_share=0),
    )
    params = BacktestParams(
        risk_per_trade=0.01,
        max_concentration=0.10,
        stop_loss_multiplier=4.0,
        take_profit_pct=0.50,
        min_confidence=0.0,
    )
    engine = BacktestEngine(
        {"RND": random_walk_ohlc()},
        CallableStrategy(random_one_bar_strategy()),
        params,
        config,
    )

    result = engine.run()

    assert abs(result.metrics["sharpe_ratio"]) <= 0.3
