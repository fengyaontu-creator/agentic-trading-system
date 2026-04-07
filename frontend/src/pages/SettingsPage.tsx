import { AlertTriangle, CheckCircle, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, SettingsData, TradingParams } from "../api";

const AI_PARAM_LABELS: { key: keyof TradingParams; label: string; format: (v: number) => string }[] = [
  { key: "risk_per_trade",       label: "Risk per Trade",             format: (v) => `${(v * 100).toFixed(1)}%` },
  { key: "max_concentration",    label: "Max Concentration",          format: (v) => `${(v * 100).toFixed(0)}%` },
  { key: "stop_loss_multiplier", label: "Stop-Loss Multiplier",       format: (v) => `${v.toFixed(1)}x` },
  { key: "take_profit_pct",      label: "Take-Profit Target",         format: (v) => `${(v * 100).toFixed(1)}%` },
  { key: "min_confidence",       label: "Min Confidence",             format: (v) => `${(v * 100).toFixed(0)}%` },
  { key: "trailing_stop_high_profit", label: "Aggressive Trail Trigger", format: (v) => `${(v * 100).toFixed(0)}%` },
  { key: "trailing_stop_low_profit",  label: "Moderate Trail Trigger",   format: (v) => `${(v * 100).toFixed(0)}%` },
  { key: "trailing_stop_cushion",     label: "Trail Cushion",            format: (v) => `${(v * 100).toFixed(1)}%` },
  { key: "trailing_stop_lock_pct",    label: "Trail Lock-in",            format: (v) => `${(v * 100).toFixed(1)}%` },
];

