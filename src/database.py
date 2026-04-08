"""
database.py -- SQLite persistence layer.

Sections:
    1. Core         -- encryption, connection, schema
    2. Users & auth -- registration, login, password hashing
    3. Settings, credentials & watchlist
    4. Portfolio & positions
    5. Trades & signals
"""

import sqlite3
import os
import hashlib
from datetime import datetime
from typing import Dict, List, Optional

from cryptography.fernet import Fernet


DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "trading.db"))


def _get_fernet() -> Fernet:
    """Load encryption key from env. Generate and print one if missing."""
    key = os.getenv("DB_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "DB_ENCRYPTION_KEY not set. Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
            "and add it to your .env file."
        )
    return Fernet(key.encode())


def encrypt(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    # SQLite ships with FK enforcement OFF by default and the PRAGMA is
    # per-connection, so the FOREIGN KEY clauses in init_db() are decorative
    # unless we set this on every connection. Must run outside a transaction;
    # doing it right after connect() is the canonical place.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id          TEXT PRIMARY KEY,
                username         TEXT UNIQUE NOT NULL,
                password_hash    TEXT,
                alpaca_key_enc   TEXT,
                alpaca_secret_enc TEXT,
                telegram_chat_id TEXT,
                telegram_chat_username TEXT,
                telegram_chat_first_name TEXT,
                telegram_bind_code TEXT,
                telegram_bind_expires_at TEXT,
                created_at       TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_symbols (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL,
                symbol     TEXT NOT NULL,
                added_at   TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, symbol)
            );

            CREATE TABLE IF NOT EXISTS portfolio_state (
                user_id         TEXT PRIMARY KEY,
                cash            REAL NOT NULL,
                portfolio_value REAL NOT NULL,
                total_trades    INTEGER NOT NULL DEFAULT 0,
                updated_at      TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS positions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       TEXT NOT NULL,
                symbol        TEXT NOT NULL,
                quantity      INTEGER NOT NULL,
                entry_price   REAL NOT NULL,
                current_price REAL NOT NULL,
                entry_time    TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, symbol)
            );

            CREATE TABLE IF NOT EXISTS trades (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT NOT NULL,
                symbol     TEXT NOT NULL,
                side       TEXT NOT NULL,
                quantity   INTEGER NOT NULL,
                price      REAL NOT NULL,
                timestamp  TEXT NOT NULL,
                order_id   TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                user_id              TEXT PRIMARY KEY,
                risk_per_trade       REAL NOT NULL DEFAULT 0.02,
                max_concentration    REAL NOT NULL DEFAULT 0.10,
                stop_loss_multiplier REAL NOT NULL DEFAULT 2.0,
                take_profit_pct      REAL NOT NULL DEFAULT 0.05,
                min_confidence       REAL NOT NULL DEFAULT 0.3,
                trailing_stop_high_profit REAL NOT NULL DEFAULT 0.10,
                trailing_stop_low_profit  REAL NOT NULL DEFAULT 0.05,
                trailing_stop_cushion     REAL NOT NULL DEFAULT 0.03,
                trailing_stop_lock_pct    REAL NOT NULL DEFAULT 0.02,
                strategy             TEXT NOT NULL DEFAULT 'intraday',
                risk_preference      TEXT NOT NULL DEFAULT 'moderate',
                last_param_update_at     TEXT,
                last_param_update_status TEXT,
                last_param_update_reason TEXT,
                updated_at           TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS signals (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          TEXT NOT NULL,
                symbol           TEXT NOT NULL,
                date             TEXT NOT NULL,
                signal           TEXT NOT NULL,
                confidence       REAL NOT NULL,
                reasoning        TEXT,
                technical_score  REAL,
                sentiment_score  REAL,
                executed         INTEGER NOT NULL DEFAULT 0,
                created_at       TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                UNIQUE(user_id, symbol, date)
            );
        """)

    # Migrations for existing databases
    with get_conn() as conn:
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN risk_preference TEXT NOT NULL DEFAULT 'moderate'")
        except Exception:
            pass  # Column already exists
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN trailing_stop_high_profit REAL NOT NULL DEFAULT 0.10")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN trailing_stop_low_profit REAL NOT NULL DEFAULT 0.05")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN trailing_stop_cushion REAL NOT NULL DEFAULT 0.03")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN trailing_stop_lock_pct REAL NOT NULL DEFAULT 0.02")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN last_param_update_at TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN last_param_update_status TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE user_settings ADD COLUMN last_param_update_reason TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN telegram_chat_id TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN telegram_chat_username TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN telegram_chat_first_name TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN telegram_bind_code TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE users ADD COLUMN telegram_bind_expires_at TEXT")
        except Exception:
            pass


# =============================================================================
# Users & auth
# =============================================================================

def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + "$" + h.hex()


def _verify_password(password: str, stored: str) -> bool:
    if "$" not in stored:
        # Legacy sha256 migration path
        return hashlib.sha256(password.encode()).hexdigest() == stored
    salt_hex, hash_hex = stored.split("$", 1)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 100_000)
    return h.hex() == hash_hex


def create_user(user_id: str, username: str, password: str = "") -> Dict:
    """Create a new user with default portfolio + settings rows.

    Raises sqlite3.IntegrityError if user_id or username already exists.
    Callers (api.py register, app.py register) MUST catch this -- the previous
    INSERT OR IGNORE behavior silently swallowed PK conflicts and let the API
    mint a JWT bound to the existing account, which is an authn bypass.

    The portfolio_state and user_settings inserts stay as INSERT OR IGNORE so
    that the function is still safe to re-run during partial-state recovery,
    but the users insert is now strict. All three inserts run in one
    transaction, so if the users insert raises, the dependent rows roll back
    automatically.
    """
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, _hash_password(password), datetime.utcnow().isoformat()),
        )
        # Init portfolio with $100k if not exists
        conn.execute(
            """INSERT OR IGNORE INTO portfolio_state
               (user_id, cash, portfolio_value, total_trades, updated_at)
               VALUES (?, 100000.0, 100000.0, 0, ?)""",
            (user_id, datetime.utcnow().isoformat()),
        )
        # Init default trading params if not exists
        conn.execute(
            """INSERT OR IGNORE INTO user_settings
               (user_id, risk_per_trade, max_concentration, stop_loss_multiplier,
                take_profit_pct, min_confidence, trailing_stop_high_profit,
                trailing_stop_low_profit, trailing_stop_cushion, trailing_stop_lock_pct,
                strategy, risk_preference, updated_at)
               VALUES (?, 0.02, 0.10, 2.0, 0.05, 0.3, 0.10, 0.05, 0.03, 0.02, 'intraday', 'moderate', ?)""",
            (user_id, datetime.utcnow().isoformat()),
        )
    return get_user(user_id)


def get_user(user_id: str) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, username, created_at FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, username, created_at FROM users WHERE username = ?", (username,)
        ).fetchone()
        return dict(row) if row else None


def verify_user(username: str, password: str) -> Optional[Dict]:
    """Return user dict if credentials match, else None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, username, password_hash, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row or not _verify_password(password, row["password_hash"]):
        return None
    return {"user_id": row["user_id"], "username": row["username"], "created_at": row["created_at"]}


def list_users() -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, username, created_at FROM users ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


# =============================================================================
# Settings, credentials & watchlist
# =============================================================================

def save_alpaca_credentials(user_id: str, api_key: str, api_secret: str):
    """Encrypt and store the user's Alpaca credentials."""
    with get_conn() as conn:
        if not api_key.strip() and not api_secret.strip():
            conn.execute(
                """UPDATE users SET alpaca_key_enc = NULL, alpaca_secret_enc = NULL
                   WHERE user_id = ?""",
                (user_id,),
            )
            return
        conn.execute(
            """UPDATE users SET alpaca_key_enc = ?, alpaca_secret_enc = ?
               WHERE user_id = ?""",
            (encrypt(api_key), encrypt(api_secret), user_id),
        )


def get_alpaca_credentials(user_id: str) -> Optional[Dict]:
    """Return decrypted Alpaca credentials, or None if not set."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT alpaca_key_enc, alpaca_secret_enc FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row or not row["alpaca_key_enc"]:
        return None
    api_key = decrypt(row["alpaca_key_enc"])
    api_secret = decrypt(row["alpaca_secret_enc"])
    if not api_key.strip() or not api_secret.strip():
        return None
    return {
        "api_key": api_key,
        "api_secret": api_secret,
    }


def save_telegram_binding(
    user_id: str,
    chat_id: str,
    chat_username: Optional[str] = None,
    chat_first_name: Optional[str] = None,
):
    """Persist a user's Telegram chat binding and clear any pending bind code."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE users
               SET telegram_chat_id = ?,
                   telegram_chat_username = ?,
                   telegram_chat_first_name = ?,
                   telegram_bind_code = NULL,
                   telegram_bind_expires_at = NULL
               WHERE user_id = ?""",
            (str(chat_id), chat_username, chat_first_name, user_id),
        )


def clear_telegram_binding(user_id: str):
    """Remove a user's Telegram chat binding and any pending bind code."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE users
               SET telegram_chat_id = NULL,
                   telegram_chat_username = NULL,
                   telegram_chat_first_name = NULL,
                   telegram_bind_code = NULL,
                   telegram_bind_expires_at = NULL
               WHERE user_id = ?""",
            (user_id,),
        )


def get_telegram_binding(user_id: str) -> Optional[Dict]:
    """Return a user's Telegram chat binding, or None if not linked."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT telegram_chat_id, telegram_chat_username, telegram_chat_first_name
               FROM users WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
    if not row or not row["telegram_chat_id"]:
        return None
    return {
        "chat_id": row["telegram_chat_id"],
        "chat_username": row["telegram_chat_username"],
        "chat_first_name": row["telegram_chat_first_name"],
    }


def save_telegram_bind_code(user_id: str, code: str, expires_at: str):
    """Store a one-time Telegram bind code for the user."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE users
               SET telegram_bind_code = ?,
                   telegram_bind_expires_at = ?
               WHERE user_id = ?""",
            (code, expires_at, user_id),
        )


