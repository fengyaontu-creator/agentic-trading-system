import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowLeft, TrendingDown, TrendingUp } from "lucide-react";
import { api, Trade } from "../api";
import { formatLocal } from "../utils/time";

// --- P&L helpers -------------------------------------------------------------

interface SymbolStats {
  symbol: string;
  tradeCount: number;
  buyCount: number;
  sellCount: number;
  realizedPnL: number;
}

interface TradeDetail extends Trade {
  tradePnL: number | null;
  runningPnL: number;
}

function computeSymbolStats(trades: Trade[]): Record<string, SymbolStats> {
  const map: Record<string, SymbolStats> = {};
  for (const t of trades) {
    if (!map[t.symbol]) {
      map[t.symbol] = { symbol: t.symbol, tradeCount: 0, buyCount: 0, sellCount: 0, realizedPnL: 0 };
    }
    map[t.symbol].tradeCount++;
    if (t.side === "BUY") map[t.symbol].buyCount++;
    else map[t.symbol].sellCount++;
  }

  // FIFO P&L per symbol
  for (const symbol of Object.keys(map)) {
    const sorted = trades
      .filter((t) => t.symbol === symbol)
      .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
    const buyQueue: { price: number; qty: number }[] = [];
    let pnl = 0;
    for (const t of sorted) {
      if (t.side === "BUY") {
        buyQueue.push({ price: t.price, qty: t.quantity });
      } else {
        let rem = t.quantity;
        while (rem > 0 && buyQueue.length > 0) {
          const b = buyQueue[0];
          const matched = Math.min(rem, b.qty);
          pnl += (t.price - b.price) * matched;
          b.qty -= matched;
          rem -= matched;
          if (b.qty === 0) buyQueue.shift();
        }
      }
    }
    map[symbol].realizedPnL = pnl;
  }
  return map;
}

function computeTradeDetails(trades: Trade[]): TradeDetail[] {
  const sorted = [...trades].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );
  const buyQueue: { price: number; qty: number }[] = [];
  let runningPnL = 0;

  return sorted.map((t) => {
    if (t.side === "BUY") {
      buyQueue.push({ price: t.price, qty: t.quantity });
      return { ...t, tradePnL: null, runningPnL };
    } else {
      let rem = t.quantity;
      let pnl = 0;
      while (rem > 0 && buyQueue.length > 0) {
        const b = buyQueue[0];
        const matched = Math.min(rem, b.qty);
        pnl += (t.price - b.price) * matched;
        b.qty -= matched;
        rem -= matched;
        if (b.qty === 0) buyQueue.shift();
      }
      runningPnL += pnl;
      return { ...t, tradePnL: pnl, runningPnL };
    }
  });
}

// --- Component ---------------------------------------------------------------

