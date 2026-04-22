"""
Reconcile DB portfolio_state against real Alpaca paper accounts.

For each user with saved Alpaca credentials, compare:
  DB:     cash / portfolio_value / open positions
  Alpaca: cash / equity          / open positions

Prints a per-user table plus a diff so you can see at a glance which
accounts have DB numbers that disagree with the broker.

Usage (from project root):
    python scripts/reconcile_alpaca.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import database as db
from src import broker_alpaca as broker


INITIAL_CAPITAL = 100_000.0


def fmt_money(x):
    if x is None:
        return "     -    "
    return f"{x:>12,.2f}"


def fmt_diff(x):
    if x is None:
        return "     -    "
    sign = "+" if x >= 0 else "-"
    return f"{sign}{abs(x):>11,.2f}"


def load_db_snapshot(user_id: str):
    pf = db.load_portfolio(user_id) or {}
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT symbol, quantity, current_price FROM positions WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    positions = {r["symbol"]: {"qty": r["quantity"], "price": r["current_price"]} for r in rows}
    return {
        "cash": pf.get("cash"),
        "portfolio_value": pf.get("portfolio_value"),
        "positions": positions,
    }


def load_alpaca_snapshot(api_key: str, api_secret: str):
    account = broker.get_account_info(api_key, api_secret)
    positions = broker.get_positions(api_key, api_secret)
    pos_map = {p["symbol"]: {"qty": p["qty"], "price": p["current_price"]} for p in positions}
    return {
        "cash": account["cash"],
        "equity": account["equity"],
        "positions": pos_map,
    }


def diff_positions(db_pos, alp_pos):
    symbols = sorted(set(db_pos) | set(alp_pos))
    rows = []
    for s in symbols:
        d = db_pos.get(s)
        a = alp_pos.get(s)
        d_qty = d["qty"] if d else 0
        a_qty = a["qty"] if a else 0
        if abs(d_qty - a_qty) > 1e-6:
            rows.append((s, d_qty, a_qty, a_qty - d_qty))
    return rows


def main():
    users = db.list_users()
    print(f"Found {len(users)} users\n")

    header = f"{'user':<22} {'DB equity':>12} {'Alpaca equity':>14} {'diff':>12}  {'DB cash':>12} {'Alpaca cash':>12}  positions"
    print(header)
    print("-" * len(header))

    suspicious = []

    for u in users:
        uid = u["user_id"]
        uname = u["username"]
        creds = db.get_alpaca_credentials(uid)

        db_snap = load_db_snapshot(uid)

        if not creds:
            print(
                f"{uname:<22} {fmt_money(db_snap['portfolio_value'])} "
                f"{'  (no creds)':>14} {'':>12}  {fmt_money(db_snap['cash'])} {'':>12}  -"
            )
            continue

        try:
            alp_snap = load_alpaca_snapshot(creds["api_key"], creds["api_secret"])
        except Exception as e:
            print(f"{uname:<22} {fmt_money(db_snap['portfolio_value'])}  Alpaca error: {e}")
            continue

        db_eq = db_snap["portfolio_value"] or 0.0
        alp_eq = alp_snap["equity"]
        eq_diff = alp_eq - db_eq

        pos_diffs = diff_positions(db_snap["positions"], alp_snap["positions"])
        pos_summary = f"{len(pos_diffs)} mismatched" if pos_diffs else "ok"

        print(
            f"{uname:<22} {fmt_money(db_eq)} {fmt_money(alp_eq)} {fmt_diff(eq_diff)}  "
            f"{fmt_money(db_snap['cash'])} {fmt_money(alp_snap['cash'])}  {pos_summary}"
        )

        if abs(eq_diff) > 1.0 or pos_diffs:
            suspicious.append((uname, db_eq, alp_eq, eq_diff, pos_diffs))

    if not suspicious:
        print("\nAll accounts reconcile.")
        return

    print("\n=== Accounts with DB/Alpaca drift ===")
    for uname, db_eq, alp_eq, eq_diff, pos_diffs in suspicious:
        print(f"\n{uname}:")
        print(f"  DB equity:     {db_eq:>12,.2f}")
        print(f"  Alpaca equity: {alp_eq:>12,.2f}")
        print(f"  diff:          {eq_diff:>+12,.2f}  (Alpaca - DB)")
        print(f"  DB pnl vs $100k start: {db_eq - INITIAL_CAPITAL:>+12,.2f}")
        print(f"  real pnl vs $100k:     {alp_eq - INITIAL_CAPITAL:>+12,.2f}")
        if pos_diffs:
            print("  position mismatches (symbol: DB qty / Alpaca qty / Alpaca-DB):")
            for s, d_qty, a_qty, delta in pos_diffs:
                print(f"    {s:<6} {d_qty:>8} / {a_qty:>8} / {delta:>+8}")


if __name__ == "__main__":
    main()
