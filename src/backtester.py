"""
backtester.py — 回测框架 + 增强版风控
Owner: Person D

1. 历史回测引擎：用 yfinance 历史数据模拟多天交易
2. 绩效指标：Sharpe, Sortino, Max Drawdown, Win Rate, Profit Factor
3. 增强风控：VaR 计算、动态止损、集中度限制
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple


# ============================================================================
# 绩效指标计算
# ============================================================================

def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """
    Calculate annualized Sharpe Ratio.

    Args:
        returns: Series of daily returns
        risk_free_rate: Annual risk-free rate (default 2%)

    Returns:
        Annualized Sharpe Ratio
    """
    if returns.std() == 0:
        return 0.0

    daily_rf = risk_free_rate / 252
    excess_returns = returns - daily_rf
    return float(np.sqrt(252) * excess_returns.mean() / excess_returns.std())


def calculate_sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
    """
    Calculate annualized Sortino Ratio (only penalizes downside volatility).

    Args:
        returns: Series of daily returns
        risk_free_rate: Annual risk-free rate

    Returns:
        Annualized Sortino Ratio
    """
    daily_rf = risk_free_rate / 252
    excess_returns = returns - daily_rf
    downside = returns[returns < 0]

    if len(downside) == 0 or downside.std() == 0:
        return 0.0

    return float(np.sqrt(252) * excess_returns.mean() / downside.std())


def calculate_max_drawdown(portfolio_values: pd.Series) -> Tuple[float, str, str]:
    """
    Calculate maximum drawdown and the period it occurred.

    Args:
        portfolio_values: Series of portfolio values over time

    Returns:
        Tuple of (max_drawdown_pct, peak_date, trough_date)
    """
    cumulative_max = portfolio_values.cummax()
    drawdown = (portfolio_values - cumulative_max) / cumulative_max

    max_dd = float(drawdown.min())
    trough_idx = drawdown.idxmin()
    peak_idx = portfolio_values[:trough_idx].idxmax()

    return max_dd, str(peak_idx), str(trough_idx)


def calculate_win_rate(trades: List[Dict]) -> float:
    """
    Calculate the percentage of profitable trades.

    Args:
        trades: List of trade dicts, each with 'pnl' field

    Returns:
        Win rate as a float (0.0 to 1.0)
    """
    if not trades:
        return 0.0

    winners = sum(1 for t in trades if t.get('pnl', 0) > 0)
    return winners / len(trades)


def calculate_profit_factor(trades: List[Dict]) -> float:
    """
    Calculate Profit Factor = gross profit / gross loss.

    Args:
        trades: List of trade dicts with 'pnl' field

    Returns:
        Profit factor (> 1.0 is profitable)
    """
    gross_profit = sum(t['pnl'] for t in trades if t.get('pnl', 0) > 0)
    gross_loss = abs(sum(t['pnl'] for t in trades if t.get('pnl', 0) < 0))

    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0

    return gross_profit / gross_loss


def generate_performance_report(
    portfolio_values: pd.Series,
    trades: List[Dict],
    initial_capital: float
) -> Dict:
    """
    Generate a comprehensive performance report.

    Args:
        portfolio_values: Series of daily portfolio values
        trades: List of all executed trades
        initial_capital: Starting capital

    Returns:
        Dict with all performance metrics
    """
    returns = portfolio_values.pct_change().dropna()
    final_value = float(portfolio_values.iloc[-1])
    total_return = (final_value - initial_capital) / initial_capital

    max_dd, peak_date, trough_date = calculate_max_drawdown(portfolio_values)

    return {
        "initial_capital": initial_capital,
        "final_value": round(final_value, 2),
        "total_return_pct": round(total_return * 100, 2),
        "total_return_dollar": round(final_value - initial_capital, 2),
        "sharpe_ratio": round(calculate_sharpe_ratio(returns), 4),
        "sortino_ratio": round(calculate_sortino_ratio(returns), 4),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "max_drawdown_peak": peak_date,
        "max_drawdown_trough": trough_date,
        "total_trades": len(trades),
        "win_rate": round(calculate_win_rate(trades) * 100, 2),
        "profit_factor": round(calculate_profit_factor(trades), 4),
        "avg_daily_return": round(float(returns.mean()) * 100, 4),
        "daily_volatility": round(float(returns.std()) * 100, 4),
    }


# ============================================================================
# 增强版风控
# ============================================================================

def calculate_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """
    Calculate Value at Risk using historical simulation.

    Args:
        returns: Series of historical returns
        confidence: Confidence level (default 95%)

    Returns:
        VaR as a negative percentage (e.g., -0.025 means 2.5% loss)
    """
    if len(returns) == 0:
        return 0.0

    return float(np.percentile(returns, (1 - confidence) * 100))


def calculate_dynamic_stop_loss(
    current_price: float,
    volatility: float,
    atr: float = None,
    multiplier: float = 2.0
) -> float:
    """
    Calculate dynamic stop-loss based on volatility.

    Uses ATR (Average True Range) if available, otherwise
    falls back to volatility-based calculation.

    Args:
        current_price: Current stock price
        volatility: Historical volatility (daily std of returns)
        atr: Average True Range (optional, preferred)
        multiplier: How many ATR/vol units below price

    Returns:
        Suggested stop-loss price
    """
    if atr:
        stop_distance = atr * multiplier
    else:
        stop_distance = current_price * volatility * multiplier

    return round(current_price - stop_distance, 2)


def check_concentration_limit(
    portfolio_positions: Dict,
    portfolio_value: float,
    symbol: str,
    proposed_value: float,
    max_concentration: float = 0.10
) -> Dict:
    """
    Check if a proposed trade would exceed concentration limits.

    Args:
        portfolio_positions: Current positions {symbol: position_value}
        portfolio_value: Total portfolio value
        symbol: Symbol to trade
        proposed_value: Dollar value of proposed trade
        max_concentration: Max allocation per position (default 10%)

    Returns:
        Dict with allowed (bool), current_pct, proposed_pct, max_pct
    """
    current_value = portfolio_positions.get(symbol, 0)
    new_value = current_value + proposed_value
    proposed_pct = new_value / portfolio_value if portfolio_value > 0 else 0

    return {
        "allowed": proposed_pct <= max_concentration,
        "current_pct": round(current_value / portfolio_value * 100, 2) if portfolio_value > 0 else 0,
        "proposed_pct": round(proposed_pct * 100, 2),
        "max_pct": max_concentration * 100,
        "reason": f"{'Within' if proposed_pct <= max_concentration else 'Exceeds'} "
                  f"{max_concentration*100:.0f}% concentration limit"
    }


def enhanced_risk_assessment(
    signal: Dict,
    portfolio_value: float,
    cash: float,
    current_price: float,
    returns_history: pd.Series,
    volatility: float,
    existing_positions: Dict = None,
) -> Dict:
    """
    Enhanced risk assessment combining VaR, dynamic stops, and concentration checks.
    This can supplement the LLM-based RiskManagementAgent.

    Args:
        signal: Trading signal dict from technical/sentiment analysis
        portfolio_value: Current portfolio value
        cash: Available cash
        current_price: Current stock price
        returns_history: Historical returns for VaR calculation
        volatility: Historical volatility
        existing_positions: Current position values by symbol

    Returns:
        Dict with comprehensive risk metrics and recommendation
    """
    existing_positions = existing_positions or {}
    symbol = signal.get('symbol', 'UNKNOWN')
    confidence = signal.get('confidence', 0.0)

    # VaR
    var_95 = calculate_var(returns_history, 0.95)
    var_99 = calculate_var(returns_history, 0.99)

    # Dynamic stop-loss
    stop_loss = calculate_dynamic_stop_loss(current_price, volatility)

    # Position sizing: risk max 2% of portfolio per trade
    max_risk_dollar = portfolio_value * 0.02
    risk_per_share = current_price - stop_loss
    if risk_per_share > 0:
        max_shares = int(max_risk_dollar / risk_per_share)
    else:
        max_shares = 0

    # Adjust by signal confidence
    suggested_shares = int(max_shares * confidence)

    # Concentration check
    proposed_value = suggested_shares * current_price
    concentration = check_concentration_limit(
        existing_positions, portfolio_value, symbol, proposed_value
    )

    # Final decision
    should_trade = (
        concentration['allowed']
        and suggested_shares > 0
        and proposed_value <= cash
        and confidence >= 0.3
    )

    risk_level = "LOW" if volatility < 0.015 else "MEDIUM" if volatility < 0.03 else "HIGH"

    return {
        "position_size": suggested_shares if should_trade else 0,
        "risk_assessment": risk_level,
        "should_trade": should_trade,
        "stop_loss": stop_loss,
        "take_profit": round(current_price * 1.05, 2),  # 5% target
        "var_95": round(var_95 * 100, 4),
        "var_99": round(var_99 * 100, 4),
        "max_risk_per_trade": round(max_risk_dollar, 2),
        "concentration_check": concentration,
        "reasoning": f"VaR(95%)={var_95*100:.2f}%, volatility={volatility*100:.2f}%, "
                     f"risk_level={risk_level}, concentration={'OK' if concentration['allowed'] else 'EXCEEDED'}"
    }


# ============================================================================
# 回测引擎
# ============================================================================

class Backtester:
    """
    Simple backtesting engine that simulates running the agent pipeline
    over historical data.

    Usage:
        bt = Backtester(initial_capital=100000)
        # For each historical day, call bt.record_trade(...) and bt.update_value(...)
        report = bt.get_report()
    """

    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions = {}       # {symbol: {"qty": int, "entry_price": float}}
        self.trades = []          # list of trade records
        self.portfolio_history = []  # list of (date, value)

    def record_trade(self, date: str, symbol: str, side: str, qty: int,
                     price: float) -> Dict:
        """Record a trade execution."""
        trade = {
            "date": date,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "value": qty * price,
            "pnl": 0.0  # calculated on close
        }

        if side == "BUY":
            self.cash -= qty * price
            if symbol in self.positions:
                # Average up
                pos = self.positions[symbol]
                total_qty = pos["qty"] + qty
                avg_price = (pos["qty"] * pos["entry_price"] + qty * price) / total_qty
                self.positions[symbol] = {"qty": total_qty, "entry_price": avg_price}
            else:
                self.positions[symbol] = {"qty": qty, "entry_price": price}

        elif side == "SELL":
            if symbol in self.positions:
                pos = self.positions[symbol]
                pnl = (price - pos["entry_price"]) * qty
                trade["pnl"] = pnl
                self.cash += qty * price

                remaining = pos["qty"] - qty
                if remaining <= 0:
                    del self.positions[symbol]
                else:
                    self.positions[symbol]["qty"] = remaining

        self.trades.append(trade)
        return trade

    def update_portfolio_value(self, date: str, current_prices: Dict[str, float]):
        """
        Update and record portfolio value for a given date.

        Args:
            date: Date string
            current_prices: {symbol: price} for all held positions
        """
        positions_value = sum(
            pos["qty"] * current_prices.get(symbol, pos["entry_price"])
            for symbol, pos in self.positions.items()
        )
        total_value = self.cash + positions_value
        self.portfolio_history.append({"date": date, "value": total_value})

    def get_portfolio_series(self) -> pd.Series:
        """Get portfolio value as a pandas Series."""
        if not self.portfolio_history:
            return pd.Series([self.initial_capital])

        df = pd.DataFrame(self.portfolio_history)
        return df.set_index('date')['value']

    def get_report(self) -> Dict:
        """Generate performance report."""
        portfolio_values = self.get_portfolio_series()
        return generate_performance_report(
            portfolio_values, self.trades, self.initial_capital
        )

    def export_trades(self, filepath: str = "outputs/execution_log.csv"):
        """Export trade log to CSV."""
        if self.trades:
            df = pd.DataFrame(self.trades)
            df.to_csv(filepath, index=False)
            print(f"Trades exported to {filepath}")

    def export_portfolio_history(self, filepath: str = "outputs/portfolio_history.csv"):
        """Export portfolio value history to CSV."""
        if self.portfolio_history:
            df = pd.DataFrame(self.portfolio_history)
            df.to_csv(filepath, index=False)
            print(f"Portfolio history exported to {filepath}")


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    print("Testing backtester...")

    bt = Backtester(initial_capital=100000)

    # Simulate some trades
    bt.record_trade("2025-01-02", "AAPL", "BUY", 50, 195.0)
    bt.update_portfolio_value("2025-01-02", {"AAPL": 195.0})

    bt.update_portfolio_value("2025-01-03", {"AAPL": 198.0})
    bt.update_portfolio_value("2025-01-06", {"AAPL": 196.5})

    bt.record_trade("2025-01-07", "AAPL", "SELL", 50, 200.0)
    bt.update_portfolio_value("2025-01-07", {"AAPL": 200.0})

    report = bt.get_report()
    print(json.dumps(report, indent=2))
