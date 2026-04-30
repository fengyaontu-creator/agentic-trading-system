import os
import sys
from dataclasses import dataclass
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from backtest import BacktestParams
from optimizer.walk_forward import aggregate_params, apply_safety_guards, build_search_space, walk_forward_optimize


@dataclass
class FakeValidation:
    metrics: dict


@dataclass
class FakeBestTrain:
    params: BacktestParams


@dataclass
class FakeWindowResult:
    best_train: FakeBestTrain
    validation: FakeValidation


@dataclass
class FakeReport:
    windows: list


def test_build_search_space_uses_risk_preference_ranges():
    conservative = build_search_space("conservative")
    aggressive = build_search_space("aggressive")

    assert conservative["risk_per_trade"][1] < aggressive["risk_per_trade"][1]
    assert conservative["max_concentration"][1] < aggressive["max_concentration"][1]


def test_aggregate_params_uses_profitable_window_median():
    report = FakeReport(windows=[
        FakeWindowResult(
            FakeBestTrain(BacktestParams(risk_per_trade=0.01, max_concentration=0.05)),
            FakeValidation({"total_return_pct": -1.0}),
        ),
        FakeWindowResult(
            FakeBestTrain(BacktestParams(risk_per_trade=0.02, max_concentration=0.10)),
            FakeValidation({"total_return_pct": 1.0}),
        ),
        FakeWindowResult(
            FakeBestTrain(BacktestParams(risk_per_trade=0.03, max_concentration=0.20)),
            FakeValidation({"total_return_pct": 2.0}),
        ),
    ])

    params = aggregate_params(report)

    assert params["risk_per_trade"] == 0.025
    assert params["max_concentration"] == 0.15


def test_safety_guards_clamp_large_param_changes(monkeypatch):
    monkeypatch.setenv("NEW_OPTIMIZER_MAX_PARAM_CHANGE", "0.25")
    report = type("Report", (), {"avg_max_drawdown_pct": -2.0})()
    current = {
        "risk_per_trade": 0.02,
        "max_concentration": 0.10,
        "stop_loss_multiplier": 2.0,
        "take_profit_pct": 0.05,
        "min_confidence": 0.3,
    }
    proposed = {
        "risk_per_trade": 0.04,
        "max_concentration": 0.20,
        "stop_loss_multiplier": 3.5,
        "take_profit_pct": 0.12,
        "min_confidence": 0.1,
    }
    search_space = {
        "risk_per_trade": (0.005, 0.05),
        "max_concentration": (0.05, 0.20),
        "stop_loss_multiplier": (1.0, 4.0),
        "take_profit_pct": (0.02, 0.15),
        "min_confidence": (0.1, 0.7),
    }

    result = apply_safety_guards(current, proposed, search_space, report)

    assert result["allowed"] is True
    assert result["params"]["risk_per_trade"] == 0.025
    assert result["params"]["max_concentration"] == 0.125
    assert result["params"]["min_confidence"] == 0.225


def test_safety_guards_reject_excessive_drawdown(monkeypatch):
    monkeypatch.setenv("NEW_OPTIMIZER_MAX_DRAWDOWN_PCT", "10")
    report = type("Report", (), {"avg_max_drawdown_pct": -12.5})()

    result = apply_safety_guards({}, {"risk_per_trade": 0.02}, {}, report)

    assert result["allowed"] is False
    assert "drawdown" in result["reason"]


@patch("optimizer.walk_forward._write_watchlist_audit")
@patch("optimizer.walk_forward.random_search")
@patch("optimizer.walk_forward.db")
def test_walk_forward_skips_under_diversified_watchlist(mock_db, mock_random, mock_audit, monkeypatch):
    monkeypatch.setenv("NEW_OPTIMIZER_MIN_SYMBOLS", "3")
    mock_db.load_user_settings.return_value = {"risk_preference": "moderate", "strategy": "intraday"}
    mock_db.get_user_symbols.return_value = ["AAPL"]

    with patch("optimizer.walk_forward.load_local_histories", return_value={"AAPL": object()}):
        result = walk_forward_optimize("u1", n_trials=1)

    assert result is None
    mock_random.assert_not_called()
    mock_audit.assert_called_once()
    mock_db.set_param_optimization_status.assert_called_once()
    status_args = mock_db.set_param_optimization_status.call_args.args
    assert status_args[1] == "skipped"
    assert "need at least 3" in status_args[2]
