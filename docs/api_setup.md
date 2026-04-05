# API Setup Guide

## Step 1: Copy environment template

```bash
cp .env.example .env
```

## Step 2: Fill in your API keys

Edit `.env` and set the following variables:

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | LLM access via OpenRouter |
| `NEWS_API_KEY` | News headlines for sentiment analysis |
| `ALPHA_VANTAGE_API_KEY` | Market data fallback |
| `ALPACA_API_KEY` | Broker (paper or live) — or set per-user via UI |
| `ALPACA_API_SECRET` | Broker secret |
| `DB_ENCRYPTION_KEY` | Fernet key for encrypting stored credentials |
| `JWT_SECRET` | Secret for signing auth tokens (required) |
| `CORS_ORIGINS` | Comma-separated allowed origins (default: `http://localhost:5173,http://localhost:3000`) |

Generate a Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Step 3: Verify

```python
from dotenv import load_dotenv
import os

load_dotenv()
print("OpenRouter:", "OK" if os.getenv("OPENROUTER_API_KEY") else "MISSING")
print("News API:", "OK" if os.getenv("NEWS_API_KEY") else "MISSING")
print("JWT Secret:", "OK" if os.getenv("JWT_SECRET") else "MISSING")
print("Encryption:", "OK" if os.getenv("DB_ENCRYPTION_KEY") else "MISSING")
```

## Security Reminders

- **Never** commit `.env` to Git
- **Never** hardcode API keys in source code
- Rotate keys if accidentally exposed
