"""
Main orchestrator for the agentic trading system.

Person A scope:
1. Coordinate module integration
2. Use real market data from yfinance
3. Preserve technical indicators
4. Add a quantitative confidence boost for technical analysis
"""

import json
import os
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from backtester import Backtester
from broker_alpaca import execute_trade as alpaca_execute_trade
from data_tools import fetch_market_data
from sentiment_tools import get_market_sentiment


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


def parse_json_response(response_text: str) -> Dict:
    """Parse plain JSON or fenced JSON from an LLM response."""
    content = response_text.strip()
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0]
    return json.loads(content.strip())


class SentimentAnalysisAgent:
    """LLM wrapper around the sentiment tool with a safe fallback."""

    def __init__(self, llm: Optional[ChatOpenAI]):
        self.llm = llm
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are an expert in market sentiment analysis.

Analyze the provided sentiment data and return a JSON object:
{{
  "sentiment_score": -1.0 to 1.0,
  "sentiment_impact": "positive" | "negative" | "neutral",
  "reasoning": "brief explanation",
  "confidence_adjustment": -0.2 to 0.2
}}""",
                ),
                ("human", "{input}"),
            ]
        )
        self.chain = self.prompt | self.llm if self.llm else None

    def analyze(self, symbol: str) -> Dict:
        sentiment_data = json.loads(get_market_sentiment.invoke({"symbol": symbol}))

        if not self.chain:
            score = float(sentiment_data.get("sentiment_score", 0.0))
            if score > 0.15:
                impact = "positive"
            elif score < -0.15:
                impact = "negative"
            else:
                impact = "neutral"
            return {
                "sentiment_score": score,
                "sentiment_impact": impact,
                "reasoning": sentiment_data.get("description", "Fallback sentiment mode"),
                "confidence_adjustment": 0.0,
            }

        input_text = f"""Analyze sentiment for {symbol} and determine its impact on trading decisions.

Sentiment Data:
{json.dumps(sentiment_data, indent=2)}
"""
        try:
            response = self.chain.invoke({"input": input_text})
            return parse_json_response(response.content)
        except Exception as exc:
            print(f"Sentiment agent fallback triggered: {exc}")
            return {
                "sentiment_score": float(sentiment_data.get("sentiment_score", 0.0)),
                "sentiment_impact": "neutral",
                "reasoning": "Using raw sentiment tool output because LLM parsing failed",
                "confidence_adjustment": 0.0,
            }


class TechnicalAnalysisAgent:
    """Technical analysis agent with quantitative signal boost."""

    def __init__(self, llm: Optional[ChatOpenAI]):
        self.llm = llm
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are an expert technical analyst for algorithmic trading.

Review the market data and return a JSON object:
{{
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "technical_score": 0.0-1.0,
  "key_indicators": ["supporting signals"]
}}""",
                ),
                ("human", "{input}"),
            ]
        )
        self.chain = self.prompt | self.llm if self.llm else None

    def _fallback_analysis(self, market_data: Dict) -> Dict:
        ml_signal = market_data.get("ml_signal", {})
        indicators = market_data.get("indicators_summary", {})
        signal = ml_signal.get("signal", "HOLD")
        confidence = 0.50 + ml_signal.get("confidence_boost", 0.0)
        confidence = min(0.90, max(0.35, confidence)) if signal != "HOLD" else 0.40

        return {
            "signal": signal,
            "confidence": round(confidence, 2),
            "reasoning": "; ".join(ml_signal.get("reasons", ["Quantitative fallback mode"])),
            "technical_score": round(abs(ml_signal.get("score", 0)) / 6, 2),
            "key_indicators": [
                f"RSI={indicators.get('rsi', 50):.1f}",
                f"MACD={indicators.get('macd', 0):.3f}",
                f"SMA20={indicators.get('sma_20', 0):.2f}",
                f"SMA50={indicators.get('sma_50', 0):.2f}",
            ],
            "ml_signal": ml_signal,
        }

    def analyze(self, symbol: str) -> Dict:
        market_data = json.loads(
            fetch_market_data.invoke({"symbol": symbol, "period": "3mo", "interval": "1h"})
        )
        if market_data.get("error"):
            return {
                "signal": "HOLD",
                "confidence": 0.0,
                "reasoning": market_data["error"],
                "technical_score": 0.0,
                "key_indicators": [],
                "ml_signal": {"signal": "HOLD", "confidence_boost": 0.0, "score": 0, "reasons": []},
            }

        if not self.chain:
            return self._fallback_analysis(market_data)

        input_text = f"""Analyze {symbol} and provide a trading recommendation.

Market Data:
{json.dumps(market_data, indent=2)}
"""

        try:
            response = self.chain.invoke({"input": input_text})
            analysis = parse_json_response(response.content)
        except Exception as exc:
            print(f"Technical agent fallback triggered: {exc}")
            return self._fallback_analysis(market_data)

        ml_signal = market_data.get("ml_signal", {})
        if ml_signal.get("confidence_boost", 0) and ml_signal.get("signal") == analysis.get("signal", "HOLD"):
            original_conf = float(analysis.get("confidence", 0.5))
            boosted_conf = min(1.0, original_conf + float(ml_signal["confidence_boost"]))
            analysis["confidence"] = round(boosted_conf, 2)
            reasons = ", ".join(ml_signal.get("reasons", []))
            analysis["reasoning"] = f"{analysis.get('reasoning', '')} [Quant boost: {reasons}]".strip()
        analysis["ml_signal"] = ml_signal
        return analysis


