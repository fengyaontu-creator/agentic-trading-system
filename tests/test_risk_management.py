"""
Regression tests for RiskManagementAgent edge cases.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agentic_trading import PortfolioState, Position, RiskManagementAgent, TradingParams


def _portfolio(cash=100_000.0, positions=None):
    return PortfolioState(
        cash=cash,
        positions=positions or {},
        portfolio_value=cash,
        total_trades=0,
    )


def test_sell_closes_existing_long_position():
    agent = RiskManagementAgent(llm=None, params=TradingParams())
    portfolio = _portfolio(positions={
        "AAPL": Position(
            symbol="AAPL",
            quantity=12,
            entry_price=100.0,
            current_price=100.0,
            entry_time="t0",
        )
    })

    result = agent.assess(
        signal={"signal": "SELL", "confidence": 0.8},
        portfolio_state=portfolio,
        current_price=110.0,
        volatility=0.01,
        symbol="AAPL",
    )

    assert result["should_trade"] is True
    assert result["position_size"] == 12


def test_buy_closes_existing_short_position():
    agent = RiskManagementAgent(llm=None, params=TradingParams())
    portfolio = _portfolio(positions={
        "TSLA": Position(
            symbol="TSLA",
            quantity=-7,
            entry_price=200.0,
            current_price=200.0,
            entry_time="t0",
        )
    })

    result = agent.assess(
        signal={"signal": "BUY", "confidence": 0.8},
        portfolio_state=portfolio,
        current_price=190.0,
        volatility=0.01,
        symbol="TSLA",
    )

    assert result["should_trade"] is True
    assert result["position_size"] == 7
    assert "Closing short" in result["reasoning"]
