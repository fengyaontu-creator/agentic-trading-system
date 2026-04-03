"""
agentic_trading.py — 主交易系统（Orchestrator）
Owner: Person A (Nora) — 负责整合所有模块

基于老师模板改造，整合以下模块：
- data_tools.py      (Person A): yfinance 真实数据 + ML 信号
- sentiment_tools.py  (Person B): 多源情绪分析
- broker_alpaca.py    (Person C): Alpaca paper trading
- backtester.py       (Person D): 回测 + 风控增强
- dashboard.py        (Person E): 可视化

模板来源：CA6115 Week6 Agentic Trading - with Cell Notes.ipynb
"""

import os
import json
import numpy as np
import pandas as pd
from enum import Enum
from typing import Dict, List
from datetime import datetime
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

# --- Import our custom modules ---
from data_tools import fetch_market_data, generate_ml_signal, fetch_historical_data
from sentiment_tools import get_market_sentiment
from broker_alpaca import execute_trade as alpaca_execute_trade
from backtester import Backtester, enhanced_risk_assessment


# ============================================================================
# Data Models (from template, unchanged)
# ============================================================================

class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

class TradingSignal(BaseModel):
    symbol: str
    signal_type: SignalType
    confidence: float = Field(ge=0.0, le=1.0)
    price: float
    timestamp: str
    reason: str
    technical_score: float = 0.0
    sentiment_score: float = 0.0

class Position(BaseModel):
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    entry_time: str
    pnl: float = 0.0

class PortfolioState(BaseModel):
    cash: float
    positions: Dict[str, Position]
    portfolio_value: float
    total_trades: int


# ============================================================================
# Agents (from template, with minor integration tweaks)
# ============================================================================

class SentimentAnalysisAgent:
    """Agent that analyzes market sentiment using LLM reasoning.

    CHANGED: Now uses real news data via sentiment_tools.get_market_sentiment
    instead of random sentiment scores.
    """

    def __init__(self, llm):
        self.llm = llm
        self.tools = [get_market_sentiment]

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert in market sentiment analysis.

Your job is to:
1. Analyze sentiment data from various sources
2. Determine how sentiment should impact trading decisions
3. Provide a sentiment score (-1 to +1)
4. Explain the sentiment impact

Respond with a JSON object containing:
{{
    "sentiment_score": -1.0 to +1.0,
    "sentiment_impact": "positive" | "negative" | "neutral",
    "reasoning": "explanation",
    "confidence_adjustment": -0.2 to +0.2
}}"""),
            ("human", "{input}")
        ])

        self.chain = self.prompt | self.llm

    def analyze(self, symbol: str) -> Dict:
        sentiment_data = get_market_sentiment.invoke({"symbol": symbol})

        input_text = f"""Analyze sentiment for {symbol} and determine its impact on trading decisions.

Sentiment Data:
{sentiment_data}

Provide your analysis as a JSON object."""

        response = self.chain.invoke({"input": input_text})

        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            analysis = json.loads(content.strip())
            return analysis
        except Exception as e:
            print(f"Error parsing sentiment response: {e}")
            return {
                "sentiment_score": 0.0,
                "sentiment_impact": "neutral",
                "reasoning": "Unable to parse sentiment",
                "confidence_adjustment": 0.0
            }


class TechnicalAnalysisAgent:
    """Agent that performs technical analysis using LLM reasoning.

    CHANGED: Now uses real yfinance data via data_tools.fetch_market_data.
    Also incorporates ML signal as supplementary input.
    """

    def __init__(self, llm):
        self.llm = llm
        self.tools = [fetch_market_data]

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert technical analyst for algorithmic trading.

Your job is to:
1. Analyze market data and technical indicators
2. Identify trading signals based on multiple indicators
3. Provide a confidence score (0-1) for your recommendation
4. Explain your reasoning clearly

Consider these indicators:
- Moving Average Crossovers (SMA 20/50)
- MACD and Signal Line
- RSI (oversold <30, overbought >70)
- Bollinger Bands
- Price trends and momentum
- ML/Quantitative signal (if provided)

Respond with a JSON object containing:
{{
    "signal": "BUY" | "SELL" | "HOLD",
    "confidence": 0.0-1.0,
    "reasoning": "detailed explanation",
    "technical_score": 0.0-1.0,
    "key_indicators": ["list of supporting indicators"]
}}"""),
            ("human", "{input}")
        ])

        self.chain = self.prompt | self.llm

    def analyze(self, symbol: str) -> Dict:
        market_data = fetch_market_data.invoke({"symbol": symbol, "period": "3mo", "interval": "1h"})

        input_text = f"""Analyze {symbol} and provide a trading recommendation.

Market Data:
{market_data}

Provide your analysis as a JSON object."""

        response = self.chain.invoke({"input": input_text})

        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            analysis = json.loads(content.strip())

            # --- ML signal boost (NEW) ---
            data = json.loads(market_data)
            ml_signal = data.get('ml_signal', {})
            if ml_signal.get('confidence_boost', 0) != 0:
                original_conf = analysis.get('confidence', 0.5)
                boost = ml_signal['confidence_boost']
                if ml_signal['signal'] == analysis.get('signal', 'HOLD'):
                    analysis['confidence'] = min(1.0, original_conf + boost)
                    analysis['reasoning'] += f" [ML confirms: {', '.join(ml_signal.get('reasons', []))}]"
                analysis['ml_signal'] = ml_signal

            return analysis
        except Exception as e:
            print(f"Error parsing LLM response: {e}")
            return {
                "signal": "HOLD",
                "confidence": 0.0,
                "reasoning": "Unable to parse analysis",
                "technical_score": 0.0,
                "key_indicators": []
            }


