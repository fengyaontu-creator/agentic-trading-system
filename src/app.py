"""
app.py --Streamlit web frontend

Run locally:
    streamlit run src/app.py

Pages:
    1. Login / Register
    2. Dashboard    --portfolio overview, positions, P&L chart
    3. Signals      --today's analysis signals
    4. History      --trade history
    5. Settings     --watchlist + Alpaca credentials
"""

import os
import sqlite3
import sys
import json
from datetime import datetime, timezone

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))
import database as db

# --Page config ---------------------------------------------------------------
st.set_page_config(
    page_title="AI Trading System",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --Session state helpers -----------------------------------------------------
def is_logged_in() -> bool:
    return st.session_state.get("user_id") is not None

def current_user() -> str:
    return st.session_state.get("user_id", "")

def logout():
    st.session_state.pop("user_id", None)
    st.session_state.pop("username", None)
    st.rerun()

# --Auth page -----------------------------------------------------------------
def page_auth():
    st.title("AI Trading System")
    st.markdown("LLM-powered automated trading with multi-user support.")

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)
        if submitted:
            if not username.strip() or not password:
                st.error("Please enter username and password.")
            else:
                user = db.verify_user(username.strip(), password)
                if user:
                    st.session_state["user_id"] = user["user_id"]
                    st.session_state["username"] = user["username"]
                    st.rerun()
                else:
                    st.error("Incorrect username or password.")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("Choose a username")
            new_password = st.text_input("Choose a password", type="password")
            new_password2 = st.text_input("Confirm password", type="password")
            submitted = st.form_submit_button("Create Account", use_container_width=True)
        if submitted:
            if not new_username.strip():
                st.error("Please enter a username.")
            elif not new_password:
                st.error("Please enter a password.")
            elif new_password != new_password2:
                st.error("Passwords do not match.")
            else:
                user_id = new_username.strip().lower().replace(" ", "_")
                existing = db.get_user_by_username(new_username.strip())
                # Also reject distinct usernames that normalize to the same
                # user_id (e.g. "Alice" / "alice"); see api.py register for the
                # full rationale.
                if existing or db.get_user(user_id):
                    st.error("Username already taken.")
                else:
                    try:
                        db.create_user(user_id, new_username.strip(), new_password)
                    except sqlite3.IntegrityError:
                        # Race-safety net for the TOCTOU window between the
                        # pre-check and the INSERT (see api.py register).
                        st.error("Username already taken.")
                    else:
                        st.session_state["user_id"] = user_id
                        st.session_state["username"] = new_username.strip()
                        st.rerun()


# --Sidebar -------------------------------------------------------------------
def sidebar():
    with st.sidebar:
        st.markdown(f"### {st.session_state.get('username', '')}")
        st.markdown("---")
        page = st.radio(
            "Navigate",
            ["Dashboard", "Signals", "History", "Settings"],
            label_visibility="collapsed",
        )
        st.markdown("---")
        if st.button("Logout", use_container_width=True):
            logout()
    return page


