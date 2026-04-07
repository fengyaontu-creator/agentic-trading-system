"""
agentic_trading.py -- Main orchestrator for the agentic trading system.

Coordinates technical, sentiment, risk, and execution agents.
Uses real market data from yfinance with quantitative confidence boost.
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from backtester import Backtester, calculate_dynamic_stop_loss, check_concentration_limit
from broker_alpaca import execute_trade as alpaca_execute_trade
from data_tools import fetch_market_data
from position import compute_fill
from sentiment_tools import get_market_sentiment
import database as db

log = logging.getLogger(__name__)


class TradingParams(BaseModel):
    """Per-user trading parameters -- loaded from DB, configurable via UI."""
    risk_per_trade: float = 0.02        # max portfolio % loss per trade
    max_concentration: float = 0.10     # max % of portfolio in one stock
    stop_loss_multiplier: float = 2.0   # volatility multiplier for stop-loss
    take_profit_pct: float = 0.05       # take-profit target %
    min_confidence: float = 0.3         # minimum signal confidence to trade
    # Trailing stop thresholds
    trailing_stop_high_profit: float = 0.10   # profit % to start aggressive trailing
    trailing_stop_low_profit: float = 0.05    # profit % to start moderate trailing
    trailing_stop_cushion: float = 0.03       # cushion below profit for aggressive trail
    trailing_stop_lock_pct: float = 0.02      # locked-in profit % for moderate trail


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
    """Thin wrapper -- the sentiment tool handles LLM headline scoring internally."""

    def __init__(self, llm: Optional[ChatOpenAI]):
        self.llm = llm

    def analyze(self, symbol: str) -> Dict:
        data = json.loads(get_market_sentiment.invoke({"symbol": symbol}))
        score = float(data.get("sentiment_score", 0.0))
        if score > 0.15:
            impact = "positive"
        elif score < -0.15:
            impact = "negative"
        else:
            impact = "neutral"
        return {
            "sentiment_score": score,
            "sentiment_impact": impact,
            "reasoning": data.get("description", ""),
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
                "current_price": 0.0,
                "volatility": 0.0,
            }

        if not self.chain:
            analysis = self._fallback_analysis(market_data)
        else:
            input_text = f"""Analyze {symbol} and provide a trading recommendation.

