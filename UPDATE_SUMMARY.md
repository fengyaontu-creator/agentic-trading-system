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

## 2026-04-07 Deployment Readiness and Reliability Cleanup

**Author:** Nora + Codex review sync

**Branch:** `full-version`

**Status:** This entry reflects the current local workspace state before the next GitHub push.

**Context:** This round focused on turning the multi-user paper-trading build into something safer to deploy on a server without losing the recent branch cleanup. The work centered on account isolation, scheduler safety, database integrity, and keeping the React settings flow aligned with the backend.

### What changed

- Tightened registration safety:
  - registration now rejects collisions on both raw `username` and normalized `user_id`
  - `create_user()` is strict on the `users` table and surfaces `sqlite3.IntegrityError` instead of silently ignoring conflicts
  - this closes the old risk where different names like `Alice` / `alice` could collapse onto the same account

- Removed hidden write side effects from `TradingOrchestrator` construction:
  - the constructor is now read-only
  - it no longer auto-creates users or initializes the DB behind the scenes
  - unknown `user_id` values now fail loudly instead of creating ghost accounts

- Hardened DB integrity:
  - SQLite foreign key enforcement is now enabled on every connection
  - credential removal now truly clears saved Alpaca secrets instead of storing encrypted empty strings
  - zero-quantity fills now delete the corresponding DB position row so stale positions do not survive after flattening

- Made settings updates safer and clearer:
  - `save_user_settings()` is now a true partial update and rejects unknown fields
  - React Settings now refreshes from the backend after saving or deleting values
  - optimization metadata (`last_param_update_*`) is stored and displayed in the UI

- Tightened close-session behavior:
  - only users with exact `strategy == "intraday"` are flattened during the `close` session
  - `swing`, `NULL`, typo'd, or legacy values are skipped with a warning instead of being flattened by mistake

- Improved scheduler and parameter optimization flow:
  - `analyze` now runs AI parameter optimization before saving signals
  - optimization results are recorded as `ok`, `failed`, or `skipped`
  - skipped / failed states are visible from the settings page
  - the default scheduled `trade` time was moved from `09:30 ET` to `09:50 ET` to avoid the noisiest part of the market open

- Cleaned test reliability issues:
  - the portfolio tests no longer leak writes into the real `trading.db`
  - integration coverage now exercises `analyze`, `trade`, and `close` behavior more directly
  - credential deletion and strategy whitelist behavior now have explicit regression coverage

### Current deployment posture

This branch is in a much better state for:

- monitored Alpaca paper trading
- manual `analyze` / `trade` runs before enabling unattended scheduling
- server deployment with persistent SQLite data

It is still not a production-grade brokerage platform. The remaining work is mostly hardening, cleanup, and operational safety rather than missing core functionality.

### What teammates should know

- React + FastAPI is the primary app path; the Streamlit app remains as a legacy/local interface
- per-user Alpaca credentials live in the database and are encrypted with `DB_ENCRYPTION_KEY`
- server `git pull` should not overwrite SQLite data as long as `DB_PATH` points to the existing DB and no cleanup command deletes it
- before updating a live server, back up `trading.db`, `trading.db-wal`, and `trading.db-shm`
- code, UI copy, and scheduler examples now assume `analyze = 07:30 ET`, `trade = 09:50 ET`, `close = 15:30 ET`

### Suggested next steps

- add numeric validation bounds to trading parameter API inputs
- replace separate stop-loss / take-profit follow-up orders with a safer bracket/OCO-style approach if Alpaca workflow permits
- tighten DB migration error handling so real migration failures do not get silently swallowed


---

## 2026-04-06 Short Selling Risk Management Fix

**Branch:** `full-version`

**Context:** 修复做空仓位缺少止损和止盈保护的严重问题。之前AI代理可以开立做空仓位而没有自动平仓保护，导致无限损失风险。

### What was fixed

#### 1. `src/broker_alpaca.py` - 函数 execute_trade() 第217-228行

**问题:** 做空开仓时（side="SELL"），函数只创建主订单，没有止损和止盈保护单。

**修复:** 添加方向判断逻辑：
- 做多（BUY）: 止损SELL STOP、止盈SELL LIMIT
- 做空（SELL）: 止损BUY STOP、止盈BUY LIMIT

#### 2. `src/broker_alpaca.py` - 函数 execute_trade() 第232-237行日志增强

**问题:** 异常日志未能清晰记录SHORT仓位的保护单失败情况。

**修复:** 改进异常日志记录逻辑，明确记录stop_loss和take_profit参数，便于诊断SHORT仓位问题。其它对项目的运行日志修改见LOGGING.MD

#### 3. `src/agentic_trading.py` - 类方法 RiskManagementAgent.assess() 第199-290行

**问题:** 计算做空头寸时，risk_per_share = current_price - stop_loss 得到负数，导致max_shares = 0，做空交易完全被阻止。

**修复:** 重构assess()方法：
- 第211-227行：添加方向感知的stop_loss和take_profit计算
  - 做多: stop_loss = current_price - distance（低于价格）
  - 做空: stop_loss = current_price + distance（高于价格）
- 第258-259行：修复risk_per_share计算，确保两个方向都为正数

### Impact

- 返回值结构不变，向后兼容
- 仅影响交易逻辑，不涉及API/数据库/前端
- 调用该方法的代码无需修改



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

