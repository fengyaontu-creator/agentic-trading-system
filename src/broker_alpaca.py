"""
broker_alpaca.py — Alpaca Paper Trading 接入
Owner: Person C

替换模板中 ExecutionAgent.execute_trade 里的模拟下单逻辑。
使用 Alpaca SDK 实现真实的 paper trading 下单、查询、管理。

Setup:
1. Register at https://app.alpaca.markets/signup
2. Get Paper Trading API Key and Secret from dashboard
3. Add to .env:
   ALPACA_API_KEY=PK...
   ALPACA_API_SECRET=...
"""

import os
import json
from datetime import datetime
from typing import Dict, Optional


# ============================================================================
# Alpaca 客户端初始化
# ============================================================================

def get_trading_client():
    """
    Initialize and return an Alpaca TradingClient for paper trading.

    Returns:
        TradingClient instance
    """
    # TODO: Implement Alpaca client initialization
    # -------------------------------------------------------
    # from alpaca.trading.client import TradingClient
    #
    # api_key = os.getenv("ALPACA_API_KEY")
    # secret_key = os.getenv("ALPACA_API_SECRET")
    #
    # if not api_key or not secret_key:
    #     raise ValueError("ALPACA_API_KEY and ALPACA_API_SECRET must be set in .env")
    #
    # client = TradingClient(api_key, secret_key, paper=True)
    # return client
    # -------------------------------------------------------

    print("[TODO] get_trading_client not yet implemented")
    return None


# ============================================================================
# 账户信息查询
# ============================================================================

def get_account_info() -> Dict:
    """
    Get current Alpaca paper trading account information.

    Returns:
        Dict with cash, portfolio_value, buying_power, etc.
    """
    # TODO: Implement account info query
    # -------------------------------------------------------
    # client = get_trading_client()
    # account = client.get_account()
    #
    # return {
    #     "cash": float(account.cash),
    #     "portfolio_value": float(account.portfolio_value),
    #     "buying_power": float(account.buying_power),
    #     "equity": float(account.equity),
    #     "currency": account.currency,
    #     "status": account.status.value,
    # }
    # -------------------------------------------------------

    print("[TODO] get_account_info not yet implemented")
    return {"cash": 100000, "portfolio_value": 100000, "status": "SIMULATED"}


def get_positions() -> list:
    """
    Get all current open positions.

    Returns:
        List of position dicts
    """
    # TODO: Implement positions query
    # -------------------------------------------------------
    # client = get_trading_client()
    # positions = client.get_all_positions()
    #
    # return [{
    #     "symbol": pos.symbol,
    #     "qty": float(pos.qty),
    #     "avg_entry_price": float(pos.avg_entry_price),
    #     "current_price": float(pos.current_price),
    #     "market_value": float(pos.market_value),
    #     "unrealized_pl": float(pos.unrealized_pl),
    #     "unrealized_plpc": float(pos.unrealized_plpc),
    # } for pos in positions]
    # -------------------------------------------------------

    print("[TODO] get_positions not yet implemented")
    return []


# ============================================================================
# 下单功能（核心）
# ============================================================================

def submit_market_order(symbol: str, qty: int, side: str) -> Dict:
    """
    Submit a market order via Alpaca.

    Args:
        symbol: Stock ticker (e.g., 'AAPL')
        qty: Number of shares
        side: 'BUY' or 'SELL'

    Returns:
        Dict with order details (order_id, status, filled_price, etc.)
    """
    # TODO: Implement market order
    # -------------------------------------------------------
    # from alpaca.trading.client import TradingClient
    # from alpaca.trading.requests import MarketOrderRequest
    # from alpaca.trading.enums import OrderSide, TimeInForce
    #
    # client = get_trading_client()
    #
    # order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
    #
    # order_data = MarketOrderRequest(
    #     symbol=symbol,
    #     qty=qty,
    #     side=order_side,
    #     time_in_force=TimeInForce.DAY
    # )
    #
    # order = client.submit_order(order_data)
    #
    # return {
    #     "order_id": str(order.id),
    #     "symbol": order.symbol,
    #     "side": order.side.value,
    #     "qty": float(order.qty),
    #     "type": order.type.value,
    #     "status": order.status.value,
    #     "submitted_at": str(order.submitted_at),
    #     "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
    # }
    # -------------------------------------------------------

    # Simulated fallback (remove once Alpaca is integrated)
    print(f"[SIMULATED] {side} {qty} shares of {symbol}")
    return {
        "order_id": f"SIM_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "type": "MARKET",
        "status": "FILLED_SIMULATED",
        "submitted_at": datetime.now().isoformat(),
        "filled_avg_price": None,
    }