export default function HistoryPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  useEffect(() => {
    api
      .history()
      .then((d) => setTrades(d.trades))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const symbolStatsMap = useMemo(() => computeSymbolStats(trades), [trades]);

  const selectedDetails = useMemo(() => {
    if (!selectedSymbol) return null;
    return computeTradeDetails(trades.filter((t) => t.symbol === selectedSymbol));
  }, [trades, selectedSymbol]);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (trades.length === 0) {
    return (
      <div>
        <h1 className="mb-4 text-xl font-bold text-gray-100">Trade History</h1>
        <p className="text-sm text-gray-500">No trades yet.</p>
      </div>
    );
  }

  // ── Detail view ──────────────────────────────────────────────────────────────
  if (selectedSymbol && selectedDetails) {
    const stats = symbolStatsMap[selectedSymbol];
    const chartData = selectedDetails
      .filter((t) => t.tradePnL !== null)
      .map((t, i) => ({ index: i + 1, pnl: parseFloat(t.runningPnL.toFixed(2)) }));

    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSelectedSymbol(null)}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-800 hover:text-gray-100 transition-colors"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-bold text-gray-100">{selectedSymbol}</h1>
            <p className="text-xs text-gray-500">{stats.tradeCount} trades</p>
          </div>
          <div className="ml-auto text-right">
            <p className="text-xs text-gray-500">Realized P&amp;L</p>
            <p className={`text-2xl font-bold ${stats.realizedPnL >= 0 ? "text-green-400" : "text-red-400"}`}>
              {stats.realizedPnL >= 0 ? "+" : ""}${stats.realizedPnL.toFixed(2)}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          {[
            { label: "Total Trades", value: stats.tradeCount },
            { label: "Buys",  value: stats.buyCount,  color: "text-green-400" },
            { label: "Sells", value: stats.sellCount, color: "text-red-400" },
          ].map(({ label, value, color }) => (
            <div key={label} className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <p className="text-xs text-gray-500">{label}</p>
              <p className={`text-2xl font-bold ${color ?? "text-gray-100"}`}>{value}</p>
            </div>
          ))}
        </div>

        {chartData.length > 0 && (
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h2 className="mb-4 text-sm font-semibold text-gray-300">Running P&amp;L</h2>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="index" tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} />
                <Tooltip
                  contentStyle={{ background: "#1f2937", border: "none", borderRadius: 8, fontSize: 12 }}
                  formatter={(v: number) => [`$${v.toFixed(2)}`, "P&L"]}
                  labelFormatter={(i) => `Sell #${i}`}
                />
                <Line
                  type="monotone"
                  dataKey="pnl"
                  stroke={stats.realizedPnL >= 0 ? "#4ade80" : "#f87171"}
                  strokeWidth={2}
                  dot={{ r: 3, fill: stats.realizedPnL >= 0 ? "#4ade80" : "#f87171" }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-xs text-gray-500">
                <th className="px-4 py-3 text-left">Time</th>
                <th className="px-4 py-3 text-left">Side</th>
                <th className="px-4 py-3 text-right">Qty</th>
                <th className="px-4 py-3 text-right">Price</th>
                <th className="px-4 py-3 text-right">Trade P&amp;L</th>
                <th className="px-4 py-3 text-right">Running P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {selectedDetails.map((t, i) => (
                <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                  <td className="px-4 py-2.5 text-gray-500 text-xs whitespace-nowrap">
                    {formatLocal(t.timestamp)}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded px-2 py-0.5 text-xs font-bold ${
                      t.side === "BUY" ? "bg-green-900/40 text-green-400" : "bg-red-900/40 text-red-400"
                    }`}>
                      {t.side}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right text-gray-300">{t.quantity}</td>
                  <td className="px-4 py-2.5 text-right text-gray-300">${t.price.toFixed(2)}</td>
                  <td className="px-4 py-2.5 text-right">
                    {t.tradePnL !== null ? (
                      <span className={t.tradePnL >= 0 ? "text-green-400" : "text-red-400"}>
                        {t.tradePnL >= 0 ? "+" : ""}${t.tradePnL.toFixed(2)}
                      </span>
                    ) : <span className="text-gray-600">—</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {t.tradePnL !== null ? (
                      <span className={t.runningPnL >= 0 ? "text-green-400" : "text-red-400"}>
                        {t.runningPnL >= 0 ? "+" : ""}${t.runningPnL.toFixed(2)}
                      </span>
                    ) : <span className="text-gray-600">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // ── Summary view (original layout + click entries) ────────────────────────
  const buys = trades.filter((t) => t.side === "BUY").length;
  const sells = trades.filter((t) => t.side === "SELL").length;

  const volMap: Record<string, number> = {};
  trades.forEach((t) => { volMap[t.symbol] = (volMap[t.symbol] ?? 0) + 1; });
  const volData = Object.entries(volMap)
    .map(([symbol, count]) => ({ symbol, count }))
    .sort((a, b) => b.count - a.count);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-100">Trade History</h1>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Total Trades", value: trades.length },
          { label: "Buys",  value: buys,  color: "text-green-400" },
          { label: "Sells", value: sells, color: "text-red-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <p className="text-xs text-gray-500">{label}</p>
            <p className={`text-2xl font-bold ${color ?? "text-gray-100"}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Trade table — symbol is clickable */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-xs text-gray-500">
              <th className="px-4 py-3 text-left">Time</th>
              <th className="px-4 py-3 text-left">Symbol</th>
              <th className="px-4 py-3 text-left">Side</th>
              <th className="px-4 py-3 text-right">Qty</th>
              <th className="px-4 py-3 text-right">Price</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                <td className="px-4 py-2.5 text-gray-500 text-xs">
                  {formatLocal(t.timestamp)}
                </td>
                <td className="px-4 py-2.5">
                  <button
                    onClick={() => setSelectedSymbol(t.symbol)}
                    className="flex items-center gap-1.5 font-medium text-gray-100 hover:text-indigo-400 transition-colors"
                  >
                    {symbolStatsMap[t.symbol]?.realizedPnL >= 0
                      ? <TrendingUp className="h-3 w-3 text-green-400" />
                      : <TrendingDown className="h-3 w-3 text-red-400" />}
                    {t.symbol}
                  </button>
                </td>
                <td className="px-4 py-2.5">
                  <span className={`rounded px-2 py-0.5 text-xs font-bold ${
                    t.side === "BUY" ? "bg-green-900/40 text-green-400" : "bg-red-900/40 text-red-400"
                  }`}>
                    {t.side}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right text-gray-300">{t.quantity}</td>
                <td className="px-4 py-2.5 text-right text-gray-300">${t.price.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Bar chart — bars are clickable */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-1 text-sm font-semibold text-gray-300">Trade Volume by Symbol</h2>
        <p className="mb-4 text-xs text-gray-500">Click a bar to see symbol details</p>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={volData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="symbol" tick={{ fill: "#6b7280", fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#6b7280", fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ background: "#1f2937", border: "none", borderRadius: 8, fontSize: 12 }}
              cursor={{ fill: "#ffffff08" }}
            />
            <Bar
              dataKey="count"
              fill="#6366f1"
              radius={[4, 4, 0, 0]}
              name="Trades"
              style={{ cursor: "pointer" }}
              onClick={(data) => setSelectedSymbol(data.symbol)}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
