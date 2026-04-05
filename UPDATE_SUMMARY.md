# Update Summary

## Purpose

This file is a running update log for the `full-version` branch.

Use it to record:

- when a major update was made
- who made it
- what changed
- what the current deployment status is
- what teammates should know before continuing work

Add new entries to the top so the latest update appears first.

---

## 2026-04-06 Night Update

**Author:** Nora

**Branch:** `full-version`

**Context:** This update was prepared the night before deployment / market open, with the goal of getting the multi-user paper-trading version into a more deployable and easier-to-maintain state.

### What was updated

- Refactored the scheduler flow:
  - `src/scheduler.py` is now a thinner entrypoint
  - session business logic was moved to `src/services/trading_sessions.py`

- Centralized shared position update rules:
  - added `src/position.py`
  - live trading and backtesting now use the same fill arithmetic

- Improved multi-user settings support:
  - user-specific trading parameters are stored in the database
  - user-specific strategy mode (`intraday` / `swing`) is supported end-to-end
  - user-specific Alpaca credentials are stored and loaded per account

- Tightened credential boundaries:
  - Alpaca trading paths now require explicit user credentials
  - main trading execution no longer silently falls back to shared `.env` Alpaca credentials

- Improved frontend/backend alignment:
  - Settings page now supports watchlist, trading params, strategy, and Alpaca credentials
  - API and DB settings structure were aligned to match the UI

- Added core tests:
  - position logic
  - portfolio logic
  - scheduler/session behavior

- Updated documentation:
  - refreshed `README.md`
  - added this update log for teammate handoff and deployment notes

### Current system scope

The project currently works as a multi-user AI trading prototype with:

- React frontend
- FastAPI backend
- SQLite persistence
- scheduled `analyze`, `trade`, and `close` sessions
- per-user Alpaca paper-trading credentials
- per-user trading parameters and strategy mode

### Shared platform config vs per-user config

**Shared platform config in `.env`:**

- `JWT_SECRET`
- `DB_ENCRYPTION_KEY`
- `OPENROUTER_API_KEY`
- `NEWS_API_KEY`
- `ALPHA_VANTAGE_API_KEY`
- `CORS_ORIGINS`
- `DB_PATH`

**Per-user config in the database:**

- Alpaca API key
- Alpaca API secret
- watchlist
- risk settings
- strategy mode

### Deployment status

This branch is deployable as a demo / prototype system.

Recommended use:

- paper trading
- monitored scheduled runs
- course demo / presentation
- internal team iteration

Not yet positioned as a production-grade brokerage platform.

### Deployment notes for tomorrow

- deploy from `full-version`
- use server-side `.env` for shared platform secrets
- use per-user saved Alpaca credentials for trading
- monitor `analyze`, `trade`, and `close` runs closely
- confirm DB positions and Alpaca positions remain aligned

### Follow-up work

- add more automated tests
- harden deployment setup
- eventually replace SQLite with PostgreSQL for longer-term multi-user use
- continue cleanup of older legacy comments / artifacts
- decide later whether `full-version` should become the default branch

