"""
Tests for apply_fill position logic.

Covers: new position, accumulate (weighted avg), partial reduce,
full close, direction flip.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import patch, MagicMock
from agentic_trading import TradingOrchestrator, PortfolioState, Position


# Must match the rate used in agentic_trading.apply_fill (src/agentic_trading.py:487).
FRICTION_RATE = 0.0005


def _friction(qty: int, price: float) -> float:
    return qty * price * FRICTION_RATE


# ---------------------------------------------------------------------------
# Auto-cleanup any patches started inside _make_orchestrator. Without this the
# patches inside `with patch(...)` would expire the moment the helper returned,
# letting subsequent apply_fill() calls hit the real trading.db file -- which
# silently inserted orphan rows until FK enforcement turned that into a hard
# IntegrityError.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _stop_all_patches():
    yield
    patch.stopall()


# ---------------------------------------------------------------------------
# Helper -- build a minimal orchestrator without DB / LLM
# ---------------------------------------------------------------------------

def _make_orchestrator(cash=100_000.0, positions=None):
    mock_db = patch("agentic_trading.db").start()
    patch("agentic_trading.ChatOpenAI").start()

    mock_db.load_user_settings.return_value = {}
    mock_db.get_alpaca_credentials.return_value = None
    mock_db.load_portfolio.return_value = {
        "cash": cash, "portfolio_value": cash, "total_trades": 0,
    }
    mock_db.load_positions.return_value = []
    mock_db.get_user.return_value = {"user_id": "test", "username": "test"}
    mock_db.record_trade.return_value = None
    mock_db.save_position.return_value = None

    orch = TradingOrchestrator(api_key=None, user_id="test", initial_capital=cash)

    # Inject positions if provided
    if positions:
        for pos in positions:
            orch.portfolio_state.positions[pos.symbol] = pos
    orch._mock_db = mock_db
    return orch


# ---------------------------------------------------------------------------
# New position
# ---------------------------------------------------------------------------

class TestNewPosition:
    def test_buy_creates_long(self):
        orch = _make_orchestrator()
        orch.apply_fill("AAPL", "BUY", 10, 150.0)

        pos = orch.portfolio_state.positions["AAPL"]
        assert pos.quantity == 10
        assert pos.entry_price == 150.0
        assert orch.portfolio_state.cash == pytest.approx(
            100_000 - 10 * 150 - _friction(10, 150.0)
        )

    def test_sell_creates_short(self):
        orch = _make_orchestrator()
        orch.apply_fill("AAPL", "SELL", 5, 200.0)

        pos = orch.portfolio_state.positions["AAPL"]
        assert pos.quantity == -5
        assert pos.entry_price == 200.0
        assert orch.portfolio_state.cash == pytest.approx(
            100_000 + 5 * 200 - _friction(5, 200.0)
        )


# ---------------------------------------------------------------------------
# Accumulate (same direction)
# ---------------------------------------------------------------------------

class TestAccumulate:
    def test_buy_adds_to_long_weighted_avg(self):
        existing = Position(symbol="AAPL", quantity=10, entry_price=100.0,
                            current_price=100.0, entry_time="t0")
        orch = _make_orchestrator(positions=[existing])

        orch.apply_fill("AAPL", "BUY", 10, 120.0)

        pos = orch.portfolio_state.positions["AAPL"]
        assert pos.quantity == 20
        # weighted avg: (10*100 + 10*120) / 20 = 110
        assert pos.entry_price == 110.0

    def test_sell_adds_to_short_weighted_avg(self):
        existing = Position(symbol="TSLA", quantity=-4, entry_price=200.0,
                            current_price=200.0, entry_time="t0")
        orch = _make_orchestrator(positions=[existing])

        orch.apply_fill("TSLA", "SELL", 6, 210.0)

        pos = orch.portfolio_state.positions["TSLA"]
        assert pos.quantity == -10
        # weighted avg: (4*200 + 6*210) / 10 = 206
        assert pos.entry_price == 206.0


# ---------------------------------------------------------------------------
# Partial reduce
# ---------------------------------------------------------------------------

class TestPartialReduce:
    def test_sell_reduces_long(self):
        existing = Position(symbol="AAPL", quantity=20, entry_price=100.0,
                            current_price=110.0, entry_time="t0")
        orch = _make_orchestrator(cash=80_000.0, positions=[existing])

        orch.apply_fill("AAPL", "SELL", 8, 115.0)

        pos = orch.portfolio_state.positions["AAPL"]
        assert pos.quantity == 12
        # entry price unchanged on partial reduce
        assert pos.entry_price == 100.0
        assert orch.portfolio_state.cash == pytest.approx(
            80_000 + 8 * 115 - _friction(8, 115.0)
        )

    def test_buy_reduces_short(self):
        existing = Position(symbol="NVDA", quantity=-10, entry_price=300.0,
                            current_price=290.0, entry_time="t0")
        orch = _make_orchestrator(positions=[existing])

        orch.apply_fill("NVDA", "BUY", 4, 295.0)

        pos = orch.portfolio_state.positions["NVDA"]
        assert pos.quantity == -6
        assert pos.entry_price == 300.0  # unchanged


# ---------------------------------------------------------------------------
# Full close
# ---------------------------------------------------------------------------

class TestFullClose:
    def test_sell_closes_long(self):
        existing = Position(symbol="AAPL", quantity=10, entry_price=100.0,
                            current_price=100.0, entry_time="t0")
        orch = _make_orchestrator(positions=[existing])

        orch.apply_fill("AAPL", "SELL", 10, 120.0)

        assert "AAPL" not in orch.portfolio_state.positions
        assert orch.portfolio_state.cash == pytest.approx(
            100_000 + 10 * 120 - _friction(10, 120.0)
        )

    def test_buy_closes_short(self):
        existing = Position(symbol="TSLA", quantity=-5, entry_price=200.0,
                            current_price=200.0, entry_time="t0")
        orch = _make_orchestrator(positions=[existing])

        orch.apply_fill("TSLA", "BUY", 5, 190.0)

        assert "TSLA" not in orch.portfolio_state.positions


# ---------------------------------------------------------------------------
# Direction flip
# ---------------------------------------------------------------------------

class TestDirectionFlip:
    def test_sell_more_than_held_flips_to_short(self):
        existing = Position(symbol="AAPL", quantity=10, entry_price=100.0,
                            current_price=100.0, entry_time="t0")
        orch = _make_orchestrator(positions=[existing])

        orch.apply_fill("AAPL", "SELL", 15, 120.0)

        pos = orch.portfolio_state.positions["AAPL"]
        assert pos.quantity == -5
        assert pos.entry_price == 120.0  # reset on flip

    def test_buy_more_than_shorted_flips_to_long(self):
        existing = Position(symbol="TSLA", quantity=-8, entry_price=200.0,
                            current_price=200.0, entry_time="t0")
        orch = _make_orchestrator(positions=[existing])

        orch.apply_fill("TSLA", "BUY", 12, 210.0)

        pos = orch.portfolio_state.positions["TSLA"]
        assert pos.quantity == 4
        assert pos.entry_price == 210.0  # reset on flip


# ---------------------------------------------------------------------------
# Trade counter
# ---------------------------------------------------------------------------

class TestTradeCounter:
    def test_total_trades_increments(self):
        orch = _make_orchestrator()
        assert orch.portfolio_state.total_trades == 0

        orch.apply_fill("A", "BUY", 1, 10.0)
        orch.apply_fill("B", "SELL", 1, 20.0)

        assert orch.portfolio_state.total_trades == 2
