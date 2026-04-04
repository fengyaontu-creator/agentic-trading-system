# Agentic Trading System

An AI-driven multi-user trading system with a web frontend, FastAPI backend, SQLite persistence, and an agent-based trading pipeline for technical analysis, sentiment analysis, risk management, and execution.

## Branch Guide

- `main`: team scaffold / TODO skeleton version
- `full-version`: integrated implementation draft

## What This Version Includes

- Multi-user login and registration
- React frontend for portfolio and signal monitoring
- FastAPI backend with JWT authentication
- SQLite persistence for users, watchlists, signals, trades, and portfolio state
- Encrypted storage of user-specific Alpaca credentials
- Technical analysis using real market data from `yfinance`
- Sentiment analysis with external APIs and LLM summarization
- Trading orchestration and backtesting support

## Architecture Overview

```text
Browser
  ->
React frontend (`frontend/`)
  ->
FastAPI backend (`src/api.py`)
  ->
SQLite database (`trading.db`)

Trading pipeline (`src/agentic_trading.py`)
  ->
market data (`src/data_tools.py`)
  + sentiment (`src/sentiment_tools.py`)
  + risk / backtesting (`src/backtester.py`)
  + broker execution (`src/broker_alpaca.py`)
```

## Project Structure

```text
agentic-trading-system/
├── frontend/                    # React + Vite frontend
│   ├── src/
│   │   ├── pages/
│   │   │   ├── AuthPage.tsx
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── SignalsPage.tsx
│   │   │   ├── HistoryPage.tsx
│   │   │   └── SettingsPage.tsx
│   │   ├── components/
│   │   ├── api.ts
│   │   └── App.tsx
│   └── package.json
├── src/
│   ├── agentic_trading.py       # Main orchestrator
│   ├── api.py                   # FastAPI backend
│   ├── app.py                   # Streamlit UI
│   ├── backtester.py            # Backtesting & risk management
│   ├── broker_alpaca.py         # Alpaca order execution
│   ├── data_tools.py            # Market data & technical indicators
│   ├── database.py              # SQLite persistence + encrypted credentials
│   ├── dashboard.py             # Visualization utilities
│   ├── scheduler.py             # Scheduled analysis / trading runs
│   └── sentiment_tools.py       # Sentiment analysis
├── docs/
├── outputs/                     # Generated runtime outputs (git-ignored)
├── .env.example
├── requirements.txt
└── README.md
```

## Frontend Pages

- `Dashboard`: portfolio summary, positions, allocation, recent trade activity
- `Signals`: today's BUY / SELL / HOLD signals plus historical signal records
- `History`: trade history and execution statistics
- `Settings`: user watchlist and Alpaca credential management

## Core Backend Modules

- `src/api.py`
  - FastAPI app
  - JWT auth
  - endpoints for auth, dashboard, signals, history, and settings
  - serves `frontend/dist` in production when available

- `src/database.py`
  - stores users, watchlists, positions, trades, portfolio state, and signals
  - encrypts user-specific Alpaca credentials using `DB_ENCRYPTION_KEY`

- `src/data_tools.py`
  - fetches market data from `yfinance`
  - computes SMA, EMA, MACD, RSI, and Bollinger Bands
  - generates a lightweight quantitative `ml_signal`

- `src/agentic_trading.py`
  - orchestrates technical analysis, sentiment analysis, risk, and execution
  - loads user-specific Alpaca credentials from the database
  - updates trades, positions, and portfolio state

- `src/backtester.py`
  - records trades and portfolio value
  - computes Sharpe ratio, Sortino ratio, max drawdown, win rate, and profit factor

## Environment Variables

Create a local `.env` file from `.env.example`.

Common variables used by this project:

```env
OPENROUTER_API_KEY=...
NEWS_API_KEY=...
ALPHA_VANTAGE_API_KEY=...
DB_ENCRYPTION_KEY=...
JWT_SECRET=...

# Optional fallback account for manual / default Alpaca usage
ALPACA_API_KEY=...
ALPACA_API_SECRET=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Optional defaults for CLI / scheduler flows
TRADING_USER_ID=default
TRADING_SYMBOLS=AAPL,MSFT,NVDA
DB_PATH=trading.db
```

Notes:

- `JWT_SECRET` is required for secure login tokens in `src/api.py`
- `DB_ENCRYPTION_KEY` is required to encrypt and decrypt stored Alpaca credentials
- user-specific Alpaca keys are primarily stored in the database through the Settings page
- global `ALPACA_API_KEY` / `ALPACA_API_SECRET` act as optional fallbacks

## Local Development

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Create `.env`

```bash
cp .env.example .env
```

Then fill in the required keys.

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

### 4. Run the frontend in dev mode

```bash
npm run dev
```

### 5. Run the backend

From the project root:

```bash
uvicorn src.api:app --reload --port 8000
```

FastAPI docs will be available at:

```text
http://127.0.0.1:8000/api/docs
```

### 6. Optional: Run the Streamlit app

```bash
streamlit run src/app.py
```

### 7. Optional: Run the trading pipeline directly

```bash
python src/agentic_trading.py
```

## Production Build

Build the frontend:

```bash
cd frontend
npm run build
```

This generates `frontend/dist/`.

When `frontend/dist/` exists, `src/api.py` mounts it automatically, so the FastAPI app can serve both:

- the web UI at `/`
- the API at `/api/...`

## Deployment Notes

Recommended simple deployment for this project:

- build the frontend on the server
- run FastAPI with `uvicorn`
- place Nginx in front as a reverse proxy
- keep secrets in a server-side `.env`
- initialize a fresh server-side SQLite database for clean deployment

For a clean server deployment:

1. clone the repo from GitHub
2. create a fresh `.env` on the server
3. run `npm run build` inside `frontend/`
4. start `uvicorn src.api:app --host 0.0.0.0 --port 8000`
5. configure Nginx to forward public traffic to port `8000`

## Current Strategy Notes

- The system uses one shared pipeline for all users
- Different users mainly differ by:
  - watchlist symbols
  - Alpaca credentials
  - portfolio state
  - trade history
- The current `ml_signal` is a rule-based quantitative enhancement, not a separately trained ML model
- User-specific strategy parameters are not yet fully configurable through the database

## Output Files

Generated runtime artifacts may include:

- `outputs/execution_log.csv`
- `outputs/portfolio_history.csv`
- `outputs/backtest_metrics.json`

These are git-ignored runtime outputs.

## Team Ownership

| Member | Module | File |
|--------|--------|------|
| Person A | Market Data & Technical Indicators | `src/data_tools.py` |
| Person B | Multi-source Sentiment Analysis | `src/sentiment_tools.py` |
| Person C | Alpaca Order Execution | `src/broker_alpaca.py` |
| Person D | Backtesting & Risk Management | `src/backtester.py` |
| Person E | Visualization Dashboard | `src/dashboard.py` |
| All | Main Orchestrator | `src/agentic_trading.py` |
