"""
api.py -- FastAPI backend

Install:  pip install fastapi uvicorn python-jose[cryptography]
Run:      uvicorn src.api:app --reload --port 8000
          (from project root)
"""

import os
import sys
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))
import database as db

db.init_db()

SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET not set -- add a random string to your .env file")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7

app = FastAPI(title="AI Trading System API", docs_url="/api/docs")

_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()


# --JWT helpers ---------------------------------------------------------------

def _make_token(user_id: str, username: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode({"sub": user_id, "username": username, "exp": exp},
                      SECRET_KEY, algorithm=ALGORITHM)


def _current_user(creds: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return {"user_id": payload["sub"], "username": payload["username"]}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# --Request models -------------------------------------------------------------

class AuthReq(BaseModel):
    username: str
    password: str

class WatchlistReq(BaseModel):
    symbols: list[str]

class AlpacaReq(BaseModel):
    api_key: str
    api_secret: str

class TradingParamsReq(BaseModel):
    risk_per_trade: float = 0.02
    max_concentration: float = 0.10
    stop_loss_multiplier: float = 2.0
    take_profit_pct: float = 0.05
    min_confidence: float = 0.3
    strategy: str = "intraday"


# --Auth -----------------------------------------------------------------------

@app.post("/api/auth/register")
def register(req: AuthReq):
    username = req.username.strip()
    if not username or not req.password:
        raise HTTPException(400, "Username and password required")
    if db.get_user_by_username(username):
        raise HTTPException(400, "Username already taken")
    user_id = username.lower().replace(" ", "_")
    db.create_user(user_id, username, req.password)
    return {"token": _make_token(user_id, username), "user_id": user_id, "username": username}


@app.post("/api/auth/login")
def login(req: AuthReq):
    user = db.verify_user(req.username.strip(), req.password)
    if not user:
        raise HTTPException(401, "Incorrect username or password")
    return {"token": _make_token(user["user_id"], user["username"]),
            "user_id": user["user_id"], "username": user["username"]}


# --Dashboard ------------------------------------------------------------------

@app.get("/api/dashboard")
def dashboard(user=Depends(_current_user)):
    uid = user["user_id"]
    return {
        "portfolio": db.load_portfolio(uid),
        "positions": db.load_positions(uid),
        "recent_trades": db.get_trade_history(uid, limit=50),
    }


# --Signals --------------------------------------------------------------------

@app.get("/api/signals")
def signals(user=Depends(_current_user)):
    uid = user["user_id"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "today": db.get_signals(uid, date=today),
        "history": db.get_signals(uid, limit=100),
    }


# --History --------------------------------------------------------------------

@app.get("/api/history")
def history(user=Depends(_current_user)):
    return {"trades": db.get_trade_history(user["user_id"], limit=200)}


# --Settings -------------------------------------------------------------------

@app.get("/api/settings")
def get_settings(user=Depends(_current_user)):
    uid = user["user_id"]
    creds = db.get_alpaca_credentials(uid)
    return {
        "symbols": db.get_user_symbols(uid),
        "has_alpaca": bool(creds and creds.get("api_key")),
        "trading_params": db.load_user_settings(uid),
    }


@app.put("/api/settings/watchlist")
def update_watchlist(req: WatchlistReq, user=Depends(_current_user)):
    symbols = [s.strip().upper() for s in req.symbols if s.strip()]
    if not symbols:
        raise HTTPException(400, "At least one symbol required")
    db.set_user_symbols(user["user_id"], symbols)
    return {"symbols": symbols}


@app.put("/api/settings/trading")
def update_trading_params(req: TradingParamsReq, user=Depends(_current_user)):
    db.save_user_settings(user["user_id"], **req.model_dump())
    return {"status": "saved", "params": req.model_dump()}


@app.put("/api/settings/alpaca")
def update_alpaca(req: AlpacaReq, user=Depends(_current_user)):
    if not req.api_key.strip() or not req.api_secret.strip():
        raise HTTPException(400, "Both API key and secret are required")
    db.save_alpaca_credentials(user["user_id"], req.api_key.strip(), req.api_secret.strip())
    return {"status": "saved"}


@app.delete("/api/settings/alpaca")
def delete_alpaca(user=Depends(_current_user)):
    db.save_alpaca_credentials(user["user_id"], "", "")
    return {"status": "removed"}


# --Reconciliation ------------------------------------------------------------

@app.get("/api/reconcile")
def reconcile(user=Depends(_current_user)):
    uid = user["user_id"]
    creds = db.get_alpaca_credentials(uid)
    if not creds:
        raise HTTPException(400, "Alpaca credentials not set")
    from broker_alpaca import reconcile_positions
    return reconcile_positions(uid, creds["api_key"], creds["api_secret"])


# --Serve React build in production -------------------------------------------

_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
