import { ChevronDown, ChevronUp } from "lucide-react";
import { useEffect, useState } from "react";
import { api, Signal, SignalsData } from "../api";

const signalStyle: Record<string, string> = {
  BUY:  "bg-green-900/40 text-green-400 border-green-800",
  SELL: "bg-red-900/40 text-red-400 border-red-800",
  HOLD: "bg-yellow-900/40 text-yellow-400 border-yellow-800",
};

function SignalCard({ sig }: { sig: Signal }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-5 py-4 text-left"
      >
        <div className="flex items-center gap-3">
          <span className={`rounded-md border px-2 py-0.5 text-xs font-bold ${signalStyle[sig.signal] ?? "bg-gray-800 text-gray-400 border-gray-700"}`}>
            {sig.signal}
          </span>
          <span className="font-semibold text-gray-100">{sig.symbol}</span>
          <span className="text-sm text-gray-400">
            {(sig.confidence * 100).toFixed(0)}% confidence
          </span>
          {sig.executed && (
            <span className="rounded-full bg-indigo-900/40 border border-indigo-800 px-2 py-0.5 text-xs text-indigo-400">
              Executed
            </span>
          )}
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-gray-500" /> : <ChevronDown className="h-4 w-4 text-gray-500" />}
      </button>
      {open && (
        <div className="border-t border-gray-800 px-5 py-4 space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-gray-500">Technical Score</p>
              <p className="text-lg font-semibold text-gray-100">{(sig.technical_score ?? 0).toFixed(2)}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Sentiment Score</p>
              <p className="text-lg font-semibold text-gray-100">{(sig.sentiment_score ?? 0) > 0 ? "+" : ""}{(sig.sentiment_score ?? 0).toFixed(2)}</p>
            </div>
          </div>
          {sig.reasoning && (
            <p className="text-sm text-gray-400 leading-relaxed">{sig.reasoning}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function SignalsPage() {
  const [data, setData] = useState<SignalsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.signals()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-gray-500">Loading...</p>;
  if (error) return <p className="text-red-400">{error}</p>;

  const { today, history } = data!;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-100">Signals</h1>

      {/* Today */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-gray-400">
          Today - {new Date().toLocaleDateString("en-US", { dateStyle: "full" })}
        </h2>
        {today.length === 0 ? (
          <div className="rounded-xl border border-gray-800 bg-gray-900 px-5 py-8 text-center text-sm text-gray-500">
            No signals yet today. Analysis runs at 07:30 ET.
          </div>
        ) : (
          <div className="space-y-2">
            {today.map((sig, i) => <SignalCard key={i} sig={sig} />)}
          </div>
        )}
      </section>

      {/* History table */}
      {history.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold text-gray-400">Signal History</h2>
          <div className="rounded-xl border border-gray-800 bg-gray-900 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800 text-xs text-gray-500">
                  <th className="px-4 py-3 text-left">Date</th>
                  <th className="px-4 py-3 text-left">Symbol</th>
                  <th className="px-4 py-3 text-left">Signal</th>
                  <th className="px-4 py-3 text-right">Confidence</th>
                  <th className="px-4 py-3 text-right">Executed</th>
                </tr>
              </thead>
              <tbody>
                {history.map((sig, i) => (
                  <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                    <td className="px-4 py-2.5 text-gray-500">{sig.date}</td>
                    <td className="px-4 py-2.5 font-medium text-gray-100">{sig.symbol}</td>
                    <td className="px-4 py-2.5">
                      <span className={`rounded px-2 py-0.5 text-xs font-bold border ${signalStyle[sig.signal] ?? "border-gray-700 text-gray-400"}`}>
                        {sig.signal}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-gray-300">
                      {(sig.confidence * 100).toFixed(0)}%
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      {sig.executed
                        ? <span className="text-green-400">Yes</span>
                        : <span className="text-gray-600">No</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
