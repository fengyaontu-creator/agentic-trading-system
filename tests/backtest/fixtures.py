import numpy as np
import pandas as pd


def ohlc(rows, start="2025-01-01"):
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    frame.index = pd.date_range(start, periods=len(frame), freq="D")
    return frame.copy()


def next_open_entry_ohlc():
    return ohlc([
        [100.0, 101.0, 99.0, 100.0],
        [110.0, 111.0, 109.0, 110.0],
        [112.0, 113.0, 111.0, 112.0],
    ])


def gap_down_ohlc():
    return ohlc([
        [100.0, 101.0, 99.0, 100.0],
        [90.0, 92.0, 88.0, 91.0],
    ])


def both_stop_and_take_hit_ohlc():
    return ohlc([
        [100.0, 101.0, 99.0, 100.0],
        [100.0, 106.0, 94.0, 101.0],
    ])


def slippage_ohlc():
    return ohlc([
        [100.0, 101.0, 99.0, 100.0],
        [100.0, 102.0, 99.0, 100.0],
        [100.0, 101.0, 99.0, 100.0],
    ])


def many_symbols_same_day_ohlc(symbol_count=5):
    return {
        f"S{i}": ohlc([
            [100.0, 101.0, 99.0, 100.0],
            [100.0, 101.0, 99.0, 100.0],
            [100.0, 101.0, 99.0, 100.0],
        ])
        for i in range(symbol_count)
    }


def concentration_ohlc():
    return ohlc([
        [100.0, 101.0, 99.0, 100.0],
        [100.0, 101.0, 99.0, 100.0],
    ])


def random_walk_ohlc(seed=7, n=10_000):
    rng = np.random.default_rng(seed)
    deltas = rng.normal(0.0, 0.25, size=n)
    close = 100 + np.cumsum(deltas)
    close = np.maximum(close, 1.0)
    open_ = np.r_[100.0, close[:-1]]
    spread = np.full(n, 0.01)
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    frame = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    }, index=pd.date_range("2000-01-01", periods=n, freq="D"))
    return frame.copy()
