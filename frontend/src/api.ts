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
  getControlMode: () => req<{ mode: ControlMode }>("GET", "/api/control_mode"),
  updateControlMode: (mode: Exclude<ControlMode, null>) =>
    req<{ status: string; mode: Exclude<ControlMode, null> }>("PUT", "/api/control_mode", { mode }),
  updateSignalApproval: (symbol: string, approved: boolean) =>
    req<{ status: string; symbol: string; date: string; approved: boolean }>(
      "PUT",
      `/api/signals/${encodeURIComponent(symbol)}/approval`,
      { approved }
    ),
  updatePositionCloseApproval: (symbol: string, approved: boolean) =>
    req<{ status: string; symbol: string; approved: boolean }>(
      "PUT",
      `/api/positions/${encodeURIComponent(symbol)}/close_approval`,
      { approved }
    ),
  updateWatchlist: (symbols: string[]) =>
    req("PUT", "/api/settings/watchlist", { symbols }),
  updateTradingParams: (params: TradingParams) =>
    req<{ status: string; params: TradingParams }>("PUT", "/api/settings/trading", params),
  updateAlpaca: (api_key: string, api_secret: string) =>
    req<{ status: string; alpaca: AlpacaStatus }>("PUT", "/api/settings/alpaca", { api_key, api_secret }),
  deleteAlpaca: () => req<{ status: string; alpaca: AlpacaStatus }>("DELETE", "/api/settings/alpaca"),
  createTelegramBind: () =>
    req<{ status: string; telegram: TelegramStatus }>("POST", "/api/settings/telegram/bind"),
  verifyTelegramBind: () =>
    req<{ status: string; telegram: TelegramStatus; detail?: string }>("POST", "/api/settings/telegram/verify"),
  deleteTelegramBind: () =>
    req<{ status: string; telegram: TelegramStatus }>("DELETE", "/api/settings/telegram"),
  sendTelegramTest: () =>
    req<{ status: string; telegram: TelegramStatus; detail: string }>("POST", "/api/settings/telegram/test"),
};

// -- Types --------------------------------------------------------------------

export type ControlMode = "auto" | "manual" | null;

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
  close_approved?: boolean;
  entry_time?: string;
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
  approved?: boolean;
  approved_at?: string | null;
  created_at?: string;
  date: string;
}

export interface TradingParams {
  risk_per_trade: number;
  max_concentration: number;
  stop_loss_multiplier: number;
  take_profit_pct: number;
  min_confidence: number;
  trailing_stop_high_profit: number;
  trailing_stop_low_profit: number;
  trailing_stop_cushion: number;
  trailing_stop_lock_pct: number;
  strategy: string;
  risk_preference: string;
  last_param_update_at: string | null;
  last_param_update_status: string | null;
  last_param_update_reason: string | null;
  control_mode?: ControlMode;
}

export interface DashboardData {
  portfolio: Portfolio | null;
  positions: Position[];
  recent_trades: Trade[];
  control_mode: ControlMode;
  strategy: string;
}

export interface SignalsData {
  today: Signal[];
  history: Signal[];
}

export interface SettingsData {
  symbols: string[];
  has_alpaca: boolean;
  alpaca: AlpacaStatus;
  telegram: TelegramStatus;
  control_mode: ControlMode;
  trading_params: TradingParams;
}

export interface AlpacaStatus {
  saved: boolean;
  valid: boolean | null;
  detail: string | null;
}

export interface TelegramStatus {
  configured: boolean;
  connected: boolean;
  bot_username: string | null;
  chat_username: string | null;
  chat_first_name: string | null;
  pending_code: string | null;
  pending_expires_at: string | null;
  detail: string | null;
}
