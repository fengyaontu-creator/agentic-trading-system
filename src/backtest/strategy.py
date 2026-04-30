"""Strategy interface and lookahead-safe data access."""

from dataclasses import dataclass
from typing import Callable, Dict, Optional

import pandas as pd


class LookaheadError(ValueError):
    """Raised when a strategy asks for data after its as-of timestamp."""


@dataclass(frozen=True)
class Signal:
    symbol: str
    side: str
    confidence: float = 1.0
    reason: str = ""


class StrategyContext:
    def __init__(self, data: Dict[str, pd.DataFrame], as_of: pd.Timestamp):
        self._data = data
        self.as_of = pd.Timestamp(as_of).normalize()

    def history(self, symbol: str, end: Optional[pd.Timestamp] = None) -> pd.DataFrame:
        requested_end = self.as_of if end is None else pd.Timestamp(end).normalize()
        if requested_end > self.as_of:
            raise LookaheadError(
                f"Strategy requested {symbol} data through {requested_end.date()} "
                f"from as_of={self.as_of.date()}"
            )
        frame = self._data[symbol]
        return frame.loc[frame.index <= requested_end].copy()


class CallableStrategy:
    def __init__(self, func: Callable[[StrategyContext, str], Optional[Signal]]):
        self.func = func

    def generate_signal(self, context: StrategyContext, symbol: str) -> Optional[Signal]:
        return self.func(context, symbol)
