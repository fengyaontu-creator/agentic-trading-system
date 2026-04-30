"""Run the Phase 3.5 random-search baseline on local CSV history.

This script is intentionally offline: it reads data/*_hist.csv and writes a
STOP/PROCEED report under outputs/. It does not update DB settings.
"""

import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backtest import BacktestConfig, BacktestParams
from backtest.fills import FillConfig
from backtest.strategy import CallableStrategy, Signal
from data_tools import calculate_technical_indicators, generate_ml_signal
from optimizer.random_search import DEFAULT_SPACE, random_search


def load_local_histories(data_dir: Path) -> dict[str, pd.DataFrame]:
    histories = {}
    for path in sorted(data_dir.glob("*_hist.csv")):
        symbol = path.name.replace("_hist.csv", "")
        frame = pd.read_csv(path)
        frame.columns = [str(col).lower() for col in frame.columns]
        date_col = "date" if "date" in frame.columns else frame.columns[0]
        frame[date_col] = pd.to_datetime(frame[date_col], utc=True).dt.tz_convert(None).dt.normalize()
        frame = frame.set_index(date_col).sort_index()
        histories[symbol] = calculate_technical_indicators(
            frame[["open", "high", "low", "close", "volume"]].copy()
        )
    return histories


def ml_signal_strategy(context, symbol):
    history = context.history(symbol)
    if len(history) < 55:
        return None

    raw = generate_ml_signal(history)
    side = raw.get("signal", "HOLD")
    if side == "HOLD":
        return None

    confidence = min(0.95, 0.50 + float(raw.get("confidence_boost", 0.0)))
    return Signal(symbol=symbol, side=side, confidence=confidence, reason="; ".join(raw.get("reasons", [])))


def report_to_jsonable(report):
    windows = []
    for item in report.windows:
        windows.append({
            "train": {
                "start": item.window.train.start.isoformat(),
                "end": item.window.train.end.isoformat(),
            },
            "validation": {
                "start": item.window.validation.start.isoformat(),
                "end": item.window.validation.end.isoformat(),
            },
            "best_train_params": item.best_train.params.__dict__,
            "best_train_score": item.best_train.score,
            "best_train_metrics": item.best_train.metrics,
            "validation_metrics": item.validation.metrics,
        })

    return {
        "decision": report.decision,
        "reason": report.reason,
        "total_windows": report.total_windows,
        "profitable_windows": report.profitable_windows,
        "avg_oos_sharpe": report.avg_oos_sharpe,
        "avg_oos_return_pct": report.avg_oos_return_pct,
        "avg_max_drawdown_pct": report.avg_max_drawdown_pct,
        "windows": windows,
    }


def main():
    data_dir = ROOT / "data"
    output_dir = ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)

    n_trials = int(os.getenv("RANDOM_SEARCH_TRIALS", "30"))
    seed = int(os.getenv("RANDOM_SEARCH_SEED", "42"))

    histories = load_local_histories(data_dir)
    if not histories:
        raise SystemExit(f"No *_hist.csv files found under {data_dir}")

    config = BacktestConfig(
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

    report = random_search(
        DEFAULT_SPACE,
        histories,
        CallableStrategy(ml_signal_strategy),
        n_trials=n_trials,
        seed=seed,
        config=config,
    )

    text = report.to_text()
    (output_dir / "random_search_baseline.txt").write_text(text + "\n", encoding="utf-8")
    (output_dir / "random_search_baseline.json").write_text(
        json.dumps(report_to_jsonable(report), indent=2),
        encoding="utf-8",
    )
    print(text)
    print(f"\nWrote {output_dir / 'random_search_baseline.txt'}")
    print(f"Wrote {output_dir / 'random_search_baseline.json'}")


if __name__ == "__main__":
    main()
