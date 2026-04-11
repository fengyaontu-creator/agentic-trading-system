"""
services/trading_sessions.py -- Business logic for each scheduler session.

    analyze  -- fetch data, run LLM analysis, save signals to DB
    trade    -- read today's signals from DB, execute open orders
    remind   -- send pre-close Telegram reminder for approved positions
    close    -- flatten approved open positions for intraday users (EOD)
"""

import json
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import database as db
from agentic_trading import TradingOrchestrator
from broker_alpaca import reconcile_positions
from data_tools import fetch_market_data
from telegram_service import (
    notify_trade_fill,
    notify_daily_signals,
    notify_close_reminder,
)

log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")


def is_market_open() -> bool:
    """Return True if current time is within US equity regular hours (Mon-Fri 09:30-16:00 ET)."""
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def _notify_fill_safe(**kwargs):
    """Best-effort notification wrapper; trade execution must not depend on it."""
    try:
        notify_trade_fill(**kwargs)
    except Exception as exc:
        log.warning("[TELEGRAM] fill notification crashed: %s", exc)


def _notify_daily_safe(**kwargs):
    try:
        notify_daily_signals(**kwargs)
    except Exception as exc:
        log.warning("[TELEGRAM] daily signals notification crashed: %s", exc)


def _notify_close_reminder_safe(**kwargs):
    try:
        notify_close_reminder(**kwargs)
    except Exception as exc:
        log.warning("[TELEGRAM] close reminder notification crashed: %s", exc)


# -- Analyze session -----------------------------------------------------------

def analyze_for_user(user: dict, api_key: str) -> dict:
    """Run analysis for all of a user's symbols and save signals to DB."""
    user_id = user["user_id"]

    # Users who have not chosen a control mode are skipped entirely. The
    # Settings page will force them to pick one before any session touches
    # their account. This is the enforcement point for the "must choose mode"
    # contract.
    mode = db.get_control_mode(user_id)
    if mode not in ("auto", "manual"):
        log.info(f"[ANALYZE] {user_id} -- control_mode not set, skipping")
        return {"user_id": user_id, "status": "skipped", "reason": "control_mode not set"}

    symbols = db.get_user_symbols(user_id)
    if not symbols:
        return {"user_id": user_id, "status": "skipped", "reason": "no symbols"}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    orchestrator = TradingOrchestrator(api_key=api_key, user_id=user_id)
    saved = 0

    # Manual users need close_approved reset to 0 each morning so pre-existing
    # positions require explicit review before the 15:30 ET close session.
    # Auto users get reset to 1 (matches the DB default; explicit for clarity).
    db.reset_close_approvals(user_id, default=1 if mode == "auto" else 0)

    default_approved = 1 if mode == "auto" else 0

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
                approved=default_approved,
            )
            saved += 1
            log.info(f"[ANALYZE] {user_id}/{symbol} -> {technical.get('signal')} ({technical.get('confidence', 0):.0%})")
        except Exception as exc:
            log.error(f"[ANALYZE] {user_id}/{symbol} failed: {exc}", exc_info=True)

    # Fire the first daily reminder (07:30 ET). Best-effort: telegram failures
    # must not block analysis results from being persisted.
    today_signals = db.get_signals(user_id, date=today)
    actionable_signals = [s for s in today_signals if s["signal"] in ("BUY", "SELL")]
    positions = db.load_positions(user_id)
    _notify_daily_safe(
        user_id=user_id,
        mode=mode,
        signals=actionable_signals,
        positions=positions,
    )

    return {"user_id": user_id, "status": "ok", "signals_saved": saved, "mode": mode}


# -- Trade session -------------------------------------------------------------

