import importlib.util
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from backtest.strategy import CallableStrategy
from optimizer.bayesian import bayesian_search
from tests.optimizer.test_random_search import _config, _windows, always_buy, trending_ohlc


SKOPT_AVAILABLE = importlib.util.find_spec("skopt") is not None


def test_bayesian_search_rejects_invalid_trial_count():
    with pytest.raises(ValueError, match="n_trials"):
        bayesian_search({}, {"UP": trending_ohlc()}, CallableStrategy(always_buy), n_trials=0)


def test_bayesian_search_rejects_initial_points_above_trials():
    with pytest.raises(ValueError, match="n_initial_points"):
        bayesian_search(
            {},
            {"UP": trending_ohlc()},
            CallableStrategy(always_buy),
            n_trials=2,
            n_initial_points=3,
        )


@pytest.mark.skipif(SKOPT_AVAILABLE, reason="Only verifies missing dependency message")
def test_bayesian_search_reports_missing_dependency():
    with pytest.raises(ImportError, match="scikit-optimize"):
        bayesian_search(
            {"risk_per_trade": [0.02]},
            {"UP": trending_ohlc()},
            CallableStrategy(always_buy),
            n_trials=2,
            n_initial_points=1,
            windows=[_windows()[0]],
            config=_config(),
        )


@pytest.mark.skipif(not SKOPT_AVAILABLE, reason="scikit-optimize is not installed")
def test_bayesian_search_matches_random_search_report_contract():
    report = bayesian_search(
        {
            "risk_per_trade": (0.01, 0.02),
            "max_concentration": (0.40, 0.50),
            "stop_loss_multiplier": (1.0, 2.0),
            "take_profit_pct": (0.10, 0.20),
            "min_confidence": (0.2, 0.4),
        },
        {"UP": trending_ohlc(step=0.5)},
        CallableStrategy(always_buy),
        n_trials=10,
        n_initial_points=5,
        windows=[_windows()[0]],
        seed=5,
        config=_config(),
    )

    assert report.total_windows == 1
    assert report.windows[0].best_train.params.risk_per_trade >= 0.01
    assert report.windows[0].validation.metrics["total_trades"] > 0
    assert report.decision in {"stop", "proceed"}
