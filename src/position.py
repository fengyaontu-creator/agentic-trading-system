"""
position.py -- Shared fill logic for positions.

Both TradingOrchestrator (live) and Backtester (simulation) call
compute_fill() so there is exactly one set of rules for position updates.
"""

from typing import Tuple


def compute_fill(
    old_qty: int,
    old_entry: float,
    side: str,
    fill_qty: int,
    fill_price: float,
) -> Tuple[int, float, float, float]:
    """Pure position arithmetic for a single fill.

    Args:
        old_qty:    Current signed quantity (+ long, - short, 0 flat).
        old_entry:  Current average entry price (ignored when flat).
        side:       "BUY" or "SELL".
        fill_qty:   Unsigned fill quantity (> 0).
        fill_price: Execution price.

    Returns:
        (new_qty, new_entry, cash_delta, realized_pnl)
        cash_delta: positive = cash inflow, negative = cash outflow.
        realized_pnl: profit/loss on the closed portion (0 if opening/accumulating).
    """
    delta = fill_qty if side == "BUY" else -fill_qty
    cash_delta = -fill_qty * fill_price if side == "BUY" else fill_qty * fill_price
    new_qty = old_qty + delta

    # Realized PnL on the portion being closed (if any)
    realized_pnl = 0.0
    if old_qty != 0 and old_qty * delta < 0:
        closed_qty = min(abs(old_qty), fill_qty)
        realized_pnl = closed_qty * (fill_price - old_entry) * (1 if old_qty > 0 else -1)

    if new_qty == 0:
        return 0, 0.0, cash_delta, realized_pnl

    if old_qty == 0:
        return new_qty, fill_price, cash_delta, 0.0

    if old_qty * new_qty < 0:
        # Direction flip -- reset entry to fill price
        return new_qty, fill_price, cash_delta, realized_pnl

    if old_qty * delta > 0:
        # Accumulate same direction -- weighted average entry
        avg = (abs(old_qty) * old_entry + fill_qty * fill_price) / abs(new_qty)
        return new_qty, round(avg, 4), cash_delta, 0.0

    # Partial reduce -- keep original entry
    return new_qty, old_entry, cash_delta, realized_pnl
