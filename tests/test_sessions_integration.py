"""
Integration tests for the analyze -> trade -> close pipeline.

These exercise real SQLite persistence and real risk / execution logic.
Only the true external boundaries are mocked:
  * fetch_market_data       (yfinance + indicator wrapper)
  * get_market_sentiment    (NewsAPI + LLM wrapper)
  * alpaca_execute_trade    (broker POST)
  * reconcile_positions     (broker GET)
  * is_market_open          (datetime gate)
  * services.trading_sessions.datetime (so the close-session weekend check
    and the analyze/trade "today" key always line up on a fixed trading day)
"""

import datetime as _stdlib_datetime
import importlib
import json
import os
import sys
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

# --- Environment must be set before importing anything under src/ ------------
os.environ.setdefault("JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("DB_ENCRYPTION_KEY", "R1QqOX1D0r7e6T7x3t4w1L4RKe0K1cW8mWG4Pzv9hQ8=")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


ET = ZoneInfo("America/New_York")
# A Tuesday at 11:00 ET -- inside US regular session, not a weekend.
_FIXED_ET = _stdlib_datetime.datetime(2026, 4, 7, 11, 0, tzinfo=ET)
_FIXED_DATE_STR = "2026-04-07"


class _FrozenDatetime(_stdlib_datetime.datetime):
    """datetime stand-in whose .now() is pinned to a known trading day."""

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return _FIXED_ET.replace(tzinfo=None)
        return _FIXED_ET.astimezone(tz)


# -----------------------------------------------------------------------------
# Helpers for building mocked external-boundary payloads
# -----------------------------------------------------------------------------

def _market_data_json(price: float = 150.0, vol: float = 0.02, signal: str = "BUY") -> str:
    """Shape matches what data_tools.fetch_market_data.invoke() actually returns."""
    return json.dumps({
        "current_price": price,
        "volatility": vol,
        "ml_signal": {
            "signal": signal,
            "confidence_boost": 0.10,
            "score": 3 if signal == "BUY" else -3,
            "reasons": ["integration-test fixture"],
        },
        "indicators_summary": {
            "rsi": 25.0 if signal == "BUY" else 75.0,
            "macd": 0.5,
            "sma_20": price * 0.99,
            "sma_50": price * 0.98,
        },
    })


def _sentiment_json(score: float = 0.1) -> str:
    return json.dumps({"sentiment_score": score, "description": "integration-test sentiment"})


def _fake_alpaca_order(order_id: str, fill_price: float) -> dict:
    """Match broker_alpaca.execute_trade's return shape."""
    return {
        "main": {
            "order_id": order_id,
            "filled_avg_price": fill_price,
            "status": "filled",
        }
    }


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Swap database.DB_PATH to a temp file. get_conn() reads the global each
    call, so agentic_trading and services.trading_sessions (which both do
    `import database as db`) pick this up automatically."""
    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "integration.db"))
    database.init_db()
    return database


@pytest.fixture
def test_user(isolated_db):
    """Create a user with a watchlist, permissive settings, and Alpaca creds."""
    db = isolated_db
    uid = "alice"
    db.create_user(uid, "alice", "pw")
    db.set_user_symbols(uid, ["AAPL"])
    db.save_user_settings(
        uid,
        risk_per_trade=0.02,
        max_concentration=0.50,  # looser than the 0.10 default so the mocked BUY fits
        stop_loss_multiplier=2.0,
        take_profit_pct=0.05,
        min_confidence=0.3,
        trailing_stop_high_profit=0.10,
        trailing_stop_low_profit=0.05,
        trailing_stop_cushion=0.03,
        trailing_stop_lock_pct=0.02,
        strategy="intraday",
        risk_preference="moderate",
    )
    db.save_alpaca_credentials(uid, "test-key", "test-secret")
    return uid


# -----------------------------------------------------------------------------
# Full analyze -> trade -> close pipeline
# -----------------------------------------------------------------------------

def test_analyze_trade_close_full_pipeline(isolated_db, test_user):
    """End-to-end: analyze writes a signal, trade opens a position, close
    flattens it. All DB interactions are real; only external calls are mocked."""
    db = isolated_db
    uid = test_user

    # Import inside the test so these modules have the patched DB_PATH in
    # scope via `database as db` (same module object).
    import agentic_trading
    from services import trading_sessions

    with patch.object(trading_sessions, "datetime", _FrozenDatetime), \
         patch.object(trading_sessions, "is_market_open", return_value=True), \
         patch.object(trading_sessions, "reconcile_positions", return_value={"ok": True, "diffs": []}) as mock_recon, \
         patch.object(trading_sessions, "fetch_market_data") as mock_fmd_sessions, \
         patch.object(agentic_trading, "fetch_market_data") as mock_fmd_agentic, \
         patch.object(agentic_trading, "get_market_sentiment") as mock_sent, \
         patch.object(agentic_trading, "alpaca_execute_trade") as mock_exec:

        mock_fmd_sessions.invoke.return_value = _market_data_json(price=150.0, signal="BUY")
        mock_fmd_agentic.invoke.return_value = _market_data_json(price=150.0, signal="BUY")
        mock_sent.invoke.return_value = _sentiment_json(score=0.1)
        mock_exec.return_value = _fake_alpaca_order("order-open", 150.0)

        # ---------- ANALYZE ----------
        analyze_result = trading_sessions.analyze_for_user({"user_id": uid}, api_key=None)
        assert analyze_result["status"] == "ok"
        assert analyze_result["signals_saved"] == 1

        signals = db.get_signals(uid, date=_FIXED_DATE_STR)
        assert len(signals) == 1
        assert signals[0]["symbol"] == "AAPL"
        assert signals[0]["signal"] == "BUY"
        assert signals[0]["executed"] == 0
        assert signals[0]["sentiment_score"] == pytest.approx(0.1)

        # ---------- TRADE ----------
        trade_result = trading_sessions.trade_for_user({"user_id": uid}, api_key=None)
        assert trade_result["status"] == "ok"
        assert trade_result["trades"] == 1

        # Broker was invoked once with expected shape
        assert mock_exec.call_count == 1
        open_kwargs = mock_exec.call_args.kwargs
        assert open_kwargs["symbol"] == "AAPL"
        assert open_kwargs["side"] == "BUY"
        assert open_kwargs["quantity"] > 0
        assert open_kwargs["api_key"] == "test-key"
        assert open_kwargs["api_secret"] == "test-secret"

        # Position persisted to DB
        positions = db.load_positions(uid)
        assert len(positions) == 1
        assert positions[0]["symbol"] == "AAPL"
        opened_qty = positions[0]["quantity"]
        assert opened_qty > 0
        assert positions[0]["entry_price"] == pytest.approx(150.0)

        # Signal marked executed -> no longer pending
        assert db.get_pending_signals(uid, _FIXED_DATE_STR) == []

        # Trade row in history
        trades = db.get_trade_history(uid)
        assert len(trades) == 1
        assert trades[0]["side"] == "BUY"
        assert trades[0]["quantity"] == opened_qty

        # Reconcile ran once at the end of trade
        assert mock_recon.call_count == 1

        # Cash debited by trade value + friction
        portfolio = db.load_portfolio(uid)
        expected_cash = 100_000 - opened_qty * 150.0 - opened_qty * 150.0 * 0.0005
        assert portfolio["cash"] == pytest.approx(expected_cash)

        # ---------- CLOSE ----------
        mock_exec.reset_mock()
        mock_exec.return_value = _fake_alpaca_order("order-close", 152.0)
        mock_fmd_sessions.invoke.return_value = _market_data_json(price=152.0, signal="BUY")
        mock_fmd_agentic.invoke.return_value = _market_data_json(price=152.0, signal="BUY")

        close_result = trading_sessions.close_for_user({"user_id": uid}, api_key=None)
        assert close_result["status"] == "ok"
        assert close_result["trades"] == 1

        # Broker was called with opposite side
        assert mock_exec.call_count == 1
        close_kwargs = mock_exec.call_args.kwargs
        assert close_kwargs["symbol"] == "AAPL"
        assert close_kwargs["side"] == "SELL"
        assert close_kwargs["quantity"] == opened_qty

        # Position removed from DB (not just from memory)
        assert db.load_positions(uid) == [], \
            "Expected DB positions to be empty after full close"

        # Second trade row appended
        trades_after = db.get_trade_history(uid)
        assert len(trades_after) == 2
        # Most recent first
        assert trades_after[0]["side"] == "SELL"
        assert trades_after[0]["quantity"] == opened_qty


# -----------------------------------------------------------------------------
# close_for_user: swing users must not be flattened
# -----------------------------------------------------------------------------

def test_close_preserves_swing_user_positions(isolated_db, test_user):
    """A user on the 'swing' strategy must keep their positions across EOD."""
    db = isolated_db
    uid = test_user

    # Flip the user to swing and inject a position directly.
    db.save_user_settings(
        uid,
        risk_per_trade=0.02,
        max_concentration=0.50,
        stop_loss_multiplier=2.0,
        take_profit_pct=0.05,
        min_confidence=0.3,
        trailing_stop_high_profit=0.10,
        trailing_stop_low_profit=0.05,
        trailing_stop_cushion=0.03,
        trailing_stop_lock_pct=0.02,
        strategy="swing",
        risk_preference="moderate",
    )
    db.save_position(uid, "AAPL", 10, 150.0, 150.0, _FIXED_ET.isoformat())

    from services import trading_sessions
    with patch.object(trading_sessions, "datetime", _FrozenDatetime):
        result = trading_sessions.close_for_user({"user_id": uid}, api_key=None)

    assert result["status"] == "skipped"
    assert result["trades"] == 0
    assert "not 'intraday'" in result["reason"]
    assert len(db.load_positions(uid)) == 1  # untouched


# -----------------------------------------------------------------------------
# trade_for_user: missing credentials -> graceful skip
# -----------------------------------------------------------------------------

def test_trade_skips_user_without_credentials(isolated_db):
    """A user with no Alpaca credentials should be skipped, not errored."""
    db = isolated_db
    uid = "bob"
    db.create_user(uid, "bob", "pw")
    db.set_user_symbols(uid, ["TSLA"])
    db.save_signal(uid, "TSLA", _FIXED_DATE_STR, "BUY", 0.6,
                   reasoning="test", technical_score=0.5, sentiment_score=0.1)

    from services import trading_sessions
    with patch.object(trading_sessions, "datetime", _FrozenDatetime), \
         patch.object(trading_sessions, "is_market_open", return_value=True):
        result = trading_sessions.trade_for_user({"user_id": uid}, api_key=None)

    assert result["status"] == "skipped"
    assert result["reason"] == "no alpaca credentials"
    # Signal remains pending
    assert len(db.get_pending_signals(uid, _FIXED_DATE_STR)) == 1


# -----------------------------------------------------------------------------
# close_for_user uses a strict 'intraday' whitelist: any other value (legacy
# rows, typos, NULL) must NOT be flattened. Invalid enum values are rejected
# upstream by the API, so reaching this branch means a legacy row escaped
# validation -- safer to preserve the position than to silently flatten it.
# -----------------------------------------------------------------------------

def test_close_preserves_unknown_strategy_value(isolated_db, test_user):
    """Legacy / typo'd strategy values must skip EOD flatten (strict whitelist).
    Only an exact 'intraday' value should trigger close."""
    db = isolated_db
    uid = test_user

    # Simulate a legacy row with a bogus strategy string.
    db.save_user_settings(
        uid,
        risk_per_trade=0.02,
        max_concentration=0.50,
        stop_loss_multiplier=2.0,
        take_profit_pct=0.05,
        min_confidence=0.3,
        trailing_stop_high_profit=0.10,
        trailing_stop_low_profit=0.05,
        trailing_stop_cushion=0.03,
        trailing_stop_lock_pct=0.02,
        strategy="intradya",  # typo -- not in Literal enum, but a legacy row
        risk_preference="moderate",
    )
    db.save_position(uid, "AAPL", 5, 150.0, 150.0, _FIXED_ET.isoformat())

    import agentic_trading
    from services import trading_sessions

    with patch.object(trading_sessions, "datetime", _FrozenDatetime), \
         patch.object(agentic_trading, "alpaca_execute_trade") as mock_exec:

        result = trading_sessions.close_for_user({"user_id": uid}, api_key=None)

    assert result["status"] == "skipped"
    assert result["trades"] == 0
    assert "not 'intraday'" in result["reason"]
    # Broker must NOT have been called for an unrecognized strategy.
    assert mock_exec.call_count == 0
    # Position must remain untouched.
    positions = db.load_positions(uid)
    assert len(positions) == 1
    assert positions[0]["symbol"] == "AAPL"
    assert positions[0]["quantity"] == 5
