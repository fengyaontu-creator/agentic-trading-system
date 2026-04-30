"""Performance metrics for simulation backtests."""

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


def calculate_sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    if returns.std() == 0:
        return 0.0
    daily_rf = risk_free_rate / 252
    excess_returns = returns - daily_rf
    return float(np.sqrt(252) * excess_returns.mean() / excess_returns.std())


def calculate_sortino_ratio(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    daily_rf = risk_free_rate / 252
    excess_returns = returns - daily_rf
    downside = returns[returns < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0.0
    return float(np.sqrt(252) * excess_returns.mean() / downside.std())


def calculate_max_drawdown(portfolio_values: pd.Series) -> Tuple[float, str, str]:
    cumulative_max = portfolio_values.cummax()
    drawdown = (portfolio_values - cumulative_max) / cumulative_max
    max_dd = float(drawdown.min())
    trough_idx = drawdown.idxmin()
    peak_idx = portfolio_values[:trough_idx].idxmax()
    return max_dd, str(peak_idx), str(trough_idx)


def calculate_win_rate(trades: List[Dict]) -> float:
    if not trades:
        return 0.0
    winners = sum(1 for trade in trades if trade.get("pnl", 0) > 0)
    return winners / len(trades)


def calculate_profit_factor(trades: List[Dict]) -> float:
    gross_profit = sum(trade["pnl"] for trade in trades if trade.get("pnl", 0) > 0)
    gross_loss = abs(sum(trade["pnl"] for trade in trades if trade.get("pnl", 0) < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def generate_performance_report(
    portfolio_values: pd.Series,
    trades: List[Dict],
    initial_capital: float,
) -> Dict:
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
        "avg_daily_return": round(float(returns.mean()) * 100, 4) if len(returns) else 0.0,
        "daily_volatility": round(float(returns.std()) * 100, 4) if len(returns) else 0.0,
    }
