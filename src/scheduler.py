"""
scheduler.py -- Cron entry point + concurrent dispatch.

Three sessions per day (all times ET / New York):

    07:30  analyze  -- fetch data, run LLM analysis, save signals to DB
    09:50  trade    -- read today's signals from DB, execute open orders
    15:30  close    -- flatten all open positions (end-of-day)

Crontab (Singapore time, summer/DST, UTC+8):
    30 19 * * 1-5  cd /path/to/project && python src/scheduler.py --session analyze
    50 21 * * 1-5  cd /path/to/project && python src/scheduler.py --session trade
    30  3 * * 2-6  cd /path/to/project && python src/scheduler.py --session close
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from services.trading_sessions import analyze_for_user, trade_for_user, close_for_user
from param_optimizer import optimize_all_users
import database as db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "..", "scheduler.log"),
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger(__name__)

_SESSION_FN = {
    "analyze": analyze_for_user,
    "trade": trade_for_user,
    "close": close_for_user,
}


def run_all_users(session: str, max_workers: int = 4):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if session in {"trade", "close"}:
        api_key = api_key or None
    elif not api_key:
        log.error("OPENROUTER_API_KEY not set -- aborting")
        sys.exit(1)

    db.init_db()
    users = db.list_users()
    if not users:
        log.info("No users registered yet -- nothing to do")
        return

    log.info(f"=== Scheduler [{session.upper()}] {datetime.now(timezone.utc).isoformat()} ===")
    log.info(f"Running for {len(users)} user(s) with max_workers={max_workers}")

    if session == "analyze" and api_key:
        log.info("Running AI parameter optimization before analysis...")
        optimize_all_users(api_key)

    worker_fn = _SESSION_FN[session]
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(worker_fn, user, api_key): user["user_id"]
            for user in users
        }
        for future in as_completed(futures):
            user_id = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                log.error(f"[{session.upper()}] {user_id} failed: {exc}", exc_info=True)
                results.append({"user_id": user_id, "status": "error", "reason": str(exc)})

    ok      = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    errors  = [r for r in results if r["status"] == "error"]
    log.info(
        f"=== Done === ok={len(ok)} skipped={len(skipped)} errors={len(errors)}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run analysis or trading for all users")
    parser.add_argument(
        "--session",
        choices=list(_SESSION_FN),
        default="analyze",
        help="'analyze' saves signals; 'trade' executes; 'close' flattens EOD",
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    run_all_users(session=args.session, max_workers=args.workers)
