"""
scheduler.py — Trading cycle scheduler

Three sessions per day (all times ET / New York):

    07:30  analyze  — fetch data, run LLM analysis, save signals to DB
    09:30  trade    — read today's signals from DB, execute open orders
    15:30  trade    — read today's signals from DB, execute close orders

If analysis has not completed by 09:30, get_pending_signals() returns empty
and the trade session safely skips — no analysis, no trade.

Crontab (Singapore time, summer/DST, UTC+8):
    30 19 * * 1-5  cd /path/to/project && python src/scheduler.py --session analyze
    30 21 * * 1-5  cd /path/to/project && python src/scheduler.py --session trade
    30  3 * * 2-6  cd /path/to/project && python src/scheduler.py --session trade
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

import database as db
from agentic_trading import TradingOrchestrator
from data_tools import fetch_market_data
from sentiment_tools import get_market_sentiment
import json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "..", "scheduler.log"),
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger(__name__)


# ── Analyze session ───────────────────────────────────────────────────────────

def analyze_for_user(user: dict, api_key: str) -> dict:
    """Run analysis for all of a user's symbols and save signals to DB."""
    user_id = user["user_id"]
    symbols = db.get_user_symbols(user_id)
    if not symbols:
        return {"user_id": user_id, "status": "skipped", "reason": "no symbols"}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    orchestrator = TradingOrchestrator(api_key=api_key, user_id=user_id)
    saved = 0

    for symbol in symbols:
        try:
            technical = orchestrator.technical_agent.analyze(symbol)
            sentiment = orchestrator.sentiment_agent.analyze(symbol)

            db.save_signal(
                user_id=user_id,
                symbol=symbol,
                date=today,
                signal=technical.get("signal", "HOLD"),
                confidence=float(technical.get("confidence", 0.0)),
                reasoning=technical.get("reasoning", ""),
                technical_score=float(technical.get("technical_score", 0.0)),
                sentiment_score=float(sentiment.get("sentiment_score", 0.0)),
            )
            saved += 1
            log.info(f"[ANALYZE] {user_id}/{symbol} → {technical.get('signal')} ({technical.get('confidence', 0):.0%})")
        except Exception as exc:
            log.error(f"[ANALYZE] {user_id}/{symbol} failed: {exc}")

    return {"user_id": user_id, "status": "ok", "signals_saved": saved}


# ── Trade session ─────────────────────────────────────────────────────────────

def trade_for_user(user: dict, api_key: str) -> dict:
    """Read today's pending signals from DB and execute trades."""
    user_id = user["user_id"]

    creds = db.get_alpaca_credentials(user_id)
    if not creds:
        return {"user_id": user_id, "status": "skipped", "reason": "no alpaca credentials"}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pending = db.get_pending_signals(user_id, today)
    if not pending:
        log.info(f"[TRADE] {user_id} — no pending signals for {today}")
        return {"user_id": user_id, "status": "ok", "trades": 0}

    orchestrator = TradingOrchestrator(api_key=api_key, user_id=user_id)
    trades = 0

    for sig in pending:
        symbol = sig["symbol"]
        try:
            market_data = json.loads(fetch_market_data.invoke({"symbol": symbol}))
            current_price = float(market_data.get("current_price", 0.0))
            volatility = float(market_data.get("volatility", 0.0))

            risk = orchestrator.risk_agent.assess(
                {"signal": sig["signal"], "confidence": sig["confidence"]},
                orchestrator.portfolio_state,
                current_price,
                volatility,
                symbol=symbol,
            )

            if not risk.get("should_trade"):
                log.info(f"[TRADE] {user_id}/{symbol} — risk gate blocked")
                continue

            quantity = int(risk.get("position_size", 0))
            order = orchestrator.execution_agent.execute_trade(
                symbol=symbol,
                signal_type=sig["signal"],
                quantity=quantity,
                price=current_price,
                stop_loss=risk.get("stop_loss"),
                take_profit=risk.get("take_profit"),
                api_key=creds["api_key"],
                secret_key=creds["api_secret"],
            )

            if order:
                filled_price = order.get("filled_avg_price") or current_price
                db.record_trade(user_id, symbol, sig["signal"], quantity, filled_price, order.get("order_id"))
                db.mark_signal_executed(user_id, symbol, today)
                trades += 1
                log.info(f"[TRADE] {user_id}/{symbol} → {sig['signal']} x{quantity} @ {filled_price}")

        except Exception as exc:
            log.error(f"[TRADE] {user_id}/{symbol} failed: {exc}")

    return {"user_id": user_id, "status": "ok", "trades": trades}


# ── Run all users ─────────────────────────────────────────────────────────────

def run_all_users(session: str, max_workers: int = 4):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        log.error("OPENROUTER_API_KEY not set — aborting")
        sys.exit(1)

    db.init_db()
    users = db.list_users()
    if not users:
        log.info("No users registered yet — nothing to do")
        return

    log.info(f"=== Scheduler [{session.upper()}] {datetime.now(timezone.utc).isoformat()} ===")
    log.info(f"Running for {len(users)} user(s) with max_workers={max_workers}")

    worker_fn = analyze_for_user if session == "analyze" else trade_for_user

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(worker_fn, user, api_key): user["user_id"]
            for user in users
        }
        for future in as_completed(futures):
            results.append(future.result())

    ok      = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    errors  = [r for r in results if r["status"] == "error"]
    log.info(
        f"=== Done === ok={len(ok)} skipped={len(skipped)} errors={len(errors)}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run analysis or trading for all users")
    parser.add_argument(
        "--session",
        choices=["analyze", "trade"],
        default="analyze",
        help="'analyze' saves signals to DB; 'trade' executes pending signals",
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    run_all_users(session=args.session, max_workers=args.workers)
