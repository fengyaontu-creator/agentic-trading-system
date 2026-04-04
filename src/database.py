"""
database.py — SQLite persistence layer

Tables:
- users          : registered users (with encrypted Alpaca credentials)
- user_symbols   : each user's watchlist
- portfolio_state: cash + portfolio value per user
- positions      : open positions per user
- trades         : full trade history per user
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


# ── Users ──────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(user_id: str, username: str, password: str = "") -> Dict:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, username, _hash_password(password), datetime.utcnow().isoformat()),
        )
        # Init portfolio with $100k if not exists
        conn.execute(
            """INSERT OR IGNORE INTO portfolio_state
               (user_id, cash, portfolio_value, total_trades, updated_at)
               VALUES (?, 100000.0, 100000.0, 0, ?)""",
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
            "SELECT user_id, username, created_at FROM users WHERE username = ? AND password_hash = ?",
            (username, _hash_password(password)),
        ).fetchone()
        return dict(row) if row else None


def list_users() -> List[Dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT user_id, username, created_at FROM users ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def save_alpaca_credentials(user_id: str, api_key: str, api_secret: str):
    """Encrypt and store the user's Alpaca credentials."""
    with get_conn() as conn:
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
    return {
        "api_key": decrypt(row["alpaca_key_enc"]),
        "api_secret": decrypt(row["alpaca_secret_enc"]),
    }


# ── Symbols ─────────────────────────────────────────────────────────────────

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


# ── Portfolio state ──────────────────────────────────────────────────────────

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


# ── Positions ────────────────────────────────────────────────────────────────

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


# ── Trades ───────────────────────────────────────────────────────────────────

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


# ── Signals ──────────────────────────────────────────────────────────────────

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
