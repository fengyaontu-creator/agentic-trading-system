"""
Alpaca paper-trading integration.

This version does not provide a mock fallback. Valid paper-trading
credentials must be present in `.env` or the environment.
"""

import os
import sys
from typing import Dict, Optional

from dotenv import load_dotenv

load_dotenv()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} must be set for Alpaca paper trading")
    return value


def get_trading_client(api_key: str = None, secret_key: str = None):
    """
    Initialize an Alpaca TradingClient for paper trading.

    Accepts explicit credentials or falls back to environment variables.
    """
    from alpaca.trading.client import TradingClient

    api_key = api_key or require_env("ALPACA_API_KEY")
    secret_key = secret_key or require_env("ALPACA_API_SECRET")
    return TradingClient(api_key, secret_key, paper=True)


def get_account_info(api_key: str = None, secret_key: str = None) -> Dict:
    """Return live paper-account information from Alpaca."""
    client = get_trading_client(api_key, secret_key)
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


def get_positions(api_key: str = None, secret_key: str = None) -> list:
    """Return all open positions from the paper account."""
    client = get_trading_client(api_key, secret_key)
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


def submit_market_order(symbol: str, qty: int, side: str, api_key: str = None, secret_key: str = None) -> Dict:
    """Submit a real paper market order."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest

    client = get_trading_client(api_key, secret_key)
    order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
    order_request = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=order_side,
        time_in_force=TimeInForce.DAY,
    )
    order = client.submit_order(order_data=order_request)
    return normalize_order(order)


def submit_limit_order(symbol: str, qty: int, side: str, limit_price: float, api_key: str = None, secret_key: str = None) -> Dict:
    """Submit a real paper limit order."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import LimitOrderRequest

    client = get_trading_client(api_key, secret_key)
    order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
    order_request = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=order_side,
        limit_price=limit_price,
        time_in_force=TimeInForce.DAY,
    )
    order = client.submit_order(order_data=order_request)
    return normalize_order(order)


def submit_stop_order(symbol: str, qty: int, side: str, stop_price: float, api_key: str = None, secret_key: str = None) -> Dict:
    """Submit a real paper stop order."""
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import StopOrderRequest

    client = get_trading_client(api_key, secret_key)
    order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
    order_request = StopOrderRequest(
        symbol=symbol,
        qty=qty,
        side=order_side,
        stop_price=stop_price,
        time_in_force=TimeInForce.DAY,
    )
    order = client.submit_order(order_data=order_request)
    return normalize_order(order)


def get_order_status(order_id: str) -> Dict:
    """Fetch a specific order by ID."""
    client = get_trading_client()
    order = client.get_order_by_id(order_id)
    return normalize_order(order)


def get_recent_orders(limit: int = 5) -> list:
    """Return the most recent paper-trading orders."""
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    client = get_trading_client()
    request = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit, nested=False)
    orders = client.get_orders(filter=request)
    return [normalize_order(order) for order in orders]


def cancel_order(order_id: str) -> bool:
    """Cancel a pending order by ID."""
    client = get_trading_client()
    client.cancel_order_by_id(order_id)
    return True


def execute_trade(
    symbol: str,
    signal_type: str,
    quantity: int,
    price: float,
    strategy: str = "MARKET",
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    api_key: str = None,
    secret_key: str = None,
) -> Optional[Dict]:
    """
    Unified execution entrypoint for the orchestrator.
    Accepts optional user credentials; falls back to .env if not provided.
    """
    if quantity <= 0:
        return None

    orders = {}
    if strategy == "LIMIT":
        orders["main"] = submit_limit_order(symbol, quantity, signal_type, price, api_key, secret_key)
    elif strategy == "STOP":
        orders["main"] = submit_stop_order(symbol, quantity, signal_type, price, api_key, secret_key)
    else:
        orders["main"] = submit_market_order(symbol, quantity, signal_type, api_key, secret_key)

    if stop_loss and signal_type.upper() == "BUY":
        orders["stop_loss"] = submit_stop_order(symbol, quantity, "SELL", stop_loss, api_key, secret_key)
    if take_profit and signal_type.upper() == "BUY":
        orders["take_profit"] = submit_limit_order(symbol, quantity, "SELL", take_profit, api_key, secret_key)

    return orders


if __name__ == "__main__":
    print("Testing Alpaca paper-trading integration...")
    print("\nAccount info:")
    print(get_account_info())
    print("\nPositions:")
    print(get_positions())
    print("\nRecent orders:")
    print(get_recent_orders())

    # Safety: only place an order when explicitly requested from the terminal.
    if "--submit-test-order" in sys.argv:
        print("\nSubmitting test paper order: BUY 1 AAPL")
        print(execute_trade("AAPL", "BUY", 1, 0.0, strategy="MARKET"))
