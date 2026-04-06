"""
Alpaca paper-trading integration.

All functions require explicit api_key and api_secret.
No fallback to environment variables -- callers must pass
the current user's credentials from the database.
"""

import os
import sys
import logging
from typing import Dict, Optional

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


def get_trading_client(api_key: str, api_secret: str):
    """
    Initialize an Alpaca TradingClient for paper trading.

    Both api_key and api_secret are required -- this function
    never reads credentials from the environment.
    """
    from alpaca.trading.client import TradingClient

    if not api_key or not api_secret:
        raise ValueError("api_key and api_secret are required for Alpaca trading")
    return TradingClient(api_key, api_secret, paper=True)


def get_account_info(api_key: str, api_secret: str) -> Dict:
    """Return live paper-account information from Alpaca."""
    client = get_trading_client(api_key, api_secret)
    account = client.get_account()
    return {
        "id": str(account.id),
        "account_number": getattr(account, "account_number", None),
        "status": account.status.value if hasattr(account.status, "value") else str(account.status),
        "currency": account.currency,
        "cash": float(account.cash),
        "buying_power": float(account.buying_power),
        "equity": float(account.equity),
        "portfolio_value": float(account.portfolio_value),
        "pattern_day_trader": bool(getattr(account, "pattern_day_trader", False)),
        "trading_blocked": bool(getattr(account, "trading_blocked", False)),
    }


def get_positions(api_key: str, api_secret: str) -> list:
    """Return all open positions from the paper account."""
    client = get_trading_client(api_key, api_secret)
    positions = client.get_all_positions()
    return [
        {
            "symbol": position.symbol,
            "qty": float(position.qty),
            "side": position.side.value if hasattr(position.side, "value") else str(position.side),
            "avg_entry_price": float(position.avg_entry_price),
            "current_price": float(position.current_price),
            "market_value": float(position.market_value),
            "unrealized_pl": float(position.unrealized_pl),
            "unrealized_plpc": float(position.unrealized_plpc),
        }
        for position in positions
    ]


def normalize_order(order) -> Dict:
    """Convert an Alpaca order object to a simple dict."""
    return {
        "order_id": str(order.id),
        "client_order_id": getattr(order, "client_order_id", None),
        "symbol": order.symbol,
        "side": order.side.value if hasattr(order.side, "value") else str(order.side),
        "qty": float(order.qty) if order.qty is not None else None,
        "type": order.order_type.value if hasattr(order.order_type, "value") else str(order.order_type),
        "time_in_force": order.time_in_force.value if hasattr(order.time_in_force, "value") else str(order.time_in_force),
        "status": order.status.value if hasattr(order.status, "value") else str(order.status),
        "submitted_at": str(getattr(order, "submitted_at", "")),
        "filled_at": str(getattr(order, "filled_at", "")) if getattr(order, "filled_at", None) else None,
        "filled_qty": float(order.filled_qty) if getattr(order, "filled_qty", None) else 0.0,
        "filled_avg_price": float(order.filled_avg_price) if getattr(order, "filled_avg_price", None) else None,
    }


def submit_market_order(symbol: str, qty: int, side: str, api_key: str, api_secret: str) -> Dict:
    """Submit a real paper market order."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    try:
        client = get_trading_client(api_key, api_secret)
        order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
        order_request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(order_data=order_request)
        order_dict = normalize_order(order)
        log.info(f"[MARKET] {symbol} {side} x{qty} -> order_id={order_dict.get('order_id')}, status={order_dict.get('status')}")
        return order_dict
    except Exception as exc:
        log.error(f"[MARKET] {symbol} {side} x{qty} failed: {exc}", exc_info=True)
        raise


def submit_limit_order(symbol: str, qty: int, side: str, limit_price: float, api_key: str, api_secret: str) -> Dict:
    """Submit a real paper limit order."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest

    try:
        client = get_trading_client(api_key, api_secret)
        order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
        order_request = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            limit_price=limit_price,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(order_data=order_request)
        order_dict = normalize_order(order)
        log.info(f"[LIMIT] {symbol} {side} x{qty} @ {limit_price} -> order_id={order_dict.get('order_id')}, status={order_dict.get('status')}")
        return order_dict
    except Exception as exc:
        log.error(f"[LIMIT] {symbol} {side} x{qty} @ {limit_price} failed: {exc}", exc_info=True)
        raise


