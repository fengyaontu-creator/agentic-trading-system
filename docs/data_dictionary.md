# Data Dictionary

## Naming Conventions

- All column names use **snake_case**
- All timestamps use **ISO 8601** format (`YYYY-MM-DDTHH:MM:SS`)
- All scores are normalized to **[-1, 1]** or **[0, 1]** (specify per file)

---

## Standard Columns

| Column | Type | Description |
|--------|------|-------------|
| `datetime` | str (ISO 8601) | Timestamp of the data point |
| `symbol` | str | Ticker symbol (e.g., AAPL) |
| `technical_score` | float [-1, 1] | Composite technical indicator score |
| `sentiment_score` | float [-1, 1] | Sentiment analysis score |
| `risk_score` | float [0, 1] | Risk assessment score (0 = low risk) |
| `final_decision` | str | Trading decision: BUY / SELL / HOLD |

---

## File Schemas

### market_data.csv
| Column | Type | Description |
|--------|------|-------------|
| `datetime` | str | Trading date |
| `symbol` | str | Ticker |
| `open` | float | Opening price |
| `high` | float | High price |
| `low` | float | Low price |
| `close` | float | Closing price |
| `volume` | int | Trading volume |

### technical_signals.csv
| Column | Type | Description |
|--------|------|-------------|
| `datetime` | str | Signal timestamp |
| `symbol` | str | Ticker |
| `rsi` | float | RSI value (0-100) |
| `macd` | float | MACD line value |
| `macd_signal` | float | MACD signal line |
| `technical_score` | float | Composite score [-1, 1] |

### sentiment_signals.csv
| Column | Type | Description |
|--------|------|-------------|
| `datetime` | str | Analysis timestamp |
| `symbol` | str | Ticker |
| `source` | str | Data source (news / social) |
| `raw_score` | float | Raw sentiment value |
| `sentiment_score` | float | Normalized score [-1, 1] |

### execution_log.csv
| Column | Type | Description |
|--------|------|-------------|
| `datetime` | str | Execution timestamp |
| `symbol` | str | Ticker |
| `action` | str | BUY / SELL |
| `quantity` | int | Number of shares |
| `price` | float | Execution price |
| `commission` | float | Transaction cost |

### portfolio_history.csv
| Column | Type | Description |
|--------|------|-------------|
| `datetime` | str | Snapshot timestamp |
| `total_value` | float | Portfolio NAV |
| `cash` | float | Cash balance |
| `positions` | str (JSON) | Current holdings |
| `daily_return` | float | Daily return % |

### risk_log.csv
| Column | Type | Description |
|--------|------|-------------|
| `datetime` | str | Assessment timestamp |
| `symbol` | str | Ticker |
| `risk_score` | float | Risk score [0, 1] |
| `risk_type` | str | Type of risk flagged |
| `action_taken` | str | Mitigation action |

### decision_log.csv
| Column | Type | Description |
|--------|------|-------------|
| `datetime` | str | Decision timestamp |
| `symbol` | str | Ticker |
| `technical_score` | float | Tech score at decision time |
| `sentiment_score` | float | Sentiment score at decision time |
| `risk_score` | float | Risk score at decision time |
| `final_decision` | str | BUY / SELL / HOLD |
| `confidence` | float | Decision confidence [0, 1] |
| `reasoning` | str | Agent reasoning summary |

### backtest_metrics.json
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
