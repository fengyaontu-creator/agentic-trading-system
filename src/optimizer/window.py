"""Walk-forward window generation.

This module only cuts train/validation ranges. It does not run strategies,
optimize parameters, or inspect market data.
"""

from dataclasses import dataclass
from datetime import date
from typing import List

import pandas as pd


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date


@dataclass(frozen=True)
class WalkForwardWindow:
    train: DateRange
    validation: DateRange


def generate_walk_forward_windows(
    start_date,
    end_date,
    train_months: int = 6,
    val_months: int = 1,
    step_months: int = 1,
) -> List[WalkForwardWindow]:
    """Return strictly causal walk-forward train/validation windows.

    Ranges are inclusive calendar-date ranges. Validation starts the day after
    training ends, and successive validation windows move forward by
    ``step_months``. If there is not enough room for one full train+validation
    pair, this returns an empty list.
    """
    if train_months <= 0:
        raise ValueError("train_months must be positive")
    if val_months <= 0:
        raise ValueError("val_months must be positive")
    if step_months <= 0:
        raise ValueError("step_months must be positive")

    start_ts = _normalize_date(start_date)
    end_ts = _normalize_date(end_date)
    if end_ts < start_ts:
        raise ValueError("end_date must be on or after start_date")

    windows: List[WalkForwardWindow] = []
    train_start = start_ts

    while True:
        train_end = train_start + pd.DateOffset(months=train_months) - pd.Timedelta(days=1)
        val_start = train_end + pd.Timedelta(days=1)
        val_end = val_start + pd.DateOffset(months=val_months) - pd.Timedelta(days=1)

        if val_end > end_ts:
            break

        windows.append(
            WalkForwardWindow(
                train=DateRange(train_start.date(), train_end.date()),
                validation=DateRange(val_start.date(), val_end.date()),
            )
        )
        train_start = train_start + pd.DateOffset(months=step_months)

    return windows


def _normalize_date(value) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("date value cannot be NaT")
    return timestamp.tz_localize(None).normalize()
