import { useEffect, useState } from "react";
import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, DashboardData } from "../api";

const COLORS = ["#6366f1", "#22d3ee", "#f59e0b", "#10b981", "#f43f5e", "#a78bfa"];

function MetricCard({ label, value, sub, color }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
      <p className="mb-1 text-xs font-medium text-gray-500">{label}</p>
      <p className={`text-2xl font-bold ${color ?? "text-gray-100"}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-gray-500">{sub}</p>}
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.dashboard()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-500">Loading…</p>;
  if (error) return <p className="text-red-400">{error}</p>;

  const { portfolio, positions, recent_trades } = data!;

  if (!portfolio) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <p className="text-lg font-medium text-gray-300">No portfolio data yet</p>
        <p className="mt-1 text-sm text-gray-500">
          Add your Alpaca credentials in Settings to get started.
        </p>
      </div>
    );
  }

  const pnl = portfolio.portfolio_value - 100_000;
  const pnlPct = (pnl / 100_000) * 100;

  // Pie chart data
  const pieData = [
    ...positions.map((p) => ({
      name: p.symbol,
      value: p.quantity * p.current_price,
    })),
    { name: "Cash", value: portfolio.cash },
  ];

  // Scatter chart data — convert timestamp to epoch ms for recharts
  const tradePoints = recent_trades.map((t) => ({
    x: new Date(t.timestamp).getTime(),
    y: t.price,
    side: t.side,
    symbol: t.symbol,
    qty: t.quantity,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-100">Dashboard</h1>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard label="Portfolio Value" value={`$${portfolio.portfolio_value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
        <MetricCard label="Cash" value={`$${portfolio.cash.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
        <MetricCard
          label="Total P&L"
          value={`${pnl >= 0 ? "+" : ""}$${pnl.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
          sub={`${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%`}
          color={pnl >= 0 ? "text-green-400" : "text-red-400"}
        />
        <MetricCard label="Total Trades" value={String(portfolio.total_trades)} />
      </div>

      {/* Positions + Pie */}
      <div className="grid gap-4 lg:grid-cols-5">
        {/* Positions table */}
        <div className="lg:col-span-3 rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="mb-4 text-sm font-semibold text-gray-300">Open Positions</h2>
          {positions.length === 0 ? (
            <p className="text-sm text-gray-500">No open positions.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-xs text-gray-500">
                  <th className="pb-2 text-left">Symbol</th>
                  <th className="pb-2 text-right">Qty</th>
                  <th className="pb-2 text-right">Entry</th>
                  <th className="pb-2 text-right">Current</th>
                  <th className="pb-2 text-right">Unr. P&L</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p) => {
                  const unr = (p.current_price - p.entry_price) * p.quantity;
                  return (
                    <tr key={p.symbol} className="border-b border-gray-800/50">
                      <td className="py-2 font-medium text-gray-100">{p.symbol}</td>
                      <td className="py-2 text-right text-gray-300">{p.quantity}</td>
                      <td className="py-2 text-right text-gray-400">${p.entry_price.toFixed(2)}</td>
                      <td className="py-2 text-right text-gray-300">${p.current_price.toFixed(2)}</td>
                      <td className={`py-2 text-right font-medium ${unr >= 0 ? "text-green-400" : "text-red-400"}`}>
                        {unr >= 0 ? "+" : ""}${unr.toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Pie chart */}
        <div className="lg:col-span-2 rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="mb-4 text-sm font-semibold text-gray-300">Allocation</h2>
          {pieData.length > 1 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} dataKey="value">
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: number) => `$${v.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} contentStyle={{ background: "#1f2937", border: "none", borderRadius: 8 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-gray-500">No positions to display.</p>
          )}
        </div>
      </div>

      {/* Trade scatter */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold text-gray-300">Recent Trade Executions</h2>
        {tradePoints.length === 0 ? (
          <p className="text-sm text-gray-500">No trades yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <ScatterChart margin={{ top: 5, right: 20, bottom: 5, left: 20 }}>
              <XAxis
                dataKey="x"
                type="number"
                domain={["auto", "auto"]}
                tickFormatter={(v) => new Date(v).toLocaleDateString()}
                tick={{ fill: "#6b7280", fontSize: 11 }}
                axisLine={{ stroke: "#374151" }}
                tickLine={false}
                name="Date"
              />
              <YAxis
                dataKey="y"
                tick={{ fill: "#6b7280", fontSize: 11 }}
                axisLine={{ stroke: "#374151" }}
                tickLine={false}
                tickFormatter={(v) => `$${v}`}
              />
              <Tooltip
                cursor={{ stroke: "#374151" }}
                contentStyle={{ background: "#1f2937", border: "none", borderRadius: 8, fontSize: 12 }}
                formatter={(v: number, name: string) => name === "y" ? [`$${v}`, "Price"] : [v, name]}
                labelFormatter={(label) => new Date(label).toLocaleString()}
              />
              <Scatter
                data={tradePoints.filter((t) => t.side === "BUY")}
                fill="#22c55e"
                name="BUY"
              />
              <Scatter
                data={tradePoints.filter((t) => t.side === "SELL")}
                fill="#ef4444"
                name="SELL"
              />
            </ScatterChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
