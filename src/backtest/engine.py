"""Event-driven OHLC backtest engine."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from position import compute_fill

from .execution import OrderCandidate, PlannedOrder, allocate_orders
from .fills import FillConfig, apply_slippage, calculate_fees, exit_price_for_bar
from .metrics import generate_performance_report
from .strategy import CallableStrategy, Signal, StrategyContext


@dataclass
class BacktestParams:
    risk_per_trade: float = 0.02
    max_concentration: float = 0.10
    stop_loss_multiplier: float = 2.0
    take_profit_pct: float = 0.05
    min_confidence: float = 0.30


@dataclass
class BacktestConfig:
    initial_capital: float = 100_000.0
    fill_timing: str = "next_open"
    intraday_priority: str = "stop_first"
    gap_handling: str = "open_price"
    allocation_method: str = "confidence_weighted"
    allow_shorts: bool = False
    warmup_bars: int = 1
    fill: FillConfig = field(default_factory=FillConfig)


@dataclass
class Position:
    symbol: str
    quantity: int
    entry_price: float
    stop_loss: float
    take_profit: float


@dataclass
class BacktestResult:
    metrics: Dict
    trades: List[Dict]
    portfolio_history: List[Dict]
    final_cash: float
    positions: Dict[str, Position]


class BacktestEngine:
    def __init__(
        self,
        data: Dict[str, pd.DataFrame],
        strategy: CallableStrategy,
        params: Optional[BacktestParams] = None,
        config: Optional[BacktestConfig] = None,
    ):
        self.data = self._prepare_data(data)
        self.strategy = strategy
        self.params = params or BacktestParams()
        self.config = config or BacktestConfig()
        self.cash = float(self.config.initial_capital)
        self.positions: Dict[str, Position] = {}
        self.trades: List[Dict] = []
        self.portfolio_history: List[Dict] = []
        self._pending_signals: List[Signal] = []

    @staticmethod
    def _prepare_data(data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        prepared = {}
        required = {"open", "high", "low", "close"}
        for symbol, frame in data.items():
            normalized = frame.copy()
            normalized.columns = [str(column).lower() for column in normalized.columns]
            missing = required - set(normalized.columns)
            if missing:
                raise ValueError(f"{symbol} missing OHLC columns: {sorted(missing)}")
            normalized.index = pd.to_datetime(normalized.index).tz_localize(None).normalize()
            prepared[symbol] = normalized.sort_index()
        return prepared

    def run(self, start: Optional[str] = None, end: Optional[str] = None) -> BacktestResult:
        dates = self._dates(start, end)
        for index, date in enumerate(dates):
            bars = self._bars_for_date(date)
            if not bars:
                continue

            self._execute_pending_signals(date, bars)
            self._process_intraday_exits(date, bars)
            self._record_portfolio_value(date, bars)

            if index + 1 >= self.config.warmup_bars:
                self._pending_signals = self._generate_signals(date)

        if not self.portfolio_history:
            self._record_portfolio_value(pd.Timestamp.today().normalize(), {})
        series = pd.DataFrame(self.portfolio_history).set_index("date")["value"]
        metrics = generate_performance_report(series, self.trades, self.config.initial_capital)
        return BacktestResult(
            metrics=metrics,
            trades=list(self.trades),
            portfolio_history=list(self.portfolio_history),
            final_cash=round(self.cash, 6),
            positions=dict(self.positions),
        )

    def _dates(self, start: Optional[str], end: Optional[str]) -> List[pd.Timestamp]:
        dates = set()
        start_ts = pd.Timestamp(start).normalize() if start else None
        end_ts = pd.Timestamp(end).normalize() if end else None
        for frame in self.data.values():
            for date in frame.index:
                if start_ts is not None and date < start_ts:
                    continue
                if end_ts is not None and date > end_ts:
                    continue
                dates.add(date)
        return sorted(dates)

    def _bars_for_date(self, date: pd.Timestamp) -> Dict[str, pd.Series]:
        return {symbol: frame.loc[date] for symbol, frame in self.data.items() if date in frame.index}

    def _generate_signals(self, date: pd.Timestamp) -> List[Signal]:
        context = StrategyContext(self.data, date)
        signals = []
        for symbol in sorted(self.data):
            signal = self.strategy.generate_signal(context, symbol)
            if signal is None or signal.side == "HOLD":
                continue
            if signal.confidence < self.params.min_confidence:
                continue
            signals.append(signal)
        return signals

    def _execute_pending_signals(self, date: pd.Timestamp, bars: Dict[str, pd.Series]) -> None:
        candidates = []
        for signal in self._pending_signals:
            bar = bars.get(signal.symbol)
            if bar is None:
                continue
            candidate = self._build_candidate(signal, bar, bars)
            if candidate is not None:
                candidates.append(candidate)

        for order in allocate_orders(candidates, self.cash, self.config.allocation_method):
            trade = self._execute_fill(date, order.symbol, order.side, order.quantity, order.raw_price, order.reason)
            if trade and order.symbol in self.positions:
                self.positions[order.symbol].stop_loss = order.stop_loss
                self.positions[order.symbol].take_profit = order.take_profit
        self._pending_signals = []

    def _build_candidate(
        self,
        signal: Signal,
        bar: pd.Series,
        bars: Dict[str, pd.Series],
    ) -> Optional[OrderCandidate]:
        side = signal.side
        existing = self.positions.get(signal.symbol)
        if side == "SELL" and existing and existing.quantity > 0:
            return OrderCandidate(signal.symbol, "SELL", signal.confidence, float(bar["open"]), 0, 0, existing.quantity, signal.reason)
        if side == "BUY" and existing and existing.quantity < 0:
            return OrderCandidate(signal.symbol, "BUY", signal.confidence, float(bar["open"]), 0, 0, abs(existing.quantity), signal.reason)
        if existing is not None:
            return None
        if side == "SELL" and not self.config.allow_shorts:
            return None

        raw_price = float(bar["open"])
        history = self.data[signal.symbol].loc[self.data[signal.symbol].index < bar.name]
        volatility = float(history["close"].pct_change().dropna().std()) if len(history) > 1 else 0.01
        if pd.isna(volatility) or volatility <= 0:
            volatility = 0.01

        if side == "BUY":
            stop_loss = round(raw_price * (1 - volatility * self.params.stop_loss_multiplier), 6)
            take_profit = round(raw_price * (1 + self.params.take_profit_pct), 6)
            risk_per_share = raw_price - stop_loss
        else:
            stop_loss = round(raw_price * (1 + volatility * self.params.stop_loss_multiplier), 6)
            take_profit = round(raw_price * (1 - self.params.take_profit_pct), 6)
            risk_per_share = stop_loss - raw_price

        if risk_per_share <= 0:
            return None

        equity = self._portfolio_value(bars)
        risk_qty = int(equity * self.params.risk_per_trade * signal.confidence / risk_per_share)
        concentration_room = equity * self.params.max_concentration - self._symbol_exposure(signal.symbol, raw_price)
        concentration_qty = int(max(0, concentration_room) / raw_price)
        max_quantity = min(risk_qty, concentration_qty)
        if side == "BUY":
            max_quantity = min(max_quantity, int(self.cash / raw_price))
        if max_quantity <= 0:
            return None

        return OrderCandidate(
            symbol=signal.symbol,
            side=side,
            confidence=signal.confidence,
            raw_price=raw_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            max_quantity=max_quantity,
            reason=signal.reason,
        )

    def _process_intraday_exits(self, date: pd.Timestamp, bars: Dict[str, pd.Series]) -> None:
        for symbol, position in list(self.positions.items()):
            bar = bars.get(symbol)
            if bar is None:
                continue
            raw_price, reason = exit_price_for_bar(
                position.quantity,
                position.stop_loss,
                position.take_profit,
                bar,
                self.config.intraday_priority,
            )
            if raw_price is None:
                continue
            side = "SELL" if position.quantity > 0 else "BUY"
            self._execute_fill(date, symbol, side, abs(position.quantity), raw_price, reason)

    def _execute_fill(
        self,
        date: pd.Timestamp,
        symbol: str,
        side: str,
        quantity: int,
        raw_price: float,
        reason: str = "",
    ) -> Dict:
        fill_price = apply_slippage(raw_price, side, self.config.fill)
        old = self.positions.get(symbol)
        old_qty = old.quantity if old else 0
        old_entry = old.entry_price if old else 0.0
        new_qty, new_entry, cash_delta, realized_pnl = compute_fill(old_qty, old_entry, side, quantity, fill_price)
        fees = calculate_fees(side, quantity, fill_price, self.config.fill)
        self.cash += cash_delta - fees

        if new_qty == 0:
            self.positions.pop(symbol, None)
        else:
            stop_loss = old.stop_loss if old else fill_price
            take_profit = old.take_profit if old else fill_price
            self.positions[symbol] = Position(symbol, new_qty, new_entry, stop_loss, take_profit)

        trade = {
            "date": str(pd.Timestamp(date).date()),
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "raw_price": round(raw_price, 6),
            "price": round(fill_price, 6),
            "value": round(quantity * fill_price, 6),
            "fees": fees,
            "pnl": round(realized_pnl - fees, 6),
            "reason": reason,
        }
        self.trades.append(trade)
        return trade

    def _record_portfolio_value(self, date: pd.Timestamp, bars: Dict[str, pd.Series]) -> None:
        self.portfolio_history.append({
            "date": str(pd.Timestamp(date).date()),
            "value": self._portfolio_value(bars),
        })

    def _portfolio_value(self, bars: Dict[str, pd.Series]) -> float:
        value = self.cash
        for symbol, position in self.positions.items():
            bar = bars.get(symbol)
            mark = float(bar["close"]) if bar is not None else position.entry_price
            value += position.quantity * mark
        return round(float(value), 6)

    def _symbol_exposure(self, symbol: str, price: float) -> float:
        position = self.positions.get(symbol)
        if position is None:
            return 0.0
        return abs(position.quantity * price)
