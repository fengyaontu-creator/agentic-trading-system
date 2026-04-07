"""
param_optimizer.py -- AI-driven trading parameter optimization.

Before each analyze session, this module uses LLM reasoning to generate
optimal trading parameters based on:
  1. User's risk preference (conservative / moderate / aggressive)
  2. Recent market volatility for the user's watchlist
  3. Recent trade history and performance
  4. Current market sentiment

The generated parameters are saved to the user's DB settings so that
the regular analyze → trade → close pipeline uses them automatically.
"""

import json
import logging
import os
from typing import Dict, List, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

import database as db
from data_tools import fetch_market_data
from sentiment_tools import get_market_sentiment

log = logging.getLogger(__name__)

# Maps user-facing risk preference to a guidance range for the LLM
_RISK_PROFILES = {
    "conservative": {
        "description": "Minimize drawdowns, smaller positions, tighter stops",
        "risk_per_trade_range": [0.005, 0.015],
        "max_concentration_range": [0.05, 0.08],
        "stop_loss_multiplier_range": [1.0, 2.0],
        "take_profit_pct_range": [0.02, 0.04],
        "min_confidence_range": [0.4, 0.6],
        "trailing_stop_high_profit_range": [0.06, 0.10],
        "trailing_stop_low_profit_range": [0.03, 0.05],
        "trailing_stop_cushion_range": [0.01, 0.03],
        "trailing_stop_lock_pct_range": [0.01, 0.02],
    },
    "moderate": {
        "description": "Balanced risk/reward, standard positions",
        "risk_per_trade_range": [0.015, 0.03],
        "max_concentration_range": [0.08, 0.12],
        "stop_loss_multiplier_range": [1.5, 2.5],
        "take_profit_pct_range": [0.03, 0.06],
        "min_confidence_range": [0.3, 0.5],
        "trailing_stop_high_profit_range": [0.08, 0.12],
        "trailing_stop_low_profit_range": [0.04, 0.06],
        "trailing_stop_cushion_range": [0.02, 0.04],
        "trailing_stop_lock_pct_range": [0.015, 0.025],
    },
    "aggressive": {
        "description": "Maximize gains, larger positions, wider stops",
        "risk_per_trade_range": [0.03, 0.05],
        "max_concentration_range": [0.12, 0.20],
        "stop_loss_multiplier_range": [2.0, 3.5],
        "take_profit_pct_range": [0.05, 0.10],
        "min_confidence_range": [0.2, 0.4],
        "trailing_stop_high_profit_range": [0.10, 0.15],
        "trailing_stop_low_profit_range": [0.05, 0.08],
        "trailing_stop_cushion_range": [0.03, 0.05],
        "trailing_stop_lock_pct_range": [0.02, 0.03],
    },
}

_PARAM_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a quantitative trading parameter optimizer.
Given a user's risk preference, their recent trading performance, current market conditions,
and sentiment data, output the optimal trading parameters as JSON.

You MUST output ONLY valid JSON with these exact keys:
- risk_per_trade (float): max portfolio % loss per trade
- max_concentration (float): max % of portfolio in one stock
- stop_loss_multiplier (float): volatility multiplier for stop-loss distance
- take_profit_pct (float): take-profit target as a percentage
- min_confidence (float): minimum signal confidence to trade
- trailing_stop_high_profit (float): profit threshold for aggressive trailing stop
- trailing_stop_low_profit (float): profit threshold for moderate trailing stop
- trailing_stop_cushion (float): cushion below profit for aggressive trail
- trailing_stop_lock_pct (float): locked-in profit for moderate trail
- reasoning (string): brief explanation of why you chose these values

Each parameter MUST be within the allowed range provided.
Consider the market conditions: in high volatility, use wider stops and smaller positions;
in low volatility, you can tighten stops and increase positions."""),
    ("human", """{input}"""),
])


def _gather_market_context(symbols: List[str]) -> Dict:
    """Collect recent volatility and sentiment for the user's watchlist."""
    volatilities = []
    sentiments = []

    for sym in symbols[:5]:  # Limit to 5 to control API costs
        try:
            raw = fetch_market_data.invoke({"symbol": sym})
            data = json.loads(raw) if isinstance(raw, str) else raw
            vol = float(data.get("volatility", 0.0))
            if vol > 0:
                volatilities.append(vol)
        except Exception as exc:
            log.warning(f"[PARAM_OPT] Failed to fetch market data for {sym}: {exc}")

        try:
            sent_raw = get_market_sentiment.invoke({"symbol": sym})
            sent = json.loads(sent_raw) if isinstance(sent_raw, str) else sent_raw
            score = float(sent.get("sentiment_score", 0.0))
            sentiments.append(score)
        except Exception as exc:
            log.warning(f"[PARAM_OPT] Failed to fetch sentiment for {sym}: {exc}")

    avg_vol = sum(volatilities) / len(volatilities) if volatilities else 0.02
    avg_sent = sum(sentiments) / len(sentiments) if sentiments else 0.0

    return {
        "avg_volatility": round(avg_vol, 4),
        "avg_sentiment": round(avg_sent, 2),
        "num_symbols": len(symbols),
        "vol_regime": "HIGH" if avg_vol > 0.03 else "MEDIUM" if avg_vol > 0.015 else "LOW",
        "sentiment_regime": "BEARISH" if avg_sent < -0.3 else "BULLISH" if avg_sent > 0.3 else "NEUTRAL",
    }


