"""Production-facing walk-forward optimizer entrypoint.

This module uses the Phase 3 random-search baseline. Bayesian search remains
available for offline A/B, but is not adopted because it did not beat random
search on the local OOS comparison.
"""

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

import database as db
from backtest import BacktestConfig, BacktestParams
from backtest.fills import FillConfig
from backtest.strategy import CallableStrategy, Signal
from data_tools import calculate_technical_indicators, generate_ml_signal
from optimizer.random_search import RandomSearchReport, random_search


ROOT = Path(__file__).resolve().parents[2]


_RISK_SPACES = {
    "conservative": {
        "risk_per_trade": (0.005, 0.015),
        "max_concentration": (0.05, 0.08),
        "stop_loss_multiplier": (1.0, 2.0),
        "take_profit_pct": (0.02, 0.06),
        "min_confidence": (0.40, 0.65),
    },
    "moderate": {
        "risk_per_trade": (0.015, 0.03),
        "max_concentration": (0.08, 0.12),
        "stop_loss_multiplier": (1.5, 2.5),
        "take_profit_pct": (0.03, 0.08),
        "min_confidence": (0.30, 0.55),
    },
    "aggressive": {
        "risk_per_trade": (0.02, 0.04),
        "max_concentration": (0.12, 0.20),
        "stop_loss_multiplier": (2.0, 3.5),
        "take_profit_pct": (0.05, 0.12),
        "min_confidence": (0.20, 0.45),
    },
}


def walk_forward_optimize(
    user_id: str,
    n_trials: Optional[int] = None,
    data_dir: Optional[Path] = None,
) -> Optional[Dict]:
    """Optimize and save user parameters with random-search walk-forward.

    Returns saved params on success. Returns None when there is no usable local
    data or the random-search STOP gate fails.
    """
    settings = db.load_user_settings(user_id)
    risk_pref = settings.get("risk_preference", "moderate")
    symbols = db.get_user_symbols(user_id)
    if not symbols:
        _set_optimizer_status(user_id, "skipped", "no symbols in watchlist")
        return None

    histories = load_local_histories(symbols, data_dir or ROOT / "data")
    if not histories:
        _set_optimizer_status(user_id, "skipped", "no local historical data for watchlist")
        return None

    min_symbols = _min_symbols_required()
    if len(histories) < min_symbols:
        reason = (
            f"watchlist has {len(histories)} local symbol(s); "
            f"need at least {min_symbols} for diversified walk-forward optimization"
        )
        _write_watchlist_audit(user_id, symbols, histories.keys(), data_dir or ROOT / "data", reason)
        _set_optimizer_status(user_id, "skipped", reason)
        return None

    trials = n_trials if n_trials is not None else int(os.getenv("WALK_FORWARD_RANDOM_TRIALS", "30"))
    report = random_search(
        build_search_space(risk_pref),
        histories,
        CallableStrategy(ml_signal_strategy),
        n_trials=trials,
        seed=int(os.getenv("WALK_FORWARD_RANDOM_SEED", "42")),
        config=default_backtest_config(),
    )
    _write_user_report(user_id, report)

    if report.decision != "proceed":
        safety = {"allowed": False, "reason": report.reason, "params": {}}
        _write_user_audit(user_id, settings, {}, safety, report)
        _set_optimizer_status(user_id, "failed", report.reason[:200])
        return None

    proposed_params = aggregate_params(report)
    safety = apply_safety_guards(settings, proposed_params, build_search_space(risk_pref), report)
    save_recommendation = evaluate_save_recommendation(report)
    _write_user_audit(user_id, settings, proposed_params, safety, report, save_recommendation)
    if not safety["allowed"]:
        _set_optimizer_status(user_id, "failed", safety["reason"][:200])
        return None

    params = safety["params"]
    if not save_recommendation["recommended"]:
        _set_optimizer_status(user_id, "skipped", save_recommendation["reason"][:200])
        return params

    if _dry_run_enabled():
        _set_optimizer_status(
            user_id,
            "skipped",
            (
                f"dry-run walk-forward: {report.profitable_windows}/{report.total_windows} "
                f"profitable, avg OOS Sharpe {report.avg_oos_sharpe:.2f}"
            ),
        )
        return params

    db_params = {
        **params,
        "strategy": settings.get("strategy", "intraday"),
        "risk_preference": risk_pref,
    }
    db.save_user_settings(user_id, **db_params)
    _set_optimizer_status(
        user_id,
        "ok",
        (
            f"walk-forward random: {report.profitable_windows}/{report.total_windows} "
            f"profitable, avg OOS Sharpe {report.avg_oos_sharpe:.2f}"
        ),
    )
    return params


def build_search_space(risk_preference: str) -> Dict:
    return dict(_RISK_SPACES.get(risk_preference, _RISK_SPACES["moderate"]))


