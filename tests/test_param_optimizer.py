"""
Tests for parameter optimizer save-path behavior.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from types import SimpleNamespace
from unittest.mock import patch

import param_optimizer


@patch("param_optimizer.db")
@patch("param_optimizer.ChatOpenAI")
def test_optimize_params_saves_trailing_stop_fields(mock_llm, mock_db):
    mock_db.load_user_settings.return_value = {
        "strategy": "intraday",
        "risk_preference": "moderate",
    }
    mock_db.get_user_symbols.return_value = ["AAPL"]
    mock_db.get_trade_history.return_value = []
    mock_db.load_portfolio.return_value = {"portfolio_value": 100000, "cash": 100000}

    fake_chain = lambda _: SimpleNamespace(content="""{
        "risk_per_trade": 0.02,
        "max_concentration": 0.1,
        "stop_loss_multiplier": 2.0,
        "take_profit_pct": 0.05,
        "min_confidence": 0.3,
        "trailing_stop_high_profit": 0.11,
        "trailing_stop_low_profit": 0.05,
        "trailing_stop_cushion": 0.03,
        "trailing_stop_lock_pct": 0.02,
        "reasoning": "ok"
    }""")

    with patch.object(param_optimizer, "_gather_market_context", return_value={
        "avg_volatility": 0.02,
        "avg_sentiment": 0.0,
        "num_symbols": 1,
        "vol_regime": "MEDIUM",
        "sentiment_regime": "NEUTRAL",
    }), patch.object(param_optimizer, "_PARAM_PROMPT") as mock_prompt:
        mock_prompt.__or__.return_value.invoke.side_effect = fake_chain

        result = param_optimizer.optimize_params_for_user("u1", "key")

    assert result is not None
    _, kwargs = mock_db.save_user_settings.call_args
    assert kwargs["trailing_stop_high_profit"] == 0.11
    assert kwargs["trailing_stop_low_profit"] == 0.05
    assert kwargs["trailing_stop_cushion"] == 0.03
    assert kwargs["trailing_stop_lock_pct"] == 0.02
    assert kwargs["risk_preference"] == "moderate"
