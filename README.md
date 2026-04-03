# Agentic Trading System

An AI-driven multi-agent trading system that integrates technical analysis, sentiment analysis, and risk management for automated trading decisions.

## Branch Guide

- `main`: team scaffold / TODO skeleton version
- `full-version`: integrated implementation draft

## Current Focus

- Person A integrates the overall pipeline and owns the technical-analysis path
- `src/data_tools.py` now uses real market data from `yfinance`
- The technical layer keeps SMA / EMA / RSI / MACD / Bollinger Bands
- A lightweight quantitative boost is added so technical decisions are not based on LLM output alone

## Project Structure

```
agentic-trading-system/
├── src/
│   ├── agentic_trading.py        # Main orchestrator
│   ├── data_tools.py             # Market data & technical indicators
│   ├── sentiment_tools.py        # Multi-source sentiment analysis
│   ├── broker_alpaca.py          # Alpaca order execution
│   ├── backtester.py             # Backtesting & risk management
│   └── dashboard.py              # Visualization dashboard
├── outputs/                      # Generated at runtime (git-ignored)
│   ├── market_data.csv           # Raw market data
│   ├── technical_signals.csv     # Technical indicator signals
│   ├── sentiment_signals.csv     # Sentiment analysis signals
│   ├── execution_log.csv         # Trade execution records
│   ├── portfolio_history.csv     # Portfolio value over time
│   ├── risk_log.csv              # Risk assessment records
│   ├── backtest_metrics.json     # Backtest summary metrics
│   ├── decision_log.csv          # Final trading decisions
│   └── presentation_assets/      # Charts & figures for presentation
├── docs/
│   ├── data_dictionary.md        # Column naming conventions & schema
│   ├── api_setup.md              # API key configuration guide
│   └── presentation_notes.md     # Presentation talking points
├── tests/                        # Unit tests
├── .env.example                  # Environment variable template
├── .gitignore
└── requirements.txt
```

## Quick Start

1. **Clone the repo**
   ```bash
   git clone https://github.com/<your-username>/agentic-trading-system.git
   cd agentic-trading-system
   ```

2. **Set up environment**
   ```bash
   pip install -r requirements.txt
   cp .env.example .env
   # Fill in your API keys in .env
   ```

3. **Run the pipeline**
   ```bash
   python src/agentic_trading.py
   ```

   If `ANTHROPIC_API_KEY` is missing, the orchestrator falls back to a rule-based mode for technical and sentiment analysis.

4. **View dashboard**
   ```bash
   python src/dashboard.py
   ```

## Output Files

| File | Description |
|------|-------------|
| `market_data.csv` | Raw OHLCV market data |
| `technical_signals.csv` | RSI, MACD, and other technical signals |
| `sentiment_signals.csv` | News/social sentiment scores |
| `execution_log.csv` | Trade execution timestamps and prices |
| `portfolio_history.csv` | Portfolio NAV and holdings over time |
| `risk_log.csv` | Risk scores and alerts |
| `decision_log.csv` | Final BUY/SELL/HOLD decisions with rationale |
| `backtest_metrics.json` | Sharpe ratio, max drawdown, total return, etc. |

## Naming Conventions

All data files follow **snake_case** naming. Standard columns:

- `datetime` — ISO 8601 timestamp
- `symbol` — Ticker symbol (e.g., AAPL, MSFT)
- `technical_score` — Composite technical indicator score
- `sentiment_score` — Sentiment analysis score
- `risk_score` — Risk assessment score
- `final_decision` — Trading decision (BUY / SELL / HOLD)

See [docs/data_dictionary.md](docs/data_dictionary.md) for full schema.

## Team

| Member | Module | File |
|--------|--------|------|
| Person A | Market Data & Technical Indicators | `data_tools.py` |
| Person B | Multi-source Sentiment Analysis | `sentiment_tools.py` |
| Person C | Alpaca Order Execution | `broker_alpaca.py` |
| Person D | Backtesting & Risk Management | `backtester.py` |
| Person E | Visualization Dashboard | `dashboard.py` |
| All | Main Orchestrator | `agentic_trading.py` |
