"""
Broker Alpaca — Alpaca Order Execution (Person C)
"""

# TODO: Implement Alpaca broker integration
import os
import csv
from datetime import datetime
from dotenv import load_dotenv
from alpaca_trade_api import REST
from alpaca_trade_api.rest import APIError

# Load environment variables
load_dotenv()

class AlpacaBroker:
    """
    Alpaca Paper Trading Execution Module
    Handles: Account info, Position query, Market orders, Trade logging
    Outputs logs to outputs/execution_log.csv
    """
    def __init__(self):
        # --------------------------
        # Alpaca API INIT (LINE 19)
        # --------------------------
        self.api = REST(
            key_id=os.getenv("APCA_API_KEY_ID"),
            secret=os.getenv("APCA_API_SECRET_KEY"),
            base_url=os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")
        )
        self.log_path = "outputs/execution_log.csv"
        self._init_log_file()

    def _init_log_file(self):
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "symbol", "side", "qty", "order_id",
                    "status", "message", "price"
                ])

    def get_account_info(self):
        try:
            # --------------------------
            # Alpaca API CALL (LINE 36)
            # --------------------------
            account = self.api.get_account()
            return {
                "cash": float(account.cash),
                "equity": float(account.equity),
                "buying_power": float(account.buying_power),
                "status": account.status
            }
        except APIError as e:
            return {"error": f"Failed to fetch account info: {str(e)}"}

    def get_positions(self, symbol=None):
        try:
            if symbol:
                # --------------------------
                # Alpaca API CALL (LINE 48)
                # --------------------------
                return self.api.get_position(symbol)
            # --------------------------
            # Alpaca API CALL (LINE 50)
            # --------------------------
            return self.api.list_positions()
        except APIError as e:
            return {"error": f"Failed to fetch positions: {str(e)}"}

    def submit_market_order(self, symbol: str, qty: int, side: str = "buy"):
        try:
            if qty <= 0:
                return self._write_log(symbol, side, qty, "", "FAILED", "Invalid quantity (must be > 0)", 0)

            # --------------------------
            # Alpaca API CALL (LINE 60)
            # --------------------------
            order = self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type="market",
                time_in_force="gtc"
            )

            avg_price = float(order.filled_avg_price) if order.filled_avg_price else 0
            self._write_log(
                symbol=symbol, side=side, qty=qty, order_id=order.id,
                status=order.status, message="Paper order submitted successfully", price=avg_price
            )
            return f"✅ ORDER SUCCESS: {side.upper()} {qty} shares of {symbol} | Order ID: {order.id}"

        except APIError as e:
            error_msg = str(e)
            self._write_log(symbol, side, qty, "", "FAILED", error_msg, 0)
            return f"❌ ORDER FAILED: {error_msg}"

    def _write_log(self, symbol, side, qty, order_id, status, message, price):
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                symbol, side, qty, order_id, status, message, price
            ])