# --Dashboard page ------------------------------------------------------------
def page_dashboard():
    user_id = current_user()
    st.title("Dashboard")

    portfolio = db.load_portfolio(user_id)
    if not portfolio:
        st.info("No portfolio data yet. Add your Alpaca credentials in Settings to get started.")
        return

    cash = portfolio["cash"]
    total = portfolio["portfolio_value"]
    pnl = total - 100000
    pnl_pct = pnl / 100000 * 100

    # --KPI row --
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Portfolio Value", f"${total:,.2f}")
    col2.metric("Cash", f"${cash:,.2f}")
    col3.metric("Total P&L", f"${pnl:+,.2f}", f"{pnl_pct:+.2f}%")
    col4.metric("Total Trades", portfolio["total_trades"])

    st.markdown("---")

    # --Positions --
    positions = db.load_positions(user_id)
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("Open Positions")
        if positions:
            df = pd.DataFrame(positions)
            df["market_value"] = df["quantity"] * df["current_price"]
            df["unrealized_pnl"] = (df["current_price"] - df["entry_price"]) * df["quantity"]
            df["pnl_%"] = (df["current_price"] - df["entry_price"]) / df["entry_price"] * 100
            st.dataframe(
                df[["symbol", "quantity", "entry_price", "current_price", "market_value", "unrealized_pnl", "pnl_%"]]
                .rename(columns={
                    "symbol": "Symbol", "quantity": "Qty",
                    "entry_price": "Entry", "current_price": "Current",
                    "market_value": "Value", "unrealized_pnl": "Unr. P&L", "pnl_%": "P&L %"
                })
                .style.format({
                    "Entry": "${:.2f}", "Current": "${:.2f}",
                    "Value": "${:,.2f}", "Unr. P&L": "${:+,.2f}", "P&L %": "{:+.2f}%"
                }),
                use_container_width=True,
            )
        else:
            st.info("No open positions.")

    with col_right:
        st.subheader("Allocation")
        if positions:
            labels = [p["symbol"] for p in positions] + ["Cash"]
            values = [p["quantity"] * p["current_price"] for p in positions] + [cash]
            fig = px.pie(values=values, names=labels, hole=0.4)
            fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=280)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No positions to display.")

    # --Trade history chart --
    st.markdown("---")
    st.subheader("Recent Trade Activity")
    trades = db.get_trade_history(user_id, limit=50)
    if trades:
        df_trades = pd.DataFrame(trades)
        df_trades["timestamp"] = pd.to_datetime(df_trades["timestamp"])
        fig2 = px.scatter(
            df_trades, x="timestamp", y="price",
            color="side", symbol="side",
            color_discrete_map={"BUY": "#00c853", "SELL": "#d50000"},
            hover_data=["symbol", "quantity"],
            title="Trade Executions",
        )
        fig2.update_layout(height=300, margin=dict(t=40, b=0))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No trades yet.")


# --Signals page --------------------------------------------------------------
def page_signals():
    user_id = current_user()
    st.title("Today's Signals")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    signals = db.get_signals(user_id, date=today)

    if not signals:
        st.info(f"No signals for {today} yet. Analysis runs at 07:30 ET.")
        return

    for sig in signals:
        signal = sig["signal"]
        color = {"BUY": "BUY", "SELL": "SELL", "HOLD": "HOLD"}.get(signal, "INFO")
        executed = "Executed" if sig["executed"] else "Pending"

        with st.expander(f"{color} **{sig['symbol']}** --{signal} ({sig['confidence']:.0%} confidence)  {executed}"):
            col1, col2 = st.columns(2)
            col1.metric("Technical Score", f"{sig.get('technical_score', 0):.2f}")
            col2.metric("Sentiment Score", f"{sig.get('sentiment_score', 0):+.2f}")
            if sig.get("reasoning"):
                st.markdown(f"**Reasoning:** {sig['reasoning']}")

    st.markdown("---")
    st.subheader("Signal History")
    all_signals = db.get_signals(user_id, limit=100)
    if all_signals:
        df = pd.DataFrame(all_signals)[["date", "symbol", "signal", "confidence", "executed"]]
        df["confidence"] = df["confidence"].apply(lambda x: f"{x:.0%}")
        df["executed"] = df["executed"].apply(lambda x: "Yes" if x else "No")
        st.dataframe(df, use_container_width=True, hide_index=True)


# --History page --------------------------------------------------------------
def page_history():
    user_id = current_user()
    st.title("Trade History")

    trades = db.get_trade_history(user_id, limit=200)
    if not trades:
        st.info("No trades yet.")
        return

    df = pd.DataFrame(trades)
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")

    # Summary stats
    buys = df[df["side"] == "BUY"]
    sells = df[df["side"] == "SELL"]
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Trades", len(df))
    col2.metric("Buys", len(buys))
    col3.metric("Sells", len(sells))

    st.markdown("---")
    st.dataframe(
        df[["timestamp", "symbol", "side", "quantity", "price"]]
        .rename(columns={
            "timestamp": "Time", "symbol": "Symbol",
            "side": "Side", "quantity": "Qty", "price": "Price"
        })
        .style.format({"Price": "${:.2f}"}),
        use_container_width=True,
        hide_index=True,
    )

    # Volume by symbol
    st.markdown("---")
    st.subheader("Trade Volume by Symbol")
    vol = df.groupby("symbol").size().reset_index(name="trades")
    fig = px.bar(vol, x="symbol", y="trades", color="symbol")
    fig.update_layout(showlegend=False, height=300, margin=dict(t=0, b=0))
    st.plotly_chart(fig, use_container_width=True)