Market Data:
{json.dumps(market_data, indent=2)}
"""
            try:
                response = self.chain.invoke({"input": input_text})
                analysis = parse_json_response(response.content)
            except Exception as exc:
                # LLM parse failed -- use quantitative fallback
                log.warning(f"[TECH] {symbol} LLM parsing failed: {exc}, using fallback analysis", exc_info=True)
                analysis = self._fallback_analysis(market_data)
            else:
                ml_signal = market_data.get("ml_signal", {})
                quant_signal = ml_signal.get("signal", "HOLD")
                llm_signal = analysis.get("signal", "HOLD")

                opposite = {("BUY", "SELL"), ("SELL", "BUY")}
                if (quant_signal, llm_signal) in opposite:
                    analysis["signal"] = "HOLD"
                    analysis["confidence"] = 0.0
                    analysis["reasoning"] = (
                        f"Quant ({quant_signal}) and LLM ({llm_signal}) disagree -- defaulting to HOLD"
                    )
                elif ml_signal.get("confidence_boost", 0) and quant_signal == llm_signal:
                    original_conf = float(analysis.get("confidence", 0.5))
                    boosted_conf = min(1.0, original_conf + float(ml_signal["confidence_boost"]))
                    analysis["confidence"] = round(boosted_conf, 2)
                    reasons = ", ".join(ml_signal.get("reasons", []))
                    analysis["reasoning"] = (
                        f"{analysis.get('reasoning', '')} [Quant boost: {reasons}]".strip()
                    )

                analysis["ml_signal"] = ml_signal

        analysis["current_price"] = float(market_data.get("current_price", 0.0))
        analysis["volatility"] = float(market_data.get("volatility", 0.0))
        return analysis


class RiskManagementAgent:
    """Risk assessment using VaR-based sizing, dynamic stops, and concentration limits.
    All thresholds come from per-user TradingParams."""

    def __init__(self, llm: Optional[ChatOpenAI], params: TradingParams = None):
        self.llm = llm
        self.params = params or TradingParams()

    def assess(
        self,
        signal: Dict,
        portfolio_state: PortfolioState,
        current_price: float,
        volatility: float,
        symbol: str = "",
    ) -> Dict:
        p = self.params
        
        # Determine action and calculate stop-loss/take-profit based on direction
        action = signal.get("signal", "HOLD")
        confidence = signal.get("confidence", 0.0)
        existing = portfolio_state.positions.get(symbol)
        if existing and existing.quantity != 0:
            is_long = existing.quantity > 0
            
            if is_long:
                profit_pct = (current_price - existing.entry_price) / existing.entry_price
            else:
                profit_pct = (existing.entry_price - current_price) / existing.entry_price
                
            if profit_pct > p.trailing_stop_high_profit:
                stop_offset = profit_pct - p.trailing_stop_cushion
                dynamic_stop = existing.entry_price * (1 + stop_offset) if is_long else existing.entry_price * (1 - stop_offset)
            elif profit_pct > p.trailing_stop_low_profit:
                dynamic_stop = existing.entry_price * (1 + p.trailing_stop_lock_pct) if is_long else existing.entry_price * (1 - p.trailing_stop_lock_pct)
            else:
                vol_offset = volatility * p.stop_loss_multiplier
                dynamic_stop = existing.entry_price * (1 - vol_offset) if is_long else existing.entry_price * (1 + vol_offset)

            triggered = (is_long and current_price < dynamic_stop) or (not is_long and current_price > dynamic_stop)

            if triggered:
                force_action = "SELL" if is_long else "BUY"
                if action != force_action:
                    action = force_action
                    signal["signal"] = force_action
                    signal["reasoning"] = f"[Trailing Stop Triggered] Current profit {profit_pct:.1%}, crossed dynamic stop level at {dynamic_stop:.2f}"
        
        if action == "BUY":
            # Long position: stop-loss below entry, take-profit above entry
            stop_distance = calculate_dynamic_stop_loss(
                current_price, volatility, multiplier=p.stop_loss_multiplier,
            )
            stop_loss = stop_distance  # Already below current_price
            take_profit = round(current_price * (1 + p.take_profit_pct), 2)
        elif action == "SELL":
            # Short position: stop-loss above entry, take-profit below entry
            stop_distance = current_price * volatility * p.stop_loss_multiplier
            stop_loss = round(current_price + stop_distance, 2)  # Above current_price
            take_profit = round(current_price * (1 - p.take_profit_pct), 2)
        else:
            # HOLD
            stop_loss = current_price
            take_profit = current_price
        
        risk_level = "LOW" if volatility < 0.015 else "MEDIUM" if volatility < 0.03 else "HIGH"

        if signal.get("signal") == "HOLD":
            return {
                "position_size": 0,
                "risk_level": risk_level,
                "reasoning": "No trade recommended",
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "should_trade": False,
            }

        existing = portfolio_state.positions.get(symbol)

        if action == "SELL" and existing and existing.quantity > 0:
            return {
                "position_size": existing.quantity,
                "risk_level": risk_level,
                "reasoning": f"Closing long of {existing.quantity} shares",
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "should_trade": True,
            }
        if action == "BUY" and existing and existing.quantity < 0:
            return {
                "position_size": abs(existing.quantity),
                "risk_level": risk_level,
                "reasoning": f"Closing short of {abs(existing.quantity)} shares",
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "should_trade": True,
            }

        # New BUY or new SHORT -- VaR-based sizing with concentration check
        max_risk_dollar = portfolio_state.portfolio_value * p.risk_per_trade
        # For both BUY and SHORT, risk_per_share is always positive
        if action == "BUY":
            risk_per_share = current_price - stop_loss
        else:  # SELL (opening short)
            risk_per_share = stop_loss - current_price
        
        max_shares = int(max_risk_dollar / risk_per_share) if risk_per_share > 0 else 0
        position_size = int(max_shares * confidence)

        existing_values = {
            s: pos.quantity * pos.current_price
            for s, pos in portfolio_state.positions.items()
        }
        proposed_value = position_size * current_price
        concentration = check_concentration_limit(
            existing_values, portfolio_state.portfolio_value, symbol, proposed_value,
            max_concentration=p.max_concentration,
        )

        should_trade = (
            concentration["allowed"]
            and position_size > 0
            and (action == "BUY" and proposed_value <= portfolio_state.cash or action == "SELL")
            and confidence >= p.min_confidence
            and risk_level != "HIGH"
        )

        return {
            "position_size": max(0, position_size) if should_trade else 0,
            "risk_level": risk_level,
            "reasoning": (
                f"VaR sizing: risk/trade=${max_risk_dollar:.0f}, "
                f"vol={volatility * 100:.2f}%, {concentration['reason']}"
            ),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "should_trade": should_trade,
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
        side: str,
        quantity: int,
        price: float,
        api_key: str,
        api_secret: str,
        strategy: str = "MARKET",
        stop_loss: float = None,
        take_profit: float = None,
    ) -> Optional[Dict]:
        if quantity <= 0:
            log.warning(f"[EXEC] {symbol} {side} x{quantity} -- invalid quantity")
            return None

        try:
            result = alpaca_execute_trade(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                api_key=api_key,
                api_secret=api_secret,
                strategy=strategy,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            if result and result.get("main"):
                order = result["main"]
                order["timestamp"] = datetime.now().isoformat()
                self.order_history.append(order)
                log.info(f"[EXEC] {symbol} {side} x{quantity} @ {price} ({strategy}) -> order_id={order.get('order_id')}")
                return order
            else:
                log.warning(f"[EXEC] {symbol} {side} x{quantity} -- no main order returned")
                return None
        except Exception as exc:
            log.error(
                f"[EXEC] {symbol} {side} x{quantity} @ {price} ({strategy}) failed: {exc} | "
                f"stop_loss={stop_loss}, take_profit={take_profit}",
                exc_info=True
            )
            return None


class TradingOrchestrator:
    """Coordinate technical, sentiment, risk, and execution modules."""

    def __init__(self, api_key: Optional[str], user_id: str = "default", initial_capital: float = 100000):
        self.user_id = user_id
        self.llm = None
        if api_key:
            self.llm = ChatOpenAI(
                model="anthropic/claude-sonnet-4-6",
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                temperature=0.3,
            )

        # User must already exist (created via the register API or CLI bootstrap).
        # Constructing an orchestrator should be a pure read; previously this
        # silently called init_db() + create_user(), which masked typo'd user_ids
        # by quietly creating a fresh account and made the constructor a hidden
        # write path.
        if db.get_user(user_id) is None:
            raise ValueError(
                f"TradingOrchestrator: user_id={user_id!r} does not exist. "
                f"Register the user before constructing an orchestrator."
            )

        self.params = TradingParams(**db.load_user_settings(user_id))
        self.technical_agent = TechnicalAnalysisAgent(self.llm)
        self.sentiment_agent = SentimentAnalysisAgent(self.llm)
        self.risk_agent = RiskManagementAgent(self.llm, self.params)
        self.execution_agent = ExecutionAgent(self.llm)

        # Load user's Alpaca credentials from DB
        creds = db.get_alpaca_credentials(user_id)
        self.alpaca_key = creds["api_key"] if creds else None
        self.alpaca_secret = creds["api_secret"] if creds else None
        saved = db.load_portfolio(user_id)
        saved_positions = {
            p["symbol"]: Position(
                symbol=p["symbol"],
                quantity=p["quantity"],
                entry_price=p["entry_price"],
                current_price=p["current_price"],
                entry_time=p["entry_time"],
            )
            for p in db.load_positions(user_id)
        }
        self.portfolio_state = PortfolioState(
            cash=saved["cash"] if saved else initial_capital,
            positions=saved_positions,
            portfolio_value=saved["portfolio_value"] if saved else initial_capital,
            total_trades=saved["total_trades"] if saved else 0,
        )
        self.backtester = Backtester(initial_capital=initial_capital)

    def update_portfolio_value(self):
        # Mark-to-market: fetch live prices for all positions
        for symbol, position in self.portfolio_state.positions.items():
            try:
                data = json.loads(fetch_market_data.invoke({"symbol": symbol}))
                price = float(data.get("current_price", 0))
                if price > 0:
                    position.current_price = price
                    position.pnl = round((price - position.entry_price) * position.quantity, 2)
            except Exception as exc:
                log.warning(f"[PORTFOLIO] {symbol} price update failed: {exc}, keeping last known price")  # keep last known price if fetch fails

        positions_value = sum(
            pos.quantity * pos.current_price
            for pos in self.portfolio_state.positions.values()
        )
        self.portfolio_state.portfolio_value = self.portfolio_state.cash + positions_value
        # Persist to DB
        db.save_portfolio(
            self.user_id,
            self.portfolio_state.cash,
            self.portfolio_state.portfolio_value,
            self.portfolio_state.total_trades,
        )
        for symbol, pos in self.portfolio_state.positions.items():
            db.save_position(self.user_id, symbol, pos.quantity, pos.entry_price, pos.current_price, pos.entry_time)

    def apply_fill(self, symbol: str, side: str, quantity: int, filled_price: float, order_id: str = None):
        """Update portfolio state after a filled order and persist to DB."""
        existing = self.portfolio_state.positions.get(symbol)
        old_qty = existing.quantity if existing else 0
        old_entry = existing.entry_price if existing else 0.0

        friction_rate = 0.0005
        trade_value = quantity * filled_price
        friction_cost = trade_value * friction_rate

        new_qty, new_entry, cash_delta, _ = compute_fill(old_qty, old_entry, side, quantity, filled_price)
        
        self.portfolio_state.cash += (cash_delta - friction_cost)

        if new_qty == 0:
            self.portfolio_state.positions.pop(symbol, None)
            # Keep DB in sync -- otherwise a flattened symbol leaves a stale
            # row that the next close_for_user / reconcile would act on.
            db.save_position(self.user_id, symbol, 0, 0.0, 0.0, "")
        elif existing:
            existing.quantity = new_qty
            existing.entry_price = new_entry
            existing.current_price = filled_price
        else:
            self.portfolio_state.positions[symbol] = Position(
                symbol=symbol,
                quantity=new_qty,
                entry_price=new_entry,
                current_price=filled_price,
                entry_time=datetime.now().isoformat(),
            )

        self.portfolio_state.total_trades += 1
        db.record_trade(self.user_id, symbol, side, quantity, filled_price, order_id=order_id)
        
    def process_symbol(self, symbol: str) -> Dict:
        print(f"\n{'=' * 70}")
        print(f"Processing {symbol}")
        print(f"{'=' * 70}")

        technical_analysis = self.technical_agent.analyze(symbol)
        technical_analysis["symbol"] = symbol
        print(f"[Technical] Signal={technical_analysis.get('signal')} confidence={technical_analysis.get('confidence')}")

        sentiment_analysis = self.sentiment_agent.analyze(symbol)
        print(f"[Sentiment] Score={sentiment_analysis.get('sentiment_score', 0):+.2f}")

        current_price = technical_analysis["current_price"]
        volatility = technical_analysis["volatility"]

        risk_assessment = self.risk_agent.assess(
            technical_analysis,
            self.portfolio_state,
            current_price,
            volatility,
            symbol=symbol,
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
            side = technical_analysis.get("signal", "HOLD")
            order = self.execution_agent.execute_trade(
                symbol, side, quantity, current_price,
                api_key=self.alpaca_key,
                api_secret=self.alpaca_secret,
                strategy=execution_decision.get("execution_strategy", "MARKET"),
                stop_loss=risk_assessment.get("stop_loss"),
                take_profit=risk_assessment.get("take_profit"),
            )

            if order:
                filled_price = order.get("filled_avg_price") or current_price
                self.apply_fill(symbol, side, quantity, filled_price, order.get("order_id"))
                self.backtester.record_trade(
                    datetime.now().strftime("%Y-%m-%d"),
                    symbol, side, quantity, filled_price,
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

    def run_trading_cycle(self, symbols: List[str] = None) -> List[Dict]:
        # If no symbols passed, load from DB; fall back to default list
        if not symbols:
            symbols = db.get_user_symbols(self.user_id)
        if not symbols:
            symbols = ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "XOM", "KO"]

        print(f"\n{'#' * 70}")
        print(f"Starting Trading Cycle - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"User: {self.user_id} | Symbols: {symbols}")
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


def load_symbols() -> List[str]:
    """Load trading symbols from CLI args, or fall back to TRADING_SYMBOLS in .env."""
    import sys
    if len(sys.argv) > 1:
        symbols = [s.strip().upper() for s in " ".join(sys.argv[1:]).replace(",", " ").split() if s.strip()]
        if symbols:
            return symbols
    env_symbols = os.getenv("TRADING_SYMBOLS", "")
    if env_symbols:
        return [s.strip().upper() for s in env_symbols.split(",") if s.strip()]
    return ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "XOM", "KO"]


if __name__ == "__main__":
    load_dotenv()
    api_key = os.getenv("OPENROUTER_API_KEY")
    symbols = load_symbols()
    print(f"Trading symbols: {symbols}")

    user_id = os.getenv("TRADING_USER_ID", "default")
    # CLI bootstrap: ensure DB exists and a default user is provisioned. Production
    # paths (FastAPI, scheduler) must not rely on this -- they go through register.
    db.init_db()
    if db.get_user(user_id) is None:
        db.create_user(user_id, user_id)
    orchestrator = TradingOrchestrator(api_key=api_key, user_id=user_id, initial_capital=100000)

    # If symbols passed via CLI or .env, save them to DB for this user
    if symbols:
        db.set_user_symbols(user_id, symbols)

    results = orchestrator.run_trading_cycle()

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
        print(f"  Risk Level: {result['risk_assessment'].get('risk_level', 'N/A')}")
        print(f"  Executed: {'Yes' if result['order'] else 'No'}")
        if result["order"]:
            print(f"  Order: {result['order']}")

    orchestrator.backtester.export_trades()
    orchestrator.backtester.export_portfolio_history()

    report = orchestrator.backtester.get_report()
    with open("outputs/backtest_metrics.json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("\nBacktest report saved to outputs/backtest_metrics.json")
