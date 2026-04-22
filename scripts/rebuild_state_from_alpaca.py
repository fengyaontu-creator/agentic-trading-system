"""
Rebuild DB portfolio_state and positions from the live Alpaca account.

For each user with valid Alpaca credentials:
  - overwrite portfolio_state.cash and portfolio_value with Alpaca values
  - replace the user's positions rows with Alpaca's current positions
  - total_trades is preserved
  - trades table is NOT touched

Safety:
  - default is dry-run: nothing is written, just prints the planned changes
  - pass --apply to actually write
  - when --apply is used, the DB file is copied to trading.db.bak.<timestamp>
    before any writes

Usage (from project root, using the venv that runs FastAPI):
    # preview
    /opt/agentic-trading-system/venv/bin/python scripts/rebuild_state_from_alpaca.py

    # actually apply
    /opt/agentic-trading-system/venv/bin/python scripts/rebuild_state_from_alpaca.py --apply
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import database as db
from src import broker_alpaca as broker


def backup_db():
    db_path = os.environ.get("DB_PATH", "trading.db")
    if not os.path.exists(db_path):
        raise SystemExit(f"DB file not found at {db_path}")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.bak.{ts}"
    shutil.copy2(db_path, backup_path)
    for suffix in ("-wal", "-shm"):
        extra = f"{db_path}{suffix}"
        if os.path.exists(extra):
            shutil.copy2(extra, f"{backup_path}{suffix}")
    return backup_path


def load_alpaca(api_key, api_secret):
    account = broker.get_account_info(api_key, api_secret)
    positions = broker.get_positions(api_key, api_secret)
    return account, positions


def rebuild_user(user_id: str, username: str, apply: bool) -> dict:
    creds = db.get_alpaca_credentials(user_id)
    if not creds:
        return {"status": "skip", "reason": "no credentials"}

    try:
        account, alp_positions = load_alpaca(creds["api_key"], creds["api_secret"])
    except Exception as e:
        return {"status": "skip", "reason": f"Alpaca error: {e}"}

    old_pf = db.load_portfolio(user_id) or {}
    old_positions = db.load_positions(user_id)

    new_cash = float(account["cash"])
    new_equity = float(account["equity"])
    total_trades = int(old_pf.get("total_trades", 0))

    now_iso = datetime.now(timezone.utc).isoformat()

    plan = {
        "status": "apply" if apply else "dryrun",
        "old_cash": old_pf.get("cash"),
        "new_cash": new_cash,
        "old_equity": old_pf.get("portfolio_value"),
        "new_equity": new_equity,
        "old_positions": {p["symbol"]: p["quantity"] for p in old_positions},
        "new_positions": {p["symbol"]: p["qty"] for p in alp_positions},
    }

    if not apply:
        return plan

    db.save_portfolio(user_id, cash=new_cash, portfolio_value=new_equity, total_trades=total_trades)

    keep_symbols = {p["symbol"] for p in alp_positions}
    for old in old_positions:
        if old["symbol"] not in keep_symbols:
            db.save_position(user_id, old["symbol"], 0, 0.0, 0.0, now_iso)

    for p in alp_positions:
        qty = int(round(p["qty"]))
        db.save_position(
            user_id,
            p["symbol"],
            quantity=qty,
            entry_price=float(p["avg_entry_price"]),
            current_price=float(p["current_price"]),
            entry_time=now_iso,
        )

    return plan


def print_plan(username: str, plan: dict):
    status = plan["status"]
    if status == "skip":
        print(f"  [skip] {username}: {plan['reason']}")
        return

    old_cash = plan["old_cash"]
    new_cash = plan["new_cash"]
    old_eq = plan["old_equity"]
    new_eq = plan["new_equity"]
    old_pos = plan["old_positions"]
    new_pos = plan["new_positions"]

    def fmt(x):
        return f"{x:,.2f}" if isinstance(x, (int, float)) else str(x)

    print(f"  [{status}] {username}:")
    print(f"      cash:   {fmt(old_cash)} -> {fmt(new_cash)}")
    print(f"      equity: {fmt(old_eq)} -> {fmt(new_eq)}")
    removed = sorted(set(old_pos) - set(new_pos))
    added = sorted(set(new_pos) - set(old_pos))
    changed = sorted(s for s in set(old_pos) & set(new_pos) if old_pos[s] != new_pos[s])
    if removed:
        print(f"      remove positions: {', '.join(f'{s}({old_pos[s]})' for s in removed)}")
    if added:
        print(f"      add positions:    {', '.join(f'{s}({new_pos[s]})' for s in added)}")
    if changed:
        print(
            "      change positions: "
            + ", ".join(f"{s} {old_pos[s]}->{new_pos[s]}" for s in changed)
        )
    if not (removed or added or changed):
        print("      positions: unchanged")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="actually write to DB (otherwise dry-run)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== rebuild_state_from_alpaca.py ({mode}) ===\n")

    if args.apply:
        path = backup_db()
        print(f"DB backed up to: {path}\n")

    users = db.list_users()
    for u in users:
        plan = rebuild_user(u["user_id"], u["username"], apply=args.apply)
        print_plan(u["username"], plan)

    if not args.apply:
        print("\nThis was a DRY-RUN. Nothing was written.")
        print("Review the plan above, then re-run with --apply to commit.")
    else:
        print("\nDone. Re-run scripts/reconcile_alpaca.py to verify.")


if __name__ == "__main__":
    main()