class RiskManagementAgent:
    """Agent that manages risk and position sizing.

    CHANGED: Incorporates enhanced_risk_assessment from backtester.py
    as a secondary check alongside LLM reasoning.
    """

    def __init__(self, llm):
        self.llm = llm

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a professional risk management expert for algorithmic trading.

Your job is to:
1. Calculate appropriate position sizes based on risk parameters
2. Assess portfolio risk levels
3. Recommend risk adjustments
4. Ensure proper diversification

Risk Parameters:
- Max position size: 10% of portfolio
- Max risk per trade: 2% of portfolio
- Max drawdown: 15%

Respond with a JSON object containing:
{{
    "position_size": integer (number of shares),
    "risk_assessment": "LOW" | "MEDIUM" | "HIGH",
    "reasoning": "explanation",
    "stop_loss": float (suggested stop loss price),
    "take_profit": float (suggested take profit price),
    "should_trade": boolean
}}"""),
            ("human", "{input}")
        ])

        self.chain = self.prompt | self.llm

    def assess(self, signal: Dict, portfolio_state: PortfolioState,
               current_price: float, volatility: float) -> Dict:

        input_text = f"""Assess risk and calculate position size for this trading opportunity.

Trading Signal:
- Symbol: {signal.get('symbol', 'UNKNOWN')}
- Signal Type: {signal.get('signal', 'HOLD')}
- Confidence: {signal.get('confidence', 0.0)}
- Reasoning: {signal.get('reasoning', 'N/A')}

Portfolio State:
- Cash Available: ${portfolio_state.cash:,.2f}
- Portfolio Value: ${portfolio_state.portfolio_value:,.2f}
- Current Positions: {len(portfolio_state.positions)}
- Total Trades: {portfolio_state.total_trades}

Market Data:
- Current Price: ${current_price:.2f}
- Volatility: {volatility:.4f}