def clear_telegram_bind_code(user_id: str):
    """Clear any pending Telegram bind code for the user."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE users
               SET telegram_bind_code = NULL,
                   telegram_bind_expires_at = NULL
               WHERE user_id = ?""",
            (user_id,),
        )


def get_telegram_bind_code(user_id: str) -> Optional[Dict]:
    """Return the user's pending Telegram bind code, if any."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT telegram_bind_code, telegram_bind_expires_at
               FROM users WHERE user_id = ?""",
            (user_id,),
        ).fetchone()
    if not row or not row["telegram_bind_code"]:
        return None
    return {
        "code": row["telegram_bind_code"],
        "expires_at": row["telegram_bind_expires_at"],
    }


_SETTINGS_DEFAULTS = {
    "risk_per_trade": 0.02,
    "max_concentration": 0.10,
    "stop_loss_multiplier": 2.0,
    "take_profit_pct": 0.05,
    "min_confidence": 0.3,
    "trailing_stop_high_profit": 0.10,
    "trailing_stop_low_profit": 0.05,
    "trailing_stop_cushion": 0.03,
    "trailing_stop_lock_pct": 0.02,
    "strategy": "intraday",
    "risk_preference": "moderate",
}

_SETTINGS_COLS = list(_SETTINGS_DEFAULTS.keys())

