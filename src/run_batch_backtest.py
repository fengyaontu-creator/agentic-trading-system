import json
import pandas as pd
from data_tools import fetch_historical_data, generate_ml_signal
from backtester import Backtester
from agentic_trading import RiskManagementAgent, TradingParams, PortfolioState, Position

def run_batch_backtest(symbols, initial_capital=100000):
    bt = Backtester(initial_capital=initial_capital)
    params = TradingParams(risk_per_trade=0.02, max_concentration=0.10) 
    risk_agent = RiskManagementAgent(llm=None, params=params)

    print(f"Fetching 6 months of data for {len(symbols)} symbols...")
    hist_data = {}
    for sym in symbols:
        try:
            hist_data[sym] = fetch_historical_data(sym, period="6mo", interval="1d")
        except Exception as e:
            print(f"Skip {sym}: {e}")

    all_dates = set()
    for df in hist_data.values():
        all_dates.update(df.index)
    all_dates = sorted(list(all_dates))

    warmup_period = 50 
    
    for i in range(warmup_period, len(all_dates)):
        current_date_ts = all_dates[i]
        current_date_str = str(current_date_ts.date())
        current_prices = {}

        for sym, df in hist_data.items():
            if current_date_ts in df.index:
                current_prices[sym] = float(df.loc[current_date_ts, 'close'])
            else:
                if bt.positions.get(sym):
                    current_prices[sym] = bt.positions[sym].get("current_price", 0)
        
        if not current_prices: continue

        current_portfolio_value = bt.cash + sum(
            pos["quantity"] * current_prices.get(sym, pos["entry_price"]) 
            for sym, pos in bt.positions.items()
        )
        
        current_positions = {
            sym: Position(
                symbol=sym, quantity=pos["quantity"], entry_price=pos["entry_price"], 
                current_price=current_prices.get(sym, pos["entry_price"]), entry_time=current_date_str
            ) for sym, pos in bt.positions.items()
        }
        
        mock_state = PortfolioState(
            cash=bt.cash, positions=current_positions, 
            portfolio_value=current_portfolio_value, total_trades=len(bt.trades)
        )

        for sym in hist_data.keys():
            if sym not in current_prices: continue
            
            df_slice = hist_data[sym].loc[:current_date_ts]
            if len(df_slice) < warmup_period: continue

            current_price = current_prices[sym]
            volatility = float(df_slice['close'].pct_change().dropna().std())

            ml_signal = generate_ml_signal(df_slice)
            signal_payload = {"signal": ml_signal["signal"], "confidence": 0.5 + ml_signal["confidence_boost"]}

            risk_assessment = risk_agent.assess(
                signal=signal_payload,
                portfolio_state=mock_state,
                current_price=current_price,
                volatility=volatility,
                symbol=sym
            )

            side = signal_payload.get("signal", "HOLD")
            should_trade = risk_assessment.get("should_trade", False)
            quantity = int(risk_assessment.get("position_size", 0))

            if should_trade and side in ["BUY", "SELL"] and quantity > 0:
                reason = signal_payload.get("reasoning", "")
                trigger_msg = f" ⚠️ {reason}" if "Triggered" in reason else ""
                print(f"[{current_date_str}] {sym} | {side} {quantity} @ ${current_price:.2f}{trigger_msg}")
                
                bt.record_trade(current_date_str, sym, side, quantity, current_price)
                
                if side == "BUY": mock_state.cash -= (quantity * current_price)
                if side == "SELL": mock_state.cash += (quantity * current_price)

        bt.update_portfolio_value(current_date_str, current_prices)

    print("\n" + "="*50)
    print("BACKTEST COMPLETE")
    print("="*50)
    print(json.dumps(bt.get_report(), indent=2))
    
    bt.export_trades()
    bt.export_portfolio_history()

if __name__ == "__main__":
    test_symbols = ["NVDA", "MSFT", "GOOGL", "META", "AAPL", "GLD", "SLV", "CPER", "JJT", "TSLA"]
    run_batch_backtest(test_symbols)
