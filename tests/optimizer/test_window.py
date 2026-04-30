import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from optimizer.window import generate_walk_forward_windows


def test_generates_strictly_causal_monthly_windows():
    windows = generate_walk_forward_windows("2025-01-01", "2025-09-30")

    assert len(windows) == 3
    assert windows[0].train.start.isoformat() == "2025-01-01"
    assert windows[0].train.end.isoformat() == "2025-06-30"
    assert windows[0].validation.start.isoformat() == "2025-07-01"
    assert windows[0].validation.end.isoformat() == "2025-07-31"


def test_train_and_validation_do_not_overlap():
    windows = generate_walk_forward_windows("2025-01-01", "2025-12-31")

    for window in windows:
        assert window.train.end < window.validation.start


def test_validation_is_always_after_training():
    windows = generate_walk_forward_windows("2025-01-15", "2025-10-14")

    for window in windows:
        assert window.validation.start > window.train.end
        assert window.validation.end > window.validation.start


def test_validation_windows_do_not_overlap_with_default_step():
    windows = generate_walk_forward_windows("2025-01-01", "2025-12-31")

    for previous, current in zip(windows, windows[1:]):
        assert previous.validation.end < current.validation.start


def test_custom_lengths_preserve_boundaries_without_off_by_one():
    windows = generate_walk_forward_windows(
        "2025-01-01",
        "2025-05-31",
        train_months=2,
        val_months=1,
        step_months=1,
    )

    assert windows[0].train.start.isoformat() == "2025-01-01"
    assert windows[0].train.end.isoformat() == "2025-02-28"
    assert windows[0].validation.start.isoformat() == "2025-03-01"
    assert windows[0].validation.end.isoformat() == "2025-03-31"
    assert windows[1].train.start.isoformat() == "2025-02-01"
    assert windows[1].train.end.isoformat() == "2025-03-31"
    assert windows[1].validation.start.isoformat() == "2025-04-01"
    assert windows[1].validation.end.isoformat() == "2025-04-30"


def test_insufficient_date_range_returns_empty_list():
    windows = generate_walk_forward_windows("2025-01-01", "2025-06-30")

    assert windows == []


def test_rejects_invalid_month_arguments():
    with pytest.raises(ValueError, match="train_months"):
        generate_walk_forward_windows("2025-01-01", "2025-12-31", train_months=0)
    with pytest.raises(ValueError, match="val_months"):
        generate_walk_forward_windows("2025-01-01", "2025-12-31", val_months=0)
    with pytest.raises(ValueError, match="step_months"):
        generate_walk_forward_windows("2025-01-01", "2025-12-31", step_months=0)


def test_rejects_end_before_start():
    with pytest.raises(ValueError, match="end_date"):
        generate_walk_forward_windows("2025-02-01", "2025-01-31")
