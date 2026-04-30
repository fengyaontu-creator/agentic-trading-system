"""Compare current DB params against latest walk-forward guarded params."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import database as db
from optimizer.compare import (
    compare_current_vs_optimized,
    current_settings_to_params,
    dict_to_params,
    report_to_jsonable,
)
from optimizer.random_search import random_search
from optimizer.walk_forward import (
    aggregate_params,
    apply_safety_guards,
    build_search_space,
    default_backtest_config,
    evaluate_save_recommendation,
    load_local_histories,
    ml_signal_strategy,
)
from backtest.strategy import CallableStrategy


def main():
    user_id = os.getenv("COMPARE_USER_ID", "nora")
    trials = int(os.getenv("WALK_FORWARD_RANDOM_TRIALS", "30"))
    settings = db.load_user_settings(user_id)
    symbols = db.get_user_symbols(user_id)
    histories = load_local_histories(symbols, ROOT / "data")
    if not histories:
        raise SystemExit(f"No usable local histories for {user_id}")

    strategy = CallableStrategy(ml_signal_strategy)
    config = default_backtest_config()
    search_report = random_search(
        build_search_space(settings.get("risk_preference", "moderate")),
        histories,
        strategy,
        n_trials=trials,
        seed=int(os.getenv("WALK_FORWARD_RANDOM_SEED", "42")),
        config=config,
    )
    if search_report.decision != "proceed":
        print(search_report.to_text())
        raise SystemExit("Random search STOP gate failed; no optimized comparison available.")

    proposed = aggregate_params(search_report)
    safety = apply_safety_guards(settings, proposed, build_search_space(settings.get("risk_preference", "moderate")), search_report)
    save_gate = evaluate_save_recommendation(search_report)
    optimized_values = safety["params"] if safety["allowed"] else proposed

    report = compare_current_vs_optimized(
        histories,
        strategy,
        [item.window for item in search_report.windows],
        current_settings_to_params(settings),
        dict_to_params(optimized_values),
        config,
        min_sharpe_delta=float(os.getenv("COMPARE_MIN_SHARPE_DELTA", "0.10")),
        min_return_delta=float(os.getenv("COMPARE_MIN_RETURN_DELTA", "0.05")),
    )

    payload = report_to_jsonable(report)
    payload["optimizer_save_gate"] = save_gate
    payload["optimizer_safety"] = {
        "allowed": safety["allowed"],
        "reason": safety["reason"],
        "params": safety.get("params", {}),
    }
    output_dir = ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)
    safe_user = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in user_id)
    (output_dir / f"current_vs_optimized_{safe_user}.txt").write_text(report.to_text() + "\n", encoding="utf-8")
    (output_dir / f"current_vs_optimized_{safe_user}.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    print(report.to_text())
    print(f"\nOptimizer save gate: {save_gate}")


if __name__ == "__main__":
    main()