function OptimizationStatus({ params }: { params: TradingParams }) {
  const status = params.last_param_update_status;
  const at = params.last_param_update_at;
  const reason = params.last_param_update_reason;

  if (!status || !at) {
    return (
      <p className="mb-3 text-xs text-gray-500">
        Not yet optimized - values will refresh on the next analyze session.
      </p>
    );
  }

  const when = new Date(at).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });

  if (status === "ok") {
    return (
      <p className="mb-3 text-xs text-green-500">
        Last updated: {when}
      </p>
    );
  }
  if (status === "failed") {
    return (
      <p className="mb-3 text-xs text-red-400">
        Last optimization failed ({when}){reason ? `: ${reason}` : ""}
      </p>
    );
  }
  if (status === "skipped") {
    return (
      <p className="mb-3 text-xs text-yellow-500">
        Last run skipped ({when}){reason ? `: ${reason}` : ""}
      </p>
    );
  }
  return (
    <p className="mb-3 text-xs text-gray-500">
      Status: {status} ({when})
    </p>
  );
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [loading, setLoading] = useState(true);

  // Watchlist state
  const [symbolsStr, setSymbolsStr] = useState("");
  const [watchlistMsg, setWatchlistMsg] = useState("");
  const [watchlistErr, setWatchlistErr] = useState("");

  // Alpaca state
  const [alpacaKey, setAlpacaKey] = useState("");
  const [alpacaSecret, setAlpacaSecret] = useState("");
  const [alpacaMsg, setAlpacaMsg] = useState("");
  const [alpacaErr, setAlpacaErr] = useState("");

  // Trading params state
  const [tradingParams, setTradingParams] = useState<TradingParams | null>(null);
  const [paramsMsg, setParamsMsg] = useState("");
  const [paramsErr, setParamsErr] = useState("");

  async function refreshSettings() {
    const fresh = await api.settings();
    setSettings(fresh);
    setSymbolsStr(fresh.symbols.join(", "));
    setTradingParams(fresh.trading_params);
    return fresh;
  }

  useEffect(() => {
    refreshSettings()
      .catch((e) => console.error(e))
      .finally(() => setLoading(false));
  }, []);

  async function saveWatchlist(e: React.FormEvent) {
    e.preventDefault();
    setWatchlistMsg(""); setWatchlistErr("");
    const symbols = symbolsStr.split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
    if (!symbols.length) return setWatchlistErr("Enter at least one symbol.");
    try {
      await api.updateWatchlist(symbols);
      const fresh = await refreshSettings();
      setWatchlistMsg(`Saved: ${fresh.symbols.join(", ")}`);
    } catch (err: unknown) {
      setWatchlistErr(err instanceof Error ? err.message : "Failed");
    }
  }

  async function saveAlpaca(e: React.FormEvent) {
    e.preventDefault();
    setAlpacaMsg(""); setAlpacaErr("");
    try {
      const result = await api.updateAlpaca(alpacaKey, alpacaSecret);
      await refreshSettings();
      setAlpacaMsg(result.alpaca.detail ?? "Credentials saved and verified.");
      setAlpacaKey(""); setAlpacaSecret("");
    } catch (err: unknown) {
      setAlpacaErr(err instanceof Error ? err.message : "Failed");
    }
  }

  async function saveTradingParams(e: React.FormEvent) {
    e.preventDefault();
    setParamsMsg(""); setParamsErr("");
    if (!tradingParams) return;
    try {
      await api.updateTradingParams(tradingParams);
      await refreshSettings();
      setParamsMsg("Trading parameters saved.");
    } catch (err: unknown) {
      setParamsErr(err instanceof Error ? err.message : "Failed");
    }
  }

  async function removeAlpaca() {
    try {
      await api.deleteAlpaca();
      await refreshSettings();
      setAlpacaMsg("Credentials removed.");
    } catch (err: unknown) {
      setAlpacaErr(err instanceof Error ? err.message : "Failed");
    }
  }

  if (loading) return <p className="text-gray-500">Loading...</p>;

  return (
    <div className="max-w-xl space-y-6">
      <h1 className="text-xl font-bold text-gray-100">Settings</h1>

      {/* Watchlist */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold text-gray-300">Stock Watchlist</h2>
        <form onSubmit={saveWatchlist} className="space-y-3">
          <div>
            <label className="mb-1.5 block text-xs text-gray-500">
              Symbols (comma-separated)
            </label>
            <input
              type="text"
              value={symbolsStr}
              onChange={(e) => setSymbolsStr(e.target.value)}
              placeholder="AAPL, TSLA, NVDA"
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          {watchlistMsg && <p className="text-sm text-green-400">{watchlistMsg}</p>}
          {watchlistErr && <p className="text-sm text-red-400">{watchlistErr}</p>}
          <button
            type="submit"
            className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition-colors"
          >
            Save Watchlist
          </button>
        </form>
      </div>

      {/* Trading Preferences */}
      {tradingParams && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="mb-4 text-sm font-semibold text-gray-300">Trading Preferences</h2>
          <form onSubmit={saveTradingParams} className="space-y-3">
            <div>
              <label className="mb-1.5 block text-xs text-gray-500">Risk Preference</label>
              <select
                value={tradingParams.risk_preference}
                onChange={(e) => setTradingParams({ ...tradingParams, risk_preference: e.target.value })}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-gray-100 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              >
                <option value="conservative">Conservative - Minimize drawdowns</option>
                <option value="moderate">Moderate - Balanced risk/reward</option>
                <option value="aggressive">Aggressive - Maximize gains</option>
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs text-gray-500">Strategy</label>
              <select
                value={tradingParams.strategy}
                onChange={(e) => setTradingParams({ ...tradingParams, strategy: e.target.value })}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-gray-100 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
              >
                <option value="intraday">Intraday (flatten at close)</option>
                <option value="swing">Swing / Multi-day (hold overnight)</option>
              </select>
            </div>
            {paramsMsg && <p className="text-sm text-green-400">{paramsMsg}</p>}
            {paramsErr && <p className="text-sm text-red-400">{paramsErr}</p>}
            <button
              type="submit"
              className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition-colors"
            >
              Save Preferences
            </button>
          </form>

          {/* AI-optimized parameters (read-only) */}
          <div className="mt-4 border-t border-gray-800 pt-4">
            <h3 className="mb-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
              AI-Optimized Parameters
            </h3>
            <p className="mb-2 text-xs text-gray-600">
              These values are automatically tuned by AI based on your risk preference, market conditions, and trade history. Refreshed before each analyze session.
            </p>
            <OptimizationStatus params={tradingParams} />
            <div className="grid grid-cols-2 gap-2">
              {AI_PARAM_LABELS.map(({ key, label, format }) => (
                <div key={key} className="rounded-lg bg-gray-800/50 px-3 py-2">
                  <span className="block text-xs text-gray-500">{label}</span>
                  <span className="text-sm font-mono text-gray-300">
                    {format(tradingParams[key] as number)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Alpaca */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold text-gray-300">Alpaca Paper Trading</h2>

        {settings?.alpaca.saved ? (
          <div
            className={`mb-4 flex items-center justify-between rounded-lg px-4 py-3 ${
              settings.alpaca.valid
                ? "border border-green-800 bg-green-900/20"
                : "border border-red-800 bg-red-900/20"
            }`}
          >
            <div
              className={`flex items-start gap-2 text-sm ${
                settings.alpaca.valid ? "text-green-400" : "text-red-400"
              }`}
            >
              {settings.alpaca.valid ? (
                <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" />
              ) : (
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              )}
              <div>
                <p>
                  {settings.alpaca.valid
                    ? "Credentials saved and verified"
                    : "Credentials saved but invalid"}
                </p>
                {settings.alpaca.detail && (
                  <p className="mt-1 text-xs opacity-80">{settings.alpaca.detail}</p>
                )}
              </div>
            </div>
            <button
              onClick={removeAlpaca}
              className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300"
            >
              <Trash2 className="h-3 w-3" />
              Remove
            </button>
          </div>
        ) : (
          <div className="mb-4 rounded-lg border border-gray-800 bg-gray-950/40 px-4 py-3 text-sm text-gray-500">
            No Alpaca credentials saved yet.
          </div>
        )}

        <form onSubmit={saveAlpaca} className="space-y-3">
          <div>
            <label className="mb-1.5 block text-xs text-gray-500">API Key</label>
            <input
              type="password"
              value={alpacaKey}
              onChange={(e) => setAlpacaKey(e.target.value)}
              placeholder="PKxxxx..."
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs text-gray-500">API Secret</label>
            <input
              type="password"
              value={alpacaSecret}
              onChange={(e) => setAlpacaSecret(e.target.value)}
              placeholder="Secret key"
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-gray-100 placeholder-gray-600 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
            />
          </div>
          {alpacaMsg && <p className="text-sm text-green-400">{alpacaMsg}</p>}
          {alpacaErr && <p className="text-sm text-red-400">{alpacaErr}</p>}
          <button
            type="submit"
            className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white hover:bg-indigo-500 transition-colors"
          >
            Save Credentials
          </button>
        </form>

        <p className="mt-3 text-xs text-gray-600">
          Credentials are encrypted with Fernet before being stored in the database and are validated against Alpaca when saved.
        </p>
      </div>

      <p className="text-xs text-gray-600">
        Analyze: 07:30 ET &nbsp;|&nbsp; Trade: 09:50 ET &nbsp;|&nbsp; Close: 15:30 ET
      </p>
    </div>
  );
}
