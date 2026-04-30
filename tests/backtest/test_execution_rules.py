import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from backtest import BacktestConfig, BacktestEngine, BacktestParams
from backtest.fills import FillConfig
from backtest.strategy import CallableStrategy, Signal

from .fixtures import many_symbols_same_day_ohlc


def all_buy(context, symbol):
    if context.as_of.strftime("%Y-%m-%d") == "2025-01-01":
        confidence = 1.0 - int(symbol[1:]) * 0.1
        return Signal(symbol, "BUY", confidence, "same day buy")
    return None


def test_cash_shortfall_allocates_same_day_signals_by_rule():
    data = many_symbols_same_day_ohlc(5)
    config = BacktestConfig(
        initial_capital=250,
        warmup_bars=1,
        allocation_method="confidence_weighted",
        fill=FillConfig(slippage_bps=0, sec_fee_per_million=0, taf_per_share=0),
    )
    params = BacktestParams(risk_per_trade=1.0, max_concentration=1.0)
    engine = BacktestEngine(data, CallableStrategy(all_buy), params, config)

    result = engine.run()
    buys = [trade for trade in result.trades if trade["side"] == "BUY"]
    total_cost = sum(trade["quantity"] * trade["price"] + trade["fees"] for trade in buys)

    assert total_cost <= 250
    assert len(buys) < 5
    assert buys[0]["symbol"] == "S0"