# Metadata written only by param_optimizer — never overwritten by save_user_settings.
_OPTIMIZATION_META_COLS = [
    "last_param_update_at",
    "last_param_update_status",
    "last_param_update_reason",
]


def load_user_settings(user_id: str) -> Dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row:
        out = dict(_SETTINGS_DEFAULTS)
        out.update({col: None for col in _OPTIMIZATION_META_COLS})
        return out
    out = {col: row[col] for col in _SETTINGS_COLS}
    for col in _OPTIMIZATION_META_COLS:
        try:
            out[col] = row[col]
        except (IndexError, KeyError):
            out[col] = None
    return out


def set_param_optimization_status(
    user_id: str,
    status: str,
    reason: Optional[str] = None,
):
    """Record the outcome of the most recent AI parameter optimization run.

    status: 'ok' | 'failed' | 'skipped'
    reason: short human-readable string (None on success)
    """
    with get_conn() as conn:
        conn.execute(
            """UPDATE user_settings
               SET last_param_update_at     = ?,
                   last_param_update_status = ?,
                   last_param_update_reason = ?
               WHERE user_id = ?""",
            (datetime.utcnow().isoformat(), status, reason, user_id),
        )


def save_user_settings(user_id: str, **kwargs):
    """Partial update of a user's trading settings.

    Any column NOT supplied in kwargs is preserved at its current DB value
    (or its default if no row exists yet). Previously this function silently
    reset every unspecified column to its default, which is a foot-gun for
    callers (e.g. legacy Streamlit UI passing only 5 of 11 fields would wipe
    out a user's strategy='swing' setting back to 'intraday').

    Unknown kwargs are rejected to catch typos at the call site rather than
    silently dropping the value.
    """
    unknown = set(kwargs) - set(_SETTINGS_COLS)
    if unknown:
        raise ValueError(
            f"save_user_settings: unknown field(s) {sorted(unknown)}; "
            f"valid fields are {_SETTINGS_COLS}"
        )
    # load_user_settings returns defaults for missing settings rows. The user
    # itself must still exist; with FK enforcement ON, an unknown user_id will
    # fail at INSERT/UPDATE time instead of silently creating an orphan row.
    existing = load_user_settings(user_id)
    values = {col: kwargs.get(col, existing[col]) for col in _SETTINGS_COLS}
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO user_settings
               (user_id, risk_per_trade, max_concentration, stop_loss_multiplier,
                take_profit_pct, min_confidence, trailing_stop_high_profit,
                trailing_stop_low_profit, trailing_stop_cushion, trailing_stop_lock_pct,
                strategy, risk_preference, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   risk_per_trade       = excluded.risk_per_trade,
                   max_concentration    = excluded.max_concentration,
                   stop_loss_multiplier = excluded.stop_loss_multiplier,
                   take_profit_pct      = excluded.take_profit_pct,
                   min_confidence       = excluded.min_confidence,
                   trailing_stop_high_profit = excluded.trailing_stop_high_profit,
                   trailing_stop_low_profit  = excluded.trailing_stop_low_profit,
                   trailing_stop_cushion     = excluded.trailing_stop_cushion,
                   trailing_stop_lock_pct    = excluded.trailing_stop_lock_pct,
                   strategy             = excluded.strategy,
                   risk_preference      = excluded.risk_preference,
                   updated_at           = excluded.updated_at""",
            (user_id, *[values[c] for c in _SETTINGS_COLS], datetime.utcnow().isoformat()),
        )


def set_user_symbols(user_id: str, symbols: List[str]):
    """Replace a user's entire watchlist."""
    symbols = [s.strip().upper() for s in symbols if s.strip()]
    with get_conn() as conn:
        conn.execute("DELETE FROM user_symbols WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO user_symbols (user_id, symbol, added_at) VALUES (?, ?, ?)",
            [(user_id, s, datetime.utcnow().isoformat()) for s in symbols],
        )


def get_user_symbols(user_id: str) -> List[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT symbol FROM user_symbols WHERE user_id = ? ORDER BY added_at",
            (user_id,),
        ).fetchall()
        return [r["symbol"] for r in rows]


# =============================================================================
# Portfolio & positions
# =============================================================================

def save_portfolio(user_id: str, cash: float, portfolio_value: float, total_trades: int):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO portfolio_state (user_id, cash, portfolio_value, total_trades, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   cash = excluded.cash,
                   portfolio_value = excluded.portfolio_value,
                   total_trades = excluded.total_trades,
                   updated_at = excluded.updated_at""",
            (user_id, cash, portfolio_value, total_trades, datetime.utcnow().isoformat()),
        )


def load_portfolio(user_id: str) -> Optional[Dict]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM portfolio_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def save_position(user_id: str, symbol: str, quantity: int, entry_price: float, current_price: float, entry_time: str):
    with get_conn() as conn:
        if quantity == 0:
            conn.execute(
                "DELETE FROM positions WHERE user_id = ? AND symbol = ?",
                (user_id, symbol),
            )
        else:
            conn.execute(
                """INSERT INTO positions (user_id, symbol, quantity, entry_price, current_price, entry_time)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, symbol) DO UPDATE SET
                       quantity = excluded.quantity,
                       current_price = excluded.current_price,
                       entry_price = excluded.entry_price,
                       entry_time = excluded.entry_time""",
                (user_id, symbol, quantity, entry_price, current_price, entry_time),
            )


def load_positions(user_id: str) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM positions WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# =============================================================================
# Trades & signals
# =============================================================================

def record_trade(user_id: str, symbol: str, side: str, quantity: int, price: float, order_id: str = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO trades (user_id, symbol, side, quantity, price, timestamp, order_id) VALUES (?,?,?,?,?,?,?)",
            (user_id, symbol, side, quantity, price, datetime.utcnow().isoformat(), order_id),
        )


def get_trade_history(user_id: str, limit: int = 100) -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def save_signal(
    user_id: str,
    symbol: str,
    date: str,
    signal: str,
    confidence: float,
    reasoning: str = None,
    technical_score: float = None,
    sentiment_score: float = None,
):
    """Save or update today's analysis signal for a user/symbol."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO signals
               (user_id, symbol, date, signal, confidence, reasoning, technical_score, sentiment_score, executed, created_at)
               VALUES (?,?,?,?,?,?,?,?,0,?)
               ON CONFLICT(user_id, symbol, date) DO UPDATE SET
                   signal = excluded.signal,
                   confidence = excluded.confidence,
                   reasoning = excluded.reasoning,
                   technical_score = excluded.technical_score,
                   sentiment_score = excluded.sentiment_score,
                   created_at = excluded.created_at""",
            (user_id, symbol, date, signal, confidence, reasoning, technical_score, sentiment_score, datetime.utcnow().isoformat()),
        )


def mark_signal_executed(user_id: str, symbol: str, date: str):
    """Mark a signal as executed after the trade is placed."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE signals SET executed = 1 WHERE user_id = ? AND symbol = ? AND date = ?",
            (user_id, symbol, date),
        )


