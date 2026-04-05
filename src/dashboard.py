"""
dashboard.py -- Trading visualization + report generation.

Charts:
    1. Price chart with buy/sell markers
    2. Cumulative return curve
    3. Position allocation pie chart
    4. Backtest performance summary table
    5. Agent pipeline architecture diagram
"""

import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Dict, List, Optional


# ============================================================================
# Global plot style
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
# Chart 1: Price with buy/sell markers
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
    buys = [t for t in trades if t.get('side') == 'BUY']
    sells = [t for t in trades if t.get('side') == 'SELL']

    if buys:
        ax.scatter(
            [pd.to_datetime(t['date']) for t in buys],
            [t['price'] for t in buys],
            marker='^', color='#00c853', s=150, zorder=5, label='Buy',
        )
    if sells:
        ax.scatter(
            [pd.to_datetime(t['date']) for t in sells],
            [t['price'] for t in sells],
            marker='v', color='#d50000', s=150, zorder=5, label='Sell',
        )

    ax.set_title(f'{symbol} -- Price with Trading Signals')
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
# Chart 2: Cumulative return curve
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

    if benchmark_data is not None and not benchmark_data.empty:
        bench_col = 'close' if 'close' in benchmark_data.columns else 'Close'
        bench_normalized = benchmark_data[bench_col] / benchmark_data[bench_col].iloc[0] * initial_capital
        ax1.plot(benchmark_data.index, bench_normalized, label='Benchmark (SPY)',
                 color='#FF9800', alpha=0.7)

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
# Chart 3: Position allocation pie
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
# Chart 4: Performance summary table
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
# Chart 5: Agent pipeline architecture diagram
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
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)

    # Box styles
    src = dict(boxstyle='round,pad=0.4', facecolor='#E8F5E9', edgecolor='#2E7D32', linewidth=1.5)
    agent = dict(boxstyle='round,pad=0.5', facecolor='#E3F2FD', edgecolor='#1565C0', linewidth=2)
    exe = dict(boxstyle='round,pad=0.5', facecolor='#FFF3E0', edgecolor='#E65100', linewidth=2)
    sink = dict(boxstyle='round,pad=0.4', facecolor='#F3E5F5', edgecolor='#6A1B9A', linewidth=1.5)
    kw = dict(ha='center', va='center', fontsize=10)
    bkw = dict(ha='center', va='center', fontsize=11, fontweight='bold')

    # Data sources
    ax.text(0.8, 4.5, 'yfinance\n(OHLCV)', bbox=src, **kw)
    ax.text(0.8, 2.0, 'NewsAPI\nFinViz\nAlpha Vantage', bbox=src, fontsize=9, ha='center', va='center')

    # Agents
    ax.text(3.3, 4.5, 'Technical\nAgent', bbox=agent, **bkw)
    ax.text(3.3, 2.0, 'Sentiment\nAgent', bbox=agent, **bkw)
    ax.text(5.8, 3.25, 'Risk\nAgent', bbox=agent, **bkw)
    ax.text(8.0, 3.25, 'Execution\nAgent', bbox=exe, **bkw)

    # Sinks
    ax.text(9.8, 4.5, 'Alpaca\n(Paper)', bbox=sink, **kw)
    ax.text(9.8, 2.0, 'SQLite DB\n+ CSV', bbox=sink, **kw)

    # Arrows
    ap = dict(arrowstyle='->', color='#424242', linewidth=1.8)
    for start, end in [
        ((1.5, 4.5), (2.3, 4.5)),    # yfinance -> Technical
        ((1.5, 2.0), (2.3, 2.0)),    # News -> Sentiment
        ((4.3, 4.2), (4.9, 3.6)),    # Technical -> Risk
        ((4.3, 2.3), (4.9, 2.9)),    # Sentiment -> Risk
        ((6.7, 3.25), (7.1, 3.25)),  # Risk -> Execution
        ((8.9, 3.7), (9.2, 4.2)),    # Execution -> Alpaca
        ((8.9, 2.8), (9.2, 2.3)),    # Execution -> DB
    ]:
        ax.annotate('', xy=end, xytext=start, arrowprops=ap)

    ax.set_title('Agentic Trading System -- Pipeline Architecture',
                 fontsize=16, fontweight='bold', pad=15)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved: {save_path}")


# ============================================================================
# Generate all charts
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
# CLI test entry point
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
