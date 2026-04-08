# Agentic Trading System

Multi-user AI trading prototype with a React frontend, FastAPI backend, SQLite persistence, and scheduled paper-trading flows built around technical analysis, sentiment analysis, risk management, and Alpaca execution.

For the latest branch status, deployment notes, and teammate handoff summary, see [UPDATE_SUMMARY.md](./UPDATE_SUMMARY.md).

## What It Does

- Supports multi-user registration and login
- Lets each user manage their own watchlist, trading parameters, Alpaca paper-trading credentials, and Telegram trade notifications
- Validates Alpaca credentials when they are saved in Settings, so unusable paper keys are rejected immediately
- Runs scheduled sessions for:
  - `analyze`: optimize per-user parameters, then generate daily signals
  - `trade`: execute open trades from today's signals, with the default scheduled run at `09:50 ET`
  - `close`: flatten end-of-day positions only for users whose strategy is exactly `intraday`
- Stores portfolio state, positions, trades, signals, and encrypted user credentials in SQLite
- Provides a React dashboard for monitoring portfolio, signals, history, and settings

## Architecture

```text
Browser
  ->
React frontend (frontend/)
  ->
FastAPI API (src/api.py)
  ->
SQLite (trading.db)

Trading flow
  ->
Scheduler / session services
  ->
TradingOrchestrator
  + technical analysis (src/data_tools.py)
  + sentiment analysis (src/sentiment_tools.py)
  + risk and backtesting (src/backtester.py)
  + execution (src/broker_alpaca.py)
```

## Current Structure

```text
frontend/                  React + Vite frontend
src/
  api.py                   FastAPI backend and auth
  scheduler.py             Cron / scheduled entrypoint
  services/
    trading_sessions.py    Analyze / trade / close session logic
  param_optimizer.py       Pre-analyze AI parameter optimization
  agentic_trading.py       Main orchestrator
  position.py              Shared position / fill arithmetic
  broker_alpaca.py         Alpaca paper-trading adapter
  database.py              SQLite persistence + encrypted user creds
  data_tools.py            Market data and indicators
  sentiment_tools.py       News + sentiment analysis
  backtester.py            Metrics and portfolio history
  app.py                   Optional legacy Streamlit UI
tests/                     Regression tests for core logic
docs/                      Setup notes and data dictionary
```

## Public vs User Secrets

This project intentionally separates platform-level secrets from per-user trading credentials.

### Platform-level secrets in `.env`

These are shared by the deployed system:

- `JWT_SECRET`
- `DB_ENCRYPTION_KEY`
- `OPENROUTER_API_KEY`
- `NEWS_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `CORS_ORIGINS`
- `DB_PATH`

### Per-user data stored in the database

These belong to each user account:

- Alpaca `API Key`
- Alpaca `API Secret`
- Telegram chat binding
- watchlist symbols
- trading parameters
- strategy mode (`intraday` or `swing`)

User Alpaca credentials are encrypted with Fernet before being written to the database.

The React Settings page now distinguishes between:

- credentials not set
- credentials saved and verified
- credentials saved but invalid

## Environment Variables

Create a `.env` file in the project root.

Minimum example:

```env
JWT_SECRET=replace-with-a-long-random-string
DB_ENCRYPTION_KEY=replace-with-a-fernet-key
OPENROUTER_API_KEY=replace-with-your-openrouter-key
NEWS_API_KEY=replace-with-your-newsapi-key
ALPHA_VANTAGE_API_KEY=replace-with-your-alpha-vantage-key
TELEGRAM_BOT_TOKEN=

CORS_ORIGINS=http://localhost:5173,http://localhost:3000
DB_PATH=trading.db

# Optional local CLI defaults
TRADING_USER_ID=default
TRADING_SYMBOLS=AAPL,MSFT,NVDA

