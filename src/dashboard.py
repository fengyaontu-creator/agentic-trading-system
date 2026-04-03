"""
dashboard.py — 交易结果可视化 + 报告生成
Owner: Person E

生成以下图表：
1. 价格走势 + 买卖点标注
2. 累计收益曲线
3. 持仓分布饼图
4. 回测绩效摘要表
5. Agent 决策流程图（用于 PPT）
"""

import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Dict, List, Optional


# ============================================================================
# 全局样式设置
# ============================================================================

def setup_plot_style():
    """Configure consistent plot styling."""
    plt.style.use('seaborn-v0_8-whitegrid')
    plt.rcParams.update({
        'figure.figsize': (12, 6),
        'font.size': 11,
        'axes.titlesize': 14,
        'axes.labelsize': 12,
        'lines.linewidth': 1.5,
    })


# ============================================================================
# 图表 1：价格走势 + 买卖点
# ============================================================================

def plot_price_with_signals(
    price_data: pd.DataFrame,
    trades: List[Dict],
    symbol: str,
    save_path: str = "outputs/presentation_assets/price_signals.png"
):
    """
    Plot stock price with buy/sell markers overlaid.

    Args:
        price_data: DataFrame with 'close' column (index = datetime)
        trades: List of trade dicts with 'date', 'side', 'price'
        symbol: Stock ticker for title
        save_path: Where to save the figure
    """
    setup_plot_style()
    fig, ax = plt.subplots(figsize=(14, 7))

    # Price line
    ax.plot(price_data.index, price_data['close'], label='Close Price',
            color='#2196F3', linewidth=1.5)

    # Buy/sell markers
    for trade in trades:
        # TODO: Parse trade dates and plot markers
        # -------------------------------------------------------
        # date = pd.to_datetime(trade['date'])
        # if trade['side'] == 'BUY':
        #     ax.scatter(date, trade['price'], marker='^', color='green',
        #                s=150, zorder=5, label='Buy' if 'Buy' not in str(ax.get_legend()) else '')
        # elif trade['side'] == 'SELL':
        #     ax.scatter(date, trade['price'], marker='v', color='red',
        #                s=150, zorder=5, label='Sell' if 'Sell' not in str(ax.get_legend()) else '')
        # -------------------------------------------------------
        pass

    ax.set_title(f'{symbol} — Price with Trading Signals')
    ax.set_xlabel('Date')
    ax.set_ylabel('Price ($)')
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {save_path}")


# ============================================================================
# 图表 2：累计收益曲线
# ============================================================================

def plot_portfolio_performance(
    portfolio_history: pd.DataFrame,
    initial_capital: float = 100000,
    benchmark_data: pd.DataFrame = None,
    save_path: str = "outputs/presentation_assets/portfolio_performance.png"
):
    """
    Plot cumulative portfolio value over time, optionally vs a benchmark.

    Args:
        portfolio_history: DataFrame with 'date' and 'value' columns
        initial_capital: Starting capital for reference line
        benchmark_data: Optional DataFrame with benchmark prices
        save_path: Where to save the figure
    """
    setup_plot_style()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), height_ratios=[3, 1])

    # -- Top: Portfolio value --
    dates = pd.to_datetime(portfolio_history['date'])
    values = portfolio_history['value']

    ax1.plot(dates, values, label='Portfolio Value', color='#4CAF50', linewidth=2)
    ax1.axhline(y=initial_capital, color='gray', linestyle='--', alpha=0.5,
                label='Initial Capital')

    # TODO: Add benchmark comparison if benchmark_data is provided
    # -------------------------------------------------------
    # if benchmark_data is not None:
    #     bench_normalized = benchmark_data['close'] / benchmark_data['close'].iloc[0] * initial_capital
    #     ax1.plot(benchmark_data.index, bench_normalized, label='Benchmark (SPY)',
    #              color='#FF9800', alpha=0.7)
    # -------------------------------------------------------

    ax1.set_title('Portfolio Performance')
    ax1.set_ylabel('Portfolio Value ($)')
    ax1.legend()
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

    # -- Bottom: Drawdown --
    cummax = values.cummax()
    drawdown = (values - cummax) / cummax * 100

    ax2.fill_between(dates, drawdown, 0, color='red', alpha=0.3)
    ax2.plot(dates, drawdown, color='red', linewidth=0.8)
    ax2.set_title('Drawdown')
    ax2.set_ylabel('Drawdown (%)')
    ax2.set_xlabel('Date')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {save_path}")


# ============================================================================
# 图表 3：持仓分布饼图
# ============================================================================

def plot_position_allocation(
    positions: Dict[str, float],
    cash: float,
    save_path: str = "outputs/presentation_assets/allocation.png"
):
    """
    Plot current portfolio allocation as a pie chart.

    Args:
        positions: {symbol: market_value} for each position
        cash: Available cash
        save_path: Where to save the figure
    """
    setup_plot_style()
    fig, ax = plt.subplots(figsize=(8, 8))

    labels = list(positions.keys()) + ['Cash']
    values = list(positions.values()) + [cash]
    colors = plt.cm.Set3(range(len(labels)))

    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct='%1.1f%%',
        colors=colors, startangle=90,
        textprops={'fontsize': 11}
    )

    ax.set_title('Portfolio Allocation')
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {save_path}")


