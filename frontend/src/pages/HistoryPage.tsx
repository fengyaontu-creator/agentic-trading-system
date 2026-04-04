import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, Trade } from "../api";

export default function HistoryPage() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.history()
      .then((d) => setTrades(d.trades))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-500">Loading…</p>;
  if (error) return <p className="text-red-400">{error}</p>;
  if (trades.length === 0) {
    return (
      <div>
        <h1 className="mb-4 text-xl font-bold text-gray-100">Trade History</h1>
        <p className="text-sm text-gray-500">No trades yet.</p>
      </div>
    );
  }

  const buys = trades.filter((t) => t.side === "BUY").length;
  const sells = trades.filter((t) => t.side === "SELL").length;

  // Volume by symbol
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
          { label: "Buys", value: buys, color: "text-green-400" },
          { label: "Sells", value: sells, color: "text-red-400" },
        ].map(({ label, value, color }) => (
          <div key={label} className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <p className="text-xs text-gray-500">{label}</p>
            <p className={`text-2xl font-bold ${color ?? "text-gray-100"}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Table */}
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
                  {new Date(t.timestamp).toLocaleString()}
                </td>
                <td className="px-4 py-2.5 font-medium text-gray-100">{t.symbol}</td>
                <td className="px-4 py-2.5">
                  <span className={`rounded px-2 py-0.5 text-xs font-bold ${
                    t.side === "BUY"
                      ? "bg-green-900/40 text-green-400"
                      : "bg-red-900/40 text-red-400"
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

      {/* Bar chart */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold text-gray-300">Trade Volume by Symbol</h2>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={volData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="symbol" tick={{ fill: "#6b7280", fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#6b7280", fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ background: "#1f2937", border: "none", borderRadius: 8, fontSize: 12 }}
              cursor={{ fill: "#ffffff08" }}
            />
            <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} name="Trades" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