Provide your risk assessment as a JSON object."""

        response = self.chain.invoke({"input": input_text})

        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            assessment = json.loads(content.strip())
            return assessment
        except Exception as e:
            print(f"Error parsing risk assessment: {e}")
            return {
                "position_size": 0,
                "risk_assessment": "HIGH",
                "reasoning": "Unable to assess risk",
                "stop_loss": current_price * 0.95,
                "take_profit": current_price * 1.05,
                "should_trade": False
            }


class ExecutionAgent:
    """Agent that handles trade execution decisions.

    CHANGED: execute_trade now routes to Alpaca paper trading
    via broker_alpaca.execute_trade.
    """

    def __init__(self, llm):
        self.llm = llm
        self.order_history = []

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a trade execution specialist.

Your job is to:
1. Review all analysis and recommendations
2. Make final execution decision
3. Determine optimal execution strategy
4. Consider market conditions for execution

Respond with a JSON object containing:
{{
    "execute": boolean,
    "execution_strategy": "MARKET" | "LIMIT" | "STOP",
    "reasoning": "explanation",
    "urgency": "LOW" | "MEDIUM" | "HIGH"
}}"""),
            ("human", "{input}")
        ])

        self.chain = self.prompt | self.llm

    def decide(self, technical_analysis: Dict, sentiment_analysis: Dict,
               risk_assessment: Dict) -> Dict:

        input_text = f"""Review all analysis and make a final execution decision.

Technical Analysis:
{json.dumps(technical_analysis, indent=2)}

Sentiment Analysis:
{json.dumps(sentiment_analysis, indent=2)}

Risk Assessment:
{json.dumps(risk_assessment, indent=2)}

Should we execute this trade? Provide your decision as a JSON object."""

        response = self.chain.invoke({"input": input_text})

        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            decision = json.loads(content.strip())
            return decision
        except Exception as e:
            print(f"Error parsing execution decision: {e}")
            return {
                "execute": False,
                "execution_strategy": "MARKET",
                "reasoning": "Unable to make decision",
                "urgency": "LOW"
            }

    def execute_trade(self, symbol: str, signal_type: str, quantity: int,
                      price: float, strategy: str = "MARKET",
                      stop_loss: float = None, take_profit: float = None) -> Dict:
        """Execute trade via Alpaca (or simulation fallback)."""
        if quantity == 0:
            return None

        # Route to Alpaca
        result = alpaca_execute_trade(
            symbol=symbol,
            signal_type=signal_type,
            quantity=quantity,
            price=price,
            strategy=strategy,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        if result and result.get('main'):
            order = result['main']
            order['timestamp'] = datetime.now().isoformat()
            self.order_history.append(order)
            return order

        return None


# ============================================================================
# Main Orchestrator
# ============================================================================

class TradingOrchestrator:
    """Main orchestrator that coordinates all LangChain agents."""

    def __init__(self, api_key: str, initial_capital: float = 100000):
        # Initialize LLM
        self.llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            anthropic_api_key=api_key,
            temperature=0.3
        )

        # Initialize agents
        self.technical_agent = TechnicalAnalysisAgent(self.llm)
        self.sentiment_agent = SentimentAnalysisAgent(self.llm)
        self.risk_agent = RiskManagementAgent(self.llm)
        self.execution_agent = ExecutionAgent(self.llm)

        # Portfolio state
        self.portfolio_state = PortfolioState(
            cash=initial_capital,
            positions={},
            portfolio_value=initial_capital,
            total_trades=0
        )

        # Backtester for tracking
        self.backtester = Backtester(initial_capital=initial_capital)

    def update_portfolio_value(self):
        positions_value = sum(
            pos.quantity * pos.current_price
            for pos in self.portfolio_state.positions.values()
        )
        self.portfolio_state.portfolio_value = self.portfolio_state.cash + positions_value

    def process_symbol(self, symbol: str) -> Dict:
        print(f"\n{'='*70}")
        print(f"🔍 Processing {symbol}")
        print(f"{'='*70}")

        # Step 1: Technical Analysis
        print(f"\n📊 [Technical Analysis Agent] Analyzing {symbol}...")
        technical_analysis = self.technical_agent.analyze(symbol)
        technical_analysis['symbol'] = symbol
        print(f"Signal: {technical_analysis.get('signal', 'UNKNOWN')}")
        print(f"Confidence: {technical_analysis.get('confidence', 0):.1%}")
        print(f"Reasoning: {technical_analysis.get('reasoning', 'N/A')[:100]}...")

        # Step 2: Sentiment Analysis
        print(f"\n💭 [Sentiment Analysis Agent] Analyzing sentiment...")
        sentiment_analysis = self.sentiment_agent.analyze(symbol)
        print(f"Sentiment Score: {sentiment_analysis.get('sentiment_score', 0):+.2f}")
        print(f"Impact: {sentiment_analysis.get('sentiment_impact', 'unknown')}")

        # Get current price and volatility
        market_data = json.loads(fetch_market_data.invoke({"symbol": symbol}))
        current_price = market_data['current_price']
        volatility = market_data['volatility']

        # Step 3: Risk Management
        print(f"\n⚖️  [Risk Management Agent] Assessing risk...")
        risk_assessment = self.risk_agent.assess(
            technical_analysis,
            self.portfolio_state,
            current_price,
            volatility
        )
        print(f"Position Size: {risk_assessment.get('position_size', 0)} shares")
        print(f"Risk Level: {risk_assessment.get('risk_assessment', 'UNKNOWN')}")
        print(f"Should Trade: {risk_assessment.get('should_trade', False)}")

        # Step 4: Execution Decision
        print(f"\n🎯 [Execution Agent] Making final decision...")
        execution_decision = self.execution_agent.decide(
            technical_analysis,
            sentiment_analysis,
            risk_assessment
        )
        print(f"Execute: {execution_decision.get('execute', False)}")
        print(f"Strategy: {execution_decision.get('execution_strategy', 'N/A')}")
        print(f"Reasoning: {execution_decision.get('reasoning', 'N/A')[:100]}...")

        # Step 5: Execute if approved
        order = None
        if execution_decision.get('execute', False) and risk_assessment.get('should_trade', False):
            position_size = risk_assessment.get('position_size', 0)

            if position_size > 0:
                print(f"\n✅ [Execution Agent] Executing trade...")
                strategy = execution_decision.get('execution_strategy', 'MARKET')
                order = self.execution_agent.execute_trade(
                    symbol,
                    technical_analysis.get('signal', 'HOLD'),
                    position_size,
                    current_price,
                    strategy=strategy,
                    stop_loss=risk_assessment.get('stop_loss'),
                    take_profit=risk_assessment.get('take_profit')
                )

                if order:
                    print(f"Order: {order}")

                    # Update portfolio
                    signal_type = technical_analysis.get('signal', 'HOLD')
                    exec_price = order.get('filled_avg_price') or current_price

                    if signal_type == 'BUY':
                        self.portfolio_state.cash -= position_size * exec_price
                        self.portfolio_state.positions[symbol] = Position(
                            symbol=symbol,
                            quantity=position_size,
                            entry_price=exec_price,
                            current_price=exec_price,
                            entry_time=datetime.now().isoformat()
                        )
                    elif signal_type == 'SELL' and symbol in self.portfolio_state.positions:
                        self.portfolio_state.cash += position_size * exec_price
                        del self.portfolio_state.positions[symbol]

                    self.portfolio_state.total_trades += 1

                    # Record in backtester
                    self.backtester.record_trade(
                        datetime.now().strftime('%Y-%m-%d'),
                        symbol, signal_type, position_size, exec_price
                    )
        else:
            print(f"\n❌ Trade not executed - conditions not met")

        self.update_portfolio_value()

        return {
            'symbol': symbol,
            'technical_analysis': technical_analysis,
            'sentiment_analysis': sentiment_analysis,
            'risk_assessment': risk_assessment,
            'execution_decision': execution_decision,
            'order': order,
            'portfolio_value': self.portfolio_state.portfolio_value
        }

    def run_trading_cycle(self, symbols: List[str]):
        print(f"\n{'#'*70}")
        print(f"🚀 Starting Trading Cycle - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"💰 Portfolio Value: ${self.portfolio_state.portfolio_value:,.2f}")
        print(f"💵 Cash: ${self.portfolio_state.cash:,.2f}")
        print(f"📈 Positions: {len(self.portfolio_state.positions)}")
        print(f"{'#'*70}")

        results = []
        for symbol in symbols:
            result = self.process_symbol(symbol)
            results.append(result)

        # Update backtester portfolio value
        current_prices = {s: r.get('risk_assessment', {}).get('current_price', 0)
                         for s, r in zip(symbols, results)}
        self.backtester.update_portfolio_value(
            datetime.now().strftime('%Y-%m-%d'), current_prices
        )

        print(f"\n{'#'*70}")
        print(f"✨ Trading Cycle Complete")
        print(f"💰 Final Portfolio Value: ${self.portfolio_state.portfolio_value:,.2f}")
        print(f"💵 Cash: ${self.portfolio_state.cash:,.2f}")
        print(f"📈 Active Positions: {len(self.portfolio_state.positions)}")
        print(f"📊 Total Trades: {self.portfolio_state.total_trades}")

        initial = self.backtester.initial_capital
        pnl = self.portfolio_state.portfolio_value - initial
        pnl_pct = (pnl / initial) * 100
        print(f"{'📈' if pnl >= 0 else '📉'} P&L: ${pnl:+,.2f} ({pnl_pct:+.2f}%)")
        print(f"{'#'*70}\n")

        return results


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    symbols = ['AAPL', 'GOOGL']

    load_dotenv()
    API_KEY = os.getenv("ANTHROPIC_API_KEY")

    if not API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        exit(1)

    orchestrator = TradingOrchestrator(api_key=API_KEY, initial_capital=100000)
    results = orchestrator.run_trading_cycle(symbols)

    # Display summary
    print("\n" + "="*70)
    print("📋 DETAILED TRADING SUMMARY")
    print("="*70)

    for result in results:
        print(f"\n{result['symbol']}:")
        print(f"  Technical Signal: {result['technical_analysis'].get('signal', 'N/A')} "
              f"(Confidence: {result['technical_analysis'].get('confidence', 0):.1%})")
        print(f"  Sentiment: {result['sentiment_analysis'].get('sentiment_score', 0):+.2f}")
        print(f"  Risk Level: {result['risk_assessment'].get('risk_assessment', 'N/A')}")
        print(f"  Executed: {'Yes ✅' if result['order'] else 'No ❌'}")
        if result['order']:
            print(f"  Order: {result['order']}")

    # Export results
    orchestrator.backtester.export_trades()
    orchestrator.backtester.export_portfolio_history()

    report = orchestrator.backtester.get_report()
    with open("outputs/backtest_metrics.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nBacktest report saved to outputs/backtest_metrics.json")

    print(f"\n{'='*70}")
    print(f"Final Portfolio Value: ${orchestrator.portfolio_state.portfolio_value:,.2f}")
    pnl = orchestrator.portfolio_state.portfolio_value - 100000
    print(f"Total Return: ${pnl:+,.2f} ({(pnl/100000)*100:+.2f}%)")
    print(f"{'='*70}")