class RiskManagementAgent:
    """Simplified risk layer until the teammate module is fully integrated."""

    def __init__(self, llm: Optional[ChatOpenAI]):
        self.llm = llm

    def assess(
        self,
        signal: Dict,
        portfolio_state: PortfolioState,
        current_price: float,
        volatility: float,
    ) -> Dict:
        if signal.get("signal") == "HOLD":
            return {
                "position_size": 0,
                "risk_assessment": "LOW",
                "reasoning": "No trade recommended from technical analysis",
                "stop_loss": round(current_price * 0.97, 2),
                "take_profit": round(current_price * 1.05, 2),
                "should_trade": False,
            }

        max_position_value = portfolio_state.portfolio_value * 0.10
        risk_adjustment = max(0.25, 1 - (volatility * 10))
        target_value = max_position_value * signal.get("confidence", 0.0) * risk_adjustment
        position_size = int(min(target_value, portfolio_state.cash) / current_price)
        risk_label = "LOW" if volatility < 0.015 else "MEDIUM" if volatility < 0.03 else "HIGH"

        return {
            "position_size": max(0, position_size),
            "risk_assessment": risk_label,
            "reasoning": f"10% max allocation with volatility adjustment ({volatility:.4f})",
            "stop_loss": round(current_price * 0.97, 2),
            "take_profit": round(current_price * 1.05, 2),
            "should_trade": position_size > 0 and risk_label != "HIGH",
        }


