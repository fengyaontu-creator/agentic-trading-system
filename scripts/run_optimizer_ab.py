"""Run Phase 4 A/B: random search vs Bayesian search on local CSV history."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from optimizer.bayesian import bayesian_search
from optimizer.random_search import DEFAULT_SPACE, random_search
from scripts.run_random_search_baseline import (
    load_local_histories,
    ml_signal_strategy,
    report_to_jsonable,
)
from backtest import BacktestConfig
from backtest.fills import FillConfig
from backtest.strategy import CallableStrategy


def _config():
    return BacktestConfig(
        initial_capital=100_000,
        warmup_bars=1,
        allow_shorts=False,
        fill=FillConfig(
            slippage_bps=5,
            commission_pct=0.0,
            sec_fee_per_million=20.60,
            taf_per_share=0.000166,
        ),
    )


def _comparison_text(random_report, bayesian_report, min_sharpe_improvement):
    sharpe_delta = bayesian_report.avg_oos_sharpe - random_report.avg_oos_sharpe
    return_delta = bayesian_report.avg_oos_return_pct - random_report.avg_oos_return_pct
    bayesian_wins = (
        bayesian_report.decision == "proceed"
        and sharpe_delta >= min_sharpe_improvement
        and bayesian_report.avg_oos_return_pct >= random_report.avg_oos_return_pct
    )
    decision = "ADOPT_BAYESIAN" if bayesian_wins else "KEEP_RANDOM"
    reason = (
        f"Bayesian OOS Sharpe improved by {sharpe_delta:.2f} "
        f"and OOS return delta was {return_delta:.2f}%."
        if bayesian_wins
        else (
            f"Bayesian did not clear the +{min_sharpe_improvement:.2f} OOS Sharpe hurdle "
            f"with non-worse return. Sharpe delta={sharpe_delta:.2f}, "
            f"return delta={return_delta:.2f}%."
        )
    )
    text = (
        "=== Optimizer A/B Report ===\n"
        f"Trial budget per method/window: same\n\n"
        "[Random]\n"
        f"Windows: {random_report.profitable_windows} / {random_report.total_windows} profitable\n"
        f"Avg OOS Sharpe: {random_report.avg_oos_sharpe:.2f}\n"
        f"Avg OOS Return: {random_report.avg_oos_return_pct:.2f}%\n"
        f"Avg Max Drawdown: {random_report.avg_max_drawdown_pct:.2f}%\n\n"
        "[Bayesian]\n"
        f"Windows: {bayesian_report.profitable_windows} / {bayesian_report.total_windows} profitable\n"
        f"Avg OOS Sharpe: {bayesian_report.avg_oos_sharpe:.2f}\n"
        f"Avg OOS Return: {bayesian_report.avg_oos_return_pct:.2f}%\n"
        f"Avg Max Drawdown: {bayesian_report.avg_max_drawdown_pct:.2f}%\n\n"
        f"{decision}: {reason}"
    )
    return decision, sharpe_delta, return_delta, text


def main():
    output_dir = ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)

    n_trials = int(os.getenv("OPTIMIZER_AB_TRIALS", "10"))
    n_initial = int(os.getenv("BAYESIAN_INITIAL_POINTS", str(min(5, n_trials))))
    seed = int(os.getenv("OPTIMIZER_AB_SEED", "42"))
    min_sharpe_improvement = float(os.getenv("BAYESIAN_MIN_SHARPE_IMPROVEMENT", "0.30"))

    histories = load_local_histories(ROOT / "data")
    strategy = CallableStrategy(ml_signal_strategy)
    config = _config()

    random_report = random_search(
        DEFAULT_SPACE,
        histories,
        strategy,
        n_trials=n_trials,
        seed=seed,
        config=config,
    )
    bayesian_report = bayesian_search(
        DEFAULT_SPACE,
        histories,
        strategy,
        n_trials=n_trials,
        n_initial_points=n_initial,
        seed=seed,
        config=config,
    )

    decision, sharpe_delta, return_delta, text = _comparison_text(
        random_report,
        bayesian_report,
        min_sharpe_improvement,
    )

    payload = {
        "decision": decision,
        "sharpe_delta": sharpe_delta,
        "return_delta": return_delta,
        "min_sharpe_improvement": min_sharpe_improvement,
        "random": report_to_jsonable(random_report),
        "bayesian": report_to_jsonable(bayesian_report),
    }
    (output_dir / "optimizer_ab_report.txt").write_text(text + "\n", encoding="utf-8")
    (output_dir / "optimizer_ab_report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(text)
    print(f"\nWrote {output_dir / 'optimizer_ab_report.txt'}")
    print(f"Wrote {output_dir / 'optimizer_ab_report.json'}")


if __name__ == "__main__":
    main()