def submit_stop_order(symbol: str, qty: int, side: str, stop_price: float, api_key: str, api_secret: str) -> Dict:
    """Submit a real paper stop order."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import StopOrderRequest

    try:
        client = get_trading_client(api_key, api_secret)
        order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
        order_request = StopOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            stop_price=stop_price,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(order_data=order_request)
        order_dict = normalize_order(order)
        log.info(f"[STOP] {symbol} {side} x{qty} @ {stop_price} -> order_id={order_dict.get('order_id')}, status={order_dict.get('status')}")
        return order_dict
    except Exception as exc:
        log.error(f"[STOP] {symbol} {side} x{qty} @ {stop_price} failed: {exc}", exc_info=True)
        raise


def get_order_status(order_id: str, api_key: str, api_secret: str) -> Dict:
    """Fetch a specific order by ID."""
    client = get_trading_client(api_key, api_secret)
    order = client.get_order_by_id(order_id)
    return normalize_order(order)


def get_recent_orders(api_key: str, api_secret: str, limit: int = 5) -> list:
    """Return the most recent paper-trading orders."""
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    client = get_trading_client(api_key, api_secret)
    request = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit, nested=False)
    orders = client.get_orders(filter=request)
    return [normalize_order(order) for order in orders]


def cancel_order(order_id: str, api_key: str, api_secret: str) -> bool:
    """Cancel a pending order by ID."""
    client = get_trading_client(api_key, api_secret)
    client.cancel_order_by_id(order_id)
    return True


def execute_trade(
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    api_key: str,
    api_secret: str,
    strategy: str = "MARKET",
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
) -> Optional[Dict]:
    """
    Unified execution entrypoint for the orchestrator.

    api_key and api_secret are required -- no env fallback.
    """
    if not api_key or not api_secret:
        raise ValueError("api_key and api_secret are required to execute trades")
    if quantity <= 0:
        log.warning(f"[EXECUTE] {symbol} {side} x{quantity} -- invalid quantity, skipping")
        return None

    try:
        orders = {}
        if strategy == "LIMIT":
            orders["main"] = submit_limit_order(symbol, quantity, side, price, api_key, api_secret)
        elif strategy == "STOP":
            orders["main"] = submit_stop_order(symbol, quantity, side, price, api_key, api_secret)
        else:
            orders["main"] = submit_market_order(symbol, quantity, side, api_key, api_secret)

        # Set stop-loss and take-profit based on position direction
        if side.upper() == "BUY":
            if stop_loss:
                orders["stop_loss"] = submit_stop_order(symbol, quantity, "SELL", stop_loss, api_key, api_secret)
            if take_profit:
                orders["take_profit"] = submit_limit_order(symbol, quantity, "SELL", take_profit, api_key, api_secret)
        elif side.upper() == "SELL":
            # For SHORT positions: stop_loss triggers BUY (to cover), take_profit is BUY limit (to close)
            if stop_loss:
                orders["stop_loss"] = submit_stop_order(symbol, quantity, "BUY", stop_loss, api_key, api_secret)
            if take_profit:
                orders["take_profit"] = submit_limit_order(symbol, quantity, "BUY", take_profit, api_key, api_secret)

        log.info(f"[EXECUTE] {symbol} {side} x{quantity} ({strategy}) completed with {len(orders)} order(s)")
        return orders
    except Exception as exc:
        log.error(
            f"[EXECUTE] {symbol} {side} x{quantity} ({strategy}) failed: {exc} | "
            f"stop_loss={stop_loss}, take_profit={take_profit}",
            exc_info=True
        )
        return None


def reconcile_positions(user_id: str, api_key: str, api_secret: str) -> Dict:
    """Compare Alpaca positions with local DB and return discrepancies.

    Returns {"ok": bool, "diffs": [...]}.  Each diff is a dict with
    symbol, broker_qty, db_qty so the caller can decide how to resolve.
    """
    import database as db  # local import to avoid circular at module level

    try:
        broker_positions = get_positions(api_key, api_secret)
        broker_map = {p["symbol"]: int(p["qty"]) for p in broker_positions}

        db_positions = db.load_positions(user_id)
        db_map = {p["symbol"]: p["quantity"] for p in db_positions}

        all_symbols = set(broker_map) | set(db_map)
        diffs = []
        for sym in sorted(all_symbols):
            bq = broker_map.get(sym, 0)
            dq = db_map.get(sym, 0)
            if bq != dq:
                diffs.append({"symbol": sym, "broker_qty": bq, "db_qty": dq})

        result = {"ok": len(diffs) == 0, "diffs": diffs}
        if result["ok"]:
            log.info(f"[RECONCILE] {user_id} -- {len(broker_map)} positions in sync")
        else:
            log.warning(f"[RECONCILE] {user_id} -- {len(diffs)} position(s) out of sync: {diffs}")
        return result
    except Exception as exc:
        log.error(f"[RECONCILE] {user_id} failed: {exc}", exc_info=True)
        return {"ok": False, "diffs": [], "error": str(exc)}


if __name__ == "__main__":
    # CLI test -- reads from .env explicitly, never implicitly
    api_key = os.getenv("ALPACA_API_KEY")
    api_secret = os.getenv("ALPACA_API_SECRET")
    if not api_key or not api_secret:
        print("Set ALPACA_API_KEY and ALPACA_API_SECRET in .env to test")
        sys.exit(1)

    print("Testing Alpaca paper-trading integration...")
    print("\nAccount info:")
    print(get_account_info(api_key, api_secret))
    print("\nPositions:")
    print(get_positions(api_key, api_secret))
    print("\nRecent orders:")
    print(get_recent_orders(api_key, api_secret))

    if "--submit-test-order" in sys.argv:
        print("\nSubmitting test paper order: BUY 1 AAPL")
        print(execute_trade("AAPL", "BUY", 1, 0.0, api_key, api_secret, strategy="MARKET"))
