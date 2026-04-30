"""Audit whether a user's watchlist is ready for walk-forward optimization."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import database as db
from optimizer.walk_forward import available_local_symbols


def main():
    user_id = os.getenv("AUDIT_USER_ID", "nora")
    min_symbols = int(os.getenv("NEW_OPTIMIZER_MIN_SYMBOLS", "3"))
    data_dir = ROOT / "data"
    requested = [symbol.upper() for symbol in db.get_user_symbols(user_id)]
    available = available_local_symbols(data_dir)
    usable = [symbol for symbol in requested if symbol in available]
    missing = [symbol for symbol in requested if symbol not in available]
    suggestions = [symbol for symbol in available if symbol not in usable][: max(0, min_symbols - len(usable))]
    allowed = len(usable) >= min_symbols
    reason = (
        "watchlist has enough local symbols"
        if allowed
        else f"watchlist has {len(usable)} local symbol(s); need at least {min_symbols}"
    )
    payload = {
        "user_id": user_id,
        "allowed": allowed,
        "reason": reason,
        "requested_symbols": requested,
        "usable_symbols": usable,
        "missing_local_data": missing,
        "available_local_symbols": available,
        "suggested_additions": suggestions,
    }
    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    safe_user = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in user_id)
    (out_dir / f"watchlist_audit_{safe_user}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    text = (
        "=== Watchlist Audit ===\n"
        f"User: {user_id}\n"
        f"Allowed: {allowed}\n"
        f"Reason: {reason}\n"
        f"Requested: {', '.join(requested) if requested else '(none)'}\n"
        f"Usable local data: {', '.join(usable) if usable else '(none)'}\n"
        f"Missing local data: {', '.join(missing) if missing else '(none)'}\n"
        f"Suggested additions: {', '.join(suggestions) if suggestions else '(none)'}\n"
    )
    (out_dir / f"watchlist_audit_{safe_user}.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
