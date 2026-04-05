import { CheckCircle, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, SettingsData, TradingParams } from "../api";

type NumericParam = Exclude<keyof TradingParams, "strategy">;

const PARAM_LABELS: Record<NumericParam, { label: string; step: string; min: string; max: string }> = {
  risk_per_trade:       { label: "Risk per Trade (%)",    step: "0.005", min: "0.005", max: "0.2" },
  max_concentration:    { label: "Max Concentration (%)", step: "0.01",  min: "0.01",  max: "0.5" },
  stop_loss_multiplier: { label: "Stop-Loss Multiplier",  step: "0.1",   min: "0.5",   max: "5" },
  take_profit_pct:      { label: "Take-Profit (%)",       step: "0.01",  min: "0.01",  max: "0.5" },
  min_confidence:       { label: "Min Confidence",        step: "0.05",  min: "0",      max: "1" },
};

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

  useEffect(() => {
    api.settings()
      .then((s) => {
        setSettings(s);
        setSymbolsStr(s.symbols.join(", "));
        setTradingParams(s.trading_params);
      })
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
      setWatchlistMsg(`Saved: ${symbols.join(", ")}`);
    } catch (err: unknown) {
      setWatchlistErr(err instanceof Error ? err.message : "Failed");
    }
  }

  async function saveAlpaca(e: React.FormEvent) {
    e.preventDefault();
    setAlpacaMsg(""); setAlpacaErr("");
    try {
      await api.updateAlpaca(alpacaKey, alpacaSecret);
      setAlpacaMsg("Credentials saved and encrypted.");
      setSettings((s) => s ? { ...s, has_alpaca: true } : s);
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
      setParamsMsg("Trading parameters saved.");
    } catch (err: unknown) {
      setParamsErr(err instanceof Error ? err.message : "Failed");
    }
  }

  async function removeAlpaca() {
    try {
      await api.deleteAlpaca();
      setSettings((s) => s ? { ...s, has_alpaca: false } : s);
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

      {/* Trading Parameters */}
      {tradingParams && (
        <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
          <h2 className="mb-4 text-sm font-semibold text-gray-300">Trading Parameters</h2>
          <form onSubmit={saveTradingParams} className="space-y-3">
            {(Object.keys(PARAM_LABELS) as NumericParam[]).map((key) => {
              const cfg = PARAM_LABELS[key];
              return (
                <div key={key}>
                  <label className="mb-1.5 block text-xs text-gray-500">{cfg.label}</label>
                  <input
                    type="number"
                    step={cfg.step}
                    min={cfg.min}
                    max={cfg.max}
                    value={tradingParams[key]}
                    onChange={(e) =>
                      setTradingParams({ ...tradingParams, [key]: parseFloat(e.target.value) || 0 })
                    }
                    className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-gray-100 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              );
            })}
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
              Save Parameters
            </button>
          </form>
        </div>
      )}

      {/* Alpaca */}
      <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
        <h2 className="mb-4 text-sm font-semibold text-gray-300">Alpaca Paper Trading</h2>

        {settings?.has_alpaca && (
          <div className="mb-4 flex items-center justify-between rounded-lg border border-green-800 bg-green-900/20 px-4 py-3">
            <div className="flex items-center gap-2 text-sm text-green-400">
              <CheckCircle className="h-4 w-4" />
              Credentials are set
            </div>
            <button
              onClick={removeAlpaca}
              className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300"
            >
              <Trash2 className="h-3 w-3" />
              Remove
            </button>
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
          Credentials are encrypted with Fernet before being stored in the database.
        </p>
      </div>

      <p className="text-xs text-gray-600">
        Analyze: 07:30 ET &nbsp;|&nbsp; Trade: 09:30 ET &nbsp;|&nbsp; Close: 15:30 ET
      </p>
    </div>
  );
}