def _summarize_trade_history(user_id: str) -> Dict:
    """Summarize recent trade performance."""
    trades = db.get_trade_history(user_id, limit=50)
    if not trades:
        return {"total_trades": 0, "summary": "No trade history yet"}

    portfolio = db.load_portfolio(user_id)
    portfolio_value = portfolio.get("portfolio_value", 100000) if portfolio else 100000
    cash = portfolio.get("cash", 100000) if portfolio else 100000

    return {
        "total_trades": len(trades),
        "portfolio_value": round(portfolio_value, 2),
        "cash": round(cash, 2),
        "return_pct": round((portfolio_value - 100000) / 100000 * 100, 2),
    }


def optimize_params_for_user(user_id: str, api_key: str) -> Optional[Dict]:
    """Generate AI-optimized trading parameters for a user.

    Args:
        user_id: The user to optimize for.
        api_key: OpenRouter API key for LLM calls.

    Returns:
        Dict of optimized parameters, or None on failure.
    """
    settings = db.load_user_settings(user_id)
    risk_pref = settings.get("risk_preference", "moderate")
    profile = _RISK_PROFILES.get(risk_pref, _RISK_PROFILES["moderate"])

    symbols = db.get_user_symbols(user_id)
    if not symbols:
        log.info(f"[PARAM_OPT] {user_id} has no symbols, using defaults")
        db.set_param_optimization_status(user_id, "skipped", "no symbols in watchlist")
        return None

    # Gather context
    market_ctx = _gather_market_context(symbols)
    trade_summary = _summarize_trade_history(user_id)

    input_text = f"""User risk preference: {risk_pref} ({profile['description']})

Market conditions:
- Average volatility: {market_ctx['avg_volatility']} ({market_ctx['vol_regime']})
- Average sentiment: {market_ctx['avg_sentiment']} ({market_ctx['sentiment_regime']})
- Watchlist size: {market_ctx['num_symbols']} symbols

Trade history:
- Total trades: {trade_summary['total_trades']}
- Portfolio value: ${trade_summary.get('portfolio_value', 100000):,.2f}
- Cash: ${trade_summary.get('cash', 100000):,.2f}
- Return: {trade_summary.get('return_pct', 0):.2f}%

Parameter ranges (you MUST stay within these):
- risk_per_trade: {profile['risk_per_trade_range']}
- max_concentration: {profile['max_concentration_range']}
- stop_loss_multiplier: {profile['stop_loss_multiplier_range']}
- take_profit_pct: {profile['take_profit_pct_range']}
- min_confidence: {profile['min_confidence_range']}
- trailing_stop_high_profit: {profile['trailing_stop_high_profit_range']}
- trailing_stop_low_profit: {profile['trailing_stop_low_profit_range']}
- trailing_stop_cushion: {profile['trailing_stop_cushion_range']}
- trailing_stop_lock_pct: {profile['trailing_stop_lock_pct_range']}

Output only valid JSON."""

    try:
        llm = ChatOpenAI(
            model="anthropic/claude-sonnet-4-6",
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        chain = _PARAM_PROMPT | llm
        response = chain.invoke({"input": input_text})

        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in content:
            content = content.split("```", 1)[1].split("```", 1)[0]

        params = json.loads(content.strip())

        # Clamp values to allowed ranges
        for key in profile:
            if key == "description":
                continue
            param_name = key.replace("_range", "")
            if param_name in params:
                lo, hi = profile[key]
                params[param_name] = round(max(lo, min(hi, float(params[param_name]))), 4)

        reasoning = params.pop("reasoning", "")
        log.info(f"[PARAM_OPT] {user_id} -> {json.dumps(params)} | {reasoning}")

        # Save the optimized parameters while preserving non-optimized user choices.
        db_params = {
            k: v for k, v in params.items()
            if k in (
                "risk_per_trade",
                "max_concentration",
                "stop_loss_multiplier",
                "take_profit_pct",
                "min_confidence",
                "trailing_stop_high_profit",
                "trailing_stop_low_profit",
                "trailing_stop_cushion",
                "trailing_stop_lock_pct",
            )
        }
        db_params["strategy"] = settings.get("strategy", "intraday")
        db_params["risk_preference"] = risk_pref
        db.save_user_settings(user_id, **db_params)
        db.set_param_optimization_status(user_id, "ok", None)

        return params

    except Exception as exc:
        log.error(f"[PARAM_OPT] {user_id} failed: {exc}", exc_info=True)
        try:
            db.set_param_optimization_status(user_id, "failed", str(exc)[:200])
        except Exception:
            pass
        return None


def optimize_all_users(api_key: str):
    """Run parameter optimization for all registered users."""
    users = db.list_users()
    for user in users:
        user_id = user["user_id"]
        try:
            result = optimize_params_for_user(user_id, api_key)
            if result:
                log.info(f"[PARAM_OPT] {user_id} optimized successfully")
            else:
                log.info(f"[PARAM_OPT] {user_id} skipped (no symbols or failed)")
        except Exception as exc:
            log.error(f"[PARAM_OPT] {user_id} error: {exc}", exc_info=True)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Set OPENROUTER_API_KEY in .env")
    else:
        optimize_all_users(api_key)
