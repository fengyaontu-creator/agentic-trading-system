"""
Tests for scheduler close session -- strategy-aware EOD flatten.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import json
import pytest
from unittest.mock import patch, MagicMock

import scheduler
from services import trading_sessions


# ---------------------------------------------------------------------------
# close_for_user skips swing users
# ---------------------------------------------------------------------------

@patch("services.trading_sessions.db")
def test_close_skips_swing_user(mock_db):
    mock_db.load_user_settings.return_value = {"strategy": "swing"}
    result = trading_sessions.close_for_user({"user_id": "u1"}, "fake-key")
    assert result["trades"] == 0
    mock_db.load_positions.assert_not_called()


# ---------------------------------------------------------------------------
# close_for_user flattens intraday user
# ---------------------------------------------------------------------------

@patch("services.trading_sessions.TradingOrchestrator")
@patch("services.trading_sessions.fetch_market_data")
@patch("services.trading_sessions.db")
def test_close_flattens_intraday(mock_db, mock_fetch, mock_orch_cls):
    mock_db.load_user_settings.return_value = {"strategy": "intraday"}
    mock_db.get_alpaca_credentials.return_value = {"api_key": "k", "api_secret": "s"}
    mock_db.load_positions.return_value = [
        {"symbol": "AAPL", "quantity": 10},
        {"symbol": "TSLA", "quantity": -5},
    ]

    mock_fetch.invoke.return_value = json.dumps({"current_price": 150.0})

    mock_orch = MagicMock()
    mock_orch.execution_agent.execute_trade.return_value = {
        "order_id": "ord1", "filled_avg_price": 150.0,
    }
    mock_orch_cls.return_value = mock_orch

    result = trading_sessions.close_for_user({"user_id": "u1"}, "fake-key")

    assert result["trades"] == 2
    # AAPL long -> SELL, TSLA short -> BUY
    calls = mock_orch.execution_agent.execute_trade.call_args_list
    assert calls[0].kwargs["side"] == "SELL"
    assert calls[0].kwargs["quantity"] == 10
    assert calls[1].kwargs["side"] == "BUY"
    assert calls[1].kwargs["quantity"] == 5


# ---------------------------------------------------------------------------
# close_for_user skips if no credentials
# ---------------------------------------------------------------------------

@patch("services.trading_sessions.db")
def test_close_skips_no_creds(mock_db):
    mock_db.load_user_settings.return_value = {"strategy": "intraday"}
    mock_db.get_alpaca_credentials.return_value = None
    result = trading_sessions.close_for_user({"user_id": "u1"}, "fake-key")
    assert result["status"] == "skipped"


# ---------------------------------------------------------------------------
# trade_for_user skips when market is closed
# ---------------------------------------------------------------------------

@patch("services.trading_sessions.is_market_open", return_value=False)
@patch("services.trading_sessions.db")
def test_trade_skips_market_closed(mock_db, mock_mkt):
    result = trading_sessions.trade_for_user({"user_id": "u1"}, "fake-key")
    assert result["trades"] == 0
    mock_db.get_alpaca_credentials.assert_not_called()


@patch("scheduler.log")
@patch("scheduler._SESSION_FN", {"trade": MagicMock(return_value={"status": "ok"})})
@patch("scheduler.db")
@patch("scheduler.os.getenv", return_value=None)
def test_scheduler_trade_does_not_require_openrouter(mock_getenv, mock_db, mock_log):
    mock_db.list_users.return_value = [{"user_id": "u1"}]
    scheduler.run_all_users("trade", max_workers=1)
    mock_db.init_db.assert_called_once()
    mock_log.error.assert_not_called()


@patch("scheduler.optimize_all_users")
@patch("scheduler._SESSION_FN", {"analyze": MagicMock(return_value={"status": "ok"})})
@patch("scheduler.db")
@patch("scheduler.os.getenv", return_value="openrouter-key")
def test_scheduler_runs_optimizer_for_analyze(mock_getenv, mock_db, mock_opt):
    mock_db.list_users.return_value = [{"user_id": "u1"}]
    scheduler.run_all_users("analyze", max_workers=1)
    mock_opt.assert_called_once_with("openrouter-key")


@patch("scheduler.log")
@patch("scheduler._SESSION_FN", {"trade": MagicMock(side_effect=RuntimeError("boom"))})
@patch("scheduler.db")
@patch("scheduler.os.getenv", return_value=None)
def test_scheduler_collects_worker_errors(mock_getenv, mock_db, mock_log):
    mock_db.list_users.return_value = [{"user_id": "u1"}]
    scheduler.run_all_users("trade", max_workers=1)
    assert any("failed: boom" in str(call.args[0]) for call in mock_log.error.call_args_list)