def trade_for_user(user: dict, api_key: str) -> dict:
    """Read today's pending signals from DB and execute trades."""
    user_id = user["user_id"]

    mode = db.get_control_mode(user_id)
    if mode not in ("auto", "manual"):
        log.info(f"[TRADE] {user_id} -- control_mode not set, skipping")
        return {"user_id": user_id, "status": "skipped", "reason": "control_mode not set"}

    if not is_market_open():
        log.info(f"[TRADE] {user_id} -- market closed, skipping")
        return {"user_id": user_id, "status": "ok", "trades": 0}

    creds = db.get_alpaca_credentials(user_id)
    if not creds:
        return {"user_id": user_id, "status": "skipped", "reason": "no alpaca credentials"}

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pending = db.get_pending_signals(user_id, today)
    if not pending:
        log.info(f"[TRADE] {user_id} -- no pending signals for {today}")
        return {"user_id": user_id, "status": "ok", "trades": 0}

    orchestrator = TradingOrchestrator(api_key=api_key, user_id=user_id)
    trades = 0

    for sig in pending:
        symbol = sig["symbol"]
        risk = None
        try:
            market_data = json.loads(fetch_market_data.invoke({"symbol": symbol}))
            current_price = float(market_data.get("current_price", 0.0))
            volatility = float(market_data.get("volatility", 0.0))

            technical_analysis = {"signal": sig["signal"], "confidence": sig["confidence"]}
            sentiment_analysis = {"sentiment_score": sig.get("sentiment_score", 0.0)}

            risk = orchestrator.risk_agent.assess(
                technical_analysis,
                orchestrator.portfolio_state,
                current_price,
                volatility,
                symbol=symbol,
            )

            if not risk.get("should_trade"):
                log.info(f"[TRADE] {user_id}/{symbol} -- risk gate blocked")
                continue

            execution = orchestrator.execution_agent.decide(
                technical_analysis, sentiment_analysis, risk,
            )
            if not execution.get("execute"):
                log.info(f"[TRADE] {user_id}/{symbol} -- execution decision blocked")
                continue

            quantity = int(risk.get("position_size", 0))
            existing = orchestrator.portfolio_state.positions.get(symbol)
            is_closing_trade = bool(
                existing and (
                    (existing.quantity > 0 and sig["signal"] == "SELL") or
                    (existing.quantity < 0 and sig["signal"] == "BUY")
                )
            )
            order = orchestrator.execution_agent.execute_trade(
                symbol=symbol,
                side=sig["signal"],
                quantity=quantity,
                price=current_price,
                api_key=creds["api_key"],
                api_secret=creds["api_secret"],
                stop_loss=risk.get("stop_loss"),
                take_profit=risk.get("take_profit"),
                attach_protection=not is_closing_trade,
            )

            if order:
                filled_price = order.get("filled_avg_price") or current_price
                orchestrator.apply_fill(
                    symbol, sig["signal"], quantity, filled_price, order.get("order_id"),
                )
                db.mark_signal_executed(user_id, symbol, today)
                # Manual users must also re-approve the 15:30 ET close. A new
                # position they just opened defaults to close_approved=0 so they
                # explicitly control end-of-day flatten per symbol.
                if mode == "manual" and not is_closing_trade:
                    db.set_position_close_approval(user_id, symbol, False)
                _notify_fill_safe(
                    user_id=user_id,
                    session="trade",
                    symbol=symbol,
                    side=sig["signal"],
                    quantity=quantity,
                    price=filled_price,
                    order_id=order.get("order_id"),
                )
                trades += 1
                log.info(f"[TRADE] {user_id}/{symbol} -> {sig['signal']} x{quantity} @ {filled_price}")

        except Exception as exc:
            quantity = int(risk.get("position_size", 0)) if risk else 0
            log.error(
                f"[TRADE] {user_id}/{symbol} failed: {exc} | "
                f"signal={sig.get('signal')}, quantity={quantity}",
                exc_info=True
            )

    orchestrator.update_portfolio_value()
    reconcile(user_id, creds)
    return {"user_id": user_id, "status": "ok", "trades": trades}


# -- Remind session -----------------------------------------------------------

def remind_for_user(user: dict, api_key: str) -> dict:
    """Send the 14:30 ET close reminder without mutating trading state."""
    del api_key  # Unused, kept for scheduler signature consistency.

    user_id = user["user_id"]
    mode = db.get_control_mode(user_id)
    if mode not in ("auto", "manual"):
        log.info(f"[REMIND] {user_id} -- control_mode not set, skipping")
        return {"user_id": user_id, "status": "skipped", "reason": "control_mode not set"}

    settings = db.load_user_settings(user_id)
    strategy = settings.get("strategy")
    if strategy != "intraday":
        log.info(f"[REMIND] {user_id} -- strategy={strategy!r}, skipping")
        return {"user_id": user_id, "status": "skipped", "reason": f"strategy={strategy!r} not 'intraday'"}

    positions = db.load_positions(user_id)
    if not positions:
        log.info(f"[REMIND] {user_id} -- no open positions")
        return {"user_id": user_id, "status": "ok", "reminded": False, "positions": 0}

    _notify_close_reminder_safe(
        user_id=user_id,
        mode=mode,
        positions=positions,
    )
    return {"user_id": user_id, "status": "ok", "reminded": True, "positions": len(positions)}


