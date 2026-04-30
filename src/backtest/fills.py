"""Fill pricing and trading cost rules for the simulator."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FillConfig:
    slippage_bps: float = 5.0
    commission_pct: float = 0.0
    min_commission: float = 0.0
    sec_fee_per_million: float = 20.60
    taf_per_share: float = 0.000166
    taf_max: float = 8.30


def apply_slippage(price: float, side: str, config: FillConfig) -> float:
    slip = config.slippage_bps / 10_000
    if side == "BUY":
        return round(price * (1 + slip), 6)
    return round(price * (1 - slip), 6)


def calculate_fees(side: str, quantity: int, fill_price: float, config: FillConfig) -> float:
    notional = quantity * fill_price
    commission = max(config.min_commission, notional * config.commission_pct)
    regulatory = 0.0
    if side == "SELL":
        regulatory += notional * config.sec_fee_per_million / 1_000_000
        regulatory += min(quantity * config.taf_per_share, config.taf_max)
    return round(commission + regulatory, 6)


def exit_price_for_bar(
    quantity: int,
    stop_loss: float,
    take_profit: float,
    bar,
    intraday_priority: str = "stop_first",
) -> tuple[float | None, str | None]:
    open_price = float(bar["open"])
    high = float(bar["high"])
    low = float(bar["low"])

    if quantity > 0:
        stop_hit = open_price <= stop_loss or low <= stop_loss
        take_hit = open_price >= take_profit or high >= take_profit
        stop_price = open_price if open_price <= stop_loss else stop_loss
        take_price = open_price if open_price >= take_profit else take_profit
    else:
        stop_hit = open_price >= stop_loss or high >= stop_loss
        take_hit = open_price <= take_profit or low <= take_profit
        stop_price = open_price if open_price >= stop_loss else stop_loss
        take_price = open_price if open_price <= take_profit else take_profit

    if stop_hit and take_hit:
        if intraday_priority == "take_first":
            return take_price, "take_profit"
        return stop_price, "stop_loss"
    if stop_hit:
        return stop_price, "stop_loss"
    if take_hit:
        return take_price, "take_profit"
    return None, None
