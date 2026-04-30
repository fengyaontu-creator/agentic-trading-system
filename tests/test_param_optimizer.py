"""
Tests for parameter optimizer save-path behavior.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from types import SimpleNamespace
from unittest.mock import patch

import param_optimizer


@patch.dict(os.environ, {"USE_NEW_OPTIMIZER": "true"})
@patch("param_optimizer.ChatOpenAI")
def test_new_optimizer_success_skips_llm(mock_llm):
    with patch("optimizer.walk_forward.walk_forward_optimize", return_value={
        "risk_per_trade": 0.02,
        "max_concentration": 0.1,
        "stop_loss_multiplier": 2.0,
        "take_profit_pct": 0.05,
        "min_confidence": 0.3,
    }):
        result = param_optimizer.optimize_params_for_user("u1", "key")

    assert result["risk_per_trade"] == 0.02
    mock_llm.assert_not_called()


@patch.dict(os.environ, {
    "USE_NEW_OPTIMIZER": "true",
    "NEW_OPTIMIZER_DRY_RUN": "true",
})
@patch("param_optimizer.ChatOpenAI")
def test_new_optimizer_dry_run_result_skips_llm(mock_llm):
    with patch("optimizer.walk_forward.walk_forward_optimize", return_value={
        "risk_per_trade": 0.021,
    }):
        result = param_optimizer.optimize_params_for_user("u1", "key")

    assert result == {"risk_per_trade": 0.021}
    mock_llm.assert_not_called()


@patch.dict(os.environ, {
    "USE_NEW_OPTIMIZER": "true",
    "NEW_OPTIMIZER_FALLBACK_TO_LLM": "false",
})
@patch("param_optimizer.ChatOpenAI")
def test_new_optimizer_no_result_without_fallback_skips_llm(mock_llm):
    with patch("optimizer.walk_forward.walk_forward_optimize", return_value=None):
        result = param_optimizer.optimize_params_for_user("u1", "key")

    assert result is None
    mock_llm.assert_not_called()


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
    mock_llm.assert_called_once_with(
        model="anthropic/claude-sonnet-4-6",
        api_key="key",
        base_url="https://openrouter.ai/api/v1",
        temperature=0,
        max_tokens=1200,
    )
    _, kwargs = mock_db.save_user_settings.call_args
    assert kwargs["trailing_stop_high_profit"] == 0.11
    assert kwargs["trailing_stop_low_profit"] == 0.05
    assert kwargs["trailing_stop_cushion"] == 0.03
    assert kwargs["trailing_stop_lock_pct"] == 0.02
    assert kwargs["risk_preference"] == "moderate"


@patch("param_optimizer.db")
@patch("param_optimizer.ChatOpenAI")
def test_optimize_params_shortens_credit_failure_reason(mock_llm, mock_db):
    mock_db.load_user_settings.return_value = {
        "strategy": "intraday",
        "risk_preference": "moderate",
    }
    mock_db.get_user_symbols.return_value = ["AAPL"]
    mock_db.get_trade_history.return_value = []
    mock_db.load_portfolio.return_value = {"portfolio_value": 100000, "cash": 100000}

    with patch.object(param_optimizer, "_gather_market_context", return_value={
        "avg_volatility": 0.02,
        "avg_sentiment": 0.0,
        "num_symbols": 1,
        "vol_regime": "MEDIUM",
        "sentiment_regime": "NEUTRAL",
    }), patch.object(param_optimizer, "_PARAM_PROMPT") as mock_prompt:
        mock_prompt.__or__.return_value.invoke.side_effect = Exception(
            "Error code: 402 - {'error': {'message': 'This request requires more credits, "
            "or fewer max_tokens. You requested up to 65536 tokens, but can only afford 59175.'}}"
        )

        result = param_optimizer.optimize_params_for_user("u1", "key")

    assert result is None
    mock_db.set_param_optimization_status.assert_called_with(
        "u1",
        "failed",
        "OpenRouter 402: token budget exceeds current credits (65536 requested, 59175 available).",
    )
