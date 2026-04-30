"""Order sizing and same-day multi-signal allocation rules."""

from dataclasses import dataclass
from typing import List


@dataclass
class OrderCandidate:
    symbol: str
    side: str
    confidence: float
    raw_price: float
    stop_loss: float
    take_profit: float
    max_quantity: int
    reason: str = ""


@dataclass
class PlannedOrder:
    symbol: str
    side: str
    quantity: int
    raw_price: float
    stop_loss: float
    take_profit: float
    reason: str = ""


def allocate_orders(
    candidates: List[OrderCandidate],
    available_cash: float,
    allocation_method: str = "confidence_weighted",
) -> List[PlannedOrder]:
    if not candidates:
        return []

    buy_candidates = [c for c in candidates if c.side == "BUY"]
    other_candidates = [c for c in candidates if c.side != "BUY"]
    planned: List[PlannedOrder] = []

    total_buy_cash = sum(c.max_quantity * c.raw_price for c in buy_candidates)
    if total_buy_cash <= available_cash:
        planned.extend(_candidate_to_order(c, c.max_quantity) for c in buy_candidates)
    else:
        if allocation_method == "equal_weight":
            weights = {c.symbol: 1.0 for c in buy_candidates}
        else:
            weights = {c.symbol: max(c.confidence, 0.0) for c in buy_candidates}
        total_weight = sum(weights.values()) or len(buy_candidates)

        ranked = sorted(buy_candidates, key=lambda c: (-c.confidence, c.symbol))
        spent = 0.0
        quantities = {}
        for candidate in ranked:
            weight = weights[candidate.symbol] or 1.0
            budget = available_cash * weight / total_weight
            quantity = min(candidate.max_quantity, int(budget / candidate.raw_price))
            if quantity > 0:
                quantities[candidate.symbol] = quantity
                spent += quantity * candidate.raw_price

        remaining_cash = available_cash - spent
        for candidate in ranked:
            current = quantities.get(candidate.symbol, 0)
            while current < candidate.max_quantity and remaining_cash >= candidate.raw_price:
                current += 1
                remaining_cash -= candidate.raw_price
            if current > 0:
                planned.append(_candidate_to_order(candidate, current))

    planned.extend(_candidate_to_order(c, c.max_quantity) for c in other_candidates if c.max_quantity > 0)
    return [order for order in planned if order.quantity > 0]


def _candidate_to_order(candidate: OrderCandidate, quantity: int) -> PlannedOrder:
    return PlannedOrder(
        symbol=candidate.symbol,
        side=candidate.side,
        quantity=quantity,
        raw_price=candidate.raw_price,
        stop_loss=candidate.stop_loss,
        take_profit=candidate.take_profit,
        reason=candidate.reason,
    )
