"""
data_tools.py — 市场数据获取 + 技术指标计算 + ML信号增强
Owner: Person A (Nora)

替换模板中 fetch_market_data 里的随机数据，改用 yfinance 真实数据。
同时加入 ML/量化策略增强信号（RSI/MACD 策略逻辑）。
"""

import os
import json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
from langchain_core.tools import tool


# ============================================================================
# 核心数据获取工具（替换模板中的 @tool fetch_market_data）
# ============================================================================

@tool
def fetch_market_data(symbol: str, period: str = "3mo", interval: str = "1h") -> str:
    """
    Fetch real historical market data for a given symbol using yfinance.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL', 'GOOGL')
        period: Data period (e.g., '1mo', '3mo', '6mo', '1y')
        interval: Data interval (e.g., '1h', '1d')

    Returns:
        JSON string with OHLCV data and calculated indicators
    """
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            return json.dumps({"error": f"No data found for {symbol}"})

        # Standardize column names to lowercase
        df.columns = [c.lower() for c in df.columns]

        # --- Calculate Technical Indicators ---
        df = calculate_technical_indicators(df)

        # --- Build ML/Quantitative Signal ---
        ml_signal = generate_ml_signal(df)

        # Return last 5 rows with key metrics
        recent = df.tail(5).fillna(0)
        cols = ['close', 'sma_20', 'sma_50', 'rsi', 'macd', 'signal_line',
                'bb_upper', 'bb_lower']
        available_cols = [c for c in cols if c in recent.columns]

        result = {
            'symbol': symbol,
            'current_price': float(df['close'].iloc[-1]),
            'volume': int(df['volume'].iloc[-1]),
            'volatility': float(df['close'].pct_change().std()),
            'recent_data': recent[available_cols].to_dict('records'),
            'indicators_summary': {
                'SMA_20': float(df['sma_20'].iloc[-1]) if 'sma_20' in df else 0,
                'SMA_50': float(df['sma_50'].iloc[-1]) if 'sma_50' in df else 0,
                'RSI': float(df['rsi'].iloc[-1]) if 'rsi' in df else 50,
                'MACD': float(df['macd'].iloc[-1]) if 'macd' in df else 0,
                'Signal_Line': float(df['signal_line'].iloc[-1]) if 'signal_line' in df else 0,
                'price_vs_BB_upper': float(df['close'].iloc[-1] - df['bb_upper'].iloc[-1]) if 'bb_upper' in df else 0,
                'price_vs_BB_lower': float(df['close'].iloc[-1] - df['bb_lower'].iloc[-1]) if 'bb_lower' in df else 0,
            },
            'ml_signal': ml_signal,
        }

        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        return json.dumps({"error": str(e), "symbol": symbol})


# ============================================================================
# 技术指标计算
# ============================================================================

def calculate_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate standard technical indicators on OHLCV DataFrame.

    Indicators computed:
    - SMA 20 / SMA 50
    - EMA 12 / EMA 26
    - MACD + Signal Line + Histogram
    - RSI (14-period)
    - Bollinger Bands (20-period, 2 std)

    Args:
        df: DataFrame with columns ['open', 'high', 'low', 'close', 'volume']

    Returns:
        DataFrame with indicator columns added
    """
    # Moving Averages
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_50'] = df['close'].rolling(window=50).mean()
    df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
    df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()

    # MACD
    df['macd'] = df['ema_12'] - df['ema_26']
    df['signal_line'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_histogram'] = df['macd'] - df['signal_line']

    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # Bollinger Bands
    df['bb_middle'] = df['close'].rolling(window=20).mean()
    bb_std = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
    df['bb_lower'] = df['bb_middle'] - (bb_std * 2)

    return df


# ============================================================================
# ML / 量化策略增强信号
# ============================================================================

def generate_ml_signal(df: pd.DataFrame) -> dict:
    """
    Generate a quantitative signal based on multiple indicator rules.
    This supplements the LLM's judgment with rule-based logic.

    Rules:
    - RSI < 30 and MACD crossover (bullish) → BUY boost
    - RSI > 70 and MACD crossunder (bearish) → SELL boost
    - SMA 20 > SMA 50 (golden cross) → bullish bias
    - SMA 20 < SMA 50 (death cross) → bearish bias
    - Price below lower BB → potential mean reversion BUY
    - Price above upper BB → potential mean reversion SELL

    Args:
        df: DataFrame with technical indicators already calculated

    Returns:
        dict with signal, confidence_boost, and reasons
    """
    if len(df) < 50:
        return {"signal": "HOLD", "confidence_boost": 0.0, "reasons": ["Insufficient data"]}

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    reasons = []
    score = 0  # positive = bullish, negative = bearish

    # --- RSI signals ---
    rsi = latest.get('rsi', 50)
    if rsi < 30:
        score += 2
        reasons.append(f"RSI oversold ({rsi:.1f})")
    elif rsi > 70:
        score -= 2
        reasons.append(f"RSI overbought ({rsi:.1f})")

    # --- MACD crossover ---
    macd_now = latest.get('macd', 0)
    signal_now = latest.get('signal_line', 0)
    macd_prev = prev.get('macd', 0)
    signal_prev = prev.get('signal_line', 0)

    if macd_prev < signal_prev and macd_now > signal_now:
        score += 2
        reasons.append("MACD bullish crossover")
    elif macd_prev > signal_prev and macd_now < signal_now:
        score -= 2
        reasons.append("MACD bearish crossunder")

    # --- SMA crossover ---
    sma_20 = latest.get('sma_20', 0)
    sma_50 = latest.get('sma_50', 0)
    if sma_20 > sma_50:
        score += 1
        reasons.append("SMA 20 > SMA 50 (bullish trend)")
    elif sma_20 < sma_50:
        score -= 1
        reasons.append("SMA 20 < SMA 50 (bearish trend)")

    # --- Bollinger Band signals ---
    price = latest.get('close', 0)
    bb_lower = latest.get('bb_lower', 0)
    bb_upper = latest.get('bb_upper', 0)

    if price < bb_lower:
        score += 1
        reasons.append("Price below lower Bollinger Band")
    elif price > bb_upper:
        score -= 1
        reasons.append("Price above upper Bollinger Band")

    # --- Convert score to signal ---
    if score >= 3:
        signal = "BUY"
        confidence_boost = min(score * 0.05, 0.2)
    elif score <= -3:
        signal = "SELL"
        confidence_boost = min(abs(score) * 0.05, 0.2)
    else:
        signal = "HOLD"
        confidence_boost = 0.0

    return {
        "signal": signal,
        "confidence_boost": round(confidence_boost, 2),
        "score": score,
        "reasons": reasons
    }


# ============================================================================
# 辅助函数：批量获取数据（用于回测）
# ============================================================================

def fetch_historical_data(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """
    Fetch historical data as a DataFrame (for backtesting, not as a tool).

    Args:
        symbol: Stock ticker
        period: e.g., '6mo', '1y', '2y'
        interval: e.g., '1d', '1h'

    Returns:
        DataFrame with OHLCV + technical indicators
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    df.columns = [c.lower() for c in df.columns]
    df = calculate_technical_indicators(df)
    return df


# ============================================================================
# 测试入口
# ============================================================================

if __name__ == "__main__":
    # Quick test
    print("Testing fetch_market_data for AAPL...")
    result = fetch_market_data.invoke({"symbol": "AAPL", "period": "1mo", "interval": "1d"})
    data = json.loads(result)
    print(json.dumps(data, indent=2))