# ============================================================================
# 图表 4：绩效摘要表
# ============================================================================

def plot_performance_summary_table(
    metrics: Dict,
    save_path: str = "outputs/presentation_assets/performance_summary.png"
):
    """
    Render performance metrics as a styled table image (for PPT).

    Args:
        metrics: Dict from backtester.generate_performance_report()
        save_path: Where to save the figure
    """
    setup_plot_style()
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.axis('off')

    table_data = [
        ['Metric', 'Value'],
        ['Initial Capital', f"${metrics.get('initial_capital', 0):,.0f}"],
        ['Final Value', f"${metrics.get('final_value', 0):,.2f}"],
        ['Total Return', f"{metrics.get('total_return_pct', 0):+.2f}%"],
        ['Sharpe Ratio', f"{metrics.get('sharpe_ratio', 0):.4f}"],
        ['Sortino Ratio', f"{metrics.get('sortino_ratio', 0):.4f}"],
        ['Max Drawdown', f"{metrics.get('max_drawdown_pct', 0):.2f}%"],
        ['Total Trades', f"{metrics.get('total_trades', 0)}"],
        ['Win Rate', f"{metrics.get('win_rate', 0):.1f}%"],
        ['Profit Factor', f"{metrics.get('profit_factor', 0):.4f}"],
    ]

    table = ax.table(
        cellText=table_data[1:],
        colLabels=table_data[0],
        cellLoc='center',
        loc='center'
    )

    table.auto_set_font_size(False)
    table.set_fontsize(12)
    table.scale(1.2, 1.8)

    # Style header
    for j in range(2):
        table[0, j].set_facecolor('#2196F3')
        table[0, j].set_text_props(color='white', fontweight='bold')

    # Alternate row colors
    for i in range(1, len(table_data)):
        color = '#f5f5f5' if i % 2 == 0 else 'white'
        for j in range(2):
            table[i, j].set_facecolor(color)

    ax.set_title('Backtest Performance Summary', fontsize=16, fontweight='bold', pad=20)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {save_path}")


# ============================================================================
# 图表 5：Agent 架构图（用于 PPT）
# ============================================================================

def plot_agent_architecture(
    save_path: str = "outputs/presentation_assets/architecture.png"
):
    """
    Draw the agent pipeline architecture diagram for presentation.
    """
    setup_plot_style()
    fig, ax = plt.subplots(figsize=(16, 8))
    ax.axis('off')

    # TODO: Draw boxes and arrows for the 4-agent pipeline
    # -------------------------------------------------------
    # This is best done with matplotlib patches and annotations.
    # Alternatively, use draw.io / PowerPoint directly.
    #
    # Suggested layout:
    #
    #  [yfinance] → [Technical Agent] ↘
    #                                   → [Risk Agent] → [Execution Agent] → [Alpaca]
    #  [NewsAPI]  → [Sentiment Agent] ↗
    #
    # -------------------------------------------------------

    ax.text(0.5, 0.5, 'Agent Architecture Diagram\n(TODO: implement with patches)',
            ha='center', va='center', fontsize=16, color='gray')

    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {save_path}")


# ============================================================================
# 一键生成所有图表
# ============================================================================

def generate_all_charts(
    portfolio_history_path: str = "outputs/portfolio_history.csv",
    trades_path: str = "outputs/execution_log.csv",
    metrics_path: str = "outputs/backtest_metrics.json",
    initial_capital: float = 100000
):
    """
    Load data from output files and generate all presentation charts.

    Run this after backtesting is complete.
    """
    import os
    os.makedirs("outputs/presentation_assets", exist_ok=True)

    # Load data
    if os.path.exists(portfolio_history_path):
        portfolio_df = pd.read_csv(portfolio_history_path)
        plot_portfolio_performance(portfolio_df, initial_capital)
    else:
        print(f"WARNING: {portfolio_history_path} not found, skipping portfolio chart")

    if os.path.exists(trades_path):
        trades = pd.read_csv(trades_path).to_dict('records')
    else:
        trades = []
        print(f"WARNING: {trades_path} not found")

    if os.path.exists(metrics_path):
        with open(metrics_path) as f:
            metrics = json.load(f)
        plot_performance_summary_table(metrics)
    else:
        print(f"WARNING: {metrics_path} not found, skipping summary table")

    plot_agent_architecture()

    print("\nAll charts generated in outputs/presentation_assets/")


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    print("Testing dashboard...")

    # Generate sample performance summary
    sample_metrics = {
        "initial_capital": 100000,
        "final_value": 108530.50,
        "total_return_pct": 8.53,
        "sharpe_ratio": 1.2345,
        "sortino_ratio": 1.8765,
        "max_drawdown_pct": -5.23,
        "total_trades": 42,
        "win_rate": 57.1,
        "profit_factor": 1.85,
    }

    import os
    os.makedirs("outputs/presentation_assets", exist_ok=True)
    plot_performance_summary_table(sample_metrics)
    plot_agent_architecture()
    print("Test charts saved.")
