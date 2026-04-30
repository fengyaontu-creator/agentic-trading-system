"""Historical data loading helpers for optimizer backtests."""

from functools import lru_cache
from typing import Dict, Iterable

import pandas as pd

from data_tools import fetch_historical_data


@lru_cache(maxsize=128)
def load_symbol_history(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    return fetch_historical_data(symbol, period=period, interval=interval).copy()


def load_histories(symbols: Iterable[str], period: str = "1y", interval: str = "1d") -> Dict[str, pd.DataFrame]:
    return {symbol: load_symbol_history(symbol, period, interval).copy() for symbol in symbols}
