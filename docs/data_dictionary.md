# Data Dictionary

All data is stored in **SQLite** (`trading.db`). Timestamps use ISO 8601 format.

---

## Tables

### users
| Column | Type | Description |
|--------|------|-------------|
| `user_id` | TEXT PK | Unique user identifier |
| `username` | TEXT UNIQUE | Display name / login |
| `password_hash` | TEXT | PBKDF2-HMAC-SHA256 salted hash |
| `alpaca_key_enc` | TEXT | Fernet-encrypted Alpaca API key |
| `alpaca_secret_enc` | TEXT | Fernet-encrypted Alpaca secret |
| `telegram_chat_id` | TEXT | Bound Telegram chat ID for notifications |
| `telegram_chat_username` | TEXT | Telegram username captured during binding |
| `telegram_chat_first_name` | TEXT | Telegram first name captured during binding |
| `telegram_bind_code` | TEXT | Pending one-time bind code shown in Settings |
| `telegram_bind_expires_at` | TEXT | Expiry timestamp for the pending bind code |
| `created_at` | TEXT | Registration timestamp |

### user_symbols
| Column | Type | Description |
|--------|------|-------------|
| `user_id` | TEXT FK | Owner |
| `symbol` | TEXT | Ticker (e.g. AAPL) |
| `added_at` | TEXT | When added to watchlist |

### portfolio_state
| Column | Type | Description |
|--------|------|-------------|
| `user_id` | TEXT PK | Owner |
| `cash` | REAL | Available cash |
| `portfolio_value` | REAL | Cash + positions market value |
| `total_trades` | INTEGER | Lifetime trade count |
| `updated_at` | TEXT | Last update timestamp |

### positions
| Column | Type | Description |
|--------|------|-------------|
| `user_id` | TEXT FK | Owner |
| `symbol` | TEXT | Ticker |
| `quantity` | INTEGER | Signed qty (negative = short) |
| `entry_price` | REAL | Weighted average entry price |
| `current_price` | REAL | Last mark-to-market price |
| `entry_time` | TEXT | Position open timestamp |

### trades
| Column | Type | Description |
|--------|------|-------------|
| `user_id` | TEXT FK | Owner |
| `symbol` | TEXT | Ticker |
| `side` | TEXT | BUY or SELL |
| `quantity` | INTEGER | Shares traded |
| `price` | REAL | Fill price |
| `timestamp` | TEXT | Execution timestamp |
| `order_id` | TEXT | Broker order ID |

### signals
| Column | Type | Description |
|--------|------|-------------|
| `user_id` | TEXT FK | Owner |
| `symbol` | TEXT | Ticker |
| `date` | TEXT | Analysis date (YYYY-MM-DD) |
| `signal` | TEXT | BUY / SELL / HOLD |
| `confidence` | REAL [0,1] | Signal confidence |
| `reasoning` | TEXT | LLM reasoning summary |
| `technical_score` | REAL [0,1] | Technical indicator score |
| `sentiment_score` | REAL [-1,1] | Sentiment analysis score |
| `executed` | INTEGER | 0 = pending, 1 = traded |
| `created_at` | TEXT | Signal generation timestamp |

### user_settings
| Column | Type | Description |
|--------|------|-------------|
| `user_id` | TEXT PK | Owner |
| `risk_per_trade` | REAL | Max portfolio % risk per trade (default 0.02) |
| `max_concentration` | REAL | Max % of portfolio in one stock (default 0.10) |
| `stop_loss_multiplier` | REAL | Volatility multiplier for stop-loss (default 2.0) |
| `take_profit_pct` | REAL | Take-profit target % (default 0.05) |
| `min_confidence` | REAL | Minimum confidence to trade (default 0.3) |
| `updated_at` | TEXT | Last update timestamp |

---

## API Response Shapes

### GET /api/dashboard
```json
{
  "portfolio": { "cash": 0.0, "portfolio_value": 0.0, "total_trades": 0 },
  "positions": [{ "symbol": "", "quantity": 0, "entry_price": 0.0, "current_price": 0.0 }],
  "recent_trades": [{ "symbol": "", "side": "", "quantity": 0, "price": 0.0, "timestamp": "" }]
}
```

### GET /api/signals
```json
{
  "today": [{ "symbol": "", "signal": "", "confidence": 0.0, "executed": false, "date": "" }],
  "history": []
}
```

### GET /api/settings
```json
{
  "symbols": ["AAPL"],
  "has_alpaca": true,
  "telegram": {
    "configured": true,
    "connected": false,
    "bot_username": "my_trade_bot",
    "chat_username": null,
    "chat_first_name": null,
    "pending_code": "ABCD2345",
    "pending_expires_at": "2026-04-08T12:34:56+00:00",
    "detail": "Telegram binding pending. Send the code to the bot, then click Verify."
  },
  "trading_params": {
    "risk_per_trade": 0.02,
    "max_concentration": 0.10,
    "stop_loss_multiplier": 2.0,
    "take_profit_pct": 0.05,
    "min_confidence": 0.3
  }
}
```

### backtest_metrics.json (file output)
```json
{
  "total_return": 0.0,
  "annualized_return": 0.0,
  "sharpe_ratio": 0.0,
  "max_drawdown": 0.0,
  "win_rate": 0.0,
  "total_trades": 0,
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD"
}
```
