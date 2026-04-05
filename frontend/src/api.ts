const BASE = "";

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("token");
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: authHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

export const api = {
  login: (username: string, password: string) =>
    req<{ token: string; user_id: string; username: string }>(
      "POST", "/api/auth/login", { username, password }
    ),
  register: (username: string, password: string) =>
    req<{ token: string; user_id: string; username: string }>(
      "POST", "/api/auth/register", { username, password }
    ),
  dashboard: () => req<DashboardData>("GET", "/api/dashboard"),
  signals: () => req<SignalsData>("GET", "/api/signals"),
  history: () => req<{ trades: Trade[] }>("GET", "/api/history"),
  settings: () => req<SettingsData>("GET", "/api/settings"),
  updateWatchlist: (symbols: string[]) =>
    req("PUT", "/api/settings/watchlist", { symbols }),
  updateAlpaca: (api_key: string, api_secret: string) =>
    req("PUT", "/api/settings/alpaca", { api_key, api_secret }),
  deleteAlpaca: () => req("DELETE", "/api/settings/alpaca"),
  updateTradingParams: (params: TradingParams) =>
    req("PUT", "/api/settings/trading", params),
};

// -- Types --------------------------------------------------------------------

export interface Portfolio {
  cash: number;
  portfolio_value: number;
  total_trades: number;
}

export interface Position {
  symbol: string;
  quantity: number;
  entry_price: number;
  current_price: number;
}

export interface Trade {
  timestamp: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
}

export interface Signal {
  symbol: string;
  signal: string;
  confidence: number;
  technical_score?: number;
  sentiment_score?: number;
  reasoning?: string;
  executed: boolean;
  date: string;
}

export interface DashboardData {
  portfolio: Portfolio | null;
  positions: Position[];
  recent_trades: Trade[];
}

export interface SignalsData {
  today: Signal[];
  history: Signal[];
}

export interface TradingParams {
  risk_per_trade: number;
  max_concentration: number;
  stop_loss_multiplier: number;
  take_profit_pct: number;
  min_confidence: number;
  strategy: string;
}

export interface SettingsData {
  symbols: string[];
  has_alpaca: boolean;
  trading_params: TradingParams;
}