def get_signals(user_id: str, date: str = None, limit: int = 50) -> List[Dict]:
    """Get signals for a user. If date given, filter to that day only."""
    with get_conn() as conn:
        if date:
            rows = conn.execute(
                "SELECT * FROM signals WHERE user_id = ? AND date = ? ORDER BY created_at DESC",
                (user_id, date),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM signals WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


def get_pending_signals(user_id: str, date: str) -> List[Dict]:
    """Get unexecuted BUY/SELL signals for today."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM signals
               WHERE user_id = ? AND date = ? AND executed = 0 AND signal != 'HOLD'
               ORDER BY confidence DESC""",
            (user_id, date),
        ).fetchall()
        return [dict(r) for r in rows]


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    init_db()
    print(f"Database initialized at: {os.path.abspath(DB_PATH)}")

    # Quick smoke test
    create_user("user_001", "alice")
    set_user_symbols("user_001", ["AAPL", "TSLA", "NVDA"])
    save_alpaca_credentials("user_001", "FAKE_KEY_123", "FAKE_SECRET_456")

    print("User:", get_user("user_001"))
    print("Symbols:", get_user_symbols("user_001"))
    print("Portfolio:", load_portfolio("user_001"))
    print("Alpaca creds:", get_alpaca_credentials("user_001"))