class ExecutionAgent:
    """Final execution wrapper with broker integration."""

    def __init__(self, llm: Optional[ChatOpenAI]):
        self.llm = llm
        self.order_history = []

    def decide(self, technical_analysis: Dict, sentiment_analysis: Dict, risk_assessment: Dict) -> Dict:
        sentiment_score = float(sentiment_analysis.get("sentiment_score", 0.0))
        tech_signal = technical_analysis.get("signal", "HOLD")
        should_trade = bool(risk_assessment.get("should_trade", False))

        execute = should_trade and tech_signal != "HOLD"
        if tech_signal == "BUY" and sentiment_score < -0.4:
            execute = False
        if tech_signal == "SELL" and sentiment_score > 0.4:
            execute = False

        return {
            "execute": execute,
            "execution_strategy": "MARKET",
            "reasoning": "Execution based on technical signal, sentiment check, and risk gate",
            "urgency": "MEDIUM" if execute else "LOW",
        }

    def execute_trade(
        self,
        symbol: str,
        signal_type: str,
        quantity: int,
        price: float,
        strategy: str = "MARKET",
        stop_loss: float = None,
        take_profit: float = None,
    ) -> Optional[Dict]:
        if quantity <= 0:
            return None

        result = alpaca_execute_trade(
            symbol=symbol,
            signal_type=signal_type,
            quantity=quantity,
            price=price,
            strategy=strategy,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        if result and result.get("main"):
            order = result["main"]
            order["timestamp"] = datetime.now().isoformat()
            self.order_history.append(order)
            return order
        return None


class TradingOrchestrator:
    """Coordinate technical, sentiment, risk, and execution modules."""

    def __init__(self, api_key: Optional[str], initial_capital: float = 100000):
        self.llm = None
        if api_key:
            self.llm = ChatOpenAI(
                model="anthropic/claude-sonnet-4-5",
                openai_api_key=api_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.3,
            )

        self.technical_agent = TechnicalAnalysisAgent(self.llm)
        self.sentiment_agent = SentimentAnalysisAgent(self.llm)
        self.risk_agent = RiskManagementAgent(self.llm)
        self.execution_agent = ExecutionAgent(self.llm)
        self.portfolio_state = PortfolioState(
            cash=initial_capital,
            positions={},
            portfolio_value=initial_capital,
            total_trades=0,
        )
        self.backtester = Backtester(initial_capital=initial_capital)

    def update_portfolio_value(self):
        positions_value = sum(
            position.quantity * position.current_price
            for position in self.portfolio_state.positions.values()
        )
        self.portfolio_state.portfolio_value = self.portfolio_state.cash + positions_value

    def process_symbol(self, symbol: str) -> Dict:
        print(f"\n{'=' * 70}")
        print(f"Processing {symbol}")
        print(f"{'=' * 70}")

        technical_analysis = self.technical_agent.analyze(symbol)
        technical_analysis["symbol"] = symbol
        print(f"[Technical] Signal={technical_analysis.get('signal')} confidence={technical_analysis.get('confidence')}")

        sentiment_analysis = self.sentiment_agent.analyze(symbol)
        print(f"[Sentiment] Score={sentiment_analysis.get('sentiment_score', 0):+.2f}")

        market_data = json.loads(fetch_market_data.invoke({"symbol": symbol}))
        current_price = float(market_data.get("current_price", 0.0))
        volatility = float(market_data.get("volatility", 0.0))

        risk_assessment = self.risk_agent.assess(
            technical_analysis,
            self.portfolio_state,
            current_price,
            volatility,
        )
        print(f"[Risk] should_trade={risk_assessment.get('should_trade')} size={risk_assessment.get('position_size')}")

        execution_decision = self.execution_agent.decide(
            technical_analysis,
            sentiment_analysis,
            risk_assessment,
        )
        print(f"[Execution] execute={execution_decision.get('execute')}")

        order = None
        if execution_decision.get("execute") and risk_assessment.get("should_trade"):
            quantity = int(risk_assessment.get("position_size", 0))
            order = self.execution_agent.execute_trade(
                symbol,
                technical_analysis.get("signal", "HOLD"),
                quantity,
                current_price,
                strategy=execution_decision.get("execution_strategy", "MARKET"),
                stop_loss=risk_assessment.get("stop_loss"),
                take_profit=risk_assessment.get("take_profit"),
            )

            if order:
                filled_price = order.get("filled_avg_price") or current_price
                signal_type = technical_analysis.get("signal", "HOLD")

                if signal_type == "BUY":
                    self.portfolio_state.cash -= quantity * filled_price
                    self.portfolio_state.positions[symbol] = Position(
                        symbol=symbol,
                        quantity=quantity,
                        entry_price=filled_price,
                        current_price=filled_price,
                        entry_time=datetime.now().isoformat(),
                    )
                elif signal_type == "SELL" and symbol in self.portfolio_state.positions:
                    self.portfolio_state.cash += quantity * filled_price
                    del self.portfolio_state.positions[symbol]

                self.portfolio_state.total_trades += 1
                self.backtester.record_trade(
                    datetime.now().strftime("%Y-%m-%d"),
                    symbol,
                    signal_type,
                    quantity,
                    filled_price,
                )

        self.update_portfolio_value()

        return {
            "symbol": symbol,
            "technical_analysis": technical_analysis,
            "sentiment_analysis": sentiment_analysis,
            "risk_assessment": risk_assessment,
            "execution_decision": execution_decision,
            "order": order,
            "current_price": current_price,
            "portfolio_value": self.portfolio_state.portfolio_value,
        }

    def run_trading_cycle(self, symbols: List[str]) -> List[Dict]:
        print(f"\n{'#' * 70}")
        print(f"Starting Trading Cycle - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Portfolio Value: ${self.portfolio_state.portfolio_value:,.2f}")
        print(f"Cash: ${self.portfolio_state.cash:,.2f}")
        print(f"{'#' * 70}")

        results = [self.process_symbol(symbol) for symbol in symbols]
        current_prices = {result["symbol"]: result["current_price"] for result in results}
        self.backtester.update_portfolio_value(datetime.now().strftime("%Y-%m-%d"), current_prices)

        print(f"\n{'#' * 70}")
        print("Trading Cycle Complete")
        print(f"Final Portfolio Value: ${self.portfolio_state.portfolio_value:,.2f}")
        print(f"Active Positions: {len(self.portfolio_state.positions)}")
        print(f"Total Trades: {self.portfolio_state.total_trades}")
        print(f"{'#' * 70}\n")

        return results


if __name__ == "__main__":
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")

    orchestrator = TradingOrchestrator(api_key=api_key, initial_capital=100000)
    results = orchestrator.run_trading_cycle(["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "XOM", "KO"])

    print("\n" + "=" * 70)
    print("DETAILED TRADING SUMMARY")
    print("=" * 70)

    for result in results:
        print(f"\n{result['symbol']}:")
        print(
            f"  Technical Signal: {result['technical_analysis'].get('signal', 'N/A')} "
            f"(Confidence: {result['technical_analysis'].get('confidence', 0):.1%})"
        )
        print(f"  Sentiment: {result['sentiment_analysis'].get('sentiment_score', 0):+.2f}")
        print(f"  Risk Level: {result['risk_assessment'].get('risk_assessment', 'N/A')}")
        print(f"  Executed: {'Yes' if result['order'] else 'No'}")
        if result["order"]:
            print(f"  Order: {result['order']}")

    orchestrator.backtester.export_trades()
    orchestrator.backtester.export_portfolio_history()

    report = orchestrator.backtester.get_report()
    with open("outputs/backtest_metrics.json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("\nBacktest report saved to outputs/backtest_metrics.json")