def default_backtest_config() -> BacktestConfig:
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


def load_local_histories(symbols: Iterable[str], data_dir: Path) -> Dict[str, pd.DataFrame]:
    histories = {}
    for symbol in symbols:
        path = data_dir / f"{symbol.upper()}_hist.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        frame.columns = [str(col).lower() for col in frame.columns]
        date_col = "date" if "date" in frame.columns else frame.columns[0]
        frame[date_col] = pd.to_datetime(frame[date_col], utc=True).dt.tz_convert(None).dt.normalize()
        frame = frame.set_index(date_col).sort_index()
        histories[symbol.upper()] = calculate_technical_indicators(
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


def aggregate_params(report: RandomSearchReport) -> Dict:
    profitable = [
        item.best_train.params
        for item in report.windows
        if float(item.validation.metrics.get("total_return_pct", 0.0)) > 0
    ]
    source = profitable or [item.best_train.params for item in report.windows]
    if not source:
        return asdict(BacktestParams())

    fields = asdict(BacktestParams()).keys()
    out = {}
    for field in fields:
        values = sorted(float(getattr(params, field)) for params in source)
        middle = len(values) // 2
        if len(values) % 2:
            out[field] = values[middle]
        else:
            out[field] = (values[middle - 1] + values[middle]) / 2
        out[field] = round(out[field], 4)
    return out


def apply_safety_guards(
    current_settings: Dict,
    proposed_params: Dict,
    search_space: Dict,
    report: RandomSearchReport,
) -> Dict:
    max_drawdown_limit = float(os.getenv("NEW_OPTIMIZER_MAX_DRAWDOWN_PCT", "15.0"))
    max_change_ratio = float(os.getenv("NEW_OPTIMIZER_MAX_PARAM_CHANGE", "0.25"))
    if abs(float(report.avg_max_drawdown_pct)) > max_drawdown_limit:
        return {
            "allowed": False,
            "reason": (
                f"OOS drawdown {report.avg_max_drawdown_pct:.2f}% exceeds "
                f"{max_drawdown_limit:.2f}% safety limit"
            ),
            "params": {},
        }

    guarded = {}
    for name, proposed in proposed_params.items():
        value = float(proposed)
        if name in search_space:
            lo, hi = search_space[name]
            value = min(float(hi), max(float(lo), value))

        current = current_settings.get(name)
        if current is not None:
            current = float(current)
            if current != 0:
                lower = current * (1 - max_change_ratio)
                upper = current * (1 + max_change_ratio)
                value = min(upper, max(lower, value))

        guarded[name] = round(value, 4)

    return {
        "allowed": True,
        "reason": "safety guards applied",
        "params": guarded,
    }


def evaluate_save_recommendation(report: RandomSearchReport) -> Dict:
    min_profitable_ratio = float(os.getenv("NEW_OPTIMIZER_MIN_PROFITABLE_RATIO", "0.60"))
    min_return = float(os.getenv("NEW_OPTIMIZER_MIN_OOS_RETURN_PCT", "0.20"))
    min_sharpe = float(os.getenv("NEW_OPTIMIZER_MIN_OOS_SHARPE", "0.80"))

    total_windows = max(1, int(report.total_windows))
    profitable_ratio = int(report.profitable_windows) / total_windows
    failures = []
    if profitable_ratio < min_profitable_ratio:
        failures.append(
            f"profitable ratio {profitable_ratio:.2%} below {min_profitable_ratio:.2%}"
        )
    if float(report.avg_oos_return_pct) < min_return:
        failures.append(
            f"avg OOS return {report.avg_oos_return_pct:.2f}% below {min_return:.2f}%"
        )
    if float(report.avg_oos_sharpe) < min_sharpe:
        failures.append(
            f"avg OOS Sharpe {report.avg_oos_sharpe:.2f} below {min_sharpe:.2f}"
        )

    if failures:
        return {
            "recommended": False,
            "reason": "; ".join(failures),
            "profitable_ratio": round(profitable_ratio, 4),
        }
    return {
        "recommended": True,
        "reason": "OOS metrics clear save thresholds",
        "profitable_ratio": round(profitable_ratio, 4),
    }


def _dry_run_enabled() -> bool:
    return os.getenv("NEW_OPTIMIZER_DRY_RUN", "true").strip().lower() in {"1", "true", "yes", "on"}


def _min_symbols_required() -> int:
    return int(os.getenv("NEW_OPTIMIZER_MIN_SYMBOLS", "3"))


def _set_optimizer_status(user_id: str, status: str, reason: str) -> None:
    db.save_user_settings(user_id)
    db.set_param_optimization_status(user_id, status, reason)


def available_local_symbols(data_dir: Path) -> list[str]:
    return sorted(path.name.replace("_hist.csv", "") for path in data_dir.glob("*_hist.csv"))


def _write_watchlist_audit(
    user_id: str,
    requested_symbols: Iterable[str],
    usable_symbols: Iterable[str],
    data_dir: Path,
    reason: str,
) -> None:
    output_dir = ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)
    safe_user = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in user_id)
    requested = [symbol.upper() for symbol in requested_symbols]
    usable = sorted(symbol.upper() for symbol in usable_symbols)
    available = available_local_symbols(data_dir)
    suggested = [symbol for symbol in available if symbol not in usable][: max(0, _min_symbols_required() - len(usable))]
    payload = {
        "user_id": user_id,
        "allowed": False,
        "reason": reason,
        "requested_symbols": requested,
        "usable_symbols": usable,
        "min_symbols": _min_symbols_required(),
        "available_local_symbols": available,
        "suggested_additions": suggested,
    }
    lines = [
        "=== Watchlist Optimizer Audit ===",
        f"User: {user_id}",
        f"Allowed: False",
        f"Reason: {reason}",
        f"Requested: {', '.join(requested) if requested else '(none)'}",
        f"Usable local data: {', '.join(usable) if usable else '(none)'}",
        f"Suggested additions: {', '.join(suggested) if suggested else '(none)'}",
    ]
    (output_dir / f"watchlist_audit_{safe_user}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / f"watchlist_audit_{safe_user}.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _write_user_report(user_id: str, report: RandomSearchReport) -> None:
    output_dir = ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)
    safe_user = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in user_id)
    payload = {
        "decision": report.decision,
        "reason": report.reason,
        "total_windows": report.total_windows,
        "profitable_windows": report.profitable_windows,
        "avg_oos_sharpe": report.avg_oos_sharpe,
        "avg_oos_return_pct": report.avg_oos_return_pct,
        "avg_max_drawdown_pct": report.avg_max_drawdown_pct,
        "params_by_window": [
            {
                "train": {
                    "start": item.window.train.start.isoformat(),
                    "end": item.window.train.end.isoformat(),
                },
                "validation": {
                    "start": item.window.validation.start.isoformat(),
                    "end": item.window.validation.end.isoformat(),
                },
                "best_train_params": asdict(item.best_train.params),
                "validation_metrics": item.validation.metrics,
            }
            for item in report.windows
        ],
    }
    (output_dir / f"walk_forward_{safe_user}.txt").write_text(report.to_text() + "\n", encoding="utf-8")
    (output_dir / f"walk_forward_{safe_user}.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _write_user_audit(
    user_id: str,
    current_settings: Dict,
    proposed_params: Dict,
    safety: Dict,
    report: RandomSearchReport,
    save_recommendation: Optional[Dict] = None,
) -> None:
    output_dir = ROOT / "outputs"
    output_dir.mkdir(exist_ok=True)
    safe_user = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in user_id)
    audit_params = sorted(proposed_params)
    payload = {
        "user_id": user_id,
        "dry_run": _dry_run_enabled(),
        "allowed": safety["allowed"],
        "reason": safety["reason"],
        "save_recommended": save_recommendation["recommended"] if save_recommendation else False,
        "save_reason": save_recommendation["reason"] if save_recommendation else "not evaluated",
        "report": {
            "decision": report.decision,
            "total_windows": report.total_windows,
            "profitable_windows": report.profitable_windows,
            "avg_oos_sharpe": report.avg_oos_sharpe,
            "avg_oos_return_pct": report.avg_oos_return_pct,
            "avg_max_drawdown_pct": report.avg_max_drawdown_pct,
        },
        "params": [
            {
                "name": name,
                "current": current_settings.get(name),
                "proposed": proposed_params.get(name),
                "guarded": safety.get("params", {}).get(name),
            }
            for name in audit_params
        ],
    }
    lines = [
        "=== Walk-Forward Optimizer Audit ===",
        f"User: {user_id}",
        f"Dry run: {payload['dry_run']}",
        f"Allowed: {payload['allowed']}",
        f"Reason: {payload['reason']}",
        f"Save recommended: {payload['save_recommended']}",
        f"Save reason: {payload['save_reason']}",
        (
            f"OOS: {report.profitable_windows}/{report.total_windows} profitable, "
            f"Sharpe={report.avg_oos_sharpe:.2f}, Return={report.avg_oos_return_pct:.2f}%, "
            f"MaxDD={report.avg_max_drawdown_pct:.2f}%"
        ),
        "",
        "Parameters:",
    ]
    for item in payload["params"]:
        lines.append(
            f"- {item['name']}: current={item['current']} "
            f"proposed={item['proposed']} guarded={item['guarded']}"
        )
    (output_dir / f"walk_forward_audit_{safe_user}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / f"walk_forward_audit_{safe_user}.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