def submit_limit_order(symbol: str, qty: int, side: str, limit_price: float) -> Dict:
    """
    Submit a limit order via Alpaca.

    Args:
        symbol: Stock ticker
        qty: Number of shares
        side: 'BUY' or 'SELL'
        limit_price: Limit price

    Returns:
        Dict with order details
    """
    # TODO: Implement limit order
    # -------------------------------------------------------
    # from alpaca.trading.requests import LimitOrderRequest
    # from alpaca.trading.enums import OrderSide, TimeInForce
    #
    # client = get_trading_client()
    # order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
    #
    # order_data = LimitOrderRequest(
    #     symbol=symbol,
    #     qty=qty,
    #     side=order_side,
    #     time_in_force=TimeInForce.DAY,
    #     limit_price=limit_price
    # )
    #
    # order = client.submit_order(order_data)
    # return { ... }  # same format as market order
    # -------------------------------------------------------

    print(f"[TODO] submit_limit_order not yet implemented")
    return {}


def submit_stop_order(symbol: str, qty: int, side: str, stop_price: float) -> Dict:
    """
    Submit a stop-loss order via Alpaca.

    Args:
        symbol: Stock ticker
        qty: Number of shares
        side: 'BUY' or 'SELL'
        stop_price: Stop trigger price

    Returns:
        Dict with order details
    """
    # TODO: Implement stop order
    # -------------------------------------------------------
    # from alpaca.trading.requests import StopOrderRequest
    # from alpaca.trading.enums import OrderSide, TimeInForce
    #
    # client = get_trading_client()
    # order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
    #
    # order_data = StopOrderRequest(
    #     symbol=symbol,
    #     qty=qty,
    #     side=order_side,
    #     time_in_force=TimeInForce.DAY,
    #     stop_price=stop_price
    # )
    #
    # order = client.submit_order(order_data)
    # return { ... }
    # -------------------------------------------------------

    print(f"[TODO] submit_stop_order not yet implemented")
    return {}


# ============================================================================
# 订单查询与管理
# ============================================================================

def get_order_status(order_id: str) -> Dict:
    """
    Check status of a specific order.

    Args:
        order_id: Alpaca order UUID

    Returns:
        Dict with order status details
    """
    # TODO: Implement order status check
    # -------------------------------------------------------
    # client = get_trading_client()
    # order = client.get_order_by_id(order_id)
    # return {
    #     "order_id": str(order.id),
    #     "status": order.status.value,
    #     "filled_qty": float(order.filled_qty) if order.filled_qty else 0,
    #     "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
    # }
    # -------------------------------------------------------

    print(f"[TODO] get_order_status not yet implemented")
    return {}


def cancel_order(order_id: str) -> bool:
    """
    Cancel a pending order.

    Args:
        order_id: Alpaca order UUID

    Returns:
        True if cancelled successfully
    """
    # TODO: Implement order cancellation
    # -------------------------------------------------------
    # client = get_trading_client()
    # client.cancel_order_by_id(order_id)
    # return True
    # -------------------------------------------------------

    print(f"[TODO] cancel_order not yet implemented")
    return False


# ============================================================================
# 封装：供 ExecutionAgent 调用的统一接口
# ============================================================================

def execute_trade(
    symbol: str,
    signal_type: str,
    quantity: int,
    price: float,
    strategy: str = "MARKET",
    stop_loss: float = None,
    take_profit: float = None
) -> Dict:
    """
    Unified trade execution interface for the ExecutionAgent.
    Replaces the simulated execute_trade in the template.

    Args:
        symbol: Stock ticker
        signal_type: 'BUY' or 'SELL'
        quantity: Number of shares
        price: Current market price (used for limit/stop reference)
        strategy: 'MARKET', 'LIMIT', or 'STOP'
        stop_loss: Optional stop-loss price
        take_profit: Optional take-profit price

    Returns:
        Dict with order details and any bracket orders
    """
    if quantity <= 0:
        return None

    orders = {}

    # Main order
    if strategy == "MARKET":
        orders['main'] = submit_market_order(symbol, quantity, signal_type)
    elif strategy == "LIMIT":
        orders['main'] = submit_limit_order(symbol, quantity, signal_type, price)
    elif strategy == "STOP":
        orders['main'] = submit_stop_order(symbol, quantity, signal_type, price)
    else:
        orders['main'] = submit_market_order(symbol, quantity, signal_type)

    # Optional: place stop-loss order after main fill
    if stop_loss and signal_type == "BUY":
        # TODO: Place a sell stop order at stop_loss price
        # orders['stop_loss'] = submit_stop_order(symbol, quantity, "SELL", stop_loss)
        pass

    # Optional: place take-profit order after main fill
    if take_profit and signal_type == "BUY":
        # TODO: Place a sell limit order at take_profit price
        # orders['take_profit'] = submit_limit_order(symbol, quantity, "SELL", take_profit)
        pass

    return orders


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    print("Testing Alpaca broker integration...")
    print("\nAccount info:", get_account_info())
    print("\nPositions:", get_positions())
    print("\nSimulated trade:", execute_trade("AAPL", "BUY", 10, 150.0))