# -- Close session (EOD flatten) ----------------------------------------------

def close_for_user(user: dict, api_key: str) -> dict:
    """Close approved open positions for intraday users at end of day."""
    user_id = user["user_id"]

    now_et = datetime.now(ET)
    if now_et.weekday() >= 5:
        log.info(f"[CLOSE] {user_id} -- weekend, skipping")
        return {"user_id": user_id, "status": "ok", "trades": 0}

    mode = db.get_control_mode(user_id)
    if mode not in ("auto", "manual"):
        log.info(f"[CLOSE] {user_id} -- control_mode not set, skipping")
        return {"user_id": user_id, "status": "skipped", "reason": "control_mode not set"}

    settings = db.load_user_settings(user_id)
    strategy = settings.get("strategy")
    if strategy != "intraday":
        log.warning(
            f"[CLOSE] {user_id} -- strategy={strategy!r} is not 'intraday', "
            f"skipping EOD flatten (set strategy='intraday' to enable)"
        )
        return {
            "user_id": user_id,
            "status": "skipped",
            "reason": f"strategy={strategy!r} not 'intraday'",
            "trades": 0,
        }

    creds = db.get_alpaca_credentials(user_id)
    if not creds:
        return {"user_id": user_id, "status": "skipped", "reason": "no alpaca credentials"}

    positions = db.load_positions_for_close(user_id)
    if not positions:
        log.info(f"[CLOSE] {user_id} -- no approved positions to close")
        return {"user_id": user_id, "status": "ok", "trades": 0}

    orchestrator = TradingOrchestrator(api_key=api_key, user_id=user_id)
    trades = 0

    for pos in positions:
        symbol = pos["symbol"]
        qty = pos["quantity"]
        side = "SELL" if qty > 0 else "BUY"
        abs_qty = abs(qty)
        try:
            market_data = json.loads(fetch_market_data.invoke({"symbol": symbol}))
            current_price = float(market_data.get("current_price", 0.0))

            order = orchestrator.execution_agent.execute_trade(
                symbol=symbol,
                side=side,
                quantity=abs_qty,
                price=current_price,
                api_key=creds["api_key"],
                api_secret=creds["api_secret"],
                attach_protection=False,
            )
            if order:
                filled_price = order.get("filled_avg_price") or current_price
                orchestrator.apply_fill(symbol, side, abs_qty, filled_price, order.get("order_id"))
                _notify_fill_safe(
                    user_id=user_id,
                    session="close",
                    symbol=symbol,
                    side=side,
                    quantity=abs_qty,
                    price=filled_price,
                    order_id=order.get("order_id"),
                )
                trades += 1
                log.info(f"[CLOSE] {user_id}/{symbol} -> {side} x{abs_qty} @ {filled_price}")
        except Exception as exc:
            log.error(
                f"[CLOSE] {user_id}/{symbol} failed: {exc} | "
                f"side={side}, quantity={abs_qty}",
                exc_info=True
            )

    orchestrator.update_portfolio_value()
    reconcile(user_id, creds)
    return {"user_id": user_id, "status": "ok", "trades": trades}


# -- Reconciliation -----------------------------------------------------------

def reconcile(user_id: str, creds: dict):
    """Log any drift between broker and local DB positions."""
    try:
        result = reconcile_positions(user_id, creds["api_key"], creds["api_secret"])
        if not result["ok"]:
            for d in result["diffs"]:
                log.warning(
                    f"[RECONCILE] {user_id}/{d['symbol']} -- broker={d['broker_qty']} db={d['db_qty']}"
                )
        else:
            log.info(f"[RECONCILE] {user_id} -- positions in sync")
    except Exception as exc:
        log.error(f"[RECONCILE] {user_id} failed: {exc}", exc_info=True)
