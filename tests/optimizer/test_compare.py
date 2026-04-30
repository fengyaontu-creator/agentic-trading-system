import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from backtest import BacktestParams
from optimizer.compare import (
    FixedParamReport,
    ParamComparisonReport,
    current_settings_to_params,
    dict_to_params,
)


def _fixed_report(sharpe, ret, drawdown, wins):
    return FixedParamReport(
        params=BacktestParams(),
        windows=[],
        profitable_windows=wins,
        avg_oos_sharpe=sharpe,
        avg_oos_return_pct=ret,
        avg_max_drawdown_pct=drawdown,
        total_windows=30,
    )


def test_params_helpers_preserve_defaults_and_cast_values():
    settings = {"risk_per_trade": "0.03", "take_profit_pct": 0.07}
    params = current_settings_to_params(settings)

    assert params.risk_per_trade == 0.03
    assert params.take_profit_pct == 0.07
    assert params.max_concentration == BacktestParams().max_concentration

    params2 = dict_to_params({"min_confidence": "0.5"})
    assert params2.min_confidence == 0.5


def test_comparison_text_includes_delta_and_recommendation():
    report = ParamComparisonReport(
        current=_fixed_report(0.6, 0.1, -4.0, 16),
        optimized=_fixed_report(0.8, 0.3, -3.0, 19),
        delta={
            "avg_oos_sharpe": 0.2,
            "avg_oos_return_pct": 0.2,
            "avg_max_drawdown_pct": 1.0,
            "profitable_windows": 3,
        },
        save_recommended=True,
        reason="optimized params improve current DB params",
    )

    text = report.to_text()

    assert "Current DB Params" in text
    assert "Optimized Guarded Params" in text
    assert "Save recommended: True" in text
