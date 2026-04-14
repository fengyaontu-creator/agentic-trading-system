"""Telegram binding and trade-notification helpers."""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import requests

import database as db

log = logging.getLogger(__name__)

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_TTL_MINUTES = 10
_BOT_USERNAME_CACHE: Optional[str] = None
_BOT_USERNAME_CACHE_AT: Optional[datetime] = None
_BOT_USERNAME_CACHE_TTL = timedelta(minutes=30)


def _normalize_app_url(value: str) -> str:
    """Return a clickable app URL even when env vars contain a bare host."""
    candidate = value.strip().rstrip("/")
    if not candidate:
        return ""
    parsed = urlparse(candidate)
    if parsed.scheme and parsed.netloc:
        return candidate
    if parsed.scheme and not parsed.netloc:
        return candidate
    return f"http://{candidate}"


def _app_url() -> str:
    """Best-effort frontend URL included in reminder messages."""
    for key in ("APP_URL", "FRONTEND_URL", "PUBLIC_APP_URL"):
        value = os.getenv(key, "").strip()
        if value:
            return _normalize_app_url(value)
    return _normalize_app_url("localhost:5173")


def get_bot_token() -> Optional[str]:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    return token or None


def is_bot_configured() -> bool:
    return bool(get_bot_token())


def _api_url(method: str, token: Optional[str] = None) -> str:
    bot_token = token or get_bot_token()
    if not bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not configured")
    return f"https://api.telegram.org/bot{bot_token}/{method}"


