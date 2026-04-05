"""
Tests for shared position logic (compute_fill).

Covers the four critical scenarios:
    1. Accumulate (add to same direction)
    2. Partial reduce (trim existing position)
    3. Direction flip (overshoot close -> reverse)
    4. Full close (exact opposite fill)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from position import compute_fill


# ---------------------------------------------------------------------------
# New position from flat
# ---------------------------------------------------------------------------

class TestNewPosition:
    def test_buy_from_flat(self):
        new_qty, entry, cash, pnl = compute_fill(0, 0.0, "BUY", 10, 150.0)
        assert new_qty == 10
        assert entry == 150.0
        assert cash == -1500.0
        assert pnl == 0.0

    def test_sell_from_flat(self):
        new_qty, entry, cash, pnl = compute_fill(0, 0.0, "SELL", 5, 200.0)
        assert new_qty == -5
        assert entry == 200.0
        assert cash == 1000.0
        assert pnl == 0.0


# ---------------------------------------------------------------------------
# 1. Accumulate (same direction)
# ---------------------------------------------------------------------------

class TestAccumulate:
    def test_buy_adds_to_long(self):
        # Long 10 @ 100, buy 10 more @ 120 -> long 20 @ 110
        new_qty, entry, cash, pnl = compute_fill(10, 100.0, "BUY", 10, 120.0)
        assert new_qty == 20
        assert entry == 110.0
        assert cash == -1200.0
        assert pnl == 0.0

    def test_sell_adds_to_short(self):
        # Short 4 @ 200, sell 6 more @ 210 -> short 10 @ 206
        new_qty, entry, cash, pnl = compute_fill(-4, 200.0, "SELL", 6, 210.0)
        assert new_qty == -10
        assert entry == 206.0
        assert cash == 1260.0
        assert pnl == 0.0


# ---------------------------------------------------------------------------
# 2. Partial reduce
# ---------------------------------------------------------------------------

class TestPartialReduce:
    def test_sell_reduces_long(self):
        # Long 20 @ 100, sell 8 @ 115 -> long 12 @ 100 (entry unchanged)
        new_qty, entry, cash, pnl = compute_fill(20, 100.0, "SELL", 8, 115.0)
        assert new_qty == 12
        assert entry == 100.0
        assert cash == 920.0
        assert pnl == 8 * (115 - 100)  # 120 realized

    def test_buy_reduces_short(self):
        # Short 10 @ 300, buy 4 @ 295 -> short 6 @ 300 (entry unchanged)
        new_qty, entry, cash, pnl = compute_fill(-10, 300.0, "BUY", 4, 295.0)
        assert new_qty == -6
        assert entry == 300.0
        assert cash == -1180.0
        assert pnl == 4 * (300 - 295)  # 20 realized


# ---------------------------------------------------------------------------
# 3. Direction flip
# ---------------------------------------------------------------------------

class TestDirectionFlip:
    def test_sell_flips_long_to_short(self):
        # Long 10 @ 100, sell 15 @ 120 -> short 5 @ 120 (entry reset)
        new_qty, entry, cash, pnl = compute_fill(10, 100.0, "SELL", 15, 120.0)
        assert new_qty == -5
        assert entry == 120.0
        assert cash == 1800.0
        # PnL on the 10 closed shares
        assert pnl == 10 * (120 - 100)  # 200

    def test_buy_flips_short_to_long(self):
        # Short 8 @ 200, buy 12 @ 210 -> long 4 @ 210 (entry reset)
        new_qty, entry, cash, pnl = compute_fill(-8, 200.0, "BUY", 12, 210.0)
        assert new_qty == 4
        assert entry == 210.0
        assert cash == -2520.0
        # PnL on the 8 closed shares (loss: shorted at 200, covered at 210)
        assert pnl == 8 * (200 - 210)  # -80


# ---------------------------------------------------------------------------
# 4. Full close
# ---------------------------------------------------------------------------

class TestFullClose:
    def test_sell_closes_long(self):
        new_qty, entry, cash, pnl = compute_fill(10, 100.0, "SELL", 10, 120.0)
        assert new_qty == 0
        assert cash == 1200.0
        assert pnl == 10 * (120 - 100)  # 200

    def test_buy_closes_short(self):
        new_qty, entry, cash, pnl = compute_fill(-5, 200.0, "BUY", 5, 190.0)
        assert new_qty == 0
        assert cash == -950.0
        assert pnl == 5 * (200 - 190)  # 50


# ---------------------------------------------------------------------------
# Backtester uses same logic -- verify via Backtester.record_trade
# ---------------------------------------------------------------------------

class TestBacktesterUsesSharedLogic:
    def test_backtester_accumulate(self):
        from backtester import Backtester
        bt = Backtester(initial_capital=100_000)

        bt.record_trade("2025-01-02", "AAPL", "BUY", 10, 100.0)
        assert bt.positions["AAPL"]["quantity"] == 10
        assert bt.positions["AAPL"]["entry_price"] == 100.0

        bt.record_trade("2025-01-03", "AAPL", "BUY", 10, 120.0)
        assert bt.positions["AAPL"]["quantity"] == 20
        assert bt.positions["AAPL"]["entry_price"] == 110.0  # weighted avg

    def test_backtester_partial_sell(self):
        from backtester import Backtester
        bt = Backtester(initial_capital=100_000)

        bt.record_trade("2025-01-02", "AAPL", "BUY", 20, 100.0)
        trade = bt.record_trade("2025-01-03", "AAPL", "SELL", 8, 115.0)

        assert bt.positions["AAPL"]["quantity"] == 12
        assert bt.positions["AAPL"]["entry_price"] == 100.0  # unchanged
        assert trade["pnl"] == 8 * (115 - 100)

    def test_backtester_direction_flip(self):
        from backtester import Backtester
        bt = Backtester(initial_capital=100_000)

        bt.record_trade("2025-01-02", "AAPL", "BUY", 10, 100.0)
        trade = bt.record_trade("2025-01-03", "AAPL", "SELL", 15, 120.0)

        assert bt.positions["AAPL"]["quantity"] == -5
        assert bt.positions["AAPL"]["entry_price"] == 120.0
        assert trade["pnl"] == 10 * (120 - 100)
