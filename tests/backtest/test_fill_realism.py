import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from backtest import BacktestConfig, BacktestEngine, BacktestParams
from backtest.engine import Position
from backtest.fills import FillConfig
from backtest.strategy import CallableStrategy, Signal

from .fixtures import both_stop_and_take_hit_ohlc, gap_down_ohlc, next_open_entry_ohlc, slippage_ohlc


def buy_once(context, symbol):
    if context.as_of.strftime("%Y-%m-%d") == "2025-01-01":
        return Signal(symbol, "BUY", 1.0, "buy once")
    return None


def buy_then_sell(context, symbol):
    day = context.as_of.strftime("%Y-%m-%d")
    if day == "2025-01-01":
        return Signal(symbol, "BUY", 1.0, "buy")
    if day == "2025-01-02":
        return Signal(symbol, "SELL", 1.0, "sell")
    return None


def _engine(data, strategy=buy_once, **config_overrides):
    config = BacktestConfig(
        initial_capital=10_000,
        warmup_bars=1,
        fill=FillConfig(slippage_bps=0, sec_fee_per_million=0, taf_per_share=0),
        **config_overrides,
    )
    params = BacktestParams(risk_per_trade=1.0, max_concentration=1.0, take_profit_pct=0.05)
    return BacktestEngine({"AAPL": data}, CallableStrategy(strategy), params, config)


def test_signal_on_t_fills_at_t_plus_one_open():
    engine = _engine(next_open_entry_ohlc())
    result = engine.run()

    assert result.trades[0]["date"] == "2025-01-02"
    assert result.trades[0]["side"] == "BUY"
    assert result.trades[0]["raw_price"] == 110.0


def test_gap_down_stop_fills_at_open_not_stop_price():
    engine = _engine(gap_down_ohlc())
    engine.positions["AAPL"] = Position("AAPL", 10, 100.0, stop_loss=95.0, take_profit=110.0)

    result = engine.run(start="2025-01-02", end="2025-01-02")

    assert result.trades[0]["reason"] == "stop_loss"
    assert result.trades[0]["raw_price"] == 90.0


def test_same_day_stop_and_take_uses_stop_first_by_default():
    engine = _engine(both_stop_and_take_hit_ohlc())
    engine.positions["AAPL"] = Position("AAPL", 10, 100.0, stop_loss=95.0, take_profit=105.0)

    result = engine.run(start="2025-01-02", end="2025-01-02")

    assert result.trades[0]["reason"] == "stop_loss"
    assert result.trades[0]["raw_price"] == 95.0


def test_slippage_applies_once_to_buys_and_sells():
    config = BacktestConfig(
        initial_capital=10_000,
        warmup_bars=1,
        fill=FillConfig(slippage_bps=5, sec_fee_per_million=0, taf_per_share=0),
    )
    params = BacktestParams(risk_per_trade=1.0, max_concentration=1.0, take_profit_pct=0.50)
    engine = BacktestEngine({"AAPL": slippage_ohlc()}, CallableStrategy(buy_then_sell), params, config)

    result = engine.run()
    buy, sell = result.trades[:2]

    assert math.isclose(buy["price"], buy["raw_price"] * 1.0005, rel_tol=0, abs_tol=1e-6)
    assert math.isclose(sell["price"], sell["raw_price"] * 0.9995, rel_tol=0, abs_tol=1e-6)


def test_cash_delta_is_components_not_magic_number():
    fill = FillConfig(slippage_bps=0, sec_fee_per_million=20.60, taf_per_share=0.000166)
    config = BacktestConfig(initial_capital=10_000, warmup_bars=1, fill=fill)
    params = BacktestParams(risk_per_trade=1.0, max_concentration=1.0, take_profit_pct=0.50)
    engine = BacktestEngine({"AAPL": slippage_ohlc()}, CallableStrategy(buy_then_sell), params, config)

    result = engine.run()
    buy, sell = result.trades[:2]
    expected_buy_delta = -(buy["quantity"] * buy["price"] + buy["fees"])
    expected_sell_delta = sell["quantity"] * sell["price"] - sell["fees"]
    expected_delta = expected_buy_delta + expected_sell_delta

    assert math.isclose(result.final_cash - 10_000, expected_delta, rel_tol=0, abs_tol=1e-6)