def _telegram_get(method: str, params: Optional[dict] = None) -> dict:
    response = requests.get(_api_url(method), params=params or {}, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description") or f"Telegram {method} failed")
    return payload


def _telegram_post(method: str, data: dict) -> dict:
    response = requests.post(_api_url(method), data=data, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(payload.get("description") or f"Telegram {method} failed")
    return payload


def get_bot_username(refresh: bool = False) -> Optional[str]:
    if not is_bot_configured():
        return None
    global _BOT_USERNAME_CACHE, _BOT_USERNAME_CACHE_AT
    if not refresh and _BOT_USERNAME_CACHE_AT:
        if datetime.now(timezone.utc) - _BOT_USERNAME_CACHE_AT < _BOT_USERNAME_CACHE_TTL:
            return _BOT_USERNAME_CACHE
    try:
        profile = _telegram_get("getMe")
        username = profile.get("result", {}).get("username")
        _BOT_USERNAME_CACHE = str(username) if username else None
        _BOT_USERNAME_CACHE_AT = datetime.now(timezone.utc)
        return _BOT_USERNAME_CACHE
    except Exception as exc:
        log.warning("[TELEGRAM] getMe failed: %s", exc)
        return _BOT_USERNAME_CACHE


def _generate_bind_code(length: int = 8) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def create_bind_code(user_id: str) -> dict:
    if not is_bot_configured():
        raise RuntimeError("Telegram bot is not configured on the server")
    code = _generate_bind_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_CODE_TTL_MINUTES)
    db.save_telegram_bind_code(user_id, code, expires_at.isoformat())
    return {
        "code": code,
        "expires_at": expires_at.isoformat(),
        "bot_username": get_bot_username(),
    }


def _extract_start_code(text: str) -> Optional[str]:
    if not text:
        return None
    stripped = text.strip()
    if not stripped:
        return None
    parts = stripped.split()
    if len(parts) == 1 and not parts[0].startswith("/"):
        return parts[0].strip().upper()
    if parts[0].startswith("/start") and len(parts) >= 2:
        return parts[1].strip().upper()
    return None


def _find_chat_for_code(code: str) -> Optional[dict]:
    updates = _telegram_get("getUpdates", params={"limit": 100, "timeout": 0})
    target = code.strip().upper()
    for update in reversed(updates.get("result", [])):
        message = update.get("message") or {}
        candidate = _extract_start_code(message.get("text", ""))
        if candidate != target:
            continue
        chat = message.get("chat") or {}
        user = message.get("from") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        return {
            "chat_id": str(chat_id),
            "chat_username": user.get("username"),
            "chat_first_name": user.get("first_name") or chat.get("first_name"),
        }
    return None


def confirm_bind_code(user_id: str) -> dict:
    pending = db.get_telegram_bind_code(user_id)
    if not pending:
        raise ValueError("No pending Telegram bind code. Generate a new code first.")

    expires_at = pending.get("expires_at")
    if expires_at and datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
        db.clear_telegram_bind_code(user_id)
        raise ValueError("Telegram bind code expired. Generate a new code and try again.")

    match = _find_chat_for_code(pending["code"])
    if not match:
        raise LookupError("No matching Telegram /start code found yet.")

    db.save_telegram_binding(
        user_id,
        match["chat_id"],
        chat_username=match.get("chat_username"),
        chat_first_name=match.get("chat_first_name"),
    )
    return match


def send_message(chat_id: str, text: str) -> dict:
    return _telegram_post(
        "sendMessage",
        {
            "chat_id": str(chat_id),
            "text": text,
            "disable_web_page_preview": "true",
        },
    )


def send_test_message(user_id: str) -> dict:
    """Send a one-off confirmation message to the bound Telegram chat."""
    binding = db.get_telegram_binding(user_id)
    if not binding:
        raise ValueError("Telegram notifications are not linked yet.")
    username = get_bot_username()
    text = "\n".join(
        [
            "AlphaPing test message",
            "Telegram notifications are connected and ready.",
            f"User: {user_id}",
            f"Bot: @{username}" if username else "Bot: configured",
            f"Time (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
        ]
    )
    return send_message(binding["chat_id"], text)


def send_binding_success_message(user_id: str) -> dict:
    """Send a welcome message immediately after Telegram binding succeeds."""
    binding = db.get_telegram_binding(user_id)
    if not binding:
        raise ValueError("Telegram notifications are not linked yet.")
    username = get_bot_username()
    text = "\n".join(
        [
            "Telegram binding successful",
            "You will now receive BUY and SELL execution alerts here.",
            f"User: {user_id}",
            f"Bot: @{username}" if username else "Bot: configured",
            "Congratulations, your notifications are ready.",
        ]
    )
    return send_message(binding["chat_id"], text)


def _format_fill_message(
    user_id: str,
    session: str,
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    order_id: Optional[str],
) -> str:
    action = "Trade executed" if session == "trade" else "Position closed"
    lines = [
        f"{action} for {user_id}",
        f"{side} {quantity} {symbol} @ ${float(price):,.2f}",
    ]
    if order_id:
        lines.append(f"Order ID: {order_id}")
    lines.append(f"Session: {session}")
    lines.append(f"Time (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


def _mode_label(mode: str) -> str:
    return "🤖 Auto" if mode == "auto" else "👤 Manual"


def _format_signal_line(sig: dict) -> str:
    confidence = float(sig.get("confidence", 0.0)) * 100
    return f"- {sig.get('symbol', '?')}: {sig.get('signal', '?')} ({confidence:.0f}%)"


def _format_position_line(pos: dict) -> str:
    qty = int(pos.get("quantity", 0))
    side = "LONG" if qty > 0 else "SHORT"
    return f"- {pos.get('symbol', '?')}: {side} {abs(qty)}"


def _join_or_none(lines: list[str], empty_text: str) -> list[str]:
    return lines if lines else [empty_text]


def notify_daily_signals(
    user_id: str,
    signals: list[dict],
    positions: list[dict],
    mode: str,
) -> bool:
    """Send the 07:30 ET summary for today's open and close candidates."""
    binding = db.get_telegram_binding(user_id)
    if not binding or not is_bot_configured():
        return False

    open_lines = _join_or_none(
        [_format_signal_line(sig) for sig in signals],
        "- No actionable open signals today.",
    )
    close_lines = _join_or_none(
        [_format_position_line(pos) for pos in positions],
        "- No current positions to review for close.",
    )

    if mode == "auto":
        action_line = "These will auto-execute unless you STOP them before 09:50 ET / 15:30 ET."
    else:
        action_line = "Please APPROVE the trades you want before 09:50 ET / 15:30 ET."

    text = "\n".join(
        [
            f"{_mode_label(mode)} daily trading plan",
            "",
            "Open candidates:",
            *open_lines,
            "",
            "Close candidates:",
            *close_lines,
            "",
            action_line,
            f"Open app to review: {_app_url()}",
        ]
    )

    try:
        send_message(binding["chat_id"], text)
        return True
    except Exception as exc:
        log.warning("[TELEGRAM] daily summary failed for %s: %s", user_id, exc)
        return False


def notify_close_reminder(
    user_id: str,
    positions: list[dict],
    mode: str,
) -> bool:
    """Send the 14:30 ET close-session reminder."""
    binding = db.get_telegram_binding(user_id)
    if not binding or not is_bot_configured():
        return False

    lines = _join_or_none(
        [_format_position_line(pos) for pos in positions],
        "- No positions queued for close review.",
    )

    if mode == "auto":
        action_line = "You can STOP any of these before 15:30 ET."
    else:
        action_line = "You must APPROVE the positions you want closed before 15:30 ET."

    text = "\n".join(
        [
            f"{_mode_label(mode)} close reminder",
            "",
            "Positions for the 15:30 ET close session:",
            *lines,
            "",
            action_line,
            f"Open app to review: {_app_url()}",
        ]
    )

    try:
        send_message(binding["chat_id"], text)
        return True
    except Exception as exc:
        log.warning("[TELEGRAM] close reminder failed for %s: %s", user_id, exc)
        return False


def notify_trade_fill(
    user_id: str,
    session: str,
    symbol: str,
    side: str,
    quantity: int,
    price: float,
    order_id: Optional[str] = None,
) -> bool:
    """Send a best-effort Telegram fill notification. Failures never raise."""
    binding = db.get_telegram_binding(user_id)
    if not binding or not is_bot_configured():
        return False

    try:
        send_message(
            binding["chat_id"],
            _format_fill_message(
                user_id=user_id,
                session=session,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                order_id=order_id,
            ),
        )
        return True
    except Exception as exc:
        log.warning(
            "[TELEGRAM] notify failed for %s/%s %s x%s: %s",
            user_id,
            symbol,
            side,
            quantity,
            exc,
        )
        return False