# Optional only for local CLI testing in broker_alpaca.py __main__
ALPACA_API_KEY=
ALPACA_API_SECRET=
```

Notes:

- `JWT_SECRET` is required for login tokens
- `DB_ENCRYPTION_KEY` is required to save and read encrypted Alpaca credentials
- scheduled analysis requires `OPENROUTER_API_KEY`
- `TELEGRAM_BOT_TOKEN` enables Telegram bot binding and trade-fill notifications
- deployed multi-user trading should use user-saved Alpaca credentials from Settings, not shared `.env` credentials

Generate a Fernet key with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Generate a JWT secret with:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

## Local Development

### 1. Install Python dependencies

```powershell
pip install -r requirements.txt
```

### 2. Install frontend dependencies

```powershell
cd frontend
npm install
cd ..
```

### 3. Start the backend

From the project root:

```powershell
uvicorn src.api:app --reload --port 8000
```

API docs:

```text
http://127.0.0.1:8000/api/docs
```

### 4. Start the frontend

In a second terminal:

```powershell
cd frontend
npm run dev
```

Frontend URL:

```text
http://127.0.0.1:5173
```

If you changed `JWT_SECRET`, clear old browser tokens and log in again.

## Scheduled Sessions

The scheduler supports three sessions:

```powershell
python src/scheduler.py --session analyze
python src/scheduler.py --session trade
python src/scheduler.py --session close
```

Default schedule in ET:

- `analyze`: `07:30 ET`
- `trade`: `09:50 ET`
- `close`: `15:30 ET`

Behavior:

- `analyze`: run AI parameter optimization, then save today's signals for each user's watchlist
- `trade`: execute today's pending non-`HOLD` signals during market hours
  - protected entry trades use Alpaca advanced orders (`bracket` or `OTO`) when stop-loss / take-profit data is available
- `close`: flatten positions only for users whose strategy is exactly `intraday`

The market-hours logic is evaluated in `America/New_York`.

The scheduler writes operational logs to `scheduler.log`.

## Trading Modes

Each user can choose a strategy in Settings:

- `intraday`: open positions can be flattened during the close session
- `swing`: positions can be carried overnight

Trading parameters are user-specific and persisted in the database.

## Telegram Notifications

When `TELEGRAM_BOT_TOKEN` is configured on the server, users can bind the shared bot from Settings:

1. Click `Generate Binding Code`
2. Send `/start CODE` to the bot in Telegram
3. Click `Verify Binding`

After the chat is linked, the backend sends a Telegram message whenever a `BUY` or `SELL` order is executed in the `trade` or `close` sessions. Notification delivery is best-effort only; a Telegram outage does not block the trade itself.

## Testing

Core regression tests live in `tests/`.

Run tests with:

```powershell
python -m pytest
```

Current coverage focuses on:

- shared position update rules
- scheduler behavior
- portfolio update logic
- session integration and credential handling

## Production Build

Build the frontend:

```powershell
cd frontend
npm run build
cd ..
```

When `frontend/dist/` exists, FastAPI serves the built frontend automatically.

Start the app:

```powershell
uvicorn src.api:app --host 0.0.0.0 --port 8000
```

## Deployment Notes

This repository is suitable for a demo / prototype deployment.

Recommended deployment shape:

1. Push the current code to GitHub
2. Clone it on the server
3. Create a fresh server-side `.env`
4. Build the frontend
5. Start FastAPI behind a reverse proxy
6. Configure scheduled `analyze`, `trade`, and `close` jobs

Important reminders:

- use user-specific Alpaca credentials for multi-user trading
- keep `JWT_SECRET` and `DB_ENCRYPTION_KEY` private and stable
- back up `trading.db`, `trading.db-wal`, and `trading.db-shm` before updating a live server
- keep `DB_PATH` stable on the server so code updates do not point the app at a fresh empty database
- SQLite is acceptable for demos, but PostgreSQL would be better for longer-term multi-user use
- start with Alpaca paper trading, not live capital

## Status

This is a working multi-user paper-trading prototype, not a production-grade brokerage platform.

It is best suited for:

- demos
- coursework
- prototyping
- monitored paper-trading runs