# --Settings page -------------------------------------------------------------
def page_settings():
    user_id = current_user()
    st.title("Settings")

    # --Watchlist --
    st.subheader("Stock Watchlist")
    current_symbols = db.get_user_symbols(user_id)
    symbols_str = st.text_input(
        "Symbols (comma-separated)",
        value=", ".join(current_symbols),
        placeholder="AAPL, TSLA, NVDA",
    )
    if st.button("Save Watchlist", use_container_width=True):
        symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]
        if symbols:
            db.set_user_symbols(user_id, symbols)
            st.success(f"Saved: {', '.join(symbols)}")
        else:
            st.error("Please enter at least one symbol.")

    st.markdown("---")

    # --Trading parameters --
    st.subheader("Trading Parameters")
    params = db.load_user_settings(user_id)

    col_a, col_b = st.columns(2)
    with col_a:
        risk_per_trade = st.slider(
            "Risk per trade (%)", 0.5, 10.0,
            value=params["risk_per_trade"] * 100, step=0.5,
            help="Maximum portfolio percentage risked on a single trade",
        )
        max_concentration = st.slider(
            "Max concentration (%)", 5.0, 50.0,
            value=params["max_concentration"] * 100, step=5.0,
            help="Maximum portfolio percentage in one stock",
        )
        min_confidence = st.slider(
            "Min confidence", 0.1, 0.9,
            value=params["min_confidence"], step=0.05,
            help="Minimum signal confidence required to trade",
        )
    with col_b:
        stop_loss_mult = st.slider(
            "Stop-loss multiplier", 1.0, 5.0,
            value=params["stop_loss_multiplier"], step=0.5,
            help="Volatility multiplier for dynamic stop-loss",
        )
        take_profit_pct = st.slider(
            "Take-profit target (%)", 1.0, 20.0,
            value=params["take_profit_pct"] * 100, step=1.0,
            help="Percentage gain target for take-profit",
        )

    if st.button("Save Trading Parameters", use_container_width=True):
        db.save_user_settings(
            user_id,
            risk_per_trade=risk_per_trade / 100,
            max_concentration=max_concentration / 100,
            stop_loss_multiplier=stop_loss_mult,
            take_profit_pct=take_profit_pct / 100,
            min_confidence=min_confidence,
        )
        st.success("Trading parameters saved.")

    st.markdown("---")

    # --Alpaca credentials --
    st.subheader("Alpaca Paper Trading Credentials")
    creds = db.get_alpaca_credentials(user_id)
    if creds:
        st.success("Alpaca credentials are set.")
        if st.button("Remove credentials"):
            db.save_alpaca_credentials(user_id, "", "")
            st.rerun()

    with st.form("alpaca_form"):
        api_key = st.text_input("Alpaca API Key", type="password", placeholder="PKxxxx...")
        api_secret = st.text_input("Alpaca API Secret", type="password")
        submitted = st.form_submit_button("Save Credentials", use_container_width=True)
    if submitted:
        if api_key.strip() and api_secret.strip():
            db.save_alpaca_credentials(user_id, api_key.strip(), api_secret.strip())
            st.success("Credentials saved and encrypted.")
        else:
            st.error("Both fields are required.")

    st.markdown("---")
    st.caption(f"User ID: `{user_id}` | Next analysis: 07:30 ET | Next trade: 09:50 ET")


# --Main ----------------------------------------------------------------------
def main():
    db.init_db()

    if not is_logged_in():
        page_auth()
        return

    page = sidebar()

    if page == "Dashboard":
        page_dashboard()
    elif page == "Signals":
        page_signals()
    elif page == "History":
        page_history()
    elif page == "Settings":
        page_settings()


if __name__ == "__main__":
    main()

