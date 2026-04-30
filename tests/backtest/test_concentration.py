import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from backtest import BacktestConfig, BacktestEngine, BacktestParams
from backtest.fills import FillConfig
from backtest.strategy import CallableStrategy, Signal

from .fixtures import concentration_ohlc


def buy_once(context, symbol):
    if context.as_of.strftime("%Y-%m-%d") == "2025-01-01":
        return Signal(symbol, "BUY", 1.0, "buy once")
    return None


def test_max_concentration_caps_position_size():
    config = BacktestConfig(
        initial_capital=10_000,
        warmup_bars=1,
        fill=FillConfig(slippage_bps=0, sec_fee_per_million=0, taf_per_share=0),
    )
    params = BacktestParams(risk_per_trade=1.0, max_concentration=0.10)
    engine = BacktestEngine({"AAPL": concentration_ohlc()}, CallableStrategy(buy_once), params, config)

    result = engine.run()

    assert result.trades[0]["quantity"] == 10
    assert result.trades[0]["quantity"] * result.trades[0]["price"] <= 1_000
