import { useEffect, useMemo, useState } from "react";
import {
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

// --- P&L helpers -------------------------------------------------------------

interface SymbolStats {
  symbol: string;
  tradeCount: number;
  buyCount: number;
  sellCount: number;
  realizedPnL: number;
}

interface TradeDetail extends Trade {
  tradePnL: number | null; // null for BUY rows (P&L not yet realized)
  runningPnL: number;
}

function computeSymbolStats(trades: Trade[]): SymbolStats[] {
  const symbolMap: Record<string, Trade[]> = {};
  for (const t of trades) {
    if (!symbolMap[t.symbol]) symbolMap[t.symbol] = [];
    symbolMap[t.symbol].push(t);
  }

  return Object.entries(symbolMap)
    .map(([symbol, symTrades]) => {
      const sorted = [...symTrades].sort(
        (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      );
      const buyQueue: { price: number; qty: number }[] = [];
      let realizedPnL = 0;

      for (const t of sorted) {
        if (t.side === "BUY") {
          buyQueue.push({ price: t.price, qty: t.quantity });
        } else {
          let rem = t.quantity;
          while (rem > 0 && buyQueue.length > 0) {
            const b = buyQueue[0];
            const matched = Math.min(rem, b.qty);
            realizedPnL += (t.price - b.price) * matched;
            b.qty -= matched;
            rem -= matched;
            if (b.qty === 0) buyQueue.shift();
          }
        }
      }

      return {
        symbol,
        tradeCount: sorted.length,
        buyCount: sorted.filter((t) => t.side === "BUY").length,
        sellCount: sorted.filter((t) => t.side === "SELL").length,
        realizedPnL,
      };
    })
    .sort((a, b) => Math.abs(b.realizedPnL) - Math.abs(a.realizedPnL));
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

  const symbolStats = useMemo(() => computeSymbolStats(trades), [trades]);

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
    const stats = symbolStats.find((s) => s.symbol === selectedSymbol)!;
    const chartData = selectedDetails
      .filter((t) => t.tradePnL !== null)
      .map((t, i) => ({
        index: i + 1,
        pnl: parseFloat(t.runningPnL.toFixed(2)),
      }));

    return (
      <div className="space-y-6">
        {/* Header */}
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
            <p
              className={`text-2xl font-bold ${
                stats.realizedPnL >= 0 ? "text-green-400" : "text-red-400"
              }`}
            >
              {stats.realizedPnL >= 0 ? "+" : ""}${stats.realizedPnL.toFixed(2)}
            </p>
          </div>
        </div>

        {/* Stats */}
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

        {/* Running P&L chart */}
        {chartData.length > 0 && (
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h2 className="mb-4 text-sm font-semibold text-gray-300">Running P&amp;L</h2>
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis
                  dataKey="index"
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  label={{ value: "Sell #", position: "insideBottom", offset: -2, fill: "#6b7280", fontSize: 11 }}
                />
                <YAxis
                  tick={{ fill: "#6b7280", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `$${v}`}
                />
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

        {/* Trade table */}
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
                    {new Date(t.timestamp).toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-bold ${
                        t.side === "BUY"
                          ? "bg-green-900/40 text-green-400"
                          : "bg-red-900/40 text-red-400"
                      }`}
                    >
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
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {t.tradePnL !== null ? (
                      <span className={t.runningPnL >= 0 ? "text-green-400" : "text-red-400"}>
                        {t.runningPnL >= 0 ? "+" : ""}${t.runningPnL.toFixed(2)}
                      </span>
                    ) : (
                      <span className="text-gray-600">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // ── Summary view ─────────────────────────────────────────────────────────────
  const buys = trades.filter((t) => t.side === "BUY").length;
  const sells = trades.filter((t) => t.side === "SELL").length;
  const totalPnL = symbolStats.reduce((sum, s) => sum + s.realizedPnL, 0);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-100">Trade History</h1>

      {/* Overall stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: "Total Trades", value: String(trades.length) },
          { label: "Buys",  value: String(buys),  color: "text-green-400" },
          { label: "Sells", value: String(sells), color: "text-red-400" },
          {
            label: "Total Realized P&L",
            value: `${totalPnL >= 0 ? "+" : ""}$${totalPnL.toFixed(2)}`,
            color: totalPnL >= 0 ? "text-green-400" : "text-red-400",
          },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <p className="text-xs text-gray-500">{label}</p>
            <p className={`text-2xl font-bold ${color ?? "text-gray-100"}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Per-symbol table */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800">
          <h2 className="text-sm font-semibold text-gray-300">Performance by Symbol</h2>
          <p className="text-xs text-gray-500 mt-0.5">Click a row to see trade details &amp; P&amp;L breakdown</p>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-xs text-gray-500">
              <th className="px-4 py-3 text-left">Symbol</th>
              <th className="px-4 py-3 text-right">Trades</th>
              <th className="px-4 py-3 text-right">Buys</th>
              <th className="px-4 py-3 text-right">Sells</th>
              <th className="px-4 py-3 text-right">Realized P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {symbolStats.map((s) => (
              <tr
                key={s.symbol}
                onClick={() => setSelectedSymbol(s.symbol)}
                className="border-b border-gray-800/50 hover:bg-gray-800/50 cursor-pointer transition-colors"
              >
                <td className="px-4 py-3 font-medium text-gray-100">
                  <div className="flex items-center gap-2">
                    {s.realizedPnL >= 0 ? (
                      <TrendingUp className="h-4 w-4 text-green-400" />
                    ) : (
                      <TrendingDown className="h-4 w-4 text-red-400" />
                    )}
                    {s.symbol}
                  </div>
                </td>
                <td className="px-4 py-3 text-right text-gray-300">{s.tradeCount}</td>
                <td className="px-4 py-3 text-right text-green-400">{s.buyCount}</td>
                <td className="px-4 py-3 text-right text-red-400">{s.sellCount}</td>
                <td className="px-4 py-3 text-right font-semibold">
                  <span className={s.realizedPnL >= 0 ? "text-green-400" : "text-red-400"}>
                    {s.realizedPnL >= 0 ? "+" : ""}${s.realizedPnL.toFixed(2)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
